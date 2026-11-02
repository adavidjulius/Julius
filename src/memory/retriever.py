"""
Multi-tier memory retrieval with ranking.
Searches all memory tiers in parallel and returns ranked results.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .storage import MemoryStorage
from .task_memory import TaskMemory
from .conversation_memory import ConversationMemory
from .episodic_memory import EpisodicMemory
from .semantic_memory import SemanticMemory
from .execution_graph import ExecutionGraph

logger = logging.getLogger(__name__)


@dataclass
class MemoryResult:
    """A single memory retrieval result."""
    source: str  # "task", "conversation", "episodic", "semantic", "graph"
    content: str
    score: float
    metadata: Dict[str, Any] = field(default_factory=dict)


class MemoryRetriever:
    """
    Multi-tier memory retrieval.
    Searches all memory tiers, ranks by relevance, returns top results.
    """

    def __init__(self, storage: MemoryStorage, task_memory: TaskMemory,
                 conversation: ConversationMemory, episodic: EpisodicMemory,
                 semantic: SemanticMemory, graph: ExecutionGraph) -> None:
        self._storage = storage
        self._task_memory = task_memory
        self._conversation = conversation
        self._episodic = episodic
        self._semantic = semantic
        self._graph = graph

    def retrieve(self, query: str, limit: int = 10) -> List[MemoryResult]:
        """
        Search all memory tiers and return ranked results.
        Uses keyword overlap scoring for cross-tier ranking.
        """
        results: List[MemoryResult] = []
        query_words = set(re.findall(r"\w+", query.lower()))
        stop_words = {"the", "a", "an", "is", "are", "was", "were", "to", "of",
                      "in", "for", "on", "and", "or", "but", "with", "about",
                      "what", "show", "list", "me", "how", "do", "did", "i",
                      "you", "it", "we", "they", "this", "that", "continue",
                      "previous", "last", "task", "memory", "status"}
        query_words = query_words - stop_words

        # 1. Search task memory
        try:
            tasks = self._task_memory.search_tasks(query, limit=5)
            for t in tasks:
                content = f"Task: {t.summary} | Status: {t.status} | Files: {', '.join(t.files_modified[:3])}"
                score = self._keyword_score(query_words, content)
                results.append(MemoryResult(
                    source="task",
                    content=content,
                    score=score,
                    metadata={"task_id": t.task_id, "status": t.status},
                ))
        except Exception as e:
            logger.warning(f"Retriever: Task search failed: {e}")

        # 2. Search episodic notes
        try:
            notes = self._episodic.search_notes(query, limit=5)
            for n in notes:
                content = f"[{n['date']}] {n['summary']}"
                score = self._keyword_score(query_words, content)
                results.append(MemoryResult(
                    source="episodic",
                    content=content,
                    score=score,
                    metadata={"date": n["date"]},
                ))
        except Exception as e:
            logger.warning(f"Retriever: Episodic search failed: {e}")

        # 3. Search semantic facts
        try:
            facts = self._semantic.search_facts(query, limit=5)
            for f in facts:
                content = f"[{f['category']}] {f['fact_key']}: {f['fact_value']}"
                score = self._keyword_score(query_words, content)
                results.append(MemoryResult(
                    source="semantic",
                    content=content,
                    score=score,
                    metadata={"key": f["fact_key"], "category": f["category"]},
                ))
        except Exception as e:
            logger.warning(f"Retriever: Semantic search failed: {e}")

        # 4. Search graph nodes
        try:
            nodes = self._graph.get_all_nodes()
            for n in nodes:
                content = f"[{n['category']}] {n['name']}"
                score = self._keyword_score(query_words, content) * 0.8  # slight penalty
                if score > 0:
                    results.append(MemoryResult(
                        source="graph",
                        content=content,
                        score=score,
                        metadata={"node_id": n["node_id"], "category": n["category"]},
                    ))
        except Exception as e:
            logger.warning(f"Retriever: Graph search failed: {e}")

        # 5. Get recent conversation turns (always include a few)
        try:
            turns = self._conversation.get_recent_turns(limit=10)
            for t in turns:
                content = f"[{t.role}] {t.content[:150]}"
                score = self._keyword_score(query_words, content) * 0.6
                if score > 0:
                    results.append(MemoryResult(
                        source="conversation",
                        content=content,
                        score=score,
                        metadata={"turn_id": t.id, "role": t.role},
                    ))
        except Exception as e:
            logger.warning(f"Retriever: Conversation search failed: {e}")

        # Sort by score descending
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:limit]

    def _keyword_score(self, query_words: set, text: str) -> float:
        """Simple keyword overlap scoring."""
        if not query_words:
            return 0.0
        text_lower = text.lower()
        matches = sum(1 for w in query_words if w in text_lower)
        return matches / len(query_words) if matches > 0 else 0.0

    def retrieve_for_prompt(self, query: str, limit: int = 5) -> str:
        """Retrieve memories and format them as a prompt block."""
        results = self.retrieve(query, limit=limit)
        if not results:
            return "<no_relevant_memory/>"

        lines = ["<retrieved_memory>"]
        for r in results:
            lines.append(f"  [{r.source}] (score: {r.score:.2f}) {r.content[:200]}")
        lines.append("</retrieved_memory>")
        return "\n".join(lines)
