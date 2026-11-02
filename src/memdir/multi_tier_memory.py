"""
Julius Multi-Tier Memory Subsystem.

Implements unified access, persistence, and isolation across 6 memory tiers:
1. Project Memory (Rules & JULIUS.md / .julius/rules)
2. Agent Memory (Active task DAG & state)
3. Conversation Memory (Turn transcript history)
4. Execution Memory (Command cache & tool outputs)
5. Knowledge Memory (PKB Symbol & reference graph)
6. Failure Memory (Anti-patterns & bug fix history)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class FailureMemoryRecord:
    error_signature: str
    root_cause: str
    resolution: str
    file_path: Optional[str] = None
    timestamp: float = 0.0


class MultiTierMemoryManager:
    """Unified Memory Manager orchestrating all 6 memory tiers for Julius AI Agent Platform."""

    def __init__(self, workspace_path: str = ".") -> None:
        self.workspace_path = Path(workspace_path).resolve()
        julius_dir = self.workspace_path / ".julius"
        legacy_dir = self.workspace_path / ".julius"
        self.julius_dir = julius_dir if julius_dir.exists() or not legacy_dir.exists() else legacy_dir
        self.julius_dir = self.julius_dir  # Backward compatibility alias
        self.memory_dir = self.julius_dir / "memory"
        self.memory_dir.mkdir(parents=True, exist_ok=True)

        # In-Memory caches for performance
        self._project_memory: Dict[str, Any] = {}
        self._agent_memory: Dict[str, Any] = {}
        self._conversation_turns: List[Dict[str, Any]] = []
        self._execution_cache: Dict[str, Any] = {}
        self._knowledge_cache: Dict[str, Any] = {}
        self._failure_memory: List[FailureMemoryRecord] = []

        self._load_persistent_memories()

    def _load_persistent_memories(self) -> None:
        """Load persistent memories from workspace `.julius/memory/` files."""
        # 1. Project Memory (.julius/rules, JULIUS.md, or legacy fallbacks)
        julius_md = self.workspace_path / "JULIUS.md"
        julius_md = self.workspace_path / "JULIUS.md"
        rules_path = self.julius_dir / "rules"
        rules_text = ""
        if rules_path.exists():
            rules_text = rules_path.read_text(encoding="utf-8")
        elif julius_md.exists():
            rules_text = julius_md.read_text(encoding="utf-8")
        elif julius_md.exists():
            rules_text = julius_md.read_text(encoding="utf-8")
        self._project_memory["rules"] = rules_text

        # 6. Failure Memory (.julius/memory/failures.json)
        fail_file = self.memory_dir / "failures.json"
        if fail_file.exists():
            try:
                raw_data = json.loads(fail_file.read_text(encoding="utf-8"))
                self._failure_memory = [
                    FailureMemoryRecord(**item) for item in raw_data
                ]
            except Exception as exc:
                logger.warning(f"Could not parse failure memory store: {exc}")

    def get_project_rules(self) -> str:
        return self._project_memory.get("rules", "")

    def record_conversation_turn(self, role: str, content: str, tool_calls: Optional[List[Dict[str, Any]]] = None) -> None:
        """Record turn into Conversation Memory."""
        self._conversation_turns.append({
            "role": role,
            "content": content,
            "tool_calls": tool_calls or [],
        })

    def cache_tool_execution(self, command_hash: str, output: str, exit_code: int) -> None:
        """Record command result in Execution Memory."""
        self._execution_cache[command_hash] = {
            "output": output,
            "exit_code": exit_code,
        }

    def get_cached_execution(self, command_hash: str) -> Optional[Dict[str, Any]]:
        return self._execution_cache.get(command_hash)

    def record_failure(self, error_signature: str, root_cause: str, resolution: str, file_path: Optional[str] = None) -> None:
        """Record anti-pattern / bug fix into Failure Memory."""
        record = FailureMemoryRecord(
            error_signature=error_signature,
            root_cause=root_cause,
            resolution=resolution,
            file_path=file_path,
        )
        self._failure_memory.append(record)

        # Save to disk
        fail_file = self.memory_dir / "failures.json"
        try:
            records_data = [
                {
                    "error_signature": r.error_signature,
                    "root_cause": r.root_cause,
                    "resolution": r.resolution,
                    "file_path": r.file_path,
                    "timestamp": r.timestamp,
                }
                for r in self._failure_memory
            ]
            fail_file.write_text(json.dumps(records_data, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.error(f"Failed to persist failure memory: {exc}")

    def inspect_memory_summary(self) -> Dict[str, Any]:
        """Return summary metrics for all 6 memory tiers."""
        return {
            "project_rules_length": len(self.get_project_rules()),
            "conversation_turns_count": len(self._conversation_turns),
            "execution_cache_count": len(self._execution_cache),
            "failure_records_count": len(self._failure_memory),
            "agent_memory_active_tasks": len(self._agent_memory),
            "knowledge_cache_entries": len(self._knowledge_cache),
        }
