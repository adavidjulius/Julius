"""
Workspace Ledger and Undo System.
Manages a SQLite database at `.julius/ledger.db` to record every file mutation,
enabling reverting files to their prior states via `julius undo`.
"""

from __future__ import annotations

import contextlib
import gzip
import logging
import os
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class Ledger:
    """
    Manages local workspace snapshots and reverts.
    """

    def __init__(self, workspace_root: str) -> None:
        self.workspace_root = str(os.path.abspath(workspace_root))
        julius_dir = Path(self.workspace_root) / '.julius'
        legacy_dir = Path(self.workspace_root) / '.julius'
        self.julius_dir = julius_dir if julius_dir.exists() or not legacy_dir.exists() else legacy_dir
        self.julius_dir.mkdir(parents=True, exist_ok=True)
        self.julius_dir = self.julius_dir  # Backward compatibility alias
        self.db_path = self.julius_dir / 'ledger.db'
        
        self._init_db()

    @contextlib.contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        """Initialise database tables."""
        with self._connect() as conn:
            cursor = conn.cursor()
            
            # Table for recording actions (user prompts or agent steps)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS actions (
                    id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    command TEXT NOT NULL,
                    explanation TEXT
                )
            """)
            
            # Table for recording file snapshots before they are modified
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS file_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action_id TEXT NOT NULL,
                    filepath TEXT NOT NULL,
                    original_content BLOB,
                    is_deleted INTEGER NOT NULL,
                    FOREIGN KEY(action_id) REFERENCES actions(id) ON DELETE CASCADE
                )
            """)
            conn.commit()

    def start_action(self, command: str, explanation: str = "") -> str:
        """
        Record the start of a new action/step. Returns a unique action_id.
        """
        action_id = str(uuid.uuid4())
        timestamp = datetime.now().isoformat()
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO actions (id, timestamp, command, explanation) VALUES (?, ?, ?, ?)",
                (action_id, timestamp, command, explanation)
            )
            conn.commit()
        return action_id

    def snapshot_file(self, action_id: str, filepath: str) -> None:
        """
        Create a snapshot of the file before it is written or edited.
        
        If the file exists, compress and store its content.
        If it does not exist, mark it as created (to be deleted on undo).
        """
        abs_path = Path(os.path.abspath(filepath))
        # Ensure path is relative to workspace root for portability in DB
        try:
            rel_path = str(abs_path.relative_to(self.workspace_root))
        except ValueError:
            # Fallback if path is outside workspace root
            rel_path = str(abs_path)

        if abs_path.exists() and abs_path.is_file():
            try:
                with open(abs_path, 'rb') as f:
                    content = f.read()
                compressed = gzip.compress(content)
                is_deleted = 0
            except Exception as e:
                logger.error(f"Ledger: Failed to read/compress file {filepath}: {e}")
                return
        else:
            compressed = None
            is_deleted = 1

        with self._connect() as conn:
            cursor = conn.cursor()
            # Avoid duplicate snapshots of the same file in the same action
            cursor.execute(
                "SELECT id FROM file_snapshots WHERE action_id = ? AND filepath = ?",
                (action_id, rel_path)
            )
            if cursor.fetchone():
                return  # already snapshotted

            cursor.execute(
                "INSERT INTO file_snapshots (action_id, filepath, original_content, is_deleted) VALUES (?, ?, ?, ?)",
                (action_id, rel_path, compressed, is_deleted)
            )
            conn.commit()

    def undo_last_action(self) -> list[str]:
        """
        Revert the workspace to the state before the most recent action.
        
        Returns a list of file paths that were reverted.
        """
        reverted_files = []
        with self._connect() as conn:
            cursor = conn.cursor()
            
            # Find the most recent action
            cursor.execute("SELECT id, command FROM actions ORDER BY timestamp DESC LIMIT 1")
            row = cursor.fetchone()
            if not row:
                logger.info("Ledger: No actions found to undo.")
                return []
                
            action_id, command = row
            logger.info(f"Ledger: Reverting action {action_id} (command: '{command}')")
            
            # Get snapshots for this action
            cursor.execute(
                "SELECT filepath, original_content, is_deleted FROM file_snapshots WHERE action_id = ?",
                (action_id,)
            )
            snapshots = cursor.fetchall()
            
            # Restore snapshots
            for rel_path, compressed, is_deleted in snapshots:
                abs_path = Path(self.workspace_root) / rel_path
                
                if is_deleted:
                    # File was created during the action -> delete it
                    if abs_path.exists():
                        try:
                            abs_path.unlink()
                            reverted_files.append(f"Deleted: {rel_path}")
                        except Exception as e:
                            logger.error(f"Ledger Undo: Failed to delete {rel_path}: {e}")
                else:
                    # File existed -> restore original content
                    try:
                        content = gzip.decompress(compressed)
                        abs_path.parent.mkdir(parents=True, exist_ok=True)
                        with open(abs_path, 'wb') as f:
                            f.write(content)
                        reverted_files.append(f"Restored: {rel_path}")
                    except Exception as e:
                        logger.error(f"Ledger Undo: Failed to restore {rel_path}: {e}")
            
            # Delete the action record (cascades or delete snapshots manually)
            cursor.execute("DELETE FROM file_snapshots WHERE action_id = ?", (action_id,))
            cursor.execute("DELETE FROM actions WHERE id = ?", (action_id,))
            conn.commit()
            
        return reverted_files
