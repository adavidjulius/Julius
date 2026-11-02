"""
Official DeepSeek API Adapter (WS1.2).
"""

from __future__ import annotations

import os
from typing import Optional

from src.providers.base import ProviderCapabilities
from src.providers.openai_compat import OpenAICompatibleProvider


class DeepSeekProvider(OpenAICompatibleProvider):
    """Official DeepSeek direct API adapter."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "deepseek-chat",
        base_url: Optional[str] = None,
    ) -> None:
        key = api_key or os.getenv("DEEPSEEK_API_KEY", "")
        url = base_url or os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        caps = ProviderCapabilities(
            tools=True,
            parallel_tools=True,
            vision=False,
            json_mode=True,
            reasoning=True,
            max_context=64_000,
            streams_usage=True,
            supports_system_prompt=True,
        )
        super().__init__(
            name="deepseek",
            base_url=url,
            api_key=key,
            default_model=model,
            capabilities=caps,
        )

