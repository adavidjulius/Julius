"""AI Free Forever provider metadata and configuration."""

from __future__ import annotations

import os
from typing import Any, Optional
from .base import ChatProvider


class AIFreeForeverProvider(ChatProvider):
    """Provider configuration for legacy AI Free Forever."""

    def __init__(self, model: str = "deepseek-v4-flash") -> None:
        self.base_url = "https://aifreeforever.com"
        self.default_model = model
        self.model = model

    @property
    def name(self) -> str:
        return "AIFreeForever"

    @property
    def url(self) -> str:
        return self.base_url
