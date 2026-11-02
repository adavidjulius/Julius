"""Unit tests for Job Manager state transitions and crash recovery."""
import asyncio
import tempfile
from pathlib import Path
import pytest
from src.music.db import MusicDatabase
from src.music.jobs import MusicJobManager
from src.music.models import DownloadRecord, JobStatus, MusicJob, Track


@pytest.mark.asyncio
async def test_job_persistence_and_crash_recovery():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        db_path = str(Path(tmp_dir) / "test_jobs.db")
        db = MusicDatabase(db_path)

        # Create job and job track
        job = MusicJob(
            id="job_recovery_test",
            user_id="user_1",
            playlist_url="https://open.spotify.com/playlist/test",
            playlist_name="Recovery Playlist",
            status=JobStatus.PENDING,
            total_tracks=1
        )
        db.create_job(job)

        rec = DownloadRecord(
            id="rec_interrupted_1",
            job_id="job_recovery_test",
            track_id="sp_test_trk",
            provider="local",
            provider_id="local_1",
            status=JobStatus.DOWNLOADING  # Was interrupted while downloading
        )
        db.create_job_track(rec)

        # Ensure database query detects this interrupted track
        resumable = db.get_resumable_job_tracks()
        assert len(resumable) == 1
        assert resumable[0].id == "rec_interrupted_1"

        # Initialize JobManager on the same database
        job_mgr = MusicJobManager(db=db, max_concurrent=2, temp_dir=tmp_dir)

        # Start job manager (should automatically enqueue the interrupted track)
        await job_mgr.start()
        try:
            assert job_mgr.queue.qsize() == 1
        finally:
            await job_mgr.stop()
