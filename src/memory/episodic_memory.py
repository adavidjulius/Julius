"""
Episodic memory: day-level "notebook" summaries.
Like a software engineer's notebook capturing what happened each day.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, List, Optional

from .storage import MemoryStorage

logger = logging.getLogger(__name__)


class EpisodicMemory:
    """Day-level episodic notes — "Yesterday: Refactored parser. Bug: Tokenizer broken." """

    def __init__(self, storage: MemoryStorage) -> None:
        self._storage = storage

    def record_note(self, summary: str, task_ids: Optional[List[str]] = None,
                    note_date: Optional[str] = None) -> None:
        """Record an episodic note for a given date (defaults to today)."""
        if note_date is None:
            note_date = date.today().isoformat()
        self._storage.save_episodic_note(note_date, summary, task_ids or [])
        logger.info(f"EpisodicMemory: Recorded note for {note_date}")

    def get_recent_notes(self, limit: int = 30) -> List[Dict[str, Any]]:
        """Get recent episodic notes."""
        return self._storage.get_episodic_notes(limit=limit)

    def search_notes(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search episodic notes by content."""
        return self._storage.search_episodic_notes(query, limit=limit)

    def to_prompt_block(self, limit: int = 7) -> str:
        """Render recent episodic notes as a compact prompt block."""
        notes = self.get_recent_notes(limit=limit)
        if not notes:
            return "<no_episodic_memory/>"

        lines = ["<episodic_memory>"]
        for n in notes:
            lines.append(f"  [{n['date']}] {n['summary'][:200]}")
        lines.append("</episodic_memory>")
        return "\n".join(lines)
