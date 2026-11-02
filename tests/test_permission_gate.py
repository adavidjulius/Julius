"""Tests for Phase 1.1: Interactive Tool & MCP Permission Gate."""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import MagicMock

from src.permission_gate import (
    ActionType,
    DangerLevel,
    PermissionGate,
    PermissionRequest,
    PermissionResponse,
    classify_danger,
    is_auto_approved,
)


class TestPermissionGate(unittest.IsolatedAsyncioTestCase):
    """Test suite for PermissionGate condition variable, allowlist, and danger classifier."""

    def test_danger_classification(self):
        """Test danger level categorization for commands and actions."""
        # Critical
        self.assertEqual(classify_danger(ActionType.BASH_COMMAND, "rm -rf /"), DangerLevel.CRITICAL)
        self.assertEqual(classify_danger(ActionType.BASH_COMMAND, "mkfs.ext4 /dev/sda1"), DangerLevel.CRITICAL)
        self.assertEqual(classify_danger(ActionType.BASH_COMMAND, "DROP DATABASE production"), DangerLevel.CRITICAL)

        # High
        self.assertEqual(classify_danger(ActionType.BASH_COMMAND, "rm -rf ./temp"), DangerLevel.HIGH)
        self.assertEqual(classify_danger(ActionType.BASH_COMMAND, "sudo apt update"), DangerLevel.HIGH)
        self.assertEqual(classify_danger(ActionType.FILE_DELETE, "some_file.py"), DangerLevel.HIGH)

        # Medium
        self.assertEqual(classify_danger(ActionType.BASH_COMMAND, "git checkout main"), DangerLevel.MEDIUM)
        self.assertEqual(classify_danger(ActionType.BASH_COMMAND, "mv old.py new.py"), DangerLevel.MEDIUM)

        # Low
        self.assertEqual(classify_danger(ActionType.FILE_WRITE, "content"), DangerLevel.LOW)
        self.assertEqual(classify_danger(ActionType.MCP_CALL, "read_file"), DangerLevel.LOW)

    def test_allowlist_auto_approval(self):
        """Test allowlist pattern matching for read-only MCP tools."""
        allowlist = [
            {"pattern": "read_*", "server_pattern": "*"},
            {"pattern": "list_*", "server_pattern": "filesystem"},
        ]
        self.assertTrue(is_auto_approved("read_file", "filesystem", allowlist))
        self.assertTrue(is_auto_approved("read_symbol", "any_server", allowlist))
        self.assertTrue(is_auto_approved("list_dir", "filesystem", allowlist))
        self.assertFalse(is_auto_approved("list_dir", "other_server", allowlist))
        self.assertFalse(is_auto_approved("delete_file", "filesystem", allowlist))

    async def test_permission_approval_flow(self):
        """Worker pauses until permission is approved."""
        events_emitted = []

        def emit_event(ev):
            events_emitted.append(ev)

        gate = PermissionGate(emit_event=emit_event, default_timeout=5.0)

        # Coroutine requesting permission
        async def worker_coro():
            return await gate.request_permission(
                action_type=ActionType.BASH_COMMAND,
                payload="rm -rf ./dist",
                description="Clean build folder",
            )

        task = asyncio.create_task(worker_coro())
        await asyncio.sleep(0.05)  # Let worker reach gate

        # Verify event emitted
        self.assertEqual(len(events_emitted), 1)
        req_event = events_emitted[0]
        self.assertEqual(req_event["type"], "agent.permission_required")
        self.assertEqual(req_event["danger_level"], "HIGH")
        call_id = req_event["call_id"]

        # Resolve with approve_once
        resolved = gate.resolve_permission(call_id, PermissionResponse.APPROVE_ONCE)
        self.assertTrue(resolved)

        result = await task
        self.assertEqual(result, PermissionResponse.APPROVE_ONCE)

    async def test_permission_rejection_flow(self):
        """Worker unfreezes and receives REJECT when user denies."""
        events = []
        gate = PermissionGate(emit_event=events.append, default_timeout=5.0)

        async def worker_coro():
            return await gate.request_permission(
                action_type=ActionType.BASH_COMMAND,
                payload="rm -rf /var/log",
            )

        task = asyncio.create_task(worker_coro())
        await asyncio.sleep(0.05)

        call_id = events[0]["call_id"]
        gate.resolve_permission(call_id, PermissionResponse.REJECT)

        result = await task
        self.assertEqual(result, PermissionResponse.REJECT)

    async def test_permission_timeout_flow(self):
        """Request returns TIMEOUT when user does not respond within limit."""
        gate = PermissionGate(emit_event=lambda _: None, default_timeout=0.1)

        result = await gate.request_permission(
            action_type=ActionType.BASH_COMMAND,
            payload="rm -rf ./data",
            timeout=0.15,
        )
        self.assertEqual(result, PermissionResponse.TIMEOUT)

    async def test_session_approval_caching(self):
        """Approve Session caches approval for subsequent identical actions."""
        events = []
        gate = PermissionGate(emit_event=events.append, default_timeout=5.0)

        # First request: approve for session
        task1 = asyncio.create_task(gate.request_permission(
            action_type=ActionType.BASH_COMMAND,
            payload="npm run build",
        ))
        await asyncio.sleep(0.05)
        call_id = events[0]["call_id"]
        gate.resolve_permission(call_id, PermissionResponse.APPROVE_SESSION)
        res1 = await task1
        self.assertEqual(res1, PermissionResponse.APPROVE_SESSION)

        # Second request: identical action should be automatically session-approved
        res2 = await gate.request_permission(
            action_type=ActionType.BASH_COMMAND,
            payload="npm run build",
        )
        self.assertEqual(res2, PermissionResponse.APPROVE_SESSION)
        # Should not have emitted a second event
        self.assertEqual(len(events), 1)


if __name__ == "__main__":
    unittest.main()
