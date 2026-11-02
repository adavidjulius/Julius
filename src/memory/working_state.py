"""
Julius Persistent Working State Subsystem.
Tracks live, evolving picture of an in-progress task for seamless resumption across sessions.
"""

from __future__ import annotations

from contextlib import contextmanager
import json
import logging
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class TaskWorkingState:
    task_id: str
    project_id: str
    goal: str
    current_plan: str
    completed_subtasks: List[str] = field(default_factory=list)
    remaining_subtasks: List[str] = field(default_factory=list)
    last_known_good_state: str = ""
    blockers: List[str] = field(default_factory=list)
    files_in_progress: List[str] = field(default_factory=list)
    last_updated: float = field(default_factory=time.time)
    session_count: int = 1
    status: str = "in_progress"  # 'in_progress', 'completed', 'abandoned'

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "project_id": self.project_id,
            "goal": self.goal,
            "current_plan": self.current_plan,
            "completed_subtasks": self.completed_subtasks,
            "remaining_subtasks": self.remaining_subtasks,
            "last_known_good_state": self.last_known_good_state,
            "blockers": self.blockers,
            "files_in_progress": self.files_in_progress,
            "last_updated": self.last_updated,
            "session_count": self.session_count,
            "status": self.status,
        }

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> TaskWorkingState:
        keys = row.keys()
        return cls(
            task_id=row["task_id"],
            project_id=row["project_id"],
            goal=row["goal"],
            current_plan=row["current_plan"],
            completed_subtasks=json.loads(row["completed_subtasks"] or "[]"),
            remaining_subtasks=json.loads(row["remaining_subtasks"] or "[]"),
            last_known_good_state=row["last_known_good_state"],
            blockers=json.loads(row["blockers"] or "[]"),
            files_in_progress=json.loads(row["files_in_progress"] or "[]"),
            last_updated=row["last_updated"],
            session_count=row["session_count"],
            status=row["status"] if "status" in keys else "in_progress",
        )


class WorkingStateManager:
    """
    Manages SQLite persistence for task_working_state in .julius/memory.db.
    """

    def __init__(self, workspace_root: str | Path = ".") -> None:
        self.workspace_root = Path(workspace_root).resolve()
        julius_dir = self.workspace_root / ".julius"
        legacy_dir = self.workspace_root / ".julius"
        self.julius_dir = julius_dir if julius_dir.exists() or not legacy_dir.exists() else legacy_dir
        self.julius_dir.mkdir(parents=True, exist_ok=True)
        self.julius_dir = self.julius_dir  # Backward compatibility alias
        self.db_path = self.julius_dir / "memory.db"
        self.init_db()

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            yield conn
            conn.commit()
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def init_db(self) -> None:
        """Create task_working_state table if it doesn't exist."""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS task_working_state (
                    task_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    goal TEXT NOT NULL,
                    current_plan TEXT NOT NULL,
                    completed_subtasks TEXT NOT NULL DEFAULT '[]',
                    remaining_subtasks TEXT NOT NULL DEFAULT '[]',
                    last_known_good_state TEXT NOT NULL,
                    blockers TEXT NOT NULL DEFAULT '[]',
                    files_in_progress TEXT NOT NULL DEFAULT '[]',
                    last_updated REAL NOT NULL,
                    session_count INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'in_progress'
                )
            """)
            conn.commit()

    def save_working_state(self, state: TaskWorkingState) -> None:
        """Upsert a TaskWorkingState record."""
        state.last_updated = time.time()
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO task_working_state (
                    task_id, project_id, goal, current_plan,
                    completed_subtasks, remaining_subtasks, last_known_good_state,
                    blockers, files_in_progress, last_updated, session_count, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    project_id=excluded.project_id,
                    goal=excluded.goal,
                    current_plan=excluded.current_plan,
                    completed_subtasks=excluded.completed_subtasks,
                    remaining_subtasks=excluded.remaining_subtasks,
                    last_known_good_state=excluded.last_known_good_state,
                    blockers=excluded.blockers,
                    files_in_progress=excluded.files_in_progress,
                    last_updated=excluded.last_updated,
                    session_count=excluded.session_count,
                    status=excluded.status
            """, (
                state.task_id,
                state.project_id,
                state.goal,
                state.current_plan,
                json.dumps(state.completed_subtasks),
                json.dumps(state.remaining_subtasks),
                state.last_known_good_state,
                json.dumps(state.blockers),
                json.dumps(state.files_in_progress),
                state.last_updated,
                state.session_count,
                state.status,
            ))
            conn.commit()

    def get_working_state(self, task_id: str) -> Optional[TaskWorkingState]:
        """Fetch working state by task_id."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM task_working_state WHERE task_id = ?", (task_id,))
            row = cursor.fetchone()
            if row:
                return TaskWorkingState.from_row(row)
        return None

    def get_active_tasks(self, project_id: str) -> List[TaskWorkingState]:
        """Get all non-terminal tasks for project_id."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM task_working_state WHERE project_id = ? AND status = 'in_progress' ORDER BY last_updated DESC",
                (project_id,)
            )
            rows = cursor.fetchall()
            return [TaskWorkingState.from_row(r) for r in rows]

    def mark_completed(self, task_id: str, summary: str | None = None) -> None:
        """Mark a task as completed (terminal status)."""
        with self._get_connection() as conn:
            if summary:
                conn.execute(
                    "UPDATE task_working_state SET status = 'completed', last_known_good_state = ?, last_updated = ? WHERE task_id = ?",
                    (summary, time.time(), task_id)
                )
            else:
                conn.execute(
                    "UPDATE task_working_state SET status = 'completed', last_updated = ? WHERE task_id = ?",
                    (time.time(), task_id)
                )
            conn.commit()

    def mark_abandoned(self, task_id: str) -> None:
        """Mark a task as explicitly abandoned (terminal status)."""
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE task_working_state SET status = 'abandoned', last_updated = ? WHERE task_id = ?",
                (time.time(), task_id)
            )
            conn.commit()

    def is_likely_abandoned(self, state: TaskWorkingState, days_threshold: int = 30) -> bool:
        """Check staleness rule: true if untouched for > 30 days and not completed."""
        if state.status == "completed":
            return False
        seconds_in_day = 86400.0
        elapsed_days = (time.time() - state.last_updated) / seconds_in_day
        return elapsed_days >= days_threshold


