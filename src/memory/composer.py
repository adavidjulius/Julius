"""
Context Composer: assembles LLM prompt from retrieved context.
Takes retrieved memories, agent state, working memory, and composes
a structured preamble for the LLM.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .agent_state import AgentState
from .working_memory import WorkingMemory
from .retriever import MemoryRetriever

logger = logging.getLogger(__name__)


@dataclass
class ComposedContext:
    """The assembled context block for LLM consumption."""
    prompt_block: str
    token_estimate: int
    sources_used: List[str]


class ContextComposer:
    """
    Assembles a structured LLM context preamble from:
    - Agent state (project, goals, completed tasks)
    - Working memory (current file, errors)
    - Retrieved memories (task history, episodic notes, semantic facts)
    - Execution graph
    """

    def __init__(self, retriever: MemoryRetriever) -> None:
        self._retriever = retriever

    def compose(self, query: str, agent_state: AgentState,
                working_memory: Optional[WorkingMemory] = None,
                max_tokens: int = 4000) -> ComposedContext:
        """
        Compose context for an LLM call.
        Retrieves relevant memories and structures them with agent state.
        """
        blocks: List[str] = []
        sources: List[str] = []
        estimated_tokens = 0

        # 1. Agent state block (always included, compact)
        state_block = agent_state.to_prompt_block()
        blocks.append(state_block)
        sources.append("agent_state")
        estimated_tokens += len(state_block) // 4

        # 2. Working memory block (if available)
        if working_memory:
            wm_block = working_memory.to_prompt_block()
            blocks.append(wm_block)
            sources.append("working_memory")
            estimated_tokens += len(wm_block) // 4

        # 3. Retrieved memories (query-dependent)
        try:
            retrieved = self._retriever.retrieve_for_prompt(query, limit=5)
            blocks.append(retrieved)
            sources.append("retrieved_memory")
            estimated_tokens += len(retrieved) // 4
        except Exception as e:
            logger.warning(f"Composer: Memory retrieval failed: {e}")

        # 4. Truncate if over budget
        combined = "\n\n".join(blocks)
        while estimated_tokens > max_tokens and len(blocks) > 1:
            removed = blocks.pop()
            combined = "\n\n".join(blocks)
            estimated_tokens -= len(removed) // 4
            if sources:
                sources.pop()

        return ComposedContext(
            prompt_block=combined,
            token_estimate=estimated_tokens,
            sources_used=sources,
        )
