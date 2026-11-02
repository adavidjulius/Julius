"""Kimi API provider metadata and configuration."""

from __future__ import annotations

import os
from typing import Any, Optional
from .base import ChatProvider


class KimiProvider(ChatProvider):
    """Provider for Moonshot AI Kimi official API."""

    def __init__(self, model: str = "kimi-k3") -> None:
        self.base_url = os.getenv("KIMI_BASE_URL", "https://api.moonshot.ai/v1").strip().rstrip("/")
        self.default_model = os.getenv("KIMI_MODEL", model).strip()
        self.model = self.default_model
        self.api_key = (os.getenv("KIMI_API_KEY") or os.getenv("MOONSHOT_API_KEY", "")).strip()

    @property
    def name(self) -> str:
        return "Kimi"

    @property
    def url(self) -> str:
        return self.base_url or "https://kimi.moonshot.cn/"
