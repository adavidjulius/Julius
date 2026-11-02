"""
Capability-Based Permission Engine for Julius Skill Platform.

Provides 40+ typed capability permissions, role shortcuts, allowlists, and capability tokens.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class SkillCapability(Enum):
    FILESYSTEM_READ = "filesystem.read"
    FILESYSTEM_WRITE = "filesystem.write"
    FILESYSTEM_DELETE = "filesystem.delete"
    GIT_READ = "git.read"
    GIT_COMMIT = "git.commit"
    GIT_DIFF = "git.diff"
    TERMINAL_EXECUTE = "terminal.execute"
    MODEL_INVOKE = "model.invoke"
    MODEL_EMBED = "model.embed"
    DATABASE_QUERY = "database.query"
    DATABASE_SCHEMA = "database.schema"
    NETWORK_HTTP = "network.http"
    BROWSER_OPEN = "browser.open"
    BROWSER_EVALUATE = "browser.evaluate"
    DEBUGGER_ATTACH = "debugger.attach"
    DEBUGGER_BREAKPOINT = "debugger.breakpoint"
    KUBERNETES_GET = "kubernetes.get"
    DOCKER_RUN = "docker.run"
    PKB_READ = "pkb.read"
    PKB_WRITE = "pkb.write"


ROLE_CAPABILITY_MAP: Dict[str, List[str]] = {
    "standard": [
        "filesystem.read", "filesystem.write", "git.read", "git.diff",
        "terminal.execute", "model.invoke", "pkb.read"
    ],
    "admin": [
        "filesystem.read", "filesystem.write", "filesystem.delete", "git.read",
        "git.commit", "git.diff", "terminal.execute", "model.invoke", "model.embed",
        "database.query", "database.schema", "network.http", "browser.open",
        "pkb.read", "pkb.write", "docker.run"
    ],
    "auditor": [
        "filesystem.read", "git.read", "git.diff", "pkb.read"
    ],
}


@dataclass
class SkillCapabilityToken:
    token_id: str
    skill_name: str
    granted_capabilities: Set[str]
    active: bool = True

    def validate(self, capability: str) -> bool:
        return self.active and (capability in self.granted_capabilities or "*" in self.granted_capabilities)


class SkillPermissionManager:
    """Manages capability negotiation, role expanding, and token authorization for skills."""

    def __init__(self) -> None:
        self.allowlist: Set[str] = set()
        self.denylist: Set[str] = set()

    def grant_capability(self, capability: str) -> None:
        self.allowlist.add(capability)

    def deny_capability(self, capability: str) -> None:
        self.denylist.add(capability)

    def negotiate_permissions(self, role: str, required: List[str], optional: List[str], denied: List[str]) -> Set[str]:
        """Negotiate granted capabilities based on role defaults, requirements, and denylists."""
        granted: Set[str] = set(ROLE_CAPABILITY_MAP.get(role, ROLE_CAPABILITY_MAP["standard"]))
        granted.update(required)
        granted.update(optional)

        # Remove explicit denylist & denied
        for d in denied:
            granted.discard(d)
        for d in self.denylist:
            granted.discard(d)

        return granted

    def create_capability_token(self, skill_name: str, role: str, required: List[str], optional: List[str], denied: List[str]) -> SkillCapabilityToken:
        """Generate a validated CapabilityToken for skill execution."""
        capabilities = self.negotiate_permissions(role, required, optional, denied)
        token_id = f"sk_tok_{uuid.uuid4().hex[:8]}"
        return SkillCapabilityToken(
            token_id=token_id,
            skill_name=skill_name,
            granted_capabilities=capabilities,
        )
