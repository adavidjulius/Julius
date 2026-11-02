"""
SQLite persistence layer for all memory tiers.
Single database at `.julius/memory.db` with tables for:
- agent_state
- task_memory
- conversation_turns, conversation_summaries
- episodic_notes
- semantic_facts
- execution_graph_nodes, execution_graph_edges
- working_memory_snapshots

Reinforced with:
- Connection pooling (reuse connections within a transaction scope)
- Retry logic for SQLITE_BUSY
- WAL auto-checkpoint management
- Specific exception handling (no bare except: pass)
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Maximum retries for SQLITE_BUSY errors
_MAX_BUSY_RETRIES = 3
_BUSY_RETRY_DELAY_SECS = 0.05  # 50ms base delay

# WAL checkpoint threshold
_WAL_CHECKPOINT_INTERVAL = 1000


class StorageError(Exception):
    """Base exception for storage layer errors."""
    pass


class ConnectionPool:
    """
    Thread-local connection pool for SQLite.
    Reuses connections within the same thread to avoid connection churn.
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._local = threading.local()
        self._lock = threading.Lock()
        self._write_count = 0

    def get_connection(self) -> sqlite3.Connection:
        """Get a thread-local connection, creating one if needed."""
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            conn = sqlite3.connect(self._db_path, timeout=5.0)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA synchronous=NORMAL")
            self._local.conn = conn
        return self._local.conn

    def close_thread_connection(self) -> None:
        """Close the thread-local connection if open."""
        if hasattr(self._local, 'conn') and self._local.conn is not None:
            try:
                self._local.conn.close()
            except Exception as e:
                logger.debug("ConnectionPool: Error closing connection: %s", e)
            self._local.conn = None

    def increment_write_count(self) -> None:
        """Increment write counter and checkpoint WAL if threshold reached."""
        self._write_count += 1
        if self._write_count >= _WAL_CHECKPOINT_INTERVAL:
            self._checkpoint_wal()

    def _checkpoint_wal(self) -> None:
        """Run WAL checkpoint to keep journal size bounded."""
        try:
            conn = self.get_connection()
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            self._write_count = 0
            logger.debug("ConnectionPool: WAL checkpoint completed")
        except Exception as e:
            logger.warning("ConnectionPool: WAL checkpoint failed: %s", e)

    def close_all(self) -> None:
        """Close all connections (for cleanup)."""
        # Since connections are thread-local, we can only close the current thread's connection
        self.close_thread_connection()


def _with_retry(func):
    """Decorator: retry on SQLITE_BUSY with exponential backoff."""
    def wrapper(self, *args, **kwargs):
        last_error = None
        for attempt in range(_MAX_BUSY_RETRIES):
            try:
                result = func(self, *args, **kwargs)
                # If we got here without exception, increment write count for write operations
                if func.__name__.startswith('save_') or func.__name__.startswith('delete_') or func.__name__ == 'clear_all':
                    try:
                        if hasattr(self, '_pool') and self._pool is not None:
                            self._pool.increment_write_count()
                    except Exception:
                        pass
                return result
            except sqlite3.OperationalError as e:
                if 'database is locked' in str(e) or 'SQLITE_BUSY' in str(e):
                    last_error = e
                    delay = _BUSY_RETRY_DELAY_SECS * (2 ** attempt)
                    logger.warning(
                        "Storage: SQLITE_BUSY on %s (attempt %d/%d), retrying in %.0fms",
                        func.__name__, attempt + 1, _MAX_BUSY_RETRIES, delay * 1000
                    )
                    time.sleep(delay)
                else:
                    raise
            except Exception as e:
                logger.error(
                    "Storage: Unexpected error in %s: %s\n%s",
                    func.__name__, e, traceback.format_exc(),
                )
                raise
        # All retries exhausted
        raise StorageError(
            f"Storage operation '{func.__name__}' failed after {_MAX_BUSY_RETRIES} retries: {last_error}"
        ) from last_error
    return wrapper


