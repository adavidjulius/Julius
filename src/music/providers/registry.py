"""
Provider Registry for Julius Music Subsystem.
Manages provider lifecycles, configuration toggles, and multi-provider searches.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, List, Optional

from src.music.models import ProviderCandidate, Track
from src.music.providers.base import MusicProvider
from src.music.providers.local_ingest import LocalIngestProvider
from src.music.providers.official_stream import OfficialStreamProvider
from src.music.providers.spotiflac_cli import SpotiFlacCliProvider

logger = logging.getLogger("julius.music.providers.registry")


class ProviderRegistry:
    """Central registry of all authorized lossless music providers."""

    def __init__(self) -> None:
        self._providers: Dict[str, MusicProvider] = {}
        self._register_default_providers()

    def _register_default_providers(self) -> None:
        # Register core adapters
        self.register(SpotiFlacCliProvider())
        self.register(LocalIngestProvider())
        self.register(OfficialStreamProvider())

    def register(self, provider: MusicProvider) -> None:
        """Register a provider instance."""
        self._providers[provider.name.lower()] = provider
        logger.info("Registered music provider '%s' (available=%s)", provider.name, provider.is_available)

    def get_provider(self, name: str) -> Optional[MusicProvider]:
        return self._providers.get(name.lower())

    def list_providers(self) -> List[Dict[str, Any]]:
        """Return safe status of all registered providers without exposing secrets."""
        res = []
        for name, p in self._providers.items():
            res.append({
                "name": name,
                "available": p.is_available,
            })
        return res

    async def get_all_candidates(self, track: Track) -> List[ProviderCandidate]:
        """
        Query all active and available providers in parallel to discover candidates.
        """
        active_providers = [p for p in self._providers.values() if p.is_available]
        if not active_providers:
            logger.warning("No music providers are currently available to match track: %s", track.title)
            return []

        async def _query_provider(p: MusicProvider) -> List[ProviderCandidate]:
            try:
                return await p.get_candidates(track)
            except Exception as exc:
                logger.error("Provider '%s' failed fetching candidates: %s", p.name, exc)
                return []

        results = await asyncio.gather(*[_query_provider(p) for p in active_providers])
        all_candidates: List[ProviderCandidate] = []
        for cand_list in results:
            all_candidates.extend(cand_list)

        return all_candidates

    search_all = get_all_candidates


# Global provider registry instance
provider_registry = ProviderRegistry()
