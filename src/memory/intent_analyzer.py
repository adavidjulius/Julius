"""
Enhanced intent classification for memory-aware request routing.
Detects: continue_previous_task, memory_query, task_execution, information_query
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class Intent(Enum):
    CONTINUE_PREVIOUS_TASK = "continue_previous_task"
    MEMORY_QUERY = "memory_query"          # "what did I do yesterday", "show me past tasks"
    TASK_EXECUTION = "task_execution"       # normal task: "create parser", "fix bug"
    INFORMATION_QUERY = "information_query" # "what's the weather", "hello"
    STATUS_CHECK = "status_check"           # "what are you working on", "show state"


@dataclass
class IntentResult:
    intent: Intent
    confidence: float
    reason: str
    memory_query: Optional[str] = None  # extracted query for MEMORY_QUERY intents


# Patterns for memory-related queries
_CONTINUE_PATTERNS = [
    r"\bcontinue\b.*\b(previous|last|prior)\b.*\btask\b",
    r"\bcontinue\b.*\bwhere\b.*\bleft\s+off\b",
    r"\b(go\s+on|carry\s+on|keep\s+going)\b",
    r"\bresume\b",
    r"\bcontinue\b",
]

_MEMORY_QUERY_PATTERNS = [
    r"\bwhat\b.*\b(i|we)\b.*\b(do|did|work)\b",
    r"\bshow\b.*\b(me\s+)?\b(past|recent|previous|last)\b.*\btask",
    r"\blist\b.*\btask",
    r"\bwhat\b.*\b(happen|went\s+on)\b.*\b(yesterday|today|last\s+\w+)\b",
    r"\b(recall|remember|remind)\b",
    r"\bwhat\b.*\b(current|active)\b.*\b(state|status|task|goal)\b",
    r"\b(show|display)\b.*\b(memory|state|status)\b",
    r"\bhow\b.*\bfar\b.*\balong\b",
    r"\bwhat\s+(are|is)\b.*\b(you\s+)?\b(working\s+on|doing)\b",
]

_STATUS_PATTERNS = [
    r"\bstatus\b",
    r"\b(what|show)\b.*\b(state|memory|active|current)\b",
    r"\bhow\b.*\b(are\s+you|it\s+going)\b",
]


class IntentAnalyzer:
    """Analyzes user input to determine the intent. Memory-aware."""

    def __init__(self) -> None:
        self._continue_re = re.compile('|'.join(_CONTINUE_PATTERNS), re.IGNORECASE)
        self._memory_query_re = re.compile('|'.join(_MEMORY_QUERY_PATTERNS), re.IGNORECASE)
        self._status_re = re.compile('|'.join(_STATUS_PATTERNS), re.IGNORECASE)

    def analyze(self, query: str) -> IntentResult:
        """Analyze a user query and return classified intent."""
        q = query.strip()
        q_lower = q.lower()

        if not q_lower:
            return IntentResult(Intent.TASK_EXECUTION, 0.5, "Empty query", None)

        # Check for continue intent first (highest priority)
        continue_match = self._continue_re.search(q_lower)
        if continue_match and ("continue" in q_lower or "resume" in q_lower):
            return IntentResult(
                Intent.CONTINUE_PREVIOUS_TASK, 0.9,
                f"Continue pattern matched: '{continue_match.group(0)}'",
                None,
            )

        # Check for memory query
        memory_match = self._memory_query_re.search(q_lower)
        if memory_match:
            # Extract the actual query from the text
            extracted = self._extract_memory_query(q)
            return IntentResult(
                Intent.MEMORY_QUERY, 0.85,
                f"Memory query pattern matched: '{memory_match.group(0)}'",
                extracted,
            )

        # Check for status check
        if self._status_re.search(q_lower) and len(q.split()) <= 8:
            return IntentResult(
                Intent.STATUS_CHECK, 0.8,
                "Short status-oriented query",
                None,
            )

        # Default to task execution
        return IntentResult(
            Intent.TASK_EXECUTION, 0.7,
            "Defaulting to task execution",
            None,
        )

    def _extract_memory_query(self, query: str) -> str:
        """Extract the subject of a memory query."""
        # Remove common prefixes
        cleaned = re.sub(
            r"^(?:what\s+(?:did\s+)?|show\s+(?:me\s+)?|list\s+|recall\s+|remember\s+|tell\s+me\s+(?:about\s+)?)",
            "", query, flags=re.IGNORECASE,
        ).strip()
        return cleaned or query

    def is_continuation(self, query: str) -> bool:
        return self.analyze(query).intent == Intent.CONTINUE_PREVIOUS_TASK

    def is_memory_query(self, query: str) -> bool:
        return self.analyze(query).intent == Intent.MEMORY_QUERY

    def is_task(self, query: str) -> bool:
        return self.analyze(query).intent == Intent.TASK_EXECUTION
