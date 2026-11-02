"""
Official Google Gemini API Adapter (WS1.2).

Uses Google's official direct API endpoints.
"""

from __future__ import annotations

import os
from typing import Optional

from src.providers.base import ProviderCapabilities
from src.providers.openai_compat import OpenAICompatibleProvider


class GeminiProvider(OpenAICompatibleProvider):
    """Official Google Gemini API Adapter."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gemini-2.5-flash",
        base_url: Optional[str] = None,
    ) -> None:
        key = api_key or os.getenv("GEMINI_API_KEY", "")
        # Official Google AI Studio OpenAI-compatible direct endpoint
        url = base_url or os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai")
        caps = ProviderCapabilities(
            tools=True,
            parallel_tools=True,
            vision=True,
            json_mode=True,
            reasoning=True,
            max_context=1_000_000,
            streams_usage=True,
            supports_system_prompt=True,
        )
        super().__init__(
            name="gemini",
            base_url=url,
            api_key=key,
            default_model=model,
            capabilities=caps,
        )

