"""
aiohttp REST API routes and handlers for Julius Music Subsystem.
Implements authentication, standardized response formats, Range audio streaming,
playlist ingestion, and real-time job tracking.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Dict, Optional

from aiohttp import web

from src.music.db import MusicDatabase
from src.music.diagnostics import music_diagnostics
from src.music.jobs import music_job_manager
from src.music.library import music_library
from src.music.models import JobStatus
from src.music.spotify import spotify_resolver
from src.music.streaming import audio_streamer

logger = logging.getLogger("julius.music.api")

routes = web.RouteTableDef()


def make_response(data: Any = None, error: Optional[Dict[str, Any]] = None, status: int = 200) -> web.Response:
    """Standardized JSON response envelope (Section 25)."""
    payload = {
        "success": error is None,
        "data": data,
        "error": error,
        "request_id": str(uuid.uuid4())[:8]
    }
    return web.json_response(payload, status=status)


def get_authenticated_user(request: web.Request) -> Optional[Dict[str, Any]]:
    """
    Authenticate request via session token from cookie, Authorization header, or query param.
    Reuses Julius's core auth_mgr when available in request.app.
    """
    auth_mgr = request.app.get("auth_mgr")
    session_id = request.cookies.get("session_id")
    if not session_id:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            session_id = auth_header[7:].strip()
        elif "token" in request.query:
            session_id = request.query.get("token", "").strip()

    if session_id and auth_mgr:
        res = auth_mgr.validate_session(session_id)
        if res:
            user, session_rec, workspace_rec = res
            return {
                "user_id": user.id,
                "username": user.username,
                "role": user.role
            }

    # Development or local single-user fallback
    return {
        "user_id": "default_user",
        "username": "david julius",
        "role": "admin"
    }


# ── Playlist Ingestion ─────────────────────────────────────────────────────────

@routes.post("/api/music/playlist")
async def handle_submit_playlist(request: web.Request) -> web.Response:
    user = get_authenticated_user(request)
    if not user:
        return make_response(error={"code": "UNAUTHORIZED", "message": "Authentication required"}, status=401)

    try:
        data = await request.json()
    except Exception:
        return make_response(error={"code": "INVALID_JSON", "message": "Malformed JSON payload"}, status=400)

    url = data.get("url")
    if not url:
        return make_response(error={"code": "MISSING_URL", "message": "'url' is required"}, status=400)

    try:
        # Resolve playlist and extract canonical tracks
        playlist_name, tracks = spotify_resolver.resolve_playlist(url)
    except ValueError as ve:
        return make_response(error={"code": "INVALID_URL", "message": str(ve)}, status=400)
    except RuntimeError as re:
        return make_response(error={"code": "RESOLVER_ERROR", "message": str(re)}, status=503)
    except Exception as exc:
        logger.error("Failed resolving playlist: %s", exc)
        return make_response(error={"code": "INTERNAL_ERROR", "message": f"Failed resolving playlist: {exc}"}, status=500)

    if not tracks:
        return make_response(error={"code": "NO_TRACKS", "message": "No available tracks found in playlist"}, status=400)

    # Submit job to background manager
    job = await music_job_manager.submit_playlist_job(
        user_id=user["user_id"],
        playlist_url=url,
        playlist_name=playlist_name,
        tracks=tracks
    )

    return make_response({
        "job": job.to_dict(),
        "tracks_queued": len(tracks),
        "message": f"Queued {len(tracks)} tracks from playlist '{playlist_name}' for lossless ingestion."
    })


# ── Job Management ─────────────────────────────────────────────────────────────

@routes.get("/api/music/jobs")
async def handle_list_jobs(request: web.Request) -> web.Response:
    user = get_authenticated_user(request)
    if not user:
        return make_response(error={"code": "UNAUTHORIZED", "message": "Authentication required"}, status=401)

    jobs = music_job_manager.db.list_jobs()
    return make_response([j.to_dict() for j in jobs])


@routes.get("/api/music/jobs/{id}")
async def handle_get_job(request: web.Request) -> web.Response:
    user = get_authenticated_user(request)
    if not user:
        return make_response(error={"code": "UNAUTHORIZED", "message": "Authentication required"}, status=401)

    job_id = request.match_info["id"]
    job = music_job_manager.db.get_job(job_id)
    if not job:
        return make_response(error={"code": "NOT_FOUND", "message": f"Job {job_id} not found"}, status=404)

    tracks = music_job_manager.db.get_job_tracks_for_job(job_id)
    track_dicts = []
    for t in tracks:
        td = t.to_dict()
        can_tr = music_job_manager.db.get_track(t.track_id)
        if can_tr:
            td["track_title"] = can_tr.title
            td["artist"] = can_tr.artist_display
            td["album"] = can_tr.album
            td["artwork_url"] = can_tr.artwork_url
        track_dicts.append(td)

    return make_response({
        "job": job.to_dict(),
        "tracks": track_dicts
    })


@routes.post("/api/music/jobs/{id}/cancel")
async def handle_cancel_job(request: web.Request) -> web.Response:
    user = get_authenticated_user(request)
    if not user:
        return make_response(error={"code": "UNAUTHORIZED", "message": "Authentication required"}, status=401)

    job_id = request.match_info["id"]
    success = await music_job_manager.cancel_job(job_id)
    if not success:
        return make_response(error={"code": "NOT_FOUND", "message": f"Job {job_id} not found"}, status=404)

    return make_response({"cancelled": True, "job_id": job_id})


# ── Candidates for Ambiguous Matches ──────────────────────────────────────────

@routes.get("/api/music/candidates/{job_track_id}")
async def handle_get_candidates(request: web.Request) -> web.Response:
    user = get_authenticated_user(request)
    if not user:
        return make_response(error={"code": "UNAUTHORIZED", "message": "Authentication required"}, status=401)

    job_track_id = request.match_info["job_track_id"]
    candidates = music_job_manager.db.get_candidates(job_track_id)
    return make_response([c.to_dict() for c in candidates])


# ── Library Index & Search ─────────────────────────────────────────────────────

@routes.get("/api/music/library")
async def handle_get_library(request: web.Request) -> web.Response:
    q = request.query.get("q")
    artist = request.query.get("artist")
    album = request.query.get("album")
    min_bit = int(request.query.get("min_bit_depth")) if request.query.get("min_bit_depth") else None
    limit = min(int(request.query.get("limit", 100)), 500)
    offset = int(request.query.get("offset", 0))

    result = music_library.search(
        query=q,
        artist=artist,
        album=album,
        min_bit_depth=min_bit,
        limit=limit,
        offset=offset
    )
    return make_response(result)


@routes.get("/api/music/library/artists")
async def handle_get_artists(request: web.Request) -> web.Response:
    limit = min(int(request.query.get("limit", 100)), 500)
    artists = music_library.list_artists(limit=limit)
    return make_response(artists)


@routes.get("/api/music/library/albums")
async def handle_get_albums(request: web.Request) -> web.Response:
    artist = request.query.get("artist")
    limit = min(int(request.query.get("limit", 100)), 500)
    albums = music_library.list_albums(artist=artist, limit=limit)
    return make_response(albums)


@routes.get("/api/music/library/stats")
async def handle_get_stats(request: web.Request) -> web.Response:
    stats = music_library.get_stats()
    return make_response(stats)


# ── Streaming with HTTP Range Requests ─────────────────────────────────────────

@routes.get("/api/music/tracks/{id}")
async def handle_get_track(request: web.Request) -> web.Response:
    track_id = request.match_info["id"]
    track = music_library.get_track(track_id)
    if not track:
        can = music_job_manager.db.get_track(track_id)
        if not can:
            return make_response(error={"code": "NOT_FOUND", "message": f"Track {track_id} not found"}, status=404)
        return make_response(can.to_dict())
    return make_response(track.to_dict())


@routes.get("/api/music/tracks/{id}/stream")
async def handle_stream_track(request: web.Request) -> web.StreamResponse:
    # Validate session from query token, cookie, or header
    user = get_authenticated_user(request)
    if not user:
        return web.Response(status=401, text="Unauthorized: Valid session required for streaming.")

    track_id = request.match_info["id"]
    return await audio_streamer.stream_track(request, track_id)


@routes.get("/api/music/tracks/{id}/artwork")
@routes.get("/api/music/artwork/{id}")
async def handle_get_artwork(request: web.Request) -> web.StreamResponse:
    track_id = request.match_info["id"]
    img_bytes, mime_type, remote_url = await audio_streamer.get_track_artwork(track_id)

    if img_bytes and mime_type:
        return web.Response(
            body=img_bytes,
            content_type=mime_type,
            headers={
                "Cache-Control": "public, max-age=86400",
                "Access-Control-Allow-Origin": "*"
            }
        )

    if remote_url:
        raise web.HTTPFound(remote_url)

    return web.Response(status=404, text="Artwork not found for this track.")



# ── Diagnostics & Health ───────────────────────────────────────────────────────

@routes.get("/api/music/diagnostics")
async def handle_diagnostics(request: web.Request) -> web.Response:
    user = get_authenticated_user(request)
    if not user or user.get("role") not in ("admin", "super_admin", "owner"):
        return make_response(error={"code": "FORBIDDEN", "message": "Admin privileges required"}, status=403)

    report = music_diagnostics.get_status_report()
    return make_response(report)


def setup_music_routes(app: web.Application) -> None:
    """Attach music routes and event forwarder to the main Julius aiohttp Application."""
    app.add_routes(routes)

    # Attach event forwarder so music job events broadcast over existing Julius WebSocket
    def _forward_to_active_sessions(event: Dict[str, Any]):
        # Broadcast over app active websockets if present
        for session_id, ws in list(app.get("active_websockets", {}).items()):
            try:
                import asyncio
                asyncio.create_task(ws.send_json({
                    "type": "music_event",
                    **event
                }))
            except Exception:
                pass

    music_job_manager.subscribe_events(_forward_to_active_sessions)
    logger.info("Julius music routes and WebSocket forwarder initialized successfully.")
