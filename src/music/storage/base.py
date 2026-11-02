"""
Storage backend protocol and path sanitization helpers for Julius Music Platform.
"""

from __future__ import annotations

import os
import re
from typing import AsyncIterator, Optional, Protocol, runtime_checkable

from src.music.models import Track


def sanitize_path_segment(name: str) -> str:
    """Sanitize directory or file names to avoid path traversal, illegal chars, or collision."""
    if not name:
        return "Unknown"
    # Remove path traversal tokens and illegal filesystem characters
    cleaned = re.sub(r'[/\\?%*:|"<>.]', "_", name)
    cleaned = " ".join(cleaned.split()).strip()
    return cleaned or "Unknown"


def build_track_storage_path(
    track: Track,
    root_folder: Optional[str] = None,
    playlist_name: Optional[str] = None,
    include_artist_folder: bool = True
) -> str:
    """
    Construct canonical hierarchical storage path.
    When playlist_name is provided:
        {root_folder} / {playlist_name} / 01 - Track.flac
    When include_artist_folder is False:
        {root_folder} / {album_or_playlist} / 01 - Track.flac
    Default legacy structure:
        {root_folder} / Artist / Album / 01 - Track.flac
    """
    if not root_folder:
        root_folder = os.getenv("MUSIC_ROOT_FOLDER", "Song")
    root_folder = sanitize_path_segment(root_folder)
    track_num = f"{track.track_number:02d}" if track.track_number else "01"
    title = sanitize_path_segment(track.title or "Track")
    filename = f"{track_num} - {title}.flac"

    if playlist_name:
        folder = sanitize_path_segment(playlist_name)
        return f"{root_folder}/{folder}/{filename}"

    if not include_artist_folder:
        folder = sanitize_path_segment(track.album or "Unknown Album")
        return f"{root_folder}/{folder}/{filename}"

    artist = sanitize_path_segment(track.album_artist or (track.artists[0] if track.artists else "Unknown Artist"))
    album = sanitize_path_segment(track.album or "Unknown Album")
    return f"{root_folder}/{artist}/{album}/{filename}"



@runtime_checkable
class StorageBackend(Protocol):
    """Storage backend protocol for lossless audio files."""

    @property
    def name(self) -> str:
        """Storage backend identifier ('gdrive', 'local')."""
        ...

    @property
    def is_available(self) -> bool:
        """Whether this storage backend is configured and ready."""
        ...

    async def upload(self, local_path: str, remote_path: str, mime_type: str = "audio/flac") -> str:
        """
        Upload file from local_path to remote_path.
        Returns unique storage identifier (e.g. Google Drive file_id or local file path).
        """
        ...

    async def exists(self, remote_path: str) -> bool:
        """Check if file exists at remote_path."""
        ...

    async def delete(self, remote_path_or_id: str) -> bool:
        """Delete file at remote path or identifier."""
        ...

    async def read_range(self, remote_path_or_id: str, start_byte: int, end_byte: Optional[int] = None) -> bytes:
        """Read a byte range from the stored audio file."""
        ...

    async def get_file_size(self, remote_path_or_id: str) -> int:
        """Get file size in bytes."""
        ...
