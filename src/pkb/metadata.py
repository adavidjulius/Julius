"""
Layer 10 — Documentation Index, Layer 11 — Git Intelligence,
Layer 12 — Runtime Knowledge, Layer 13 — Test Knowledge.

Provides non-LLM git provenance lookup (blame, history), documentation indexing,
runtime error mapping, and test-to-symbol coverage associations.
"""

from __future__ import annotations

from contextlib import contextmanager
import re
import sqlite3
import logging
import threading
import subprocess
from pathlib import Path
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple, Any

logger = logging.getLogger(__name__)


@dataclass
class GitCommitInfo:
    """Git commit information for a symbol or file."""
    commit_hash: str
    author: str
    date: str
    message: str


@dataclass
class TestMappingInfo:
    """Mapping between a test function and the target code symbol."""
    test_file: str
    test_symbol: str
    target_symbol: str


class PKBMetadataEngine:
    """
    Manages Documentation indexing, Git intelligence queries,
    Runtime diagnostic logs, and Test coverage mapping.
    """

    def __init__(self, workspace_root: str, db_path: str) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.db_path = Path(db_path)
        self._lock = threading.Lock()
        self._init_tables()

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _init_tables(self) -> None:
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()

            # Layer 10 — Documentation Index
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS doc_index (
                    doc_id TEXT PRIMARY KEY,
                    file_path TEXT NOT NULL,
                    symbol_id TEXT,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL
                )
            """)

            # Layer 12 — Runtime Knowledge
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS runtime_errors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    error_type TEXT NOT NULL,
                    message TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    line_number INTEGER,
                    symbol_id TEXT,
                    timestamp REAL NOT NULL
                )
            """)

            # Layer 13 — Test Knowledge Mapping
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS test_mappings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    test_file TEXT NOT NULL,
                    test_symbol TEXT NOT NULL,
                    target_symbol TEXT NOT NULL
                )
            """)

            conn.commit()

    # ── Layer 11 — Git Intelligence ───────────────────────────────────────────

    def get_git_blame_for_line(self, rel_path: str, line_number: int) -> Optional[GitCommitInfo]:
        """Fetch git blame info for a specific line without calling an LLM."""
        full_path = self.workspace_root / rel_path
        if not full_path.exists():
            return None
        try:
            cmd = [
                "git", "blame", "-L", f"{line_number},{line_number}",
                "--porcelain", str(full_path)
            ]
            res = subprocess.run(
                cmd,
                cwd=str(self.workspace_root),
                capture_output=True,
                text=True,
                timeout=3.0,
            )
            if res.returncode != 0 or not res.stdout:
                return None

            lines = res.stdout.splitlines()
            commit_hash = lines[0].split()[0]
            author = "Unknown"
            date = ""
            summary = ""

            for l in lines:
                if l.startswith("author "):
                    author = l[7:]
                elif l.startswith("author-time "):
                    date = l[12:]
                elif l.startswith("summary "):
                    summary = l[8:]

            return GitCommitInfo(
                commit_hash=commit_hash,
                author=author,
                date=date,
                message=summary,
            )
        except Exception as e:
            logger.debug(f"Git blame failed for {rel_path}:{line_number} — {e}")
            return None

    def get_file_last_modified_author(self, rel_path: str) -> str:
        """Fetch the name of the last developer who modified a file."""
        info = self.get_git_blame_for_line(rel_path, 1)
        return info.author if info else "Unknown"

    # ── Layer 12 — Runtime Knowledge ──────────────────────────────────────────

    def record_runtime_error(self, error_type: str, message: str, file_path: str, line_number: Optional[int] = None, symbol_id: Optional[str] = None) -> None:
        """Record compiler diagnostic, stack trace, or test error."""
        import time
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO runtime_errors (error_type, message, file_path, line_number, symbol_id, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                (error_type, message, file_path, line_number, symbol_id, time.time())
            )
            conn.commit()

    def get_recent_runtime_errors(self, file_path: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
        """Query active runtime errors."""
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            if file_path:
                cursor.execute(
                    "SELECT * FROM runtime_errors WHERE file_path = ? ORDER BY timestamp DESC LIMIT ?",
                    (file_path, limit)
                )
            else:
                cursor.execute(
                    "SELECT * FROM runtime_errors ORDER BY timestamp DESC LIMIT ?",
                    (limit,)
                )
            return [dict(r) for r in cursor.fetchall()]

    # ── Layer 13 — Test Knowledge ─────────────────────────────────────────────

    def register_test_mapping(self, test_file: str, test_symbol: str, target_symbol: str) -> None:
        """Link a unit test function to its covered code symbol."""
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO test_mappings (test_file, test_symbol, target_symbol) VALUES (?, ?, ?)",
                (test_file, test_symbol, target_symbol)
            )
            conn.commit()

    def find_tests_for_symbol(self, target_symbol: str) -> List[str]:
        """Instantly answer: 'What tests cover this method?'"""
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT test_symbol, test_file FROM test_mappings WHERE target_symbol LIKE ?",
                (f"%{target_symbol}%",)
            )
            return [f"{r['test_file']}::{r['test_symbol']}" for r in cursor.fetchall()]
