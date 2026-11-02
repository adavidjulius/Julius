# Module docstring explaining this file acts as the plugin registry and factory for all chat providers
"""Chat provider plugin registry and factory for Julius."""

# Enable modern type hinting feature support across Python versions
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

# Only import abstract base provider during static type analysis to prevent circular runtime imports
if TYPE_CHECKING:
    from .base import ChatProvider

# ── Provider registry ─────────────────────────────────────────────────────────

# Initialize a module-level dictionary mapping lowercase provider names to their provider classes
_REGISTRY: dict[str, type[ChatProvider]] = {}


def register_provider(name: str, cls: type[ChatProvider]) -> None:
    """Register a provider class under the given name."""
    # Convert name to lowercase and store the class reference in the registry
    _REGISTRY[name.lower()] = cls


# Define factory function to retrieve and instantiate a provider instance by its name
def get_provider(name: str) -> ChatProvider:
    """Instantiate and return a provider by name."""
    logger.warning("src.chat_providers.get_provider is deprecated; migrate to src.providers (ProviderRouter/create_provider).")
    # Convert requested provider name to lowercase key
    key = name.lower()
    # Check if the requested key does not exist in the registered providers dictionary
    if key not in _REGISTRY:
        # Join all available provider names into a comma-separated string for clear error reporting
        available = ', '.join(sorted(_REGISTRY.keys()))
        # Raise ValueError with descriptive message listing all supported providers
        raise ValueError(f"Unknown provider '{name}'. Available: {available}")
    # Instantiate and return a new instance of the registered provider class
    return _REGISTRY[key]()


def list_providers() -> list[str]:
    """Return a sorted list of registered provider names."""
    # Return a sorted list of all registered provider dictionary keys
    return sorted(_REGISTRY.keys())


# ── Auto-register built-in providers on import ────────────────────────────────

# Private function that automatically imports and registers all built-in providers on startup
def _auto_register() -> None:
    from .chatgpt import ChatGPTProvider
    from .deepseek import DeepSeekProvider
    from .grok import GrokProvider
    from .perplexity import PerplexityProvider
    from .gemini import GeminiProvider
    from .kimi import KimiProvider
    from .ollama import OllamaProvider
    from .aifreeforever import AIFreeForeverProvider
    from .nvidia import NvidiaProvider

    register_provider('nvidia', NvidiaProvider)
    register_provider('nvidia-nim', NvidiaProvider)
    register_provider('nemotron', NvidiaProvider)
    register_provider('nemotron-550b', NvidiaProvider)
    register_provider('nvidia-550b', NvidiaProvider)
    register_provider('chatgpt', ChatGPTProvider)
    register_provider('deepseek', DeepSeekProvider)
    # Register ChatGPT provider
    register_provider('chatgpt', ChatGPTProvider)
    # Register Grok provider
    register_provider('grok', GrokProvider)
    # Register Perplexity provider
    register_provider('perplexity', PerplexityProvider)
    # Register Gemini provider
    register_provider('gemini', GeminiProvider)
    # Register Kimi provider
    register_provider('kimi', KimiProvider)
    # Register Ollama provider
    register_provider('ollama', OllamaProvider)
    # Register Llama alias mapping to Ollama provider
    register_provider('llama', OllamaProvider)

    # Register internal backward-compatibility alias for legacy aifreeforever references
    register_provider('aifreeforever', DeepSeekProvider)
    # Register internal backward-compatibility alias for short aifree
    register_provider('aifree', DeepSeekProvider)
    # Register internal backward-compatibility alias for deepseek-v4-flash
    register_provider('deepseek-v4-flash', DeepSeekProvider)
    # Register internal backward-compatibility alias for free-deepseek
    register_provider('free-deepseek', DeepSeekProvider)


# Execute the auto-registration function immediately upon module import
_auto_register()

# Define public module exports list
__all__ = ['get_provider', 'list_providers', 'register_provider']
