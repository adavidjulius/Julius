"""Gemini API provider metadata and configuration."""

from __future__ import annotations

import os
from typing import Any, Optional
from .base import ChatProvider


class GeminiProvider(ChatProvider):
    """Provider for Google Gemini official API."""

    def __init__(self, model: str = "gemini-2.0-flash") -> None:
        self.base_url = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai").strip().rstrip("/")
        self.default_model = os.getenv("GEMINI_MODEL", model).strip()
        self.model = self.default_model
        self.api_key = os.getenv("GEMINI_API_KEY", "").strip()

    @property
    def name(self) -> str:
        return "Gemini"

    @property
    def url(self) -> str:
        return self.base_url or "https://gemini.google.com/"
