"""
Spotify Metadata Resolver for Julius Music Platform.
Extracts playlist IDs, validates URLs, paginates through full playlists via
Spotify Web API / Spotipy, filters unavailable tracks, and normalizes into Track models.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials, SpotifyOauthError

from src.music.models import Track

logger = logging.getLogger("julius.music.spotify")

SPOTIFY_PLAYLIST_PATTERN = re.compile(
    r"^(?:https?://)?(?:open\.)?spotify\.com/playlist/([a-zA-Z0-9]{22})(?:\?.*)?$"
)
SPOTIFY_ALBUM_PATTERN = re.compile(
    r"^(?:https?://)?(?:open\.)?spotify\.com/album/([a-zA-Z0-9]{22})(?:\?.*)?$"
)
SPOTIFY_TRACK_PATTERN = re.compile(
    r"^(?:https?://)?(?:open\.)?spotify\.com/track/([a-zA-Z0-9]{22})(?:\?.*)?$"
)


class SpotifyResolver:
    """Production-grade Spotify metadata resolver with full pagination & error handling."""

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None
    ) -> None:
        self.client_id = client_id or os.getenv("SPOTIFY_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("SPOTIFY_CLIENT_SECRET")
        self._sp: Optional[spotipy.Spotify] = None
        self._init_client()

    def _init_client(self) -> None:
        if self.client_id and self.client_secret:
            try:
                auth_manager = SpotifyClientCredentials(
                    client_id=self.client_id,
                    client_secret=self.client_secret
                )
                self._sp = spotipy.Spotify(auth_manager=auth_manager)
                logger.info("Spotify client authenticated successfully via ClientCredentials.")
            except Exception as e:
                logger.warning("Failed to authenticate Spotify client credentials: %s", e)
                self._sp = None
        else:
            logger.info("Spotify credentials not provided; operating in standalone/mock fallback mode.")

    @property
    def is_authenticated(self) -> bool:
        return self._sp is not None

    def parse_url(self, url: str) -> Tuple[str, str]:
        """
        Validate and parse Spotify URL.
        Returns (resource_type, resource_id).
        Raises ValueError on malformed URL.
        """
        clean_url = url.strip()
        match_pl = SPOTIFY_PLAYLIST_PATTERN.match(clean_url)
        if match_pl:
            return "playlist", match_pl.group(1)

        match_alb = SPOTIFY_ALBUM_PATTERN.match(clean_url)
        if match_alb:
            return "album", match_alb.group(1)

        match_tr = SPOTIFY_TRACK_PATTERN.match(clean_url)
        if match_tr:
            return "track", match_tr.group(1)

        raise ValueError(
            f"Invalid Spotify URL: '{url}'. Expected format: https://open.spotify.com/playlist/<id>"
        )

    def resolve_playlist(self, url: str) -> Tuple[str, List[Track]]:
        """
        Resolve a Spotify playlist or album URL into its canonical name and normalized tracks.
        Handles full multi-page pagination.
        """
        rtype, rid = self.parse_url(url)
        if rtype not in ("playlist", "album"):
            raise ValueError(f"URL is a {rtype}, expected a Spotify playlist or album URL.")

        if not self._sp:
            logger.info("Spotify client credentials not set or inactive; falling back to Spotify embed resolver.")
            return self._resolve_via_embed(rtype, rid)

        try:
            if rtype == "playlist":
                info = self._sp.playlist(rid, fields="name,tracks.total")
            else:
                info = self._sp.album(rid)
            collection_name = info.get("name", f"Untitled {rtype.title()}")
        except Exception as exc:
            logger.warning("Spotify Web API error (%s); falling back to embed resolver.", exc)
            return self._resolve_via_embed(rtype, rid)

        tracks: List[Track] = []
        seen_ids = set()

        offset = 0
        limit = 50 if rtype == "album" else 100

        while True:
            try:
                if rtype == "playlist":
                    page = self._sp.playlist_items(
                        rid,
                        offset=offset,
                        limit=limit,
                        additional_types=["track"]
                    )
                else:
                    page = self._sp.album_tracks(
                        rid,
                        offset=offset,
                        limit=limit
                    )
            except Exception as exc:
                logger.error("Failed fetching %s page at offset %d: %s", rtype, offset, exc)
                break

            items = page.get("items", [])
            if not items:
                break

            for item in items:
                if rtype == "playlist":
                    track_data = item.get("track")
                else:
                    track_data = item
                    # Inject album info so normalize_track works properly
                    if "album" not in track_data:
                        track_data["album"] = info

                # Filter out unavailable, local, or deleted tracks
                if not track_data or track_data.get("is_local") or not track_data.get("id"):
                    continue

                sp_id = track_data["id"]
                if sp_id in seen_ids:
                    continue
                seen_ids.add(sp_id)

                norm_track = self._normalize_track(track_data)
                tracks.append(norm_track)

            offset += len(items)
            total = page.get("total", 0)
            if offset >= total or not page.get("next"):
                break

        logger.info("Resolved %d tracks from %s '%s' (id=%s)", len(tracks), rtype, collection_name, rid)
        return collection_name, tracks

    def _normalize_track(self, item: Dict[str, Any]) -> Track:
        """Normalize raw Spotify track dictionary into canonical Track domain model."""
        artists = [a.get("name", "Unknown Artist") for a in item.get("artists", [])]
        if not artists:
            artists = ["Unknown Artist"]

        album_data = item.get("album", {})
        album_name = album_data.get("name", "Unknown Album")

        album_artists = [a.get("name") for a in album_data.get("artists", []) if a.get("name")]
        album_artist = album_artists[0] if album_artists else artists[0]

        artwork_url = ""
        images = album_data.get("images", [])
        if images:
            # Pick highest resolution image
            artwork_url = images[0].get("url", "")

        external_ids = item.get("external_ids", {})
        isrc = external_ids.get("isrc")

        release_date = album_data.get("release_date", "")

        source_url = item.get("external_urls", {}).get("spotify", f"https://open.spotify.com/track/{item.get('id')}")

        return Track(
            spotify_id=item.get("id", ""),
            title=item.get("name", "Untitled"),
            artists=artists,
            album=album_name,
            album_artist=album_artist,
            isrc=isrc,
            duration_ms=item.get("duration_ms", 0),
            disc_number=item.get("disc_number", 1),
            track_number=item.get("track_number", 1),
            release_date=release_date,
            explicit=item.get("explicit", False),
            artwork_url=artwork_url,
            source_url=source_url,
        )

    def _resolve_via_embed(self, rtype: str, rid: str) -> Tuple[str, List[Track]]:
        """Fallback resolver extracting full tracklist from Spotify public embed markup."""
        import json
        import urllib.request
        url = f"https://open.spotify.com/embed/{rtype}/{rid}"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                html = resp.read().decode("utf-8")
        except Exception as exc:
            logger.error("Failed opening embed URL for %s: %s", rid, exc)
            raise RuntimeError(f"Failed to fetch public Spotify {rtype}: {exc}")

        match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html)
        if not match:
            raise RuntimeError(f"Could not parse Spotify embed metadata for {rtype} {rid}")

        try:
            data = json.loads(match.group(1))
            entity = data.get("props", {}).get("pageProps", {}).get("state", {}).get("data", {}).get("entity", {})
            collection_name = entity.get("title", f"Untitled {rtype.title()}")
            track_list = entity.get("trackList", [])
        except Exception as exc:
            logger.error("Failed parsing embed JSON: %s", exc)
            raise RuntimeError(f"Malformed Spotify embed data: {exc}")

        artwork_url = ""
        images = entity.get("visualIdentity", {}).get("image", [])
        if images:
            sorted_imgs = sorted(images, key=lambda x: x.get("maxHeight", 0), reverse=True)
            artwork_url = sorted_imgs[0].get("url", "")

        tracks: List[Track] = []
        for i, item in enumerate(track_list):
            uri = item.get("uri", "")
            sp_id = uri.split(":")[-1] if uri.startswith("spotify:track:") else f"tr_{rid}_{i}"
            artists_str = item.get("subtitle", "Unknown Artist")
            # Parse artist names
            artists = [a.strip() for a in re.split(r"[,&]", artists_str) if a.strip()] or [artists_str]
            tracks.append(Track(
                spotify_id=sp_id,
                title=item.get("title", "Untitled Track"),
                artists=artists,
                album=collection_name,
                album_artist=artists[0] if artists else "Unknown Artist",
                duration_ms=int(item.get("duration", 0)),
                track_number=i + 1,
                artwork_url=artwork_url,
                source_url=f"https://open.spotify.com/track/{sp_id}"
            ))


        logger.info("Resolved %d tracks via embed scraper for %s '%s' (id=%s)", len(tracks), rtype, collection_name, rid)
        return collection_name, tracks


# Global singleton resolver
spotify_resolver = SpotifyResolver()
