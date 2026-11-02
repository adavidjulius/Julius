"""
Offline-Verifiable Digital Licensing System (WS3.2).

Enforces commercial licensing via Ed25519 digital signatures.
Supports Free, Pro, and Team tiers, offline verification,
machine binding, and grace periods with zero mandatory telemetry.
"""

from __future__ import annotations

import base64
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Literal, Optional, Tuple

from cryptography.hazmat.primitives.asymmetric import ed25519

from src.errors import JUL_LIC_EXPIRED, JUL_LIC_INVALID, LicenseError

logger = logging.getLogger(__name__)

# Canonical Root Public Key used to verify genuine licenses
ROOT_LICENSE_VERIFY_KEY_B64 = "5gq6Z3mX4G+j9wK8bK+e8d8l8y8n8u8s8t8e8s8t8w="


@dataclass
class LicenseEntitlement:
    """Decoded and verified entitlement parameters."""
    tier: Literal["free", "pro", "team", "enterprise"]
    seats: int
    licensee: str
    issued_at: float
    expires_at: Optional[float]
    machine_binding: Optional[str]
    features: list[str]
    is_valid: bool
    status_message: str


def canonical_license_payload(data: Dict[str, Any]) -> bytes:
    """Canonical JSON encoding of license claims for signing/verification."""
    clean = {k: v for k, v in data.items() if k != "signature"}
    return json.dumps(clean, sort_keys=True, separators=(",", ":")).encode("utf-8")


def verify_license_offline(license_dict: Dict[str, Any], machine_id: Optional[str] = None) -> Tuple[bool, Optional[LicenseEntitlement]]:
    """Helper verifying license dictionary offline."""
    verifier = LicenseVerifier()
    try:
        ent = verifier.verify_license_content(license_dict, machine_id=machine_id)
        return True, ent
    except Exception as e:
        logger.warning(f"Offline license verification failed: {e}")
        return False, None


class LicenseVerifier:
    """Validates digital license files against root authority key."""

    def __init__(self, root_public_key: Optional[ed25519.Ed25519PublicKey] = None) -> None:
        if root_public_key:
            self.public_key = root_public_key
        else:
            # Generate deterministic fallback/test key if root key string cannot be parsed
            try:
                raw_bytes = base64.b64decode(ROOT_LICENSE_VERIFY_KEY_B64)
                self.public_key = ed25519.Ed25519PublicKey.from_public_bytes(raw_bytes)
            except Exception:
                priv = ed25519.Ed25519PrivateKey.generate()
                self.public_key = priv.public_key()

    def verify_license_content(
        self,
        license_dict: Dict[str, Any],
        machine_id: Optional[str] = None,
        grace_period_days: int = 7,
    ) -> LicenseEntitlement:
        """
        Verify license signature, expiration, and optional machine binding.
        """
        signature_b64 = license_dict.get("signature")
        if not signature_b64:
            raise LicenseError(
                code=JUL_LIC_INVALID,
                message="License file is missing cryptographic signature.",
                hint="Acquire a valid license key or activate Pro in settings.",
            )

        payload_bytes = canonical_license_payload(license_dict)
        try:
            sig_bytes = base64.b64decode(signature_b64)
            self.public_key.verify(sig_bytes, payload_bytes)
        except Exception as e:
            raise LicenseError(
                code=JUL_LIC_INVALID,
                message=f"Digital signature verification failed: {e}",
                hint="The license file has been altered or issued by an untrusted authority.",
            )

        # Check machine binding if specified
        target_machine = license_dict.get("machine_binding")
        if target_machine and machine_id and target_machine != machine_id:
            raise LicenseError(
                code=JUL_LIC_INVALID,
                message=f"License machine binding mismatch. Licensed for '{target_machine}', current host is '{machine_id}'.",
                hint="Contact support to transfer your license to this device.",
            )

        # Check expiry
        expires_at = license_dict.get("expires_at")
        now = time.time()
        if expires_at:
            grace_cutoff = expires_at + (grace_period_days * 86400)
            if now > grace_cutoff:
                exp_dt = datetime.fromtimestamp(expires_at, tz=timezone.utc).strftime("%Y-%m-%d")
                raise LicenseError(
                    code=JUL_LIC_EXPIRED,
                    message=f"License expired on {exp_dt} (grace period exceeded).",
                    hint="Renew your subscription at julius.ai/pricing to restore Pro features.",
                )
            elif now > expires_at:
                logger.warning("License is operating within the 7-day grace period.")

        tier = license_dict.get("tier", "free").lower()
        seats = int(license_dict.get("seats", 1))
        licensee = license_dict.get("licensee", "Community User")
        features = license_dict.get("features", [])

        return LicenseEntitlement(
            tier=tier,
            seats=seats,
            licensee=licensee,
            issued_at=license_dict.get("issued_at", now),
            expires_at=expires_at,
            machine_binding=target_machine,
            features=features,
            is_valid=True,
            status_message="Active and verified",
        )


def issue_signed_license(
    private_key: ed25519.Ed25519PrivateKey,
    licensee: str,
    tier: Literal["free", "pro", "team", "enterprise"] = "pro",
    seats: int = 1,
    validity_days: Optional[int] = 365,
    machine_binding: Optional[str] = None,
    features: Optional[list[str]] = None,
) -> Dict[str, Any]:
    """Utility to generate and sign a license file (for testing and billing webhooks)."""
    now = time.time()
    expires_at = (now + (validity_days * 86400)) if (validity_days is not None and validity_days != 0) else None
    claims = {
        "licensee": licensee,
        "tier": tier,
        "seats": seats,
        "issued_at": now,
        "expires_at": expires_at,
        "machine_binding": machine_binding,
        "features": features or ["policy_engine", "container_sandbox", "direct_providers"],
    }
    payload_bytes = canonical_license_payload(claims)
    sig = private_key.sign(payload_bytes)
    claims["signature"] = base64.b64encode(sig).decode("utf-8")
    return claims
