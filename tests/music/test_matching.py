"""Unit tests for Hierarchical Track Matching Engine."""
from src.music.matching import MatchEngine
from src.music.models import ProviderCandidate, Track


def test_exact_match_high_score():
    engine = MatchEngine(match_threshold=80.0)

    track = Track(
        spotify_id="sp_1",
        title="Hotel California",
        artists=["Eagles"],
        album="Hotel California",
        album_artist="Eagles",
        isrc="USPR37600001",
        duration_ms=391000
    )

    candidate = ProviderCandidate(
        provider="spotiflac",
        provider_id="cand_1",
        title="Hotel California",
        artists=["Eagles"],
        album="Hotel California",
        album_artist="Eagles",
        isrc="USPR37600001",
        duration_ms=391200,
        sample_rate=192000,
        bit_depth=24
    )

    score = engine.calculate_score(track, candidate)
    assert score >= 90.0, f"Expected high score for exact match, got {score}"


def test_remix_and_live_variant_rejection():
    engine = MatchEngine(match_threshold=80.0)

    track = Track(
        spotify_id="sp_2",
        title="Blinding Lights",
        artists=["The Weeknd"],
        album="After Hours",
        isrc="USUG11904206",
        duration_ms=200000
    )

    # Incompatible remix candidate
    remix_cand = ProviderCandidate(
        provider="spotiflac",
        provider_id="cand_remix",
        title="Blinding Lights (Major Lazer Remix)",
        artists=["The Weeknd", "Major Lazer"],
        album="After Hours (Remixes)",
        duration_ms=195000
    )

    # Incompatible live candidate
    live_cand = ProviderCandidate(
        provider="spotiflac",
        provider_id="cand_live",
        title="Blinding Lights - Live at SoFi Stadium",
        artists=["The Weeknd"],
        album="Live at SoFi Stadium",
        duration_ms=215000
    )

    score_remix = engine.calculate_score(track, remix_cand)
    score_live = engine.calculate_score(track, live_cand)

    assert score_remix == 0.0, f"Remix should be rejected for non-remix track, got {score_remix}"
    assert score_live == 0.0, f"Live recording should be rejected for studio track, got {score_live}"


def test_duration_proximity_penalty():
    engine = MatchEngine(match_threshold=80.0)

    track = Track(
        spotify_id="sp_3",
        title="Song A",
        artists=["Artist B"],
        album="Album C",
        duration_ms=180000  # 3 minutes
    )

    # Completely different duration (+60 seconds)
    wrong_cand = ProviderCandidate(
        provider="local",
        provider_id="cand_wrong",
        title="Song A",
        artists=["Artist B"],
        album="Album C",
        duration_ms=240000  # 4 minutes
    )

    score = engine.calculate_score(track, wrong_cand)
    assert score < 80.0, f"Major duration discrepancy should prevent match pass, got {score}"
