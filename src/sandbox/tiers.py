"""
Sandbox Tiers & Scoped Path Grants (WS2.2).

Implements Tier 0 (Read-only), Tier 1 (Workspace - Default),
Tier 2 (Container), and Tier 3 (Host with per-action TTL grants).
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Literal, Optional, Set

from src.errors import JUL_POL_PATH_DENIED, PolicyViolationError
from src.security.workspace_sandbox import BLOCKED_PATTERNS

logger = logging.getLogger(__name__)


@dataclass
class ScopedPathGrant:
    """Time-boxed, single-use or TTL-bounded scoped path permission."""
    path: str
    mode: Literal["read", "write"]
    expires_at: float
    once: bool = True
    used: bool = False


class SandboxTierManager:
    """Manages execution isolation tiers and ephemeral path grants."""

    def __init__(self, workspace: str, tier: Literal[0, 1, 2, 3] = 1) -> None:
        self.workspace = str(Path(workspace).resolve())
        self.tier = tier
        self._path_grants: Dict[str, ScopedPathGrant] = {}

    def set_tier(self, tier: Literal[0, 1, 2, 3]) -> None:
        self.tier = tier

    def grant_path_access(
        self,
        path: str,
        mode: Literal["read", "write"] = "read",
        ttl_seconds: float = 60.0,
        once: bool = True,
    ) -> None:
        """
        Grant time-boxed access to a path outside the workspace.
        Canonicalizes realpath and checks for symlink escapes and hard-denied files.
        """
        if not path or not str(path).strip():
            raise PolicyViolationError("Empty path provided for scoped access grant.")

        resolved = os.path.realpath(os.path.expanduser(str(path).strip()))
        resolved_p = Path(resolved)

        if resolved_p.name in BLOCKED_PATTERNS or any(part in BLOCKED_PATTERNS for part in resolved_p.parts):
            raise PolicyViolationError(f"Cannot grant scoped access to hard-denied sensitive path '{path}'")

        grant = ScopedPathGrant(
            path=resolved,
            mode=mode,
            expires_at=time.monotonic() + ttl_seconds,
            once=once,
        )
        self._path_grants[resolved] = grant
        logger.info(f"Granted scoped {mode} access to '{resolved}' for {ttl_seconds}s (once={once})")

    def check_path_access(self, target_path: str, mode: Literal["read", "write"] = "read") -> bool:
        """
        Validate path access against tier restrictions, TOCTOU, and ephemeral grants.
        """
        if self.tier == 0:
            # Tier 0 is strictly read-only
            if mode == "write":
                return False

        # Canonicalize realpath
        try:
            expanded = os.path.expanduser(str(target_path).strip())
            if not os.path.isabs(expanded):
                target = str((Path(self.workspace) / expanded).resolve())
            else:
                target = str(Path(expanded).resolve())
            real_target = os.path.realpath(target)
            real_ws = os.path.realpath(self.workspace)
        except Exception:
            return False  # Fail-closed

        # If inside workspace, allowed in Tier 1, 2, 3
        if real_target == real_ws or real_target.startswith(real_ws + os.sep):
            # Check for git hooks write block
            if mode == "write" and ".git/hooks" in real_target:
                return False
            return True

        # If outside workspace:
        # Check active ephemeral grants
        now = time.monotonic()
        for grant_path, grant in list(self._path_grants.items()):
            if now > grant.expires_at or (grant.once and grant.used):
                del self._path_grants[grant_path]
                continue

            if real_target == grant_path or real_target.startswith(grant_path + os.sep):
                if mode == "write" and grant.mode == "read":
                    continue
                target_p = Path(real_target)
                if target_p.name in BLOCKED_PATTERNS or any(part in BLOCKED_PATTERNS for part in target_p.parts):
                    return False
                if grant.once:
                    grant.used = True
                return True

        # Tier 3 (Host) allows reads outside workspace, but writes outside require explicit grant
        if self.tier == 3 and mode == "read":
            return True

        return False

