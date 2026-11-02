"""
Official OpenAI API Adapter (WS1.2).
"""

from __future__ import annotations

import os
from typing import Optional

from src.providers.base import ProviderCapabilities
from src.providers.openai_compat import OpenAICompatibleProvider


class OpenAIProvider(OpenAICompatibleProvider):
    """Official OpenAI Direct API provider."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-4o",
        base_url: Optional[str] = None,
    ) -> None:
        key = api_key or os.getenv("OPENAI_API_KEY", "")
        url = base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        caps = ProviderCapabilities(
            tools=True,
            parallel_tools=True,
            vision=True,
            json_mode=True,
            reasoning=True,
            max_context=128_000,
            streams_usage=True,
            supports_system_prompt=True,
        )
        super().__init__(
            name="openai",
            base_url=url,
            api_key=key,
            default_model=model,
            capabilities=caps,
        )

