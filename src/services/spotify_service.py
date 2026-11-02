"""
Production-grade Spotify Playlist Service for Julius.
Provides URL validation, playlist ID extraction, Spotify API authentication,
comprehensive pagination, embed metadata fallback, and canonical track normalization.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from src.music.models import Track
from src.music.spotify import SpotifyResolver, spotify_resolver

logger = logging.getLogger("julius.services.spotify")

# Canonical Track Model alias as required by specification
CanonicalTrack = Track


class SpotifyService:
    """Production service for analyzing Spotify playlists and extracting canonical tracks."""

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None
    ) -> None:
        self.resolver = SpotifyResolver(client_id=client_id, client_secret=client_secret)

    @property
    def is_configured(self) -> bool:
        return self.resolver.is_authenticated

    def extract_playlist_id(self, url: str) -> Optional[str]:
        """Extract the 22-character Spotify collection ID from a URL or URI."""
        clean = (url or "").strip()
        if "track/" in clean or "spotify:track:" in clean:
            return None
        m = re.search(r"(?:playlist/|album/|spotify:playlist:|spotify:album:|^)([a-zA-Z0-9]{22})(?:$|[?&/])", clean)
        if m:
            return m.group(1)
        try:
            rtype, rid = self.resolver.parse_url(clean)
            return rid if rtype in ("playlist", "album") else None
        except Exception:
            return None

    def validate_url(self, url: str, allow_albums: bool = False) -> bool:
        """Return True if the URL is a valid Spotify collection URL/URI."""
        clean = (url or "").strip()
        if clean.startswith("http") and "spotify.com" not in clean:
            return False
        if "track/" in clean or "spotify:track:" in clean:
            return False
        if not allow_albums and ("album/" in clean or "spotify:album:" in clean):
            return False
        pid = self.extract_playlist_id(clean)
        return pid is not None and len(pid) == 22

    def is_supported_url(self, url: str) -> bool:
        """Return True if the URL is a supported playlist or album URL."""
        return self.validate_url(url, allow_albums=True)

    def get_playlist_tracks(self, url: str) -> List[Dict[str, Any]]:
        """
        Retrieve all tracks from a playlist as standard dictionaries (backwards compatibility).
        Handles full pagination (10, 100, 500, 1000+ tracks).
        """
        _, tracks = self.resolver.resolve_playlist(url)
        return [t.to_dict() for t in tracks]

    def resolve_playlist(self, url: str) -> Tuple[str, List[CanonicalTrack]]:
        """
        Resolve a Spotify playlist URL into its canonical name and list of CanonicalTrack objects.
        """
        return self.resolver.resolve_playlist(url)


# Global singleton instance
spotify_service = SpotifyService()
