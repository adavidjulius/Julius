"""
Local Ollama REST API Adapter (WS1.2).
"""

from __future__ import annotations

import os
from typing import Optional
from urllib.parse import urlparse

from src.errors import JUL_POL_COMMAND_FORBIDDEN, PolicyViolationError
from src.providers.base import ProviderCapabilities
from src.providers.openai_compat import OpenAICompatibleProvider


class OllamaProvider(OpenAICompatibleProvider):
    """Local Ollama direct HTTP API adapter."""

    def __init__(
        self,
        host: Optional[str] = None,
        model: str = "llama3.1:latest",
        allow_insecure_lan: Optional[bool] = None,
    ) -> None:
        raw_host = host or os.getenv("OLLAMA_HOST") or os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
        if not raw_host.startswith("http://") and not raw_host.startswith("https://"):
            raw_host = f"http://{raw_host}"

        # Enforce security principle: non-loopback Ollama bind requires explicit config + auth/TLS
        parsed = urlparse(raw_host)
        hostname = parsed.hostname or ""
        is_insecure_lan_allowed = allow_insecure_lan is True or os.getenv("JULIUS_ALLOW_INSECURE_LAN") in ("1", "true")
        if hostname not in ("127.0.0.1", "localhost", "::1"):
            if parsed.scheme != "https" and not is_insecure_lan_allowed:
                raise PolicyViolationError(
                    code=JUL_POL_COMMAND_FORBIDDEN,
                    message=f"Non-loopback Ollama host '{raw_host}' requires HTTPS/TLS or explicit configuration.",
                    hint="Set allow_insecure_lan=True, set JULIUS_ALLOW_INSECURE_LAN=1, or use loopback (127.0.0.1).",
                )

        base_url = f"{raw_host.rstrip('/')}/v1"
        caps = ProviderCapabilities(
            tools=True,
            parallel_tools=False,
            vision=True,
            json_mode=True,
            reasoning=True,
            max_context=32_768,
            streams_usage=True,
            supports_system_prompt=True,
        )
        super().__init__(
            name="ollama",
            base_url=base_url,
            api_key=os.getenv("OLLAMA_API_KEY", "ollama"),
            default_model=model,
            capabilities=caps,
        )
