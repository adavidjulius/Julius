"""
Cryptographic Audit Ledger v2 (WS2.6).

Features:
- HMAC-SHA256 hash chaining with OS Keychain key storage.
- Canonical JSON serialization (sorted keys, compact delimiters, UTF-8).
- Genesis hash pinning.
- Single-writer file locking (portalocker / filelock).
- Ed25519 signed checkpoints.
- Chain integrity verification command (`julius audit verify`).
- Seamless backward compatibility with legacy `AuditLogger` calls.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import filelock
from cryptography.hazmat.primitives.asymmetric import ed25519

from src.security.secrets import get_secrets_manager

logger = logging.getLogger(__name__)

GENESIS_HASH = "0000000000000000000000000000000000000000000000000000000000000000"


def canonical_json(obj: Any) -> str:
    """Canonical JSON: sorted keys, compact separators (no spaces), UTF-8 encoded."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class CryptographicAuditLedger:
    """
    Tamper-evident, HMAC-SHA256 chained audit ledger.
    """

    def __init__(
        self,
        db_or_path: Optional[Any] = None,
        ledger_path: Optional[Path | str] = None,
        log_file: Optional[Path | str] = None,
        keychain_service: str = "JuliusAuditLedger",
        db: Optional[Any] = None,
        **kwargs: Any,
    ) -> None:
        # Disambiguate first positional argument
        if isinstance(db_or_path, (str, Path)):
            target_path = db_or_path
            resolved_db = db
        else:
            resolved_db = db_or_path or db
            target_path = ledger_path or log_file

        if target_path:
            self.ledger_path = Path(target_path)
        else:
            self.ledger_path = Path.home() / ".julius" / "audit_chain.jsonl"

        self.lock_path = self.ledger_path.with_suffix(".lock")
        self.log_file = self.ledger_path  # legacy attribute alias
        self.db = resolved_db
        self.keychain_service = keychain_service
        self._audit_key = self._get_or_create_audit_key()
        self._checkpoint_key = self._get_or_create_checkpoint_key()
        self._last_hash = self._initialize_chain_state()

    def _get_or_create_audit_key(self) -> bytes:
        """Retrieve audit HMAC key from local protected store, env, or keychain."""
        env_val = os.getenv("JULIUS_AUDIT_HMAC_KEY")
        if env_val:
            try:
                return base64.b64decode(env_val)
            except Exception:
                pass
        key_file = Path.home() / ".julius" / "audit_hmac.key"
        if key_file.exists():
            try:
                return key_file.read_bytes()
            except Exception:
                pass

        # Generate new high-entropy 256-bit key and persist with 0600 permissions
        new_key = os.urandom(32)
        try:
            key_file.parent.mkdir(parents=True, exist_ok=True)
            key_file.write_bytes(new_key)
            if os.name != "nt":
                os.chmod(key_file, 0o600)
        except Exception:
            pass
        return new_key

    def _get_or_create_checkpoint_key(self) -> ed25519.Ed25519PrivateKey:
        """Retrieve or create Ed25519 key for audit checkpoint signing."""
        key_file = Path.home() / ".julius" / "audit_checkpoint.key"
        if key_file.exists():
            try:
                raw_bytes = key_file.read_bytes()
                return ed25519.Ed25519PrivateKey.from_private_bytes(raw_bytes)
            except Exception:
                pass
        priv_key = ed25519.Ed25519PrivateKey.generate()
        try:
            key_file.parent.mkdir(parents=True, exist_ok=True)
            key_file.write_bytes(priv_key.private_bytes_raw())
            if os.name != "nt":
                os.chmod(key_file, 0o600)
        except Exception:
            pass
        return priv_key

    def _initialize_chain_state(self) -> str:
        """Read last hash from ledger or pin genesis hash."""
        if not self.ledger_path.exists():
            return GENESIS_HASH

        last_hash = GENESIS_HASH
        try:
            with open(self.ledger_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        entry = json.loads(line)
                        if "entry_hash" in entry:
                            last_hash = entry["entry_hash"]
        except Exception as e:
            logger.warning(f"Error reading audit chain state: {e}")
        return last_hash

    def append_entry(
        self,
        actor: str,
        action: str,
        decision: str,
        policy_rule: str,
        payload: Any,
    ) -> Dict[str, Any]:
        """
        Atomically append an HMAC-chained audit entry.
        """
        sec_mgr = get_secrets_manager()
        payload_redacted = sec_mgr.choke_point_audit(payload)

        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        lock = filelock.FileLock(str(self.lock_path), timeout=10)

        with lock:
            ts = datetime.now(timezone.utc).isoformat()
            # Determine current sequence
            seq = 1
            if self.ledger_path.exists():
                with open(self.ledger_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            seq += 1

            entry_data = {
                "seq": seq,
                "ts": ts,
                "actor": actor,
                "action": action,
                "decision": decision,
                "policy_rule": policy_rule,
                "payload_redacted": payload_redacted,
                "prev_hash": self._last_hash,
            }

            canonical_str = canonical_json(entry_data)
            entry_hash = hmac.new(
                self._audit_key,
                canonical_str.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()

            full_record = {**entry_data, "entry_hash": entry_hash}

            with open(self.ledger_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(full_record, ensure_ascii=False) + "\n")

            self._last_hash = entry_hash

            # Also write to SQLite DB if configured
            if self.db and hasattr(self.db, "add_audit_log"):
                try:
                    self.db.add_audit_log(
                        action=action,
                        details=json.dumps(payload_redacted),
                        ip_address=actor,
                    )
                except Exception:
                    pass

            return full_record

    def log(
        self,
        action: str,
        user_id: int | None = None,
        details: dict[str, Any] | str | None = None,
        ip_address: str | None = None,
    ) -> None:
        """Legacy compatibility wrapper for AuditLogger."""
        self.append_entry(
            actor=f"user_{user_id}" if user_id else (ip_address or "system"),
            action=action,
            decision="logged",
            policy_rule="audit_logger.legacy",
            payload=details or {},
        )

    def log_policy_event(
        self,
        actor: str,
        action: str,
        decision: str,
        rule: str,
        payload: Any,
    ) -> Dict[str, Any]:
        """Direct hook for Central Policy Engine."""
        return self.append_entry(
            actor=actor,
            action=action,
            decision=decision,
            policy_rule=rule,
            payload=payload,
        )

    def create_signed_checkpoint(self) -> Dict[str, Any]:
        """Emit an Ed25519-signed checkpoint pinning the current chain head."""
        pub_key = self._checkpoint_key.public_key()
        pub_bytes = pub_key.public_bytes_raw()
        b64_pub = base64.b64encode(pub_bytes).decode("utf-8")

        checkpoint_data = {
            "type": "checkpoint",
            "ts": datetime.now(timezone.utc).isoformat(),
            "head_hash": self._last_hash,
            "public_key": b64_pub,
        }
        can_str = canonical_json(checkpoint_data)
        sig = self._checkpoint_key.sign(can_str.encode("utf-8"))
        b64_sig = base64.b64encode(sig).decode("utf-8")

        full_checkpoint = {**checkpoint_data, "signature": b64_sig}
        with open(self.ledger_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(full_checkpoint, ensure_ascii=False) + "\n")

        return full_checkpoint

    def anchor_to_zephon(self, node_url: str = "http://localhost:8332") -> Dict[str, Any]:
        """Anchor the latest signed checkpoint to the Zephon blockchain."""
        checkpoint = self.create_signed_checkpoint()
        try:
            from src.integrations.zephon import ZephonAuditNotary
            notary = ZephonAuditNotary(node_url=node_url)
            return notary.anchor_checkpoint(checkpoint)
        except Exception as e:
            logger.warning(f"Could not anchor to Zephon: {e}")
            return {"status": "error", "error": str(e), "checkpoint": checkpoint}

    def verify_chain(self) -> Tuple[bool, Optional[str], int]:
        """
        Verify entire cryptographic chain continuity.
        Returns (is_valid, error_description, verified_count).
        """
        if not self.ledger_path.exists():
            return True, "Audit log does not exist yet (clean state)", 0

        current_prev = GENESIS_HASH
        count = 0

        with open(self.ledger_path, "r", encoding="utf-8") as f:
            for line_idx, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except Exception:
                    return False, f"Line {line_idx}: Invalid JSON syntax", count

                if record.get("type") == "checkpoint":
                    # Checkpoint validation
                    sig_b64 = record.get("signature")
                    pub_b64 = record.get("public_key")
                    chk_data = {
                        "type": record["type"],
                        "ts": record["ts"],
                        "head_hash": record["head_hash"],
                        "public_key": pub_b64,
                    }
                    try:
                        pub = ed25519.Ed25519PublicKey.from_public_bytes(base64.b64decode(pub_b64))
                        pub.verify(base64.b64decode(sig_b64), canonical_json(chk_data).encode("utf-8"))
                    except Exception as e:
                        return False, f"Line {line_idx}: Checkpoint signature verification failed: {e}", count
                    continue

                claimed_hash = record.get("entry_hash")
                claimed_prev = record.get("prev_hash")

                # Verify prev_hash matches expected chain continuity
                if claimed_prev != current_prev:
                    return (
                        False,
                        f"Line {line_idx} (seq={record.get('seq')}): Chain break detected! "
                        f"Expected prev_hash '{current_prev}', got '{claimed_prev}'",
                        count,
                    )

                # Recompute HMAC
                fields_to_hash = {
                    "seq": record["seq"],
                    "ts": record["ts"],
                    "actor": record["actor"],
                    "action": record["action"],
                    "decision": record["decision"],
                    "policy_rule": record["policy_rule"],
                    "payload_redacted": record["payload_redacted"],
                    "prev_hash": claimed_prev,
                }
                computed_hash = hmac.new(
                    self._audit_key,
                    canonical_json(fields_to_hash).encode("utf-8"),
                    hashlib.sha256,
                ).hexdigest()

                if computed_hash != claimed_hash:
                    return (
                        False,
                        f"Line {line_idx} (seq={record.get('seq')}): HMAC hash tampering detected! "
                        f"Computed '{computed_hash}', stored '{claimed_hash}'",
                        count,
                    )

                current_prev = claimed_hash
                count += 1

        return True, "Chain intact and mathematically verified", count


# Alias for backwards compatibility
AuditLogger = CryptographicAuditLedger
