"""
"Continue previous task" mechanism.
When the user says "continue the previous task", this handler loads
the last task context and rebuilds working memory without the user noticing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .storage import MemoryStorage
from .task_memory import TaskMemory, TaskRecord
from .conversation_memory import ConversationMemory
from .working_memory import WorkingMemory
from .agent_state import AgentState
from .compression import ConversationCompressor, CompressedTaskSummary

logger = logging.getLogger(__name__)


@dataclass
class ContinueContext:
    """Reconstructed context for continuing a previous task."""
    task: TaskRecord
    summary: Optional[str]
    working_memory: WorkingMemory
    prompt_block: str
    tasks_since: int  # number of tasks completed since this one


class ContinueTaskHandler:
    """Handles "continue previous task" by reconstructing full context."""

    def __init__(self, storage: MemoryStorage, task_memory: TaskMemory,
                 conversation: ConversationMemory, agent_state: AgentState,
                 compressor: ConversationCompressor) -> None:
        self._storage = storage
        self._task_memory = task_memory
        self._conversation = conversation
        self._agent_state = agent_state
        self._compressor = compressor

    def get_continuation_context(self) -> Optional[ContinueContext]:
        """
        Find the last incomplete task and build continuation context.
        If no incomplete task, get the last completed task.
        """
        # First try to find an in-progress task
        tasks = self._task_memory.list_tasks(limit=20)
        last_incomplete = None
        last_completed = None

        for t in tasks:
            if t.status == "in_progress":
                last_incomplete = t
                break
            if t.status == "completed" and last_completed is None:
                last_completed = t

        target_task = last_incomplete or last_completed
        if target_task is None:
            logger.info("ContinueTaskHandler: No previous task found")
            return None

        # Calculate how many tasks happened since
        tasks_since = 0
        if target_task.status == "completed":
            all_tasks = self._task_memory.list_tasks(limit=50)
            found = False
            for t in all_tasks:
                if t.task_id == target_task.task_id:
                    found = True
                elif found and t.status == "completed":
                    tasks_since += 1

        # Get the conversation summary
        summary = self._conversation.get_summary(target_task.task_id)

        # Rebuild working memory
        wm = WorkingMemory()
        wm.current_task_id = target_task.task_id
        wm.current_goal = target_task.summary
        if target_task.files_modified:
            wm.set_current_file(target_task.files_modified[-1])
        if target_task.known_issues:
            wm.add_context(f"Previous known issues: {', '.join(target_task.known_issues)}")

        # Build the prompt block
        prompt = self._build_continue_prompt(target_task, summary, tasks_since)

        return ContinueContext(
            task=target_task,
            summary=summary.get("summary") if summary else None,
            working_memory=wm,
            prompt_block=prompt,
            tasks_since=tasks_since,
        )

    def _build_continue_prompt(self, task: TaskRecord,
                               summary: Optional[Dict[str, Any]],
                               tasks_since: int) -> str:
        """Build a context block for continuing a task."""
        lines = ["<continue_previous_task>"]

        if task.status == "in_progress":
            lines.append("  Status: Previous task was still in progress")
        else:
            lines.append("  Status: Continuing from last completed task")

        lines.append(f"  Task: {task.summary}")
        lines.append(f"  Previous status: {task.status}")

        if task.files_modified:
            lines.append(f"  Previously modified files ({len(task.files_modified)}):")
            for f in task.files_modified:
                lines.append(f"    - {f}")

        if task.functions_changed:
            lines.append(f"  Previously changed functions ({len(task.functions_changed)}):")
            for f in task.functions_changed:
                lines.append(f"    - {f}")

        if task.known_issues:
            lines.append("  Known issues to address:")
            for i in task.known_issues:
                lines.append(f"    - {i}")

        if summary:
            lines.append(f"  Conversation summary: {summary.get('summary', '')[:200]}")

        if tasks_since > 0:
            lines.append(f"  Note: {tasks_since} other task(s) have been completed since this one")

        lines.append("</continue_previous_task>")
        return "\n".join(lines)

    def continue_task(self) -> Optional[str]:
        """
        Get the context block for continuing the previous task.
        Returns None if no previous task exists.
        The returned string should be prepended to the LLM prompt.
        """
        context = self.get_continuation_context()
        if context is None:
            return None

        logger.info(f"ContinueTaskHandler: Continuing task {context.task.task_id[:8]}: {context.task.summary[:60]}")
        return context.prompt_block

    def get_last_task_summary(self) -> Optional[str]:
        """Get a short summary of the last task for display or quick reference."""
        last = self._task_memory.get_last_completed_task()
        if not last:
            last = self._task_memory.get_latest_task()
        if not last:
            return None
        return f"Task {last.task_id[:8]}: {last.summary} (status: {last.status})"
