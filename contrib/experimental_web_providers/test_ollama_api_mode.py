"""
Tests for Ollama Local LLM Direct API Mode.
Verifies HTTP API streaming, thinking token handling, LAN auto-discovery, and TUI model parsing.
"""

import asyncio
import json
import os
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from src.llm_web_client import LLMResponse, WebLLMClient


@pytest.mark.asyncio
async def test_ollama_health_probe_discovers_models():
    """Verify _check_ollama_health correctly parses tags and discovers installed models."""
    client = WebLLMClient()
    client._ollama_url = "http://mock-ollama:11434"
    client._ollama_model = "qwen2.5:latest"

    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value={
        "models": [
            {"name": "huihui_ai/qwen2.5-coder-uncensored:latest"},
            {"name": "deepseek-r1:8b"}
        ]
    })

    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    mock_session.get.return_value.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_session.get.return_value.__aexit__ = AsyncMock(return_value=None)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        ok = await client._check_ollama_health()
        assert ok is True
        assert len(client._available_ollama_models) == 2
        assert client._ollama_model in ("deepseek-r1:8b", "huihui_ai/qwen2.5-coder-uncensored:latest")


@pytest.mark.asyncio
async def test_initialize_uses_api_when_ollama_online():
    """Verify WebLLMClient activates direct API mode when Ollama responds."""
    client = WebLLMClient()

    with patch.object(client, "_check_ollama_health", new=AsyncMock(return_value=True)):
        await client.initialize(provider_name="ollama")
        assert client.is_initialized is True
        assert client.is_logged_in is True
        assert client._use_api is True
        assert "ollama" in client.provider_name


@pytest.mark.asyncio
async def test_send_message_uses_ollama_api():
    """Verify send_message routes through Ollama API when API mode is active."""
    client = WebLLMClient()
    client._initialized = True
    client._use_api = True
    client._provider_key = "ollama"
    client._ollama_model = "qwen2.5:latest"

    expected_response = LLMResponse(
        raw_text='```json\n{"thought": "test", "action": "done", "args": {}}\n```',
        parsed_json={"thought": "test", "action": "done", "args": {}},
        provider="ollama (qwen2.5:latest)",
    )

    with patch.object(client, "_call_ollama_api", new=AsyncMock(return_value=expected_response)) as mock_api:
        resp = await client.send_message("Hello Ollama")
        mock_api.assert_called_once()
        assert resp.parsed_json["action"] == "done"
        assert resp.provider == "ollama (qwen2.5:latest)"


@pytest.mark.asyncio
async def test_send_message_safe_error_on_api_failure():
    """Verify send_message returns structured error response when Ollama API errors."""
    client = WebLLMClient()
    client._initialized = True
    client._use_api = True
    client._provider_key = "ollama"

    with patch.object(client, "_call_ollama_api", side_effect=RuntimeError("Connection refused")):
        resp = await client.send_message("Task requiring fallback")
        assert resp.success is False
        assert "Connection refused" in resp.error


@pytest.mark.asyncio
async def test_start_new_conversation_resets_api_messages():
    """Verify start_new_conversation clears in-memory Ollama message history."""
    client = WebLLMClient()
    client._initialized = True
    client._api_messages = [{"role": "user", "content": "hello"}]
    await client.start_new_conversation()
    assert client._api_messages == []


def test_llama_alias_resolves_to_ollama_provider():
    """Verify that 'llama' resolves to OllamaProvider identically to 'ollama'."""
    from src.chat_providers import get_provider
    from src.chat_providers.ollama import OllamaProvider

    prov_ollama = get_provider("ollama")
    prov_llama = get_provider("llama")
    assert isinstance(prov_ollama, OllamaProvider)
    assert isinstance(prov_llama, OllamaProvider)
    assert prov_llama.name == "ollama"


@pytest.mark.asyncio
async def test_plan_mode_streams_thinking_tokens():
    """Verify that in /plan mode, thinking tokens are streamed live to on_chunk."""
    client = WebLLMClient()
    client._ollama_url = "http://127.0.0.1:11434"
    client._ollama_model = "qwen2.5:latest"

    lines = [
        json.dumps({"message": {"thinking": "Analyzing requirements... "}}).encode("utf-8") + b"\n",
        json.dumps({"message": {"content": "Here is the implementation plan."}}).encode("utf-8") + b"\n",
        json.dumps({"done": True}).encode("utf-8") + b"\n",
    ]

    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.content.readline = AsyncMock(side_effect=lines + [b""])

    mock_session = MagicMock()
    mock_session.closed = False
    mock_session.post.return_value.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_session.post.return_value.__aexit__ = AsyncMock(return_value=None)
    client._session = mock_session

    streamed_chunks = []
    resp = await client._call_ollama_api(
        prompt="/plan Build authentication flow",
        on_chunk=lambda c: streamed_chunks.append(c)
    )

    assert any("Analyzing requirements" in c for c in streamed_chunks)
    assert any("implementation plan" in c for c in streamed_chunks)
    assert "<think>" in resp.raw_text
    assert "Analyzing requirements" in resp.raw_text


@pytest.mark.asyncio
async def test_lan_auto_discovery_roaming():
    """Verify that _check_ollama_health dynamically discovers roamed IP if primary fails."""
    client = WebLLMClient()
    client._ollama_url = "http://192.168.0.999:11434"

    with patch.object(client, "_probe_single_ollama_url", side_effect=[False, True]):
        with patch.object(client, "_discover_ollama_on_lan", new=AsyncMock(return_value="http://192.168.195.42:11434")):
            with patch.object(client, "_persist_ollama_host"):
                ok = await client._check_ollama_health()
                assert ok is True
                assert client._ollama_url == "http://192.168.195.42:11434"


@pytest.mark.asyncio
async def test_live_ollama_models_discovery_in_tui():
    """Verify that JuliusCLIV3App._get_live_ollama_models dynamically parses Ollama API tags."""
    from src.cli.v3_tui import JuliusCLIV3App
    app = JuliusCLIV3App()

    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value={
        "models": [
            {
                "name": "mannix/llama3.1-8b-lexi:latest",
                "size": 4661226236,
                "details": {"parameter_size": "8.0B", "quantization_level": "Q4_0"}
            },
            {
                "name": "hf.co/HauhauCS/Qwen3.5-9B-Uncensored-HauhauCS-Aggressive:Q4_K_M",
                "size": 6548749153,
                "details": {"parameter_size": "8.95B", "quantization_level": "Q4_K_M"}
            }
        ]
    })

    with patch("aiohttp.ClientSession.get", return_value=mock_resp):
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=None)

        models = await app._get_live_ollama_models()
        assert len(models) == 2
        assert models[0]["short_alias"] == "lexi"
        assert models[0]["display_name"] == "Llama 3.1 8B Lexi (Ollama LAN)"
        assert models[1]["short_alias"] == "qwen"
        assert models[1]["display_name"] == "Qwen 3.5 9B Uncensored (Ollama LAN)"
