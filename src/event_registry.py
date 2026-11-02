"""
Julius Event Registry and Schemas.

Defines the single source of truth for all backend event types emitted across
WebAgent, SelfHealer, ActionExecutor, and AppBuilder.
"""

from enum import Enum
from typing import Any, Dict, Optional, Set
from dataclasses import dataclass, field
import time


class JuliusEventType(str, Enum):
    """Enumeration of all valid event types emitted by Julius backend components."""

    THOUGHT = "thought"
    ASK_USER_QUESTION = "ask_user_question"
    CONFIRM_ACTION = "confirm_action"
    ACTION = "action"
    STATUS = "status"
    STEP_START = "step_start"
    STREAM = "stream"
    STREAM_END = "stream_end"
    ERROR = "error"
    RESULT = "result"
    HEAL_START = "heal_start"
    HEAL_STEP = "heal_step"
    HEAL_SUCCESS = "heal_success"
    HEAL_FAILED = "heal_failed"
    DONE = "done"
    CONVERSE = "converse"
    FINISHED = "finished"
    PIPELINE = "pipeline"
    PLAN_APPROVAL_REQUESTED = "plan_approval_requested"
    MUSIC_PROGRESS = "music_progress"
    WHATSAPP_STATUS = "whatsapp_status"
    WHATSAPP_MESSAGE = "whatsapp_message"
    WHATSAPP_APPROVAL = "whatsapp_approval"


@dataclass
class JuliusEvent:
    """Standardized event structure for Julius communication."""

    type: JuliusEventType
    timestamp: float = field(default_factory=time.time)
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary for callbacks."""
        res = {"type": self.type.value, "timestamp": self.timestamp}
        res.update(self.data)
        return res


ALL_EVENT_TYPES: Set[str] = {e.value for e in JuliusEventType}
