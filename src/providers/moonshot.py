"""
Official Moonshot (Kimi) API Adapter (WS1.2).
"""

from __future__ import annotations

import os
from typing import Optional

from src.providers.base import ProviderCapabilities
from src.providers.openai_compat import OpenAICompatibleProvider


class MoonshotProvider(OpenAICompatibleProvider):
    """Official Moonshot Kimi direct API adapter."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "moonshot-v1-8k",
        base_url: Optional[str] = None,
    ) -> None:
        key = api_key or os.getenv("MOONSHOT_API_KEY") or os.getenv("KIMI_API_KEY", "")
        url = base_url or os.getenv("MOONSHOT_BASE_URL", "https://api.moonshot.cn/v1")
        caps = ProviderCapabilities(
            tools=True,
            parallel_tools=False,
            vision=False,
            json_mode=True,
            reasoning=False,
            max_context=32_768,
            streams_usage=True,
            supports_system_prompt=True,
        )
        super().__init__(
            name="moonshot",
            base_url=url,
            api_key=key,
            default_model=model,
            capabilities=caps,
        )

