"""
Base protocol and data contracts for Music Providers in Julius.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from src.music.models import ProviderCandidate, Track


class ProviderError(Exception):
    """Base exception for music provider operations."""
    pass


class ProviderUnavailableError(ProviderError):
    """Raised when a provider is disabled, unconfigured, or unreachable."""
    pass


class ProviderAuthenticationError(ProviderError):
    """Raised when provider credentials or tokens fail."""
    pass


class ProviderRateLimitError(ProviderError):
    """Raised when provider API or download rate limit is exceeded."""
    def __init__(self, message: str, retry_after: float = 60.0):
        super().__init__(message)
        self.retry_after = retry_after


@runtime_checkable
class MusicProvider(Protocol):
    """Protocol defining the required interface for any lossless music provider."""

    @property
    def name(self) -> str:
        """Provider identifier (e.g. 'qobuz', 'tidal', 'deezer', 'spotiflac', 'local')."""
        ...

    @property
    def is_available(self) -> bool:
        """Whether this provider is currently configured and operational."""
        ...

    async def search(self, track: Track) -> List[ProviderCandidate]:
        """Search provider for candidates matching the canonical track."""
        ...

    async def get_candidates(self, track: Track) -> List[ProviderCandidate]:
        """Fetch all available quality variants for a track."""
        ...

    async def get_metadata(self, candidate: ProviderCandidate) -> Dict[str, Any]:
        """Retrieve detailed technical and release metadata for a specific candidate."""
        ...

    async def download(self, candidate: ProviderCandidate, destination_dir: str) -> str:
        """
        Download the candidate's lossless audio file into destination_dir.
        Returns the absolute path to the downloaded local file.
        Raises ProviderError or subclasses on failure.
        """
        ...
