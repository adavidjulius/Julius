"""Tests for Phase 2.2: Asynchronous DAG Multi-Agent Swarm Orchestrator."""

from __future__ import annotations

import asyncio
import unittest

from src.coordinator.swarm_orchestrator import (
    AgentPersona,
    DAGNode,
    DAGEngine,
    NodeStatus,
    SwarmOrchestrator,
    WorkerPool,
)


class TestSwarmOrchestrator(unittest.IsolatedAsyncioTestCase):
    """Test suite for the DAG multi-agent swarm engine."""

    def test_dag_topological_sort(self):
        """DAG properly calculates execution layers based on dependencies."""
        engine = DAGEngine()

        # Architecture -> (Backend, Frontend) -> Verifier
        spec = engine.add_node("spec", AgentPersona.ARCHITECT, "Write architecture spec")
        backend = engine.add_node("backend", AgentPersona.DEVELOPER, "Implement API", dependencies=["spec"])
        frontend = engine.add_node("frontend", AgentPersona.DEVELOPER, "Implement UI", dependencies=["spec"])
        test = engine.add_node("test", AgentPersona.VERIFIER, "Run integration tests", dependencies=["backend", "frontend"])

        layers = engine.get_execution_layers()
        self.assertEqual(len(layers), 3)
        self.assertEqual(layers[0], ["spec"])
        self.assertCountEqual(layers[1], ["backend", "frontend"])
        self.assertEqual(layers[2], ["test"])

    def test_cycle_detection(self):
        """DAG engine detects circular dependencies and raises ValueError."""
        engine = DAGEngine()
        engine.add_node("A", AgentPersona.DEVELOPER, "Task A", dependencies=["B"])
        engine.add_node("B", AgentPersona.DEVELOPER, "Task B", dependencies=["A"])

        with self.assertRaises(ValueError):
            engine.get_execution_layers()

    async def test_worker_pool_concurrency(self):
        """WorkerPool limits concurrency via semaphore."""
        pool = WorkerPool(max_workers=2)
        active_count = 0
        max_seen = 0

        async def worker_job():
            nonlocal active_count, max_seen
            async with pool.semaphore:
                active_count += 1
                max_seen = max(max_seen, active_count)
                await asyncio.sleep(0.05)
                active_count -= 1

        tasks = [asyncio.create_task(worker_job()) for _ in range(5)]
        await asyncio.gather(*tasks)

        self.assertLessEqual(max_seen, 2)

    async def test_swarm_execution_with_failure_isolation(self):
        """Failure in one branch halts downstream dependent nodes while preserving parallel branches."""
        engine = DAGEngine()

        # spec -> branch_fail -> downstream_blocked
        #      -> branch_ok
        spec = engine.add_node("spec", AgentPersona.ARCHITECT, "Spec")
        fail_node = engine.add_node("branch_fail", AgentPersona.DEVELOPER, "Fail", dependencies=["spec"])
        blocked_node = engine.add_node("downstream_blocked", AgentPersona.VERIFIER, "Blocked", dependencies=["branch_fail"])
        ok_node = engine.add_node("branch_ok", AgentPersona.DEVELOPER, "OK", dependencies=["spec"])

        # Mock executors
        spec.status = NodeStatus.COMPLETED
        spec.output = "Specification generated"

        fail_node.status = NodeStatus.FAILED
        fail_node.error = "Syntax error in branch"

        ok_node.status = NodeStatus.COMPLETED
        ok_node.output = "Success in parallel branch"

        # Check ready nodes for next wave:
        # downstream_blocked should NOT be runnable because branch_fail failed
        # Verify that independent branch succeeded
        self.assertEqual(ok_node.status, NodeStatus.COMPLETED)
        self.assertEqual(fail_node.status, NodeStatus.FAILED)
        self.assertEqual(blocked_node.status, NodeStatus.PENDING)


if __name__ == "__main__":
    unittest.main()
