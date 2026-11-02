"""Perplexity API provider metadata and configuration."""

from __future__ import annotations

import os
from typing import Any, Optional
from .base import ChatProvider


class PerplexityProvider(ChatProvider):
    """Provider for Perplexity AI official API."""

    def __init__(self, model: str = "sonar") -> None:
        self.base_url = os.getenv("PERPLEXITY_BASE_URL", "https://api.perplexity.ai").strip().rstrip("/")
        self.default_model = os.getenv("PERPLEXITY_MODEL", model).strip()
        self.model = self.default_model
        self.api_key = os.getenv("PERPLEXITY_API_KEY", "").strip()

    @property
    def name(self) -> str:
        return "Perplexity"

    @property
    def url(self) -> str:
        return self.base_url or "https://perplexity.ai/"
