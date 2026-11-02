"""
Long-Horizon Browser Planner — task graph with pause/resume/crash recovery.

Maintains an internal directed graph of browser sub-steps that:
  - Executes in dependency order
  - Survives interruption (persists to .julius/browser_task.json)
  - Supports pause, resume, and retry after crashes
  - Tracks success/failure per step for partial restart

Design: The agent builds the task graph via browser_build_task, then the
GoalNavigator executes it. The agent can inspect status at any time via
browser_task_status and resume a crashed task via browser_resume_task.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Any

logger = logging.getLogger(__name__)


# ── BrowserStep ───────────────────────────────────────────────────────────────

@dataclass
class BrowserStep:
    """A single step in a browser task graph."""
    id: str
    description: str
    action: str                   # browser_* action name
    args: dict = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)  # step IDs that must succeed first
    status: Literal["pending", "running", "done", "failed", "skipped"] = "pending"
    result_summary: str = ""      # short description of what happened
    error: str = ""
    retry_count: int = 0
    max_retries: int = 2
    started_at: float | None = None
    completed_at: float | None = None

    @property
    def is_terminal(self) -> bool:
        return self.status in ("done", "failed", "skipped")

    @property
    def can_retry(self) -> bool:
        return self.status == "failed" and self.retry_count < self.max_retries

    @property
    def elapsed_seconds(self) -> float | None:
        if self.started_at and self.completed_at:
            return round(self.completed_at - self.started_at, 2)
        return None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "description": self.description,
            "action": self.action,
            "args": self.args,
            "depends_on": self.depends_on,
            "status": self.status,
            "result_summary": self.result_summary,
            "error": self.error,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "BrowserStep":
        return cls(
            id=d["id"],
            description=d["description"],
            action=d["action"],
            args=d.get("args", {}),
            depends_on=d.get("depends_on", []),
            status=d.get("status", "pending"),
            result_summary=d.get("result_summary", ""),
            error=d.get("error", ""),
            retry_count=d.get("retry_count", 0),
            max_retries=d.get("max_retries", 2),
            started_at=d.get("started_at"),
            completed_at=d.get("completed_at"),
        )


# ── BrowserTaskGraph ──────────────────────────────────────────────────────────

class BrowserTaskGraph:
    """
    Directed graph of browser sub-steps for long-horizon tasks.

    Usage
    -----
    graph = BrowserTaskGraph(workspace_root)
    graph.add_step("nav", "Navigate to login page", "browser_navigate",
                   {"url": "https://example.com/login"})
    graph.add_step("fill_email", "Fill email", "browser_type",
                   {"selector": "#email", "text": "user@example.com"},
                   depends_on=["nav"])
    graph.add_step("submit", "Submit form", "browser_click",
                   {"selector": "#submit"}, depends_on=["fill_email"])

    step = graph.next_executable_step()
    # ... execute step.action with step.args ...
    graph.mark_done("nav", "Navigated to https://example.com/login")
    """

    PERSIST_FILENAME = ".julius/browser_task.json"

    def __init__(self, workspace_root: str) -> None:
        self.workspace_root = Path(workspace_root)
        self.steps: dict[str, BrowserStep] = {}
        self.goal: str = ""
        self.created_at: float = time.time()
        self._persist_path = self.workspace_root / self.PERSIST_FILENAME

    # ── Building ──────────────────────────────────────────────────────────────

    def add_step(
        self,
        step_id: str,
        description: str,
        action: str,
        args: dict | None = None,
        depends_on: list[str] | None = None,
        max_retries: int = 2,
    ) -> BrowserStep:
        step = BrowserStep(
            id=step_id,
            description=description,
            action=action,
            args=args or {},
            depends_on=depends_on or [],
            max_retries=max_retries,
        )
        self.steps[step_id] = step
        return step

    def set_goal(self, goal: str) -> None:
        self.goal = goal

    # ── Execution control ─────────────────────────────────────────────────────

    def next_executable_step(self) -> BrowserStep | None:
        """
        Return the next step whose dependencies are all done and which is pending.
        Returns None when all steps are terminal or no step is ready.
        """
        for step in self.steps.values():
            if step.status not in ("pending", "failed"):
                continue
            if step.status == "failed" and not step.can_retry:
                continue
            # Check all dependencies are done
            deps_done = all(
                self.steps.get(dep, BrowserStep("_", "_", "_")).status == "done"
                for dep in step.depends_on
            )
            if deps_done:
                return step
        return None

    def mark_running(self, step_id: str) -> None:
        if step_id in self.steps:
            self.steps[step_id].status = "running"
            self.steps[step_id].started_at = time.time()
            self._save()

    def mark_done(self, step_id: str, result_summary: str = "") -> None:
        if step_id in self.steps:
            step = self.steps[step_id]
            step.status = "done"
            step.result_summary = result_summary
            step.completed_at = time.time()
            self._save()

    def mark_failed(self, step_id: str, error: str = "", auto_retry: bool = True) -> None:
        if step_id in self.steps:
            step = self.steps[step_id]
            step.error = error
            step.completed_at = time.time()
            if auto_retry and step.can_retry:
                step.retry_count += 1
                step.status = "pending"   # will be retried
                logger.info(f"Task step {step_id!r} failed, will retry ({step.retry_count}/{step.max_retries})")
            else:
                step.status = "failed"
                # Skip all steps that depend on this one
                for other in self.steps.values():
                    if step_id in other.depends_on and other.status == "pending":
                        other.status = "skipped"
                        other.error = f"Skipped because dependency {step_id!r} failed"
            self._save()

    def skip_step(self, step_id: str, reason: str = "") -> None:
        if step_id in self.steps:
            self.steps[step_id].status = "skipped"
            self.steps[step_id].error = reason
            self._save()

    def abort(self) -> None:
        """Mark all pending/running steps as skipped."""
        for step in self.steps.values():
            if not step.is_terminal:
                step.status = "skipped"
                step.error = "Task aborted"
        self._save()

    # ── Status ────────────────────────────────────────────────────────────────

    @property
    def is_complete(self) -> bool:
        return all(s.is_terminal for s in self.steps.values())

    @property
    def is_successful(self) -> bool:
        return self.is_complete and all(
            s.status in ("done", "skipped") for s in self.steps.values()
        )

    @property
    def can_resume(self) -> bool:
        return any(s.status in ("pending", "running") for s in self.steps.values())

    def counts(self) -> dict[str, int]:
        counts: dict[str, int] = {"pending": 0, "running": 0, "done": 0,
                                   "failed": 0, "skipped": 0}
        for s in self.steps.values():
            counts[s.status] += 1
        return counts

    def to_text(self) -> str:
        c = self.counts()
        lines = [
            f"BROWSER TASK: {self.goal or '(unnamed)'}",
            f"Progress: {c['done']} done, {c['pending']} pending, "
            f"{c['failed']} failed, {c['skipped']} skipped",
            "─" * 40,
        ]
        for step in self.steps.values():
            status_icon = {
                "pending": "⏳", "running": "🔄", "done": "✅",
                "failed": "❌", "skipped": "⏭",
            }.get(step.status, "?")
            retry_tag = f" (retry {step.retry_count}/{step.max_retries})" if step.retry_count else ""
            lines.append(f"  {status_icon} [{step.id}] {step.description}{retry_tag}")
            if step.result_summary:
                lines.append(f"       → {step.result_summary}")
            if step.error and step.status in ("failed", "skipped"):
                lines.append(f"       ✗ {step.error[:80]}")
        return "\n".join(lines)

    # ── Serialization ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "goal": self.goal,
            "created_at": self.created_at,
            "steps": {sid: s.to_dict() for sid, s in self.steps.items()},
        }

    @classmethod
    def from_dict(cls, data: dict, workspace_root: str) -> "BrowserTaskGraph":
        graph = cls(workspace_root)
        graph.goal = data.get("goal", "")
        graph.created_at = data.get("created_at", time.time())
        for sid, sdata in data.get("steps", {}).items():
            graph.steps[sid] = BrowserStep.from_dict(sdata)
        return graph

    def _save(self) -> None:
        try:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            self._persist_path.write_text(
                json.dumps(self.to_dict(), indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning(f"BrowserTaskGraph: failed to persist: {exc}")

    @classmethod
    def load(cls, workspace_root: str) -> "BrowserTaskGraph | None":
        """Load a previously persisted task graph, or return None."""
        path = Path(workspace_root) / cls.PERSIST_FILENAME
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            graph = cls.from_dict(data, workspace_root)
            logger.info(f"BrowserTaskGraph: loaded {len(graph.steps)} steps from disk")
            return graph
        except Exception as exc:
            logger.warning(f"BrowserTaskGraph: failed to load: {exc}")
            return None

    def clear_persist(self) -> None:
        """Remove the persisted task file."""
        try:
            if self._persist_path.exists():
                self._persist_path.unlink()
        except Exception:
            pass
