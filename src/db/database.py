"""
Persistent SQLite database engine for Julius multi-tenant architecture.

Handles:
- WAL mode, foreign keys, and thread-safe connection pooling
- Schema migration and auto-creation
- Models for Users, Workspaces, Sessions, Audit Logs, and Rate Limits
- Zero plaintext credential storage
"""

from __future__ import annotations

import os
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.db.pragmas import apply_production_pragmas
from src.db.migrations.runner import MigrationRunner


@dataclass
class User:
    id: str
    username: str
    email: str
    password_hash: str
    role: str  # 'admin', 'developer', 'user'
    status: str  # 'active', 'disabled'
    created_at: float
    updated_at: float

    def to_dict(self, include_hash: bool = False) -> Dict[str, Any]:
        data = {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "role": self.role,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if include_hash:
            data["password_hash"] = self.password_hash
        return data


@dataclass
class WorkspaceRecord:
    id: str
    user_id: str
    name: str
    root_path: str
    is_default: bool
    created_at: float
    updated_at: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "root_path": self.root_path,
            "is_default": self.is_default,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class Session:
    id: str
    user_id: str
    token_hash: str
    ip_address: Optional[str]
    user_agent: Optional[str]
    created_at: float
    expires_at: float
    revoked_at: Optional[float]

    @property
    def is_active(self) -> bool:
        now = time.time()
        return (self.revoked_at is None) and (now < self.expires_at)


@dataclass
class AuditLogRecord:
    id: int
    user_id: Optional[str]
    event_type: str
    resource_type: Optional[str]
    resource_id: Optional[str]
    details: Optional[str]
    ip_address: Optional[str]
    created_at: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "event_type": self.event_type,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "details": self.details,
            "ip_address": self.ip_address,
            "created_at": self.created_at,
        }


