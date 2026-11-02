"""
Worker Pool for DAG Multi-Agent Swarm.

Phase 2.2 — Re-exported from swarm_orchestrator for convenience.
The WorkerPool class lives in swarm_orchestrator.py alongside the DAG engine
to keep the execution pipeline cohesive.
"""

from __future__ import annotations

from .swarm_orchestrator import WorkerPool, AgentPersona, TaskStatus

__all__ = ["WorkerPool", "AgentPersona", "TaskStatus"]
