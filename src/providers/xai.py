"""
Official xAI Grok API Adapter (WS1.2).
"""

from __future__ import annotations

import os
from typing import Optional

from src.providers.base import ProviderCapabilities
from src.providers.openai_compat import OpenAICompatibleProvider


class XAIProvider(OpenAICompatibleProvider):
    """Official xAI Grok direct API adapter."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "grok-2",
        base_url: Optional[str] = None,
    ) -> None:
        key = api_key or os.getenv("XAI_API_KEY") or os.getenv("GROK_API_KEY", "")
        url = base_url or os.getenv("XAI_BASE_URL", "https://api.x.ai/v1")
        caps = ProviderCapabilities(
            tools=True,
            parallel_tools=True,
            vision=True,
            json_mode=True,
            reasoning=True,
            max_context=131_072,
            streams_usage=True,
            supports_system_prompt=True,
        )
        super().__init__(
            name="xai",
            base_url=url,
            api_key=key,
            default_model=model,
            capabilities=caps,
        )

