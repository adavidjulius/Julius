"""
Julius Persistent Memory Engine.

Provides multi-tier persistent memory for Julius AI Agent Platform:
- Working State: persistent working state & resumption system across runs
"""

from __future__ import annotations

from .working_state import WorkingStateManager, TaskWorkingState

__all__ = [
    "WorkingStateManager",
    "TaskWorkingState",
]
