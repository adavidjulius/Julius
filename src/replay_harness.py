"""
Deterministic Event Replay Harness for Julius AI Agent.

Records turn event trajectories, tool call payloads, and state diffs, enabling
deterministic replay for regression testing.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class EventTurnRecord:
    turn_index: int
    user_prompt: str
    tool_calls: List[Dict[str, Any]]
    final_output: str


class DeterministicReplayHarness:
    """Records and replays conversation turn trajectories."""

    def __init__(self, record_path: Optional[str] = None) -> None:
        self.record_path = Path(record_path) if record_path else None
        self.turns: List[EventTurnRecord] = []

    def record_turn(self, turn_index: int, user_prompt: str, tool_calls: List[Dict[str, Any]], final_output: str) -> EventTurnRecord:
        """Record a single conversation turn trajectory."""
        turn = EventTurnRecord(
            turn_index=turn_index,
            user_prompt=user_prompt,
            tool_calls=tool_calls,
            final_output=final_output,
        )
        self.turns.append(turn)
        if self.record_path:
            self.save()
        return turn

    def save(self) -> None:
        """Persist trajectory data to file."""
        if not self.record_path:
            return
        data = [
            {
                "turn_index": t.turn_index,
                "user_prompt": t.user_prompt,
                "tool_calls": t.tool_calls,
                "final_output": t.final_output,
            }
            for t in self.turns
        ]
        self.record_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def load(self) -> None:
        """Load trajectory data from file."""
        if not self.record_path or not self.record_path.exists():
            return
        raw = json.loads(self.record_path.read_text(encoding="utf-8"))
        self.turns = [EventTurnRecord(**item) for item in raw]
