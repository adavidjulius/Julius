"""
Central Policy Schema Definition (WS2.1).

Defines strongly-typed Pydantic schemas for the deny-by-default policy engine,
hard-deny paths, roles, constraints, and policy decision records.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class ToolConstraint(BaseModel):
    """Execution constraints applied to a specific tool or action."""
    paths: Optional[List[str]] = None
    deny_paths: Optional[List[str]] = None
    sandbox: Optional[Literal["read_only", "workspace", "container", "host"]] = None
    network: Optional[bool] = None
    timeout_s: Optional[int] = None
    require_approval: Optional[bool] = None


class RolePolicy(BaseModel):
    """Permissions and constraints associated with a specific user role."""
    allow: List[str] = Field(default_factory=list, description="Permitted action patterns (e.g. fs.read, git.*)")
    deny: List[str] = Field(default_factory=list, description="Explicitly forbidden action patterns")
    require_approval: List[str] = Field(default_factory=list, description="Actions requiring interactive approval")
    constraints: Dict[str, ToolConstraint] = Field(default_factory=dict)


class PolicySchema(BaseModel):
    """Complete root policy document schema."""
    version: int = 1
    default: Literal["deny", "allow"] = "deny"
    hard_deny_paths: List[str] = Field(
        default_factory=lambda: [
            "~/.ssh/**",
            "~/.aws/**",
            "~/.gnupg/**",
            "~/.config/gcloud/**",
            "**/id_rsa*",
            "**/id_ed25519*",
            "/etc/shadow",
            "/etc/passwd",
            "/etc/sudoers*",
        ],
        description="Paths that can NEVER be accessed under any circumstances or approvals",
    )
    roles: Dict[str, RolePolicy] = Field(default_factory=dict)


class PolicyDecision(BaseModel):
    """Decision emitted by the Central Policy Engine for every tool invocation."""
    allowed: bool
    status: Literal["allowed", "denied", "needs_approval"]
    rule: str
    reason: str
    action: str
    actor: str = "agent"
    path: Optional[str] = None

