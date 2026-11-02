"""
First-Class Julius Music Import Tool Abstraction.
Encapsulates intent execution, playlist resolution, provider matching, quality selection,
background queue job submission, progress tracking, and dry-run diagnostics.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from src.music.jobs import MusicJobManager, music_job_manager
from src.music.models import JobStatus, Track
from src.music.providers.registry import provider_registry
from src.services.music_matcher import music_matcher
from src.services.quality_resolver import quality_resolver
from src.services.spotify_service import spotify_service

logger = logging.getLogger("julius.music.tool")


@dataclass
class ImportJobResult:
    """Standardized machine- and human-readable result from import_spotify_playlist tool."""
    job_id: str
    playlist_name: str
    total: int
    completed: int
    existing: int
    skipped: int
    failed: int
    status: str
    best_quality: str = "FLAC Lossless"
    destination: str = "Google Drive (Julius Songs/)"
    message: str = ""
    dry_run: bool = False
    dry_run_preview: Optional[List[Dict[str, Any]]] = None

    @property
    def summary(self) -> str:
        return self.message

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["summary"] = self.message
        return d


class MusicImportTool:
    """First-class tool for autonomous Spotify Playlist -> FLAC -> Google Drive orchestration."""

    name = "import_spotify_playlist"

    def __init__(
        self,
        manager: Optional[MusicJobManager] = None,
        job_manager: Optional[MusicJobManager] = None,
        provider_registry: Any = None,
        spotify_service: Any = None
    ) -> None:
        from src.music.providers.registry import provider_registry as default_registry
        from src.services.spotify_service import spotify_service as default_spotify
        self.job_manager = job_manager or manager or music_job_manager
        self.provider_registry = provider_registry or default_registry
        self.spotify_service = spotify_service or default_spotify

    async def execute(
        self,
        playlist_url: str,
        quality_policy: str = "best_lossless",
        destination: str = "google_drive",
        dry_run: bool = False,
        user_id: str = "user_default"
    ) -> ImportJobResult:
        """
        Execute or schedule the playlist import job.
        """
        if not playlist_url or not isinstance(playlist_url, str):
            return ImportJobResult(
                job_id="",
                playlist_name="",
                total=0,
                completed=0,
                existing=0,
                skipped=0,
                failed=0,
                status="FAILED",
                message="A valid Spotify playlist URL is required."
            )

        # 1. Validate URL and resolve playlist
        try:
            if hasattr(self.spotify_service, "get_playlist_tracks") and callable(self.spotify_service.get_playlist_tracks) and ("get_playlist_tracks" in getattr(self.spotify_service, "__dict__", {}) or not hasattr(self.spotify_service, "resolve_playlist")):
                res = self.spotify_service.get_playlist_tracks(playlist_url)
                if asyncio.iscoroutine(res):
                    res = await res
                if isinstance(res, tuple):
                    playlist_name, tracks = res
                elif isinstance(res, list):
                    playlist_name, tracks = "Spotify Playlist", res
                else:
                    playlist_name, tracks = "Spotify Playlist", []
            elif hasattr(self.spotify_service, "resolve_playlist") and callable(self.spotify_service.resolve_playlist):
                playlist_name, tracks = await asyncio.to_thread(
                    self.spotify_service.resolve_playlist, playlist_url
                )
            elif hasattr(self.spotify_service, "get_playlist_tracks") and callable(self.spotify_service.get_playlist_tracks):
                res = self.spotify_service.get_playlist_tracks(playlist_url)
                if asyncio.iscoroutine(res):
                    res = await res
                if isinstance(res, tuple):
                    playlist_name, tracks = res
                elif isinstance(res, list):
                    playlist_name, tracks = "Spotify Playlist", res
                else:
                    playlist_name, tracks = "Spotify Playlist", []
            else:
                playlist_name, tracks = "Spotify Playlist", []

            # Ensure all tracks are strongly-typed Track domain objects
            tracks = [Track.from_dict(t) if isinstance(t, dict) else t for t in tracks]
        except Exception as exc:
            return ImportJobResult(
                job_id="",
                playlist_name="",
                total=0,
                completed=0,
                existing=0,
                skipped=0,
                failed=0,
                status="FAILED",
                message=f"Failed to resolve Spotify playlist: {exc}"
            )

        if not tracks:
            return ImportJobResult(
                job_id="",
                playlist_name=playlist_name,
                total=0,
                completed=0,
                existing=0,
                skipped=0,
                failed=0,
                status="COMPLETED",
                message=f"Playlist '{playlist_name}' contains no playable tracks."
            )

        # 2. Dry-Run Diagnostic Simulation
        if dry_run:
            logger.info("Executing dry-run analysis for '%s' (%d tracks)", playlist_name, len(tracks))
            preview_items = []
            for t in tracks[:15]:  # Preview first 15 tracks
                candidates = await self.provider_registry.search_all(t)
                best_match = music_matcher.find_best_match(t, candidates)
                if best_match:
                    q_res = quality_resolver.resolve([best_match.candidate], policy=quality_policy)
                    preview_items.append({
                        "track": f"{t.title} — {t.artist_display}",
                        "provider": best_match.candidate.provider.upper(),
                        "quality": q_res.quality_badge if q_res else best_match.candidate.quality_badge,
                        "match_score": f"{best_match.score:.0f}%",
                        "status": "READY"
                    })
                else:
                    preview_items.append({
                        "track": f"{t.title} — {t.artist_display}",
                        "provider": "N/A",
                        "quality": "None",
                        "match_score": "0%",
                        "status": "NO_CONFIDENT_MATCH"
                    })

            lines = [
                f"🔍 Dry-Run Diagnostics for '{playlist_name}' ({len(tracks)} tracks total):",
                f"{'Track':<42} {'Provider':<10} {'Quality':<22} {'Match':<6}",
                "─" * 84,
            ]
            for item in preview_items:
                lines.append(f"{item['track'][:40]:<42} {item['provider']:<10} {item['quality']:<22} {item['match_score']:<6}")

            summary_msg = "\n".join(lines)
            return ImportJobResult(
                job_id="dry_run_sim",
                playlist_name=playlist_name,
                total=len(tracks),
                completed=0,
                existing=0,
                skipped=0,
                failed=0,
                status="dry_run",
                message=summary_msg,
                dry_run=True,
                dry_run_preview=preview_items
            )

        # 3. Persistent Background Job Submission
        job = await self.job_manager.submit_playlist_job(
            user_id=user_id,
            playlist_url=playlist_url,
            playlist_name=playlist_name,
            tracks=tracks,
            quality_policy=quality_policy
        )

        msg = (
            f"🎵 Import job created\n"
            f"Playlist: {playlist_name}\n"
            f"Tracks: {len(tracks)}\n"
            f"Job ID: {job.id}\n"
            f"Destination: Google Drive (Julius Songs/)\n"
            f"Processing started in background."
        )

        return ImportJobResult(
            job_id=job.id,
            playlist_name=playlist_name,
            total=len(tracks),
            completed=0,
            existing=0,
            skipped=0,
            failed=0,
            status=job.status.value,
            message=msg
        )

    def get_status(self, job_id: str) -> Dict[str, Any]:
        """Query progress and track-level breakdown of an existing job."""
        job = self.job_manager.db.get_job(job_id)
        if not job:
            return {"error": f"Job '{job_id}' not found."}

        records = self.job_manager.db.get_job_tracks_for_job(job_id)
        completed_recs = [r for r in records if r.status == JobStatus.COMPLETED]
        failed_recs = [r for r in records if r.status == JobStatus.FAILED]
        skipped_recs = [r for r in records if r.status == JobStatus.SKIPPED]

        progress_pct = int((len(completed_recs) / max(1, job.total_tracks)) * 100)
        return {
            "job_id": job.id,
            "playlist_name": job.playlist_name,
            "status": job.status.value,
            "total_tracks": job.total_tracks,
            "completed": len(completed_recs),
            "failed": len(failed_recs),
            "skipped": len(skipped_recs),
            "progress_percent": progress_pct,
            "failed_details": [
                {"track_id": r.track_id, "error": r.error, "attempts": r.attempts}
                for r in failed_recs
            ]
        }

    async def retry_job(self, job_id: str) -> Dict[str, Any]:
        """Retry failed tracks from an existing import job."""
        success = await self.job_manager.retry_failed_job(job_id)
        return {
            "job_id": job_id,
            "retried": success,
            "message": "Retry scheduled for failed tracks." if success else "No failed tracks to retry or job not found."
        }

    def cancel_job(self, job_id: str) -> Dict[str, Any]:
        """Cancel a running import job."""
        success = self.job_manager.cancel_job(job_id)
        return {
            "job_id": job_id,
            "cancelled": success,
            "message": f"Job '{job_id}' cancelled." if success else f"Job '{job_id}' could not be cancelled."
        }


# Global tool instance
music_import_tool = MusicImportTool()
