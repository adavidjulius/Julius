"""
Virtual Git Worktree Transaction Manager for Julius AI Agent.

Manages ephemeral worktree directories in `.julius/worktrees/` for executing
agent tasks transactionally with atomic commit and rollback capabilities.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class WorktreeTransaction:
    txn_id: str
    worktree_path: Path
    base_branch: str
    target_branch: str
    active: bool = True


class VirtualWorktreeManager:
    """Manages ephemeral Git worktrees for safe, sandboxed file modifications."""

    def __init__(self, workspace_root: str = ".") -> None:
        self.workspace_root = Path(workspace_root).resolve()
        julius_worktrees = self.workspace_root / ".julius" / "worktrees"
        legacy_worktrees = self.workspace_root / ".julius" / "worktrees"
        self.worktree_dir = julius_worktrees if julius_worktrees.exists() or not legacy_worktrees.exists() else legacy_worktrees
        self.worktree_dir.mkdir(parents=True, exist_ok=True)

    def is_git_repo(self) -> bool:
        return (self.workspace_root / ".git").exists()

    def create_transaction(self, base_branch: str = "main") -> WorktreeTransaction:
        """Create an ephemeral worktree directory for isolated execution."""
        txn_id = f"txn_{uuid.uuid4().hex[:8]}"
        worktree_path = self.worktree_dir / txn_id
        target_branch = f"julius-txn-{txn_id}"

        if self.is_git_repo():
            try:
                subprocess.run(
                    ["git", "worktree", "add", "-b", target_branch, str(worktree_path), base_branch],
                    cwd=self.workspace_root,
                    capture_output=True,
                    check=True,
                )
                logger.info(f"Created Git worktree at {worktree_path}")
            except Exception as exc:
                logger.warning(f"Git worktree add failed, creating directory copy fallback: {exc}")
                shutil.copytree(self.workspace_root, worktree_path, ignore=shutil.ignore_patterns(".git", ".julius", ".julius"))
        else:
            shutil.copytree(self.workspace_root, worktree_path, ignore=shutil.ignore_patterns(".julius", ".julius"))

        return WorktreeTransaction(
            txn_id=txn_id,
            worktree_path=worktree_path,
            base_branch=base_branch,
            target_branch=target_branch,
        )

    def commit_transaction(self, txn: WorktreeTransaction, commit_message: str = "Julius Agent Transaction Commit") -> bool:
        """Commit transaction changes back to workspace."""
        if not txn.active or not txn.worktree_path.exists():
            return False

        try:
            if self.is_git_repo():
                subprocess.run(["git", "add", "-A"], cwd=txn.worktree_path, capture_output=True)
                subprocess.run(["git", "commit", "-m", commit_message], cwd=txn.worktree_path, capture_output=True)
                # Merge target branch to main branch
                subprocess.run(["git", "merge", txn.target_branch], cwd=self.workspace_root, capture_output=True)
            else:
                # Copy modified files back
                for root, _, files in os.walk(txn.worktree_path):
                    rel_dir = os.path.relpath(root, txn.worktree_path)
                    dest_dir = self.workspace_root / rel_dir
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    for file in files:
                        shutil.copy2(Path(root) / file, dest_dir / file)

            self.rollback_transaction(txn)
            return True
        except Exception as exc:
            logger.error(f"Error committing worktree transaction {txn.txn_id}: {exc}")
            self.rollback_transaction(txn)
            return False

    def rollback_transaction(self, txn: WorktreeTransaction) -> None:
        """Discard worktree changes and cleanup ephemeral files."""
        if not txn.worktree_path.exists():
            return

        try:
            if self.is_git_repo():
                subprocess.run(["git", "worktree", "remove", "--force", str(txn.worktree_path)], cwd=self.workspace_root, capture_output=True)
                subprocess.run(["git", "branch", "-D", txn.target_branch], cwd=self.workspace_root, capture_output=True)
            if txn.worktree_path.exists():
                shutil.rmtree(txn.worktree_path, ignore_errors=True)
            txn.active = False
            logger.info(f"Rolled back worktree transaction {txn.txn_id}")
        except Exception as exc:
            logger.error(f"Error rolling back worktree transaction {txn.txn_id}: {exc}")
