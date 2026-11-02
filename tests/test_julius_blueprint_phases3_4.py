"""
Unit tests for Phases 3 & 4 of Julius AI OS Architecture Blueprint Implementation.

Verifies:
1. VirtualWorktreeManager worktree creation, fallback, and cleanup.
2. TaskDAGScheduler dependency ordering, execution status, and skip propagation.
3. WasmPluginEngine WASM plugin sandbox and capability validation.
4. SwarmOrchestrator multi-agent task delegation and aggregation.
5. VerificationEngine automated syntax checking.
6. DeterministicReplayHarness turn recording and persistence.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
import pytest

from src.vcs.worktree_manager import VirtualWorktreeManager
from src.planner.dag_scheduler import TaskDAGScheduler, TaskStatus
from src.plugins.wasm_runtime import WasmPluginEngine, WasmPluginManifest
from src.coordinator.swarm_orchestrator import SwarmOrchestrator, AgentPersona
from src.verification_engine import VerificationEngine
from src.replay_harness import DeterministicReplayHarness
from src.sandbox import CapabilityToken


def test_virtual_worktree_manager():
    """Verify ephemeral worktree transaction creation and rollback."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        # Create sample workspace file
        file_path = Path(tmp_dir) / "app.py"
        file_path.write_text("print('Hello World')", encoding="utf-8")

        mgr = VirtualWorktreeManager(workspace_root=tmp_dir)
        txn = mgr.create_transaction()

        assert txn.worktree_path.exists()
        assert (txn.worktree_path / "app.py").exists()

        mgr.rollback_transaction(txn)
        assert not txn.worktree_path.exists()
        assert txn.active is False


def test_dag_scheduler():
    """Verify TaskDAGScheduler dependency ordering and status machine."""
    scheduler = TaskDAGScheduler()

    # Add Node A (no deps) and Node B (depends on A)
    scheduler.add_node("node_a", "ParseCode")
    scheduler.add_node("node_b", "RefactorCode", dependencies={"node_a"})

    ready = scheduler.get_ready_nodes()
    assert len(ready) == 1
    assert ready[0].node_id == "node_a"

    # Mark A completed -> B becomes ready
    scheduler.mark_completed("node_a", result={"status": "ok"})
    ready_after = scheduler.get_ready_nodes()
    assert len(ready_after) == 1
    assert ready_after[0].node_id == "node_b"

    scheduler.mark_completed("node_b")
    assert scheduler.is_finished() is True


def test_dag_scheduler_failure_propagation():
    """Verify task failure skips dependent downstream nodes."""
    scheduler = TaskDAGScheduler()
    scheduler.add_node("node_x", "BuildStep")
    scheduler.add_node("node_y", "DeployStep", dependencies={"node_x"})

    scheduler.mark_failed("node_x", error="Compilation error")
    assert scheduler.nodes["node_x"].status == TaskStatus.FAILED
    assert scheduler.nodes["node_y"].status == TaskStatus.SKIPPED


def test_wasm_plugin_engine():
    """Verify WASM plugin execution and capability checking."""
    engine = WasmPluginEngine()
    manifest = WasmPluginManifest(
        plugin_id="sec_scanner",
        name="Security Scanner",
        version="1.0.0",
        capabilities=["plugin:sec_scanner"],
        wasm_bytes=b"\x00asm\x01\x00\x00\x00",
    )
    engine.load_plugin(manifest)

    tok_allowed = CapabilityToken("tok_1", "security", ["plugin:sec_scanner"])
    tok_denied = CapabilityToken("tok_2", "security", ["other_permission"])

    res_allowed = engine.execute_hook("sec_scanner", "PreToolUse", {}, capability_token=tok_allowed)
    assert res_allowed["status"] == "SUCCESS"

    res_denied = engine.execute_hook("sec_scanner", "PreToolUse", {}, capability_token=tok_denied)
    assert res_denied["status"] == "DENIED"


def test_swarm_orchestrator():
    """Verify multi-agent swarm task delegation and result aggregation."""
    swarm = SwarmOrchestrator()
    task1 = swarm.dispatch_subtask(AgentPersona.SECURITY_AUDITOR, "Audit auth handler")
    task2 = swarm.dispatch_subtask(AgentPersona.TESTER, "Generate unit test coverage")

    assert task1.status == "PENDING"
    swarm.execute_subtask(task1.subtask_id)
    swarm.execute_subtask(task2.subtask_id)

    agg = swarm.aggregate_results()
    assert agg["total_tasks"] == 2
    assert agg["completed_tasks"] == 2


def test_verification_engine():
    """Verify system verification syntax checking."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        py_file = Path(tmp_dir) / "valid.py"
        py_file.write_text("x = 10\nprint(x)\n", encoding="utf-8")

        verifier = VerificationEngine(workspace_root=tmp_dir)
        res = verifier.verify_syntax(str(py_file))
        assert res.passed is True


def test_replay_harness():
    """Verify trajectory recording and persistence."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        rec_file = Path(tmp_dir) / "trajectory.json"
        harness = DeterministicReplayHarness(record_path=str(rec_file))

        harness.record_turn(
            turn_index=1,
            user_prompt="Run unit tests",
            tool_calls=[{"tool": "BashTool", "cmd": "pytest"}],
            final_output="All tests passed",
        )

        assert rec_file.exists()

        harness2 = DeterministicReplayHarness(record_path=str(rec_file))
        harness2.load()
        assert len(harness2.turns) == 1
        assert harness2.turns[0].user_prompt == "Run unit tests"