class AppGenerationStore:
    """
    Persists app generation records to app_generations table in .julius/memory.db.

    Every generated app gets an explicit verification_status:
      verified_working | partially_verified | unverified | failed
    This field is NEVER omitted and NEVER implied — the same discipline
    enforced for execution_type in the research pipeline.
    """

    def __init__(self, workspace_root: str | Path = ".") -> None:
        self.workspace_root = Path(workspace_root).resolve()
        julius_dir = self.workspace_root / ".julius"
        legacy_dir = self.workspace_root / ".julius"
        self.julius_dir = julius_dir if julius_dir.exists() or not legacy_dir.exists() else legacy_dir
        self.julius_dir.mkdir(parents=True, exist_ok=True)
        self.julius_dir = self.julius_dir  # Backward compatibility alias
        self.db_path = self.julius_dir / "memory.db"
        self._init_table()

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            yield conn
            conn.commit()
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _init_table(self) -> None:
        """Create app_generations table if it doesn't exist."""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS app_generations (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    title TEXT NOT NULL DEFAULT '',
                    description TEXT NOT NULL,
                    stack TEXT NOT NULL,
                    spec_json TEXT NOT NULL DEFAULT '{}',
                    files_generated TEXT NOT NULL DEFAULT '[]',
                    output_dir TEXT NOT NULL DEFAULT '',
                    verification_status TEXT NOT NULL,
                    verification_summary TEXT NOT NULL DEFAULT '',
                    install_success INTEGER NOT NULL DEFAULT 0,
                    install_output TEXT NOT NULL DEFAULT '',
                    startup_success INTEGER NOT NULL DEFAULT 0,
                    startup_output TEXT NOT NULL DEFAULT '',
                    http_check_status INTEGER,
                    screenshot_path TEXT,
                    feature_results_json TEXT NOT NULL DEFAULT '[]',
                    port_used INTEGER,
                    incomplete_items_json TEXT NOT NULL DEFAULT '[]',
                    timestamp TEXT NOT NULL
                )
            """)
            conn.commit()

    def save_generation(self, record: "Any") -> None:
        """
        Upsert an AppGenerationRecord. Accepts the AppGenerationRecord dataclass
        (imported lazily to avoid circular imports).
        """
        import json
        spec_dict = record.spec.to_dict() if record.spec else {}
        feature_list = [
            {
                "feature": r.feature,
                "action_taken": r.action_taken,
                "expected_result": r.expected_result,
                "observed_result": r.observed_result,
                "verified": r.verified,
                "error": r.error,
            }
            for r in record.feature_results
        ]
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO app_generations (
                    id, project_id, name, title, description, stack,
                    spec_json, files_generated, output_dir,
                    verification_status, verification_summary,
                    install_success, install_output,
                    startup_success, startup_output,
                    http_check_status, screenshot_path,
                    feature_results_json, port_used, incomplete_items_json, timestamp
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    verification_status=excluded.verification_status,
                    verification_summary=excluded.verification_summary,
                    install_success=excluded.install_success,
                    install_output=excluded.install_output,
                    startup_success=excluded.startup_success,
                    startup_output=excluded.startup_output,
                    http_check_status=excluded.http_check_status,
                    screenshot_path=excluded.screenshot_path,
                    feature_results_json=excluded.feature_results_json,
                    port_used=excluded.port_used,
                    incomplete_items_json=excluded.incomplete_items_json
            """, (
                record.id,
                record.project_id,
                record.spec.slug if record.spec else "",
                record.spec.title if record.spec else "",
                record.spec.description if record.spec else "",
                record.stack,
                json.dumps(spec_dict),
                json.dumps(record.files_generated),
                record.output_dir,
                record.verification_status,
                record.verification_summary,
                int(record.install_success),
                record.install_output,
                int(record.startup_success),
                record.startup_output,
                record.http_check_status,
                record.screenshot_path,
                json.dumps(feature_list),
                record.port_used,
                json.dumps(record.incomplete_items),
                record.timestamp,
            ))
            conn.commit()

    def list_generations(self, project_id: str) -> List[Dict[str, Any]]:
        """Return all app generation records for project_id, newest first."""
        import json
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM app_generations WHERE project_id = ? ORDER BY timestamp DESC",
                (project_id,)
            )
            rows = cursor.fetchall()
        result = []
        for row in rows:
            result.append({
                "id": row["id"],
                "project_id": row["project_id"],
                "name": row["name"],
                "title": row["title"],
                "description": row["description"],
                "stack": row["stack"],
                "spec": json.loads(row["spec_json"] or "{}"),
                "files_generated": json.loads(row["files_generated"] or "[]"),
                "output_dir": row["output_dir"],
                "verification_status": row["verification_status"],
                "verification_summary": row["verification_summary"],
                "install_success": bool(row["install_success"]),
                "install_output": row["install_output"],
                "startup_success": bool(row["startup_success"]),
                "startup_output": row["startup_output"],
                "http_check_status": row["http_check_status"],
                "screenshot_path": row["screenshot_path"],
                "feature_results": json.loads(row["feature_results_json"] or "[]"),
                "port_used": row["port_used"],
                "incomplete_items": json.loads(row["incomplete_items_json"] or "[]"),
                "timestamp": row["timestamp"],
            })
        return result

    def get_generation(self, generation_id: str) -> Optional[Dict[str, Any]]:
        """Get a single generation record by id."""
        import json
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM app_generations WHERE id = ?",
                (generation_id,)
            )
            row = cursor.fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "project_id": row["project_id"],
            "name": row["name"],
            "title": row["title"],
            "description": row["description"],
            "stack": row["stack"],
            "spec": json.loads(row["spec_json"] or "{}"),
            "files_generated": json.loads(row["files_generated"] or "[]"),
            "output_dir": row["output_dir"],
            "verification_status": row["verification_status"],
            "verification_summary": row["verification_summary"],
            "install_success": bool(row["install_success"]),
            "install_output": row["install_output"],
            "startup_success": bool(row["startup_success"]),
            "startup_output": row["startup_output"],
            "http_check_status": row["http_check_status"],
            "screenshot_path": row["screenshot_path"],
            "feature_results": json.loads(row["feature_results_json"] or "[]"),
            "port_used": row["port_used"],
            "incomplete_items": json.loads(row["incomplete_items_json"] or "[]"),
            "timestamp": row["timestamp"],
        }
