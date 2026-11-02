"""
Julius LLM Provider Abstraction & Normalized Event Protocol (WS1.1).

Defines the normalized event stream, capability matrix, and provider protocol
so the agent loop never binds directly to vendor-specific payload shapes.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Dict, List, Optional, Protocol, Union, runtime_checkable


# ── Capabilities Matrix ───────────────────────────────────────────────────────

@dataclass(frozen=True)
class ProviderCapabilities:
    """Flags describing what an LLM provider natively supports."""
    tools: bool = True
    parallel_tools: bool = False
    vision: bool = False
    json_mode: bool = True
    reasoning: bool = False
    max_context: int = 128_000
    streams_usage: bool = True
    supports_system_prompt: bool = True


# ── Canonical Data Models ─────────────────────────────────────────────────────

@dataclass
class ToolDefinition:
    """Standardized tool specification passed to the model."""
    name: str
    description: str
    parameters: Dict[str, Any]  # JSON Schema


@dataclass
class ToolCall:
    """Completed tool call emitted by a model."""
    id: str
    name: str
    arguments: Dict[str, Any]


@dataclass
class ChatMessage:
    """Normalized chat message."""
    role: str  # "system", "user", "assistant", "tool"
    content: str
    name: Optional[str] = None
    tool_call_id: Optional[str] = None
    tool_calls: Optional[List[ToolCall]] = None
    reasoning_content: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ChatRequest:
    """Normalized request dispatched to an LLM provider."""
    messages: List[ChatMessage]
    model: str
    tools: Optional[List[ToolDefinition]] = None
    temperature: float = 0.2
    max_tokens: Optional[int] = 4096
    stream: bool = True
    json_mode: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HealthStatus:
    """Provider health check result."""
    ok: bool
    latency_ms: float = 0.0
    message: str = "OK"
    model: Optional[str] = None


# ── Normalized Event Stream Hierarchy ─────────────────────────────────────────

@dataclass
class TextDelta:
    """Chunk of standard response text."""
    text: str


@dataclass
class ReasoningDelta:
    """Chunk of internal reasoning or thinking process."""
    reasoning: str


@dataclass
class ToolCallDelta:
    """Streaming argument or name chunk for a tool call."""
    id: str
    name: Optional[str] = None
    arguments_delta: str = ""


@dataclass
class ToolCallDone:
    """Synthesized complete tool call once streaming chunk is closed."""
    id: str
    name: str
    arguments: Dict[str, Any]


@dataclass
class Usage:
    """Reported or estimated token usage and computed cost."""
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float = 0.0


@dataclass
class Finish:
    """End-of-stream signal with termination reason."""
    reason: str  # "stop", "tool_calls", "length", "cancelled"


@dataclass
class ProviderErrorEvent:
    """Error event emitted during streaming without crashing the stream."""
    code: str
    message: str
    retryable: bool = False


LLMEvent = Union[
    TextDelta,
    ReasoningDelta,
    ToolCallDelta,
    ToolCallDone,
    Usage,
    Finish,
    ProviderErrorEvent,
]


# ── Provider Protocol ─────────────────────────────────────────────────────────

@runtime_checkable
class LLMProvider(Protocol):
    """
    Protocol implemented by all official API adapters.

    Guarantees official API communication only (zero web-scraping).
    """

    @property
    def name(self) -> str:
        """Provider identifier (e.g. 'openai', 'anthropic', 'ollama')."""
        ...

    def capabilities(self) -> ProviderCapabilities:
        """Return provider capabilities."""
        ...

    async def stream(
        self,
        req: ChatRequest,
        *,
        cancel: Optional[asyncio.Event] = None,
    ) -> AsyncIterator[LLMEvent]:
        """Stream normalized LLM events."""
        ...

    async def count_tokens(self, req: ChatRequest) -> int:
        """Calculate approximate or exact token count."""
        ...

    async def healthcheck(self) -> HealthStatus:
        """Perform a quick ping or lightweight probe to verify endpoint health."""
        ...

    async def close(self) -> None:
        """Release underlying HTTP client sessions."""
        ...


@dataclass
class LLMResponse:
    """Structured response from the LLM provider/router."""
    raw_text: str = ""
    parsed_json: Optional[Dict[str, Any]] = None
    provider: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    attempt: int = 1
    error: Optional[str] = None
    text: str = ""
    success: bool = True
    reasoning: str = ""

    def __post_init__(self) -> None:
        if not self.text and self.raw_text:
            self.text = self.raw_text
        elif not self.raw_text and self.text:
            self.raw_text = self.text
        if self.error:
            self.success = False