class MemoryStorage:
    """Central SQLite persistence for all memory tiers."""

    def __init__(self, workspace_path: str = ".") -> None:
        import hashlib
        self.workspace_path = Path(workspace_path).resolve()
        # Compute project ID as a hash of the workspace path
        self.project_id = hashlib.sha256(str(self.workspace_path).encode('utf-8')).hexdigest()[:16]
        julius_dir = self.workspace_path / ".julius"
        legacy_dir = self.workspace_path / ".julius"
        self.julius_dir = julius_dir if julius_dir.exists() or not legacy_dir.exists() else legacy_dir
        self.julius_dir.mkdir(parents=True, exist_ok=True)
        self.julius_dir = self.julius_dir  # Backward compatibility alias
        self.db_path = self.julius_dir / "memory.db"
        self._pool = ConnectionPool(str(self.db_path))
        self._lock = threading.Lock()
        self._init_db()
        self._migrate_db()

    def _migrate_db(self) -> None:
        """Apply schema migrations, adding project_id column to task_memory if missing."""
        try:
            conn = self._pool.get_connection()
            with self._lock:
                cursor = conn.cursor()
                cursor.execute("PRAGMA table_info(task_memory)")
                columns = [col[1] for col in cursor.fetchall()]
                if 'project_id' not in columns:
                    logger.info("Storage Migration: Adding 'project_id' column to task_memory")
                    cursor.execute("ALTER TABLE task_memory ADD COLUMN project_id TEXT NOT NULL DEFAULT 'default_project'")
                    conn.commit()
        except Exception as e:
            logger.error("Storage: Migration failed: %s", e)

    def _init_db(self) -> None:
        """Create all memory tables if they don't exist."""
        try:
            conn = self._pool.get_connection()
            with self._lock:
                cursor = conn.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA foreign_keys=ON")

                # Agent state (single row)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS agent_state (
                        id INTEGER PRIMARY KEY CHECK (id = 1),
                        state_json TEXT NOT NULL,
                        updated_at REAL NOT NULL
                    )
                """)

                # Task memory (scoped by project_id)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS task_memory (
                        task_id TEXT PRIMARY KEY,
                        summary TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'in_progress',
                        files_modified TEXT NOT NULL DEFAULT '[]',
                        functions_changed TEXT NOT NULL DEFAULT '[]',
                        known_issues TEXT NOT NULL DEFAULT '[]',
                        parent_task_id TEXT,
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL,
                        project_id TEXT NOT NULL DEFAULT 'default',
                        FOREIGN KEY (parent_task_id) REFERENCES task_memory(task_id)
                    )
                """)

                # Conversation turns
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS conversation_turns (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        task_id TEXT,
                        role TEXT NOT NULL,
                        content TEXT NOT NULL,
                        tool_calls TEXT DEFAULT '[]',
                        timestamp REAL NOT NULL,
                        FOREIGN KEY (task_id) REFERENCES task_memory(task_id)
                    )
                """)

                # Conversation summaries
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS conversation_summaries (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        task_id TEXT NOT NULL,
                        summary TEXT NOT NULL,
                        turn_count INTEGER NOT NULL,
                        created_at REAL NOT NULL,
                        FOREIGN KEY (task_id) REFERENCES task_memory(task_id)
                    )
                """)

                # Episodic notes (day-level)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS episodic_notes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        date TEXT NOT NULL,
                        summary TEXT NOT NULL,
                        task_ids TEXT NOT NULL DEFAULT '[]',
                        created_at REAL NOT NULL,
                        UNIQUE(date)
                    )
                """)

                # Semantic facts
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS semantic_facts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        fact_key TEXT NOT NULL,
                        fact_value TEXT NOT NULL,
                        category TEXT DEFAULT 'general',
                        confidence REAL DEFAULT 1.0,
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL,
                        UNIQUE(fact_key)
                    )
                """)

                # Execution graph nodes
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS execution_graph_nodes (
                        node_id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        category TEXT DEFAULT 'general',
                        metadata_json TEXT DEFAULT '{}',
                        created_at REAL NOT NULL
                    )
                """)

                # Execution graph edges
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS execution_graph_edges (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        source_node_id TEXT NOT NULL,
                        target_node_id TEXT NOT NULL,
                        task_id TEXT,
                        relationship TEXT DEFAULT 'depends_on',
                        created_at REAL NOT NULL,
                        FOREIGN KEY (source_node_id) REFERENCES execution_graph_nodes(node_id),
                        FOREIGN KEY (target_node_id) REFERENCES execution_graph_nodes(node_id),
                        FOREIGN KEY (task_id) REFERENCES task_memory(task_id)
                    )
                """)

                # Working memory snapshots
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS working_memory_snapshots (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        task_id TEXT NOT NULL,
                        snapshot_json TEXT NOT NULL,
                        created_at REAL NOT NULL,
                        FOREIGN KEY (task_id) REFERENCES task_memory(task_id)
                    )
                """)

                # Research experiments memory (Stage 2)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS research_experiments (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        experiment_id TEXT UNIQUE NOT NULL,
                        hypothesis TEXT NOT NULL,
                        mechanism_description TEXT NOT NULL,
                        nearest_known_architecture TEXT NOT NULL,
                        implementation_summary TEXT NOT NULL,
                        result_metrics TEXT NOT NULL DEFAULT '{}',
                        baseline_comparison_metrics TEXT NOT NULL DEFAULT '{}',
                        outcome TEXT NOT NULL DEFAULT 'inconclusive',
                        failure_reason TEXT DEFAULT '',
                        timestamp REAL NOT NULL,
                        project_id TEXT NOT NULL DEFAULT 'default'
                    )
                """)

                conn.commit()
        except Exception as e:
            logger.error("Storage: Failed to initialize database: %s\n%s", e, traceback.format_exc())
            raise StorageError(f"Failed to initialize memory database: {e}") from e

    # ── Agent State ────────────────────────────────────────────────

    @_with_retry
    def save_agent_state(self, state: Dict[str, Any]) -> None:
        conn = self._pool.get_connection()
        conn.execute(
            """INSERT OR REPLACE INTO agent_state (id, state_json, updated_at)
               VALUES (1, ?, ?)""",
            (json.dumps(state), time.time()),
        )
        conn.commit()

    @_with_retry
    def load_agent_state(self) -> Optional[Dict[str, Any]]:
        conn = self._pool.get_connection()
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT state_json FROM agent_state WHERE id = 1"
        ).fetchone()
        if row:
            return json.loads(row[0])
        return None

    # ── Task Memory ────────────────────────────────────────────────

    @_with_retry
    def save_task(self, task_id: str, summary: str, status: str = "in_progress",
                  files_modified: Optional[List[str]] = None,
                  functions_changed: Optional[List[str]] = None,
                  known_issues: Optional[List[str]] = None,
                  parent_task_id: Optional[str] = None,
                  created_at: Optional[float] = None,
                  updated_at: Optional[float] = None) -> None:
        now = time.time()
        conn = self._pool.get_connection()
        conn.execute(
            """INSERT OR REPLACE INTO task_memory
               (task_id, summary, status, files_modified, functions_changed,
                known_issues, parent_task_id, created_at, updated_at, project_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (task_id, summary, status, json.dumps(files_modified or []),
             json.dumps(functions_changed or []),
             json.dumps(known_issues or []), parent_task_id,
             created_at or now, updated_at or now, self.project_id),
        )
        conn.commit()

    @_with_retry
    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        conn = self._pool.get_connection()
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM task_memory WHERE task_id = ? AND project_id = ?", (task_id, self.project_id)
        ).fetchone()
        if row:
            result = dict(row)
            result["files_modified"] = json.loads(result["files_modified"])
            result["functions_changed"] = json.loads(result["functions_changed"])
            result["known_issues"] = json.loads(result["known_issues"])
            return result
        return None

    @_with_retry
    def get_latest_task(self) -> Optional[Dict[str, Any]]:
        conn = self._pool.get_connection()
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM task_memory WHERE project_id = ? ORDER BY updated_at DESC LIMIT 1", (self.project_id,)
        ).fetchone()
        if row:
            result = dict(row)
            result["files_modified"] = json.loads(result["files_modified"])
            result["functions_changed"] = json.loads(result["functions_changed"])
            result["known_issues"] = json.loads(result["known_issues"])
            return result
        return None

    @_with_retry
    def get_last_completed_task(self) -> Optional[Dict[str, Any]]:
        conn = self._pool.get_connection()
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM task_memory WHERE status = 'completed' AND project_id = ? ORDER BY updated_at DESC LIMIT 1", (self.project_id,)
        ).fetchone()
        if row:
            result = dict(row)
            result["files_modified"] = json.loads(result["files_modified"])
            result["functions_changed"] = json.loads(result["functions_changed"])
            result["known_issues"] = json.loads(result["known_issues"])
            return result
        return None

    @_with_retry
    def list_tasks(self, limit: int = 20, offset: int = 0) -> List[Dict[str, Any]]:
        conn = self._pool.get_connection()
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM task_memory WHERE project_id = ? ORDER BY updated_at DESC LIMIT ? OFFSET ?",
            (self.project_id, limit, offset),
        ).fetchall()
        results = []
        for row in rows:
            result = dict(row)
            result["files_modified"] = json.loads(result["files_modified"])
            result["functions_changed"] = json.loads(result["functions_changed"])
            result["known_issues"] = json.loads(result["known_issues"])
            results.append(result)
        return results

    @_with_retry
    def search_tasks(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        conn = self._pool.get_connection()
        conn.row_factory = sqlite3.Row
        like = f"%{query}%"
        rows = conn.execute(
            """SELECT * FROM task_memory
               WHERE project_id = ? AND (summary LIKE ? OR files_modified LIKE ?)
               ORDER BY updated_at DESC LIMIT ?""",
            (self.project_id, like, like, limit),
        ).fetchall()
        results = []
        for row in rows:
            result = dict(row)
            result["files_modified"] = json.loads(result["files_modified"])
            result["functions_changed"] = json.loads(result["functions_changed"])
            result["known_issues"] = json.loads(result["known_issues"])
            results.append(result)
        return results

    # ── Conversation Turns ─────────────────────────────────────────

    @_with_retry
    def save_turn(self, task_id: Optional[str], role: str, content: str,
                  tool_calls: Optional[List[Dict[str, Any]]] = None) -> int:
        conn = self._pool.get_connection()
        cursor = conn.execute(
            """INSERT INTO conversation_turns (task_id, role, content, tool_calls, timestamp)
               VALUES (?, ?, ?, ?, ?)""",
            (task_id, role, content, json.dumps(tool_calls or []), time.time()),
        )
        conn.commit()
        return cursor.lastrowid

    @_with_retry
    def get_turns(self, task_id: Optional[str] = None, limit: int = 100,
                  offset: int = 0) -> List[Dict[str, Any]]:
        conn = self._pool.get_connection()
        conn.row_factory = sqlite3.Row
        if task_id:
            rows = conn.execute(
                """SELECT * FROM conversation_turns WHERE task_id = ?
                   ORDER BY timestamp ASC LIMIT ? OFFSET ?""",
                (task_id, limit, offset),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT * FROM conversation_turns
                   ORDER BY timestamp ASC LIMIT ? OFFSET ?""",
                (limit, offset),
            ).fetchall()
        results = []
        for row in rows:
            result = dict(row)
            result["tool_calls"] = json.loads(result["tool_calls"])
            results.append(result)
        return results

    @_with_retry
    def get_recent_turns(self, limit: int = 50) -> List[Dict[str, Any]]:
        conn = self._pool.get_connection()
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT * FROM conversation_turns
               ORDER BY timestamp DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        results = []
        for row in rows:
            result = dict(row)
            result["tool_calls"] = json.loads(result["tool_calls"])
            results.append(result)
        return list(reversed(results))

    # ── Conversation Summaries ─────────────────────────────────────

    @_with_retry
    def save_summary(self, task_id: str, summary: str, turn_count: int) -> None:
        conn = self._pool.get_connection()
        conn.execute(
            """INSERT INTO conversation_summaries (task_id, summary, turn_count, created_at)
               VALUES (?, ?, ?, ?)""",
            (task_id, summary, turn_count, time.time()),
        )
        conn.commit()

    @_with_retry
    def get_summary(self, task_id: str) -> Optional[Dict[str, Any]]:
        conn = self._pool.get_connection()
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM conversation_summaries WHERE task_id = ? ORDER BY created_at DESC LIMIT 1",
            (task_id,),
        ).fetchone()
        return dict(row) if row else None

    # ── Episodic Notes ─────────────────────────────────────────────

    @_with_retry
    def save_episodic_note(self, date: str, summary: str,
                           task_ids: Optional[List[str]] = None) -> None:
        conn = self._pool.get_connection()
        conn.execute(
            """INSERT OR REPLACE INTO episodic_notes (date, summary, task_ids, created_at)
               VALUES (?, ?, ?, ?)""",
            (date, summary, json.dumps(task_ids or []), time.time()),
        )
        conn.commit()

    @_with_retry
    def get_episodic_notes(self, limit: int = 30) -> List[Dict[str, Any]]:
        conn = self._pool.get_connection()
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM episodic_notes ORDER BY date DESC LIMIT ?",
            (limit,),
        ).fetchall()
        results = []
        for row in rows:
            result = dict(row)
            result["task_ids"] = json.loads(result["task_ids"])
            results.append(result)
        return results

    @_with_retry
    def search_episodic_notes(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        conn = self._pool.get_connection()
        conn.row_factory = sqlite3.Row
        like = f"%{query}%"
        rows = conn.execute(
            """SELECT * FROM episodic_notes
               WHERE summary LIKE ? ORDER BY date DESC LIMIT ?""",
            (like, limit),
        ).fetchall()
        results = []
        for row in rows:
            result = dict(row)
            result["task_ids"] = json.loads(result["task_ids"])
            results.append(result)
        return results

    # ── Semantic Facts ─────────────────────────────────────────────

    @_with_retry
    def save_fact(self, key: str, value: str, category: str = "general",
                  confidence: float = 1.0) -> None:
        now = time.time()
        conn = self._pool.get_connection()
        conn.execute(
            """INSERT OR REPLACE INTO semantic_facts
               (fact_key, fact_value, category, confidence, created_at, updated_at)
               VALUES (?, ?, ?, ?, COALESCE((SELECT created_at FROM semantic_facts WHERE fact_key = ?), ?), ?)""",
            (key, value, category, confidence, key, now, now),
        )
        conn.commit()

    @_with_retry
    def get_fact(self, key: str) -> Optional[Dict[str, Any]]:
        conn = self._pool.get_connection()
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM semantic_facts WHERE fact_key = ?", (key,)
        ).fetchone()
        return dict(row) if row else None

    @_with_retry
    def get_all_facts(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        conn = self._pool.get_connection()
        conn.row_factory = sqlite3.Row
        if category:
            rows = conn.execute(
                "SELECT * FROM semantic_facts WHERE category = ? ORDER BY updated_at DESC",
                (category,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM semantic_facts ORDER BY category, updated_at DESC"
            ).fetchall()
        return [dict(row) for row in rows]

    @_with_retry
    def search_facts(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        conn = self._pool.get_connection()
        conn.row_factory = sqlite3.Row
        like = f"%{query}%"
        rows = conn.execute(
            """SELECT * FROM semantic_facts
               WHERE fact_key LIKE ? OR fact_value LIKE ? OR category LIKE ?
               ORDER BY updated_at DESC LIMIT ?""",
            (like, like, like, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    @_with_retry
    def delete_fact(self, key: str) -> None:
        conn = self._pool.get_connection()
        conn.execute("DELETE FROM semantic_facts WHERE fact_key = ?", (key,))
        conn.commit()

    # ── Execution Graph ────────────────────────────────────────────

    @_with_retry
    def save_graph_node(self, node_id: str, name: str, category: str = "general",
                        metadata: Optional[Dict[str, Any]] = None) -> None:
        conn = self._pool.get_connection()
        conn.execute(
            """INSERT OR REPLACE INTO execution_graph_nodes
               (node_id, name, category, metadata_json, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (node_id, name, category, json.dumps(metadata or {}), time.time()),
        )
        conn.commit()

    @_with_retry
    def save_graph_edge(self, source_node_id: str, target_node_id: str,
                        task_id: Optional[str] = None,
                        relationship: str = "depends_on") -> None:
        conn = self._pool.get_connection()
        conn.execute(
            """INSERT INTO execution_graph_edges
               (source_node_id, target_node_id, task_id, relationship, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (source_node_id, target_node_id, task_id, relationship, time.time()),
        )
        conn.commit()

    @_with_retry
    def get_graph_children(self, node_id: str) -> List[Dict[str, Any]]:
        conn = self._pool.get_connection()
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT n.*, e.relationship
               FROM execution_graph_nodes n
               JOIN execution_graph_edges e ON e.target_node_id = n.node_id
               WHERE e.source_node_id = ?
               ORDER BY n.name""",
            (node_id,),
        ).fetchall()
        results = []
        for row in rows:
            result = dict(row)
            result["metadata_json"] = json.loads(result["metadata_json"])
            results.append(result)
        return results

    @_with_retry
    def get_graph_parents(self, node_id: str) -> List[Dict[str, Any]]:
        conn = self._pool.get_connection()
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT n.*, e.relationship
               FROM execution_graph_nodes n
               JOIN execution_graph_edges e ON e.source_node_id = n.node_id
               WHERE e.target_node_id = ?
               ORDER BY n.name""",
            (node_id,),
        ).fetchall()
        results = []
        for row in rows:
            result = dict(row)
            result["metadata_json"] = json.loads(result["metadata_json"])
            results.append(result)
        return results

    @_with_retry
    def get_all_graph_nodes(self) -> List[Dict[str, Any]]:
        conn = self._pool.get_connection()
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM execution_graph_nodes ORDER BY category, name"
        ).fetchall()
        results = []
        for row in rows:
            result = dict(row)
            result["metadata_json"] = json.loads(result["metadata_json"])
            results.append(result)
        return results

    # ── Working Memory ─────────────────────────────────────────────

    @_with_retry
    def save_working_memory(self, task_id: str, snapshot: Dict[str, Any]) -> None:
        conn = self._pool.get_connection()
        conn.execute(
            """INSERT INTO working_memory_snapshots (task_id, snapshot_json, created_at)
               VALUES (?, ?, ?)""",
            (task_id, json.dumps(snapshot), time.time()),
        )
        conn.commit()

    @_with_retry
    def get_latest_working_memory(self, task_id: str) -> Optional[Dict[str, Any]]:
        conn = self._pool.get_connection()
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """SELECT * FROM working_memory_snapshots
               WHERE task_id = ? ORDER BY created_at DESC LIMIT 1""",
            (task_id,),
        ).fetchone()
        if row:
            result = dict(row)
            result["snapshot_json"] = json.loads(result["snapshot_json"])
            return result
        return None

    # ── Utility ────────────────────────────────────────────────────

    @_with_retry
    def get_stats(self) -> Dict[str, Any]:
        conn = self._pool.get_connection()
        cursor = conn.cursor()
        stats = {}
        for table in ["agent_state", "task_memory", "conversation_turns",
                       "conversation_summaries", "episodic_notes",
                       "semantic_facts", "execution_graph_nodes",
                       "execution_graph_edges", "working_memory_snapshots"]:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            stats[table] = cursor.fetchone()[0]
        return stats

    @_with_retry
    def save_research_experiment(self, entry: dict[str, Any]) -> str:
        """Save a research experiment entry into SQLite storage."""
        import uuid
        exp_id = entry.get('experiment_id') or f"exp_{uuid.uuid4().hex[:10]}"
        proj_id = entry.get('project_id') or self.project_id
        timestamp = entry.get('timestamp') or time.time()

        conn = self._pool.get_connection()
        with self._lock:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO research_experiments (
                    experiment_id, hypothesis, mechanism_description,
                    nearest_known_architecture, implementation_summary,
                    result_metrics, baseline_comparison_metrics, outcome,
                    failure_reason, timestamp, project_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                exp_id,
                entry.get('hypothesis', ''),
                entry.get('mechanism_description', ''),
                entry.get('nearest_known_architecture', ''),
                entry.get('implementation_summary', ''),
                json.dumps(entry.get('result_metrics', {})),
                json.dumps(entry.get('baseline_comparison_metrics', {})),
                entry.get('outcome', 'inconclusive'),
                entry.get('failure_reason', ''),
                timestamp,
                proj_id,
            ))
            conn.commit()
            self._pool.increment_write_count()
        return exp_id

    @_with_retry
    def query_research_experiments(
        self, description: str, project_id: str | None = None, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Query research experiments matching description within project_id scope."""
        target_project_id = project_id or self.project_id
        conn = self._pool.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT experiment_id, hypothesis, mechanism_description,
                   nearest_known_architecture, implementation_summary,
                   result_metrics, baseline_comparison_metrics, outcome,
                   failure_reason, timestamp, project_id
            FROM research_experiments
            WHERE project_id = ?
            ORDER BY timestamp DESC
        """, (target_project_id,))
        rows = cursor.fetchall()

        query_words = set(description.lower().split())
        results = []
        for r in rows:
            exp_dict = {
                'experiment_id': r[0],
                'hypothesis': r[1],
                'mechanism_description': r[2],
                'nearest_known_architecture': r[3],
                'implementation_summary': r[4],
                'result_metrics': json.loads(r[5]) if r[5] else {},
                'baseline_comparison_metrics': json.loads(r[6]) if r[6] else {},
                'outcome': r[7],
                'failure_reason': r[8],
                'timestamp': r[9],
                'project_id': r[10],
            }
            haystack = f"{r[1]} {r[2]} {r[3]} {r[4]} {r[8]}".lower()
            if not query_words:
                score = 1.0
            else:
                matches = sum(1 for w in query_words if w in haystack)
                score = round(matches / max(len(query_words), 1), 3)

            exp_dict['similarity_score'] = score
            results.append(exp_dict)

        results.sort(key=lambda x: (x['similarity_score'], x['timestamp']), reverse=True)
        return results[:limit]

    @_with_retry
    def clear_all(self) -> None:
        conn = self._pool.get_connection()
        cursor = conn.cursor()
        for table in ["working_memory_snapshots", "execution_graph_edges",
                       "execution_graph_nodes", "semantic_facts",
                       "episodic_notes", "conversation_summaries",
                       "conversation_turns", "task_memory", "agent_state"]:
            cursor.execute(f"DELETE FROM {table}")
        conn.commit()

    def health_check(self) -> Tuple[bool, str]:
        """
        Check that the database is operational.
        Returns (is_healthy, diagnostic_message).
        """
        try:
            conn = self._pool.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM agent_state")
            cursor.fetchone()
            cursor.execute("PRAGMA integrity_check")
            result = cursor.fetchone()
            if result and result[0] != "ok":
                return False, f"Database integrity check failed: {result[0]}"
            return True, "Database is healthy"
        except Exception as e:
            return False, f"Health check failed: {e}"

    def close(self) -> None:
        """Close all connections and clean up."""
        if hasattr(self, '_pool'):
            self._pool.close_all()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass
