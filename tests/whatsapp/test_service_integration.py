"""Integration-level checks for the Julius WhatsApp service pipeline."""

from __future__ import annotations

import hashlib

import pytest

from src.integrations.whatsapp.config import WhatsAppConfig
from src.integrations.whatsapp.models import ChatConfig, ChatMode, WhatsAppMessage
from src.integrations.whatsapp.service import WhatsAppService


def make_message(*, text: str = "Hello", raw_reference: str = "wa-msg-1") -> WhatsAppMessage:
    return WhatsAppMessage(
        id=raw_reference,
        raw_reference=raw_reference,
        chat_id=hashlib.sha256(b"alice").hexdigest()[:16],
        chat_name="Alice",
        sender_id="alice",
        sender_name="Alice",
        timestamp=1.0,
        text=text,
    )


@pytest.mark.asyncio
async def test_incoming_approval_is_sent_only_after_success_and_marked_replied(tmp_path):
    service = WhatsAppService(
        config=WhatsAppConfig(profile_dir=str(tmp_path / "wa-profile")),
        db_path=str(tmp_path / "wa.db"),
    )
    service.save_chat_config(ChatConfig(chat_name="Alice", mode=ChatMode.APPROVAL))

    async def generate(_: str) -> str:
        return "Hi Alice"

    sent = []

    async def send(**kwargs):
        sent.append(kwargs)
        return True

    service.set_reply_generator(generate)
    service._sender.send_message = send
    incoming = make_message()
    await service._on_incoming_message(incoming)

    approval = service.get_approvals()[0]
    assert await service.approve(approval["id"], "Hi Alice!") is True
    assert sent[0]["chat_name"] == "Alice"
    assert service.storage.is_message_replied(incoming.dedup_key)


@pytest.mark.asyncio
async def test_auto_reply_and_outbound_echo_use_the_same_canonical_chat_id(tmp_path):
    service = WhatsAppService(
        config=WhatsAppConfig(profile_dir=str(tmp_path / "wa-profile")),
        db_path=str(tmp_path / "wa.db"),
    )
    service.save_chat_config(ChatConfig(chat_name="Alice", mode=ChatMode.AUTO))

    async def generate(_: str) -> str:
        return "Automatic reply"

    async def send(**kwargs):
        return True

    service.set_reply_generator(generate)
    service._sender.send_message = send
    incoming = make_message()
    await service._on_incoming_message(incoming)
    assert service.storage.is_message_replied(incoming.dedup_key)

    # A durable DOM message id distinguishes identical text sent twice.
    assert make_message(raw_reference="wa-msg-1").dedup_key != make_message(
        raw_reference="wa-msg-2"
    ).dedup_key
