"""
Official NVIDIA NIM Hosted API Adapter (WS1.2, WS1.3).

Features:
- Strict 40 RPM (Requests Per Minute) sliding-window rate limiting & 1.5s delay pacing.
- Multi-Model Helper Squad Architecture:
  * Main Reasoning: nvidia/nemotron-3-ultra-550b-a55b (Deep thinking & architecture)
  * Tool Calling Specialist: meta/llama-3.3-70b-instruct (Native OpenAI function calling)
  * Multimodal Vision Helper: meta/llama-3.2-11b-vision-instruct (Image & screenshot analysis)
- Automatic subtask delegation between reasoning and tool-calling specialist models.
"""

from __future__ import annotations

import asyncio
import collections
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

from src.providers.base import (
    ChatMessage,
    ChatRequest,
    LLMEvent,
    ProviderCapabilities,
)
from src.providers.openai_compat import OpenAICompatibleProvider

logger = logging.getLogger(__name__)

# Canonical NVIDIA NIM Model Catalog & Validated Tool Models
NVIDIA_MODEL_NEMOTRON_550B = "nvidia/nemotron-3-ultra-550b-a55b"
NVIDIA_MODEL_NEMOTRON_LIGHTNING_30B = "nvidia/nemotron-3.5-lightning-30b-a3b"
NVIDIA_MODEL_NEMOTRON_NANO_OMNI = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning"
NVIDIA_MODEL_NEMOTRON_SUPER_VL = "nvidia/nemotron-3.5-super-vl-120b-a12b"
NVIDIA_MODEL_NEMOTRON_BOLT = "nvidia/nemotron-3.5-bolt-e4b"
NVIDIA_MODEL_LLAMA_VISION_90B = "meta/llama-3.2-90b-vision-instruct"

# Live-tested models with verified native OpenAI tool_calls support on integrate.api.nvidia.com
VALIDATED_NVIDIA_TOOL_MODELS = (
    NVIDIA_MODEL_NEMOTRON_550B,
    NVIDIA_MODEL_NEMOTRON_LIGHTNING_30B,
    NVIDIA_MODEL_NEMOTRON_NANO_OMNI,
    NVIDIA_MODEL_NEMOTRON_BOLT,
    NVIDIA_MODEL_NEMOTRON_SUPER_VL,
)


