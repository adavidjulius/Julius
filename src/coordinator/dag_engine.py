"""
DAG Engine for Multi-Agent Swarm.

Phase 2.2 — Re-exported from swarm_orchestrator for convenience.
The DAGEngine class lives in swarm_orchestrator.py alongside the orchestrator
to keep the execution pipeline cohesive.
"""

from __future__ import annotations

from .swarm_orchestrator import DAGEngine, DAGNode, DAGEdge, TaskStatus

__all__ = ["DAGEngine", "DAGNode", "DAGEdge", "TaskStatus"]
