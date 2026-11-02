"""
Official Perplexity Sonar API Adapter (WS1.2).
"""

from __future__ import annotations

import os
from typing import Optional

from src.providers.base import ProviderCapabilities
from src.providers.openai_compat import OpenAICompatibleProvider


class PerplexityProvider(OpenAICompatibleProvider):
    """Official Perplexity Sonar API Adapter with search citation flags."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "sonar-pro",
        base_url: Optional[str] = None,
    ) -> None:
        key = api_key or os.getenv("PERPLEXITY_API_KEY", "")
        url = base_url or os.getenv("PERPLEXITY_BASE_URL", "https://api.perplexity.ai")
        caps = ProviderCapabilities(
            tools=False,
            parallel_tools=False,
            vision=False,
            json_mode=True,
            reasoning=True,
            max_context=127_072,
            streams_usage=True,
            supports_system_prompt=True,
        )
        super().__init__(
            name="perplexity",
            base_url=url,
            api_key=key,
            default_model=model,
            capabilities=caps,
        )

