"""
OpenAI-Compatible Direct API Adapter (WS1.2, WS1.3).

Powers OpenAI, xAI, Moonshot, DeepSeek, Perplexity, NVIDIA NIM, and Generic endpoints.
Zero DOM scraping, 100% direct HTTP streaming.
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
    JUL_PROV_CONTEXT_TOO_LARGE,
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
    ProviderErrorEvent,
    ReasoningDelta,
    TextDelta,
    ToolCallDelta,
    ToolCallDone,
    Usage,
)

logger = logging.getLogger(__name__)


class OpenAICompatibleProvider(LLMProvider):
    """
    Standard adapter for any provider exposing an OpenAI-compatible /chat/completions endpoint.
    """

    def __init__(
        self,
        name: str = "openai_compat",
        base_url: str = "https://api.openai.com/v1",
        api_key: Optional[str] = None,
        default_model: str = "gpt-4o",
        capabilities: Optional[ProviderCapabilities] = None,
        custom_headers: Optional[Dict[str, str]] = None,
    ) -> None:
        self._name = name
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or ""
        self.default_model = default_model
        self._capabilities = capabilities or ProviderCapabilities()
        self.custom_headers = custom_headers or {}
        self._session: Optional[aiohttp.ClientSession] = None

    @property
    def name(self) -> str:
        return self._name

    def capabilities(self) -> ProviderCapabilities:
        return self._capabilities

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=120, connect=15, sock_read=60)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    def _format_request_payload(self, req: ChatRequest) -> Dict[str, Any]:
        """Convert ChatRequest to standard OpenAI payload format."""
        formatted_messages = []
        for msg in req.messages:
            m_dict: Dict[str, Any] = {"role": msg.role, "content": msg.content}
            if msg.name:
                m_dict["name"] = msg.name
            if msg.tool_call_id:
                m_dict["tool_call_id"] = msg.tool_call_id
            if msg.tool_calls:
                m_dict["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments) if isinstance(tc.arguments, dict) else str(tc.arguments),
                        },
                    }
                    for tc in msg.tool_calls
                ]
            formatted_messages.append(m_dict)

        payload: Dict[str, Any] = {
            "model": req.model or self.default_model,
            "messages": formatted_messages,
            "stream": req.stream,
            "temperature": req.temperature,
        }

        if req.max_tokens:
            payload["max_tokens"] = req.max_tokens

        if req.tools and self._capabilities.tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in req.tools
            ]

        if req.json_mode and self._capabilities.json_mode:
            payload["response_format"] = {"type": "json_object"}

        # Include stream_options for usage reporting if supported
        if req.stream and self._capabilities.streams_usage:
            payload["stream_options"] = {"include_usage": True}

        return payload

    async def stream(
        self,
        req: ChatRequest,
        *,
        cancel: Optional[asyncio.Event] = None,
    ) -> AsyncIterator[LLMEvent]:
        """Stream LLM events over HTTP SSE."""
        session = await self._get_session()
        url = f"{self.base_url}/chat/completions"

        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            **self.custom_headers,
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = self._format_request_payload(req)

        try:
            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status == 401 or resp.status == 403:
                    body = await resp.text()
                    raise ProviderError(
                        code=JUL_PROV_AUTH_FAILED,
                        message=f"Authentication failed for {self.name}: {body[:200]}",
                        hint="Check your API key in ~/.julius/config.toml or environment variables.",
                        provider=self.name,
                    )
                elif resp.status == 429:
                    body = await resp.text()
                    raise ProviderError(
                        code=JUL_PROV_RATE_LIMITED,
                        message=f"Rate limit exceeded on {self.name}: {body[:200]}",
                        hint="Wait for the provider quota to reset or configure a fallback provider.",
                        retryable=True,
                        provider=self.name,
                    )
                elif resp.status == 400:
                    body = await resp.text()
                    if "context" in body.lower() or "token" in body.lower():
                        code = JUL_PROV_CONTEXT_TOO_LARGE
                    else:
                        code = JUL_PROV_BAD_REQUEST
                    raise ProviderError(
                        code=code,
                        message=f"Bad request to {self.name}: {body[:200]}",
                        hint="Reduce context size or check requested model parameter compatibility.",
                        provider=self.name,
                    )
                elif resp.status >= 500:
                    body = await resp.text()
                    raise ProviderError(
                        code=JUL_PROV_UNAVAILABLE,
                        message=f"{self.name} server error ({resp.status}): {body[:200]}",
                        hint="Provider service is temporarily degraded; router will attempt retry/fallback.",
                        retryable=True,
                        provider=self.name,
                    )

                # Track active tool call assembly
                tool_calls_in_progress: Dict[int, Dict[str, Any]] = {}

                async for line_bytes in resp.content:
                    if cancel and cancel.is_set():
                        yield Finish(reason="cancelled")
                        break

                    line = line_bytes.decode("utf-8").strip()
                    if not line or not line.startswith("data:"):
                        continue

                    data_str = line[5:].strip()
                    if data_str == "[DONE]":
                        # Emit any assembled completed tool calls
                        for idx in sorted(tool_calls_in_progress.keys()):
                            tc_data = tool_calls_in_progress[idx]
                            try:
                                args_obj = json.loads(tc_data["args"]) if tc_data["args"] else {}
                            except Exception:
                                args_obj = {"raw": tc_data["args"]}
                            yield ToolCallDone(
                                id=tc_data["id"],
                                name=tc_data["name"],
                                arguments=args_obj,
                            )
                        tool_calls_in_progress.clear()
                        yield Finish(reason="stop")
                        break

                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    # Check for usage in chunk
                    if "usage" in chunk and chunk["usage"]:
                        u = chunk["usage"]
                        yield Usage(
                            prompt_tokens=u.get("prompt_tokens", 0),
                            completion_tokens=u.get("completion_tokens", 0),
                            total_tokens=u.get("total_tokens", 0),
                        )

                    choices = chunk.get("choices") or []
                    if not choices:
                        continue

                    choice = choices[0]
                    delta = choice.get("delta") or {}

                    # 1. Reasoning / Thinking content
                    reasoning = delta.get("reasoning_content") or delta.get("thinking")
                    if reasoning:
                        yield ReasoningDelta(reasoning=reasoning)

                    # 2. Text content
                    content = delta.get("content")
                    if content:
                        yield TextDelta(text=content)

                    # 3. Tool calls streaming
                    raw_tool_calls = delta.get("tool_calls") or []
                    for tc in raw_tool_calls:
                        idx = tc.get("index", 0)
                        fn = tc.get("function") or {}
                        tc_id = tc.get("id") or ""
                        tc_name = fn.get("name")
                        tc_args_delta = fn.get("arguments") or ""

                        if idx not in tool_calls_in_progress:
                            tool_calls_in_progress[idx] = {
                                "id": tc_id,
                                "name": tc_name or "",
                                "args": "",
                            }
                        if tc_id:
                            tool_calls_in_progress[idx]["id"] = tc_id
                        if tc_name:
                            tool_calls_in_progress[idx]["name"] = tc_name
                        tool_calls_in_progress[idx]["args"] += tc_args_delta

                        yield ToolCallDelta(
                            id=tool_calls_in_progress[idx]["id"],
                            name=tc_name,
                            arguments_delta=tc_args_delta,
                        )

                    # Finish reason check
                    finish_reason = choice.get("finish_reason")
                    if finish_reason:
                        # Flush completed tool calls
                        for idx in sorted(tool_calls_in_progress.keys()):
                            tc_data = tool_calls_in_progress[idx]
                            try:
                                args_obj = json.loads(tc_data["args"]) if tc_data["args"] else {}
                            except Exception:
                                args_obj = {"raw": tc_data["args"]}
                            yield ToolCallDone(
                                id=tc_data["id"],
                                name=tc_data["name"],
                                arguments=args_obj,
                            )
                        tool_calls_in_progress.clear()
                        yield Finish(reason=finish_reason)
                        break

        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            logger.error(f"Network error in {self.name} stream: {exc}")
            raise ProviderError(
                code=JUL_PROV_TIMEOUT if isinstance(exc, asyncio.TimeoutError) else JUL_PROV_UNAVAILABLE,
                message=f"Network error contacting {self.name}: {exc}",
                hint="Verify internet connection, host accessibility, or proxy settings.",
                retryable=True,
                provider=self.name,
            ) from exc

    async def count_tokens(self, req: ChatRequest) -> int:
        """Rough token approximation (4 characters per token)."""
        total_chars = sum(len(m.content) for m in req.messages)
        if req.tools:
            for t in req.tools:
                total_chars += len(t.name) + len(t.description) + len(str(t.parameters))
        return max(1, total_chars // 4)

    async def healthcheck(self) -> HealthStatus:
        """Lightweight endpoint probe."""
        t0 = time.perf_counter()
        session = await self._get_session()
        # Ping /models or root
        url = f"{self.base_url}/models"
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                latency = (time.perf_counter() - t0) * 1000
                if resp.status in (200, 401, 403):  # 401/403 proves server is up and reachable
                    return HealthStatus(ok=True, latency_ms=latency, message=f"HTTP {resp.status}", model=self.default_model)
                return HealthStatus(ok=False, latency_ms=latency, message=f"HTTP {resp.status}")
        except Exception as e:
            return HealthStatus(ok=False, message=str(e))

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

