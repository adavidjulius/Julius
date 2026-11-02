"""
Music Library Indexer and Search Engine for Julius.
Provides instant querying across indexed lossless tracks, artist/album aggregations,
quality filtering, and statistics without querying remote storage on every request.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from src.music.db import MusicDatabase
from src.music.models import LibraryTrack

logger = logging.getLogger("julius.music.library")


class MusicLibrary:
    """High-performance index and catalog for stored lossless audio files."""

    def __init__(self, db: Optional[MusicDatabase] = None) -> None:
        self.db = db or MusicDatabase()

    def get_track(self, track_id: str) -> Optional[LibraryTrack]:
        """Fetch a single indexed track by ID."""
        return self.db.get_library_track(track_id)

    def search(
        self,
        query: Optional[str] = None,
        artist: Optional[str] = None,
        album: Optional[str] = None,
        min_bit_depth: Optional[int] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Dict[str, Any]:
        """Full-text filtered search across the lossless music library."""
        tracks, total = self.db.search_library(
            query=query,
            artist=artist,
            album=album,
            min_bit_depth=min_bit_depth,
            limit=limit,
            offset=offset
        )
        return {
            "tracks": [t.to_dict() for t in tracks],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    def list_artists(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Aggregate unique artists and track counts."""
        conn = self.db.get_connection()
        rows = conn.execute("""
        SELECT album_artist as artist, count(*) as track_count, count(DISTINCT album) as album_count
        FROM music_library
        GROUP BY album_artist
        ORDER BY track_count DESC
        LIMIT ?
        """, (limit,)).fetchall()

        return [dict(r) for r in rows]

    def list_albums(self, artist: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """Aggregate unique albums, artists, artwork, and track counts."""
        conn = self.db.get_connection()
        if artist:
            rows = conn.execute("""
            SELECT album, album_artist, artwork_url, count(*) as track_count, max(bit_depth) as max_bit_depth, max(sample_rate) as max_sample_rate
            FROM music_library
            WHERE album_artist LIKE ?
            GROUP BY album, album_artist
            ORDER BY album ASC
            LIMIT ?
            """, (f"%{artist}%", limit)).fetchall()
        else:
            rows = conn.execute("""
            SELECT album, album_artist, artwork_url, count(*) as track_count, max(bit_depth) as max_bit_depth, max(sample_rate) as max_sample_rate
            FROM music_library
            GROUP BY album, album_artist
            ORDER BY album ASC
            LIMIT ?
            """, (limit,)).fetchall()

        return [dict(r) for r in rows]

    def get_stats(self) -> Dict[str, Any]:
        """Return library overview metrics."""
        return self.db.get_library_stats()


# Global library instance
music_library = MusicLibrary()
