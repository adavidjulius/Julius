"""
Julius WhatsApp Integration — Perception Layer, Common Workspace, and REPLY Sanitization Tests.

Tests:
1. PerceptionLayer text extraction & autonomous naming (no asking user).
2. Common workspace video handling & cross-user sharing (Sumanth video -> Naveen asks).
3. Dynamic context manifest updates when new files are saved.
4. REPLY prefix and quoting removal across JSON and plain-text replies.
5. Rapid burst messages aggregation and autonomous perception.
"""

import os
import shutil
import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.integrations.whatsapp.context import get_media_manifest_prompt_section
from src.integrations.whatsapp.intent_engine import IntentEngine, MessageIntent
from src.integrations.whatsapp.media_manager import MediaManager, get_media_manager
from src.integrations.whatsapp.media_resolver import MediaResolver
from src.integrations.whatsapp.models import (
    ChatConfig,
    ChatMode,
    Confidence,
    MessageType,
    ReceiptStatus,
    ResolutionStatus,
    WhatsAppMessage,
)
from src.integrations.whatsapp.perception import PerceptionLayer, get_perception_layer
from src.integrations.whatsapp.router import (
    WhatsAppMessageRouter,
    parse_llm_action_response,
    sanitize_reply_text,
)
from src.integrations.whatsapp.storage import WhatsAppStorage


# ── 1. REPLY Sanitization Tests ───────────────────────────────────────────────

def test_sanitize_reply_text_removes_prefixes():
    """Verify that all forms of 'REPLY' prefix and quotes are stripped without harming real content."""
    cases = [
        ("REPLY: Here is the timetable bro", "Here is the timetable bro"),
        ("\"REPLY\" Here is the timetable", "Here is the timetable"),
        ("\"REPLY\": Here is the timetable", "Here is the timetable"),
        ("[REPLY] Here is the timetable", "Here is the timetable"),
        ("[REPLY]: Here is the timetable", "Here is the timetable"),
        ("REPLY - Here is the timetable", "Here is the timetable"),
        ("REPLY\nHere is the timetable", "Here is the timetable"),
        ("\"Here is the timetable\"", "Here is the timetable"),
        ("'Here is the timetable'", "Here is the timetable"),
        ("Reply #1", "Reply #1"),
        ("Reply to Sumanth's message", "Reply to Sumanth's message"),
    ]
    for inp, expected in cases:
        assert sanitize_reply_text(inp) == expected


def test_parse_llm_action_response_sanitizes_reply():
    """Verify parse_llm_action_response strips REPLY from JSON and raw text."""
    # JSON with REPLY: inside reply_text
    raw_json = '{"action": "REPLY", "reply_text": "REPLY: sure thing bro", "thought": "responding"}'
    parsed = parse_llm_action_response(raw_json)
    assert parsed["reply_text"] == "sure thing bro"

    # Raw text starting with REPLY:
    raw_text = "REPLY: wait a sec da"
    parsed_raw = parse_llm_action_response(raw_text)
    assert parsed_raw["reply_text"] == "wait a sec da"


# ── 2. Perception Layer Tests ─────────────────────────────────────────────────

def test_perception_layer_heuristic_document_naming():
    """PerceptionLayer autonomously names documents based on filename, text, and sender without user input."""
    layer = get_perception_layer()

    # Document sent with burst text
    res = layer.fallback_heuristic_identity(
        raw_filename="doc_83921.pdf",
        media_type="document",
        sender_name="Sumanth",
        caption="Here is the PH23C11 engineering physics module notes for unit 2",
        burst_messages=["Check this out", "physics notes for tomorrow exam"],
        extracted_text="Madras Institute of Technology PH23C11 Engineering Physics Unit II Laser and Fiber Optics",
    )

    assert "Physics" in res["title"]
    assert res["category"] == "notes"
    assert "PH23C11" in res["clean_filename"] or "physics" in res["clean_filename"].lower()
    assert any("physics" in ent.lower() for ent in res["entities"])


