"""
Production Google Drive Storage Service for Julius Music Ingestion.
Provides automated folder hierarchy creation (Song/Artist/Album/),
resumable chunked file uploads, exponential backoff, token refresh, and existence checks.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from src.music.storage.gdrive import GoogleDriveStorage

logger = logging.getLogger("julius.services.gdrive")


class GDriveService:
    """Production service for managing Google Drive lossless audio storage."""

    def __init__(
        self,
        credentials_path: Optional[str] = None,
        root_folder_id: Optional[str] = None
    ) -> None:
        self.storage = GoogleDriveStorage(
            credentials_path=credentials_path,
            root_folder_id=root_folder_id
        )

    @property
    def is_available(self) -> bool:
        return self.storage.is_available

    async def upload_file(
        self,
        local_path: str,
        remote_rel_path: str,
        mime_type: str = "audio/flac"
    ) -> str:
        """
        Upload local file to Google Drive under remote_rel_path (e.g. 'Song/Artist/Album/01 - Track.flac').
        Automatically creates missing folders and returns the Drive file ID.
        """
        return await self.storage.upload(local_path, remote_rel_path, mime_type=mime_type)

    async def file_exists(self, remote_rel_path: str) -> bool:
        """Check if file already exists at remote_rel_path."""
        return await self.storage.exists(remote_rel_path)

    async def delete_file(self, remote_rel_path: str) -> bool:
        """Delete remote file if it exists."""
        return await self.storage.delete(remote_rel_path)


# Global singleton instance
gdrive_service = GDriveService()
