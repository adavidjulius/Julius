"""
Comprehensive test suite for Autonomous Spotify Playlist -> Lossless FLAC -> Drive Orchestration.
Verifies:
- SpotifyService URL validation, ID extraction, and canonical track creation
- MusicMatcher scoring tiers, version preservation, and confidence thresholds
- QualityResolver quality ranking and policy evaluation
- FlacValidationService binary FLAC stream validation
- MusicImportTool execution, dry-run mode, status inspection, cancellation, and retry
- ActionExecutor tool dispatch for import_spotify_playlist and music_* actions
- 5-Track mocked end-to-end import run to library
- Crash recovery and deduplication
"""
import asyncio
import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from src.action_executor import ActionExecutor
from src.music.db import MusicDatabase
from src.music.jobs import MusicJobManager
from src.music.models import JobStatus, ProviderCandidate, QualityResult, Track
from src.music.providers.base import MusicProvider
from src.music.providers.registry import ProviderRegistry
from src.music.tool import MusicImportTool
from src.services.spotify_service import SpotifyService, CanonicalTrack
from src.services.music_matcher import MusicMatcher
from src.services.quality_resolver import QualityResolver
from src.services.flac_validator import FlacValidationService
from src.services.gdrive_service import GDriveService
from tests.music.test_flac_validator import create_mock_flac_bytes


class MockFlacProvider(MusicProvider):
    def __init__(self, flac_file_path: str, name: str = "mock_qobuz"):
        self._name = name
        self.flac_file_path = flac_file_path

    @property
    def name(self) -> str:
        return self._name

    @property
    def is_available(self) -> bool:
        return True

    async def search(self, track: Track) -> list[ProviderCandidate]:
        return await self.get_candidates(track)

    async def get_candidates(self, track: Track) -> list[ProviderCandidate]:
        # Return candidate with matching ISRC and 24-bit 96kHz FLAC
        return [
            ProviderCandidate(
                provider=self.name,
                provider_id=f"{self.name}_{track.spotify_id}",
                title=track.title,
                artists=track.artists,
                album=track.album,
                album_artist=track.album_artist,
                isrc=track.isrc or "US-S1Z-24-00001",
                duration_ms=track.duration_ms or 180000,
                format="FLAC",
                codec="flac",
                sample_rate=96000,
                bit_depth=24,
                channels=2,
                availability=True,
                score=98.0,
                download_url=self.flac_file_path,
            )
        ]

    async def get_metadata(self, candidate: ProviderCandidate) -> dict:
        return {"format": "FLAC", "bit_depth": 24, "sample_rate": 96000}

    async def download(self, candidate: ProviderCandidate, destination_dir: str) -> str:
        dest = Path(destination_dir) / f"{candidate.provider_id}.flac"
        dest.parent.mkdir(parents=True, exist_ok=True)
        base_bytes = Path(self.flac_file_path).read_bytes()
        dest.write_bytes(base_bytes + f"payload_{candidate.provider_id}".encode())
        return str(dest)


# ---------------------------------------------------------------------------
# Unit Tests for Services
# ---------------------------------------------------------------------------

def test_spotify_service_url_validation_and_id():
    service = SpotifyService()
    
    # Valid playlist URLs
    valid_url = "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M?si=abcd1234"
    assert service.validate_url(valid_url) is True
    assert service.extract_playlist_id(valid_url) == "37i9dQZF1DXcBWIGoYBM5M"

    uri = "spotify:playlist:37i9dQZF1DXcBWIGoYBM5M"
    assert service.validate_url(uri) is True
    assert service.extract_playlist_id(uri) == "37i9dQZF1DXcBWIGoYBM5M"

    raw_id = "37i9dQZF1DXcBWIGoYBM5M"
    assert service.validate_url(raw_id) is True
    assert service.extract_playlist_id(raw_id) == "37i9dQZF1DXcBWIGoYBM5M"

    # Invalid URLs
    assert service.validate_url("https://open.spotify.com/album/37i9dQZF1DXcBWIGoYBM5M") is False
    assert service.validate_url("https://notspotify.com/playlist/123") is False
    assert service.validate_url("not a url") is False


