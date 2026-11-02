"""
Asyncio Job Worker Pool with Cancellation & Concurrency Limits (WS6.2).
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Callable, Coroutine, Dict, Optional

from src.jobs.model import Job
from src.jobs.queue import JobQueue, SQLiteJobQueue

logger = logging.getLogger(__name__)


class JobWorkerPool:
    """Manages worker pool consuming jobs from JobQueue."""

    def __init__(
        self,
        queue: Optional[JobQueue] = None,
        max_concurrent_jobs: int = 2,
        executor_fn: Optional[Callable[[Job], Coroutine[None, None, str]]] = None,
    ) -> None:
        self.queue = queue or SQLiteJobQueue()
        self.max_concurrent_jobs = max_concurrent_jobs
        self.executor_fn = executor_fn
        self._running = False
        self._active_tasks: Dict[str, asyncio.Task] = {}
        self._cancel_tokens: Dict[str, asyncio.Event] = {}

    async def start(self) -> None:
        self._running = True
        logger.info(f"JobWorkerPool started (concurrency={self.max_concurrent_jobs})")
        while self._running:
            # Clean finished tasks
            finished = [jid for jid, task in self._active_tasks.items() if task.done()]
            for jid in finished:
                del self._active_tasks[jid]
                if jid in self._cancel_tokens:
                    del self._cancel_tokens[jid]

            # If capacity available, pull next job
            if len(self._active_tasks) < self.max_concurrent_jobs:
                job = self.queue.dequeue()
                if job:
                    cancel_evt = asyncio.Event()
                    self._cancel_tokens[job.id] = cancel_evt
                    task = asyncio.create_task(self._execute_job_wrapper(job, cancel_evt))
                    self._active_tasks[job.id] = task
                else:
                    await asyncio.sleep(0.5)
            else:
                await asyncio.sleep(0.2)

    async def _execute_job_wrapper(self, job: Job, cancel_evt: asyncio.Event) -> None:
        logger.info(f"Executing job {job.id}: {job.task[:60]}")
        start_time = time.time()
        try:
            if self.executor_fn:
                output = await self.executor_fn(job)
                job.output = output
                job.status = "completed"
            else:
                # Default mock execution
                await asyncio.sleep(0.1)
                job.output = f"Processed task: {job.task}"
                job.status = "completed"
        except asyncio.CancelledError:
            job.status = "cancelled"
            job.error = "Cancelled by user"
        except Exception as exc:
            logger.error(f"Job {job.id} failed: {exc}")
            job.status = "failed"
            job.error = str(exc)
        finally:
            job.finished_at = time.time()
            self.queue.update_job(job)

    def cancel_job(self, job_id: str) -> bool:
        if job_id in self._cancel_tokens:
            self._cancel_tokens[job_id].set()
        if job_id in self._active_tasks:
            self._active_tasks[job_id].cancel()
            return True
        return self.queue.cancel(job_id)

    async def stop(self) -> None:
        self._running = False
        for task in self._active_tasks.values():
            task.cancel()
        if self._active_tasks:
            await asyncio.gather(*self._active_tasks.values(), return_exceptions=True)

