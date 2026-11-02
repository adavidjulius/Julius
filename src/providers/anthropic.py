"""
Official Anthropic Messages API Adapter (WS1.2).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any, AsyncIterator, Dict, List, Optional

import aiohttp

from src.errors import (
    JUL_PROV_AUTH_FAILED,
    JUL_PROV_BAD_REQUEST,
    JUL_PROV_RATE_LIMITED,
    JUL_PROV_TIMEOUT,
    JUL_PROV_UNAVAILABLE,
    ProviderError,
)
from src.providers.base import (
    ChatMessage,
    ChatRequest,
    Finish,
    HealthStatus,
    LLMEvent,
    LLMProvider,
    ProviderCapabilities,
    ReasoningDelta,
    TextDelta,
    ToolCallDelta,
    ToolCallDone,
    Usage,
)

logger = logging.getLogger(__name__)


class AnthropicProvider(LLMProvider):
    """Official Anthropic Messages Direct API adapter."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "claude-3-5-sonnet-20241022",
        base_url: Optional[str] = None,
    ) -> None:
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY", "")
        self.default_model = model
        self.base_url = (base_url or os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com/v1")).rstrip("/")
        self._capabilities = ProviderCapabilities(
            tools=True,
            parallel_tools=True,
            vision=True,
            json_mode=True,
            reasoning=True,
            max_context=200_000,
            streams_usage=True,
            supports_system_prompt=True,
        )
        self._session: Optional[aiohttp.ClientSession] = None

    @property
    def name(self) -> str:
        return "anthropic"

    def capabilities(self) -> ProviderCapabilities:
        return self._capabilities

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120, connect=15, sock_read=60))
        return self._session

    def _convert_messages(self, req: ChatRequest) -> tuple[Optional[str], List[Dict[str, Any]]]:
        """Extract system prompt and convert messages to Anthropic format."""
        system_prompt: Optional[str] = None
        converted: List[Dict[str, Any]] = []

        for m in req.messages:
            if m.role == "system":
                system_prompt = (system_prompt + "\n" + m.content) if system_prompt else m.content
            elif m.role == "tool":
                converted.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": m.tool_call_id or "tool_call_0",
                            "content": m.content,
                        }
                    ],
                })
            elif m.role == "assistant" and m.tool_calls:
                content_blocks: List[Dict[str, Any]] = []
                if m.content:
                    content_blocks.append({"type": "text", "text": m.content})
                for tc in m.tool_calls:
                    content_blocks.append({
                        "type": "tool_use",
                        "id": tc.id,
                        "name": tc.name,
                        "input": tc.arguments,
                    })
                converted.append({"role": "assistant", "content": content_blocks})
            else:
                converted.append({"role": m.role, "content": m.content})

        return system_prompt, converted

    async def stream(
        self,
        req: ChatRequest,
        *,
        cancel: Optional[asyncio.Event] = None,
    ) -> AsyncIterator[LLMEvent]:
        session = await self._get_session()
        url = f"{self.base_url}/messages"

        system_prompt, messages = self._convert_messages(req)

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
            "accept": "text/event-stream",
        }

        payload: Dict[str, Any] = {
            "model": req.model or self.default_model,
            "messages": messages,
            "max_tokens": req.max_tokens or 4096,
            "stream": True,
            "temperature": req.temperature,
        }
        if system_prompt:
            payload["system"] = system_prompt

        if req.tools and self._capabilities.tools:
            payload["tools"] = [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.parameters,
                }
                for t in req.tools
            ]

        try:
            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status in (401, 403):
                    body = await resp.text()
                    raise ProviderError(
                        code=JUL_PROV_AUTH_FAILED,
                        message=f"Anthropic authentication failed: {body[:200]}",
                        hint="Check your ANTHROPIC_API_KEY in ~/.julius/config.toml or environment.",
                        provider=self.name,
                    )
                elif resp.status == 429:
                    body = await resp.text()
                    raise ProviderError(
                        code=JUL_PROV_RATE_LIMITED,
                        message=f"Anthropic rate limited: {body[:200]}",
                        retryable=True,
                        provider=self.name,
                    )
                elif resp.status >= 500:
                    body = await resp.text()
                    raise ProviderError(
                        code=JUL_PROV_UNAVAILABLE,
                        message=f"Anthropic server error ({resp.status}): {body[:200]}",
                        retryable=True,
                        provider=self.name,
                    )
                elif resp.status >= 400:
                    body = await resp.text()
                    raise ProviderError(
                        code=JUL_PROV_BAD_REQUEST,
                        message=f"Anthropic bad request: {body[:200]}",
                        provider=self.name,
                    )

                active_tool_id = ""
                active_tool_name = ""
                active_tool_input = ""
                prompt_tok = 0
                comp_tok = 0

                async for line_bytes in resp.content:
                    if cancel and cancel.is_set():
                        yield Finish(reason="cancelled")
                        break

                    line = line_bytes.decode("utf-8").strip()
                    if not line.startswith("data:"):
                        continue

                    data_str = line[5:].strip()
                    try:
                        chunk = json.loads(data_str)
                    except Exception:
                        continue

                    event_type = chunk.get("type")

                    if event_type == "message_start":
                        msg_info = chunk.get("message", {})
                        usage = msg_info.get("usage", {})
                        prompt_tok = usage.get("input_tokens", 0)

                    elif event_type == "content_block_start":
                        block = chunk.get("content_block", {})
                        if block.get("type") == "tool_use":
                            active_tool_id = block.get("id", "")
                            active_tool_name = block.get("name", "")
                            active_tool_input = ""

                    elif event_type == "content_block_delta":
                        delta = chunk.get("delta", {})
                        d_type = delta.get("type")
                        if d_type == "text_delta":
                            yield TextDelta(text=delta.get("text", ""))
                        elif d_type == "thinking_delta":
                            yield ReasoningDelta(reasoning=delta.get("thinking", ""))
                        elif d_type == "input_json_delta":
                            partial = delta.get("partial_json", "")
                            active_tool_input += partial
                            yield ToolCallDelta(
                                id=active_tool_id,
                                name=active_tool_name,
                                arguments_delta=partial,
                            )

                    elif event_type == "content_block_stop":
                        if active_tool_name:
                            try:
                                args = json.loads(active_tool_input) if active_tool_input else {}
                            except Exception:
                                args = {"raw": active_tool_input}
                            yield ToolCallDone(
                                id=active_tool_id,
                                name=active_tool_name,
                                arguments=args,
                            )
                            active_tool_id = ""
                            active_tool_name = ""
                            active_tool_input = ""

                    elif event_type == "message_delta":
                        usage = chunk.get("usage", {})
                        comp_tok = usage.get("output_tokens", 0)
                        yield Usage(
                            prompt_tokens=prompt_tok,
                            completion_tokens=comp_tok,
                            total_tokens=prompt_tok + comp_tok,
                        )
                        stop_reason = chunk.get("delta", {}).get("stop_reason")
                        if stop_reason:
                            yield Finish(reason=stop_reason)

        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            raise ProviderError(
                code=JUL_PROV_TIMEOUT if isinstance(exc, asyncio.TimeoutError) else JUL_PROV_UNAVAILABLE,
                message=f"Network error contacting Anthropic: {exc}",
                retryable=True,
                provider=self.name,
            ) from exc

    async def count_tokens(self, req: ChatRequest) -> int:
        total_chars = sum(len(m.content) for m in req.messages)
        return max(1, total_chars // 4)

    async def healthcheck(self) -> HealthStatus:
        t0 = time.perf_counter()
        session = await self._get_session()
        # Light test ping
        try:
            async with session.get(f"{self.base_url}/models", timeout=aiohttp.ClientTimeout(total=5)) as resp:
                lat = (time.perf_counter() - t0) * 1000
                return HealthStatus(ok=True, latency_ms=lat, message="OK")
        except Exception as e:
            return HealthStatus(ok=False, message=str(e))

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

