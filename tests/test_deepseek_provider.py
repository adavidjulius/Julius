"""Unit tests for DeepSeek direct API provider integration and functionality in Julius."""

import os
import pytest
from unittest.mock import patch

from src.chat_providers import get_provider, list_providers
from src.chat_providers.deepseek import DeepSeekProvider


def test_deepseek_provider_registered():
    assert "deepseek" in list_providers()

    provider = get_provider("deepseek")
    assert isinstance(provider, DeepSeekProvider)
    assert provider.name == "DeepSeek"
    assert "deepseek" in provider.url


def test_deepseek_provider_model_routing():
    p1 = DeepSeekProvider(model="deepseek")
    assert "deepseek-v4-flash" in p1.url

    p2 = DeepSeekProvider(model="deepseek-r1")
    assert "deepseek-r1" in p2.url


def test_deepseek_provider_env_configuration():
    with patch.dict(os.environ, {
        "DEEPSEEK_BASE_URL": "https://custom.deepseek.api/v1",
        "DEEPSEEK_MODEL": "deepseek-coder",
        "DEEPSEEK_API_KEY": "sk-deepseek-test-key",
    }):
        provider = DeepSeekProvider()
        assert provider.base_url == "https://custom.deepseek.api/v1"
        assert provider.default_model == "deepseek-coder"
        assert provider.api_key == "sk-deepseek-test-key"


def test_deepseek_provider_selectors():
    provider = DeepSeekProvider()
    assert "textarea" in provider.input_selector
    assert "button" in provider.send_button_selector
    assert "prose" in provider.response_selector or "markdown" in provider.response_selector
    assert "stop" in provider.streaming_indicator_selector.lower()


@pytest.mark.asyncio
async def test_deepseek_provider_async_noops():
    provider = DeepSeekProvider()
    # Direct API mode: these are non-blocking safe stubs
    res = await provider.send_message()
    assert res is None
    extracted = await provider.extract_response()
    assert extracted == ""
    await provider.start_new_chat()


def test_deepseek_provider_looks_complete():
    # Valid JSON objects and arrays
    assert DeepSeekProvider._looks_complete('{"action": "bash", "args": {"command": "ls"}}') is True
    assert DeepSeekProvider._looks_complete('[{"id": 1}]') is True

    # Incomplete or invalid JSON
    assert DeepSeekProvider._looks_complete('{"action": "bash"') is False
    assert DeepSeekProvider._looks_complete('Plain text without json') is False

    # Markdown wrapped json
    assert DeepSeekProvider._looks_complete('```json\n{"status": "ok"}\n```') is True
    assert DeepSeekProvider._looks_complete('```json\n{"status": "ok"') is False
