"""
Update Verification Engine (WS9.3).

Verifies Ed25519 manifest signature and payload SHA-256 integrity.
"""

from __future__ import annotations

import base64
import hashlib
import logging
from pathlib import Path
from typing import Tuple

from cryptography.hazmat.primitives.asymmetric import ed25519

from src.updater.manifest import UpdateManifest

logger = logging.getLogger(__name__)


def verify_update_signature(manifest: UpdateManifest) -> Tuple[bool, str]:
    """Helper verifying manifest digital signature."""
    return UpdateVerifier.verify_manifest_signature(manifest)


class UpdateVerifier:
    """Validates downloaded manifests and release payload archives."""

    @staticmethod
    def verify_manifest_signature(manifest: UpdateManifest) -> Tuple[bool, str]:
        """Verify digital signature on update manifest."""
        try:
            pub_bytes = base64.b64decode(manifest.signer_pubkey)
            sig_bytes = base64.b64decode(manifest.signature)
            pub_key = ed25519.Ed25519PublicKey.from_public_bytes(pub_bytes)
            pub_key.verify(sig_bytes, manifest.to_canonical_bytes())
            return True, "Manifest signature verified"
        except Exception as e:
            return False, f"Manifest signature verification failed: {e}"

    @staticmethod
    def verify_payload_hash(payload_path: Path | str, expected_sha256: str) -> Tuple[bool, str]:
        """Compute and assert SHA-256 checksum of downloaded artifact."""
        p = Path(payload_path)
        if not p.exists():
            return False, f"Payload file {p} does not exist"

        hasher = hashlib.sha256()
        with open(p, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        digest = hasher.hexdigest().lower()

        if digest == expected_sha256.lower():
            return True, "Payload SHA-256 verified"
        return False, f"Checksum mismatch: expected {expected_sha256}, got {digest}"

