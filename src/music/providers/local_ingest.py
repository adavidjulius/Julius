"""
Authorized Local Ingestion Music Provider for Julius.
Allows scanning and importing verified lossless FLAC audio files from authorized
local storage directories or mounts without requiring external cloud accounts.
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.music.models import ProviderCandidate, Track
from src.music.providers.base import MusicProvider, ProviderError, ProviderUnavailableError

logger = logging.getLogger("julius.music.provider.local")


class LocalIngestProvider:
    """
    Authorized provider that indexes and serves FLAC files from a local directory.
    Useful for local collections, test fixtures, and air-gapped environments.
    """

    def __init__(self, root_dir: Optional[str] = None, enabled: bool = True) -> None:
        self._enabled = enabled and os.getenv("MUSIC_PROVIDER_LOCAL_ENABLED", "true").lower() in ("true", "1", "yes")
        base = root_dir or os.getenv("MUSIC_LOCAL_ARCHIVE_DIR", "")
        self.root_dir = Path(base).expanduser().resolve() if base else None

    @property
    def name(self) -> str:
        return "local"

    @property
    def is_available(self) -> bool:
        return bool(self._enabled and self.root_dir and self.root_dir.exists() and self.root_dir.is_dir())

    async def search(self, track: Track) -> List[ProviderCandidate]:
        return await self.get_candidates(track)

    async def get_candidates(self, track: Track) -> List[ProviderCandidate]:
        if not self.is_available or not self.root_dir:
            return []

        candidates: List[ProviderCandidate] = []
        track_title_lower = track.title.lower().strip()
        first_artist = track.artists[0].lower().strip() if track.artists else ""

        # Scan for matching FLAC files in the archive
        try:
            for file_path in self.root_dir.glob("**/*.flac"):
                fname_lower = file_path.stem.lower()
                # Check if file name matches title and artist
                if track_title_lower in fname_lower:
                    score = 80.0
                    if first_artist and first_artist in fname_lower:
                        score += 15.0

                    c = ProviderCandidate(
                        provider=self.name,
                        provider_id=str(file_path.relative_to(self.root_dir)),
                        title=track.title,
                        artists=track.artists,
                        album=track.album,
                        album_artist=track.album_artist,
                        isrc=track.isrc,
                        duration_ms=track.duration_ms,
                        format="FLAC",
                        codec="flac",
                        sample_rate=44100,
                        bit_depth=16,
                        channels=2,
                        release_date=track.release_date,
                        artwork=track.artwork_url,
                        availability=True,
                        score=score,
                        download_url=str(file_path),
                        extra_metadata={"local_file": str(file_path)}
                    )
                    candidates.append(c)
        except Exception as exc:
            logger.warning("Error scanning local provider archive: %s", exc)

        return candidates

    async def get_metadata(self, candidate: ProviderCandidate) -> Dict[str, Any]:
        return {"provider": self.name, "provider_id": candidate.provider_id}

    async def download(self, candidate: ProviderCandidate, destination_dir: str) -> str:
        source_path = candidate.download_url
        if not source_path or not Path(source_path).exists():
            raise ProviderError(f"Local file '{source_path}' does not exist.")

        dest_dir = Path(destination_dir).expanduser().resolve()
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_file = dest_dir / f"{Path(source_path).name}"

        try:
            shutil.copy2(source_path, dest_file)
            return str(dest_file)
        except Exception as e:
            raise ProviderError(f"Failed to copy local audio file: {e}")
