"""Ollama Local LLM Provider (LAN / On-Device)."""

from __future__ import annotations

import os
from typing import Any
from .base import ChatProvider


class OllamaProvider(ChatProvider):
    """Provider implementation for Ollama running locally or on a LAN device."""

    def __init__(self) -> None:
        raw_url = os.getenv("OLLAMA_HOST", os.getenv("OLLAMA_API_URL", "http://localhost:11434")).strip()
        if not raw_url.startswith("http://") and not raw_url.startswith("https://"):
            raw_url = f"http://{raw_url}"
        self.base_url = raw_url.rstrip("/")
        self.default_model = os.getenv("OLLAMA_MODEL", "hushus_ai/deepseek-r1-uncalibrated-14b").strip()
        self.fallback_provider = os.getenv("LOCAL_LLM_FALLBACK_PROVIDER", "nvidia").strip().lower()

    @property
    def name(self) -> str:
        return "ollama"

    @property
    def url(self) -> str:
        return self.base_url

    @property
    def input_selector(self) -> str:
        return "textarea"

    @property
    def send_button_selector(self) -> str:
        return "button[type='submit']"

    @property
    def response_selector(self) -> str:
        return ".response"

    @property
    def streaming_indicator_selector(self) -> str:
        return ".streaming"

    async def send_prompt(self, page: Any, prompt: str) -> None:
        pass

    async def extract_response(self, page: Any) -> str:
        return ""

    async def is_generating(self, page: Any) -> bool:
        return False
