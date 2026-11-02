"""Unit tests for Storage Path Builders and Deduplication."""
import tempfile
from pathlib import Path
import pytest
from src.music.models import Track, LibraryTrack
from src.music.storage.base import build_track_storage_path, sanitize_path_segment
from src.music.storage.local import LocalStorageBackend
from src.music.db import MusicDatabase


def test_sanitize_path_segment():
    assert sanitize_path_segment("AC/DC") == "AC_DC"
    assert sanitize_path_segment("Song: Special Edition?") == "Song_ Special Edition_"
    assert sanitize_path_segment("   Leading/Trailing   ") == "Leading_Trailing"
    assert sanitize_path_segment("") == "Unknown"


def test_build_track_storage_path():
    track = Track(
        spotify_id="123",
        title="Money",
        artists=["Pink Floyd"],
        album="The Dark Side of the Moon",
        album_artist="Pink Floyd",
        track_number=6
    )
    # Default legacy path with artist
    path = build_track_storage_path(track)
    assert path == "Song/Pink Floyd/The Dark Side of the Moon/06 - Money.flac"

    # Direct playlist path (no artist subfolder)
    playlist_path = build_track_storage_path(track, root_folder="Julius Songs", playlist_name="Classic Rock Hits")
    assert playlist_path == "Julius Songs/Classic Rock Hits/06 - Money.flac"

    # Direct album path (include_artist_folder=False)
    direct_album_path = build_track_storage_path(track, root_folder="Julius Songs", include_artist_folder=False)
    assert direct_album_path == "Julius Songs/The Dark Side of the Moon/06 - Money.flac"


@pytest.mark.asyncio
async def test_local_storage_upload_and_range_read():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_root:
        storage = LocalStorageBackend(root_dir=tmp_root)

        # Create dummy audio file
        with tempfile.NamedTemporaryFile(delete=False) as src_f:
            src_f.write(b"0123456789ABCDEF" * 100)
            src_path = src_f.name

        try:
            rel_path = "Song/Test/Album/01 - Test.flac"
            stored_path = await storage.upload(src_path, rel_path)
            assert await storage.exists(rel_path)

            # Read range: bytes 0-9
            data = await storage.read_range(stored_path, 0, 9)
            assert data == b"0123456789"
        finally:
            Path(src_path).unlink()


def test_database_deduplication():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        db_path = str(Path(tmp_dir) / "test_music.db")
        db = MusicDatabase(db_path)

        track = LibraryTrack(
            id="trk_1",
            isrc="USABC1234567",
            title="Bohemian Rhapsody",
            artists=["Queen"],
            album="A Night at the Opera",
            album_artist="Queen",
            duration_ms=354000,
            disc_number=1,
            track_number=11,
            release_date="1975-10-31",
            artwork_url="",
            source_url="",
            drive_file_id="drive_file_abc",
            local_path="/path/to/file.flac",
            checksum="hash_queen_123",
            codec="flac",
            sample_rate=96000,
            bit_depth=24,
            channels=2,
            file_size_bytes=45000000,
            created_at=1000.0,
            updated_at=1000.0
        )
        db.upsert_library_track(track)

        # Deduplication lookup by ISRC
        found = db.find_existing_track(isrc="USABC1234567")
        assert found is not None
        assert found.id == "trk_1"

        # Deduplication lookup by Title and Artist
        found2 = db.find_existing_track(title="Bohemian Rhapsody", artist="Queen")
        assert found2 is not None
        assert found2.checksum == "hash_queen_123"
