"""
Dynamic Task Graph (DAG) Execution Scheduler for Julius AI Agent.

Manages execution nodes, topological scheduling, node dependencies, and status state machines.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


@dataclass
class DAGNode:
    node_id: str
    action_name: str
    payload: Dict[str, Any] = field(default_factory=dict)
    dependencies: Set[str] = field(default_factory=set)
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[Any] = None
    error: Optional[str] = None


class TaskDAGScheduler:
    """Directed Acyclic Graph (DAG) task execution scheduler."""

    def __init__(self) -> None:
        self.nodes: Dict[str, DAGNode] = {}

    def add_node(self, node_id: str, action_name: str, payload: Optional[Dict[str, Any]] = None, dependencies: Optional[Set[str]] = None) -> DAGNode:
        """Add task node to execution graph."""
        node = DAGNode(
            node_id=node_id,
            action_name=action_name,
            payload=payload or {},
            dependencies=dependencies or set(),
        )
        self.nodes[node_id] = node
        return node

    def get_ready_nodes(self) -> List[DAGNode]:
        """Return nodes whose dependencies are all COMPLETED and status is PENDING."""
        ready = []
        for node in self.nodes.values():
            if node.status != TaskStatus.PENDING:
                continue
            deps_met = all(
                dep_id in self.nodes and self.nodes[dep_id].status == TaskStatus.COMPLETED
                for dep_id in node.dependencies
            )
            if deps_met:
                ready.append(node)
        return ready

    def mark_completed(self, node_id: str, result: Optional[Any] = None) -> None:
        """Set node status to COMPLETED."""
        if node_id in self.nodes:
            self.nodes[node_id].status = TaskStatus.COMPLETED
            self.nodes[node_id].result = result

    def mark_failed(self, node_id: str, error: str) -> None:
        """Set node status to FAILED and skip dependent downstream nodes."""
        if node_id in self.nodes:
            self.nodes[node_id].status = TaskStatus.FAILED
            self.nodes[node_id].error = error
            self._propagate_skip(node_id)

    def _propagate_skip(self, failed_node_id: str) -> None:
        """Cascade SKIPPED status to downstream nodes dependent on failed node."""
        for node in self.nodes.values():
            if node.status == TaskStatus.PENDING and failed_node_id in node.dependencies:
                node.status = TaskStatus.SKIPPED
                self._propagate_skip(node.node_id)

    def is_finished(self) -> bool:
        """Check if all nodes have reached terminal status."""
        return all(node.status in {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.SKIPPED} for node in self.nodes.values())