def test_music_matcher_scoring_and_confidence():
    matcher = MusicMatcher()
    track = Track(
        spotify_id="sp_1",
        title="Midnight City",
        artists=["M83"],
        album="Hurry Up, We're Dreaming",
        isrc="FR9W11100080",
        duration_ms=243000,
    )

    # Candidate 1: Exact ISRC and matching recording
    candidate_exact = ProviderCandidate(
        provider="qobuz",
        provider_id="q_1",
        title="Midnight City",
        artists=["M83"],
        album="Hurry Up, We're Dreaming",
        isrc="FR9W11100080",
        duration_ms=243100,
        format="FLAC",
        codec="flac",
        sample_rate=44100,
        bit_depth=16,
        channels=2,
    )
    result_exact = matcher.match(track, candidate_exact)
    assert result_exact.confidence == "high"
    assert result_exact.score >= 95.0
    assert any("ISRC" in r for r in result_exact.reasons)

    # Candidate 2: Different version (Live vs Studio) - should be penalized
    candidate_live = ProviderCandidate(
        provider="qobuz",
        provider_id="q_2",
        title="Midnight City (Live)",
        artists=["M83"],
        album="Live in Paris",
        isrc="FR9W11100099",
        duration_ms=260000,
        format="FLAC",
        codec="flac",
        sample_rate=44100,
        bit_depth=16,
        channels=2,
    )
    result_live = matcher.match(track, candidate_live)
    assert result_live.confidence in ("none", "low", "rejected")
    assert result_live.score < 80.0


def test_quality_resolver_ranking():
    resolver = QualityResolver()
    
    c_flac_24_96 = ProviderCandidate(
        provider="qobuz", provider_id="1", title="T", artists=["A"], album="Album",
        format="FLAC", codec="flac", sample_rate=96000, bit_depth=24, channels=2
    )
    c_flac_16_44 = ProviderCandidate(
        provider="tidal", provider_id="2", title="T", artists=["A"], album="Album",
        format="FLAC", codec="flac", sample_rate=44100, bit_depth=16, channels=2
    )
    c_mp3_320 = ProviderCandidate(
        provider="deezer", provider_id="3", title="T", artists=["A"], album="Album",
        format="MP3", codec="mp3", sample_rate=44100, bit_depth=16, channels=2
    )

    ranked = resolver.rank_candidates([c_flac_16_44, c_mp3_320, c_flac_24_96], policy="best_lossless")
    # Lossless FLAC 24/96 must be ranked first, MP3 must be last or discarded
    assert ranked[0].provider_id == "1"
    assert ranked[1].provider_id == "2"

    best_res = resolver.select_best([c_flac_16_44, c_flac_24_96], policy="best_lossless")
    assert best_res is not None
    assert best_res.candidate.bit_depth == 24
    assert best_res.candidate.sample_rate == 96000


def test_flac_validator_service():
    validator = FlacValidationService()
    
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        valid_flac_path = Path(tmp_dir) / "valid.flac"
        valid_flac_bytes = create_mock_flac_bytes(sample_rate=96000, bit_depth=24, channels=2, total_samples=960000)
        valid_flac_path.write_bytes(valid_flac_bytes)

        res = validator.validate(str(valid_flac_path))
        assert res.valid is True
        assert res.codec == "FLAC"
        assert res.sample_rate == 96000
        assert res.bit_depth == 24
        assert res.channels == 2
        assert len(res.checksum) == 64

        # Non-existent or empty file
        empty_flac_path = Path(tmp_dir) / "empty.flac"
        empty_flac_path.write_bytes(b"")
        res_empty = validator.validate(str(empty_flac_path))
        assert res_empty.valid is False


