"""
Julius Production Lossless Music Platform Subsystem.
"""

from .models import Track, ProviderCandidate, DownloadRecord, MusicJob, LibraryTrack, JobStatus
from .db import MusicDatabase
from .spotify import SpotifyResolver, spotify_resolver
from .matching import MatchEngine, match_engine
from .quality import QualityEngine, quality_engine
from .flac_validator import FlacValidator, flac_validator
from .metadata import MetadataProcessor, metadata_processor
from .storage import StorageBackend, GoogleDriveStorage, LocalStorageBackend, gdrive_storage
from .jobs import MusicJobManager, music_job_manager
from .library import MusicLibrary, music_library
from .streaming import AudioStreamer, audio_streamer
from .diagnostics import MusicDiagnostics, music_diagnostics
from .api import setup_music_routes

__all__ = [
    "Track",
    "ProviderCandidate",
    "DownloadRecord",
    "MusicJob",
    "LibraryTrack",
    "JobStatus",
    "MusicDatabase",
    "SpotifyResolver",
    "spotify_resolver",
    "MatchEngine",
    "match_engine",
    "QualityEngine",
    "quality_engine",
    "FlacValidator",
    "flac_validator",
    "MetadataProcessor",
    "metadata_processor",
    "StorageBackend",
    "GoogleDriveStorage",
    "LocalStorageBackend",
    "gdrive_storage",
    "MusicJobManager",
    "music_job_manager",
    "MusicLibrary",
    "music_library",
    "AudioStreamer",
    "audio_streamer",
    "MusicDiagnostics",
    "music_diagnostics",
    "setup_music_routes",
]
