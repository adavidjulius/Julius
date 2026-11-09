import pytest
from src.web_agent import WebAgent, StepRecord
from src.agent_config import AgentConfig


def test_followup_query_detection():
    agent = WebAgent(AgentConfig())
    # Empty history -> not a follow-up
    assert not agent._is_followup_query("with those details what can you do to that")

    # Populate session history
    agent.session_history.append({
        "user_prompt": "check in our wifi who are all connected the ip",
        "assistant_response": "Connected Devices: 1. 192.168.0.1, 2. 192.168.0.104, 3. 192.168.0.224",
        "tools_summary": "run_bash (arp -a): 5 devices detected",
        "stop_reason": "converse",
    })

    # Test anaphoric follow-ups
    assert agent._is_followup_query("with those details what can you do to that")
    assert agent._is_followup_query("what can we do with that")
    assert agent._is_followup_query("what can you do with those")
    assert agent._is_followup_query("explain those")
    assert agent._is_followup_query("what about that")
    assert agent._is_followup_query("what does that mean")
    assert agent._is_followup_query("tell me more about those")

    # Device & Hardware Follow-ups and Typo Handling
    assert agent._is_followup_query("when did tis model launched?")
    assert agent._is_followup_query("when was this model released?")
    assert agent._is_followup_query("i asking my device lauched not you bro")
    assert agent._is_followup_query("how much is my device capable like explian with a real world things")
    assert agent._is_followup_query("analyse my device and check when it is lauched in market")

    # Non-followup tasks that explicitly mention files or actions
    assert not agent._is_followup_query("read the file src/main.py")
    assert not agent._is_followup_query("run git status")
    assert not agent._is_followup_query("delete all screenshot in my desktop")


def test_default_provider_is_nvidia():
    from src.agent_config import get_default_provider
    from src.providers.router import ProviderRouter
    
    assert get_default_provider() == "nvidia"
    router = ProviderRouter(workspace="/Users/davidjulius/Julius")
    assert router.provider_name == "nvidia"


def test_session_context_formatting():
    agent = WebAgent(AgentConfig())
    agent.session_history.append({
        "user_prompt": "check in our wifi who are all connected the ip",
        "assistant_response": "Connected Devices: 192.168.0.1, 192.168.0.104",
        "tools_summary": "run_bash (arp -a): 5 devices detected",
        "stop_reason": "converse",
    })

    ctx = agent._format_session_context()
    assert "### PREVIOUS CONVERSATION IN THIS SESSION:" in ctx
    assert "check in our wifi who are all connected the ip" in ctx
    assert "192.168.0.1" in ctx
    assert "Actions Taken & Findings: run_bash (arp -a)" in ctx


@pytest.mark.asyncio
async def test_session_history_clear_on_new_chat():
    agent = WebAgent(AgentConfig())
    agent.session_history.append({
        "user_prompt": "test prompt",
        "assistant_response": "test response",
        "tools_summary": "",
        "stop_reason": "converse",
    })
    assert len(agent.session_history) == 1

    await agent.start_new_chat()
    assert len(agent.session_history) == 0

