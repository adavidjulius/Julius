"""
SQLite-Backed Persistent Job Queue (WS6.2).

Guarantees atomic status transitions, priority ordering,
persistence across daemon restarts, and support for swapping in Redis/Postgres in server mode.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol

from src.db.pragmas import apply_production_pragmas
from src.jobs.model import Job, JobBudgets, JobStatus

logger = logging.getLogger(__name__)


class JobQueue(Protocol):
    """Abstract interface for job persistence and queue scheduling."""

    def enqueue(self, job: Job) -> str: ...
    def dequeue(self) -> Optional[Job]: ...
    def get_job(self, job_id: str) -> Optional[Job]: ...
    def list_jobs(self, status: Optional[str] = None, limit: int = 50) -> List[Job]: ...
    def cancel(self, job_id: str) -> bool: ...
    def update_job(self, job: Job) -> None: ...


class SQLiteJobQueue:
    """Production-grade SQLite-backed queue implementation."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        if db_path:
            self.db_path = Path(db_path)
        else:
            self.db_path = Path.home() / ".julius" / "jobs.db"
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        apply_production_pragmas(conn)
        return conn

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                task TEXT NOT NULL,
                workspace TEXT NOT NULL,
                status TEXT NOT NULL,
                priority INTEGER NOT NULL DEFAULT 0,
                policy_profile TEXT NOT NULL,
                budgets_json TEXT NOT NULL,
                created_at REAL NOT NULL,
                started_at REAL,
                finished_at REAL,
                error TEXT,
                output TEXT,
                step_count INTEGER NOT NULL DEFAULT 0,
                tokens_used INTEGER NOT NULL DEFAULT 0,
                cost_usd REAL NOT NULL DEFAULT 0.0,
                metadata_json TEXT NOT NULL
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status, priority DESC, created_at ASC);")
        conn.commit()
        conn.close()

    def enqueue(self, job: Job | str) -> str:
        if isinstance(job, str):
            job = Job(task=job)
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO jobs (
                id, task, workspace, status, priority, policy_profile,
                budgets_json, created_at, started_at, finished_at,
                error, output, step_count, tokens_used, cost_usd, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job.id,
                job.task,
                job.workspace,
                job.status,
                job.priority,
                job.policy_profile,
                json.dumps(job.budgets.__dict__),
                job.created_at,
                job.started_at,
                job.finished_at,
                job.error,
                job.output,
                job.step_count,
                job.tokens_used,
                job.cost_usd,
                json.dumps(job.metadata),
            ),
        )
        conn.commit()
        conn.close()
        return job.id

    def dequeue(self) -> Optional[Job]:
        """Atomically select and mark the highest-priority pending job as running."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE;")
        cursor.execute(
            """
            SELECT id FROM jobs
            WHERE status = 'queued'
            ORDER BY priority DESC, created_at ASC
            LIMIT 1;
            """
        )
        row = cursor.fetchone()
        if not row:
            conn.commit()
            conn.close()
            return None

        job_id = row[0]
        now = time.time()
        cursor.execute(
            "UPDATE jobs SET status = 'running', started_at = ? WHERE id = ?",
            (now, job_id),
        )
        conn.commit()
        conn.close()
        return self.get_job(job_id)

    def get_job(self, job_id: str) -> Optional[Job]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, task, workspace, status, priority, policy_profile,
                   budgets_json, created_at, started_at, finished_at,
                   error, output, step_count, tokens_used, cost_usd, metadata_json
            FROM jobs WHERE id = ?
            """,
            (job_id,),
        )
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None

        b_data = json.loads(row[6])
        budgets = JobBudgets(**b_data)
        meta = json.loads(row[15])

        return Job(
            id=row[0],
            task=row[1],
            workspace=row[2],
            status=row[3],
            priority=row[4],
            policy_profile=row[5],
            budgets=budgets,
            created_at=row[7],
            started_at=row[8],
            finished_at=row[9],
            error=row[10],
            output=row[11],
            step_count=row[12],
            tokens_used=row[13],
            cost_usd=row[14],
            metadata=meta,
        )

    def list_jobs(self, status: Optional[str] = None, limit: int = 50) -> List[Job]:
        conn = self._get_connection()
        cursor = conn.cursor()
        if status:
            cursor.execute(
                """
                SELECT id, task, workspace, status, priority, policy_profile,
                       budgets_json, created_at, started_at, finished_at,
                       error, output, step_count, tokens_used, cost_usd, metadata_json
                FROM jobs WHERE status = ?
                ORDER BY created_at DESC LIMIT ?
                """,
                (status, limit),
            )
        else:
            cursor.execute(
                """
                SELECT id, task, workspace, status, priority, policy_profile,
                       budgets_json, created_at, started_at, finished_at,
                       error, output, step_count, tokens_used, cost_usd, metadata_json
                FROM jobs ORDER BY created_at DESC LIMIT ?
                """,
                (limit,),
            )
        rows = cursor.fetchall()
        conn.close()

        jobs = []
        for row in rows:
            b_data = json.loads(row[6])
            budgets = JobBudgets(**b_data)
            meta = json.loads(row[15])
            jobs.append(
                Job(
                    id=row[0],
                    task=row[1],
                    workspace=row[2],
                    status=row[3],
                    priority=row[4],
                    policy_profile=row[5],
                    budgets=budgets,
                    created_at=row[7],
                    started_at=row[8],
                    finished_at=row[9],
                    error=row[10],
                    output=row[11],
                    step_count=row[12],
                    tokens_used=row[13],
                    cost_usd=row[14],
                    metadata=meta,
                )
            )
        return jobs

    def cancel(self, job_id: str) -> bool:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE jobs SET status = 'cancelled', finished_at = ? WHERE id = ? AND status IN ('queued', 'running', 'paused')",
            (time.time(), job_id),
        )
        affected = cursor.rowcount
        conn.commit()
        conn.close()
        return affected > 0

    def update_job(self, job: Job) -> None:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE jobs SET
                status = ?, started_at = ?, finished_at = ?, error = ?, output = ?,
                step_count = ?, tokens_used = ?, cost_usd = ?, metadata_json = ?
            WHERE id = ?
            """,
            (
                job.status,
                job.started_at,
                job.finished_at,
                job.error,
                job.output,
                job.step_count,
                job.tokens_used,
                job.cost_usd,
                json.dumps(job.metadata),
                job.id,
            ),
        )
        conn.commit()
        conn.close()

