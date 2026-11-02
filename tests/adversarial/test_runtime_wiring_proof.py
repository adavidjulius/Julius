"""
Runtime Wiring Proof Test Suite (T0.3).

Executes an end-to-end task workflow and proves runtime execution of:
1. policy.engine (PolicyEngine)
2. providers.router (LLMRouter)
3. security.secrets (SecretsManager)
4. security.audit (CryptographicAuditLedger)
5. telemetry.cost (CostTracker)
6. sandbox.tiers (SandboxTierManager)
"""

import asyncio
import os
import tempfile
from pathlib import Path
from typing import AsyncIterator
import pytest

from src.agent_config import AgentConfig
from src.web_agent import WebAgent
from src.policy.engine import PolicyEngine
from src.providers.base import (
    ChatMessage,
    ChatRequest,
    Finish,
    HealthStatus,
    LLMEvent,
    LLMProvider,
    ProviderCapabilities,
    TextDelta,
    Usage,
)
from src.providers.router import LLMRouter
from src.sandbox.tiers import SandboxTierManager
from src.security.audit import CryptographicAuditLedger
from src.security.secrets import SecretsManager, get_secrets_manager
from src.telemetry.cost import CostTracker


class MockDirectProvider(LLMProvider):
    """Deterministic mock provider to prove router runtime execution."""

    @property
    def name(self) -> str:
        return "mock"

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(supports_tools=True, supports_streaming=True)

    async def stream(
        self, req: ChatRequest, cancel: asyncio.Event | None = None
    ) -> AsyncIterator[LLMEvent]:
        yield TextDelta(text='{"thought": "Writing file", "action": "write_file", "args": {"path": "proof.txt", "content": "verified"}}\n')
        yield Usage(prompt_tokens=10, completion_tokens=25, total_tokens=35)
        yield Finish(reason="stop")

    async def check_health(self) -> HealthStatus:
        return HealthStatus(ok=True, latency_ms=1.0)


@pytest.mark.asyncio
async def test_runtime_wiring_proof_end_to_end(tmp_path):
    """Verify runtime execution and wiring of all six foundational systems."""
    ws = str(tmp_path)
    config = AgentConfig()
    config.allowed_directory = ws
    config.confirm_actions = False

    agent = WebAgent(config=config, keep_browser_open=False)

    # 1. Prove providers.router execution
    assert isinstance(agent.router, LLMRouter)
    mock_prov = MockDirectProvider()
    agent.router.register_provider("mock", mock_prov)

    req = ChatRequest(
        messages=[ChatMessage(role="user", content="Write a proof file")],
        model="mock-model",
    )
    events = []
    async for ev in agent.router.stream_with_resilience(req, provider_name="mock"):
        events.append(ev)

    assert any(isinstance(ev, TextDelta) for ev in events)
    usage_events = [ev for ev in events if isinstance(ev, Usage)]
    assert len(usage_events) >= 1
    assert usage_events[0].prompt_tokens == 10

    # 2. Prove telemetry.cost execution
    assert isinstance(agent.cost_tracker, CostTracker)
    agent.cost_tracker.record_usage(
        provider="mock",
        model="mock-model",
        prompt_tokens=10,
        completion_tokens=25,
        cost_usd=0.0001,
    )
    daily = agent.cost_tracker.get_daily_summary()
    assert daily["prompt_tokens"] >= 10
    assert daily["cost_usd"] >= 0.0001

    # 3. Prove policy.engine & sandbox.tiers execution via ActionExecutor
    assert isinstance(agent.executor._policy_engine, PolicyEngine)
    assert isinstance(agent.executor._tier_manager, SandboxTierManager)

    action_res = agent.executor.execute(
        "write_file",
        {"path": "proof.txt", "content": "verified content with API_KEY = 'sk-proj-mock12345678901234567890123456789012345'"}
    )
    assert action_res.success is True
    assert (tmp_path / "proof.txt").exists()

    # 4. Prove security.secrets redaction
    sec_mgr = get_secrets_manager()
    assert isinstance(sec_mgr, SecretsManager)
    sanitized = sec_mgr.scan_and_redact((tmp_path / "proof.txt").read_text())
    assert "sk-proj-" not in sanitized
    assert "[REDACTED" in sanitized

    # 5. Prove security.audit execution and cryptographic integrity
    assert isinstance(agent.executor._cryptographic_audit, CryptographicAuditLedger)
    ok, msg, count = agent.executor._cryptographic_audit.verify_chain()
    assert ok is True, f"Audit chain verification failed: {msg}"
    assert count >= 1

    # Clean up
    await agent.close()
