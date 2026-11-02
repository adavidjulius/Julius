"""
SQLite Production Pragmas & Connection Factory (WS6.3).

Enforces WAL mode, foreign keys, busy timeout, incremental vacuum,
and optimize maintenance routines across all Julius databases.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

PRODUCTION_PRAGMAS = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA busy_timeout = 5000;
PRAGMA foreign_keys = ON;
PRAGMA wal_autocheckpoint = 1000;
PRAGMA journal_size_limit = 67108864;
"""


def apply_production_pragmas(conn: sqlite3.Connection, enable_incremental_vacuum: bool = False) -> None:
    """Apply robust performance and corruption-prevention PRAGMAs to an open SQLite connection."""
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode = WAL;")
    cursor.execute("PRAGMA synchronous = NORMAL;")
    cursor.execute("PRAGMA busy_timeout = 5000;")
    cursor.execute("PRAGMA foreign_keys = ON;")
    cursor.execute("PRAGMA wal_autocheckpoint = 1000;")
    cursor.execute("PRAGMA journal_size_limit = 67108864;")
    if enable_incremental_vacuum:
        try:
            cursor.execute("PRAGMA auto_vacuum = INCREMENTAL;")
        except Exception:
            pass


def open_hardened_sqlite(db_path: Path | str, auto_create_parent: bool = True) -> sqlite3.Connection:
    """Connect to SQLite database with quick_check integrity verification and production PRAGMAs."""
    p = Path(db_path)
    if auto_create_parent:
        p.parent.mkdir(parents=True, exist_ok=True)

    is_new = not p.exists()
    conn = sqlite3.connect(str(p), timeout=10.0)

    # If database already existed, run PRAGMA quick_check
    if not is_new:
        try:
            cur = conn.cursor()
            cur.execute("PRAGMA quick_check;")
            res = cur.fetchone()
            if not res or res[0] != "ok":
                logger.error(f"Integrity check failed for database {p}: {res[0] if res else 'None'}")
        except Exception as e:
            logger.warning(f"Failed running quick_check on {p}: {e}")

    apply_production_pragmas(conn, enable_incremental_vacuum=is_new)
    return conn


def run_idle_maintenance(conn: sqlite3.Connection) -> None:
    """Run idle-time maintenance (incremental vacuum, truncate WAL, and optimize query planner)."""
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA wal_checkpoint(TRUNCATE);")
        cur.execute("PRAGMA incremental_vacuum(50);")
        cur.execute("PRAGMA optimize;")
        conn.commit()
    except Exception as e:
        logger.debug(f"Idle maintenance error: {e}")

