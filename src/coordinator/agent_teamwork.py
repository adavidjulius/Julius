"""
Agent Teamwork & Swarm Delegation Subsystem for Julius.

Bridges the DAGEngine and SwarmOrchestrator into a callable tool action.
Enables Julius to spawn specialized multi-agent squads (Architect, Developer,
Security Auditor, Verifier, Researcher) to solve complex goals concurrently.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .swarm_orchestrator import (
    AgentPersona,
    DAGEngine,
    DAGNode,
    TaskStatus,
    WorkerPool,
)

logger = logging.getLogger(__name__)


@dataclass
class TeamMemberReport:
    """Report from an individual agent team member."""
    persona: str
    subtask: str
    status: str
    output: str
    duration_ms: float = 0.0
    error: Optional[str] = None


@dataclass
class TeamworkReport:
    """Consolidated outcome from a multi-agent team mission."""
    goal: str
    success: bool
    summary: str
    members: List[TeamMemberReport] = field(default_factory=list)
    total_duration_ms: float = 0.0
    artifacts_created: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal": self.goal,
            "success": self.success,
            "summary": self.summary,
            "total_duration_ms": self.total_duration_ms,
            "members": [
                {
                    "persona": m.persona,
                    "subtask": m.subtask,
                    "status": m.status,
                    "duration_ms": round(m.duration_ms, 1),
                    "output_preview": m.output[:200] if m.output else "",
                    "error": m.error,
                }
                for m in self.members
            ],
            "artifacts_created": self.artifacts_created,
        }

    def format_markdown(self) -> str:
        status_icon = "✅" if self.success else "❌"
        lines = [
            f"### {status_icon} Teamwork Swarm Mission: {self.goal}",
            f"**Total Execution Time**: {round(self.total_duration_ms, 1)}ms",
            "",
            "#### 👥 Squad Contributions:",
        ]
        for m in self.members:
            m_icon = "🟢" if m.status == "COMPLETED" else "🔴"
            lines.append(f"- {m_icon} **{m.persona.upper()}**: {m.subtask} ({round(m.duration_ms, 1)}ms)")
            if m.output:
                lines.append(f"  > {m.output.strip().replace(chr(10), ' '[:100])}")
            if m.error:
                lines.append(f"  *Error*: {m.error}")

        lines.append("")
        lines.append(f"**Executive Conclusion**: {self.summary}")
        return "\n".join(lines)


class TeamworkDispatcher:
    """
    Orchestrates the dynamic deployment of multi-agent squads.
    """

    def __init__(
        self,
        executor_func: Optional[Callable[[AgentPersona, str, Dict[str, Any]], Any]] = None,
        on_event: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> None:
        self.executor_func = executor_func
        self.on_event = on_event

    async def execute_mission_async(
        self,
        goal: str,
        personas: Optional[List[str]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> TeamworkReport:
        """
        Execute a multi-agent goal across a DAG of specialized agents.
        """
        start_time = time.time()
        ctx = context or {}

        # Default engineering squad: Architect -> Developer -> Verifier + SecurityAuditor
        requested_personas = [p.lower() for p in (personas or ["architect", "developer", "security_auditor", "verifier"])]

        worker_pool = WorkerPool(executor_func=self.executor_func, max_concurrent=4)
        dag = DAGEngine(worker_pool=worker_pool, on_event=self.on_event)

        # 1. Architect Node
        if "architect" in requested_personas:
            dag.add_node(
                "architect_node",
                persona=AgentPersona.ARCHITECT,
                task_description=f"Analyze specification and design technical architecture for goal: {goal}",
            )

        # 2. Developer Node (Depends on Architect if present)
        if "developer" in requested_personas:
            dev_deps = ["architect_node"] if "architect" in requested_personas else []
            dag.add_node(
                "developer_node",
                persona=AgentPersona.DEVELOPER,
                task_description=f"Implement core logic and modules to fulfill goal: {goal}",
                dependencies=dev_deps,
            )

        # 3. Security Auditor Node (Runs parallel, evaluates architectural safety)
        if "security_auditor" in requested_personas:
            sec_deps = ["architect_node"] if "architect" in requested_personas else []
            dag.add_node(
                "security_node",
                persona=AgentPersona.SECURITY_AUDITOR,
                task_description=f"Perform threat modeling and security verification on goal: {goal}",
                dependencies=sec_deps,
            )

        # 4. Verifier Node (Depends on Developer)
        if "verifier" in requested_personas:
            ver_deps = ["developer_node"] if "developer" in requested_personas else []
            dag.add_node(
                "verifier_node",
                persona=AgentPersona.VERIFIER,
                task_description=f"Validate test coverage and acceptance criteria for goal: {goal}",
                dependencies=ver_deps,
            )

        logger.info(f"TeamworkDispatcher launching mission: '{goal}' with {len(dag.nodes)} nodes")

        # Execute DAG
        results_map = await dag.execute(context=ctx)

        total_duration = (time.time() - start_time) * 1000.0
        member_reports: List[TeamMemberReport] = []
        all_success = True

        for nid, node in results_map.items():
            is_ok = node.status == TaskStatus.COMPLETED
            if not is_ok:
                all_success = False

            member_reports.append(
                TeamMemberReport(
                    persona=node.persona.value,
                    subtask=node.prompt,
                    status=node.status.value,
                    output=node.result or "",
                    duration_ms=node.duration_ms or 0.0,
                    error=node.error,
                )
            )

        summary = (
            f"Successfully coordinated {len(member_reports)} agents to complete mission: {goal}"
            if all_success
            else f"Team mission partially succeeded with errors in {sum(1 for m in member_reports if m.status != 'COMPLETED')} tasks."
        )

        return TeamworkReport(
            goal=goal,
            success=all_success,
            summary=summary,
            members=member_reports,
            total_duration_ms=total_duration,
        )

    def execute_mission(
        self,
        goal: str,
        personas: Optional[List[str]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> TeamworkReport:
        """Synchronous wrapper for TeamworkDispatcher."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Run inside existing loop via a task or runner thread
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    return pool.submit(
                        lambda: asyncio.run(self.execute_mission_async(goal, personas, context))
                    ).result(timeout=60.0)
            return loop.run_until_complete(self.execute_mission_async(goal, personas, context))
        except Exception:
            return asyncio.run(self.execute_mission_async(goal, personas, context))


# Singleton instance
_teamwork_dispatcher: Optional[TeamworkDispatcher] = None


def get_teamwork_dispatcher() -> TeamworkDispatcher:
    """Get or instantiate global TeamworkDispatcher."""
    global _teamwork_dispatcher
    if _teamwork_dispatcher is None:
        _teamwork_dispatcher = TeamworkDispatcher()
    return _teamwork_dispatcher
