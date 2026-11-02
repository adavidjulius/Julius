"""Base Skill specification and abstract interface for production catalog skills."""

from __future__ import annotations

from typing import Any, Dict
from ..uar_runtime.base_adapter import ActionResult


class StandardSkill:
    """Abstract base class for standard production skills."""

    async def initialize(self, skill_config: Dict[str, Any]) -> bool:
        return True

    async def health(self) -> Dict[str, Any]:
        return {"status": "ok"}

    async def observe(self) -> Dict[str, Any]:
        return {}

    async def execute(self, action: Dict[str, Any]) -> ActionResult:
        return ActionResult(success=True, output="Skill executed successfully.")

    async def verify(self, criteria: Dict[str, Any]) -> bool:
        return True

    async def recover(self, error: Exception) -> bool:
        return True

    async def rollback(self) -> bool:
        return True

    async def cleanup(self) -> None:
        pass

    async def shutdown(self) -> None:
        pass
