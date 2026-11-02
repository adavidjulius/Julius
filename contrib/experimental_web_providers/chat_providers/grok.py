"""Grok API provider metadata and configuration."""

from __future__ import annotations

import os
from typing import Any, Optional
from .base import ChatProvider


class GrokProvider(ChatProvider):
    """Provider for xAI Grok official API."""

    def __init__(self, model: str = "grok-2-latest") -> None:
        self.base_url = os.getenv("GROK_BASE_URL", "https://api.x.ai/v1").strip().rstrip("/")
        self.default_model = os.getenv("GROK_MODEL", model).strip()
        self.model = self.default_model
        self.api_key = (os.getenv("GROK_API_KEY") or os.getenv("XAI_API_KEY", "")).strip()

    @property
    def name(self) -> str:
        return "Grok"

    @property
    def url(self) -> str:
        return self.base_url or "https://grok.com/"
