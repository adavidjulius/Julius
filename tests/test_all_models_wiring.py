"""
Comprehensive test suite verifying wiring, execution, and output handling
for all models in the Julius model list:
  1. DeepSeek (deepseek)
  2. ChatGPT (chatgpt)
  3. Gemini (gemini)
  4. Grok (grok)
  5. Kimi (kimi)
  6. Perplexity (perplexity)
  7. Ollama (ollama, lexi, qwen, r1-14b)
"""

import asyncio
import json
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.chat_providers import get_provider, list_providers
from src.llm_web_client import WebLLMClient, LLMResponse
from src.web_agent import WebAgent, AgentConfig
from src.tui.components.modals.model_picker import MODELS as TUI_MODELS
from src.cli.v3_tui import AVAILABLE_MODELS as CLI_MODELS


ALL_MODELS = ["deepseek", "chatgpt", "gemini", "grok", "kimi", "perplexity", "ollama"]


class TestModelRegistryAndSelectors:
    """Verify all models are registered and declare required selectors and API properties."""

    @pytest.mark.parametrize("model_key", ALL_MODELS)
    def test_model_registered_and_configured(self, model_key: str):
        provider = get_provider(model_key)
        assert provider is not None
        assert provider.name, f"{model_key} must have a non-empty name"
        assert provider.url, f"{model_key} must have a non-empty url"
        assert provider.input_selector, f"{model_key} must define input_selector"
        assert provider.send_button_selector, f"{model_key} must define send_button_selector"
        assert provider.response_selector, f"{model_key} must define response_selector"
        assert provider.streaming_indicator_selector, f"{model_key} must define streaming_indicator_selector"

    def test_all_models_in_picker_and_cli(self):
        tui_keys = {m[0] for m in TUI_MODELS}
        cli_keys = set(CLI_MODELS.keys())
        for model in ALL_MODELS:
            assert model in tui_keys, f"Model {model} must be present in TUI MODELS"
            assert model in cli_keys, f"Model {model} must be present in CLI AVAILABLE_MODELS"


