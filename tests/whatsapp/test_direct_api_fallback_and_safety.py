"""
Tests for Direct API WebLLM fallback and auto-mode reply reliability.

Verifies:
1. Primary vision API failure seamlessly triggers direct WebLLMClient (NVIDIA NIM) fallback.
2. If direct WebLLMClient fails, Tony Stark fallback reply is returned.
3. In auto mode, trusted college friends discussing sensitive terms (passwords, secrets, ssh)
   are NOT blocked or sent to approval queue — replies are auto-sent.
4. Circuit breaker OPEN state falls back to Stark rather than dropping messages.
"""

import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.integrations.whatsapp.api import generate_whatsapp_reply
from src.integrations.whatsapp.config import WhatsAppConfig
from src.integrations.whatsapp.models import ChatConfig, ChatMode, WhatsAppMessage
from src.integrations.whatsapp.router import WhatsAppMessageRouter
from src.integrations.whatsapp.safety import SafetyGate


@pytest.mark.asyncio
async def test_api_calls_direct_web_llm_when_vision_fails():
    """Verify that when primary vision API throws an exception, direct WebLLMClient (NVIDIA NIM) is called."""
    mock_resp = MagicMock(text="Yes bro, physics lab is at 8:30am", raw_text="Yes bro, physics lab is at 8:30am", success=True)
    with patch("urllib.request.urlopen", side_effect=Exception("API Connection Refused")), \
         patch.dict("os.environ", {"NVIDIA_API_KEY": "dummy", "GROQ_API_KEY": "", "DEEPSEEK_API_KEY": ""}), \
         patch("src.llm_web_client.WebLLMClient.send_message", new_callable=AsyncMock, return_value=mock_resp) as mock_send:

        reply = await generate_whatsapp_reply("What time is physics lab?")
        assert "physics lab" in reply.lower()
        mock_send.assert_called_once()


@pytest.mark.asyncio
async def test_api_falls_back_to_stark_when_direct_api_fails():
    """Verify that when both primary vision API and direct WebLLMClient fail, Stark fallback is returned."""
    with patch("urllib.request.urlopen", side_effect=Exception("API Connection Refused")), \
         patch.dict("os.environ", {"NVIDIA_API_KEY": "dummy", "GROQ_API_KEY": "", "DEEPSEEK_API_KEY": ""}), \
         patch("src.llm_web_client.WebLLMClient.send_message", side_effect=Exception("Direct API failure")):

        reply = await generate_whatsapp_reply("Are you free tonight?")
        assert len(reply) > 0
        assert reply != "[NO_RESPONSE]"


@pytest.mark.asyncio
async def test_trusted_peer_sensitive_terms_do_not_escalate_to_approval_queue(tmp_path):
    """Trusted contacts (like MIT Naveen Raj ECE or MIT Gova) saying 'don't tell this' or 'password'
    must NOT be escalated to approval queue in auto mode."""
    from src.integrations.whatsapp.service import WhatsAppService
    service = WhatsAppService(
        config=WhatsAppConfig(profile_dir=str(tmp_path / "wa-profile"), require_approval_for_low_confidence=False),
        db_path=str(tmp_path / "wa.db"),
    )
    service.save_chat_config(ChatConfig(chat_name="MIT Naveen Raj ECE", mode=ChatMode.AUTO))

    async def generate(_: str, **kwargs) -> str:
        return "Don't worry bro, I won't tell anyone!"

    sent_messages = []
    async def send(chat_name="", text="", **kwargs):
        sent_messages.append({"chat_name": chat_name, "text": text})
        return True

    service.set_reply_generator(generate)
    service._sender.send_message = send

    msg = WhatsAppMessage(
        id="msg_secret_1",
        chat_id="chat_naveen",
        chat_name="MIT Naveen Raj ECE",
        sender_id="sender_naveen",
        sender_name="MIT Naveen Raj ECE",
        timestamp=time.time(),
        text="Don't tell this to anyone, okay?",
    )

    await service._on_incoming_message(msg)

    # Must NOT be in approval queue
    assert len(service._approval_queue.get_pending()) == 0
    # Must have sent the message
    assert len(sent_messages) == 1
    assert "won't tell" in sent_messages[0]["text"].lower()


@pytest.mark.asyncio
async def test_circuit_breaker_open_falls_back_and_replies(tmp_path):
    """When circuit breaker is open, auto mode must still reply using Stark fallback."""
    from src.integrations.whatsapp.service import WhatsAppService

    service = WhatsAppService(
        config=WhatsAppConfig(profile_dir=str(tmp_path / "wa-profile")),
        db_path=str(tmp_path / "wa.db"),
    )
    service.save_chat_config(ChatConfig(chat_name="MIT Putta Reddy Guru Rakesh Reddy", mode=ChatMode.AUTO))

    sent_messages = []
    async def send(chat_name="", text="", **kwargs):
        sent_messages.append({"chat_name": chat_name, "text": text})
        return True

    service._sender.send_message = send

    # Trip router circuit breaker
    cb = service._router._circuit_breaker
    for _ in range(10):
        cb.record_failure()
    assert not cb.can_execute()

    msg = WhatsAppMessage(
        id="msg_cb_1",
        chat_id="chat_reddy",
        chat_name="MIT Putta Reddy Guru Rakesh Reddy",
        sender_id="sender_reddy",
        sender_name="Reddy",
        timestamp=time.time(),
        text="What is the schedule today?",
    )

    await service._on_incoming_message(msg)

    # Must have sent a message via fallback
    assert len(sent_messages) == 1
    assert len(sent_messages[0]["text"]) > 0

