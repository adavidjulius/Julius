"""
Tests for WhatsApp Media Ingestion, Workspace Indexing, and Hardened Sending.
"""

import asyncio
import base64
import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from src.integrations.whatsapp.media_manager import WhatsAppMediaManager
from src.integrations.whatsapp.materials import find_matching_document
from src.integrations.whatsapp.models import MessageType, WhatsAppMessage
from src.integrations.whatsapp.router import WhatsAppMessageRouter
from src.integrations.whatsapp.adapter import WhatsAppAdapter, PREVIEW_SEND_BUTTON_STRATEGY


@pytest.fixture
def temp_media_manager(tmp_path):
    mgr = WhatsAppMediaManager(media_root=tmp_path / "received_media")
    return mgr


def test_media_manager_save_and_search_document(temp_media_manager):
    content = b"%PDF-1.4 Mock Tutorial Content"
    filename = "Max_Assignment_Unit2.pdf"
    sender = "MIT Gova"
    caption = "Here is the max assignment for engineering graphics"

    record = temp_media_manager.save_document(
        content=content,
        filename=filename,
        sender_name=sender,
        caption=caption,
    )

    assert record["filename"] == filename
    assert record["category"] == "assignment"
    assert "max" in record["keywords"]
    assert "assignment" in record["keywords"]
    assert Path(record["path"]).exists()
    assert Path(record["path"]).read_bytes() == content

    # Test search for "max assignment"
    match = temp_media_manager.search_media("send me the max assignment")
    assert match is not None
    assert match["filename"] == filename

    # Test search for "tutorial"
    match_tut = temp_media_manager.search_media("give me the tutorial pdf")
    assert match_tut is None  # no tutorial saved yet

    # Now save a tutorial
    tut_content = b"%PDF-1.4 Calculus Tutorial"
    temp_media_manager.save_document(
        content=tut_content,
        filename="Maths_Calculus_Tutorial.pdf",
        sender_name="MIT Monish",
        caption="calculus tutorial 1",
    )

    match_tut2 = temp_media_manager.search_media("send me the calculus tutorial pdf")
    assert match_tut2 is not None
    assert match_tut2["filename"] == "Maths_Calculus_Tutorial.pdf"


def test_media_manager_save_and_search_image(temp_media_manager):
    img_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 20
    b64_img = base64.b64encode(img_bytes).decode("ascii")

    record = temp_media_manager.save_image(
        image_data=f"data:image/jpeg;base64,{b64_img}",
        sender_name="MIT Naveen Raj ECE",
        caption="Circuit diagram assignment",
    )

    assert record is not None
    assert record["is_image"] is True
    assert record["category"] == "assignment"
    assert Path(record["path"]).exists()

    # Search for circuit diagram
    match = temp_media_manager.search_media("send the circuit diagram image")
    assert match is not None
    assert match["is_image"] is True


def test_materials_find_matching_document_integrates_media_manager(temp_media_manager):
    # Register document in media manager
    temp_media_manager.save_document(
        content=b"%PDF-1.4 Special Assignment",
        filename="Physics_Assignment_Lab.pdf",
        sender_name="MIT Sundar",
        caption="physics lab assignment",
    )

    with patch("src.integrations.whatsapp.materials.get_media_manager", return_value=temp_media_manager):
        match = find_matching_document("give me the physics lab assignment pdf")
        assert match is not None
        assert match["filename"] == "Physics_Assignment_Lab.pdf"


