"""
Layer 20 — LLM Integration & Context Injection.

Ensures the LLM never searches raw repositories directly. Intercepts incoming user
prompts, queries PKB to assemble minimal deterministic context, and injects it.
"""

from __future__ import annotations

import logging
from typing import Optional, Tuple, Dict, Any

from .pipeline import ProjectKnowledgeBase
from .retrieval import RetrievalContext

logger = logging.getLogger(__name__)


class PKBLLMIntegration:
    """
    Middleware connecting PKB to LLM prompt construction pipelines.
    """

    def __init__(self, pkb: ProjectKnowledgeBase) -> None:
        self.pkb = pkb

    def process_prompt(
        self,
        user_prompt: str,
        max_context_tokens: int = 2500,
    ) -> Tuple[str, RetrievalContext]:
        """
        Analyze prompt intent, query PKB, and generate augmented user prompt.

        Returns:
            Tuple of (augmented_prompt_string, retrieval_context_object)
        """
        logger.info(f"PKB processing prompt for context optimization: '{user_prompt[:50]}...'")

        # 1. Query PKB Retrieval Engine
        context: RetrievalContext = self.pkb.query_api.buildContext(
            query=user_prompt,
            max_tokens=max_context_tokens
        )

        # 2. Construct augmented prompt with PKB context section
        if context.target_symbols or context.callers or context.dependencies:
            augmented_prompt = f"{context.formatted_prompt_context}\n\nUSER PROMPT:\n{user_prompt}"
        else:
            augmented_prompt = user_prompt

        return augmented_prompt, context
