"""
Lossless Quality Engine for Julius.
Enforces genuine FLAC audio requirements and ranks lossless candidates.
Strictly prioritizes recording match identity over raw resolution,
then orders by bit-depth (24-bit vs 16-bit) and sample rate (192, 96, 48, 44.1 kHz).
"""

from __future__ import annotations

import logging
import os
from typing import List, Optional

from src.music.models import ProviderCandidate

logger = logging.getLogger("julius.music.quality")


class QualityEngine:
    """Production quality selector for lossless audio ingestion."""

    def __init__(
        self,
        policy: Optional[str] = None,
        provider_preference: Optional[List[str]] = None
    ) -> None:
        self.policy = policy or os.getenv("MUSIC_QUALITY_POLICY", "flac_only")
        # Preferred providers in order if qualities are otherwise equal
        self.provider_preference = provider_preference or ["spotiflac", "local", "qobuz", "tidal", "deezer", "stream"]

    def is_lossless(self, candidate: ProviderCandidate) -> bool:
        """Verify format is genuinely lossless."""
        fmt = (candidate.format or "").upper()
        codec = (candidate.codec or "").lower()
        if self.policy == "flac_only":
            return fmt == "FLAC" and codec == "flac"
        return fmt in ("FLAC", "ALAC", "WAV", "AIFF")

    def rank_candidates(self, candidates: List[ProviderCandidate]) -> List[ProviderCandidate]:
        """
        Rank candidates by:
        1. Match identity score (must be exact/verified recording first)
        2. Lossless validation
        3. Bit depth (24-bit > 16-bit)
        4. Sample rate (192kHz > 96kHz > 48kHz > 44.1kHz)
        5. Provider preference
        """
        lossless_candidates = [c for c in candidates if self.is_lossless(c)]
        if not lossless_candidates:
            return []

        def sort_key(c: ProviderCandidate):
            # Identity score is the foundation (tier 1)
            # Candidates with score < 75 are heavily de-prioritized
            score_tier = round(c.score, 1)

            # Bit depth tier (24 > 16)
            bit_depth = c.bit_depth or 16

            # Sample rate tier (192000 > 96000 > 48000 > 44100)
            sample_rate = c.sample_rate or 44100

            # Provider preference ranking (lower index = higher priority)
            try:
                prov_pref = -self.provider_preference.index(c.provider.lower())
            except ValueError:
                prov_pref = -99

            return (
                score_tier,       # Match score first!
                bit_depth,        # 24-bit vs 16-bit
                sample_rate,      # Hi-Res sample rate
                prov_pref,        # Provider preference
            )

        ranked = sorted(lossless_candidates, key=sort_key, reverse=True)
        return ranked

    def select_best(self, candidates: List[ProviderCandidate]) -> Optional[ProviderCandidate]:
        """Return the single optimal lossless candidate or None if none qualify."""
        ranked = self.rank_candidates(candidates)
        return ranked[0] if ranked else None


# Global quality engine
quality_engine = QualityEngine()
