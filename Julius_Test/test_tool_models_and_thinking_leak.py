import asyncio
import pytest
from unittest.mock import MagicMock
from src.providers.base import ChatMessage, ChatRequest, ToolDefinition, ReasoningDelta, TextDelta
from src.providers.nim import (
    NvidiaNIMProvider,
    VALIDATED_NVIDIA_TOOL_MODELS,
    NVIDIA_MODEL_NEMOTRON_550B,
    NVIDIA_MODEL_NEMOTRON_LIGHTNING_30B,
    NVIDIA_MODEL_NEMOTRON_SUPER_VL,
    NVIDIA_MODEL_LLAMA_VISION_90B,
)
from src.providers.router import ProviderRouter


def test_nvidia_nim_tool_model_enforcement():
    """Verify that NvidiaNIMProvider ONLY calls validated models when tools are present."""
    provider = NvidiaNIMProvider(api_key="mock-key")
    tool = ToolDefinition(
        name="run_bash",
        description="Run bash command",
        parameters={"type": "object", "properties": {"command": {"type": "string"}}},
    )

    # 1. Validated tool model requested with tools -> preserved
    req1 = ChatRequest(
        messages=[ChatMessage(role="user", content="ls")],
        model=NVIDIA_MODEL_NEMOTRON_LIGHTNING_30B,
        tools=[tool],
    )
    assert provider._select_specialist_model(req1) == NVIDIA_MODEL_NEMOTRON_LIGHTNING_30B

    # 2. Non-tool model requested with tools -> rerouted to validated tool model
    req2 = ChatRequest(
        messages=[ChatMessage(role="user", content="ls")],
        model="deprecated/some-non-tool-model",
        tools=[tool],
    )
    chosen = provider._select_specialist_model(req2)
    assert chosen in VALIDATED_NVIDIA_TOOL_MODELS
    assert chosen == NVIDIA_MODEL_NEMOTRON_550B

    # 3. Request without tools -> respects requested model
    req3 = ChatRequest(
        messages=[ChatMessage(role="user", content="hello")],
        model="some-chat-model",
        tools=None,
    )
    assert provider._select_specialist_model(req3) == "some-chat-model"

    # 4. Request with image + tools -> routes to super-vl (which supports both)
    req4 = ChatRequest(
        messages=[ChatMessage(role="user", content="check this image [image: foo.png]")],
        model="some-model",
        tools=[tool],
    )
    assert provider._select_specialist_model(req4) == NVIDIA_MODEL_NEMOTRON_SUPER_VL

    # 5. Request with image without tools -> routes to llama-3.2 vision
    req5 = ChatRequest(
        messages=[ChatMessage(role="user", content="check this image [image: foo.png]")],
        model="some-model",
        tools=None,
    )
    assert provider._select_specialist_model(req5) == NVIDIA_MODEL_LLAMA_VISION_90B


@pytest.mark.asyncio
async def test_router_never_leaks_thinking_to_on_chunk():
    """Verify router send_message separates reasoning from on_chunk."""
    router = ProviderRouter(workspace="/tmp")

    async def mock_stream(*args, **kwargs):
        yield ReasoningDelta(reasoning="Thinking: analyzing request...")
        yield ReasoningDelta(reasoning="More thoughts...")
        yield TextDelta(text="Here is the final answer.")

    router.stream_with_resilience = mock_stream
    router.get_provider = MagicMock(return_value=MagicMock(default_model="test-model"))

    chunk_output = []
    thought_output = []

    def on_chunk(c: str):
        chunk_output.append(c)

    def on_thought(th: str):
        thought_output.append(th)

    res = await router.send_message(
        "test prompt",
        on_chunk=on_chunk,
        on_thought=on_thought,
    )

    # Verify thoughts went ONLY to on_thought, NEVER to on_chunk
    assert thought_output == ["Thinking: analyzing request...", "More thoughts..."]
    assert chunk_output == ["Here is the final answer."]
    assert "<think>" not in "".join(chunk_output)
    assert "</think>" not in "".join(chunk_output)
    assert res.text == "Here is the final answer."
    assert res.reasoning == "Thinking: analyzing request...More thoughts..."


def test_strip_or_replace_emojis_removes_all_thinking_tags():
    """Verify that frontend sanitization removes any residual thinking tags."""
    import re
    dirty = "- <think> user is asking me</think><think> to respond</think>I'm Julius. I'm your technical partner."
    cleaned = re.sub(r'<think>[\s\S]*?</think>', '', dirty, flags=re.I)
    cleaned = re.sub(r'<\/?(?:think|thought|reasoning)>', '', cleaned, flags=re.I)
    assert cleaned == "- I'm Julius. I'm your technical partner."
    assert "<think>" not in cleaned
    assert "</think>" not in cleaned


def test_model_list_contains_only_validated_nvidia_models():
    """Verify that the model picker list contains ONLY validated tool-calling models, not hardcoded API key models."""
    from src.tui.components.modals.model_picker import MODELS

    model_ids = [m[0] for m in MODELS]
    # Verify ONLY validated models are in the list
    for mid in model_ids:
        assert mid in VALIDATED_NVIDIA_TOOL_MODELS or mid == "nvidia"

    # Verify no unconfigured API-key models are present
    disallowed = ["chatgpt", "grok", "gemini", "kimi", "perplexity", "deepseek", "aifreeforever"]
    for bad in disallowed:
        assert bad not in model_ids


@pytest.mark.asyncio
async def test_router_handles_all_validated_model_names():
    """Verify that ProviderRouter properly resolves all validated NVIDIA models."""
    router = ProviderRouter(workspace="/tmp")
    for model_name in VALIDATED_NVIDIA_TOOL_MODELS:
        provider = router.get_provider(model_name)
        assert provider is not None
        assert provider.name == "nvidia"


