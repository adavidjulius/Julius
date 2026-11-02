"""DeepSeek provider metadata and configuration."""

from __future__ import annotations

import os
from typing import Any, Optional
from .base import ChatProvider


class DeepSeekProvider(ChatProvider):
    """Provider for DeepSeek official API and chat routing."""

    def __init__(self, model: str = "deepseek") -> None:
        self.base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip().rstrip("/")
        self.model = model.strip()
        self.default_model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat").strip()
        self.api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()

    @property
    def name(self) -> str:
        return "DeepSeek"

    @property
    def url(self) -> str:
        if "r1" in self.model.lower():
            return "https://chat.deepseek.com/?model=deepseek-r1"
        return "https://chat.deepseek.com/?model=deepseek-v4-flash"

    @property
    def input_selector(self) -> str:
        return "textarea#chat-input, textarea"

    @property
    def send_button_selector(self) -> str:
        return "button[type='submit'], .send-button"

    @property
    def response_selector(self) -> str:
        return ".prose, .markdown"

    @property
    def streaming_indicator_selector(self) -> str:
        return ".stop-button, .stop"

    async def send_message(self, *args: Any, **kwargs: Any) -> Any:
        return None

    async def extract_response(self, *args: Any, **kwargs: Any) -> str:
        return ""

    async def start_new_chat(self, *args: Any, **kwargs: Any) -> None:
        pass

    @staticmethod
    def _looks_complete(text: str) -> bool:
        """Check if text appears to be a complete JSON action payload."""
        import json
        s = text.strip()
        if (s.startswith("{") and s.endswith("}")) or (s.startswith("[") and s.endswith("]")):
            try:
                json.loads(s)
                return True
            except Exception:
                return False
        if "```json" in s and "```" in s.split("```json", 1)[1]:
            return True
        return False
