"""Unit tests for FLAC Binary Stream Validator."""
import struct
import tempfile
from pathlib import Path
import pytest
from src.music.flac_validator import FlacValidator, FlacValidationError


def create_mock_flac_bytes(sample_rate: int = 44100, bit_depth: int = 16, channels: int = 2, total_samples: int = 441000) -> bytes:
    """Synthesize a valid minimal FLAC header and STREAMINFO metadata block."""
    magic = b"fLaC"
    # Block type 0 (STREAMINFO), length 34
    block_header = bytes([0x00, 0x00, 0x00, 34])

    min_blocksize = 4096
    max_blocksize = 4096
    min_framesize = 0
    max_framesize = 0

    # 10..17: 8 bytes packed
    # sample_rate (20 bits) | channels-1 (3 bits) | bit_depth-1 (5 bits) | total_samples (36 bits)
    packed = (sample_rate & 0xFFFFF) << 44
    packed |= ((channels - 1) & 0x07) << 41
    packed |= ((bit_depth - 1) & 0x1F) << 36
    packed |= (total_samples & 0xFFFFFFFFF)

    streaminfo = (
        struct.pack(">H", min_blocksize) +
        struct.pack(">H", max_blocksize) +
        bytes([0, 0, 0]) +  # 24 bits min frame
        bytes([0, 0, 0]) +  # 24 bits max frame
        struct.pack(">Q", packed) +
        b"\x00" * 16        # 16 bytes MD5
    )

    # Some mock audio payload
    payload = b"\x00" * 1024
    return magic + block_header + streaminfo + payload


def test_flac_validation_valid():
    validator = FlacValidator()

    with tempfile.NamedTemporaryFile(suffix=".flac", delete=False) as f:
        f.write(create_mock_flac_bytes(sample_rate=96000, bit_depth=24, channels=2, total_samples=960000))
        temp_path = f.name

    try:
        props = validator.validate_file(temp_path)
        assert props.codec == "flac"
        assert props.sample_rate == 96000
        assert props.bit_depth == 24
        assert props.channels == 2
        assert abs(props.duration_seconds - 10.0) < 0.01
        assert len(props.checksum_sha256) == 64
    finally:
        Path(temp_path).unlink()


def test_flac_validation_rejects_corrupt_file():
    validator = FlacValidator()

    # Mislabeled file (MP3/garbage disguised as FLAC)
    with tempfile.NamedTemporaryFile(suffix=".flac", delete=False) as f:
        f.write(b"ID3" + b"\x00" * 500)
        temp_path = f.name

    try:
        with pytest.raises(FlacValidationError):
            validator.validate_file(temp_path)
    finally:
        Path(temp_path).unlink()
