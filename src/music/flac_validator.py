"""
FLAC Binary Stream Validator for Julius.
Inspects raw binary headers (fLaC marker), parses the STREAMINFO block directly
according to the FLAC standard, extracts verified hardware properties (sample rate,
bit depth, channels, duration, MD5 audio signature), and computes file SHA-256.
Rejects spoofed, truncated, or corrupt files.
"""

from __future__ import annotations

import hashlib
import logging
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger("julius.music.flac_validator")

FLAC_MAGIC = b"fLaC"


class FlacValidationError(Exception):
    """Raised when audio stream fails lossless FLAC format validation."""
    pass


@dataclass
class FlacProperties:
    """Verified technical properties extracted directly from the FLAC binary stream."""
    codec: str
    sample_rate: int
    bit_depth: int
    channels: int
    total_samples: int
    duration_seconds: float
    md5_signature: str
    checksum_sha256: str
    file_size_bytes: int


class FlacValidator:
    """Rigorous binary inspector for Free Lossless Audio Codec (FLAC) streams."""

    def validate_file(self, file_path: str) -> FlacProperties:
        """
        Open and inspect the FLAC file.
        Throws FlacValidationError if corrupt, mislabeled, or invalid.
        """
        path = Path(file_path).expanduser().resolve()
        if not path.exists():
            raise FlacValidationError(f"Audio file does not exist: '{file_path}'")

        file_size = path.stat().st_size
        if file_size < 42:  # 4 bytes magic + 4 bytes header + 34 bytes STREAMINFO
            raise FlacValidationError(f"File size ({file_size} bytes) is too small to be a valid FLAC stream.")

        # Compute SHA-256 checksum
        sha256 = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(65536):
                sha256.update(chunk)
        file_hash = sha256.hexdigest()

        # Parse FLAC headers
        with open(path, "rb") as f:
            magic = f.read(4)
            if magic != FLAC_MAGIC:
                raise FlacValidationError(
                    f"Invalid FLAC magic header: expected b'fLaC', found {magic!r}. File is not a valid FLAC container."
                )

            # Read first metadata block header
            header_bytes = f.read(4)
            if len(header_bytes) < 4:
                raise FlacValidationError("Unexpected EOF while reading FLAC metadata block header.")

            # Bit 0: is_last, Bits 1-7: block_type, Bytes 1-3: length (24 bits)
            first_byte = header_bytes[0]
            block_type = first_byte & 0x7F
            block_length = (header_bytes[1] << 16) | (header_bytes[2] << 8) | header_bytes[3]

            if block_type != 0:
                raise FlacValidationError(
                    f"First FLAC metadata block must be STREAMINFO (type 0), got type {block_type}."
                )

            if block_length < 34:
                raise FlacValidationError(
                    f"STREAMINFO block length must be at least 34 bytes, got {block_length}."
                )

            streaminfo_bytes = f.read(34)
            if len(streaminfo_bytes) < 34:
                raise FlacValidationError("Truncated STREAMINFO block in FLAC header.")

        # Decode STREAMINFO:
        # 0..1: min blocksize (uint16)
        # 2..3: max blocksize (uint16)
        # 4..6: min framesize (24 bits)
        # 7..9: max framesize (24 bits)
        # 10..17: 8 bytes packed:
        #   - 20 bits: sample rate (Hz)
        #   - 3 bits: channels - 1
        #   - 5 bits: bits per sample - 1
        #   - 36 bits: total inter-channel samples in stream
        # 18..33: 16 bytes MD5 signature
        packed_audio = struct.unpack(">Q", streaminfo_bytes[10:18])[0]
        sample_rate = (packed_audio >> 44) & 0xFFFFF
        channels = ((packed_audio >> 41) & 0x07) + 1
        bit_depth = ((packed_audio >> 36) & 0x1F) + 1
        total_samples = packed_audio & 0xFFFFFFFFF

        md5_bytes = streaminfo_bytes[18:34]
        md5_sig = md5_bytes.hex()

        # Sanity checks on parsed values
        if sample_rate < 8000 or sample_rate > 384000:
            raise FlacValidationError(f"Invalid FLAC sample rate: {sample_rate} Hz")

        if bit_depth not in (16, 24, 32):
            raise FlacValidationError(f"Unsupported or invalid FLAC bit depth: {bit_depth}-bit")

        if channels < 1 or channels > 8:
            raise FlacValidationError(f"Invalid FLAC channel count: {channels}")

        duration_sec = total_samples / float(sample_rate) if sample_rate > 0 else 0.0

        logger.info(
            "FLAC verified: %s [%d-bit / %.1f kHz, %d ch, %.2fs, sha256=%s]",
            path.name, bit_depth, sample_rate / 1000.0, channels, duration_sec, file_hash[:8]
        )

        return FlacProperties(
            codec="flac",
            sample_rate=sample_rate,
            bit_depth=bit_depth,
            channels=channels,
            total_samples=total_samples,
            duration_seconds=duration_sec,
            md5_signature=md5_sig,
            checksum_sha256=file_hash,
            file_size_bytes=file_size,
        )


# Global validator instance
flac_validator = FlacValidator()
