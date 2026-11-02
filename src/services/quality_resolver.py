"""
Production Quality Resolution Engine for Julius Music Platform.
Implements resolution and ranking of candidate audio streams according to policies:
- "best_lossless" (default): Verified recording > FLAC/Lossless > 24-bit > Sample Rate > Provider
- "highest_hires": Highest available bit depth / sample rate among verified recordings
- "cd_quality": Standard 16-bit / 44.1 kHz FLAC preferred for bandwidth optimization
"""

from __future__ import annotations

import logging
import os
from typing import List, Optional

from src.music.models import ProviderCandidate, QualityResult
from src.music.quality import QualityEngine

logger = logging.getLogger("julius.services.quality_resolver")


class QualityResolver:
    """Production quality resolver choosing the best candidate according to policy."""

    def __init__(self, default_policy: str = "best_lossless") -> None:
        self.default_policy = os.getenv("MUSIC_DEFAULT_QUALITY_POLICY", default_policy)
        self._engine = QualityEngine()

    def resolve(
        self,
        candidates: List[ProviderCandidate],
        policy: Optional[str] = None
    ) -> Optional[QualityResult]:
        """
        Evaluate candidates against quality policy, returning QualityResult for the optimal candidate.
        """
        active_policy = policy or self.default_policy
        if not candidates:
            return None

        # Filter strictly for lossless FLAC
        lossless_candidates = [
            c for c in candidates
            if (c.format or "").upper() == "FLAC" and (c.codec or "").lower() == "flac" and c.availability
        ]

        if not lossless_candidates:
            logger.debug("No lossless FLAC candidates available among %d candidates", len(candidates))
            return None

        def ranking_key(c: ProviderCandidate):
            # 1. Match identity score (must be the verified recording first)
            match_tier = round(c.score, 1)

            bit_depth = c.bit_depth or 16
            sample_rate = c.sample_rate or 44100

            if active_policy == "cd_quality":
                # Prefer 16-bit / 44.1 kHz
                is_cd = 1 if (bit_depth == 16 and sample_rate == 44100) else 0
                return (match_tier, is_cd, -bit_depth, -sample_rate)
            else:
                # Default "best_lossless" & "highest_hires": 24-bit > 16-bit, then higher sample rate
                return (match_tier, bit_depth, sample_rate)

        ranked = sorted(lossless_candidates, key=ranking_key, reverse=True)
        best = ranked[0]

        return QualityResult(
            candidate=best,
            policy=active_policy,
            codec=best.codec,
            bit_depth=best.bit_depth,
            sample_rate=best.sample_rate,
            channels=best.channels,
            quality_badge=best.quality_badge,
            is_valid_lossless=True
        )

    def rank_candidates(
        self,
        candidates: List[ProviderCandidate],
        policy: Optional[str] = None
    ) -> List[ProviderCandidate]:
        """Rank candidates according to quality policy."""
        active_policy = policy or self.default_policy
        if not candidates:
            return []

        def ranking_key(c: ProviderCandidate):
            is_flac = 1 if (c.format or "").upper() == "FLAC" else 0
            bit_depth = c.bit_depth or 16
            sample_rate = c.sample_rate or 44100
            return (is_flac, bit_depth, sample_rate)

        return sorted(candidates, key=ranking_key, reverse=True)

    select_best = resolve


# Global singleton
quality_resolver = QualityResolver()
