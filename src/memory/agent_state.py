"""
Persistent agent state across sessions.
Stores structured state: current_project, current_goal, completed_tasks,
next_task, known_errors, current_branch.

Reinforced with:
- Lazy save (dirty flag): set_goal(), set_project(), etc. just set self._dirty = True
- Caller must explicitly flush() to persist
- Reduced from 7+ SQLite writes per task to 1-2 writes
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

from .storage import MemoryStorage

logger = logging.getLogger(__name__)

DEFAULT_AGENT_STATE: Dict[str, Any] = {
    "current_project": "",
    "current_goal": "",
    "completed_tasks": [],
    "next_task": "",
    "known_errors": [],
    "current_branch": "",
    "session_count": 0,
    "total_tasks_completed": 0,
}


@dataclass
class AgentState:
    """Persistent agent state, loaded from and saved to SQLite."""

    current_project: str = ""
    current_goal: str = ""
    completed_tasks: List[str] = field(default_factory=list)
    next_task: str = ""
    known_errors: List[str] = field(default_factory=list)
    current_branch: str = ""
    session_count: int = 0
    total_tasks_completed: int = 0

    _storage: Optional[MemoryStorage] = None
    _dirty: bool = False

    @classmethod
    def load(cls, storage: MemoryStorage) -> "AgentState":
        """Load agent state from storage, or return defaults."""
        raw = None
        try:
            raw = storage.load_agent_state()
        except Exception as e:
            logger.warning("AgentState: Failed to load from storage: %s. Using defaults.", e)

        if raw:
            return cls(
                current_project=raw.get("current_project", ""),
                current_goal=raw.get("current_goal", ""),
                completed_tasks=raw.get("completed_tasks", []),
                next_task=raw.get("next_task", ""),
                known_errors=raw.get("known_errors", []),
                current_branch=raw.get("current_branch", ""),
                session_count=raw.get("session_count", 0),
                total_tasks_completed=raw.get("total_tasks_completed", 0),
                _storage=storage,
                _dirty=False,
            )
        return cls(_storage=storage, _dirty=False)

    def save(self) -> None:
        """Persist current state to storage (only if dirty)."""
        if not self._dirty:
            return
        if self._storage:
            try:
                self._storage.save_agent_state(self.to_dict())
                self._dirty = False
                logger.debug("AgentState: Saved to storage")
            except Exception as e:
                logger.error("AgentState: Failed to save: %s", e)
                raise

    def flush(self) -> None:
        """Force persist regardless of dirty flag."""
        if self._storage:
            try:
                self._storage.save_agent_state(self.to_dict())
                self._dirty = False
                logger.debug("AgentState: Flushed to storage")
            except Exception as e:
                logger.error("AgentState: Failed to flush: %s", e)
                raise

    def mark_task_completed(self, task_summary: str) -> None:
        """Record a completed task and update counters."""
        self.completed_tasks.append(task_summary)
        self.total_tasks_completed += 1
        self._dirty = True

    def set_goal(self, goal: str) -> None:
        self.current_goal = goal
        self._dirty = True

    def set_project(self, project: str) -> None:
        self.current_project = project
        self._dirty = True

    def set_next_task(self, task: str) -> None:
        self.next_task = task
        self._dirty = True

    def add_error(self, error: str) -> None:
        if error not in self.known_errors:
            self.known_errors.append(error)
            self._dirty = True

    def resolve_error(self, error: str) -> None:
        if error in self.known_errors:
            self.known_errors.remove(error)
            self._dirty = True

    def set_branch(self, branch: str) -> None:
        self.current_branch = branch
        self._dirty = True

    def increment_session(self) -> None:
        self.session_count += 1
        self._dirty = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "current_project": self.current_project,
            "current_goal": self.current_goal,
            "completed_tasks": list(self.completed_tasks),
            "next_task": self.next_task,
            "known_errors": list(self.known_errors),
            "current_branch": self.current_branch,
            "session_count": self.session_count,
            "total_tasks_completed": self.total_tasks_completed,
        }

    def to_prompt_block(self) -> str:
        """Render agent state as a compact prompt block for LLM context."""
        lines = ["<agent_state>"]
        if self.current_project:
            lines.append(f"  Project: {self.current_project}")
        if self.current_goal:
            lines.append(f"  Goal: {self.current_goal}")
        if self.completed_tasks:
            lines.append(f"  Completed tasks ({len(self.completed_tasks)}):")
            for t in self.completed_tasks[-5:]:  # last 5
                lines.append(f"    - {t}")
        if self.next_task:
            lines.append(f"  Next task: {self.next_task}")
        if self.known_errors:
            lines.append(f"  Known errors ({len(self.known_errors)}):")
            for e in self.known_errors:
                lines.append(f"    - {e}")
        if self.current_branch:
            lines.append(f"  Branch: {self.current_branch}")
        lines.append(f"  Session: {self.session_count}")
        lines.append(f"  Total tasks completed: {self.total_tasks_completed}")
        lines.append("</agent_state>")
        return "\n".join(lines)
