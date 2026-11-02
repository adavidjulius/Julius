"""
Automated Database Schema Migration Runner with Pre-Migration Backups (WS6.3).

Tracks migration versions in a `schema_version` table, executes forward migrations,
and takes an atomic SQLite backup before applying schema changes.
"""

from __future__ import annotations

import logging
import shutil
import sqlite3
import time
from pathlib import Path
from typing import Callable, Dict, List, Tuple

from src.errors import JUL_DB_MIGRATION_FAILED, DatabaseError

logger = logging.getLogger(__name__)


class MigrationRunner:
    """Manages forward-only schema migrations with automated backup and rollback."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self.migrations: Dict[int, Callable[[sqlite3.Connection], None]] = {}

    def register(self, version: int, fn: Callable[[sqlite3.Connection], None]) -> None:
        """Register a numbered migration function."""
        self.migrations[version] = fn

    def get_current_version(self, conn: sqlite3.Connection) -> int:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at REAL NOT NULL,
                description TEXT
            );
        """)
        conn.commit()
        cursor.execute("SELECT MAX(version) FROM schema_version;")
        row = cursor.fetchone()
        return row[0] or 0

    def backup_database(self) -> Path:
        """Create a point-in-time backup using SQLite Online Backup API."""
        backup_path = self.db_path.with_suffix(f".backup_{int(time.time())}.db")
        source = sqlite3.connect(str(self.db_path))
        dest = sqlite3.connect(str(backup_path))
        with dest:
            source.backup(dest)
        source.close()
        dest.close()
        logger.info(f"Created pre-migration backup at: {backup_path}")
        return backup_path

    def run_pending_migrations(self) -> int:
        """Apply all pending registered migrations in ascending order."""
        if not self.db_path.exists():
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(str(self.db_path))
        current = self.get_current_version(conn)
        pending = [v for v in sorted(self.migrations.keys()) if v > current]

        if not pending:
            conn.close()
            return current

        # Create backup before running migrations
        backup_file = self.backup_database()

        try:
            for v in pending:
                logger.info(f"Applying migration v{v} to {self.db_path}...")
                fn = self.migrations[v]
                fn(conn)
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO schema_version (version, applied_at, description) VALUES (?, ?, ?);",
                    (v, time.time(), getattr(fn, "__doc__", "") or f"Migration {v}"),
                )
                conn.commit()
                current = v

            conn.close()
            return current
        except Exception as exc:
            conn.close()
            logger.error(f"Migration failed at version v{pending[0]}: {exc}. Restoring backup...")
            # Restore backup
            shutil.copy2(backup_file, self.db_path)
            raise DatabaseError(
                code=JUL_DB_MIGRATION_FAILED,
                message=f"Migration failed and was rolled back from backup: {exc}",
                hint="Check database permissions or schema conflict.",
            ) from exc

