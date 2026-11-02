"""
Julius Enterprise Lifecycle Event Hooks System.

Provides 50 fine-grained lifecycle hooks across 10 system categories for intercepting,
auditing, and extending Julius AI Agent workflows.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class HookCategory(Enum):
    PKB_SYMBOLS = "pkb_symbols"
    BUILD_COMPILATION = "build_compilation"
    GIT_VCS = "git_vcs"
    TOOL_RUNTIME = "tool_runtime"
    MULTI_AGENT = "multi_agent"
    VERIFICATION_TESTING = "verification_testing"
    SECURITY_GOVERNANCE = "security_governance"
    CONTEXT_COMPRESSION = "context_compression"
    MEMORY_LEARNING = "memory_learning"
    ENVIRONMENT_RUNTIME = "environment_runtime"


JULIUS_50_HOOKS = [
    # Category A: PKB & Symbol Events
    "BeforePKBIndex", "AfterPKBIndex", "OnSymbolDiscovered", "OnSymbolModified", "BeforeSymbolGraphQuery",
    # Category B: Build & Compilation
    "BeforeBuild", "AfterBuildSuccess", "OnBuildFailure", "BeforeTypeCheck", "AfterTypeCheckFailure",
    # Category C: Version Control & Git
    "BeforeGitCommit", "AfterGitCommit", "BeforeBranchSwitch", "OnGitConflict", "BeforeRollback",
    # Category D: Tool Runtime & Sandboxing
    "BeforeToolExecute", "AfterToolSuccess", "AfterToolFailure", "OnToolTimeout", "OnToolPermissionDenied",
    # Category E: Multi-Agent & Orchestration
    "BeforeAgentSpawn", "AfterAgentComplete", "OnAgentFailure", "OnAgentTaskBlocked", "BeforeAgentHandoff",
    # Category F: Verification & Testing
    "BeforeTestRun", "AfterTestSuccess", "OnTestFailure", "BeforeCoverageCheck", "OnRegressionDetected",
    # Category G: Security & Governance
    "BeforeShellExecute", "OnSecretDetected", "BeforeFileWrite", "OnPermissionViolation", "BeforeExternalNetworkCall",
    # Category H: Context Management & Compression
    "BeforeContextCompress", "AfterContextCompress", "OnTokenLimitWarning", "BeforePromptAssembly", "AfterPromptAssembly",
    # Category I: Memory & Learning
    "BeforeAutoMemoryUpdate", "AfterAutoMemoryUpdate", "OnFailureRecorded", "OnPatternLearned", "BeforeMemoryClear",
    # Category J: Environment & Runtime State
    "OnSessionStart", "OnSessionEnd", "OnFileCreated", "OnFileDeleted", "OnConfigChanged",
]

# Backward compatibility alias
JULIUS_50_HOOKS = JULIUS_50_HOOKS


@dataclass
class HookEvent:
    name: str
    category: HookCategory
    payload: Dict[str, Any] = field(default_factory=dict)
    cancelled: bool = False
    error: Optional[Exception] = None


HookHandler = Callable[[HookEvent], None]


class JuliusHookRegistry:
    """Central manager for subscribing to and dispatching Julius lifecycle event hooks."""

    def __init__(self) -> None:
        self._handlers: Dict[str, List[HookHandler]] = {hook: [] for hook in JULIUS_50_HOOKS}

    def register(self, hook_name: str, handler: HookHandler) -> None:
        if hook_name not in self._handlers:
            self._handlers[hook_name] = []
        self._handlers[hook_name].append(handler)
        logger.debug(f"Registered handler for hook: {hook_name}")

    def dispatch(self, hook_name: str, category: HookCategory, payload: Dict[str, Any]) -> HookEvent:
        event = HookEvent(name=hook_name, category=category, payload=payload)
        handlers = self._handlers.get(hook_name, [])
        for handler in handlers:
            try:
                handler(event)
                if event.cancelled:
                    logger.warning(f"Hook event {hook_name} cancelled by handler {handler}")
                    break
            except Exception as exc:
                event.error = exc
                logger.error(f"Error executing hook handler for {hook_name}: {exc}")
        return event


# Backward compatibility alias
JuliusHookRegistry = JuliusHookRegistry

# Global Singleton instance
HOOK_REGISTRY = JuliusHookRegistry()
