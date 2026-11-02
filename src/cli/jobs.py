"""
Job Management CLI Commands (WS6.2).

Powers `julius jobs list`, `julius jobs cancel <id>`, and `julius jobs logs <id>`.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from typing import Optional

from src.jobs.model import Job
from src.jobs.queue import SQLiteJobQueue
from src.jobs.worker import JobWorkerPool


def submit_job_cli(task: str) -> str:
    queue = SQLiteJobQueue()
    job_id = queue.enqueue(task)
    print(f"✅ Job submitted successfully. ID: {job_id}")
    return job_id


def resume_job_cli(job_id: str) -> bool:
    queue = SQLiteJobQueue()
    job = queue.get_job(job_id)
    if not job:
        print(f"❌ Job '{job_id}' not found.")
        return False
    # Re-enqueue job
    resumed_id = queue.enqueue(job.task)
    print(f"🔄 Resumed job '{job_id}' as new queued job: {resumed_id}")
    return True


def run_worker_cli(concurrency: int = 2) -> None:
    pool = JobWorkerPool(max_concurrent_jobs=concurrency)
    print(f"🚀 Starting Julius Job Worker Pool (concurrency={concurrency})...")
    try:
        asyncio.run(pool.start())
    except KeyboardInterrupt:
        print("\nStopping worker pool...")


def list_jobs_cli(status: Optional[str] = None, limit: int = 20) -> None:
    queue = SQLiteJobQueue()
    jobs = queue.list_jobs(status=status, limit=limit)
    print("\n📋 Julius Job Execution Queue")
    print("=" * 80)
    print(f"{'ID':<16} {'Status':<12} {'Created':<20} {'Task'}")
    print("-" * 80)
    for j in jobs:
        created_str = datetime.fromtimestamp(j.created_at, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        task_preview = (j.task[:36] + "...") if len(j.task) > 36 else j.task
        print(f"{j.id:<16} {j.status:<12} {created_str:<20} {task_preview}")
    print("=" * 80 + "\n")


def cancel_job_cli(job_id: str) -> None:
    queue = SQLiteJobQueue()
    ok = queue.cancel(job_id)
    if ok:
        print(f"✅ Job '{job_id}' marked as cancelled.")
    else:
        print(f"❌ Failed to cancel job '{job_id}' (job not found or already terminated).")


def show_job_logs(job_id: str) -> None:
    queue = SQLiteJobQueue()
    job = queue.get_job(job_id)
    if not job:
        print(f"❌ Job '{job_id}' not found.")
        return
    print(f"\n📜 Logs & Output for Job: {job.id}")
    print("=" * 60)
    print(f" Task    : {job.task}")
    print(f" Status  : {job.status}")
    print(f" Steps   : {job.step_count}")
    print(f" Tokens  : {job.tokens_used}")
    print(f" Cost    : ${job.cost_usd:.4f}")
    if job.error:
        print(f" Error   : {job.error}")
    print("-" * 60)
    print(job.output or "[No output recorded]")
    print("=" * 60 + "\n")

