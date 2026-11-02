"""
Production Track Matching Engine for Julius Music Platform.
Implements 3-tier matching priority:
- Tier 1: ISRC exact match (+100)
- Tier 2: Recording identity (title, primary artist, album, duration, track number)
- Tier 3: Normalized metadata comparison (Unicode, punctuation, featuring handling,
  strict version segregation for Live, Remaster, Acoustic, Remix).
"""

from __future__ import annotations

import logging
import os
import re
import unicodedata
from difflib import SequenceMatcher
from typing import List, Optional, Set, Tuple

from src.music.models import MatchResult, ProviderCandidate, Track
from src.music.matching import MatchEngine

logger = logging.getLogger("julius.services.music_matcher")

VERSION_TOKENS = {
    "remix": re.compile(r"\b(remix|rmx|club mix|extended mix|dub mix)\b", re.IGNORECASE),
    "live": re.compile(r"\b(live|concert|in concert|live at)\b", re.IGNORECASE),
    "acoustic": re.compile(r"\b(acoustic|unplugged|stripped)\b", re.IGNORECASE),
    "instrumental": re.compile(r"\b(instrumental|karaoke|backing track)\b", re.IGNORECASE),
    "radio_edit": re.compile(r"\b(radio edit|radio mix|single version)\b", re.IGNORECASE),
    "remaster": re.compile(r"\b(remastered|remaster|\d{4} remaster)\b", re.IGNORECASE),
}

FEATURING_PATTERN = re.compile(r"\b(feat\.?|ft\.?|featuring)\b.*$", re.IGNORECASE)


