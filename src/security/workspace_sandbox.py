"""
Centralized Workspace Filesystem Sandbox.

Enforces strict path isolation per user and workspace:
- Resolves all paths relative to user's assigned workspace root.
- Rejects path traversal (../, ..\\).
- Canonicalizes paths using realpath and validates commonpath boundary.
- Resolves symlinks to verify target is strictly within the workspace.
- For non-existent target files (new writes), verifies all existing parent ancestors.
- Blocks access to server secrets, application code, databases, credentials,
  and other users' directories.
- Role-aware: admin has repository access; normal users are strictly contained.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any
import logging

logger = logging.getLogger(__name__)

# Files and directories completely forbidden to normal users regardless of location
BLOCKED_PATTERNS = {
    ".env",
    "julius.db",
    "audit.log",
    "secret.key",
    "credentials.enc",
    "id_rsa",
    "id_ed25519",
    "id_ecdsa",
    "id_dsa",
    "authorized_keys",
    "known_hosts",
    "chrome_profile",
    "browser_profiles",
    "shadow",
    "passwd",
    ".ssh",
    ".bashrc",
    ".zshrc",
}


class WorkspaceSandbox:
    """
    Validates and resolves filesystem paths for a specific workspace and role.
    """

    def __init__(self, workspace_root: str, role: str = "user") -> None:
        self.workspace_root = str(Path(os.path.abspath(workspace_root)).resolve())
        self.role = role.lower().strip() if role else "user"
        self._host_access_allowed: bool = False
        self._scoped_grants: dict[str, dict[str, Any]] = {}

    def is_admin(self) -> bool:
        return self.role in ("admin", "super_admin", "owner")

    def is_developer(self) -> bool:
        return self.role in ("developer", "power_user")

    def grant_path_access(
        self,
        path: str,
        mode: str = "read",
        ttl_seconds: float = 60.0,
        once: bool = False,
    ) -> None:
        """
        Grant scoped, time-boxed path access outside the workspace (T1.3).
        Enforces realpath canonicalization and hard-deny list validation.
        """
        if not path or not str(path).strip():
            raise ValueError("Empty path provided for scoped access grant")

        import time
        resolved = os.path.realpath(os.path.expanduser(str(path).strip()))
        resolved_p = Path(resolved)

        if resolved_p.name in BLOCKED_PATTERNS or any(part in BLOCKED_PATTERNS for part in resolved_p.parts):
            raise PermissionError(f"Access Denied: Cannot grant access to hard-denied sensitive path '{path}'")

        self._scoped_grants[resolved] = {
            "path": resolved,
            "mode": mode,
            "expires_at": time.monotonic() + ttl_seconds,
            "once": once,
            "used": False,
        }
        logger.info(f"Granted scoped {mode} access to '{resolved}' for {ttl_seconds}s (once={once})")

    def grant_host_access(self, allowed: bool = True) -> None:
        """Global un-sandboxed access is deprecated in favor of scoped grants."""
        logger.warning("Global grant_host_access is deprecated under Phase 2 security policy.")
        self._host_access_allowed = False

    def resolve_safe_path(self, requested_path: str, allow_create_parent: bool = True) -> str:
        """
        Validate and resolve requested_path safely within self.workspace_root.

        Raises:
            PermissionError: If path attempts to escape the sandbox or access forbidden files.
            ValueError: If path is malformed or invalid.
        """
        if not requested_path or not str(requested_path).strip():
            raise ValueError("Empty path provided")

        cleaned = str(requested_path).strip()

        # Super admin or approved host access has unrestricted access across the Mac
        if self.is_admin() or self._host_access_allowed:
            expanded = os.path.expanduser(cleaned)
            if os.path.isabs(expanded):
                return str(Path(expanded).resolve())
            return str((Path(self.workspace_root) / expanded).resolve())

        # For normal users (and developers in user-workspace mode):
        # 1. Reject paths containing null bytes or suspicious characters
        if "\0" in cleaned or re.search(r'\.{3,}', cleaned):
            raise PermissionError(f"Access Denied: Path '{requested_path}' escapes the workspace blast radius.")

        # 2. Prevent explicit access to sensitive file basenames
        basename = os.path.basename(cleaned)
        if basename in BLOCKED_PATTERNS or any(part in BLOCKED_PATTERNS for part in Path(cleaned).parts):
            raise PermissionError(f"Access Denied: Path '{requested_path}' escapes the workspace blast radius.")

        # 3. Handle absolute vs relative paths
        if os.path.isabs(cleaned):
            # Normal users are NOT permitted to access arbitrary host paths.
            # However, if the client sent an absolute path that is already prefixed with
            # their own workspace root, we permit it subject to canonical check.
            try:
                candidate = str(Path(cleaned).resolve())
            except Exception as e:
                raise PermissionError(f"Access denied: Invalid path format.") from e
        else:
            # Anchor relative to workspace root
            # Normalize redundant separators
            candidate = os.path.normpath(os.path.join(self.workspace_root, cleaned))

        # 4. Canonicalize via realpath to resolve all symlinks
        canonical_workspace = os.path.realpath(self.workspace_root)
        canonical_target = os.path.realpath(candidate)

        # 5. For non-existent files (write/touch), resolve closest existing parent to prevent
        # writing through a symlinked parent directory to escape the sandbox
        check_target = canonical_target
        if not os.path.exists(candidate):
            curr = candidate
            while curr and not os.path.exists(curr) and curr != os.path.dirname(curr):
                curr = os.path.dirname(curr)
            if curr and os.path.exists(curr):
                canonical_parent = os.path.realpath(curr)
                if not self._is_subpath(canonical_parent, canonical_workspace):
                    raise PermissionError("Access denied: Target parent escapes workspace boundary.")

        # 6. Verify target is within canonical workspace root or covered by active scoped grant
        if not self._is_subpath(canonical_target, canonical_workspace):
            import time
            now = time.monotonic()
            granted = False
            for grant_path, grant in list(self._scoped_grants.items()):
                if now > grant["expires_at"] or (grant["once"] and grant["used"]):
                    del self._scoped_grants[grant_path]
                    continue
                if canonical_target == grant_path or canonical_target.startswith(grant_path + os.sep):
                    if grant["once"]:
                        grant["used"] = True
                    granted = True
                    break
            if not granted:
                raise PermissionError("Access denied: Path escapes workspace blast radius.")

        # 7. Check if target or any symlink inside points to a blocked file or server secret
        target_path_obj = Path(canonical_target)
        if target_path_obj.name in BLOCKED_PATTERNS:
            raise PermissionError("Access denied: Restricted file target.")

        # 8. Ensure developers/normal users cannot read server-level files (e.g. .git/config, .env)
        for part in target_path_obj.parts:
            if part in BLOCKED_PATTERNS:
                raise PermissionError("Access denied: Restricted path segment.")

        return canonical_target

    @staticmethod
    def _is_subpath(target: str, root: str) -> bool:
        """Return True if target is strictly within or equal to root."""
        try:
            # os.path.commonpath returns common prefix of paths
            common = os.path.commonpath([target, root])
            return common == root
        except ValueError:
            # On Windows or if drives differ
            return False

    def is_path_safe(self, requested_path: str) -> bool:
        """Return True if requested_path is within sandbox, False otherwise."""
        try:
            self.resolve_safe_path(requested_path)
            return True
        except (PermissionError, ValueError):
            return False
