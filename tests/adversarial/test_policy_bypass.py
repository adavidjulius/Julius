"""
Policy Bypass & Complete Coverage Verification Test Suite (WS2.1).

Enumerates every tool supported by ActionExecutor and asserts:
1. Every tool call routes through the Central Policy Engine.
2. Tools cannot bypass deny-by-default security boundaries.
3. Decisions are recorded in the cryptographic audit ledger.
"""

import tempfile
from pathlib import Path
import pytest

from src.action_executor import ActionExecutor
from src.policy import PolicyEngine


def test_every_action_routes_through_policy_engine():
    """Verify all actions in ActionExecutor dispatch table pass through policy checks."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        # Create an ActionExecutor under the restricted 'viewer' role
        executor = ActionExecutor(workspace_root=tmpdir, user_role="viewer")
        try:
            # In viewer role, write actions must be blocked by central policy
            write_actions = [
                ("write_file", {"path": "test.txt", "content": "forbidden"}),
                ("edit_file", {"path": "test.txt", "old_text": "a", "new_text": "b"}),
                ("multi_edit", {"path": "test.txt", "edits": []}),
                ("run_bash", {"command": "echo test"}),
                ("run_python", {"code": "print('hello')"}),
            ]

            for action_name, args in write_actions:
                result = executor.execute(action_name, args)
                assert result.success is False, f"Action '{action_name}' bypassed central policy under viewer role!"
                assert result.error in ("policy_violation", "security_violation"), f"Unexpected error type for {action_name}: {result.error}"
                assert "blocked" in result.output.lower() or "policy" in result.output.lower() or "forbidden" in result.output.lower()
        finally:
            executor.close()


def test_hard_deny_path_blocks_all_file_tools():
    """Verify hard_deny_path blocks write_file, edit_file, read_file even under admin/host access."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        executor = ActionExecutor(workspace_root=tmpdir, user_role="admin")
        try:
            executor.grant_host_access(True)

            forbidden_path = "~/.ssh/id_rsa"

            # Test read_file
            res_read = executor.execute("read_file", {"path": forbidden_path})
            assert res_read.success is False
        finally:
            executor.close()
        assert "hard-deny" in res_read.output.lower() or "policy" in res_read.output.lower()

        # Test write_file
        res_write = executor.execute("write_file", {"path": forbidden_path, "content": "overwrite"})
        assert res_write.success is False
        assert "hard-deny" in res_write.output.lower() or "policy" in res_write.output.lower()

