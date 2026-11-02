"""ChatGPT API provider metadata and configuration."""

from __future__ import annotations

import os
from typing import Any, Optional
from .base import ChatProvider


class ChatGPTProvider(ChatProvider):
    """Provider for OpenAI / ChatGPT official API."""

    def __init__(self, model: str = "gpt-4o") -> None:
        self.base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip().rstrip("/")
        self.default_model = os.getenv("OPENAI_MODEL", os.getenv("CHATGPT_MODEL", model)).strip()
        self.model = self.default_model
        self.api_key = (os.getenv("OPENAI_API_KEY") or os.getenv("CHATGPT_API_KEY", "")).strip()

    @property
    def name(self) -> str:
        return "ChatGPT"

    @property
    def url(self) -> str:
        return self.base_url or "https://chatgpt.com/"
