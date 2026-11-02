"""
FLAC Stream Validator Service for Julius.
Verifies file existence, binary stream markers (fLaC), STREAMINFO headers,
lossless sample rate, bit depth, stream integrity, and SHA-256 checksums.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.music.flac_validator import (
    FlacProperties,
    FlacValidationError,
    FlacValidator,
    flac_validator,
)


@dataclass
class FlacValidationResult:
    """Outcome of validating a downloaded FLAC file."""
    valid: bool
    codec: str
    sample_rate: int
    bit_depth: int
    channels: int
    duration_ms: int
    checksum: str
    file_size_bytes: int
    error: Optional[str] = None


class FlacValidationService:
    """Wrapper service providing safe boolean validation and structural metadata."""

    def __init__(self) -> None:
        self._validator = FlacValidator()

    def validate(self, file_path: str) -> FlacValidationResult:
        """
        Validate audio file at file_path.
        Returns FlacValidationResult with status and extracted audio stream properties.
        """
        try:
            props: FlacProperties = self._validator.validate_file(file_path)
            return FlacValidationResult(
                valid=True,
                codec=props.codec.upper(),
                sample_rate=props.sample_rate,
                bit_depth=props.bit_depth,
                channels=props.channels,
                duration_ms=int(props.duration_seconds * 1000),
                checksum=props.checksum_sha256,
                file_size_bytes=props.file_size_bytes,
                error=None
            )
        except FlacValidationError as exc:
            return FlacValidationResult(
                valid=False,
                codec="unknown",
                sample_rate=0,
                bit_depth=0,
                channels=0,
                duration_ms=0,
                checksum="",
                file_size_bytes=0,
                error=str(exc)
            )


# Global singleton instance
flac_validation_service = FlacValidationService()
