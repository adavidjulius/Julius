"""Unit tests for Lossless Quality Engine."""
from src.music.models import ProviderCandidate
from src.music.quality import QualityEngine


def test_quality_ranking_order():
    engine = QualityEngine(policy="flac_only")

    # High res 24/192
    cand_hires = ProviderCandidate(
        provider="spotiflac",
        provider_id="hires",
        title="Song",
        artists=["Artist"],
        album="Album",
        format="FLAC",
        codec="flac",
        sample_rate=192000,
        bit_depth=24,
        score=95.0
    )

    # Standard lossless 16/44.1
    cand_std = ProviderCandidate(
        provider="spotiflac",
        provider_id="std",
        title="Song",
        artists=["Artist"],
        album="Album",
        format="FLAC",
        codec="flac",
        sample_rate=44100,
        bit_depth=16,
        score=95.0
    )

    ranked = engine.rank_candidates([cand_std, cand_hires])
    assert len(ranked) == 2
    assert ranked[0].bit_depth == 24
    assert ranked[0].sample_rate == 192000


def test_identity_priority_over_raw_resolution():
    """Exact recording match must always beat wrong recording even if wrong recording is 24/192."""
    engine = QualityEngine()

    # Ambiguous/wrong recording with high resolution
    cand_wrong_hires = ProviderCandidate(
        provider="spotiflac",
        provider_id="hires_wrong",
        title="Song (Wrong Version)",
        artists=["Artist"],
        album="Album",
        format="FLAC",
        codec="flac",
        sample_rate=192000,
        bit_depth=24,
        score=55.0  # low match score
    )

    # Exact recording match with standard lossless
    cand_exact_std = ProviderCandidate(
        provider="spotiflac",
        provider_id="std_exact",
        title="Song",
        artists=["Artist"],
        album="Album",
        format="FLAC",
        codec="flac",
        sample_rate=44100,
        bit_depth=16,
        score=95.0  # high match score
    )

    best = engine.select_best([cand_wrong_hires, cand_exact_std])
    assert best is not None
    assert best.provider_id == "std_exact", f"Exact recording should win over wrong recording, got {best.provider_id}"
