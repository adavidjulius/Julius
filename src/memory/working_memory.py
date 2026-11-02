"""
Ephemeral session-scoped working memory.
Current file, current errors, current branch, current goal, temporary variables.
Cleared after completion.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class WorkingMemory:
    """Session-scoped ephemeral context. Not persisted between sessions."""

    current_task_id: Optional[str] = None
    current_file: Optional[str] = None
    current_errors: List[str] = field(default_factory=list)
    current_branch: Optional[str] = None
    current_goal: Optional[str] = None
    temp_variables: Dict[str, Any] = field(default_factory=dict)
    accumulated_context: List[str] = field(default_factory=list)
    last_action: Optional[str] = None
    last_action_result: Optional[str] = None

    def set_current_file(self, path: str) -> None:
        self.current_file = path

    def set_current_branch(self, branch: str) -> None:
        self.current_branch = branch

    def set_current_goal(self, goal: str) -> None:
        self.current_goal = goal

    def add_error(self, error: str) -> None:
        if error not in self.current_errors:
            self.current_errors.append(error)

    def clear_errors(self) -> None:
        self.current_errors.clear()

    def set_temp(self, key: str, value: Any) -> None:
        self.temp_variables[key] = value

    def get_temp(self, key: str, default: Any = None) -> Any:
        return self.temp_variables.get(key, default)

    def pop_temp(self, key: str, default: Any = None) -> Any:
        return self.temp_variables.pop(key, default)

    def add_context(self, context: str) -> None:
        self.accumulated_context.append(context)

    def record_action(self, action: str, result: str) -> None:
        self.last_action = action
        self.last_action_result = result

    def clear(self) -> None:
        """Clear all working memory for a fresh session."""
        self.current_task_id = None
        self.current_file = None
        self.current_errors.clear()
        self.current_branch = None
        self.current_goal = None
        self.temp_variables.clear()
        self.accumulated_context.clear()
        self.last_action = None
        self.last_action_result = None

    def snapshot(self) -> Dict[str, Any]:
        """Create a serializable snapshot for storage."""
        return asdict(self)

    def to_prompt_block(self) -> str:
        """Render working memory as a compact prompt block."""
        lines = ["<working_memory>"]
        if self.current_file:
            lines.append(f"  Current file: {self.current_file}")
        if self.current_branch:
            lines.append(f"  Current branch: {self.current_branch}")
        if self.current_goal:
            lines.append(f"  Current goal: {self.current_goal}")
        if self.current_errors:
            lines.append(f"  Current errors ({len(self.current_errors)}):")
            for e in self.current_errors:
                lines.append(f"    - {e}")
        if self.last_action:
            lines.append(f"  Last action: {self.last_action}")
        lines.append("</working_memory>")
        return "\n".join(lines)
