"""
SQLite Online Backup & Restore CLI Commands (WS6.3).

Uses SQLite's official online backup API to take consistent, non-blocking
snapshots of memory.db, pkb.db, and audit.db while the daemon is running.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def perform_online_backup(source_db: Path | str, target_backup: Path | str) -> bool:
    """Take a consistent snapshot of source_db using SQLite Online Backup API."""
    src_p = Path(source_db)
    dst_p = Path(target_backup)

    if not src_p.exists():
        print(f"⚠️ Source database does not exist: {src_p}")
        return False

    dst_p.parent.mkdir(parents=True, exist_ok=True)
    src_conn = sqlite3.connect(str(src_p))
    dst_conn = sqlite3.connect(str(dst_p))

    try:
        with dst_conn:
            src_conn.backup(dst_conn)
        print(f"✅ Backup created successfully: {dst_p}")
        return True
    except Exception as e:
        print(f"❌ Backup failed: {e}")
        return False
    finally:
        src_conn.close()
        dst_conn.close()


def perform_online_restore(backup_file: Path | str, target_db: Path | str) -> bool:
    """Restore database from backup file safely."""
    b_p = Path(backup_file)
    dst_p = Path(target_db)

    if not b_p.exists():
        print(f"❌ Backup file not found: {b_p}")
        return False

    dst_p.parent.mkdir(parents=True, exist_ok=True)
    src_conn = sqlite3.connect(str(b_p))
    dst_conn = sqlite3.connect(str(dst_p))

    try:
        with dst_conn:
            src_conn.backup(dst_conn)
        print(f"✅ Database restored successfully to: {dst_p}")
        return True
    except Exception as e:
        print(f"❌ Restore failed: {e}")
        return False
    finally:
        src_conn.close()
        dst_conn.close()

