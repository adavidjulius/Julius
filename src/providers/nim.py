"""
Official NVIDIA NIM Hosted API Adapter (WS1.2).
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, Optional

from src.providers.base import ChatRequest, ProviderCapabilities
from src.providers.openai_compat import OpenAICompatibleProvider


def resolve_nvidia_api_key() -> str:
    """Resolve active NVIDIA API key from environment, user config, or .env."""
    try:
        from dotenv import load_dotenv
        for _env in [Path.cwd() / ".env", Path.home() / ".julius" / ".env", Path(__file__).resolve().parent.parent.parent / ".env"]:
            if _env.exists():
                load_dotenv(dotenv_path=_env, override=False)
    except Exception:
        pass
    env_key = os.getenv("NVIDIA_API_KEY", "").strip() or os.getenv("NVIDIA_NIM_API_KEY", "").strip()
    return env_key


class NvidiaNIMProvider(OpenAICompatibleProvider):
    """Official NVIDIA NIM direct API adapter."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "nvidia/nemotron-3-ultra-550b-a55b",
        base_url: Optional[str] = None,
    ) -> None:
        key = api_key or resolve_nvidia_api_key()
        url = base_url or os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
        caps = ProviderCapabilities(
            tools=True,
            parallel_tools=True,
            vision=False,
            json_mode=True,
            reasoning=True,
            max_context=128_000,
            streams_usage=True,
            supports_system_prompt=True,
        )
        super().__init__(
            name="nvidia",
            base_url=url,
            api_key=key,
            default_model=model,
            capabilities=caps,
        )

    def _format_request_payload(self, req: ChatRequest) -> Dict[str, Any]:
        payload = super()._format_request_payload(req)
        # Enable native reasoning thoughts for Nemotron-3 Ultra 550B
        payload["chat_template_kwargs"] = {"enable_thinking": True}
        return payload

