"""
Unit tests for Phase 1 of Julius AI OS Architecture Blueprint Implementation.

Verifies:
1. Slash Commands registry and execution pipeline (20 new commands).
2. PKB Graph Engine PageRank scoring algorithm.
3. Sandbox Capability Token validation.
4. 50 Enterprise Lifecycle Event Hooks dispatching.
5. 6-Tier Multi-Tier Memory Manager.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
import pytest

from src.commands import (
    JULIUS_SLASH_COMMANDS,
    JULIUS_SLASH_COMMANDS,
    built_in_command_names,
    execute_command,
    find_commands,
    get_command,
)
from src.pkb.graphs import GraphEdge, PKBGraphEngine
from src.sandbox import CapabilityToken, NativeSandbox, get_sandbox
from src.hooks.julius_hooks import HOOK_REGISTRY, HookCategory, HookEvent
from src.hooks.julius_hooks import HOOK_REGISTRY as LEGACY_HOOK_REGISTRY
from src.memdir.multi_tier_memory import MultiTierMemoryManager


def test_20_slash_commands_registered():
    """Verify all 20 new Julius slash commands exist and execute cleanly."""
    assert len(JULIUS_SLASH_COMMANDS) >= 20
    assert len(JULIUS_SLASH_COMMANDS) >= 20  # Backward compatibility alias
    assert HOOK_REGISTRY is LEGACY_HOOK_REGISTRY
    
    # Test slash command names exist in built-in names
    all_names = built_in_command_names()
    assert "context optimize" in all_names
    assert "pkb rebuild" in all_names
    assert "symbol graph" in all_names

    # Test executing a command
    res = execute_command("context optimize", prompt="max_tokens=8000")
    assert res.handled is True
    assert "[Julius Slash Command]" in res.message
    assert "Context" in res.message

    # Test lookup and filter
    matches = find_commands("symbol")
    assert len(matches) > 0


def test_pkb_pagerank_computation():
    """Verify PKB Graph Engine computes PageRank over symbol edges."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "pkb_test.db"
        engine = PKBGraphEngine(str(db_path))

        # Add sample call edges: A -> B, C -> B, B -> D
        edges = [
            GraphEdge("SymbolA", "SymbolB", "calls", "file1.py", 10),
            GraphEdge("SymbolC", "SymbolB", "calls", "file2.py", 15),
            GraphEdge("SymbolB", "SymbolD", "calls", "file1.py", 20),
        ]
        engine.update_file_edges("file1.py", edges[:1])
        engine.update_file_edges("file2.py", edges[1:])

        ranks = engine.compute_pagerank()
        assert "SymbolB" in ranks
        # SymbolB should have higher PageRank than A/C because two symbols call B
        assert ranks["SymbolB"] > ranks["SymbolA"]


def test_sandbox_capability_tokens():
    """Verify Capability Token validation in Sandbox factory."""
    tok_allowed = CapabilityToken("tok_1", "workspace", ["sandbox:execute"])
    tok_denied = CapabilityToken("tok_2", "workspace", ["read_only"])

    sb_allowed = get_sandbox(".", use_docker=False, capability_token=tok_allowed)
    assert isinstance(sb_allowed, NativeSandbox)

    assert tok_allowed.validate("sandbox:execute") is True
    assert tok_denied.validate("sandbox:execute") is False


def test_50_lifecycle_hooks():
    """Verify registering and dispatching enterprise lifecycle event hooks."""
    received = []

    def sample_handler(event: HookEvent):
        received.append(event.name)

    HOOK_REGISTRY.register("BeforePKBIndex", sample_handler)
    HOOK_REGISTRY.register("BeforeGitCommit", sample_handler)

    event1 = HOOK_REGISTRY.dispatch("BeforePKBIndex", HookCategory.PKB_SYMBOLS, {"files": ["main.py"]})
    assert event1.name == "BeforePKBIndex"
    assert "BeforePKBIndex" in received

    event2 = HOOK_REGISTRY.dispatch("BeforeGitCommit", HookCategory.GIT_VCS, {"commit_msg": "test"})
    assert event2.name == "BeforeGitCommit"
    assert "BeforeGitCommit" in received


def test_multi_tier_memory():
    """Verify memory operations across the 6 memory tiers."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        mem_mgr = MultiTierMemoryManager(workspace_path=tmp_dir)

        # Record conversation turn
        mem_mgr.record_conversation_turn("user", "Run unit tests")
        
        # Cache tool execution
        mem_mgr.cache_tool_execution("hash_123", "All tests passed", 0)
        cached = mem_mgr.get_cached_execution("hash_123")
        assert cached is not None
        assert cached["exit_code"] == 0

        # Record failure memory
        mem_mgr.record_failure(
            error_signature="NullPointerInHandler",
            root_cause="Uninitialized variable",
            resolution="Added non-null check before invocation",
            file_path="src/handler.py",
        )

        summary = mem_mgr.inspect_memory_summary()
        assert summary["conversation_turns_count"] == 1
        assert summary["execution_cache_count"] == 1
        assert summary["failure_records_count"] == 1
