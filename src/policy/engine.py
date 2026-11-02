"""
Central Deny-by-Default Policy Engine (WS2.1).

The unified gate that EVERY tool path must pass through before execution.
Enforces hard-deny paths, realpath canonicalization, role RBAC, and audit recording.
"""

from __future__ import annotations

import fnmatch
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from src.errors import JUL_POL_HARD_DENY_PATH, JUL_POL_PATH_DENIED, PolicyViolationError
from src.policy.schema import PolicyDecision, PolicySchema, RolePolicy, ToolConstraint

logger = logging.getLogger(__name__)

DEFAULT_POLICY_YAML = """
version: 1
default: deny
hard_deny_paths:
  - "~/.ssh/**"
  - "~/.aws/**"
  - "~/.gnupg/**"
  - "~/.config/gcloud/**"
  - "**/id_rsa*"
  - "**/id_ed25519*"
  - "/etc/shadow"
  - "/etc/passwd"
  - "/etc/sudoers*"
roles:
  viewer:
    allow:
      - "fs.read"
      - "pkb.query"
      - "logs.read"
      - "read_file"
      - "list_dir"
      - "search_files"
      - "search_*"
      - "find_*"
      - "read_symbol"
      - "list_symbols"
  developer:
    allow:
      - "fs.read"
      - "fs.write"
      - "git.*"
      - "test.run"
      - "shell.exec"
      - "read_file"
      - "write_file"
      - "edit_file"
      - "multi_edit"
      - "list_dir"
      - "search_files"
      - "search_*"
      - "find_*"
      - "glob"
      - "run_bash"
      - "run_python"
      - "run_tests"
      - "todo"
      - "checkpoint"
      - "converse"
      - "done"
      - "ask_human"
      - "fetch_url"
      - "music.*"
      - "music_*"
      - "import_spotify_playlist"
      - "music_status"
      - "music_retry"
    require_approval:
      - "host.exec"
      - "fs.write_outside_workspace"
      - "network.egress_unlisted"
  admin:
    allow:
      - "*"
    require_approval:
      - "host.exec"
      - "fs.write_outside_workspace"
      - "network.egress_unlisted"
"""