class Database:
    """Thread-safe SQLite database manager for Julius."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        if db_path is None:
            # Default protected storage location outside normal workspaces
            base_dir = os.environ.get("JULIUS_DATA_DIR")
            if base_dir:
                base_dir = os.path.expanduser(base_dir)
            if not base_dir:
                # If /var/lib/julius exists and writable, use it; otherwise use .julius_data in repo parent or root
                var_lib = Path("/var/lib/julius")
                if var_lib.exists() and os.access(str(var_lib), os.W_OK):
                    base_dir = str(var_lib)
                else:
                    base_dir = str(Path.cwd() / ".julius_data")
            Path(base_dir).mkdir(parents=True, exist_ok=True)
            self.db_path = str(Path(base_dir) / "julius.db")
        else:
            self.db_path = str(Path(db_path).resolve())
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        self._local = threading.local()
        self._init_schema()

    def get_connection(self) -> sqlite3.Connection:
        """Get or create a thread-local SQLite connection with WAL mode enabled."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=30.0)
            conn.row_factory = sqlite3.Row
            apply_production_pragmas(conn)
            self._local.conn = conn
        return self._local.conn

    def _init_schema(self) -> None:
        """Create database tables and indices if not already present, running migrations."""
        runner = MigrationRunner(self.db_path)
        runner.run_pending_migrations()
        conn = self.get_connection()
        with conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                status TEXT NOT NULL DEFAULT 'active',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
            """)

            conn.execute("""
            CREATE TABLE IF NOT EXISTS workspaces (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                name TEXT NOT NULL,
                root_path TEXT UNIQUE NOT NULL,
                is_default INTEGER DEFAULT 0,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            """)

            conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                token_hash TEXT UNIQUE NOT NULL,
                ip_address TEXT,
                user_agent TEXT,
                created_at REAL NOT NULL,
                expires_at REAL NOT NULL,
                revoked_at REAL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            """)

            conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                event_type TEXT NOT NULL,
                resource_type TEXT,
                resource_id TEXT,
                details TEXT,
                ip_address TEXT,
                created_at REAL NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
            );
            """)

            conn.execute("""
            CREATE TABLE IF NOT EXISTS rate_limits (
                key TEXT PRIMARY KEY,
                count INTEGER NOT NULL DEFAULT 1,
                window_start REAL NOT NULL
            );
            """)

            # Indices for rapid querying and enforcement
            conn.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_workspaces_user ON workspaces(user_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(token_hash);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_logs(user_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_logs(created_at);")

    # ── User DAO ─────────────────────────────────────────────────────────────

    def create_user(
        self,
        username: str,
        email: str,
        password_hash: str,
        role: str = "user",
        status: str = "active",
    ) -> User:
        now = time.time()
        user_id = str(uuid.uuid4())
        conn = self.get_connection()
        with conn:
            conn.execute(
                """
                INSERT INTO users (id, username, email, password_hash, role, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, username.strip(), email.strip().lower(), password_hash, role, status, now, now),
            )
        return User(
            id=user_id,
            username=username.strip(),
            email=email.strip().lower(),
            password_hash=password_hash,
            role=role,
            status=status,
            created_at=now,
            updated_at=now,
        )

    def get_user_by_id(self, user_id: str) -> Optional[User]:
        conn = self.get_connection()
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            return None
        return User(**dict(row))

    def get_user_by_email_or_username(self, identifier: str) -> Optional[User]:
        clean = identifier.strip().lower()
        conn = self.get_connection()
        row = conn.execute(
            "SELECT * FROM users WHERE LOWER(email) = ? OR LOWER(username) = ?",
            (clean, clean),
        ).fetchone()
        if not row:
            return None
        return User(**dict(row))

    def list_users(self, limit: int = 100, offset: int = 0) -> List[User]:
        conn = self.get_connection()
        rows = conn.execute(
            "SELECT * FROM users ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [User(**dict(r)) for r in rows]

    def update_user_status(self, user_id: str, status: str) -> bool:
        now = time.time()
        conn = self.get_connection()
        with conn:
            cur = conn.execute(
                "UPDATE users SET status = ?, updated_at = ? WHERE id = ?",
                (status, now, user_id),
            )
            return cur.rowcount > 0

    def update_user_role(self, user_id: str, role: str) -> bool:
        now = time.time()
        conn = self.get_connection()
        with conn:
            cur = conn.execute(
                "UPDATE users SET role = ?, updated_at = ? WHERE id = ?",
                (role, now, user_id),
            )
            return cur.rowcount > 0

    def count_users(self) -> int:
        conn = self.get_connection()
        row = conn.execute("SELECT COUNT(*) AS cnt FROM users").fetchone()
        return row["cnt"] if row else 0

    # ── Workspace DAO ────────────────────────────────────────────────────────

    def create_workspace(
        self,
        user_id: str,
        name: str,
        root_path: str,
        is_default: bool = True,
    ) -> WorkspaceRecord:
        now = time.time()
        ws_id = str(uuid.uuid4())
        canonical_path = str(Path(root_path).resolve())
        conn = self.get_connection()
        with conn:
            if is_default:
                # Mark other workspaces of this user as non-default
                conn.execute(
                    "UPDATE workspaces SET is_default = 0 WHERE user_id = ?",
                    (user_id,),
                )
            conn.execute(
                """
                INSERT INTO workspaces (id, user_id, name, root_path, is_default, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (ws_id, user_id, name, canonical_path, 1 if is_default else 0, now, now),
            )
        return WorkspaceRecord(
            id=ws_id,
            user_id=user_id,
            name=name,
            root_path=canonical_path,
            is_default=is_default,
            created_at=now,
            updated_at=now,
        )

    def get_workspace_by_id(self, workspace_id: str) -> Optional[WorkspaceRecord]:
        conn = self.get_connection()
        row = conn.execute("SELECT * FROM workspaces WHERE id = ?", (workspace_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["is_default"] = bool(d["is_default"])
        return WorkspaceRecord(**d)

    def get_user_workspaces(self, user_id: str) -> List[WorkspaceRecord]:
        conn = self.get_connection()
        rows = conn.execute(
            "SELECT * FROM workspaces WHERE user_id = ? ORDER BY is_default DESC, created_at ASC",
            (user_id,),
        ).fetchall()
        res = []
        for r in rows:
            d = dict(r)
            d["is_default"] = bool(d["is_default"])
            res.append(WorkspaceRecord(**d))
        return res

    def get_user_default_workspace(self, user_id: str) -> Optional[WorkspaceRecord]:
        conn = self.get_connection()
        row = conn.execute(
            "SELECT * FROM workspaces WHERE user_id = ? AND is_default = 1",
            (user_id,),
        ).fetchone()
        if not row:
            # Fallback to earliest workspace
            row = conn.execute(
                "SELECT * FROM workspaces WHERE user_id = ? ORDER BY created_at ASC LIMIT 1",
                (user_id,),
            ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["is_default"] = bool(d["is_default"])
        return WorkspaceRecord(**d)

    # ── Session DAO ──────────────────────────────────────────────────────────

    def create_session(
        self,
        user_id: str,
        token_hash: str,
        ttl_seconds: int = 30 * 24 * 3600,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Session:
        now = time.time()
        session_id = str(uuid.uuid4())
        expires_at = now + ttl_seconds
        conn = self.get_connection()
        with conn:
            conn.execute(
                """
                INSERT INTO sessions (id, user_id, token_hash, ip_address, user_agent, created_at, expires_at, revoked_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (session_id, user_id, token_hash, ip_address, user_agent, now, expires_at),
            )
        return Session(
            id=session_id,
            user_id=user_id,
            token_hash=token_hash,
            ip_address=ip_address,
            user_agent=user_agent,
            created_at=now,
            expires_at=expires_at,
            revoked_at=None,
        )

    def get_session_by_token_hash(self, token_hash: str) -> Optional[Session]:
        conn = self.get_connection()
        row = conn.execute(
            "SELECT * FROM sessions WHERE token_hash = ? AND revoked_at IS NULL",
            (token_hash,),
        ).fetchone()
        if not row:
            return None
        session = Session(**dict(row))
        if not session.is_active:
            return None
        return session

    def revoke_session(self, token_hash: str) -> bool:
        now = time.time()
        conn = self.get_connection()
        with conn:
            cur = conn.execute(
                "UPDATE sessions SET revoked_at = ? WHERE token_hash = ? AND revoked_at IS NULL",
                (now, token_hash),
            )
            return cur.rowcount > 0

    def revoke_all_user_sessions(self, user_id: str) -> int:
        now = time.time()
        conn = self.get_connection()
        with conn:
            cur = conn.execute(
                "UPDATE sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
                (now, user_id),
            )
            return cur.rowcount

    # ── Audit Log DAO ────────────────────────────────────────────────────────

    def record_audit(
        self,
        event_type: str,
        user_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        details: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> int:
        now = time.time()
        conn = self.get_connection()
        with conn:
            cur = conn.execute(
                """
                INSERT INTO audit_logs (user_id, event_type, resource_type, resource_id, details, ip_address, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, event_type, resource_type, resource_id, details, ip_address, now),
            )
            return cur.lastrowid

    def list_audit_logs(
        self,
        limit: int = 100,
        offset: int = 0,
        user_id: Optional[str] = None,
        event_type: Optional[str] = None,
    ) -> List[AuditLogRecord]:
        conn = self.get_connection()
        query = "SELECT * FROM audit_logs WHERE 1=1"
        params: List[Any] = []
        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)
        if event_type:
            query += " AND event_type = ?"
            params.append(event_type)
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = conn.execute(query, tuple(params)).fetchall()
        return [AuditLogRecord(**dict(r)) for r in rows]

    # ── Rate Limiting DAO ────────────────────────────────────────────────────

    def check_and_increment_rate_limit(
        self,
        key: str,
        limit: int,
        window_seconds: int,
    ) -> Tuple[bool, int]:
        """
        Check if an action exceeds rate limits.
        Returns:
            (allowed: bool, current_count: int)
        """
        now = time.time()
        conn = self.get_connection()
        with conn:
            row = conn.execute("SELECT count, window_start FROM rate_limits WHERE key = ?", (key,)).fetchone()
            if not row or (now - row["window_start"] > window_seconds):
                # Reset window
                conn.execute(
                    "INSERT OR REPLACE INTO rate_limits (key, count, window_start) VALUES (?, 1, ?)",
                    (key, now),
                )
                return True, 1
            else:
                count = row["count"] + 1
                conn.execute("UPDATE rate_limits SET count = ? WHERE key = ?", (count, key))
                if count > limit:
                    return False, count
                return True, count
