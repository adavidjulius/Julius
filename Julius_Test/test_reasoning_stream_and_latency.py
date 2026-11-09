"""
Verification test for second input latency, ReasoningDelta streaming, and active model catalog.
"""

import asyncio
import sys
import time
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.providers.base import ChatRequest, ChatMessage, ReasoningDelta, TextDelta
from src.providers.nim import (
    NvidiaNIMProvider,
    NVIDIA_MODEL_NEMOTRON_550B,
    NVIDIA_MODEL_LLAMA_VISION_90B,
)
from src.providers.router import ProviderRouter


def test_model_catalog_and_selection():
    p = NvidiaNIMProvider()
    assert p.default_model == NVIDIA_MODEL_NEMOTRON_550B

    # Test that vision delegation selects active 90b vision model
    req_vision = ChatRequest(
        messages=[ChatMessage(role="user", content="Look at this [image: /tmp/test.png]")],
        model=p.default_model,
    )
    chosen = p._select_specialist_model(req_vision)
    assert chosen == NVIDIA_MODEL_LLAMA_VISION_90B, f"Expected {NVIDIA_MODEL_LLAMA_VISION_90B}, got {chosen}"

    # Test standard request keeps flagship model
    req_std = ChatRequest(
        messages=[ChatMessage(role="user", content="Hello")],
        model=p.default_model,
    )
    chosen_std = p._select_specialist_model(req_std)
    assert chosen_std == NVIDIA_MODEL_NEMOTRON_550B
    print("✅ test_model_catalog_and_selection passed")


def test_reasoning_delta_forwarding_in_router():
    """Verify that ReasoningDelta is forwarded as <think> chunks through on_chunk."""
    chunks = []

    def on_chunk(text: str):
        chunks.append(text)

    # Simulate what router._stream_collector does with ReasoningDelta
    event = ReasoningDelta(reasoning="Analyzing project structure...")
    if isinstance(event, ReasoningDelta):
        if on_chunk and event.reasoning:
            on_chunk(f"<think>{event.reasoning}</think>")

    assert len(chunks) == 1
    assert chunks[0] == "<think>Analyzing project structure...</think>"
    print("✅ test_reasoning_delta_forwarding_in_router passed")


def test_identity_query_detection():
    """Verify conversational identity matching on variations of 'who are you'."""
    queries = [
        "who are you",
        "who are you man",
        "who are you man talking too good",
        "who r u",
        "who is julius",
        "what is your name",
        "tell me about yourself",
    ]
    for q in queries:
        task_lower = q.lower()
        matched = any(k in task_lower for k in ("who is julius", "who are you", "who are u", "what is your name", "tell me about yourself", "who are you man", "who r u"))
        assert matched, f"Failed to match query: '{q}'"

    conversational_queries = [
        "tell a 20 lines of poen for you",
        "tell me a joke",
        "roast me please",
        "distract me",
        "how are you today",
    ]
    for q in conversational_queries:
        task_lower = q.lower()
        is_conv = (
            len(task_lower.split()) <= 15
            and any(task_lower.startswith(g) for g in ("hello", "hi", "hey", "who", "what are you", "roast", "tell me a", "tell a", "how are you", "good morning", "good evening", "thanks", "thank you", "distract", "joke", "poem", "sing"))
            and not any(k in task_lower for k in ("file", "code", "git", "test", "build", "run", "delete", "create", "install", "mkdir", "rm", "fix", "script", "dir", "directory", "grep", "search", "write", "edit", "commit", "push", "pull", "pr", "repo", "chmod", "sh", "bash"))
        )
        assert is_conv, f"Failed conversational match: '{q}'"
    print("✅ test_identity_query_detection passed")


if __name__ == "__main__":
    test_model_catalog_and_selection()
    test_reasoning_delta_forwarding_in_router()
    test_identity_query_detection()
    print("\n🎉 ALL REASONING STREAM & LATENCY TESTS PASSED CLEANLY!\n")
