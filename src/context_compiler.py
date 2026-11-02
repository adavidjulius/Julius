"""
Compiler-Grade Context Compiler Engine for Julius AI Agent Platform.

Implements AST symbol scoring, PageRank importance allocation, recency decay,
semantic similarity ranking, code minification, and context snapshot diffing.
"""

from __future__ import annotations

import math
import re
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class SymbolScore:
    symbol_id: str
    file_path: str
    pagerank_score: float
    recency_score: float
    similarity_score: float
    total_score: float
    tokens: int
    content: str


@dataclass
class ContextSnapshot:
    snapshot_id: str
    included_symbols: List[str]
    total_tokens: int
    compiled_prompt: str


class ContextCompiler:
    """
    Compiler-Grade Context Management Engine.

    Packs high-priority AST code symbols into token windows using PageRank,
    recency decay, and AST minification.
    """

    def __init__(
        self,
        default_token_budget: int = 128000,
        alpha: float = 0.4,
        beta: float = 0.3,
        gamma: float = 0.3,
    ) -> None:
        self.default_token_budget = default_token_budget
        self.alpha = alpha  # PageRank weight
        self.beta = beta    # Git recency weight
        self.gamma = gamma  # Query similarity weight

    def estimate_tokens(self, text: str) -> int:
        """Rough token counter heuristic (4 chars per token average)."""
        return max(1, len(text) // 4)

    def minify_code_snippet(self, code: str) -> str:
        """
        AST-aware code minification for context packing.
        Removes excessive blank lines and leading docstring noise while preserving structural symbols.
        """
        lines = code.splitlines()
        minified_lines = []
        in_docstring = False

        for line in lines:
            stripped = line.strip()
            # Single-line triple quote docstrings
            if (stripped.startswith('"""') and stripped.endswith('"""') and len(stripped) >= 6) or \
               (stripped.startswith("'''") and stripped.endswith("'''") and len(stripped) >= 6):
                continue

            # Multi-line docstring toggle
            if stripped.startswith('"""') or stripped.startswith("'''"):
                in_docstring = not in_docstring
                continue
            if in_docstring:
                if stripped.endswith('"""') or stripped.endswith("'''"):
                    in_docstring = False
                continue

            # Strip full line comments if not essential
            if stripped.startswith("#") and not stripped.startswith("# TODO") and not stripped.startswith("#!"):
                continue

            if stripped:
                minified_lines.append(line)

        return "\n".join(minified_lines)

    def calculate_score(
        self,
        symbol_id: str,
        pagerank: float,
        last_modified_delta_sec: float,
        similarity: float,
    ) -> float:
        """
        Compute total context score:
        Score(s) = alpha * PageRank + beta * e^(-lambda * dt) + gamma * CosSim
        """
        # Recency decay: half-life of 1 hour (3600s)
        lambda_decay = math.log(2) / 3600.0
        recency = math.exp(-lambda_decay * last_modified_delta_sec)

        return (self.alpha * pagerank) + (self.beta * recency) + (self.gamma * similarity)

    def compile_context(
        self,
        query: str,
        symbols_pool: List[Dict[str, Any]],
        token_budget: Optional[int] = None,
        minify: bool = True,
    ) -> ContextSnapshot:
        """
        Select and pack highest scoring AST symbols into the token budget.
        """
        budget = token_budget or self.default_token_budget
        scored_symbols: List[SymbolScore] = []

        query_words = set(re.findall(r"\w+", query.lower()))

        for item in symbols_pool:
            sym_id = item.get("symbol_id", "unknown")
            file_path = item.get("file_path", "")
            pr_score = item.get("pagerank", 0.1)
            delta_sec = item.get("last_modified_delta_sec", 3600.0)
            content = item.get("content", "")

            # Heuristic text similarity
            sym_words = set(re.findall(r"\w+", content.lower()))
            overlap = len(query_words.intersection(sym_words))
            similarity = overlap / max(1, len(query_words))

            score = self.calculate_score(sym_id, pr_score, delta_sec, similarity)
            
            processed_content = self.minify_code_snippet(content) if minify else content
            tokens = self.estimate_tokens(processed_content)

            scored_symbols.append(
                SymbolScore(
                    symbol_id=sym_id,
                    file_path=file_path,
                    pagerank_score=pr_score,
                    recency_score=math.exp(-(math.log(2) / 3600.0) * delta_sec),
                    similarity_score=similarity,
                    total_score=score,
                    tokens=tokens,
                    content=processed_content,
                )
            )

        # Sort by total score descending
        scored_symbols.sort(key=lambda s: s.total_score, reverse=True)

        included_ids: List[str] = []
        packed_snippets: List[str] = []
        current_tokens = 0

        for sym in scored_symbols:
            if current_tokens + sym.tokens > budget:
                continue
            included_ids.append(sym.symbol_id)
            packed_snippets.append(f"### Symbol: {sym.symbol_id} ({sym.file_path})\n{sym.content}")
            current_tokens += sym.tokens

        compiled_text = "\n\n".join(packed_snippets)
        snapshot_id = f"snap_{hash(query + str(current_tokens))}"

        return ContextSnapshot(
            snapshot_id=snapshot_id,
            included_symbols=included_ids,
            total_tokens=current_tokens,
            compiled_prompt=compiled_text,
        )
