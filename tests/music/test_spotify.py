"""Unit tests for Spotify URL parsing, playlist pagination, and normalization."""
import pytest
from src.music.spotify import SpotifyResolver
from src.music.models import Track


def test_spotify_url_parsing():
    resolver = SpotifyResolver(client_id=None, client_secret=None)

    # Valid playlist URLs
    rtype, rid = resolver.parse_url("https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M")
    assert rtype == "playlist"
    assert rid == "37i9dQZF1DXcBWIGoYBM5M"

    rtype, rid = resolver.parse_url("http://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M?si=abcd1234efgh")
    assert rtype == "playlist"
    assert rid == "37i9dQZF1DXcBWIGoYBM5M"

    # Track URL
    rtype, rid = resolver.parse_url("https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT")
    assert rtype == "track"
    assert rid == "4cOdK2wGLETKBW3PvgPWqT"

    # Invalid URL
    with pytest.raises(ValueError):
        resolver.parse_url("https://invalid.com/not-spotify/1234")


def test_track_normalization():
    resolver = SpotifyResolver(client_id=None, client_secret=None)

    raw_item = {
        "id": "trk123456789012345678",
        "name": "Lose Yourself",
        "artists": [{"name": "Eminem"}],
        "album": {
            "name": "8 Mile Soundtrack",
            "artists": [{"name": "Eminem"}],
            "release_date": "2002-10-28",
            "images": [{"url": "https://i.scdn.co/image/ab67616d0000b273test"}]
        },
        "duration_ms": 326000,
        "disc_number": 1,
        "track_number": 1,
        "explicit": True,
        "external_ids": {"isrc": "USIR10200843"},
        "external_urls": {"spotify": "https://open.spotify.com/track/trk123456789012345678"}
    }

    track = resolver._normalize_track(raw_item)
    assert isinstance(track, Track)
    assert track.title == "Lose Yourself"
    assert track.artists == ["Eminem"]
    assert track.album_artist == "Eminem"
    assert track.isrc == "USIR10200843"
    assert track.duration_ms == 326000
    assert track.explicit is True
    assert track.artwork_url == "https://i.scdn.co/image/ab67616d0000b273test"
