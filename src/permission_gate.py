"""
Interactive Permission Gate for Julius Agent.

Phase 1.1 — Milestone 1.1: Tool & MCP Permission Gate.

When an agent action requires approval (e.g., bash commands, file writes,
MCP tool calls), this module pauses the worker coroutine using an
asyncio.Event condition variable, emits a structured
``agent.permission_required`` WebSocket event, and waits for the user to
approve or reject.

Auto-grant rules are loaded from ``mcp_allowlist.json`` so that read-only,
idempotent operations bypass the modal entirely.
"""

from __future__ import annotations

import asyncio
import fnmatch
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ── Permission Modes (WS1.1 / WS1.2) ──────────────────────────────────────────

class PermissionMode(str, Enum):
    BYPASS = "bypass"
    ACCEPT = "accept"
    AUTO = "auto"
    NORMAL = "normal"
    EDIT = "edit"
    PLAN = "plan"
    MANUAL = "manual"
    STRICT = "strict"


# ── Danger classification ─────────────────────────────────────────────────────

class DangerLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ActionType(str, Enum):
    BASH_COMMAND = "bash_command"
    MCP_CALL = "mcp_call"
    FILE_WRITE = "file_write"
    FILE_DELETE = "file_delete"
    GIT_OPERATION = "git_operation"


# ── Structured permission request ─────────────────────────────────────────────

@dataclass
class PermissionRequest:
    """Structured payload for ``agent.permission_required`` events."""
    call_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    action_type: ActionType = ActionType.BASH_COMMAND
    danger_level: DangerLevel = DangerLevel.MEDIUM
    payload: str = ""
    description: str = ""
    timeout_seconds: float = 120.0
    timestamp: float = field(default_factory=time.time)

    def to_event(self) -> dict[str, Any]:
        """Serialize to a WebSocket-ready event dict."""
        return {
            "type": "agent.permission_required",
            "call_id": self.call_id,
            "action_type": self.action_type.value,
            "danger_level": self.danger_level.value,
            "payload": self.payload,
            "description": self.description,
            "timeout_seconds": self.timeout_seconds,
            "timestamp": self.timestamp,
        }


class PermissionResponse(str, Enum):
    APPROVE_ONCE = "approve_once"
    APPROVE_SESSION = "approve_session"
    REJECT = "reject"
    TIMEOUT = "timeout"


# ── Danger classifier ─────────────────────────────────────────────────────────

# Patterns that indicate high/critical danger
_CRITICAL_PATTERNS = [
    "rm -rf /", "mkfs", "dd if=", "> /dev/", "chmod 777",
    "curl.*|.*sh", "wget.*|.*sh", "eval(", "exec(",
    "DROP TABLE", "DROP DATABASE", "DELETE FROM",
]

_HIGH_PATTERNS = [
    "rm -rf", "rm -r", "sudo ", "su -", "kill -9", "killall",
    "git push --force", "git reset --hard", "pip install",
    "npm install -g", "docker rm", "docker rmi",
]

_MEDIUM_PATTERNS = [
    "git commit", "git merge", "git checkout", "git stash",
    "mv ", "cp -r", "chmod ", "chown ",
]


def classify_danger(action_type: ActionType, payload: str) -> DangerLevel:
    """Classify the danger level of an action based on its payload."""
    payload_lower = payload.lower().strip()

    if action_type == ActionType.FILE_DELETE:
        return DangerLevel.HIGH

    for pattern in _CRITICAL_PATTERNS:
        if pattern.lower() in payload_lower:
            return DangerLevel.CRITICAL

    for pattern in _HIGH_PATTERNS:
        if pattern.lower() in payload_lower:
            return DangerLevel.HIGH

    for pattern in _MEDIUM_PATTERNS:
        if pattern.lower() in payload_lower:
            return DangerLevel.MEDIUM

    if action_type == ActionType.BASH_COMMAND:
        return DangerLevel.MEDIUM
    if action_type == ActionType.FILE_WRITE:
        return DangerLevel.LOW
    if action_type == ActionType.MCP_CALL:
        return DangerLevel.LOW

    return DangerLevel.LOW


# ── Allowlist loader ──────────────────────────────────────────────────────────