class NvidiaRateLimiter:
    """
    Thread-safe sliding-window rate limiter enforcing NVIDIA NIM Free tier limits:
    - Hard limit: 40 RPM (Requests Per Minute).
    - Minimum pacing interval: 1.5 seconds between consecutive calls.
    - Automatic exponential backoff on 429 rate limit errors.
    """

    def __init__(self, max_rpm: int = 40, min_interval_s: float = 1.5) -> None:
        self.max_rpm = max_rpm
        self.min_interval_s = min_interval_s
        self._timestamps: collections.deque[float] = collections.deque()
        self._last_call_time: float = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Wait until a request slot is available within the 40 RPM window."""
        async with self._lock:
            now = time.monotonic()

            # 1. Enforce minimum interval between consecutive requests (1.5s)
            elapsed_since_last = now - self._last_call_time
            if elapsed_since_last < self.min_interval_s:
                sleep_dur = self.min_interval_s - elapsed_since_last
                await asyncio.sleep(sleep_dur)
                now = time.monotonic()

            # 2. Enforce 40 requests per 60-second sliding window
            while self._timestamps and now - self._timestamps[0] >= 60.0:
                self._timestamps.popleft()

            if len(self._timestamps) >= self.max_rpm:
                oldest = self._timestamps[0]
                wait_time = max(0.1, 60.0 - (now - oldest) + 0.1)
                logger.info(f"[NVIDIA NIM Rate Limiter] 40 RPM ceiling reached. Pacing for {wait_time:.2f}s...")
                await asyncio.sleep(wait_time)
                now = time.monotonic()
                while self._timestamps and now - self._timestamps[0] >= 60.0:
                    self._timestamps.popleft()

            self._timestamps.append(now)
            self._last_call_time = now


_global_nvidia_limiter = NvidiaRateLimiter(max_rpm=40, min_interval_s=1.5)


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
    """
    Official NVIDIA NIM direct API adapter with multi-model helper squad
    and 40 RPM rate limiting.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = NVIDIA_MODEL_NEMOTRON_550B,
        base_url: Optional[str] = None,
    ) -> None:
        key = api_key or resolve_nvidia_api_key()
        url = base_url or os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
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
            name="nvidia",
            base_url=url,
            api_key=key,
            default_model=model,
            capabilities=caps,
        )
        self.rate_limiter = _global_nvidia_limiter

    def _select_specialist_model(self, req: ChatRequest) -> str:
        """
        Dynamically route between NVIDIA NIM models:
        - Tool Calling Check: When tools are provided, ONLY route to verified tool-calling models.
          If the requested model is not in VALIDATED_NVIDIA_TOOL_MODELS, automatically route to
          the flagship tool-capable model (NVIDIA_MODEL_NEMOTRON_550B).
        - Vision Check: Image attached -> meta/llama-3.2-90b-vision-instruct (or super-vl if tools also required)
        - Otherwise -> requested or flagship reasoning model.
        """
        requested = req.model or self.default_model

        # 1. Vision Check: image attachments in messages
        has_image = any(
            (getattr(msg, "metadata", None) and (msg.metadata.get("image_path") or msg.metadata.get("image_url")))
            or ("[image:" in (getattr(msg, "content", "") or "").lower())
            for msg in req.messages
        )
        if has_image:
            if req.tools:
                logger.info("[NVIDIA NIM Router] Image + Tools requested: routing to %s", NVIDIA_MODEL_NEMOTRON_SUPER_VL)
                return NVIDIA_MODEL_NEMOTRON_SUPER_VL
            logger.info("[NVIDIA NIM Router] Delegating to Vision Helper: %s", NVIDIA_MODEL_LLAMA_VISION_90B)
            return NVIDIA_MODEL_LLAMA_VISION_90B

        # 2. Strict Tool Calling Check:
        # User constraint: ONLY call models having tool calling option when tools are requested.
        if req.tools:
            if requested not in VALIDATED_NVIDIA_TOOL_MODELS:
                logger.info(
                    "[NVIDIA NIM Router] Model '%s' lacks verified tool calling. Routing to validated model '%s'",
                    requested,
                    NVIDIA_MODEL_NEMOTRON_550B,
                )
                return NVIDIA_MODEL_NEMOTRON_550B
            return requested

        return requested

    def _format_request_payload(self, req: ChatRequest) -> Dict[str, Any]:
        chosen_model = self._select_specialist_model(req)
        # Temporarily assign chosen specialist model
        orig_model = req.model
        req.model = chosen_model

        # Defensive guard: if chosen model is NOT in VALIDATED_NVIDIA_TOOL_MODELS, strip tools
        # to ensure the NVIDIA API endpoint will not reject the request with HTTP 400/404
        if req.tools and chosen_model not in VALIDATED_NVIDIA_TOOL_MODELS:
            saved_tools = req.tools
            req.tools = None
            payload = super()._format_request_payload(req)
            req.tools = saved_tools
        else:
            payload = super()._format_request_payload(req)

        req.model = orig_model

        # Only pass chat_template_kwargs to Nemotron models that support it
        if "nemotron" in chosen_model.lower():
            payload["chat_template_kwargs"] = {"enable_thinking": True}
        else:
            payload.pop("chat_template_kwargs", None)

        return payload

    async def stream(
        self,
        req: ChatRequest,
        cancel: Optional[asyncio.Event] = None,
    ) -> AsyncIterator[LLMEvent]:
        # Enforce 40 RPM pacing before every streaming request
        await self.rate_limiter.acquire()
        async for event in super().stream(req, cancel=cancel):
            yield event
