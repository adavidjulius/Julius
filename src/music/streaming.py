"""
HTTP Range Audio Streamer for Julius.
Implements RFC 7233 partial content (206) streaming for lossless FLAC audio files.
Allows seeking, fast buffering, and resumes without loading entire audio files into memory.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Optional, Tuple

from aiohttp import web

from src.music.db import MusicDatabase
from src.music.models import LibraryTrack
from src.music.storage.gdrive import GoogleDriveStorage, gdrive_storage
from src.music.storage.local import LocalStorageBackend

logger = logging.getLogger("julius.music.streaming")

RANGE_HEADER_PATTERN = re.compile(r"^bytes=(\d*)-(\d*)$")


class AudioStreamer:
    """Handles RFC 7233 HTTP Range requests for lossless audio streaming."""

    def __init__(
        self,
        db: Optional[MusicDatabase] = None,
        local_storage: Optional[LocalStorageBackend] = None,
        gdrive: Optional[GoogleDriveStorage] = None
    ) -> None:
        self.db = db or MusicDatabase()
        self.local_storage = local_storage or LocalStorageBackend()
        self.gdrive_storage = gdrive or gdrive_storage

    def parse_range(self, range_header: Optional[str], total_size: int) -> Optional[Tuple[int, int]]:
        """Parse 'Range: bytes=start-end'. Returns (start, end) or None."""
        if not range_header:
            return None

        match = RANGE_HEADER_PATTERN.match(range_header.strip())
        if not match:
            return None

        start_str, end_str = match.groups()

        if start_str and end_str:
            start = int(start_str)
            end = int(end_str)
        elif start_str:
            start = int(start_str)
            end = total_size - 1
        elif end_str:
            # Suffix byte range: last N bytes
            length = int(end_str)
            start = max(0, total_size - length)
            end = total_size - 1
        else:
            return None

        if start >= total_size or end < start:
            return None

        end = min(end, total_size - 1)
        return start, end

    async def stream_track(self, request: web.Request, track_id: str) -> web.StreamResponse:
        """Stream FLAC file with Range support."""
        track = self.db.get_library_track(track_id)
        if not track:
            return web.Response(status=404, text=f"Track {track_id} not found in library.")

        # Determine file source: local storage cache first, then Google Drive
        use_local = False
        local_file_path = None
        if track.local_path and Path(track.local_path).exists():
            use_local = True
            local_file_path = Path(track.local_path)
            total_size = local_file_path.stat().st_size
        elif track.drive_file_id and self.gdrive_storage.is_available:
            total_size = await self.gdrive_storage.get_file_size(track.drive_file_id)
            if total_size <= 0:
                total_size = track.file_size_bytes
        else:
            return web.Response(status=404, text="Audio file not accessible in local cache or Google Drive.")

        range_header = request.headers.get("Range")
        byte_range = self.parse_range(range_header, total_size)

        mime_type = "audio/flac"

        # If Range requested, respond with 206 Partial Content
        if byte_range:
            start, end = byte_range
            content_length = end - start + 1

            headers = {
                "Content-Type": mime_type,
                "Content-Range": f"bytes {start}-{end}/{total_size}",
                "Content-Length": str(content_length),
                "Accept-Ranges": "bytes",
                "Cache-Control": "public, max-age=3600",
            }

            response = web.StreamResponse(status=206, headers=headers)
            await response.prepare(request)

            chunk_size = 65536  # 64 KB chunks
            bytes_remaining = content_length

            if use_local and local_file_path:
                with open(local_file_path, "rb") as f:
                    f.seek(start)
                    while bytes_remaining > 0:
                        to_read = min(chunk_size, bytes_remaining)
                        chunk = f.read(to_read)
                        if not chunk:
                            break
                        await response.write(chunk)
                        bytes_remaining -= len(chunk)
            else:
                # Stream from Google Drive
                data = await self.gdrive_storage.read_range(track.drive_file_id, start, end)
                await response.write(data)

            await response.write_eof()
            return response

        # Non-range full stream
        headers = {
            "Content-Type": mime_type,
            "Content-Length": str(total_size),
            "Accept-Ranges": "bytes",
            "Cache-Control": "public, max-age=3600",
        }
        response = web.StreamResponse(status=200, headers=headers)
        await response.prepare(request)

        chunk_size = 65536
        if use_local and local_file_path:
            with open(local_file_path, "rb") as f:
                while chunk := f.read(chunk_size):
                    await response.write(chunk)
        else:
            data = await self.gdrive_storage.read_range(track.drive_file_id, 0, total_size - 1)
            await response.write(data)

        await response.write_eof()
        return response

    async def get_track_artwork(self, track_id: str) -> Tuple[Optional[bytes], Optional[str], Optional[str]]:
        """
        Extract embedded cover art from local FLAC file or retrieve remote artwork URL.
        Returns: (image_bytes, mime_type, remote_url)
        """
        track = self.db.get_library_track(track_id)
        if not track:
            canonical_tr = self.db.get_track(track_id)
            if canonical_tr:
                return None, None, canonical_tr.artwork_url or None
            return None, None, None

        # Try extracting directly from local FLAC Vorbis picture metadata
        if track.local_path and Path(track.local_path).exists():
            try:
                from mutagen.flac import FLAC
                audio = FLAC(track.local_path)
                if audio.pictures:
                    pic = audio.pictures[0]
                    mime = pic.mime or ("image/jpeg" if pic.data.startswith(b"\xff\xd8") else "image/png")
                    return pic.data, mime, None
            except Exception as exc:
                logger.debug("Could not read embedded artwork from %s: %s", track.local_path, exc)

        # Fallback to artwork_url
        if track.artwork_url:
            return None, None, track.artwork_url

        return None, None, None


# Global audio streamer
audio_streamer = AudioStreamer()