def load_allowlist(allowlist_path: str | Path | None = None) -> list[dict]:
    """Load the MCP auto-approval allowlist from JSON.

    Args:
        allowlist_path: Path to ``mcp_allowlist.json``. If None, attempts to
            find it relative to the project root.

    Returns:
        List of allowlist rule dicts.
    """
    if allowlist_path is None:
        # Try common locations
        candidates = [
            Path(__file__).resolve().parent.parent / "mcp_allowlist.json",
            Path.cwd() / "mcp_allowlist.json",
        ]
        for candidate in candidates:
            if candidate.exists():
                allowlist_path = candidate
                break

    if allowlist_path is None:
        logger.warning("mcp_allowlist.json not found — no auto-grant rules loaded")
        return []

    try:
        data = json.loads(Path(allowlist_path).read_text())
        return data.get("allowlist", [])
    except Exception as exc:
        logger.error("Failed to load mcp_allowlist.json: %s", exc)
        return []


def is_auto_approved(tool_name: str, server_name: str = "", allowlist: list[dict] | None = None) -> bool:
    """Check if a tool call is auto-approved based on the allowlist.

    Args:
        tool_name: The MCP tool name (e.g. ``read_file``).
        server_name: The MCP server name (e.g. ``filesystem``).
        allowlist: Pre-loaded allowlist rules. Loaded from disk if None.

    Returns:
        True if the tool call should be auto-approved.
    """
    if allowlist is None:
        allowlist = load_allowlist()

    for rule in allowlist:
        pattern = rule.get("pattern", "")
        server_pattern = rule.get("server_pattern", "*")

        if fnmatch.fnmatch(tool_name, pattern):
            if server_pattern == "*" or not server_name or fnmatch.fnmatch(server_name, server_pattern):
                return True

    return False


# ── Permission Gate ───────────────────────────────────────────────────────────

