"""
Layer 1 — Repository Monitor & Change Detector.

Monitors new, modified, deleted, and renamed files with debouncing
and queueing. Ensures incremental updates without whole-repo rebuilds.
"""

from __future__ import annotations

import os
import time
import threading
import logging
from pathlib import Path
from typing import Callable, Set, Dict, Optional, List, Tuple

logger = logging.getLogger(__name__)

DEFAULT_IGNORE_PATTERNS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".julius",
    ".julius",
    ".DS_Store",
    "dist",
    "build",
    "target",
    "coverage",
    ".next",
    ".cache",
}

DEFAULT_SUPPORTED_EXTENSIONS = {
    # Code languages
    ".py", ".js", ".jsx", ".ts", ".tsx", ".rs", ".go", ".java",
    ".c", ".h", ".cpp", ".hpp", ".cc", ".cs", ".swift", ".kt", ".kts",
    ".rb", ".php", ".scala",
    # Shell & Build scripts
    ".sh", ".bash", ".zsh", "dockerfile", "makefile", ".cmake",
    # Config & Data formats
    ".json", ".yaml", ".yml", ".toml", ".xml", ".ini", ".env.example",
    # Schemas & Queries
    ".sql", ".graphql", ".proto",
    # Documentation & Markup
    ".md", ".rst", ".html", ".css", ".scss", ".vue", ".svelte",
}


SECRET_FILE_PATTERNS = {
    "id_rsa", "id_ecdsa", "id_ed25519", "id_dsa",
    "credentials", "credentials.json", "service_account.json",
}

SECRET_EXTENSIONS = {
    ".pem", ".key", ".pfx", ".p12", ".pkcs12", ".keystore", ".crt", ".der"
}


class RepositoryWatcher:
    """
    Monitors workspace directory for file changes and triggers callbacks for debounced file events.
    """

    def __init__(
        self,
        workspace_root: str,
        on_change_callback: Callable[[List[Tuple[str, str]]], None],
        poll_interval_sec: float = 1.0,
        debounce_sec: float = 0.5,
        ignore_patterns: Optional[Set[str]] = None,
        supported_extensions: Optional[Set[str]] = None,
    ) -> None:
        self.workspace_root = str(Path(workspace_root).resolve())
        self.on_change_callback = on_change_callback
        self.poll_interval = poll_interval_sec
        self.debounce_sec = debounce_sec
        self.ignore_patterns = ignore_patterns or DEFAULT_IGNORE_PATTERNS
        self.supported_extensions = supported_extensions or DEFAULT_SUPPORTED_EXTENSIONS

        self._snapshot: Dict[str, Tuple[float, int]] = {}  # rel_path -> (mtime, size)
        self._pending_events: Dict[str, Tuple[str, float]] = {}  # rel_path -> (event_type, event_time)
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def is_ignored(self, rel_path: str) -> bool:
        """Check if path matches ignored directory or file patterns."""
        parts = Path(rel_path).parts
        file_name = parts[-1] if parts else ""
        ext = Path(rel_path).suffix.lower()

        # Check secret filename patterns and extensions (T1.4)
        if file_name.startswith(".env") and file_name not in {".env.example", ".env.sample"}:
            return True
        if file_name.lower() in SECRET_FILE_PATTERNS or any(file_name.lower().startswith(p) for p in ("id_rsa", "id_ecdsa", "id_ed25519")):
            return True
        if ext.lower() in SECRET_EXTENSIONS:
            return True

        # Check ignored directory components
        for part in parts[:-1]:
            if part in self.ignore_patterns or (part.startswith(".") and part not in {".julius", ".julius"}):
                return True

        # Check file name ignition
        if file_name in self.ignore_patterns:
            return True
        if file_name.startswith(".") and file_name not in {".env.example"} and ext not in self.supported_extensions:
            return True

        # Allow explicitly permitted template files
        if file_name in {".env.example", ".env.sample"}:
            return False

        # Allow supported extensions or special filenames (dockerfile, makefile)
        if ext and ext in self.supported_extensions:
            return False
        if file_name.lower() in {"dockerfile", "makefile"}:
            return False
            
        return ext not in self.supported_extensions

    def scan_workspace(self) -> Dict[str, Tuple[float, int]]:
        """Walk workspace directory and record (mtime, size) for valid files."""
        current_snapshot: Dict[str, Tuple[float, int]] = {}
        for root, dirs, files in os.walk(self.workspace_root):
            # Filter out ignored directories in-place for performance
            dirs[:] = [
                d for d in dirs
                if d not in self.ignore_patterns and not d.startswith(".")
            ]
            for file_name in files:
                full_path = os.path.join(root, file_name)
                rel_path = os.path.relpath(full_path, self.workspace_root)
                if self.is_ignored(rel_path):
                    continue
                try:
                    stat = os.stat(full_path)
                    current_snapshot[rel_path] = (stat.st_mtime, stat.st_size)
                except OSError:
                    continue
        return current_snapshot

    def start(self) -> None:
        """Start the background monitor thread."""
        with self._lock:
            if self._running:
                return
            self._running = True
            self._snapshot = self.scan_workspace()
            self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self._thread.start()
            logger.info(f"PKB Watcher started for workspace: {self.workspace_root} ({len(self._snapshot)} files initialized)")

    def stop(self) -> None:
        """Stop background monitor thread."""
        with self._lock:
            self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
            logger.info("PKB Watcher stopped.")

    def _monitor_loop(self) -> None:
        """Main loop detecting file additions, modifications, and deletions."""
        while self._running:
            try:
                sleep_start = time.time()
                while self._running and (time.time() - sleep_start < self.poll_interval):
                    time.sleep(0.05)

                if not self._running:
                    break

                current = self.scan_workspace()
                now = time.time()

                with self._lock:
                    # Detect created & modified
                    for path, stat_info in current.items():
                        if path not in self._snapshot:
                            self._pending_events[path] = ("created", now)
                        elif self._snapshot[path] != stat_info:
                            self._pending_events[path] = ("modified", now)

                    # Detect deleted
                    for path in self._snapshot:
                        if path not in current:
                            self._pending_events[path] = ("deleted", now)

                    self._snapshot = current

                    # Flush debounced events
                    ready_events: List[Tuple[str, str]] = []
                    paths_to_remove = []
                    for path, (event_type, event_time) in self._pending_events.items():
                        if now - event_time >= self.debounce_sec:
                            ready_events.append((path, event_type))
                            paths_to_remove.append(path)

                    for path in paths_to_remove:
                        del self._pending_events[path]

                if ready_events:
                    try:
                        self.on_change_callback(ready_events)
                    except Exception as e:
                        logger.error(f"Error in PKB watcher callback: {e}", exc_info=True)

            except Exception as e:
                logger.error(f"Error in PKB watcher loop: {e}")
