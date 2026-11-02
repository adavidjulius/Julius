"""
Conversation memory: stores every interaction with optional summarization.
Raw turns in SQLite; summarizer compresses older turns into summaries.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .storage import MemoryStorage

logger = logging.getLogger(__name__)


@dataclass
class TurnRecord:
    id: int
    task_id: Optional[str]
    role: str
    content: str
    tool_calls: List[Dict[str, Any]]
    timestamp: float


class ConversationMemory:
    """Stores and retrieves conversation turns."""

    def __init__(self, storage: MemoryStorage) -> None:
        self._storage = storage

    def add_turn(self, task_id: Optional[str], role: str, content: str,
                 tool_calls: Optional[List[Dict[str, Any]]] = None) -> int:
        """Record a single conversation turn. Returns turn ID."""
        return self._storage.save_turn(task_id, role, content, tool_calls)

    def get_turns(self, task_id: Optional[str] = None, limit: int = 100,
                  offset: int = 0) -> List[TurnRecord]:
        """Get turns for a task or globally."""
        raws = self._storage.get_turns(task_id, limit, offset)
        return [
            TurnRecord(
                id=r["id"],
                task_id=r["task_id"],
                role=r["role"],
                content=r["content"],
                tool_calls=r["tool_calls"],
                timestamp=r["timestamp"],
            )
            for r in raws
        ]

    def get_recent_turns(self, limit: int = 50) -> List[TurnRecord]:
        """Get most recent turns across all tasks."""
        raws = self._storage.get_recent_turns(limit)
        return [
            TurnRecord(
                id=r["id"],
                task_id=r["task_id"],
                role=r["role"],
                content=r["content"],
                tool_calls=r["tool_calls"],
                timestamp=r["timestamp"],
            )
            for r in raws
        ]

    def summarize_turns(self, task_id: str, turn_count: int, summary: str) -> None:
        """Store a summary for a set of turns."""
        self._storage.save_summary(task_id, summary, turn_count)

    def get_summary(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get the latest summary for a task."""
        return self._storage.get_summary(task_id)

    def get_turns_as_text(self, task_id: Optional[str] = None, limit: int = 20) -> str:
        """Render recent turns as a compact text block for LLM context."""
        turns = self.get_recent_turns(limit) if task_id is None else self.get_turns(task_id, limit)
        if not turns:
            return "<no_conversation_history/>"

        lines = ["<conversation_history>"]
        for t in turns:
            role_tag = "user" if t.role == "user" else "assistant"
            content = t.content[:200]  # truncate for context budget
            lines.append(f"  <{role_tag}>{content}</{role_tag}>")
        lines.append("</conversation_history>")
        return "\n".join(lines)