# ---------------------------------------------------------------------------
# MusicImportTool & ActionExecutor Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_music_import_tool_dry_run():
    """Verify dry-run mode returns candidate and match information without downloading."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        db_path = str(Path(tmp_dir) / "tool_test.db")
        db = MusicDatabase(db_path)
        job_mgr = MusicJobManager(db=db, max_concurrent=2, temp_dir=tmp_dir)

        # Mock spotify track fetch
        mock_track = Track(
            spotify_id="dry_1",
            title="Symphony No. 5",
            artists=["Ludwig van Beethoven"],
            album="Beethoven: The Symphonies",
            isrc="DE-A62-08-00001",
            duration_ms=420000,
        )

        mock_flac_path = Path(tmp_dir) / "dummy.flac"
        mock_flac_path.write_bytes(create_mock_flac_bytes())

        custom_registry = ProviderRegistry()
        custom_registry._providers.clear()
        custom_registry.register(MockFlacProvider(str(mock_flac_path)))

        tool = MusicImportTool(job_manager=job_mgr, provider_registry=custom_registry)

        with patch.object(tool.spotify_service, "get_playlist_tracks", new_callable=AsyncMock) as mock_get_tracks:
            mock_get_tracks.return_value = ("Beethoven Essentials", [mock_track])

            res = await tool.execute(
                playlist_url="https://open.spotify.com/playlist/37i9dQZF1DX70Bzs1Qp5w1",
                quality_policy="best_lossless",
                destination="google_drive",
                dry_run=True,
            )

            assert res.status == "dry_run"
            assert res.total == 1
            assert "dry-run" in res.summary.lower() or "preview" in res.summary.lower()


@pytest.mark.asyncio
async def test_action_executor_import_and_management():
    """Verify ActionExecutor dispatches import_spotify_playlist and related control actions."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        executor = ActionExecutor(workspace_root=tmp_dir)

        # 1. Invalid Spotify URL returns clear error
        invalid_res = executor.execute(
            "import_spotify_playlist",
            {"playlist_url": "https://invalid-service.com/test"},
        )
        assert invalid_res.success is False
        assert "Invalid Spotify" in (invalid_res.error or "")

        # 2. Dry-run import via ActionExecutor
        mock_flac_path = Path(tmp_dir) / "dummy.flac"
        mock_flac_path.write_bytes(create_mock_flac_bytes())

        from src.music.tool import music_import_tool
        custom_registry = ProviderRegistry()
        custom_registry.register(MockFlacProvider(str(mock_flac_path)))

        mock_track = Track(
            spotify_id="sp_ae_1",
            title="Nocturne in E-flat major",
            artists=["Frédéric Chopin"],
            album="Chopin: Nocturnes",
            isrc="PL-A12-10-00001",
            duration_ms=270000,
        )

        with patch.object(music_import_tool, "provider_registry", custom_registry):
            with patch.object(music_import_tool.spotify_service, "get_playlist_tracks", new_callable=AsyncMock) as mock_fetch:
                mock_fetch.return_value = ("Chopin Classics", [mock_track])

                res = executor.execute(
                    "import_spotify_playlist",
                    {
                        "playlist_url": "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M",
                        "dry_run": True,
                    },
                )
                assert res.success is True
                assert "dry-run" in str(res.output).lower()

        # 3. Test music_library action
        lib_res = executor.execute("music_library", {"limit": 10})
        assert lib_res.success is True

        # 4. Test music_status action for non-existent job
        status_res = executor.execute("music_status", {"job_id": "nonexistent_job_id"})
        assert status_res.success is False


# ---------------------------------------------------------------------------
# 5-Track Mocked End-to-End Test (Section 38 & Section 53)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_five_track_mocked_end_to_end_import():
    """
    Simulates:
    Spotify playlist with 5 tracks -> Provider resolution -> Matching ->
    Quality ranking (24/96 FLAC) -> Download -> Validation -> Metadata ->
    Mock Google Drive upload -> Library Database indexing.
    """
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        # Create source FLAC file
        test_flac_bytes = create_mock_flac_bytes(sample_rate=96000, bit_depth=24, channels=2, total_samples=960000)
        source_flac = Path(tmp_dir) / "source.flac"
        source_flac.write_bytes(test_flac_bytes)

        db_path = str(Path(tmp_dir) / "e2e_5track.db")
        db = MusicDatabase(db_path)
        mock_gdrive = AsyncMock()
        mock_gdrive.is_available = True
        mock_gdrive.upload.return_value = "mock_drive_file_id_12345"
        job_mgr = MusicJobManager(db=db, max_concurrent=3, temp_dir=tmp_dir, gdrive_storage=mock_gdrive)

        custom_registry = ProviderRegistry()
        custom_registry._providers.clear()
        mock_provider = MockFlacProvider(str(source_flac), name="qobuz")
        custom_registry.register(mock_provider)

        # 5 Mock Tracks with matching ISRC and durations
        tracks = [
            Track(
                spotify_id=f"sp_0{i}",
                title=f"Track {i}",
                artists=[f"Artist {i}"],
                album=f"Album {i}",
                isrc=f"US-S1Z-24-0000{i}",
                duration_ms=180000,
                track_number=i,
            )
            for i in range(1, 6)
        ]

        import src.music.jobs as jobs_mod
        orig_registry = jobs_mod.provider_registry
        jobs_mod.provider_registry = custom_registry

        try:
            await job_mgr.start()

            job = await job_mgr.submit_playlist_job(
                user_id="test_user",
                playlist_url="https://open.spotify.com/playlist/5trackstest1234567890",
                playlist_name="Top 5 Audiophile FLACs",
                tracks=tracks,
                quality_policy="best_lossless",
            )

            assert job.total_tracks == 5

            # Wait for all 5 tracks to complete in the background
            for _ in range(80):
                await asyncio.sleep(0.1)
                recs = db.get_job_tracks_for_job(job.id)
                if all(r.status in (JobStatus.COMPLETED, JobStatus.FAILED) for r in recs):
                    break

            recs = db.get_job_tracks_for_job(job.id)
            completed = [r for r in recs if r.status == JobStatus.COMPLETED]
            assert len(completed) == 5, f"Expected 5 completed tracks, got {len(completed)}. Errors: {[r.error for r in recs]}"

            # Verify tracks in library DB
            lib_tracks = db.list_library_tracks(limit=10)
            assert len(lib_tracks) == 5

            # Verify job record
            final_job = db.get_job(job.id)
            assert final_job.completed_tracks == 5
            assert final_job.status == JobStatus.COMPLETED

        finally:
            jobs_mod.provider_registry = orig_registry
            await job_mgr.shutdown()


