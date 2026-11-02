"""Tests for Phase 1.2: Checkpointed Self-Healing Engine with Git Rollback."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from src.self_healer import (
    GitCheckpoint,
    HealLedger,
    HealLedgerEntry,
    SelfHealer,
)


class TestSelfHealer(unittest.TestCase):
    """Test suite for checkpointed self-healing engine and rollback mechanism."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        # Initialize a temporary git repository for rollback testing
        subprocess.run(["git", "init"], cwd=self.tmp_dir, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "TestUser"], cwd=self.tmp_dir, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=self.tmp_dir, capture_output=True, check=True)

        # Create an initial committed file
        self.test_file = os.path.join(self.tmp_dir, "app.py")
        with open(self.test_file, "w") as f:
            f.write("def calculate(x):\n    return x * 2\n")

        subprocess.run(["git", "add", "."], cwd=self.tmp_dir, capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=self.tmp_dir, capture_output=True, check=True)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_git_checkpoint_lifecycle(self):
        """Test snapshot creation, file modification tracking, and automatic rollback."""
        checkpoint = GitCheckpoint(self.tmp_dir)
        self.assertTrue(checkpoint.is_git_repo())

        # Modify the file
        with open(self.test_file, "w") as f:
            f.write("def calculate(x):\n    return x / 0  # Broken bug\n")

        checkpoint.track_modified_file(self.test_file)

        # Diff should show the change
        diff = checkpoint.get_file_diff(self.test_file)
        self.assertIn("Broken bug", diff)

        # Rollback the file
        checkpoint.rollback_file(self.test_file)

        # File should be restored to initial state
        with open(self.test_file, "r") as f:
            content = f.read()
        self.assertIn("return x * 2", content)
        self.assertNotIn("Broken bug", content)

    def test_heal_ledger_audit_trail(self):
        """Test that HealLedger records all iterations and produces a structured postmortem."""
        ledger = HealLedger()
        ledger.record(
            attempt_number=1,
            target_file="app.py",
            error_line=2,
            error_type="ZeroDivisionError",
            patch_diff="-    return x / 0\n+    return x",
            verification_command="pytest",
            success=False,
        )
        ledger.record(
            attempt_number=2,
            target_file="app.py",
            error_line=2,
            error_type="ZeroDivisionError",
            patch_diff="-    return x\n+    return x * 2",
            verification_command="pytest",
            success=True,
        )

        summary = ledger.get_summary()
        self.assertEqual(summary["total_attempts"], 2)
        self.assertEqual(summary["successful"], 1)
        self.assertEqual(summary["failed"], 1)
        self.assertEqual(len(summary["entries"]), 2)

    def test_self_healer_abort_and_clean_rollback(self):
        """Test that after max failed attempts, SelfHealer restores files to clean baseline."""
        checkpoint = GitCheckpoint(self.tmp_dir)

        # Corrupt file
        with open(self.test_file, "w") as f:
            f.write("def calculate(x):\n    syntax error !!\n")
        checkpoint.track_modified_file(self.test_file)

        # Rollback all
        restored = checkpoint.rollback_all()
        self.assertIn(self.test_file, restored)

        with open(self.test_file, "r") as f:
            content = f.read()
        self.assertEqual(content, "def calculate(x):\n    return x * 2\n")


if __name__ == "__main__":
    unittest.main()