def test_perception_layer_heuristic_video_naming():
    """PerceptionLayer autonomously names videos without asking the user."""
    layer = get_perception_layer()

    res = layer.fallback_heuristic_identity(
        raw_filename="VID_20260929_WA0001.mp4",
        media_type="video",
        sender_name="Sumanth",
        caption="Sumanth sleeping during calculus class",
        burst_messages=["Look at sumanth bro haha", "sleeping video"],
    )

    assert "Sumanth" in res["title"]
    assert "Video" in res["title"]
    assert res["category"] == "video"
    assert "sumanth" in res["clean_filename"].lower()


@pytest.mark.asyncio
async def test_perception_layer_infer_file_identity_no_user_questions():
    """Verify infer_file_identity runs asynchronously and returns complete labels without asking user."""
    layer = PerceptionLayer()
    inferred = await layer.infer_file_identity(
        file_bytes=b"%PDF-1.4 test academic document",
        original_filename="schedule.pdf",
        mime_type="application/pdf",
        context_text="Schedule for First Assessment Test 2026",
        sender_name="MIT Gova",
        media_type="document",
    )

    assert inferred["title"]
    assert any(c in inferred["category"] for c in ("timetable", "document", "academic"))
    assert inferred["clean_filename"].endswith(".pdf")


# ── 3. Common Workspace & Cross-User Video Sharing ────────────────────────────

def test_common_workspace_video_saved_and_retrieved_by_different_user(tmp_path):
    """
    Core user requirement:
    'in the common workspace not like single workspace like if sumanth send a video
     if naveen ask that video also he needs to send that if now someone ask it it is saying
     there is nothing there it is saying make it and fix it make a clear path'
    """
    storage = WhatsAppStorage(db_path=str(tmp_path / "test_common.db"))
    media_mgr = MediaManager(media_root=tmp_path / "received_media")

    # Sumanth sends a video -> saved in common workspace
    video_bytes = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00isommp42" + b"A" * 200
    saved = media_mgr.save_video(
        content=video_bytes,
        filename="sumanth_sleeping_video.mp4",
        sender_name="Sumanth",
        caption="Sumanth sleeping in class",
        chat_id="chat_sumanth",
        title="Sumanth Sleeping Video",
        entities=["Sumanth"],
    )
    assert saved is not None
    assert Path(saved["path"]).exists()

    # Index in SQLite storage to simulate persistence
    storage.save_media_item({
        "media_id": saved["id"],
        "media_type": "video",
        "filename": saved["filename"],
        "storage_path": saved["path"],
        "sender": "Sumanth",
        "chat_id": "chat_sumanth",
        "caption": saved["caption"],
        "entities": ["Sumanth"],
        "verified": True,
        "status": "VERIFIED",
    })

    # Now Naveen asks for Sumanth's video in Naveen's chat!
    resolver = MediaResolver(storage)
    with patch("src.integrations.whatsapp.media_resolver.get_media_manager", return_value=media_mgr):
        # 1. Naveen asks "send sumanth video"
        res = resolver.resolve_video(
            person_query="Sumanth",
            general_query="send sumanth video",
            chat_name="Naveen Raj",
        )
        assert res.status == ResolutionStatus.EXACT_MATCH
        assert "sumanth" in res.item["filename"].lower()
        assert Path(res.item["storage_path"]).exists()

        # 2. Naveen asks "send the video" (general query referring to the workspace video)
        res_gen = resolver.resolve_video(
            person_query=None,
            general_query="send the video",
            chat_name="Naveen Raj",
        )
        assert res_gen.status == ResolutionStatus.EXACT_MATCH
        assert Path(res_gen.item["storage_path"]).exists()


# ── 4. IntentEngine Video Classification ──────────────────────────────────────

def test_intent_engine_classifies_send_video():
    """Verify IntentEngine recognizes video requests from different users."""
    queries = [
        ("send sumanth video", "Sumanth"),
        ("send naveen video", "Naveen"),
        ("send me the video", ""),
        ("share that video", ""),
        ("give sumanth's video", "Sumanth"),
        ("send gova video", "Gova"),
    ]
    for q, expected_person in queries:
        classified = IntentEngine.classify(q)
        assert classified["intent"] == MessageIntent.SEND_VIDEO
        if expected_person:
            assert classified["target"] == expected_person


# ── 5. Dynamic Context Manifest Updates ────────────────────────────────────────

