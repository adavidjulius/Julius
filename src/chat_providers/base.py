"""Abstract base class for LLM chat providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable, Optional


class ChatProvider(ABC):
    """
    Base class for all direct API and local LLM chat providers.

    Supplies model identification, endpoint routing, and interaction contracts.
    """

    # ── Identity ──────────────────────────────────────────────────

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable provider name (e.g. 'NVIDIA', 'Ollama')."""

    @property
    @abstractmethod
    def url(self) -> str:
        """Base endpoint or portal URL for the provider."""

    @property
    def is_api(self) -> bool:
        """Whether this provider uses direct API communication."""
        return True

    # ── Legacy Selector Compatibility (Non-abstract defaults) ────

    @property
    def input_selector(self) -> str:
        """Default selector retained for backward compatibility."""
        return "textarea"

    @property
    def send_button_selector(self) -> str:
        """Default selector retained for backward compatibility."""
        return "button[type='submit']"

    @property
    def response_selector(self) -> str:
        """Default selector retained for backward compatibility."""
        return ".response"

    @property
    def streaming_indicator_selector(self) -> str:
        """Default selector retained for backward compatibility."""
        return ".streaming"

    # ── Interaction methods ───────────────────────────────────────

    async def send_message(self, *args: Any, **kwargs: Any) -> Any:
        """Send a prompt/message to the model provider."""
        return None

    async def wait_for_response(self, *args: Any, **kwargs: Any) -> str:
        """Wait for the model to finish generating and return response text."""
        return ""

    async def extract_response(self, *args: Any, **kwargs: Any) -> str:
        """Extract the text content of the last model response."""
        return ""

    async def upload_image(self, *args: Any, **kwargs: Any) -> None:
        """Upload an image to the provider if supported."""
        pass

    async def start_new_chat(self, *args: Any, **kwargs: Any) -> None:
        """Reset or initialize a new conversation session."""
        pass

    async def close(self) -> None:
        """Clean up active provider network or client resources."""
        pass

    def __repr__(self) -> str:
        return f"{type(self).__name__}(url={self.url!r})"

