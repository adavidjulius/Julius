"""
Persistent SQLite database engine for Julius Music Subsystem.
Provides thread-safe connections, WAL mode, indexing, and schema management
for tracks, library items, jobs, and candidates.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from src.music.models import DownloadRecord, JobStatus, LibraryTrack, MusicJob, ProviderCandidate, Track


class MusicDatabase:
    """Thread-safe SQLite database manager for the music platform."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        if db_path is None:
            base_dir = os.environ.get("JULIUS_DATA_DIR")
            if base_dir:
                base_dir = os.path.expanduser(base_dir)
            if not base_dir:
                base_dir = str(Path.home() / ".julius")
            Path(base_dir).mkdir(parents=True, exist_ok=True)
            self.db_path = str(Path(base_dir) / "music.db")
        else:
            self.db_path = str(Path(db_path).resolve())
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        self._local = threading.local()
        self._init_schema()

    def get_connection(self) -> sqlite3.Connection:
        """Get or create a thread-local SQLite connection with WAL mode enabled."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=30.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA foreign_keys=ON;")
            conn.execute("PRAGMA busy_timeout=5000;")
            self._local.conn = conn
        return self._local.conn

    def _init_schema(self) -> None:
        """Initialize tables and indexes for the music subsystem."""
        conn = self.get_connection()
        with conn:
            # Canonical Tracks
            conn.execute("""
            CREATE TABLE IF NOT EXISTS music_tracks (
                spotify_id TEXT PRIMARY KEY,
                isrc TEXT,
                title TEXT NOT NULL,
                artists TEXT NOT NULL,
                album TEXT NOT NULL,
                album_artist TEXT,
                duration_ms INTEGER NOT NULL,
                disc_number INTEGER DEFAULT 1,
                track_number INTEGER DEFAULT 1,
                release_date TEXT,
                explicit INTEGER DEFAULT 0,
                artwork_url TEXT,
                source_url TEXT,
                created_at REAL NOT NULL
            );
            """)

            # Search Index on Tracks
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tracks_isrc ON music_tracks(isrc);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tracks_title ON music_tracks(title);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tracks_artists ON music_tracks(artists);")

            # Ingestion Jobs
            conn.execute("""
            CREATE TABLE IF NOT EXISTS music_jobs (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                playlist_url TEXT NOT NULL,
                playlist_name TEXT NOT NULL,
                status TEXT NOT NULL,
                total_tracks INTEGER DEFAULT 0,
                completed_tracks INTEGER DEFAULT 0,
                failed_tracks INTEGER DEFAULT 0,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
            """)

            # Track Job State Machine (Per-track execution within a job)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS music_job_tracks (
                id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL,
                track_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                provider_id TEXT NOT NULL,
                status TEXT NOT NULL,
                attempts INTEGER DEFAULT 0,
                error TEXT,
                quality TEXT,
                local_path TEXT,
                checksum TEXT,
                drive_file_id TEXT,
                progress REAL DEFAULT 0.0,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                completed_at REAL,
                FOREIGN KEY (job_id) REFERENCES music_jobs(id) ON DELETE CASCADE
            );
            """)

            conn.execute("CREATE INDEX IF NOT EXISTS idx_job_tracks_job ON music_job_tracks(job_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_job_tracks_status ON music_job_tracks(status);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_job_tracks_track_id ON music_job_tracks(track_id);")

            # Candidates found during matching
            conn.execute("""
            CREATE TABLE IF NOT EXISTS music_candidates (
                id TEXT PRIMARY KEY,
                job_track_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                provider_id TEXT NOT NULL,
                title TEXT NOT NULL,
                artists TEXT NOT NULL,
                album TEXT NOT NULL,
                album_artist TEXT,
                isrc TEXT,
                duration_ms INTEGER,
                format TEXT,
                codec TEXT,
                sample_rate INTEGER,
                bit_depth INTEGER,
                channels INTEGER,
                release_date TEXT,
                artwork TEXT,
                availability INTEGER DEFAULT 1,
                score REAL DEFAULT 0.0,
                extra_json TEXT,
                FOREIGN KEY (job_track_id) REFERENCES music_job_tracks(id) ON DELETE CASCADE
            );
            """)

            # Persistent Music Library Index
            conn.execute("""
            CREATE TABLE IF NOT EXISTS music_library (
                id TEXT PRIMARY KEY,
                isrc TEXT,
                title TEXT NOT NULL,
                artists TEXT NOT NULL,
                album TEXT NOT NULL,
                album_artist TEXT NOT NULL,
                duration_ms INTEGER NOT NULL,
                disc_number INTEGER DEFAULT 1,
                track_number INTEGER DEFAULT 1,
                release_date TEXT,
                artwork_url TEXT,
                source_url TEXT,
                drive_file_id TEXT,
                local_path TEXT,
                checksum TEXT UNIQUE NOT NULL,
                codec TEXT NOT NULL,
                sample_rate INTEGER NOT NULL,
                bit_depth INTEGER NOT NULL,
                channels INTEGER NOT NULL,
                file_size_bytes INTEGER NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
            """)

            conn.execute("CREATE INDEX IF NOT EXISTS idx_lib_title ON music_library(title);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_lib_artists ON music_library(artists);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_lib_album ON music_library(album);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_lib_checksum ON music_library(checksum);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_lib_isrc ON music_library(isrc);")

    # ── Canonical Tracks ───────────────────────────────────────────────────────

    def upsert_track(self, track: Union[Track, Dict[str, Any]]) -> None:
        if isinstance(track, dict):
            track = Track.from_dict(track)
        conn = self.get_connection()
        with conn:
            conn.execute("""
            INSERT INTO music_tracks (
                spotify_id, isrc, title, artists, album, album_artist,
                duration_ms, disc_number, track_number, release_date,
                explicit, artwork_url, source_url, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(spotify_id) DO UPDATE SET
                title=excluded.title,
                artists=excluded.artists,
                album=excluded.album,
                album_artist=excluded.album_artist,
                isrc=coalesce(excluded.isrc, music_tracks.isrc),
                duration_ms=excluded.duration_ms,
                disc_number=excluded.disc_number,
                track_number=excluded.track_number,
                release_date=excluded.release_date,
                explicit=excluded.explicit,
                artwork_url=excluded.artwork_url,
                source_url=excluded.source_url;
            """, (
                track.spotify_id,
                track.isrc,
                track.title,
                json.dumps(track.artists),
                track.album,
                track.album_artist,
                track.duration_ms,
                track.disc_number,
                track.track_number,
                track.release_date,
                1 if track.explicit else 0,
                track.artwork_url,
                track.source_url,
                time.time()
            ))

    def get_track(self, spotify_id: str) -> Optional[Track]:
        conn = self.get_connection()
        row = conn.execute("SELECT * FROM music_tracks WHERE spotify_id = ?", (spotify_id,)).fetchone()
        if not row:
            return None
        return Track.from_dict(dict(row))

    # ── Jobs & Track Executions ────────────────────────────────────────────────

    def create_job(self, job: MusicJob) -> None:
        conn = self.get_connection()
        with conn:
            conn.execute("""
            INSERT INTO music_jobs (
                id, user_id, playlist_url, playlist_name, status,
                total_tracks, completed_tracks, failed_tracks,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                job.id, job.user_id, job.playlist_url, job.playlist_name,
                job.status.value, job.total_tracks, job.completed_tracks,
                job.failed_tracks, job.created_at, job.updated_at
            ))

    def update_job_status(self, job_id: str, status: JobStatus, completed_delta: int = 0, failed_delta: int = 0) -> None:
        conn = self.get_connection()
        with conn:
            conn.execute("""
            UPDATE music_jobs
            SET status = ?,
                completed_tracks = completed_tracks + ?,
                failed_tracks = failed_tracks + ?,
                updated_at = ?
            WHERE id = ?
            """, (status.value, completed_delta, failed_delta, time.time(), job_id))

    def get_job(self, job_id: str) -> Optional[MusicJob]:
        conn = self.get_connection()
        row = conn.execute("SELECT * FROM music_jobs WHERE id = ?", (job_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["status"] = JobStatus(d["status"])
        return MusicJob(**d)

    def list_jobs(self, user_id: Optional[str] = None, limit: int = 50) -> List[MusicJob]:
        conn = self.get_connection()
        if user_id:
            rows = conn.execute(
                "SELECT * FROM music_jobs WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
                (user_id, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM music_jobs ORDER BY created_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
        jobs = []
        for r in rows:
            d = dict(r)
            d["status"] = JobStatus(d["status"])
            jobs.append(MusicJob(**d))
        return jobs

    def create_job_track(self, record: DownloadRecord) -> None:
        conn = self.get_connection()
        with conn:
            conn.execute("""
            INSERT INTO music_job_tracks (
                id, job_id, track_id, provider, provider_id, status,
                attempts, error, quality, local_path, checksum,
                drive_file_id, progress, created_at, updated_at, completed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record.id, record.job_id, record.track_id, record.provider,
                record.provider_id, record.status.value, record.attempts,
                record.error, record.quality, record.local_path, record.checksum,
                record.drive_file_id, record.progress, record.created_at,
                record.updated_at, record.completed_at
            ))

    def update_job_track(self, record: DownloadRecord) -> None:
        conn = self.get_connection()
        with conn:
            conn.execute("""
            UPDATE music_job_tracks
            SET status = ?,
                attempts = ?,
                error = ?,
                quality = ?,
                local_path = ?,
                checksum = ?,
                drive_file_id = ?,
                progress = ?,
                updated_at = ?,
                completed_at = ?
            WHERE id = ?
            """, (
                record.status.value, record.attempts, record.error,
                record.quality, record.local_path, record.checksum,
                record.drive_file_id, record.progress, record.updated_at,
                record.completed_at, record.id
            ))

    def get_job_track(self, job_track_id: str) -> Optional[DownloadRecord]:
        conn = self.get_connection()
        row = conn.execute("SELECT * FROM music_job_tracks WHERE id = ?", (job_track_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["status"] = JobStatus(d["status"])
        return DownloadRecord(**d)

    def get_job_tracks_for_job(self, job_id: str) -> List[DownloadRecord]:
        conn = self.get_connection()
        rows = conn.execute(
            "SELECT * FROM music_job_tracks WHERE job_id = ? ORDER BY created_at ASC",
            (job_id,)
        ).fetchall()
        res = []
        for r in rows:
            d = dict(r)
            d["status"] = JobStatus(d["status"])
            res.append(DownloadRecord(**d))
        return res

    def get_resumable_job_tracks(self) -> List[DownloadRecord]:
        """Find pending or interrupted tracks for crash recovery upon server boot."""
        conn = self.get_connection()
        rows = conn.execute("""
        SELECT * FROM music_job_tracks
        WHERE status IN ('PENDING', 'RESOLVING', 'MATCHING', 'READY', 'DOWNLOADING', 'VALIDATING', 'PROCESSING_METADATA', 'UPLOADING', 'RETRYING')
        ORDER BY created_at ASC
        """).fetchall()
        res = []
        for r in rows:
            d = dict(r)
            d["status"] = JobStatus(d["status"])
            res.append(DownloadRecord(**d))
        return res

    # ── Candidates ─────────────────────────────────────────────────────────────

    def save_candidates(self, job_track_id: str, candidates: List[ProviderCandidate]) -> None:
        conn = self.get_connection()
        with conn:
            conn.execute("DELETE FROM music_candidates WHERE job_track_id = ?", (job_track_id,))
            for c in candidates:
                cand_id = f"{job_track_id}_{c.provider}_{c.provider_id}"
                conn.execute("""
                INSERT INTO music_candidates (
                    id, job_track_id, provider, provider_id, title, artists,
                    album, album_artist, isrc, duration_ms, format, codec,
                    sample_rate, bit_depth, channels, release_date, artwork,
                    availability, score, extra_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    cand_id, job_track_id, c.provider, c.provider_id, c.title,
                    json.dumps(c.artists), c.album, c.album_artist, c.isrc,
                    c.duration_ms, c.format, c.codec, c.sample_rate, c.bit_depth,
                    c.channels, c.release_date, c.artwork, 1 if c.availability else 0,
                    c.score, json.dumps(c.extra_metadata)
                ))

    def get_candidates(self, job_track_id: str) -> List[ProviderCandidate]:
        conn = self.get_connection()
        rows = conn.execute(
            "SELECT * FROM music_candidates WHERE job_track_id = ? ORDER BY score DESC",
            (job_track_id,)
        ).fetchall()
        cands = []
        for r in rows:
            d = dict(r)
            extra = json.loads(d["extra_json"]) if d.get("extra_json") else {}
            cands.append(ProviderCandidate(
                provider=d["provider"],
                provider_id=d["provider_id"],
                title=d["title"],
                artists=json.loads(d["artists"]),
                album=d["album"],
                album_artist=d["album_artist"] or "",
                isrc=d["isrc"],
                duration_ms=d["duration_ms"] or 0,
                format=d["format"] or "FLAC",
                codec=d["codec"] or "flac",
                sample_rate=d["sample_rate"] or 44100,
                bit_depth=d["bit_depth"] or 16,
                channels=d["channels"] or 2,
                release_date=d["release_date"] or "",
                artwork=d["artwork"] or "",
                availability=bool(d["availability"]),
                score=d["score"] or 0.0,
                extra_metadata=extra
            ))
        return cands

    # ── Music Library Index & Deduplication ─────────────────────────────────────

    def find_existing_track(self, isrc: Optional[str] = None, title: str = "", artist: str = "") -> Optional[LibraryTrack]:
        """Deduplication check: checks by exact ISRC, or title + primary artist."""
        conn = self.get_connection()
        if isrc:
            row = conn.execute("SELECT * FROM music_library WHERE isrc = ?", (isrc,)).fetchone()
            if row:
                return self._row_to_library_track(row)

        if title and artist:
            row = conn.execute(
                "SELECT * FROM music_library WHERE lower(title) = lower(?) AND lower(artists) LIKE lower(?)",
                (title.strip(), f"%{artist.strip()}%")
            ).fetchone()
            if row:
                return self._row_to_library_track(row)

        return None

    def find_by_checksum(self, checksum: str) -> Optional[LibraryTrack]:
        conn = self.get_connection()
        row = conn.execute("SELECT * FROM music_library WHERE checksum = ?", (checksum,)).fetchone()
        if row:
            return self._row_to_library_track(row)
        return None

    def upsert_library_track(self, track: LibraryTrack) -> None:
        conn = self.get_connection()
        with conn:
            conn.execute("""
            INSERT INTO music_library (
                id, isrc, title, artists, album, album_artist, duration_ms,
                disc_number, track_number, release_date, artwork_url, source_url,
                drive_file_id, local_path, checksum, codec, sample_rate, bit_depth,
                channels, file_size_bytes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(checksum) DO UPDATE SET
                drive_file_id = coalesce(excluded.drive_file_id, music_library.drive_file_id),
                local_path = coalesce(excluded.local_path, music_library.local_path),
                updated_at = excluded.updated_at;
            """, (
                track.id, track.isrc, track.title, json.dumps(track.artists),
                track.album, track.album_artist, track.duration_ms,
                track.disc_number, track.track_number, track.release_date,
                track.artwork_url, track.source_url, track.drive_file_id,
                track.local_path, track.checksum, track.codec, track.sample_rate,
                track.bit_depth, track.channels, track.file_size_bytes,
                track.created_at, track.updated_at
            ))

    def get_library_track(self, track_id: str) -> Optional[LibraryTrack]:
        conn = self.get_connection()
        row = conn.execute("SELECT * FROM music_library WHERE id = ?", (track_id,)).fetchone()
        if not row:
            return None
        return self._row_to_library_track(row)

    def search_library(
        self,
        query: Optional[str] = None,
        artist: Optional[str] = None,
        album: Optional[str] = None,
        min_bit_depth: Optional[int] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[LibraryTrack], int]:
        conn = self.get_connection()
        clauses = []
        params: List[Any] = []

        if query:
            q = f"%{query.strip()}%"
            clauses.append("(title LIKE ? OR artists LIKE ? OR album LIKE ?)")
            params.extend([q, q, q])
        if artist:
            clauses.append("artists LIKE ?")
            params.append(f"%{artist.strip()}%")
        if album:
            clauses.append("album LIKE ?")
            params.append(f"%{album.strip()}%")
        if min_bit_depth:
            clauses.append("bit_depth >= ?")
            params.append(min_bit_depth)

        where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""

        count_sql = f"SELECT count(*) FROM music_library {where_sql}"
        total_count = conn.execute(count_sql, params).fetchone()[0]

        data_sql = f"SELECT * FROM music_library {where_sql} ORDER BY created_at DESC LIMIT ? OFFSET ?"
        data_params = list(params) + [limit, offset]
        rows = conn.execute(data_sql, data_params).fetchall()

        return [self._row_to_library_track(r) for r in rows], total_count

    def list_library_tracks(self, limit: int = 100, offset: int = 0) -> List[LibraryTrack]:
        """Convenience method to list library tracks."""
        tracks, _ = self.search_library(limit=limit, offset=offset)
        return tracks

    get_all_library_tracks = list_library_tracks

    def get_library_stats(self) -> Dict[str, Any]:
        conn = self.get_connection()
        total_tracks = conn.execute("SELECT count(*) FROM music_library").fetchone()[0]
        total_size = conn.execute("SELECT coalesce(sum(file_size_bytes), 0) FROM music_library").fetchone()[0]
        hi_res_count = conn.execute("SELECT count(*) FROM music_library WHERE bit_depth >= 24").fetchone()[0]
        return {
            "total_tracks": total_tracks,
            "total_size_bytes": total_size,
            "hi_res_tracks": hi_res_count,
            "standard_lossless_tracks": total_tracks - hi_res_count,
        }

    def _row_to_library_track(self, row: sqlite3.Row) -> LibraryTrack:
        d = dict(row)
        artists = d.get("artists", "[]")
        if isinstance(artists, str):
            try:
                artists = json.loads(artists)
            except Exception:
                artists = [artists]
        d["artists"] = artists
        return LibraryTrack(**d)


# Global singleton database instance
default_music_db = MusicDatabase()
