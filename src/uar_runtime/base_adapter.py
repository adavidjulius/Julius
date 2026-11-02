"""UAR Runtime Base Adapter models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ActionResult:
    success: bool
    output: str
    error: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)
