"""
Lossless Metadata Processor & Tag Normalizer for Julius.
Normalizes Vorbis comment tags (TITLE, ARTIST, ALBUM, ALBUMARTIST, DATE, TRACKNUMBER,
DISCNUMBER, ISRC) on FLAC files using Mutagen, embeds high-resolution cover art (PICTURE block),
and ensures idempotent processing.
"""

from __future__ import annotations

import logging
import os
import urllib.request
from pathlib import Path
from typing import Optional

from src.music.models import Track

logger = logging.getLogger("julius.music.metadata")

try:
    import mutagen
    from mutagen.flac import FLAC, Picture
    MUTAGEN_AVAILABLE = True
except ImportError:
    MUTAGEN_AVAILABLE = False
    logger.warning("Mutagen is not installed; metadata tagging will be skipped or limited.")


class MetadataProcessor:
    """Production Vorbis tag editor and artwork embedder for FLAC files."""

    def process_metadata(
        self,
        file_path: str,
        track: Track,
        artwork_bytes: Optional[bytes] = None
    ) -> bool:
        """
        Write standard tags and embed cover art into the FLAC file idempotently.
        Returns True if tags were written, False if skipped.
        """
        if not MUTAGEN_AVAILABLE:
            logger.warning("Cannot tag FLAC file '%s': mutagen not available.", file_path)
            return False

        path = Path(file_path).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"File not found: '{file_path}'")

        try:
            audio = FLAC(str(path))
        except Exception as exc:
            logger.error("Failed opening FLAC with mutagen: %s", exc)
            return False

        # Build normalized Vorbis tags
        audio["TITLE"] = track.title
        audio["ARTIST"] = track.artists
        audio["ALBUM"] = track.album
        audio["ALBUMARTIST"] = track.album_artist or (track.artists[0] if track.artists else "")

        if track.release_date:
            audio["DATE"] = track.release_date
            audio["YEAR"] = track.release_date[:4]

        if track.track_number:
            audio["TRACKNUMBER"] = str(track.track_number)

        if track.disc_number:
            audio["DISCNUMBER"] = str(track.disc_number)

        if track.isrc:
            audio["ISRC"] = track.isrc

        audio["ENCODER"] = "Julius Production Music Platform"

        # Embed artwork if provided or if track has artwork_url
        if not artwork_bytes and track.artwork_url:
            artwork_bytes = self._download_artwork(track.artwork_url)

        if artwork_bytes:
            try:
                # Clear existing front covers to prevent bloat
                audio.clear_pictures()

                pic = Picture()
                pic.type = 3  # Cover (front)
                pic.desc = "Front Cover"
                pic.mime = "image/jpeg" if artwork_bytes.startswith(b"\xff\xd8") else "image/png"
                pic.data = artwork_bytes
                audio.add_picture(pic)
            except Exception as e:
                logger.warning("Failed embedding picture into FLAC: %s", e)

        audio.save()
        logger.info("Successfully tagged FLAC: %s - %s", track.artists[0] if track.artists else "", track.title)
        return True

    def _download_artwork(self, url: str) -> Optional[bytes]:
        """Fetch artwork image bytes over HTTP with a quick timeout."""
        if not url.startswith("http://") and not url.startswith("https://"):
            return None
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Julius-Music/1.0"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    return resp.read()
        except Exception as exc:
            logger.debug("Failed downloading artwork from %s: %s", url, exc)
        return None


# Global metadata processor instance
metadata_processor = MetadataProcessor()
