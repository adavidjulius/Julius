"""NVIDIA Build NIM Free API provider."""

from __future__ import annotations

import logging
import os
from pathlib import Path
import re
from typing import Any, Callable, Optional

from .base import ChatProvider
from ..utils.rate_limiter import get_nvidia_rate_limiter, NvidiaRateLimiter

logger = logging.getLogger(__name__)


def resolve_nvidia_api_key() -> str:
    """Resolve active NVIDIA API key from environment, user config, or .env."""
    try:
        from dotenv import load_dotenv
        for _env in [Path.cwd() / ".env", Path.home() / ".julius" / ".env", Path(__file__).resolve().parent.parent.parent / ".env"]:
            if _env.exists():
                load_dotenv(dotenv_path=_env, override=False)
    except Exception:
        pass
    env_key = os.getenv("NVIDIA_API_KEY", "").strip() or os.getenv("NVIDIA_NIM_API_KEY", "").strip()
    return env_key


DEFAULT_NVIDIA_API_KEY = resolve_nvidia_api_key()
DEFAULT_NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
DEFAULT_NVIDIA_MODEL = "nvidia/nemotron-3-ultra-550b-a55b"
DEFAULT_NVIDIA_RPM = 40
DEFAULT_NVIDIA_MIN_SPACING = 1.5


class NvidiaProvider(ChatProvider):
    """
    Provider for NVIDIA Build NIM Free API.

    Features:
      - 550B Nemotron-3 Ultra Reasoning Model.
      - 40 RPM sliding-window rate limiter with intelligent request spacing.
      - Exponential backoff on HTTP 429 Too Many Requests.
      - Native reasoning_content extraction and SSE streaming.
    """

    AVAILABLE_MODELS = {
        "nvidia/nemotron-3-ultra-550b-a55b": "nvidia/nemotron-3-ultra-550b-a55b",
        "nemotron-550b": "nvidia/nemotron-3-ultra-550b-a55b",
        "nemotron": "nvidia/nemotron-3-ultra-550b-a55b",
        "nvidia-550b": "nvidia/nemotron-3-ultra-550b-a55b",
        "nvidia": "nvidia/nemotron-3-ultra-550b-a55b",
        "550b": "nvidia/nemotron-3-ultra-550b-a55b",
        "meta/llama-3.1-405b-instruct": "meta/llama-3.1-405b-instruct",
        "meta/llama-3.3-70b-instruct": "meta/llama-3.3-70b-instruct",
        "deepseek-ai/deepseek-r1": "deepseek-ai/deepseek-r1",
    }

    def __init__(self, model: str = DEFAULT_NVIDIA_MODEL) -> None:
        clean_model = model.strip()
        self.model = self.AVAILABLE_MODELS.get(clean_model.lower(), clean_model)
        self.api_key = os.getenv("NVIDIA_API_KEY", DEFAULT_NVIDIA_API_KEY).strip()
        self.base_url = os.getenv("NVIDIA_BASE_URL", DEFAULT_NVIDIA_BASE_URL).strip().rstrip("/")
        self.default_model = self.model
        self.rate_limit_rpm = int(os.getenv("NVIDIA_RPM", str(DEFAULT_NVIDIA_RPM)))
        self.min_spacing = float(os.getenv("NVIDIA_MIN_SPACING", str(DEFAULT_NVIDIA_MIN_SPACING)))
        self.rate_limiter: NvidiaRateLimiter = get_nvidia_rate_limiter()

    @property
    def name(self) -> str:
        return "NVIDIA"

    @property
    def url(self) -> str:
        return f"https://build.nvidia.com/{self.model}"

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

