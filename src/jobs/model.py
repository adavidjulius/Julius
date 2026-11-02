"""
Job Data Models & Lifecycle States (WS6.2).
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

JobStatus = Literal["queued", "running", "paused", "completed", "failed", "cancelled"]


@dataclass
class JobBudgets:
    """Resource limits for an individual job."""
    max_steps: int = 50
    max_wall_time_seconds: int = 900
    max_tokens: int = 500_000
    max_cost_usd: float = 5.0
    max_consecutive_tool_errors: int = 5


@dataclass
class Job:
    """Execution unit for an autonomous agent task."""
    task: str
    id: str = field(default_factory=lambda: f"job_{uuid.uuid4().hex[:12]}")
    workspace: str = "."
    status: JobStatus = "queued"
    priority: int = 0
    policy_profile: str = "developer"
    budgets: JobBudgets = field(default_factory=JobBudgets)
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    error: Optional[str] = None
    output: Optional[str] = None
    step_count: int = 0
    tokens_used: int = 0
    cost_usd: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