class TestModelWiringAPI:
    """Verify all models correctly wire to official API mode when keys are present."""

    @pytest.mark.asyncio
    async def test_deepseek_api_wiring_and_output(self):
        client = WebLLMClient()
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-deepseek-mock"}):
            await client.initialize(provider_name="deepseek")
            assert client.is_initialized is True
            assert client.is_logged_in is True
            assert client._use_api is True
            assert client.provider_key == "deepseek"
            assert "deepseek" in client.provider_name.lower()

            mock_response = LLMResponse(
                raw_text='<think>Solving task</think>\n```json\n{"action": "done", "thought": "Completed", "args": {"summary": "Done"}}\n```',
                parsed_json={"action": "done", "thought": "Completed", "args": {"summary": "Done"}},
                provider=client.provider_name,
            )
            with patch.object(client, "_call_cloud_api", new=AsyncMock(return_value=mock_response)):
                resp = await client.send_message("Run test")
                assert resp.parsed_json["action"] == "done"
                assert resp.parsed_json["args"]["summary"] == "Done"

    @pytest.mark.asyncio
    async def test_chatgpt_api_wiring_and_output(self):
        client = WebLLMClient()
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-openai-mock"}):
            await client.initialize(provider_name="chatgpt")
            assert client.is_initialized is True
            assert client.is_logged_in is True
            assert client._use_api is True
            assert client.provider_key == "chatgpt"
            assert "chatgpt" in client.provider_name.lower() or "cloud" in client.provider_name.lower()

            mock_response = LLMResponse(
                raw_text='```json\n{"action": "run_bash", "thought": "Listing files", "args": {"command": "ls"}}\n```',
                parsed_json={"action": "run_bash", "thought": "Listing files", "args": {"command": "ls"}},
                provider=client.provider_name,
            )
            with patch.object(client, "_call_cloud_api", new=AsyncMock(return_value=mock_response)):
                resp = await client.send_message("List directory")
                assert resp.parsed_json["action"] == "run_bash"
                assert resp.parsed_json["args"]["command"] == "ls"

    @pytest.mark.asyncio
    async def test_gemini_api_wiring_and_output(self):
        client = WebLLMClient()
        with patch.dict(os.environ, {"GEMINI_API_KEY": "mock-gemini-key"}):
            await client.initialize(provider_name="gemini")
            assert client.is_initialized is True
            assert client.is_logged_in is True
            assert client._use_api is True
            assert client.provider_key == "gemini"
            assert "gemini" in client.provider_name.lower()

            mock_response = LLMResponse(
                raw_text='```json\n{"action": "read_file", "thought": "Reading doc", "args": {"path": "README.md"}}\n```',
                parsed_json={"action": "read_file", "thought": "Reading doc", "args": {"path": "README.md"}},
                provider=client.provider_name,
            )
            with patch.object(client, "_call_cloud_api", new=AsyncMock(return_value=mock_response)):
                resp = await client.send_message("Read README")
                assert resp.parsed_json["action"] == "read_file"
                assert resp.parsed_json["args"]["path"] == "README.md"

    @pytest.mark.asyncio
    async def test_grok_api_wiring_and_output(self):
        client = WebLLMClient()
        with patch.dict(os.environ, {"GROK_API_KEY": "mock-xai-key"}):
            await client.initialize(provider_name="grok")
            assert client.is_initialized is True
            assert client.is_logged_in is True
            assert client._use_api is True
            assert client.provider_key == "grok"
            assert "grok" in client.provider_name.lower()

            mock_response = LLMResponse(
                raw_text='```json\n{"action": "done", "thought": "Done", "args": {"summary": "Grok completed task"}}\n```',
                parsed_json={"action": "done", "thought": "Done", "args": {"summary": "Grok completed task"}},
                provider=client.provider_name,
            )
            with patch.object(client, "_call_cloud_api", new=AsyncMock(return_value=mock_response)):
                resp = await client.send_message("Check status")
                assert resp.parsed_json["action"] == "done"
                assert resp.parsed_json["args"]["summary"] == "Grok completed task"

    @pytest.mark.asyncio
    async def test_kimi_api_wiring_and_output(self):
        client = WebLLMClient()
        with patch.dict(os.environ, {"MOONSHOT_API_KEY": "mock-kimi-key"}):
            await client.initialize(provider_name="kimi")
            assert client.is_initialized is True
            assert client.is_logged_in is True
            assert client._use_api is True
            assert client.provider_key == "kimi"
            assert "kimi" in client.provider_name.lower()

            mock_response = LLMResponse(
                raw_text='```json\n{"action": "done", "thought": "Kimi answered", "args": {"summary": "Math calculation 42"}}\n```',
                parsed_json={"action": "done", "thought": "Kimi answered", "args": {"summary": "Math calculation 42"}},
                provider=client.provider_name,
            )
            with patch.object(client, "_call_cloud_api", new=AsyncMock(return_value=mock_response)):
                resp = await client.send_message("Solve equation")
                assert resp.parsed_json["action"] == "done"
                assert resp.parsed_json["args"]["summary"] == "Math calculation 42"

    @pytest.mark.asyncio
    async def test_perplexity_api_wiring_and_output(self):
        client = WebLLMClient()
        with patch.dict(os.environ, {"PERPLEXITY_API_KEY": "mock-sonar-key"}):
            await client.initialize(provider_name="perplexity")
            assert client.is_initialized is True
            assert client.is_logged_in is True
            assert client._use_api is True
            assert client.provider_key == "perplexity"
            assert "perplexity" in client.provider_name.lower()

            mock_response = LLMResponse(
                raw_text='```json\n{"action": "done", "thought": "Research complete", "args": {"summary": "Grounded search result"}}\n```',
                parsed_json={"action": "done", "thought": "Research complete", "args": {"summary": "Grounded search result"}},
                provider=client.provider_name,
            )
            with patch.object(client, "_call_cloud_api", new=AsyncMock(return_value=mock_response)):
                resp = await client.send_message("Search facts")
                assert resp.parsed_json["action"] == "done"
                assert "Grounded search result" in resp.parsed_json["args"]["summary"]

    @pytest.mark.asyncio
    async def test_ollama_wiring_and_output(self):
        client = WebLLMClient()
        with patch.object(client, "_check_ollama_health", new=AsyncMock(return_value=True)):
            await client.initialize(provider_name="ollama")
            assert client.is_initialized is True
            assert client.is_logged_in is True
            assert client._use_api is True
            assert client.provider_key == "ollama"
            assert "ollama" in client.provider_name.lower()

            mock_response = LLMResponse(
                raw_text='<think>Reasoning locally</think>\n```json\n{"action": "done", "thought": "Local Ollama executed", "args": {"summary": "Offline success"}}\n```',
                parsed_json={"action": "done", "thought": "Local Ollama executed", "args": {"summary": "Offline success"}},
                provider=client.provider_name,
            )
            with patch.object(client, "_call_ollama_api", new=AsyncMock(return_value=mock_response)):
                resp = await client.send_message("Local inference")
                assert resp.parsed_json["action"] == "done"
                assert resp.parsed_json["args"]["summary"] == "Offline success"