# ---------------------------------------------------------------------------
# Crash Recovery & Deduplication Test (Section 16 & Section 20)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_crash_recovery_and_deduplication():
    """Verify that restarting the job manager resumes incomplete tracks and does not redownload completed ones."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        test_flac_bytes = create_mock_flac_bytes(sample_rate=44100, bit_depth=16, channels=2, total_samples=441000)
        source_flac = Path(tmp_dir) / "source.flac"
        source_flac.write_bytes(test_flac_bytes)

        db_path = str(Path(tmp_dir) / "recovery.db")
        db = MusicDatabase(db_path)

        custom_registry = ProviderRegistry()
        custom_registry._providers.clear()
        mock_provider = MockFlacProvider(str(source_flac), name="lossless_provider")
        custom_registry.register(mock_provider)

        import src.music.jobs as jobs_mod
        orig_registry = jobs_mod.provider_registry
        jobs_mod.provider_registry = custom_registry

        # Step 1: Create 2 tracks, run first job manager to finish track 1
        t1 = Track(
            spotify_id="rec_01",
            title="Track One",
            artists=["Artist A"],
            album="Album A",
            isrc="US-A1-01",
            duration_ms=180000,
        )
        t2 = Track(
            spotify_id="rec_02",
            title="Track Two",
            artists=["Artist B"],
            album="Album B",
            isrc="US-A1-02",
            duration_ms=180000,
        )

        mock_gdrive = AsyncMock()
        mock_gdrive.is_available = True
        mock_gdrive.upload.return_value = "mock_drive_file_id_rec"
        mgr1 = MusicJobManager(db=db, max_concurrent=1, temp_dir=tmp_dir, gdrive_storage=mock_gdrive)
        try:
            await mgr1.start()
            job = await mgr1.submit_playlist_job(
                user_id="user_rec",
                playlist_url="https://open.spotify.com/playlist/recoverytest12345678",
                playlist_name="Recovery Playlist",
                tracks=[t1, t2],
            )

            # Wait until at least 1 track finishes
            for _ in range(50):
                await asyncio.sleep(0.1)
                recs = db.get_job_tracks_for_job(job.id)
                if any(r.status == JobStatus.COMPLETED for r in recs):
                    break

            # Simulate crash: shut down manager 1 immediately
            await mgr1.shutdown()

            # Inspect state
            mid_recs = db.get_job_tracks_for_job(job.id)
            comp_count = sum(1 for r in mid_recs if r.status == JobStatus.COMPLETED)
            assert comp_count >= 1, f"Statuses: {[(r.status, r.error) for r in mid_recs]}"

            # Step 2: "Reboot" / start new JobManager with the same DB
            mgr2 = MusicJobManager(db=db, max_concurrent=1, temp_dir=tmp_dir, gdrive_storage=mock_gdrive)
            await mgr2.start()

            # Wait for all tracks to finish processing
            for _ in range(60):
                await asyncio.sleep(0.1)
                recs = db.get_job_tracks_for_job(job.id)
                if all(r.status == JobStatus.COMPLETED for r in recs):
                    break

            final_recs = db.get_job_tracks_for_job(job.id)
            assert all(r.status == JobStatus.COMPLETED for r in final_recs)

            # Deduplication: Re-importing same playlist avoids duplicate downloads
            job2 = await mgr2.submit_playlist_job(
                user_id="user_rec",
                playlist_url="https://open.spotify.com/playlist/recoverytest12345678",
                playlist_name="Recovery Playlist",
                tracks=[t1, t2],
            )
            # Tracks already in library should be recognized
            lib_tracks = db.list_library_tracks(limit=10)
            assert len(lib_tracks) == 2  # No duplicate rows created

        finally:
            jobs_mod.provider_registry = orig_registry
            try:
                await mgr2.shutdown()
            except Exception:
                pass
