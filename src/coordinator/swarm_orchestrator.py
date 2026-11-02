"""
Asynchronous DAG Multi-Agent Swarm Orchestrator.

Phase 2.2 — Milestone 2.2: Replaces the synchronous mock orchestrator with a
true Directed Acyclic Graph (DAG) task engine featuring:
  - Nodes: Independent atomic subtasks (spec, code, audit, test)
  - Edges: Context dependency and execution flow
  - Specialized Worker Personas: Architect, Developer, SecurityAuditor, Verifier
  - Real async dispatch using asyncio.TaskGroup with isolated LLM message histories
  - Bidirectional result streaming into the frontend timeline
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


# ── Worker Personas ───────────────────────────────────────────────────────────

class AgentPersona(str, Enum):
    ARCHITECT = "architect"
    DEVELOPER = "developer"
    SECURITY_AUDITOR = "security_auditor"
    VERIFIER = "verifier"
    REFACTORER = "refactorer"
    GENERAL_ENGINEER = "general_engineer"
    PERFORMANCE_SPECIALIST = "performance_specialist"
    TESTER = "tester"

    @property
    def system_prompt(self) -> str:
        """Return the persona-specific system prompt."""
        prompts = {
            "architect": (
                "You are ArchitectAgent, a senior software architect. "
                "Generate detailed specifications, interface designs, and module boundaries. "
                "Focus on clean abstractions, dependency management, and scalability."
            ),
            "developer": (
                "You are DeveloperAgent, an expert software developer. "
                "Implement code in isolated branches following the specification. "
                "Write clean, well-documented, production-ready code."
            ),
            "security_auditor": (
                "You are SecurityAuditorAgent, a security specialist. "
                "Perform static analysis, secret scanning, and vulnerability assessment. "
                "Flag any security issues with severity ratings."
            ),
            "verifier": (
                "You are VerifierAgent, a QA/testing specialist. "
                "Execute test suites, parse telemetry, and verify acceptance criteria. "
                "Report pass/fail status with detailed diagnostics."
            ),
            "refactorer": (
                "You are RefactorerAgent, a code quality specialist. "
                "Improve code structure, reduce duplication, and enhance readability."
            ),
            "general_engineer": (
                "You are a general software engineer. "
                "Handle a variety of development tasks competently."
            ),
            "performance_specialist": (
                "You are PerformanceAgent, a performance optimization specialist. "
                "Profile, benchmark, and optimize code for speed and memory efficiency."
            ),
            "tester": (
                "You are TesterAgent, a testing specialist. "
                "Write comprehensive test suites and validate functionality."
            ),
        }
        return prompts.get(self.value, prompts["general_engineer"])


# ── Task Status ───────────────────────────────────────────────────────────────

class TaskStatus(str, Enum):
    PENDING = "PENDING"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    SKIPPED = "SKIPPED"

# Alias for NodeStatus
NodeStatus = TaskStatus


# ── DAG Node (Subtask) ───────────────────────────────────────────────────────

@dataclass
class DAGNode:
    """A single node in the task DAG representing an atomic subtask."""
    node_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    persona: AgentPersona = AgentPersona.GENERAL_ENGINEER
    prompt: str = ""
    context: Dict[str, Any] = field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[str] = None
    error: Optional[str] = None
    dependencies: Set[str] = field(default_factory=set)  # Set of node_ids this depends on
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def duration_ms(self) -> float | None:
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time) * 1000
        return None

    @property
    def output(self) -> Optional[str]:
        return self.result

    @output.setter
    def output(self, value: Optional[str]) -> None:
        self.result = value

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "name": self.name,
            "persona": self.persona.value,
            "status": self.status.value,
            "dependencies": list(self.dependencies),
            "duration_ms": self.duration_ms,
            "result_preview": (self.result[:200] + "...") if self.result and len(self.result) > 200 else self.result,
            "error": self.error,
        }


# ── DAG Edge ──────────────────────────────────────────────────────────────────

@dataclass
class DAGEdge:
    """An edge in the DAG representing a dependency relationship."""
    from_node: str  # node_id of the dependency
    to_node: str    # node_id of the dependent
    edge_type: str = "data"  # "data" | "control" | "context"


# ── Worker Pool ──────────────────────────────────────────────────────────────

class WorkerPool:
    """Pool of async workers for executing DAG nodes concurrently.

    Each worker maintains an isolated LLM message history scoped to its
    persona and subtask context.
    """

    def __init__(
        self,
        max_workers: int = 4,
        executor_func: Optional[Callable] = None,
    ) -> None:
        self.max_workers = max_workers
        self._executor_func = executor_func
        self._semaphore = asyncio.Semaphore(max_workers)
        self._active_workers: int = 0

    @property
    def semaphore(self) -> asyncio.Semaphore:
        """Concurrency semaphore for the worker pool."""
        return self._semaphore

    async def execute_node(
        self,
        node: DAGNode,
        upstream_results: Dict[str, str],
        on_event: Optional[Callable] = None,
    ) -> DAGNode:
        """Execute a single DAG node with concurrency limiting.

        Args:
            node: The DAG node to execute.
            upstream_results: Results from dependency nodes.
            on_event: Callback for streaming status events.

        Returns:
            The updated DAGNode with result or error.
        """
        async with self._semaphore:
            self._active_workers += 1
            node.status = TaskStatus.RUNNING
            node.start_time = time.time()

            if on_event:
                on_event({
                    "type": "swarm.node_started",
                    "node_id": node.node_id,
                    "name": node.name,
                    "persona": node.persona.value,
                })

            try:
                # Build isolated context with upstream results
                execution_context = {
                    **node.context,
                    "upstream_results": upstream_results,
                    "persona_prompt": node.persona.system_prompt,
                }

                if self._executor_func:
                    # Real LLM execution
                    result = await self._executor_func(
                        node.persona,
                        node.prompt,
                        execution_context,
                    )
                    node.result = str(result) if result else ""
                else:
                    # Mock execution for testing
                    await asyncio.sleep(0.1)
                    node.result = (
                        f"[{node.persona.value}] Completed: {node.name} — "
                        f"{node.prompt[:80]}..."
                    )

                node.status = TaskStatus.COMPLETED
                node.end_time = time.time()

                if on_event:
                    on_event({
                        "type": "swarm.node_completed",
                        "node_id": node.node_id,
                        "name": node.name,
                        "persona": node.persona.value,
                        "duration_ms": node.duration_ms,
                        "result_preview": node.result[:200] if node.result else "",
                    })

                logger.info(
                    "DAG node completed: %s [%s] in %.0fms",
                    node.name, node.persona.value, node.duration_ms or 0,
                )

            except asyncio.CancelledError:
                node.status = TaskStatus.CANCELLED
                node.end_time = time.time()
                if on_event:
                    on_event({
                        "type": "swarm.node_cancelled",
                        "node_id": node.node_id,
                        "name": node.name,
                    })
                raise

            except Exception as exc:
                node.status = TaskStatus.FAILED
                node.error = str(exc)
                node.end_time = time.time()

                if on_event:
                    on_event({
                        "type": "swarm.node_failed",
                        "node_id": node.node_id,
                        "name": node.name,
                        "error": str(exc),
                    })

                logger.error("DAG node failed: %s — %s", node.name, exc)

            finally:
                self._active_workers -= 1

            return node


# ── DAG Engine ────────────────────────────────────────────────────────────────

class DAGEngine:
    """Directed Acyclic Graph execution engine.

    Topologically sorts nodes, identifies parallelizable groups, and
    dispatches them through the WorkerPool. Failure in one branch halts
    downstream dependent nodes while preserving parallel branches.
    """

    def __init__(
        self,
        worker_pool: WorkerPool | None = None,
        on_event: Optional[Callable] = None,
    ) -> None:
        self.nodes: Dict[str, DAGNode] = {}
        self.edges: List[DAGEdge] = []
        self._worker_pool = worker_pool or WorkerPool()
        self._on_event = on_event

    def add_node(
        self,
        node_or_id: DAGNode | str,
        persona: AgentPersona = AgentPersona.DEVELOPER,
        task_description: str = "",
        dependencies: list[str] | None = None,
    ) -> DAGNode:
        """Add a node to the DAG, either directly as DAGNode or via parameters."""
        if isinstance(node_or_id, DAGNode):
            node = node_or_id
        else:
            node = DAGNode(
                node_id=str(node_or_id),
                name=str(node_or_id),
                persona=persona,
                prompt=task_description,
                dependencies=set(dependencies or []),
            )
            for dep in (dependencies or []):
                self.add_edge(dep, str(node_or_id))

        self.nodes[node.node_id] = node
        return node

    def add_edge(self, from_id: str, to_id: str, edge_type: str = "data") -> DAGEdge:
        """Add a dependency edge: from_id must complete before to_id starts."""
        edge = DAGEdge(from_node=from_id, to_node=to_id, edge_type=edge_type)
        self.edges.append(edge)

        # Update the dependent node's dependency set
        if to_id in self.nodes:
            self.nodes[to_id].dependencies.add(from_id)

        return edge

    def _topological_layers(self) -> List[List[str]]:
        """Compute topological layers for parallel execution.

        Returns a list of layers. Nodes in the same layer have no
        interdependencies and can run concurrently.
        """
        # Build adjacency and in-degree maps
        in_degree: Dict[str, int] = {nid: 0 for nid in self.nodes}
        adj: Dict[str, List[str]] = {nid: [] for nid in self.nodes}

        for edge in self.edges:
            if edge.from_node in self.nodes and edge.to_node in self.nodes:
                adj[edge.from_node].append(edge.to_node)
                in_degree[edge.to_node] += 1

        # Kahn's algorithm — layered BFS
        layers: List[List[str]] = []
        queue = [nid for nid, deg in in_degree.items() if deg == 0]

        while queue:
            layers.append(list(queue))
            next_queue = []
            for nid in queue:
                for neighbor in adj[nid]:
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        next_queue.append(neighbor)
            queue = next_queue

        return layers

    def get_execution_layers(self) -> List[List[str]]:
        """Compute topological layers with cycle detection."""
        layers = self._topological_layers()
        visited = sum(len(l) for l in layers)
        if visited < len(self.nodes):
            raise ValueError(f"Cycle detected in DAG: {len(self.nodes) - visited} unreachable nodes due to cyclic dependency.")
        return layers

    async def execute(self) -> Dict[str, Any]:
        """Execute the full DAG with maximum parallelism.

        Processes layers sequentially. Within each layer, all nodes
        execute concurrently. A failed node causes its downstream
        dependents to be skipped, but parallel branches continue.

        Returns:
            Aggregated results dict.
        """
        layers = self._topological_layers()
        results: Dict[str, str] = {}
        failed_nodes: Set[str] = set()

        if self._on_event:
            self._on_event({
                "type": "swarm.dag_started",
                "total_nodes": len(self.nodes),
                "total_layers": len(layers),
                "layers": [[self.nodes[nid].name for nid in layer] for layer in layers],
            })

        start_time = time.time()

        for layer_idx, layer in enumerate(layers):
            logger.info("DAG: executing layer %d/%d (%d nodes)", layer_idx + 1, len(layers), len(layer))

            # Filter out nodes whose dependencies failed
            executable = []
            for node_id in layer:
                node = self.nodes[node_id]
                failed_deps = node.dependencies & failed_nodes
                if failed_deps:
                    node.status = TaskStatus.SKIPPED
                    node.error = f"Skipped: upstream dependencies failed: {failed_deps}"
                    failed_nodes.add(node_id)
                    logger.info("DAG: skipping %s (failed deps: %s)", node.name, failed_deps)
                    continue
                executable.append(node_id)

            # Execute all nodes in this layer concurrently
            if executable:
                tasks = []
                for node_id in executable:
                    node = self.nodes[node_id]
                    # Gather upstream results for this node
                    upstream = {
                        dep_id: results.get(dep_id, "")
                        for dep_id in node.dependencies
                    }
                    tasks.append(
                        self._worker_pool.execute_node(node, upstream, self._on_event)
                    )

                # Wait for all tasks in this layer
                completed = await asyncio.gather(*tasks, return_exceptions=True)

                for item in completed:
                    if isinstance(item, Exception):
                        logger.error("DAG layer task exception: %s", item)
                        continue
                    if isinstance(item, DAGNode):
                        if item.status == TaskStatus.COMPLETED and item.result:
                            results[item.node_id] = item.result
                        elif item.status == TaskStatus.FAILED:
                            failed_nodes.add(item.node_id)

        total_time = time.time() - start_time

        summary = self._aggregate_results(total_time)

        if self._on_event:
            self._on_event({
                "type": "swarm.dag_completed",
                **summary,
            })

        return summary

    def _aggregate_results(self, total_time: float) -> Dict[str, Any]:
        """Aggregate results across all nodes."""
        completed = sum(1 for n in self.nodes.values() if n.status == TaskStatus.COMPLETED)
        failed = sum(1 for n in self.nodes.values() if n.status == TaskStatus.FAILED)
        skipped = sum(1 for n in self.nodes.values() if n.status == TaskStatus.SKIPPED)

        return {
            "total_nodes": len(self.nodes),
            "completed": completed,
            "failed": failed,
            "skipped": skipped,
            "total_time_ms": total_time * 1000,
            "nodes": {nid: node.to_dict() for nid, node in self.nodes.items()},
        }


# ── Swarm Orchestrator (High-Level API) ──────────────────────────────────────

class SwarmOrchestrator:
    """High-level multi-agent swarm orchestrator.

    Provides a simple API for dispatching specialized subtasks, building
    DAG workflows, and executing them with concurrent worker agents.

    Usage::

        orchestrator = SwarmOrchestrator(executor_func=my_llm_executor)

        # Simple dispatch
        task = orchestrator.dispatch_subtask(
            AgentPersona.DEVELOPER,
            "Implement the login endpoint",
        )
        result = await orchestrator.execute_subtask(task.subtask_id)

        # DAG workflow
        spec = orchestrator.create_dag_node(
            "specification", AgentPersona.ARCHITECT, "Design the auth module"
        )
        impl = orchestrator.create_dag_node(
            "implementation", AgentPersona.DEVELOPER, "Implement auth module"
        )
        audit = orchestrator.create_dag_node(
            "security_audit", AgentPersona.SECURITY_AUDITOR, "Audit auth module"
        )
        test = orchestrator.create_dag_node(
            "testing", AgentPersona.VERIFIER, "Test auth module"
        )

        # spec → impl → audit
        # spec → impl → test
        orchestrator.add_dag_dependency(spec.node_id, impl.node_id)
        orchestrator.add_dag_dependency(impl.node_id, audit.node_id)
        orchestrator.add_dag_dependency(impl.node_id, test.node_id)

        results = await orchestrator.execute_dag()
    """

    def __init__(
        self,
        executor_func: Optional[Callable] = None,
        max_workers: int = 4,
        on_event: Optional[Callable] = None,
    ) -> None:
        self._executor_func = executor_func
        self._on_event = on_event
        self._worker_pool = WorkerPool(
            max_workers=max_workers,
            executor_func=executor_func,
        )
        self._dag = DAGEngine(
            worker_pool=self._worker_pool,
            on_event=on_event,
        )

        # Legacy compatibility: simple subtask registry
        self.subtasks: Dict[str, "SwarmSubtask"] = {}

    # ── Legacy API (backward-compatible) ──────────────────────────────────────

    def dispatch_subtask(
        self,
        persona: AgentPersona,
        prompt: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> "SwarmSubtask":
        """Create and queue a specialized subagent task (legacy API)."""
        subtask_id = f"task_{persona.value}_{len(self.subtasks) + 1}"
        subtask = SwarmSubtask(
            subtask_id=subtask_id,
            persona=persona,
            prompt=prompt,
            context=context or {},
        )
        self.subtasks[subtask_id] = subtask
        logger.info(f"Dispatched subagent task {subtask_id} [{persona.value}]")
        return subtask

    def execute_subtask(
        self,
        subtask_id: str,
        executor_func: Optional[Any] = None,
    ) -> "SwarmSubtask":
        """Execute subagent turn with isolated context window (legacy API)."""
        if subtask_id not in self.subtasks:
            raise KeyError(f"Subtask {subtask_id} not found")

        subtask = self.subtasks[subtask_id]
        subtask.status = "RUNNING"

        try:
            func = executor_func or self._executor_func
            if func:
                subtask.result = func(subtask.persona, subtask.prompt, subtask.context)
            else:
                subtask.result = (
                    f"Completed subagent task [{subtask.persona.value}] "
                    f"for prompt: {subtask.prompt[:60]}..."
                )
            subtask.status = "COMPLETED"
        except Exception as exc:
            subtask.status = "FAILED"
            subtask.result = f"Error executing subagent task: {exc}"
            logger.error(f"Subagent execution failed for {subtask_id}: {exc}")

        return subtask

    def aggregate_results(self) -> Dict[str, Any]:
        """Aggregate results across all subagent tasks in the swarm (legacy API)."""
        return {
            "total_tasks": len(self.subtasks),
            "completed_tasks": sum(1 for t in self.subtasks.values() if t.status == "COMPLETED"),
            "failed_tasks": sum(1 for t in self.subtasks.values() if t.status == "FAILED"),
            "results": {tid: task.result for tid, task in self.subtasks.items()},
        }

    # ── DAG API ───────────────────────────────────────────────────────────────

    def create_dag_node(
        self,
        name: str,
        persona: AgentPersona,
        prompt: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> DAGNode:
        """Create and add a node to the execution DAG."""
        node = DAGNode(
            name=name,
            persona=persona,
            prompt=prompt,
            context=context or {},
        )
        self._dag.add_node(node)
        return node

    def add_dag_dependency(self, from_id: str, to_id: str, edge_type: str = "data") -> DAGEdge:
        """Add a dependency edge: from_id must complete before to_id starts."""
        return self._dag.add_edge(from_id, to_id, edge_type)

    async def execute_dag(self) -> Dict[str, Any]:
        """Execute the full DAG workflow with maximum parallelism."""
        return await self._dag.execute()

    def reset_dag(self) -> None:
        """Clear the DAG for a fresh workflow."""
        self._dag = DAGEngine(
            worker_pool=self._worker_pool,
            on_event=self._on_event,
        )

    # ── Convenience: standard development workflow ────────────────────────────

    async def run_development_pipeline(
        self,
        task_description: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Run a standard spec → code → audit → test pipeline.

        Creates a 4-node DAG with the standard development workflow:
        - ArchitectAgent: Generate specification
        - DeveloperAgent: Implement code
        - SecurityAuditorAgent: Static analysis (parallel with Verifier)
        - VerifierAgent: Run tests (parallel with SecurityAuditor)

        Args:
            task_description: High-level task description.
            context: Additional context dict.

        Returns:
            Aggregated DAG results.
        """
        self.reset_dag()
        ctx = context or {}

        spec = self.create_dag_node(
            "specification",
            AgentPersona.ARCHITECT,
            f"Generate a detailed specification for: {task_description}",
            ctx,
        )

        impl = self.create_dag_node(
            "implementation",
            AgentPersona.DEVELOPER,
            f"Implement the following based on the architect's specification: {task_description}",
            ctx,
        )

        audit = self.create_dag_node(
            "security_audit",
            AgentPersona.SECURITY_AUDITOR,
            f"Perform security audit on the implementation of: {task_description}",
            ctx,
        )

        verify = self.create_dag_node(
            "verification",
            AgentPersona.VERIFIER,
            f"Write and execute tests for: {task_description}",
            ctx,
        )

        # spec → impl → (audit, verify in parallel)
        self.add_dag_dependency(spec.node_id, impl.node_id)
        self.add_dag_dependency(impl.node_id, audit.node_id)
        self.add_dag_dependency(impl.node_id, verify.node_id)

        return await self.execute_dag()


# ── Legacy SwarmSubtask dataclass ─────────────────────────────────────────────

@dataclass
class SwarmSubtask:
    subtask_id: str
    persona: AgentPersona
    prompt: str
    context: Dict[str, Any] = field(default_factory=dict)
    status: str = "PENDING"
    result: Optional[str] = None