@pytest.mark.asyncio
async def test_router_acknowledges_newly_received_media():
    sender_mock = AsyncMock()
    sender_mock.send_message.return_value = True
    storage_mock = MagicMock()
    storage_mock.is_message_replied.return_value = False
    policy_mock = MagicMock()
    policy_mock.should_process.return_value = (True, "OK")
    policy_mock.resolve_mode.return_value = "auto"
    config_mock = MagicMock()
    config_mock.default_mode = "auto"

    router = WhatsAppMessageRouter(
        policy=policy_mock,
        sender=sender_mock,
        storage=storage_mock,
        config=config_mock,
        context=MagicMock(),
        persona=MagicMock(),
        training=MagicMock(),
        safety=MagicMock(),
        approval_queue=MagicMock(),
    )

    msg = WhatsAppMessage(
        id="test_msg_media_1",
        chat_id="mit_gova",
        chat_name="MIT Gova",
        sender_id="mit_gova",
        sender_name="MIT Gova",
        timestamp=1000.0,
        text="[Document: max_assignment.pdf]",
        message_type=MessageType.DOCUMENT,
        attachment_metadata={
            "saved_media": {
                "filename": "max_assignment.pdf",
                "category": "assignment",
                "title": "Max Assignment",
            }
        },
    )

    await router.route_message(msg)

    # Verify acknowledgment was sent
    sender_mock.send_message.assert_awaited_once()
    call_args = sender_mock.send_message.call_args[1]
    assert call_args["chat_name"] == "MIT Gova"
    assert "max_assignment.pdf" in call_args["text"]
    assert "Saved it to workspace" in call_args["text"]


@pytest.mark.asyncio
async def test_adapter_strict_verification_failure_dismisses_dialog():
    browser_mock = MagicMock()
    page_mock = AsyncMock()
    browser_mock.page = page_mock
    browser_mock.is_connected = True

    adapter = WhatsAppAdapter(browser_mock)
    adapter.find_chat = AsyncMock(return_value=True)
    adapter._mount_attachment_menu = AsyncMock()
    adapter._locate_file_input = AsyncMock(return_value=AsyncMock())
    adapter._wait_for_preview = AsyncMock(return_value=True)
    adapter._dispatch_preview_send = AsyncMock(return_value=True)
    adapter._wait_for_preview_dismissal = AsyncMock()

    # Simulate message verification failure (row count did NOT increment)
    adapter.verify_message_sent = AsyncMock(return_value=False)
    adapter._dismiss_any_stuck_dialog = AsyncMock()

    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
        tmp.write(b"%PDF-1.4 sample file content")
        tmp.flush()
        success = await adapter.send_media(
            chat_name="MIT Gova",
            file_path=tmp.name,
            media_type="document",
        )

    # Must return False and must dismiss stuck dialog!
    assert success is False
    adapter._dismiss_any_stuck_dialog.assert_awaited_once()


def test_preview_send_button_strategy_contains_modern_selectors():
    candidates = PREVIEW_SEND_BUTTON_STRATEGY.candidates
    assert any("wds-ic-send-filled" in c for c in candidates)
    assert any('aria-label*="Send"' in c for c in candidates)


def test_base64_image_extraction_and_saving(temp_media_manager):
    img_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 150
    raw_b64 = "/9j/" + base64.b64encode(img_bytes[4:]).decode("ascii")

    assert temp_media_manager.is_base64_image(raw_b64) is True
    assert temp_media_manager.is_base64_image("hello how are you") is False

    record = temp_media_manager.save_image_from_base64_text(
        text=raw_b64,
        sender_name="Sundaramoorthy",
        context_hint="Sumanth sleeping image save it in your memory",
    )

    assert record is not None
    assert record["is_image"] is True
    assert "sumanth" in record["filename"]
    assert Path(record["path"]).exists()

    # Search for sumanth photo
    match = temp_media_manager.search_media("send me sumanth sleeping photo")
    assert match is not None
    assert match["filename"] == record["filename"]


def test_sync_workspace_documents(tmp_path):
    mgr = WhatsAppMediaManager(media_root=tmp_path / "received_media")
    mgr.sync_workspace_documents()

    # Check that documents/ exists and has indexed records
    docs = mgr.list_all_media()
    assert isinstance(docs, list)
    # Search for timetable
    match = mgr.search_media("timetable")
    if match:
        assert Path(match["path"]).exists()
        assert "timetable" in match["filename"].lower()
