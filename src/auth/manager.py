"""
High-level authentication, session, and role lifecycle management for Julius.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional, Tuple

from src.db.database import Database, User, Session, WorkspaceRecord
from .crypto import hash_password, verify_password, generate_session_token, hash_session_token


EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
USERNAME_REGEX = re.compile(r"^[a-zA-Z0-9_\-\. ]{3,32}$")


class AuthManager:
    """Manages authentication, sessions, and multi-tenant workspace provisioning."""

    def __init__(
        self,
        db: Database,
        base_workspaces_dir: Optional[str] = None,
        server_root: Optional[str] = None,
    ) -> None:
        self.db = db
        self.server_root = str(Path(server_root or Path.cwd()).resolve())
        if base_workspaces_dir:
            self.base_workspaces_dir = str(Path(base_workspaces_dir).resolve())
        else:
            self.base_workspaces_dir = str(Path(self.server_root) / "workspaces")
        Path(self.base_workspaces_dir).mkdir(parents=True, exist_ok=True)

        # Seed initial Super Admin if DB is completely empty
        self.ensure_admin_account()

    def ensure_admin_account(self) -> None:
        """Seed default admin account for owner if no users exist in database."""
        if self.db.count_users() == 0:
            admin_user = os.environ.get("JULIUS_ADMIN_USERNAME", "david julius")
            admin_email = os.environ.get("JULIUS_ADMIN_EMAIL", "david@julius.ai")
            admin_pass = os.environ.get("JULIUS_ADMIN_PASSWORD", "david")

            pw_hash = hash_password(admin_pass)
            user = self.db.create_user(
                username=admin_user,
                email=admin_email,
                password_hash=pw_hash,
                role="admin",
                status="active",
            )

            # Admin default workspace is the primary Julius repository root
            self.db.create_workspace(
                user_id=user.id,
                name="Main Repository",
                root_path=self.server_root,
                is_default=True,
            )

            self.db.record_audit(
                event_type="SYSTEM_INITIALIZED",
                user_id=user.id,
                details=f"Seeded initial Super Admin account '{admin_user}'",
            )

    def signup(
        self,
        username: str,
        email: str,
        password: str,
        role: str = "user",
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Tuple[User, str, Session, WorkspaceRecord]:
        """
        Register a new user, allocate an isolated workspace directory, and issue a session.
        """
        username = username.strip()
        email = email.strip().lower()

        # Validation
        if not USERNAME_REGEX.match(username):
            raise ValueError("Username must be 3-32 characters (letters, numbers, underscores, dots, hyphens)")

        if not EMAIL_REGEX.match(email):
            raise ValueError("Please enter a valid email address")

        if len(password) < 6:
            raise ValueError("Password must be at least 6 characters long")

        # Duplicate check
        if self.db.get_user_by_email_or_username(email) or self.db.get_user_by_email_or_username(username):
            raise ValueError("An account with this username or email already exists")

        # Hash password securely
        pw_hash = hash_password(password)

        # Restrict role assignment from public signup to 'user'
        final_role = "user" if role not in ("admin", "developer", "user") else role

        user = self.db.create_user(
            username=username,
            email=email,
            password_hash=pw_hash,
            role=final_role,
            status="active",
        )

        # Allocate user-specific isolated workspace
        ws_dir = Path(self.base_workspaces_dir) / f"user_{user.id}"
        ws_dir.mkdir(parents=True, exist_ok=True)
        (ws_dir / ".julius").mkdir(parents=True, exist_ok=True)

        workspace = self.db.create_workspace(
            user_id=user.id,
            name=f"{username}'s Workspace",
            root_path=str(ws_dir.resolve()),
            is_default=True,
        )

        # Create session
        raw_token, token_hash = generate_session_token()
        session = self.db.create_session(
            user_id=user.id,
            token_hash=token_hash,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        self.db.record_audit(
            event_type="USER_CREATED",
            user_id=user.id,
            resource_type="workspace",
            resource_id=workspace.id,
            details=f"User signed up with role '{final_role}'",
            ip_address=ip_address,
        )

        return user, raw_token, session, workspace

    def login(
        self,
        identifier: str,
        password: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Tuple[User, str, Session, WorkspaceRecord]:
        """
        Authenticate user by username or email, verify password, and issue a session.
        """
        identifier = identifier.strip()
        if not identifier or not password:
            raise ValueError("Username/Email and password are required")

        # Rate limiting check: max 15 attempts per IP in 60 seconds
        rate_key = f"login_attempt:{ip_address or 'global'}"
        allowed, _ = self.db.check_and_increment_rate_limit(rate_key, limit=15, window_seconds=60)
        if not allowed:
            self.db.record_audit(
                event_type="RATE_LIMIT_EXCEEDED",
                details=f"Login rate limit exceeded for identifier: {identifier[:30]}",
                ip_address=ip_address,
            )
            raise ValueError("Too many login attempts. Please try again in a few moments.")

        user = self.db.get_user_by_email_or_username(identifier)
        if not user or not verify_password(password, user.password_hash):
            self.db.record_audit(
                event_type="LOGIN_FAILURE",
                user_id=user.id if user else None,
                details=f"Failed login attempt for identifier: {identifier[:30]}",
                ip_address=ip_address,
            )
            raise ValueError("Invalid email/username or password")

        if user.status != "active":
            self.db.record_audit(
                event_type="LOGIN_BLOCKED",
                user_id=user.id,
                details=f"Login blocked for user status: {user.status}",
                ip_address=ip_address,
            )
            raise ValueError(f"Account is {user.status}. Please contact an administrator.")

        # Re-hash legacy password to Argon2id / PBKDF2 if it used old legacy SHA-256
        if not user.password_hash.startswith(("$argon2", "pbkdf2_sha256$")):
            new_hash = hash_password(password)
            conn = self.db.get_connection()
            with conn:
                conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, user.id))
            user.password_hash = new_hash

        # Get user's default workspace (or allocate one if missing)
        workspace = self.db.get_user_default_workspace(user.id)
        if not workspace:
            ws_path = str(Path(self.base_workspaces_dir) / f"user_{user.id}")
            Path(ws_path).mkdir(parents=True, exist_ok=True)
            workspace = self.db.create_workspace(
                user_id=user.id,
                name=f"{user.username}'s Workspace",
                root_path=ws_path,
                is_default=True,
            )

        raw_token, token_hash = generate_session_token()
        session = self.db.create_session(
            user_id=user.id,
            token_hash=token_hash,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        self.db.record_audit(
            event_type="LOGIN_SUCCESS",
            user_id=user.id,
            details=f"User logged in successfully (role: {user.role})",
            ip_address=ip_address,
        )

        return user, raw_token, session, workspace

    def validate_session(
        self,
        raw_token: str,
    ) -> Optional[Tuple[User, Session, WorkspaceRecord]]:
        """
        Validate a raw session token. Returns (User, Session, WorkspaceRecord) if valid, else None.
        """
        if not raw_token:
            return None
        token_hash = hash_session_token(raw_token)
        session = self.db.get_session_by_token_hash(token_hash)
        if not session or not session.is_active:
            return None

        user = self.db.get_user_by_id(session.user_id)
        if not user or user.status != "active":
            return None

        workspace = self.db.get_user_default_workspace(user.id)
        if not workspace:
            # Recreate default workspace if needed
            ws_path = str(Path(self.base_workspaces_dir) / f"user_{user.id}")
            Path(ws_path).mkdir(parents=True, exist_ok=True)
            workspace = self.db.create_workspace(
                user_id=user.id,
                name=f"{user.username}'s Workspace",
                root_path=ws_path,
                is_default=True,
            )

        return user, session, workspace

    def logout(self, raw_token: str, ip_address: Optional[str] = None) -> bool:
        """Revoke the given session."""
        if not raw_token:
            return False
        token_hash = hash_session_token(raw_token)
        session = self.db.get_session_by_token_hash(token_hash)
        if session:
            self.db.revoke_session(token_hash)
            self.db.record_audit(
                event_type="LOGOUT",
                user_id=session.user_id,
                details="User logged out cleanly",
                ip_address=ip_address,
            )
            return True
        return False
