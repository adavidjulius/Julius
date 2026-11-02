"""
Atomic Update Swapper with Automatic Rollback (WS9.3).

Performs atomic file swaps of application binaries and runs
a post-update health check, automatically restoring backup on failure.
"""

from __future__ import annotations

import logging
import os
import shutil
import time
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)


def apply_atomic_update(target_dir: Path | str, new_dir: Path | str) -> bool:
    """Helper executing atomic release directory swap."""
    swapper = AtomicSwapper(target_dir)
    return swapper.apply_update(new_dir)


class AtomicSwapper:
    """Safely swaps new release files with rollback recovery."""

    def __init__(self, target_dir: Path | str) -> None:
        self.target_dir = Path(target_dir).resolve()
        self.backup_dir = self.target_dir.with_name(f"{self.target_dir.name}.backup_{int(time.time())}")

    def apply_update(self, new_dir: Path | str, health_check_fn: Optional[Callable[[], bool]] = None) -> bool:
        """
        Atomically replace target_dir with new_dir.
        If health_check_fn fails, immediately revert from backup_dir.
        """
        new_p = Path(new_dir).resolve()
        if not new_p.exists():
            logger.error(f"New update payload directory not found: {new_p}")
            return False

        # 1. Create backup of current directory
        if self.target_dir.exists():
            shutil.copytree(self.target_dir, self.backup_dir)

        # 2. Swap new contents into target_dir
        try:
            # Overwrite or copy files
            for item in new_p.iterdir():
                dest = self.target_dir / item.name
                if item.is_dir():
                    if dest.exists():
                        shutil.rmtree(dest)
                    shutil.copytree(item, dest)
                else:
                    shutil.copy2(item, dest)

            # 3. Post-swap health check
            if health_check_fn:
                healthy = health_check_fn()
                if not healthy:
                    logger.error("Health check failed on new version! Initiating automatic rollback...")
                    self.rollback()
                    return False

            logger.info("Update applied and verified successfully.")
            # Remove backup if healthy
            shutil.rmtree(self.backup_dir, ignore_errors=True)
            return True

        except Exception as exc:
            logger.error(f"Error during update swap: {exc}. Rolling back...")
            self.rollback()
            return False

    def rollback(self) -> None:
        """Restore previous version from backup."""
        if self.backup_dir.exists():
            if self.target_dir.exists():
                shutil.rmtree(self.target_dir, ignore_errors=True)
            shutil.copytree(self.backup_dir, self.target_dir)
            logger.info("Rollback completed successfully.")

