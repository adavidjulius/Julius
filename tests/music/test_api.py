"""Unit tests for Julius Music API routes and response envelopes."""
import pytest
from aiohttp import web
from src.music.api import setup_music_routes, make_response
from src.music.diagnostics import music_diagnostics


@pytest.mark.asyncio
async def test_make_response_envelope():
    resp = make_response(data={"item": 123}, status=200)
    assert resp.status == 200
    assert resp.content_type == "application/json"


@pytest.mark.asyncio
async def test_diagnostics_report_structure():
    report = music_diagnostics.get_status_report()
    assert "status" in report
    assert "database" in report
    assert "spotify" in report
    assert "providers" in report
    assert "storage" in report
    assert "jobs" in report
    assert "library" in report
    assert report["database"]["engine"] == "sqlite-wal"


@pytest.mark.asyncio
async def test_track_detail_and_artwork_endpoints():
    from unittest.mock import AsyncMock, patch
    from aiohttp.test_utils import TestClient, TestServer
    from src.music.api import audio_streamer, music_library

    app = web.Application()
    setup_music_routes(app)
    client = TestClient(TestServer(app))
    await client.start_server()

    try:
        # 1. Non-existent track returns 404
        resp = await client.get("/api/music/tracks/nonexistent_id")
        assert resp.status == 404
        body = await resp.json()
        assert body["success"] is False

        # 2. Artwork returns image bytes with caching headers
        with patch.object(audio_streamer, "get_track_artwork", new_callable=AsyncMock) as mock_art:
            mock_art.return_value = (b"\xff\xd8\xff\xe0dummyjpegdata", "image/jpeg", None)
            art_resp = await client.get("/api/music/tracks/test_id/artwork")
            assert art_resp.status == 200
            assert art_resp.content_type == "image/jpeg"
            assert "max-age=86400" in art_resp.headers.get("Cache-Control", "")
            data = await art_resp.read()
            assert data.startswith(b"\xff\xd8")

        # 3. Artwork with redirect returns 302
        with patch.object(audio_streamer, "get_track_artwork", new_callable=AsyncMock) as mock_art:
            mock_art.return_value = (None, None, "https://cdn.example.com/cover.jpg")
            redirect_resp = await client.get("/api/music/tracks/test_id/artwork", allow_redirects=False)
            assert redirect_resp.status == 302
            assert redirect_resp.headers["Location"] == "https://cdn.example.com/cover.jpg"
    finally:
        await client.close()


