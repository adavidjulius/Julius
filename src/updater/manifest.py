"""
Update Manifest Specification & Schema (WS9.3).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional


@dataclass
class UpdateManifest:
    """Cryptographically signed release update manifest."""
    version: str
    channel: Literal["stable", "beta"]
    release_notes: str
    download_url: str
    sha256_hash: str
    min_supported_version: str
    published_at: str
    signature: str
    signer_pubkey: str

    def to_canonical_bytes(self) -> bytes:
        data = {
            "version": self.version,
            "channel": self.channel,
            "release_notes": self.release_notes,
            "download_url": self.download_url,
            "sha256_hash": self.sha256_hash,
            "min_supported_version": self.min_supported_version,
            "published_at": self.published_at,
        }
        return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")


def fetch_latest_manifest(channel: str = "stable") -> Optional[UpdateManifest]:
    """Retrieve latest update manifest metadata if available."""
    manifest_cache = Path.home() / ".julius" / f"manifest_{channel}.json"
    if manifest_cache.exists():
        try:
            data = json.loads(manifest_cache.read_text(encoding="utf-8"))
            return UpdateManifest(**data)
        except Exception:
            pass
    return None

