"""
Julius Official LLM Providers Package (WS1).

Exports official API adapters, LLMRouter, protocol base, and factory loader.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from src.providers.base import (
    ChatMessage,
    ChatRequest,
    Finish,
    HealthStatus,
    LLMEvent,
    LLMProvider,
    LLMResponse,
    ProviderCapabilities,
    ReasoningDelta,
    TextDelta,
    ToolCallDelta,
    ToolCallDone,
    ToolDefinition,
    Usage,
)
from src.providers.openai import OpenAIProvider
from src.providers.anthropic import AnthropicProvider
from src.providers.gemini import GeminiProvider
from src.providers.xai import XAIProvider
from src.providers.moonshot import MoonshotProvider
from src.providers.deepseek import DeepSeekProvider
from src.providers.perplexity import PerplexityProvider
from src.providers.nim import NvidiaNIMProvider
from src.providers.ollama import OllamaProvider
from src.providers.openai_compat import OpenAICompatibleProvider
from src.providers.router import LLMRouter, ProviderRouter

_REGISTRY: Dict[str, type[LLMProvider]] = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "gemini": GeminiProvider,
    "xai": XAIProvider,
    "grok": XAIProvider,
    "moonshot": MoonshotProvider,
    "kimi": MoonshotProvider,
    "deepseek": DeepSeekProvider,
    "perplexity": PerplexityProvider,
    "nvidia": NvidiaNIMProvider,
    "nemotron": NvidiaNIMProvider,
    "ollama": OllamaProvider,
    "openai_compat": OpenAICompatibleProvider,
}


def create_provider(name: str, **kwargs) -> LLMProvider:
    """Instantiate a provider adapter by name."""
    key = name.lower()
    cls = _REGISTRY.get(key)
    if not cls:
        raise ValueError(f"Unknown provider '{name}'. Available: {', '.join(sorted(_REGISTRY.keys()))}")
    return cls(**kwargs)


def list_providers() -> list[str]:
    """Return sorted list of supported provider names."""
    return sorted(_REGISTRY.keys())


get_provider = create_provider


def create_default_router(workspace: Optional[str] = None) -> LLMRouter:
    """Create a fully-configured router pre-loaded with all supported provider adapters."""
    router = LLMRouter(workspace=workspace)
    for name, cls in _REGISTRY.items():
        try:
            prov = cls()
            router.register_provider(name, prov)
        except Exception:
            # Skip if specific requirements like local loopback validation fail
            pass
    return router


__all__ = [
    "LLMProvider",
    "ProviderCapabilities",
    "ChatMessage",
    "ChatRequest",
    "ToolDefinition",
    "ToolCall",
    "ToolCallDelta",
    "ToolCallDone",
    "TextDelta",
    "ReasoningDelta",
    "Usage",
    "Finish",
    "HealthStatus",
    "LLMEvent",
    "OpenAIProvider",
    "AnthropicProvider",
    "GeminiProvider",
    "XAIProvider",
    "MoonshotProvider",
    "DeepSeekProvider",
    "PerplexityProvider",
    "NvidiaNIMProvider",
    "OllamaProvider",
    "OpenAICompatibleProvider",
    "LLMRouter",
    "ProviderRouter",
    "LLMResponse",
    "create_provider",
    "create_default_router",
    "list_providers",
    "get_provider",
]

