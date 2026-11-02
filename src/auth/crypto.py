"""
Cryptographic services for Julius multi-user authentication.

Provides:
- Non-reversible Argon2id password hashing (with PBKDF2/scrypt fallback)
- Constant-time password verification
- Cryptographically secure session token generation and SHA-256 token hashing
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from typing import Tuple

try:
    from argon2 import PasswordHasher
    from argon2.exceptions import VerifyMismatchError, InvalidHashError
    _ARGON2_AVAILABLE = True
    _ph = PasswordHasher(
        time_cost=2,
        memory_cost=65536,  # 64 MB
        parallelism=1,
        hash_len=32,
        salt_len=16,
    )
except ImportError:
    _ARGON2_AVAILABLE = False
    _ph = None


def hash_password(password: str) -> str:
    """
    Hash password using Argon2id if available, falling back to PBKDF2-HMAC-SHA256.
    Returns formatted hash string that self-identifies its algorithm.
    """
    if not isinstance(password, str) or not password:
        raise ValueError("Password must be a non-empty string")

    if _ARGON2_AVAILABLE and _ph is not None:
        return _ph.hash(password)

    # Standard library fallback: PBKDF2-HMAC-SHA256 with 600,000 iterations
    salt = secrets.token_bytes(16)
    iterations = 600_000
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    salt_b64 = base64.b64encode(salt).decode("ascii")
    derived_b64 = base64.b64encode(derived).decode("ascii")
    return f"pbkdf2_sha256${iterations}${salt_b64}${derived_b64}"


def verify_password(password: str, password_hash: str) -> bool:
    """
    Verify password against stored hash using constant-time comparison.
    """
    if not password or not password_hash:
        return False

    # 1. Argon2 verification
    if password_hash.startswith("$argon2"):
        if not _ARGON2_AVAILABLE or _ph is None:
            return False
        try:
            return _ph.verify(password_hash, password)
        except (VerifyMismatchError, InvalidHashError):
            return False
        except Exception:
            return False

    # 2. PBKDF2-SHA256 fallback verification
    if password_hash.startswith("pbkdf2_sha256$"):
        parts = password_hash.split("$")
        if len(parts) != 4:
            return False
        try:
            iterations = int(parts[1])
            salt = base64.b64decode(parts[2].encode("ascii"))
            expected_key = base64.b64decode(parts[3].encode("ascii"))
            derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
            return hmac.compare_digest(derived, expected_key)
        except Exception:
            return False

    # 3. Legacy SHA-256 fallback (for existing single-user dev installations)
    # Allows existing dev users to migrate automatically upon first login
    if len(password_hash) == 64 and all(c in "0123456789abcdefABCDEF" for c in password_hash):
        legacy_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()
        return hmac.compare_digest(legacy_hash.lower(), password_hash.lower())

    return False


def generate_session_token() -> Tuple[str, str]:
    """
    Generate a cryptographically random session token (for client cookie)
    and its SHA-256 hash (to store securely in the database).

    Returns:
        (raw_token, token_hash)
    """
    raw_token = secrets.token_urlsafe(32)
    token_hash = hash_session_token(raw_token)
    return raw_token, token_hash


def hash_session_token(token: str) -> str:
    """
    Hash a session token with SHA-256 before database storage or lookup.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
