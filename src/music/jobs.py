"""
Asynchronous Persistent Job Manager & Download Worker Pool for Julius.
Coordinates track resolution, provider discovery, matching, quality selection,
downloading, FLAC validation, metadata tagging, Google Drive upload, and library indexing.
Features full crash recovery from SQLite, bounded worker concurrency, and WebSocket event publishing.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from src.music.db import MusicDatabase
from src.music.flac_validator import FlacValidator, flac_validator
from src.music.matching import MatchEngine, match_engine
from src.music.metadata import MetadataProcessor, metadata_processor
from src.music.models import DownloadRecord, JobStatus, LibraryTrack, MusicJob, ProviderCandidate, Track
from src.music.providers.registry import ProviderRegistry, provider_registry
from src.music.quality import QualityEngine, quality_engine
from src.music.storage.base import StorageBackend, build_track_storage_path
from src.music.storage.gdrive import GoogleDriveStorage, gdrive_storage
from src.music.storage.local import LocalStorageBackend

logger = logging.getLogger("julius.music.jobs")


class MusicJobManager:
    """Production Job Manager orchestrating the asynchronous music pipeline."""

    def __init__(
        self,
        db: Optional[MusicDatabase] = None,
        max_concurrent: Optional[int] = None,
        temp_dir: Optional[str] = None,
        gdrive_storage: Optional[Any] = None,
        local_storage: Optional[Any] = None,
    ) -> None:
        from src.music.storage.gdrive import gdrive_storage as default_gdrive
        self.db = db or MusicDatabase()
        self.max_concurrent = int(
            max_concurrent or os.getenv("MUSIC_MAX_CONCURRENT_DOWNLOADS", "3")
        )
        base_tmp = temp_dir or os.getenv("MUSIC_TEMP_DIR")
        if not base_tmp:
            base_tmp = str(Path.home() / ".julius" / "tmp_music_downloads")
        self.temp_dir = Path(base_tmp).expanduser().resolve()
        self.temp_dir.mkdir(parents=True, exist_ok=True)

        self.queue: asyncio.Queue[str] = asyncio.Queue()
        self.workers: List[asyncio.Task] = []
        self._running = False
        self._cancelled_jobs: set[str] = set()
        self._event_subscribers: List[Callable[[Dict[str, Any]], None]] = []

        # Default storage: Google Drive if configured, local fallback
        self.local_storage = local_storage or LocalStorageBackend()
        self.gdrive_storage = gdrive_storage or default_gdrive

    def subscribe_events(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Register a callback for real-time WebSocket event broadcasting."""
        if callback not in self._event_subscribers:
            self._event_subscribers.append(callback)

    def emit_event(self, event_name: str, payload: Dict[str, Any]) -> None:
        """Broadcast structured event to all subscribers."""
        event = {
            "event": event_name,
            "timestamp": time.time(),
            **payload
        }
        for cb in self._event_subscribers:
            try:
                cb(event)
            except Exception as exc:
                logger.debug("Event subscriber error: %s", exc)

    async def start(self) -> None:
        """Start worker pool and recover interrupted jobs from previous runs."""
        if self._running:
            return
        self._running = True
        logger.info("Starting MusicJobManager worker pool (concurrency=%d)", self.max_concurrent)

        # Crash recovery: find interrupted tracks from DB
        interrupted = self.db.get_resumable_job_tracks()
        if interrupted:
            logger.info("Found %d resumable track downloads from previous session; requeueing...", len(interrupted))
            for item in interrupted:
                item.status = JobStatus.PENDING
                self.db.update_job_track(item)
                await self.queue.put(item.id)

        # Launch worker tasks
        for i in range(self.max_concurrent):
            task = asyncio.create_task(self._worker_loop(i))
            self.workers.append(task)

    async def stop(self) -> None:
        """Graceful shutdown of worker tasks."""
        self._running = False
        for task in self.workers:
            task.cancel()
        await asyncio.gather(*self.workers, return_exceptions=True)
        self.workers.clear()
        logger.info("MusicJobManager stopped.")

    shutdown = stop

    async def submit_playlist_job(
        self,
        user_id: str,
        playlist_url: str,
        playlist_name: str,
        tracks: List[Track],
        quality_policy: str = "best_lossless"
    ) -> MusicJob:
        """
        Create and enqueue a playlist ingestion job.
        Persists canonical tracks and creates atomic track download records.
        """
        job_id = str(uuid.uuid4())
        job = MusicJob(
            id=job_id,
            user_id=user_id,
            playlist_url=playlist_url,
            playlist_name=playlist_name,
            status=JobStatus.PENDING,
            total_tracks=len(tracks),
            completed_tracks=0,
            failed_tracks=0,
            created_at=time.time(),
            updated_at=time.time()
        )
        self.db.create_job(job)

        self.emit_event("playlist.started", {
            "job_id": job_id,
            "playlist_name": playlist_name,
            "total_tracks": len(tracks)
        })

        if not self._running:
            await self.start()

        for tr in tracks:
            if isinstance(tr, dict):
                tr = Track.from_dict(tr)
            # 1. Upsert canonical track into DB
            self.db.upsert_track(tr)

            # 2. Create track job record
            rec_id = str(uuid.uuid4())
            rec = DownloadRecord(
                id=rec_id,
                job_id=job_id,
                track_id=tr.spotify_id,
                provider="pending",
                provider_id="",
                status=JobStatus.PENDING,
                attempts=0,
                created_at=time.time(),
                updated_at=time.time()
            )
            self.db.create_job_track(rec)

            # Enqueue for background worker processing
            await self.queue.put(rec_id)

        self.emit_event("playlist.resolved", {
            "job_id": job_id,
            "playlist_name": playlist_name,
            "queued_tracks": len(tracks)
        })

        return job

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a running or pending playlist job."""
        self._cancelled_jobs.add(job_id)
        job = self.db.get_job(job_id)
        if job:
            self.db.update_job_status(job_id, JobStatus.FAILED)
            self.emit_event("job.failed", {"job_id": job_id, "reason": "Cancelled by user"})
            return True
        return False

    async def _worker_loop(self, worker_id: int) -> None:
        """Background worker thread pulling track jobs from the queue."""
        logger.debug("Music worker %d started.", worker_id)
        while self._running:
            try:
                track_record_id = await self.queue.get()
                if not self._running:
                    break
                await self._process_track_job(track_record_id)
                self.queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Unhandled exception in music worker %d: %s", worker_id, exc, exc_info=True)
                await asyncio.sleep(1)

    async def _process_track_job(self, record_id: str) -> None:
        """Execute full state pipeline for a single track."""
        rec = self.db.get_job_track(record_id)
        if not rec:
            return

        # Check if job was cancelled
        if rec.job_id in self._cancelled_jobs:
            rec.status = JobStatus.SKIPPED
            rec.error = "Job was cancelled."
            self.db.update_job_track(rec)
            return

        track = self.db.get_track(rec.track_id)
        if not track:
            rec.status = JobStatus.FAILED
            rec.error = f"Track metadata for {rec.track_id} not found."
            self.db.update_job_track(rec)
            return

        rec.attempts += 1
        rec.updated_at = time.time()

        try:
            # ── 1. Deduplication Check ──────────────────────────────────────────
            existing = self.db.find_existing_track(isrc=track.isrc, title=track.title, artist=track.artists[0] if track.artists else "")
            if existing:
                logger.info("Track '%s' already indexed in library (id=%s). Deduplicating.", track.title, existing.id)
                rec.status = JobStatus.COMPLETED
                rec.drive_file_id = existing.drive_file_id
                rec.local_path = existing.local_path
                rec.checksum = existing.checksum
                rec.quality = existing.quality_badge
                rec.completed_at = time.time()
                self.db.update_job_track(rec)
                self.db.update_job_status(rec.job_id, JobStatus.PENDING, completed_delta=1)

                self.emit_event("track.completed", {
                    "job_id": rec.job_id,
                    "track_id": track.spotify_id,
                    "title": track.title,
                    "quality": existing.quality_badge,
                    "deduplicated": True
                })
                return

            # ── 2. Provider Discovery & Matching ─────────────────────────────────
            rec.status = JobStatus.RESOLVING
            self.db.update_job_track(rec)
            self.emit_event("track.started", {"job_id": rec.job_id, "track_id": track.spotify_id, "title": track.title})

            candidates = await provider_registry.get_all_candidates(track)
            if not candidates:
                rec.status = JobStatus.FAILED
                rec.error = "No candidates found on any active provider."
                self.db.update_job_track(rec)
                self.db.update_job_status(rec.job_id, JobStatus.PENDING, failed_delta=1)
                self.emit_event("track.failed", {"job_id": rec.job_id, "track_id": track.spotify_id, "error": rec.error})
                return

            # Match scoring
            rec.status = JobStatus.MATCHING
            self.db.update_job_track(rec)

            ranked_candidates, is_ambiguous = match_engine.evaluate_candidates(track, candidates)
            self.db.save_candidates(rec.id, ranked_candidates)

            if not ranked_candidates:
                rec.status = JobStatus.FAILED
                rec.error = "No candidates met the match confidence threshold."
                self.db.update_job_track(rec)
                self.db.update_job_status(rec.job_id, JobStatus.PENDING, failed_delta=1)
                self.emit_event("track.failed", {"job_id": rec.job_id, "track_id": track.spotify_id, "error": rec.error})
                return

            # ── 3. Quality Selection ────────────────────────────────────────────
            selected_cand = quality_engine.select_best(ranked_candidates)
            if not selected_cand:
                rec.status = JobStatus.FAILED
                rec.error = "No genuinely lossless FLAC candidate available."
                self.db.update_job_track(rec)
                self.db.update_job_status(rec.job_id, JobStatus.PENDING, failed_delta=1)
                self.emit_event("track.failed", {"job_id": rec.job_id, "track_id": track.spotify_id, "error": rec.error})
                return

            rec.provider = selected_cand.provider
            rec.provider_id = selected_cand.provider_id
            rec.quality = selected_cand.quality_badge
            self.emit_event("track.quality_selected", {
                "job_id": rec.job_id,
                "track_id": track.spotify_id,
                "quality": selected_cand.quality_badge,
                "provider": selected_cand.provider
            })

            # ── 4. Download ────────────────────────────────────────────────────
            rec.status = JobStatus.DOWNLOADING
            self.db.update_job_track(rec)
            self.emit_event("track.downloading", {"job_id": rec.job_id, "track_id": track.spotify_id})

            provider = provider_registry.get_provider(selected_cand.provider)
            if not provider:
                raise RuntimeError(f"Provider {selected_cand.provider} no longer available.")

            download_dest = str(self.temp_dir / rec.id)
            local_audio_path = await provider.download(selected_cand, download_dest)
            rec.local_path = local_audio_path

            # ── 5. FLAC Binary Validation ───────────────────────────────────────
            rec.status = JobStatus.VALIDATING
            self.db.update_job_track(rec)
            self.emit_event("track.validating", {"job_id": rec.job_id, "track_id": track.spotify_id})

            flac_props = flac_validator.validate_file(local_audio_path)
            rec.checksum = flac_props.checksum_sha256

            # ── 6. Metadata Processing ──────────────────────────────────────────
            rec.status = JobStatus.PROCESSING_METADATA
            self.db.update_job_track(rec)

            metadata_processor.process_metadata(local_audio_path, track)

            # Re-verify checksum after tag embedding
            updated_props = flac_validator.validate_file(local_audio_path)
            rec.checksum = updated_props.checksum_sha256

            # ── 7. Storage (Google Drive + Local) ───────────────────────────────
            rec.status = JobStatus.UPLOADING
            self.db.update_job_track(rec)
            self.emit_event("track.uploading", {"job_id": rec.job_id, "track_id": track.spotify_id})

            job = self.db.get_job(rec.job_id) if rec.job_id else None
            playlist_name = job.playlist_name if (job and job.playlist_name) else (track.album or None)
            remote_rel_path = build_track_storage_path(
                track,
                playlist_name=playlist_name,
                include_artist_folder=False,
            )

            # Primary: Google Drive if available
            drive_file_id = None
            if self.gdrive_storage.is_available:
                try:
                    drive_file_id = await self.gdrive_storage.upload(local_audio_path, remote_rel_path)
                    rec.drive_file_id = drive_file_id
                except Exception as exc:
                    logger.error("Google Drive upload failed for '%s': %s", track.title, exc)

            # Secondary / Cache: Local persistent storage
            stored_local_path = await self.local_storage.upload(local_audio_path, remote_rel_path)
            rec.local_path = stored_local_path

            # Clean up temporary download file from scratch folder
            try:
                temp_file = Path(local_audio_path)
                if temp_file.exists() and temp_file.resolve() != Path(stored_local_path).resolve():
                    temp_file.unlink()
                if temp_file.parent.exists() and temp_file.parent != self.temp_dir:
                    temp_file.parent.rmdir()
            except Exception as e:
                logger.debug("Temp file cleanup note: %s", e)

            # ── 8. Index in Music Library ───────────────────────────────────────
            lib_track = LibraryTrack(
                id=track.spotify_id,
                isrc=track.isrc,
                title=track.title,
                artists=track.artists,
                album=track.album,
                album_artist=track.album_artist,
                duration_ms=int(updated_props.duration_seconds * 1000) or track.duration_ms,
                disc_number=track.disc_number,
                track_number=track.track_number,
                release_date=track.release_date,
                artwork_url=track.artwork_url,
                source_url=track.source_url,
                drive_file_id=drive_file_id,
                local_path=stored_local_path,
                checksum=updated_props.checksum_sha256,
                codec=updated_props.codec,
                sample_rate=updated_props.sample_rate,
                bit_depth=updated_props.bit_depth,
                channels=updated_props.channels,
                file_size_bytes=updated_props.file_size_bytes,
                created_at=time.time(),
                updated_at=time.time()
            )
            self.db.upsert_library_track(lib_track)

            # ── 9. Finalize Success ─────────────────────────────────────────────
            rec.status = JobStatus.COMPLETED
            rec.completed_at = time.time()
            rec.progress = 1.0
            self.db.update_job_track(rec)
            self.db.update_job_status(rec.job_id, JobStatus.PENDING, completed_delta=1)

            self.emit_event("track.completed", {
                "job_id": rec.job_id,
                "track_id": track.spotify_id,
                "title": track.title,
                "quality": lib_track.quality_badge,
                "drive_file_id": drive_file_id
            })

            # Check if entire job is completed
            job = self.db.get_job(rec.job_id)
            if job and (job.completed_tracks + job.failed_tracks) >= job.total_tracks:
                final_status = JobStatus.COMPLETED if job.completed_tracks > 0 else JobStatus.FAILED
                self.db.update_job_status(rec.job_id, final_status)
                self.emit_event("job.completed", {
                    "job_id": job.id,
                    "status": final_status.value,
                    "completed": job.completed_tracks,
                    "failed": job.failed_tracks
                })

        except Exception as exc:
            logger.error("Track processing failed for '%s' (id=%s): %s", track.title, rec.track_id, exc, exc_info=True)
            rec.status = JobStatus.FAILED
            rec.error = str(exc)
            self.db.update_job_track(rec)
            self.db.update_job_status(rec.job_id, JobStatus.PENDING, failed_delta=1)
            self.emit_event("track.failed", {"job_id": rec.job_id, "track_id": track.spotify_id, "error": str(exc)})


# Global job manager
music_job_manager = MusicJobManager()
