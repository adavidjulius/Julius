"""
Hierarchical Track Matching Engine for Julius.
Computes match confidence using ISRC verification, recording version identity,
duration proximity, and textual normalization. Prevents false positive matching
of remixes, live recordings, radio edits, and alternate takes.
"""

from __future__ import annotations

import logging
import os
import re
from difflib import SequenceMatcher
from typing import List, Optional, Tuple

from src.music.models import ProviderCandidate, Track

logger = logging.getLogger("julius.music.matching")

# Regex pattern for version modifiers in titles
VERSION_PATTERNS = {
    "remix": re.compile(r"\b(remix|rmx|club mix|extended mix|dub mix)\b", re.IGNORECASE),
    "live": re.compile(r"\b(live|concert|in concert|at \w+ stadium|live at)\b", re.IGNORECASE),
    "acoustic": re.compile(r"\b(acoustic|unplugged|stripped)\b", re.IGNORECASE),
    "instrumental": re.compile(r"\b(instrumental|karaoke|backing track)\b", re.IGNORECASE),
    "radio_edit": re.compile(r"\b(radio edit|radio mix|single version)\b", re.IGNORECASE),
    "remaster": re.compile(r"\b(remastered|remaster|\d{4} remaster)\b", re.IGNORECASE),
    "deluxe": re.compile(r"\b(deluxe|bonus track|anniversary edition)\b", re.IGNORECASE),
}


class MatchEngine:
    """Production matching engine evaluating candidate audio recordings against canonical tracks."""

    def __init__(
        self,
        match_threshold: Optional[float] = None,
        weight_isrc: float = 50.0,
        weight_version: float = 20.0,
        weight_artist: float = 10.0,
        weight_album: float = 10.0,
        weight_duration: float = 5.0,
        weight_title: float = 5.0,
    ) -> None:
        self.threshold = float(
            match_threshold or os.getenv("MUSIC_MATCH_THRESHOLD", "80.0")
        )
        self.weight_isrc = weight_isrc
        self.weight_version = weight_version
        self.weight_artist = weight_artist
        self.weight_album = weight_album
        self.weight_duration = weight_duration
        self.weight_title = weight_title

    def clean_string(self, text: str) -> str:
        """Strip brackets, punctuation, leading/trailing whitespace for comparison."""
        if not text:
            return ""
        # Remove parenthetical contents like (feat. X) or - Remastered 2011
        cleaned = re.sub(r"[\(\[\{].*?[\)\]\}]", "", text)
        cleaned = re.sub(r"[-–—].*$", "", cleaned)
        cleaned = re.sub(r"[^\w\s]", "", cleaned)
        return " ".join(cleaned.lower().split())

    def extract_version_tags(self, text: str) -> set[str]:
        """Detect all version tags present in a title."""
        tags = set()
        for tag, pattern in VERSION_PATTERNS.items():
            if pattern.search(text):
                tags.add(tag)
        return tags

    def calculate_score(self, track: Track, candidate: ProviderCandidate) -> float:
        """
        Score a candidate against the canonical track.
        Returns a confidence score from 0.0 to 100.0.
        """
        # Step 1: Version tag check
        # If one is marked 'remix' or 'live' or 'acoustic' and the other is not, immediately penalize
        track_tags = self.extract_version_tags(f"{track.title} {track.album}")
        cand_tags = self.extract_version_tags(f"{candidate.title} {candidate.album}")

        # Incompatible recording versions cannot match
        critical_tags = {"remix", "live", "acoustic", "instrumental"}
        if (track_tags & critical_tags) != (cand_tags & critical_tags):
            logger.debug(
                "Version mismatch for '%s' vs '%s': %s != %s",
                track.title, candidate.title, track_tags, cand_tags
            )
            return 0.0

        score = 0.0

        # 1. Exact ISRC check
        if track.isrc and candidate.isrc:
            if track.isrc.strip().upper() == candidate.isrc.strip().upper():
                score += self.weight_isrc
            else:
                # Different ISRCs usually indicate different recordings
                score -= 15.0
        elif not track.isrc and not candidate.isrc:
            # Neither has ISRC; baseline credit when relying on metadata + duration
            score += 35.0
        elif track.isrc or candidate.isrc:
            # One has ISRC, one doesn't; neutral, rely on textual and duration matching
            score += 25.0  # Partial credit if ISRC was not available for verification

        # 2. Version consistency
        if track_tags == cand_tags:
            score += self.weight_version

        # 3. Artist identity
        track_artists = [a.lower().strip() for a in track.artists]
        cand_artists = [a.lower().strip() for a in candidate.artists]
        if track_artists and cand_artists:
            # Check exact primary artist match
            if track_artists[0] == cand_artists[0]:
                score += self.weight_artist
            elif any(ta in cand_artists for ta in track_artists):
                score += self.weight_artist * 0.8
            else:
                ratio = SequenceMatcher(None, track_artists[0], cand_artists[0]).ratio()
                score += self.weight_artist * ratio

        # 4. Album match
        clean_tr_album = self.clean_string(track.album)
        clean_cd_album = self.clean_string(candidate.album)
        if clean_tr_album and clean_cd_album:
            if clean_tr_album == clean_cd_album:
                score += self.weight_album
            else:
                album_ratio = SequenceMatcher(None, clean_tr_album, clean_cd_album).ratio()
                score += self.weight_album * album_ratio

        # 5. Duration proximity
        # Duration within 3 seconds (+5), within 10 seconds (+2), >15 seconds difference penalized
        if track.duration_ms > 0 and candidate.duration_ms > 0:
            diff_sec = abs(track.duration_ms - candidate.duration_ms) / 1000.0
            if diff_sec <= 3.0:
                score += self.weight_duration
            elif diff_sec <= 10.0:
                score += self.weight_duration * 0.6
            elif diff_sec <= 20.0:
                score += self.weight_duration * 0.3
            elif diff_sec > 25.0:
                score -= 15.0  # Heavy penalty for major duration divergence (e.g. wrong track)

        # 6. Title normalization & string similarity
        clean_tr_title = self.clean_string(track.title)
        clean_cd_title = self.clean_string(candidate.title)
        if clean_tr_title == clean_cd_title:
            score += self.weight_title
        else:
            ratio = SequenceMatcher(None, clean_tr_title, clean_cd_title).ratio()
            score += self.weight_title * ratio

        return max(0.0, min(100.0, score))

    def evaluate_candidates(
        self,
        track: Track,
        candidates: List[ProviderCandidate]
    ) -> Tuple[List[ProviderCandidate], bool]:
        """
        Score and sort candidates.
        Returns (ranked_candidates, is_ambiguous).
        is_ambiguous is True if multiple candidates are near the threshold or top score is close.
        """
        if not candidates:
            return [], False

        scored: List[ProviderCandidate] = []
        for c in candidates:
            s = self.calculate_score(track, c)
            c.score = round(s, 2)
            if c.score >= self.threshold:
                scored.append(c)

        # Sort descending by score
        scored.sort(key=lambda x: x.score, reverse=True)

        if not scored:
            return [], False

        # Detect ambiguity: if top 2 candidates have scores within 3 points of each other
        is_ambiguous = False
        if len(scored) >= 2:
            if abs(scored[0].score - scored[1].score) < 3.0 and scored[0].provider_id != scored[1].provider_id:
                is_ambiguous = True

        return scored, is_ambiguous


# Global match engine
match_engine = MatchEngine()