class PolicyEngine:
    """
    Central Policy Engine enforcing security and permissions across all tools.
    """

    def __init__(
        self,
        workspace: Optional[str] = None,
        policy_path: Optional[str] = None,
        audit_logger: Optional[Any] = None,
    ) -> None:
        self.workspace = Path(workspace or os.getcwd()).resolve()
        self.audit_logger = audit_logger
        self.policy = self._load_policy(policy_path)

    def _load_policy(self, policy_path: Optional[str] = None) -> PolicySchema:
        """Load and strictly validate policy YAML against schema."""
        raw_data = None
        if policy_path and Path(policy_path).exists():
            try:
                with open(policy_path, "r", encoding="utf-8") as f:
                    raw_data = yaml.safe_load(f)
            except Exception as e:
                raise PolicyViolationError(
                    message=f"Failed to parse policy configuration file {policy_path}: {e}",
                    rule="policy_load",
                )
        if not raw_data:
            ws_policy = self.workspace / ".julius" / "policy.yaml"
            if ws_policy.exists():
                try:
                    with open(ws_policy, "r", encoding="utf-8") as f:
                        raw_data = yaml.safe_load(f)
                except Exception:
                    pass

        if not raw_data:
            raw_data = yaml.safe_load(DEFAULT_POLICY_YAML)

        return PolicySchema(**raw_data)

    def is_hard_denied_path(self, target_path: str) -> bool:
        """
        Check if path matches any un-overridable hard-deny path.
        Expands '~' and canonicalizes realpath to prevent symlink traversal.
        """
        try:
            expanded = os.path.expanduser(str(target_path).strip())
            real = os.path.realpath(expanded)
        except Exception:
            return True  # Fail-closed

        home = os.path.realpath(os.path.expanduser("~"))

        for pattern in self.policy.hard_deny_paths:
            # Expand ~ in pattern
            if pattern.startswith("~"):
                resolved_pat = os.path.join(home, pattern[2:])
            else:
                resolved_pat = pattern

            # Wildcard matching against realpath and expanded path
            if fnmatch.fnmatch(real, resolved_pat) or fnmatch.fnmatch(expanded, pattern):
                return True
            if fnmatch.fnmatch(os.path.basename(real), pattern):
                return True

        return False

    def is_path_inside_workspace(self, target_path: str) -> bool:
        """Verify that canonical realpath stays strictly inside workspace."""
        try:
            expanded = os.path.expanduser(str(target_path).strip())
            if not os.path.isabs(expanded):
                target = (self.workspace / expanded).resolve()
            else:
                target = Path(expanded).resolve()
            real = os.path.realpath(target)
            ws_real = os.path.realpath(self.workspace)
            return real == ws_real or real.startswith(ws_real + os.sep)
        except Exception:
            return False

    def evaluate(
        self,
        action: str,
        target_path: Optional[str] = None,
        role: str = "developer",
        actor: str = "agent",
        is_host_action: bool = False,
        details: Optional[Dict[str, Any]] = None,
    ) -> PolicyDecision:
        """
        Central evaluation gate for any tool call.
        Emits PolicyDecision and logs to audit ledger.
        """
        role_key = role.lower()
        role_policy = self.policy.roles.get(role_key)

        # 1. Hard Deny Path Check (Absolute block, overrides everything)
        if target_path and self.is_hard_denied_path(target_path):
            decision = PolicyDecision(
                allowed=False,
                status="denied",
                rule="hard_deny_paths",
                reason=f"Path '{target_path}' matches un-overridable hard-deny security policy.",
                action=action,
                actor=actor,
                path=target_path,
            )
            self._record_audit(decision, details)
            return decision

        # 2. If unknown role, deny by default
        if not role_policy:
            decision = PolicyDecision(
                allowed=False,
                status="denied",
                rule="unknown_role",
                reason=f"Role '{role}' is not configured in policy.",
                action=action,
                actor=actor,
                path=target_path,
            )
            self._record_audit(decision, details)
            return decision

        # 3. Check explicit denies
        for pattern in role_policy.deny:
            if fnmatch.fnmatch(action, pattern):
                decision = PolicyDecision(
                    allowed=False,
                    status="denied",
                    rule=f"role.{role}.deny:{pattern}",
                    reason=f"Action '{action}' is explicitly forbidden for role '{role}'.",
                    action=action,
                    actor=actor,
                    path=target_path,
                )
                self._record_audit(decision, details)
                return decision

        # 4. Check approval requirements
        needs_approval = False
        approval_rule = ""
        for pattern in role_policy.require_approval:
            if fnmatch.fnmatch(action, pattern):
                needs_approval = True
                approval_rule = f"role.{role}.require_approval:{pattern}"
                break

        # Check path-based approval requirements (e.g. write outside workspace)
        if not needs_approval and target_path:
            is_write_action = any(w in action for w in ("write", "edit", "append", "delete", "create"))
            if is_write_action and not self.is_path_inside_workspace(target_path):
                needs_approval = True
                approval_rule = "fs.write_outside_workspace"

        if needs_approval:
            decision = PolicyDecision(
                allowed=False,
                status="needs_approval",
                rule=approval_rule,
                reason=f"Action '{action}' requires interactive human approval.",
                action=action,
                actor=actor,
                path=target_path,
            )
            self._record_audit(decision, details)
            return decision

        # 5. Check role allows
        allowed = False
        matching_rule = ""
        for pattern in role_policy.allow:
            if pattern == "*" or fnmatch.fnmatch(action, pattern):
                allowed = True
                matching_rule = f"role.{role}.allow:{pattern}"
                break

        # If not explicitly allowed, deny by default
        if not allowed:
            decision = PolicyDecision(
                allowed=False,
                status="denied",
                rule="default_deny",
                reason=f"Action '{action}' is not permitted under default deny policy.",
                action=action,
                actor=actor,
                path=target_path,
            )
            self._record_audit(decision, details)
            return decision

        # Action is allowed
        decision = PolicyDecision(
            allowed=True,
            status="allowed",
            rule=matching_rule,
            reason="Action permitted by policy rule.",
            action=action,
            actor=actor,
            path=target_path,
        )
        self._record_audit(decision, details)
        return decision

    def _record_audit(self, decision: PolicyDecision, details: Optional[Dict[str, Any]] = None) -> None:
        """Write policy evaluation result to the audit logger."""
        if self.audit_logger:
            try:
                payload = {
                    "decision": decision.status,
                    "rule": decision.rule,
                    "reason": decision.reason,
                    "path": decision.path,
                    "details": details or {},
                }
                if hasattr(self.audit_logger, "log_policy_event"):
                    self.audit_logger.log_policy_event(
                        actor=decision.actor,
                        action=decision.action,
                        decision=decision.status,
                        rule=decision.rule,
                        payload=payload,
                    )
                elif hasattr(self.audit_logger, "log"):
                    self.audit_logger.log(
                        action=f"policy.{decision.action}",
                        details=payload,
                    )
            except Exception as e:
                logger.debug(f"Audit log error: {e}")