class PermissionGate:
    """Async condition-variable gate for interactive tool approval.

    Usage from a worker coroutine::

        gate = PermissionGate(emit_event=ws_send_json)
        response = await gate.request_permission(
            action_type=ActionType.BASH_COMMAND,
            payload="rm -rf ./build",
            description="Delete the build directory",
        )
        if response in (PermissionResponse.APPROVE_ONCE, PermissionResponse.APPROVE_SESSION):
            # proceed with execution
            ...
        else:
            # user rejected or timed out
            ...
    """

    def __init__(
        self,
        emit_event: Optional[Callable] = None,
        allowlist_path: str | Path | None = None,
        default_timeout: float = 120.0,
        mode: PermissionMode = PermissionMode.NORMAL,
    ) -> None:
        self._emit = emit_event
        self._allowlist = load_allowlist(allowlist_path)
        self._default_timeout = default_timeout
        self.mode = mode

        # Session-level auto-approvals (set by "Approve Session")
        self._session_approvals: set[str] = set()

        # Pending requests: call_id → asyncio.Future[PermissionResponse]
        self._pending: dict[str, asyncio.Future[PermissionResponse]] = {}

        logger.info(
            "PermissionGate initialised (mode=%s, allowlist_rules=%d, timeout=%.0fs)",
            self.mode.value,
            len(self._allowlist),
            self._default_timeout,
        )

    def set_mode(self, mode: PermissionMode | str) -> None:
        """Switch active permission mode (bypass, normal, plan, strict)."""
        if isinstance(mode, str):
            try:
                self.mode = PermissionMode(mode.lower().strip())
            except ValueError:
                logger.warning(f"Unknown permission mode '{mode}', defaulting to normal")
                self.mode = PermissionMode.NORMAL
        else:
            self.mode = mode
        logger.info(f"PermissionGate switched to mode: {self.mode.value}")

    async def request_permission(
        self,
        action_type: ActionType,
        payload: str,
        description: str = "",
        timeout: float | None = None,
        server_name: str = "",
        tool_name: str = "",
    ) -> PermissionResponse:
        """Request user permission for an action according to active mode."""
        # ── Mode check: BYPASS / ACCEPT auto-approves all actions without restriction ──
        if self.mode in (PermissionMode.BYPASS, PermissionMode.ACCEPT):
            logger.debug("Accept/Bypass mode: auto-approving %s without restriction", action_type.value)
            return PermissionResponse.APPROVE_ONCE

        # ── Mode check: PLAN blocks all mutating operations ───────────────
        if self.mode == PermissionMode.PLAN:
            if action_type in (ActionType.BASH_COMMAND, ActionType.FILE_WRITE, ActionType.FILE_DELETE, ActionType.GIT_OPERATION):
                logger.warning("Plan mode active: blocked mutating action %s: %s", action_type.value, payload[:60])
                return PermissionResponse.REJECT

        # ── Auto-grant: read-only MCP tools from allowlist ────────────────
        if self.mode not in (PermissionMode.STRICT, PermissionMode.MANUAL) and action_type == ActionType.MCP_CALL and tool_name:
            if is_auto_approved(tool_name, server_name, self._allowlist):
                logger.debug("Auto-approved MCP call: %s (server: %s)", tool_name, server_name)
                return PermissionResponse.APPROVE_ONCE

        # ── Session-level approval shortcut ───────────────────────────────
        approval_key = f"{action_type.value}:{tool_name or payload[:64]}"
        if self.mode not in (PermissionMode.STRICT, PermissionMode.MANUAL) and approval_key in self._session_approvals:
            logger.debug("Session-approved: %s", approval_key)
            return PermissionResponse.APPROVE_SESSION

        # ── Classify danger ───────────────────────────────────────────────
        danger_level = classify_danger(action_type, payload)

        # Auto-grant LOW/MEDIUM danger actions in AUTO/NORMAL mode
        if self.mode in (PermissionMode.AUTO, PermissionMode.NORMAL) and danger_level in (DangerLevel.LOW, DangerLevel.MEDIUM):
            return PermissionResponse.APPROVE_ONCE

        # In EDIT mode, auto-grant file writes/edits within workspace
        if self.mode == PermissionMode.EDIT and action_type == ActionType.FILE_WRITE and danger_level == DangerLevel.LOW:
            return PermissionResponse.APPROVE_ONCE

        # ── Build the permission request ──────────────────────────────────
        request = PermissionRequest(
            action_type=action_type,
            danger_level=danger_level,
            payload=payload,
            description=description or f"Agent wants to execute: {payload[:120]}",
            timeout_seconds=timeout or self._default_timeout,
        )

        # ── Emit event to frontend ────────────────────────────────────────
        event = request.to_event()
        if self._emit:
            try:
                self._emit(event)
            except Exception as exc:
                logger.error("Failed to emit permission event: %s", exc)
                # If we can't reach the user, reject by default
                return PermissionResponse.REJECT

        logger.info(
            "Permission requested [%s] danger=%s: %s",
            request.call_id[:8],
            danger_level.value,
            payload[:80],
        )

        # ── Wait for user response ────────────────────────────────────────
        loop = asyncio.get_running_loop()
        future: asyncio.Future[PermissionResponse] = loop.create_future()
        self._pending[request.call_id] = future

        try:
            response = await asyncio.wait_for(
                future,
                timeout=timeout or self._default_timeout,
            )
        except asyncio.TimeoutError:
            logger.warning("Permission request timed out: %s", request.call_id[:8])
            response = PermissionResponse.TIMEOUT
        finally:
            self._pending.pop(request.call_id, None)

        # ── Handle session approval ───────────────────────────────────────
        if response == PermissionResponse.APPROVE_SESSION:
            self._session_approvals.add(approval_key)
            logger.info("Session approval granted for: %s", approval_key)

        return response

    def resolve_permission(self, call_id: str, response: PermissionResponse | str) -> bool:
        """Resolve a pending permission request.

        Called by the WebSocket handler when the user clicks Approve/Reject.

        Args:
            call_id: The UUID of the permission request.
            response: The user's response.

        Returns:
            True if the request was found and resolved.
        """
        if isinstance(response, str):
            try:
                response = PermissionResponse(response)
            except ValueError:
                logger.error("Invalid permission response: %s", response)
                return False

        future = self._pending.get(call_id)
        if future is None:
            logger.warning("No pending permission request for call_id: %s", call_id[:8])
            return False

        if not future.done():
            future.set_result(response)
            logger.info("Permission resolved [%s]: %s", call_id[:8], response.value)
            return True

        return False

    def clear_session_approvals(self) -> None:
        """Clear all session-level auto-approvals."""
        count = len(self._session_approvals)
        self._session_approvals.clear()
        logger.info("Cleared %d session approvals", count)

    @property
    def pending_count(self) -> int:
        """Number of permission requests currently awaiting user response."""
        return len(self._pending)
