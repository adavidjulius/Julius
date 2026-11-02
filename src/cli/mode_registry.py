"""
Mode Registry for Julius CLI interaction modes.

Provides extensible registry for interaction modes (/plan, /act, etc.)
and risk-based routing for bare tasks.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Any, Dict, Optional
from ..agent_config import DESTRUCTIVE_ACTIONS


@dataclass
class ModeResolveResult:
    mode: str  # 'plan' | 'act' | custom
    task: str
    requires_plan: bool
    is_destructive: bool


class ModeRegistry:
    """Registry managing interaction modes like /plan and /act."""

    def __init__(self) -> None:
        self._modes: Dict[str, Dict[str, Any]] = {}
        self._register_default_modes()

    def register(self, name: str, description: str, handler: Optional[Callable] = None) -> None:
        """Register a new interaction mode."""
        self._modes[name.lower()] = {
            "name": name.lower(),
            "description": description,
            "handler": handler,
        }

    def _register_default_modes(self) -> None:
        self.register("plan", "Analyze task and propose plan without executing actions")
        self.register("act", "Execute task directly without approval gate")
        self.register("new", "Reset conversation to a fresh chat on the open browser session")
        self.register("experiments", "Display recent research experiment history and outcome metrics")
        self.register("status", "Show system health, Docker status, sandbox state, and environment metrics")
        self.register("resume", "View and select from active/incomplete tasks for resumption")
        self.register("undo", "Rollback last file mutations using workspace ledger")
        self.register("copy", "Copy latest response or full conversation transcript to clipboard")
        self.register("exit", "Close browser and exit Julius CLI")
        self.register("help", "Display available commands and interaction modes")
        self.register("julius", "Display Julius assistant status and version")
        self.register("julius", "Deprecated alias for /julius")

    def resolve(self, raw_input: str) -> ModeResolveResult:
        """
        Resolve user input string to a mode and task prompt.
        
        If raw_input starts with /<mode>, extract mode and task.
        If unprefixed, evaluate task against safety policy & destructive keywords:
          - High risk -> defaults to /plan
          - Low risk -> defaults to /act
        """
        cleaned = raw_input.strip()
        if cleaned.startswith('/'):
            parts = cleaned.split(maxsplit=1)
            mode_name = parts[0][1:].lower()
            task_prompt = parts[1] if len(parts) > 1 else ''
            if mode_name in self._modes:
                return ModeResolveResult(
                    mode=mode_name,
                    task=task_prompt,
                    requires_plan=(mode_name == 'plan'),
                    is_destructive=self.is_destructive_prompt(task_prompt),
                )

        # Unprefixed prompt
        is_destructive = self.is_destructive_prompt(cleaned)
        if is_destructive:
            return ModeResolveResult(
                mode='plan',
                task=cleaned,
                requires_plan=True,
                is_destructive=True,
            )
        return ModeResolveResult(
            mode='act',
            task=cleaned,
            requires_plan=False,
            is_destructive=False,
        )

    @staticmethod
    def is_destructive_prompt(task_prompt: str) -> bool:
        """Check if task prompt implies destructive filesystem or bash operations."""
        prompt_lower = task_prompt.lower()
        destructive_keywords = {
            'delete', 'remove', 'rm ', 'unlink', 'overwrite', 'drop',
            'destroy', 'wipe', 'reset', 'clear', 'uninstall', 'format',
            'truncate', 'kill', 'purge'
        }
        for kw in destructive_keywords:
            if kw in prompt_lower:
                return True
        return False


# Global default registry instance
global_mode_registry = ModeRegistry()