class TestModelWiringDefaultNvidiaFallback:
    """Verify all cloud models fall back cleanly to direct NVIDIA NIM API when API keys are absent."""

    @pytest.mark.parametrize("model_key", ["deepseek", "chatgpt", "gemini", "grok", "kimi", "perplexity"])
    @pytest.mark.asyncio
    async def test_cloud_models_direct_api_wiring(self, model_key: str):
        client = WebLLMClient()
        # Clean any API keys from environment
        env_cleared = {
            "DEEPSEEK_API_KEY": "",
            "OPENAI_API_KEY": "",
            "CHATGPT_API_KEY": "",
            "GEMINI_API_KEY": "",
            "GROK_API_KEY": "",
            "XAI_API_KEY": "",
            "KIMI_API_KEY": "",
            "MOONSHOT_API_KEY": "",
            "PERPLEXITY_API_KEY": "",
        }
        with patch.dict(os.environ, env_cleared):
            await client.initialize(provider_name=model_key)
            assert client.is_initialized is True
            assert client._use_api is True
            assert client.provider_key == "nvidia"
            assert client._browser is None


class TestModelSwitchingParity:
    """Verify switching across all models cleanly re-initializes client in WebAgent."""

    @pytest.mark.asyncio
    async def test_seamless_model_switching_chain(self):
        agent = WebAgent(AgentConfig(provider="ollama"))
        agent.client = WebLLMClient()
        agent.client._initialized = True
        agent.client._use_api = True
        agent.client._provider_key = "ollama"
        agent.client._ollama_model = "hushus_ai/deepseek-r1-uncalibrated-14b"

        # Sequential model switch chain: ollama -> deepseek -> chatgpt -> gemini -> grok -> kimi -> perplexity -> ollama
        switch_chain = ["deepseek", "chatgpt", "gemini", "grok", "kimi", "perplexity", "ollama"]

        for target_model in switch_chain:
            agent.config.provider = target_model
            with patch.object(agent.client, "close", new=AsyncMock()) as mock_close:
                with patch.object(agent.client, "initialize", new=AsyncMock()) as mock_init:
                    await agent._initialize_llm()
                    # Previous session must be closed
                    mock_close.assert_called_once()
                    # New target session must be initialized
                    mock_init.assert_called_once()
                    assert mock_init.call_args[1]["provider_name"] == target_model

            # Simulate client being set to the new model
            agent.client._initialized = True
            agent.client._provider_key = target_model
            agent.client._use_api = (target_model == "ollama")


class TestActionParsingAndOutputCleanliness:
    """Verify WebAgent._parse_action handles outputs from each model cleanly."""

    @pytest.mark.parametrize("model_key", ALL_MODELS)
    def test_parse_action_with_thinking_tags(self, model_key: str):
        raw = (
            f"<think>Model {model_key} is analyzing the request carefully...</think>\n"
            f"<thought>Second reasoning block</thought>\n"
            '```json\n'
            '{\n'
            f'  "thought": "<think>inner thought</think>Working with {model_key}",\n'
            '  "action": "run_bash",\n'
            '  "args": {"command": "echo hello"}\n'
            '}\n'
            '```\n'
            'Some trailing explanation text.'
        )
        mock_resp = MagicMock(raw_text=raw, parsed_json=None)
        action = WebAgent._parse_action(mock_resp)

        assert action is not None
        assert action["action"] == "run_bash"
        assert action["args"]["command"] == "echo hello"
        assert "<think>" not in action["thought"]
        assert f"Working with {model_key}" in action["thought"]

    @pytest.mark.parametrize("model_key", ALL_MODELS)
    def test_conversational_fallback_produces_done(self, model_key: str):
        raw = f"Hello! I am {model_key}. The capital of France is Paris."
        mock_resp = MagicMock(raw_text=raw, parsed_json=None)
        action = WebAgent._parse_action(mock_resp)

        assert action is not None
        assert action["action"] in ("done", "converse")
        msg = action["args"].get("summary") or action["args"].get("message")
        assert msg == raw

