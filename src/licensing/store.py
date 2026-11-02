"""
License Storage & Local State Management (WS3.2).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from src.licensing.verify import LicenseEntitlement, LicenseVerifier

logger = logging.getLogger(__name__)


def get_installed_license(path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    return LicenseStore(path).load_license()


def install_license(raw: str, path: Optional[str] = None) -> None:
    store = LicenseStore(path)
    try:
        data = json.loads(raw)
    except Exception:
        data = {"license_key": raw}
    store.save_license(data)


class LicenseStore:
    """Manages the local license file in ~/.julius/license.json."""

    def __init__(self, license_path: Optional[str] = None, verifier: Optional[LicenseVerifier] = None) -> None:
        if license_path:
            self.license_path = Path(license_path)
        else:
            self.license_path = Path.home() / ".julius" / "license.json"
        self.verifier = verifier or LicenseVerifier()

    def load_license(self) -> Optional[Dict[str, Any]]:
        if not self.license_path.exists():
            return None
        try:
            with open(self.license_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to read license file: {e}")
            return None

    def save_license(self, license_dict: Dict[str, Any]) -> None:
        self.license_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.license_path, "w", encoding="utf-8") as f:
            json.dump(license_dict, f, indent=2)

    def get_entitlements(self, machine_id: Optional[str] = None) -> LicenseEntitlement:
        data = self.load_license()
        if not data:
            # Default to Community Free Tier
            return LicenseEntitlement(
                tier="free",
                seats=1,
                licensee="Community User",
                issued_at=0.0,
                expires_at=None,
                machine_binding=None,
                features=["core_agent", "direct_providers", "workspace_sandbox"],
                is_valid=True,
                status_message="Community Free Tier",
            )
        try:
            return self.verifier.verify_license_content(data, machine_id=machine_id)
        except Exception as e:
            return LicenseEntitlement(
                tier="free",
                seats=1,
                licensee="Invalid License",
                issued_at=0.0,
                expires_at=None,
                machine_binding=None,
                features=["core_agent"],
                is_valid=False,
                status_message=str(e),
            )

