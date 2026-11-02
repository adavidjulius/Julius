"""End-to-end integration test verifying the full lossless audio pipeline."""
import asyncio
import tempfile
from pathlib import Path
import pytest

from unittest.mock import AsyncMock, patch

from src.music.db import MusicDatabase
from src.music.jobs import MusicJobManager
from src.music.models import JobStatus, ProviderCandidate, Track
from src.music.providers.base import MusicProvider
from src.music.providers.registry import ProviderRegistry
from tests.music.test_flac_validator import create_mock_flac_bytes


class MockTestProvider:
    def __init__(self, flac_file_path: str):
        self.flac_file_path = flac_file_path

    @property
    def name(self) -> str:
        return "mock_provider"

    @property
    def is_available(self) -> bool:
        return True

    async def search(self, track: Track):
        return await self.get_candidates(track)

    async def get_candidates(self, track: Track):
        return [
            ProviderCandidate(
                provider=self.name,
                provider_id="mock_track_01",
                title=track.title,
                artists=track.artists,
                album=track.album,
                album_artist=track.album_artist,
                isrc=track.isrc,
                duration_ms=track.duration_ms,
                format="FLAC",
                codec="flac",
                sample_rate=96000,
                bit_depth=24,
                channels=2,
                availability=True,
                score=95.0,
                download_url=self.flac_file_path
            )
        ]

    async def get_metadata(self, candidate):
        return {"format": "FLAC"}

    async def download(self, candidate, destination_dir):
        import shutil
        dest = Path(destination_dir) / "downloaded.flac"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self.flac_file_path, dest)
        return str(dest)


@pytest.mark.asyncio
async def test_end_to_end_music_pipeline():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        # 1. Setup temporary FLAC file
        test_flac_bytes = create_mock_flac_bytes(sample_rate=96000, bit_depth=24, channels=2, total_samples=960000)
        source_flac = Path(tmp_dir) / "source.flac"
        with open(source_flac, "wb") as f:
            f.write(test_flac_bytes)

        # 2. Setup isolated DB and Job Manager
        db_path = str(Path(tmp_dir) / "pipeline_test.db")
        db = MusicDatabase(db_path)

        job_mgr = MusicJobManager(db=db, max_concurrent=1, temp_dir=tmp_dir)

        # Register mock provider
        custom_registry = ProviderRegistry()
        mock_p = MockTestProvider(str(source_flac))
        custom_registry._providers.clear()
        custom_registry.register(mock_p)

        # Patch the global provider_registry in jobs module for this test
        import src.music.jobs as jobs_mod
        orig_registry = jobs_mod.provider_registry
        jobs_mod.provider_registry = custom_registry

        try:
            await job_mgr.start()

            with patch.object(job_mgr.gdrive_storage, "upload", new_callable=AsyncMock) as mock_upload:
                mock_upload.return_value = "mock_drive_file_id_e2e"

                # 3. Create track and submit playlist job
                test_track = Track(
                    spotify_id="e2e_sp_01",
                    title="Clair de Lune",
                    artists=["Claude Debussy"],
                    album="Suite Bergamasque",
                    album_artist="Claude Debussy",
                    duration_ms=10000,
                    track_number=3
                )

                job = await job_mgr.submit_playlist_job(
                    user_id="user_admin",
                    playlist_url="https://open.spotify.com/playlist/test_e2e_playlist",
                    playlist_name="Classical Favorites",
                    tracks=[test_track]
                )

                assert job.total_tracks == 1

                # Wait for background queue processing
                for _ in range(60):
                    await asyncio.sleep(0.1)
                    rec = db.get_job_tracks_for_job(job.id)[0]
                    if rec.status in (JobStatus.COMPLETED, JobStatus.FAILED):
                        break


            final_rec = db.get_job_tracks_for_job(job.id)[0]
            assert final_rec.status == JobStatus.COMPLETED, f"Pipeline failed with error: {final_rec.error}"

            # Verify track in indexed library
            indexed_track = db.get_library_track("e2e_sp_01")
            assert indexed_track is not None
            assert indexed_track.title == "Clair de Lune"
            assert indexed_track.codec == "flac"
            assert indexed_track.bit_depth == 24
            assert indexed_track.sample_rate == 96000
            assert "24-bit / 96 kHz FLAC" in indexed_track.quality_badge
            assert Path(indexed_track.local_path).exists()

        finally:
            jobs_mod.provider_registry = orig_registry
            await job_mgr.stop()
