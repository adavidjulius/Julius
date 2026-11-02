"""
Observability, Health & Diagnostics Engine for Julius Music Subsystem.
Tracks queue depths, worker status, provider connectivity, and storage health
without leaking credentials or tokens.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict

from src.music.db import MusicDatabase
from src.music.jobs import MusicJobManager, music_job_manager
from src.music.providers.registry import ProviderRegistry, provider_registry
from src.music.spotify import SpotifyResolver, spotify_resolver
from src.music.storage.gdrive import GoogleDriveStorage, gdrive_storage
from src.music.storage.local import LocalStorageBackend

logger = logging.getLogger("julius.music.diagnostics")


class MusicDiagnostics:
    """Collects safe health and operational metrics across the music pipeline."""

    def __init__(
        self,
        db: Optional[MusicDatabase] = None,
        job_mgr: Optional[MusicJobManager] = None,
        sp_resolver: Optional[SpotifyResolver] = None,
        registry: Optional[ProviderRegistry] = None,
        gdrive: Optional[GoogleDriveStorage] = None,
    ) -> None:
        self.db = db or MusicDatabase()
        self.job_mgr = job_mgr or music_job_manager
        self.spotify = sp_resolver or spotify_resolver
        self.registry = registry or provider_registry
        self.gdrive = gdrive or gdrive_storage
        self.local_storage = LocalStorageBackend()

    def get_status_report(self) -> Dict[str, Any]:
        """Aggregate safe operational status report for admin console and monitoring."""
        # Database connectivity check
        db_healthy = False
        try:
            conn = self.db.get_connection()
            conn.execute("SELECT 1").fetchone()
            db_healthy = True
        except Exception:
            db_healthy = False

        # Providers
        providers = self.registry.list_providers()

        # Storage
        gdrive_status = {
            "available": self.gdrive.is_available,
            "root_folder_configured": bool(self.gdrive.root_folder_id),
            "credentials_file_configured": bool(os.path.exists(self.gdrive.credentials_path))
        }

        local_status = {
            "available": self.local_storage.is_available,
            "root_dir": str(self.local_storage.root_dir),
        }

        # Queue metrics
        queue_size = self.job_mgr.queue.qsize() if hasattr(self.job_mgr, "queue") else 0
        workers_count = len(self.job_mgr.workers)

        # Library stats
        try:
            library_stats = self.db.get_library_stats()
        except Exception:
            library_stats = {}

        return {
            "status": "healthy" if db_healthy else "degraded",
            "database": {
                "engine": "sqlite-wal",
                "connected": db_healthy,
                "path": str(self.db.db_path)
            },
            "spotify": {
                "authenticated": self.spotify.is_authenticated,
                "client_id_configured": bool(self.spotify.client_id)
            },
            "providers": providers,
            "storage": {
                "gdrive": gdrive_status,
                "local": local_status
            },
            "jobs": {
                "active_workers": workers_count,
                "max_concurrency": self.job_mgr.max_concurrent,
                "queue_depth": queue_size,
            },
            "library": library_stats,
        }


# Global diagnostics instance
music_diagnostics = MusicDiagnostics()