class MusicMatcher:
    """Production matcher calculating granular confidence scores for audio candidates."""

    def __init__(self, threshold: float = 75.0) -> None:
        self.threshold = float(os.getenv("MUSIC_MATCH_THRESHOLD", str(threshold)))
        self._engine = MatchEngine(match_threshold=self.threshold)

    @staticmethod
    def normalize_text(text: str, strip_featuring: bool = False) -> str:
        """Normalize Unicode, lowercasing, punctuation, and optionally strip featuring artist."""
        if not text:
            return ""
        # Normalize Unicode accents (e.g. é -> e)
        nfkd = unicodedata.normalize("NFKD", text)
        ascii_text = nfkd.encode("ASCII", "ignore").decode("utf-8")
        
        if strip_featuring:
            ascii_text = FEATURING_PATTERN.sub("", ascii_text)

        # Remove punctuation, keep alphanumeric and spaces
        cleaned = re.sub(r"[^\w\s]", " ", ascii_text).lower()
        return " ".join(cleaned.split())

    @staticmethod
    def extract_version_tags(text: str) -> Set[str]:
        tags = set()
        for name, pattern in VERSION_TOKENS.items():
            if pattern.search(text or ""):
                tags.add(name)
        return tags

    def evaluate_candidate(self, track: Track, candidate: ProviderCandidate) -> MatchResult:
        """
        Evaluate candidate against canonical track across 3 tiers.
        Returns MatchResult with score, confidence level, and explanation reasons.
        """
        score = 0.0
        reasons: List[str] = []

        # ── Critical Incompatibility Check ────────────────────────────────────
        track_versions = self.extract_version_tags(f"{track.title} {track.album}")
        cand_versions = self.extract_version_tags(f"{candidate.title} {candidate.album}")

        # Core incompatible versions (Live, Remix, Acoustic, Instrumental)
        incompatible = {"live", "remix", "acoustic", "instrumental"}
        track_incompat = track_versions & incompatible
        cand_incompat = cand_versions & incompatible
        if track_incompat != cand_incompat:
            reasons.append(f"Incompatible version mismatch: {track_incompat} vs {cand_incompat}")
            return MatchResult(candidate=candidate, score=0.0, confidence="none", reasons=reasons)

        # ── Tier 1: ISRC Exact Match ──────────────────────────────────────────
        if track.isrc and candidate.isrc:
            t_isrc = track.isrc.strip().upper()
            c_isrc = candidate.isrc.strip().upper()
            if t_isrc == c_isrc:
                score += 100.0
                reasons.append(f"Tier 1: Exact ISRC match ({t_isrc})")
                return MatchResult(candidate=candidate, score=score, confidence="high", reasons=reasons)
            else:
                score -= 20.0
                reasons.append(f"Tier 1: Differing ISRCs ({t_isrc} != {c_isrc})")

        # ── Tier 2: Recording Identity ─────────────────────────────────────────
        norm_track_title = self.normalize_text(track.title, strip_featuring=True)
        norm_cand_title = self.normalize_text(candidate.title, strip_featuring=True)

        if norm_track_title == norm_cand_title:
            score += 35.0
            reasons.append("Tier 2: Exact recording title match")
        else:
            similarity = SequenceMatcher(None, norm_track_title, norm_cand_title).ratio()
            title_points = similarity * 30.0
            score += title_points
            reasons.append(f"Tier 2: Title similarity {similarity:.2%}")

        # Primary Artist Comparison
        t_artist = self.normalize_text(track.album_artist or (track.artists[0] if track.artists else ""))
        c_artist = self.normalize_text(candidate.album_artist or (candidate.artists[0] if candidate.artists else ""))
        if t_artist and c_artist:
            if t_artist == c_artist:
                score += 25.0
                reasons.append("Tier 2: Exact primary artist match")
            elif t_artist in c_artist or c_artist in t_artist:
                score += 20.0
                reasons.append("Tier 2: Partial primary artist match")
            else:
                sim = SequenceMatcher(None, t_artist, c_artist).ratio()
                score += sim * 20.0
                reasons.append(f"Tier 2: Artist similarity {sim:.2%}")

        # Album Comparison
        norm_track_album = self.normalize_text(track.album)
        norm_cand_album = self.normalize_text(candidate.album)
        if norm_track_album and norm_cand_album:
            if norm_track_album == norm_cand_album:
                score += 15.0
                reasons.append("Tier 2: Exact album match")
            elif norm_track_album in norm_cand_album or norm_cand_album in norm_track_album:
                score += 10.0
                reasons.append("Tier 2: Album containment match")

        # Duration Proximity
        if track.duration_ms and candidate.duration_ms:
            diff_ms = abs(track.duration_ms - candidate.duration_ms)
            if diff_ms <= 3000:  # <= 3 seconds
                score += 15.0
                reasons.append(f"Tier 2: Duration match within {diff_ms}ms")
            elif diff_ms <= 8000:  # <= 8 seconds
                score += 8.0
                reasons.append(f"Tier 2: Duration close ({diff_ms}ms diff)")
            elif diff_ms > 20000:  # > 20 seconds difference
                score -= 15.0
                reasons.append(f"Tier 2: Significant duration discrepancy ({diff_ms}ms)")

        # ── Tier 3: Version & Track Number Compatibility ──────────────────────
        if track_versions == cand_versions and track_versions:
            score += 10.0
            reasons.append(f"Tier 3: Version tag identity matched ({track_versions})")

        # Bound score between 0.0 and 100.0
        final_score = max(0.0, min(100.0, score))

        if final_score >= 85.0:
            confidence = "high"
        elif final_score >= self.threshold:
            confidence = "medium"
        elif final_score >= 50.0:
            confidence = "low"
        else:
            confidence = "none"

        return MatchResult(
            candidate=candidate,
            score=final_score,
            confidence=confidence,
            reasons=reasons
        )

    match = evaluate_candidate

    def find_best_match(
        self,
        track: Track,
        candidates: List[ProviderCandidate]
    ) -> Optional[MatchResult]:
        """
        Evaluate candidate list, filtering below threshold, returning best confident candidate.
        """
        if not candidates:
            return None

        results = [self.evaluate_candidate(track, c) for c in candidates]
        confident_results = [r for r in results if r.is_confident]

        if not confident_results:
            return None

        # Sort primarily by match score descending
        confident_results.sort(key=lambda r: r.score, reverse=True)
        return confident_results[0]


# Global singleton
music_matcher = MusicMatcher()
