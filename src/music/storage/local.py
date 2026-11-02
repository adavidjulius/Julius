"""
Local Storage Backend for Julius Music Subsystem.
Stores files under local music directory with hierarchical folders
(Song/Artist/Album/01 - Track.flac) and supports random byte-range reads.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
from pathlib import Path
from typing import Optional

from src.music.storage.base import StorageBackend

logger = logging.getLogger("julius.music.storage.local")


class LocalStorageBackend:
    """Stores FLAC files on local filesystem."""

    def __init__(self, root_dir: Optional[str] = None) -> None:
        base = root_dir or os.getenv("MUSIC_DOWNLOAD_DIR")
        if not base:
            base = str(Path.home() / ".julius" / "music_library")
        self.root_dir = Path(base).expanduser().resolve()
        self.root_dir.mkdir(parents=True, exist_ok=True)

    @property
    def name(self) -> str:
        return "local"

    @property
    def is_available(self) -> bool:
        return self.root_dir.exists() and os.access(str(self.root_dir), os.W_OK)

    def _resolve_path(self, remote_path: str) -> Path:
        # Strip leading slashes to prevent root escape
        clean_rel = remote_path.lstrip("/\\")
        target = (self.root_dir / clean_rel).resolve()
        if not target.is_relative_to(self.root_dir):
            raise PermissionError("Path traversal attempt in storage path.")
        return target

    async def upload(self, local_path: str, remote_path: str, mime_type: str = "audio/flac") -> str:
        source = Path(local_path).expanduser().resolve()
        if not source.exists():
            raise FileNotFoundError(f"Source file not found: {local_path}")

        target = self._resolve_path(remote_path)
        target.parent.mkdir(parents=True, exist_ok=True)

        def _do_copy():
            shutil.copy2(source, target)

        await asyncio.to_thread(_do_copy)
        logger.info("Stored audio locally: %s -> %s", source.name, target)
        return str(target)

    async def exists(self, remote_path: str) -> bool:
        try:
            target = self._resolve_path(remote_path)
            return target.exists() and target.is_file()
        except Exception:
            return False

    async def delete(self, remote_path_or_id: str) -> bool:
        try:
            target = Path(remote_path_or_id)
            if not target.is_absolute():
                target = self._resolve_path(remote_path_or_id)
            if target.exists():
                target.unlink()
                return True
        except Exception as exc:
            logger.warning("Failed deleting local audio file: %s", exc)
        return False

    async def read_range(self, remote_path_or_id: str, start_byte: int, end_byte: Optional[int] = None) -> bytes:
        target = Path(remote_path_or_id)
        if not target.is_absolute():
            target = self._resolve_path(remote_path_or_id)

        if not target.exists():
            raise FileNotFoundError(f"File not found: {remote_path_or_id}")

        def _read():
            with open(target, "rb") as f:
                f.seek(start_byte)
                if end_byte is not None:
                    length = end_byte - start_byte + 1
                    return f.read(length)
                return f.read()

        return await asyncio.to_thread(_read)

    async def get_file_size(self, remote_path_or_id: str) -> int:
        target = Path(remote_path_or_id)
        if not target.is_absolute():
            target = self._resolve_path(remote_path_or_id)
        return target.stat().st_size
