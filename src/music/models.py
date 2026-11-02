"""
Canonical Music Domain Models for Julius.
Defines normalized track representations, provider candidate structures,
job records, and quality rankings.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class JobStatus(str, Enum):
    PENDING = "PENDING"
    RESOLVING = "RESOLVING"
    MATCHING = "MATCHING"
    READY = "READY"
    DOWNLOADING = "DOWNLOADING"
    VALIDATING = "VALIDATING"
    PROCESSING_METADATA = "PROCESSING_METADATA"
    UPLOADING = "UPLOADING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RETRYING = "RETRYING"
    SKIPPED = "SKIPPED"


@dataclass
class Track:
    """Canonical normalized representation of a musical track from metadata providers."""
    spotify_id: str
    title: str
    artists: List[str]
    album: str
    album_artist: str = ""
    isrc: Optional[str] = None
    duration_ms: int = 0
    disc_number: int = 1
    track_number: int = 1
    release_date: str = ""
    explicit: bool = False
    artwork_url: str = ""
    source_url: str = ""

    def __post_init__(self):
        if not self.album_artist and self.artists:
            self.album_artist = self.artists[0]

    @property
    def artist_display(self) -> str:
        return ", ".join(self.artists) if self.artists else "Unknown Artist"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Track:
        artists = data.get("artists", [])
        if isinstance(artists, str):
            try:
                artists = json.loads(artists)
            except Exception:
                artists = [artists]
        return cls(
            spotify_id=data.get("spotify_id", ""),
            title=data.get("title", ""),
            artists=artists,
            album=data.get("album", ""),
            album_artist=data.get("album_artist", ""),
            isrc=data.get("isrc"),
            duration_ms=int(data.get("duration_ms", 0)),
            disc_number=int(data.get("disc_number", 1)),
            track_number=int(data.get("track_number", 1)),
            release_date=data.get("release_date", ""),
            explicit=bool(data.get("explicit", False)),
            artwork_url=data.get("artwork_url", ""),
            source_url=data.get("source_url", ""),
        )


@dataclass
class ProviderCandidate:
    """Candidate match found on an authorized music provider."""
    provider: str
    provider_id: str
    title: str
    artists: List[str]
    album: str
    album_artist: str = ""
    isrc: Optional[str] = None
    duration_ms: int = 0
    format: str = "FLAC"
    codec: str = "flac"
    sample_rate: int = 44100
    bit_depth: int = 16
    channels: int = 2
    release_date: str = ""
    artwork: str = ""
    availability: bool = True
    score: float = 0.0
    download_url: Optional[str] = None
    extra_metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def quality_badge(self) -> str:
        khz = self.sample_rate / 1000.0
        khz_str = f"{khz:.1f}".rstrip("0").rstrip(".")
        return f"{self.bit_depth}-bit / {khz_str} kHz {self.format.upper()}"

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["quality_badge"] = self.quality_badge
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ProviderCandidate:
        artists = data.get("artists", [])
        if isinstance(artists, str):
            try:
                artists = json.loads(artists)
            except Exception:
                artists = [artists]
        return cls(
            provider=data.get("provider", "unknown"),
            provider_id=data.get("provider_id", ""),
            title=data.get("title", ""),
            artists=artists,
            album=data.get("album", ""),
            album_artist=data.get("album_artist", ""),
            isrc=data.get("isrc"),
            duration_ms=int(data.get("duration_ms", 0)),
            format=data.get("format", "FLAC"),
            codec=data.get("codec", "flac"),
            sample_rate=int(data.get("sample_rate", 44100)),
            bit_depth=int(data.get("bit_depth", 16)),
            channels=int(data.get("channels", 2)),
            release_date=data.get("release_date", ""),
            artwork=data.get("artwork", ""),
            availability=bool(data.get("availability", True)),
            score=float(data.get("score", 0.0)),
            download_url=data.get("download_url"),
            extra_metadata=data.get("extra_metadata", {}),
        )


@dataclass
class MatchResult:
    """Outcome of evaluating a provider candidate against a canonical track."""
    candidate: ProviderCandidate
    score: float
    confidence: str  # "high", "medium", "low", "none"
    reasons: List[str] = field(default_factory=list)

    @property
    def is_confident(self) -> bool:
        return self.confidence in ("high", "medium") and self.score >= 70.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate": self.candidate.to_dict(),
            "score": self.score,
            "confidence": self.confidence,
            "reasons": self.reasons,
            "is_confident": self.is_confident
        }


@dataclass
class QualityResult:
    """Selected audio quality parameters for an acquisition candidate."""
    candidate: ProviderCandidate
    policy: str
    codec: str
    bit_depth: int
    sample_rate: int
    channels: int
    quality_badge: str
    is_valid_lossless: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate": self.candidate.to_dict(),
            "policy": self.policy,
            "codec": self.codec,
            "bit_depth": self.bit_depth,
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "quality_badge": self.quality_badge,
            "is_valid_lossless": self.is_valid_lossless
        }


@dataclass
class DownloadRecord:
    """Persistent execution tracking for a specific track download."""
    id: str
    job_id: str
    track_id: str  # spotify_id
    provider: str
    provider_id: str
    status: JobStatus = JobStatus.PENDING
    attempts: int = 0
    error: Optional[str] = None
    quality: str = ""
    local_path: Optional[str] = None
    checksum: Optional[str] = None
    drive_file_id: Optional[str] = None
    created_at: float = 0.0
    updated_at: float = 0.0
    completed_at: Optional[float] = None
    progress: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value if isinstance(self.status, JobStatus) else str(self.status)
        return d


@dataclass
class MusicJob:
    """Playlist or batch ingestion job."""
    id: str
    user_id: str
    playlist_url: str
    playlist_name: str
    status: JobStatus = JobStatus.PENDING
    total_tracks: int = 0
    completed_tracks: int = 0
    failed_tracks: int = 0
    created_at: float = 0.0
    updated_at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value if isinstance(self.status, JobStatus) else str(self.status)
        return d


@dataclass
class LibraryTrack:
    """Searchable indexed track in the Julius Lossless Music Library."""
    id: str  # Unique hash or spotify_id
    isrc: Optional[str]
    title: str
    artists: List[str]
    album: str
    album_artist: str
    duration_ms: int
    disc_number: int
    track_number: int
    release_date: str
    artwork_url: str
    source_url: str
    drive_file_id: Optional[str]
    local_path: Optional[str]
    checksum: str
    codec: str
    sample_rate: int
    bit_depth: int
    channels: int
    file_size_bytes: int
    created_at: float
    updated_at: float

    @property
    def quality_badge(self) -> str:
        khz = self.sample_rate / 1000.0
        khz_str = f"{khz:.1f}".rstrip("0").rstrip(".")
        return f"{self.bit_depth}-bit / {khz_str} kHz {self.codec.upper()}"

    @property
    def artist_display(self) -> str:
        return ", ".join(self.artists) if self.artists else (self.album_artist or "Unknown Artist")

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["quality_badge"] = self.quality_badge
        d["artist_display"] = self.artist_display

        d["stream_url"] = f"/api/music/tracks/{self.id}/stream"
        d["cover_url"] = f"/api/music/tracks/{self.id}/artwork"
        if not d.get("artwork_url"):
            d["artwork_url"] = f"/api/music/tracks/{self.id}/artwork"
        return d
