"""
High-Entropy Scoped API Key Management (WS3.1).

Features:
- Prefixed high-entropy keys (`jul_live_...`).
- Stored exclusively as cryptographic hashes (never plaintext).
- Constant-time comparison via secrets.compare_digest.
- Scopes, expiration dates, rotation, and server-side revocation.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

API_KEY_PREFIX = "jul_live_"


@dataclass
class APIKeyRecord:
    """Metadata record for a provisioned API key."""
    id: str
    key_hash: str
    prefix: str
    name: str
    user_id: int
    scopes: List[str]
    created_at: float
    expires_at: Optional[float]
    revoked: bool
    last_used_at: Optional[float]


class APIKeyManager:
    """Manages scoped API keys stored in SQLite."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        if db_path:
            self.db_path = Path(db_path)
        else:
            self.db_path = Path.home() / ".julius" / "auth.db"
        self._init_db()

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                id TEXT PRIMARY KEY,
                key_hash TEXT NOT NULL UNIQUE,
                prefix TEXT NOT NULL,
                name TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                scopes TEXT NOT NULL,
                created_at REAL NOT NULL,
                expires_at REAL,
                revoked INTEGER NOT NULL DEFAULT 0,
                last_used_at REAL
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash);")
        conn.commit()
        conn.close()

    @staticmethod
    def _hash_key(raw_key: str) -> str:
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    def generate_key(
        self,
        name: str,
        user_id: int,
        scopes: Optional[List[str]] = None,
        ttl_days: Optional[int] = 90,
    ) -> Tuple[str, APIKeyRecord]:
        """
        Generate a new scoped API key. Returns (raw_plaintext_key, record).
        The raw key is returned ONCE and never stored on disk.
        """
        random_entropy = secrets.token_urlsafe(32)
        raw_key = f"{API_KEY_PREFIX}{random_entropy}"
        key_id = f"key_{secrets.token_hex(8)}"
        key_hash = self._hash_key(raw_key)
        prefix_preview = raw_key[:14] + "..."
        now = time.time()
        expires_at = (now + (ttl_days * 86400)) if ttl_days else None
        scope_list = scopes or ["*"]

        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO api_keys (id, key_hash, prefix, name, user_id, scopes, created_at, expires_at, revoked, last_used_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, NULL)
            """,
            (key_id, key_hash, prefix_preview, name, user_id, ",".join(scope_list), now, expires_at),
        )
        conn.commit()
        conn.close()

        record = APIKeyRecord(
            id=key_id,
            key_hash=key_hash,
            prefix=prefix_preview,
            name=name,
            user_id=user_id,
            scopes=scope_list,
            created_at=now,
            expires_at=expires_at,
            revoked=False,
            last_used_at=None,
        )
        return raw_key, record

    def verify_key(self, raw_key: str, required_scope: Optional[str] = None) -> Optional[APIKeyRecord]:
        """
        Verify raw API key hash, revocation status, expiration, and scope.
        Returns APIKeyRecord if valid, else None.
        """
        if not raw_key or not raw_key.startswith(API_KEY_PREFIX):
            return None

        key_hash = self._hash_key(raw_key)
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, key_hash, prefix, name, user_id, scopes, created_at, expires_at, revoked, last_used_at
            FROM api_keys WHERE key_hash = ?
            """,
            (key_hash,),
        )
        row = cursor.fetchone()

        if not row:
            conn.close()
            return None

        (k_id, stored_hash, prefix, name, u_id, scopes_str, created_at, expires_at, revoked, last_used) = row

        # Constant-time comparison
        if not secrets.compare_digest(key_hash, stored_hash):
            conn.close()
            return None

        # Check revocation
        if revoked:
            conn.close()
            return None

        # Check expiration
        now = time.time()
        if expires_at and now > expires_at:
            conn.close()
            return None

        # Check scope
        scopes = [s.strip() for s in scopes_str.split(",") if s.strip()]
        if required_scope and "*" not in scopes and required_scope not in scopes:
            conn.close()
            return None

        # Update last_used_at
        cursor.execute("UPDATE api_keys SET last_used_at = ? WHERE id = ?", (now, k_id))
        conn.commit()
        conn.close()

        return APIKeyRecord(
            id=k_id,
            key_hash=stored_hash,
            prefix=prefix,
            name=name,
            user_id=u_id,
            scopes=scopes,
            created_at=created_at,
            expires_at=expires_at,
            revoked=bool(revoked),
            last_used_at=now,
        )

    def revoke_key(self, key_id: str) -> bool:
        """Revoke key immediately."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute("UPDATE api_keys SET revoked = 1 WHERE id = ?", (key_id,))
        affected = cursor.rowcount
        conn.commit()
        conn.close()
        return affected > 0

    def list_keys(self, user_id: int = 1) -> List[APIKeyRecord]:
        """List provisioned API keys for a user."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, key_hash, prefix, name, user_id, scopes, created_at, expires_at, revoked, last_used_at FROM api_keys WHERE user_id = ?",
            (user_id,)
        )
        rows = cursor.fetchall()
        conn.close()
        return [
            APIKeyRecord(
                id=r[0],
                key_hash=r[1],
                prefix=r[2],
                name=r[3],
                user_id=r[4],
                scopes=r[5].split(","),
                created_at=r[6],
                expires_at=r[7],
                revoked=bool(r[8]),
                last_used_at=r[9],
            )
            for r in rows
        ]


# Alias for backward compatibility
ApiKeyStore = APIKeyManager