def test_context_manifest_dynamically_updates_on_new_file(tmp_path):
    """
    Verify:
    'that contxt is not updating like if new file saved it have only the knowledge
     of the files that we only sotred not the updating files memeory that may help to send the new files'
    """
    media_root = tmp_path / "received_media"
    media_mgr = MediaManager(media_root=media_root)

    with patch("src.integrations.whatsapp.media_manager.get_media_manager", return_value=media_mgr), \
         patch("src.integrations.whatsapp.context.get_media_manager", return_value=media_mgr):

        # Initial prompt manifest has no custom videos or newly received documents
        init_manifest = get_media_manifest_prompt_section()
        assert "sumanth_lab_demo.mp4" not in init_manifest

        # Save a new video to common workspace
        media_mgr.save_video(
            content=b"test_video_bytes",
            filename="sumanth_lab_demo.mp4",
            sender_name="Sumanth",
            caption="Sumanth makerspace project demo",
            title="Sumanth Makerspace Demo",
            entities=["Sumanth"],
        )

        # Save a new document to common workspace
        media_mgr.save_document(
            content=b"%PDF-1.4 chemistry notes",
            filename="CY23C11_Chemistry_Notes.pdf",
            sender_name="MIT Gova",
            caption="Chemistry unit 1 notes",
            title="Chemistry Unit 1 Notes",
            category="notes",
        )

        # Call manifest generation again
        updated_manifest = get_media_manifest_prompt_section()

        # Both new files MUST be present immediately without restarting!
        assert "sumanth_lab_demo.mp4" in updated_manifest
        assert "CY23C11_Chemistry_Notes.pdf" in updated_manifest
        assert "3. Videos Folder: materials/received_media/videos/" in updated_manifest
        assert "ACTION 'SEND_VIDEO':" in updated_manifest


# ── 6. Router Full Flow for SEND_VIDEO ────────────────────────────────────────

@pytest.mark.asyncio
async def test_router_sends_video_cross_user(tmp_path):
    """Test full router execution for sending a video received from Sumanth to Naveen."""
    media_root = tmp_path / "received_media"
    media_mgr = MediaManager(media_root=media_root)
    storage = WhatsAppStorage(db_path=str(tmp_path / "test_router_vid.db"))

    # Sumanth's video in common workspace
    vid_rec = media_mgr.save_video(
        content=b"video_bytes_content_sample_123",
        filename="sumanth_sleeping.mp4",
        sender_name="Sumanth",
        title="Sumanth Sleeping Video",
        entities=["Sumanth"],
    )

    sender_mock = AsyncMock()
    sender_mock.send_media.return_value = True
    sender_mock.send_message.return_value = True

    policy_mock = MagicMock()
    policy_mock.should_process.return_value = (True, "OK")
    policy_mock.resolve_mode.return_value = "auto"
    config_mock = MagicMock()
    config_mock.default_mode = "auto"

    resolver = MediaResolver(storage)

    with patch("src.integrations.whatsapp.media_resolver.get_media_manager", return_value=media_mgr), \
         patch("src.integrations.whatsapp.media_manager.get_media_manager", return_value=media_mgr):

        router = WhatsAppMessageRouter(
            policy=policy_mock,
            sender=sender_mock,
            storage=storage,
            config=config_mock,
            context=MagicMock(),
            persona=MagicMock(),
            training=MagicMock(),
            safety=MagicMock(),
            approval_queue=MagicMock(),
            media_resolver=resolver,
        )

        # Naveen asks for Sumanth's video
        msg = WhatsAppMessage(
            id="test_naveen_ask_vid",
            chat_id="naveen_raj",
            chat_name="Naveen Raj",
            sender_id="naveen_raj",
            sender_name="Naveen Raj",
            timestamp=time.time(),
            text="send sumanth video",
            message_type=MessageType.TEXT,
        )

        await router.route_message(msg)

        # Verify sender dispatched the video
        sender_mock.send_media.assert_awaited_once()
        call_args = sender_mock.send_media.call_args[1]
        assert call_args["chat_name"] == "Naveen Raj"
        assert "sumanth_sleeping.mp4" in call_args["file_path"]
        assert call_args["media_type"] == "video"
        # Verify no "REPLY:" was output
        assert not call_args["caption"].lower().startswith("reply:")
