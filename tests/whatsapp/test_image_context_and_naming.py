import pytest
import time
import os
import io
from pathlib import Path

from src.integrations.whatsapp.intent_engine import IntentEngine, MessageIntent
from src.integrations.whatsapp.media_manager import extract_media_subject, WhatsAppMediaManager
from src.integrations.whatsapp.media_resolver import MediaResolver, ResolutionStatus
from src.integrations.whatsapp.storage import WhatsAppStorage
from src.integrations.whatsapp.models import WhatsAppMessage, MessageType


def _make_test_jpeg_bytes(color: str = "blue") -> bytes:
    try:
        from PIL import Image
        bio = io.BytesIO()
        Image.new("RGB", (10, 10), color=color).save(bio, format="JPEG")
        return bio.getvalue()
    except ImportError:
        return (
            b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00"
            b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342"
            b"\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b"
            b"\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf\x00\xff\xd9"
        )


class TestImageContextAndNaming:

    def test_extract_media_subject_patterns(self):
        # 1. With caption attached to image
        assert extract_media_subject("Rohit images save it") == "Rohit"
        assert extract_media_subject("rohit image save it in your memory") == "Rohit"
        assert extract_media_subject("Rohit image") == "Rohit"
        assert extract_media_subject("Name of the image is Rohit") == "Rohit"
        assert extract_media_subject("The image name is Rohit") == "Rohit"
        assert extract_media_subject("this is rohit photo") == "Rohit"
        assert extract_media_subject("it is rohit") == "Rohit"
        assert extract_media_subject("save as rohit") == "Rohit"
        assert extract_media_subject("save the photo as rohit") == "Rohit"
        assert extract_media_subject("Rohit Sharma") == "Rohit Sharma"
        assert extract_media_subject("Sumanth sleeping") == "Sumanth Sleeping"

        # 2. Generic inputs that should prompt for clarification
        assert extract_media_subject("save this photo") is None
        assert extract_media_subject("photo") is None
        assert extract_media_subject("") is None
        assert extract_media_subject("[Image]") is None
        assert extract_media_subject("[Photo received: photo]") is None
        assert extract_media_subject("save it") is None

    def test_intent_engine_image_naming_and_typos(self):
        # Naming / Renaming
        c1 = IntentEngine.classify("Name of the image is Rohit")
        assert c1["intent"] == MessageIntent.RENAME_MEDIA_OR_DOCUMENT
        assert c1["target"] == "Rohit"

        c2 = IntentEngine.classify("The image name is Rohit")
        assert c2["intent"] == MessageIntent.RENAME_MEDIA_OR_DOCUMENT
        assert c2["target"] == "Rohit"

        c3 = IntentEngine.classify("it is rohit")
        assert c3["intent"] == MessageIntent.RENAME_MEDIA_OR_DOCUMENT
        assert c3["target"] == "Rohit"

        c4 = IntentEngine.classify("Rohit images save it")
        assert c4["intent"] == MessageIntent.RENAME_MEDIA_OR_DOCUMENT
        assert c4["target"] == "Rohit"

        # Typo-tolerant send image
        c5 = IntentEngine.classify("Sene me the image")
        assert c5["intent"] == MessageIntent.SEND_PERSON_IMAGE

        c6 = IntentEngine.classify("Send me Rohit image")
        assert c6["intent"] == MessageIntent.SEND_PERSON_IMAGE
        assert c6["target"] == "Rohit"

        c7 = IntentEngine.classify("Send me sumanth image")
        assert c7["intent"] == MessageIntent.SEND_PERSON_IMAGE
        assert c7["target"] == "Sumanth"

    def test_media_resolver_rohit_and_contextual(self, tmp_path):
        db_path = str(tmp_path / "test_wa.db")
        storage = WhatsAppStorage(db_path)

        # Create valid dummy JPEG with JFIF magic bytes
        rohit_path = tmp_path / "rohit.jpg"
        rohit_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xdb" + b"\x00" * 50 + b"\xff\xd9"
        rohit_path.write_bytes(rohit_bytes)

        storage.save_media_item({
            "media_id": "test_rohit_1",
            "media_type": "image",
            "filename": "rohit.jpg",
            "storage_path": str(rohit_path),
            "conversation_id": "MIT Naveen Raj ECE",
            "sender": "MIT Naveen Raj ECE",
            "timestamp": time.time(),
            "caption": "Photo of Rohit",
            "entities": ["Rohit", "MIT Rohit Sharma"],
            "status": "VERIFIED",
        })

        resolver = MediaResolver(storage)

        # 1. Explicit query for Rohit
        res_rohit = resolver.resolve_image(person_query="Rohit", chat_name="MIT Naveen Raj ECE")
        assert res_rohit.status == ResolutionStatus.EXACT_MATCH
        assert res_rohit.item["filename"] == "rohit.jpg"

        # 2. Contextual query ("Sene me the image")
        res_ctx = resolver.resolve_image(person_query="", general_query="Sene me the image", chat_name="MIT Naveen Raj ECE")
        assert res_ctx.status == ResolutionStatus.EXACT_MATCH
        assert res_ctx.item["filename"] == "rohit.jpg"

        # 3. Query for Sumanth does NOT substitute Rohit (and if found, must be sumanth)
        res_sumanth = resolver.resolve_image(person_query="Sumanth", chat_name="MIT Naveen Raj ECE")
        if res_sumanth.status == ResolutionStatus.EXACT_MATCH:
            assert "sumanth" in res_sumanth.item["filename"].lower()
            assert "rohit" not in res_sumanth.item["filename"].lower()

        # 4. Query for completely unknown person returns NOT_FOUND
        res_unknown = resolver.resolve_image(person_query="Zackary Nonexistent", chat_name="MIT Naveen Raj ECE")
        assert res_unknown.status == ResolutionStatus.NOT_FOUND

    def test_unnamed_image_triggers_needs_naming(self, tmp_path):
        mgr = WhatsAppMediaManager(media_root=tmp_path)
        jfif_bytes = _make_test_jpeg_bytes("blue")
        import base64
        b64 = "data:image/jpeg;base64," + base64.b64encode(jfif_bytes).decode()

        # 1. Image with empty context hint -> needs_naming = True
        rec_unnamed = mgr.save_image_from_base64_text(
            text=b64,
            sender_name="MIT Naveen Raj ECE",
            context_hint="",
        )
        assert rec_unnamed is not None
        assert rec_unnamed.get("needs_naming") is True
        assert rec_unnamed.get("subject") is None

        # 2. Image with explicit context hint -> needs_naming = False, subject extracted
        rec_named = mgr.save_image_from_base64_text(
            text=b64,
            sender_name="MIT Naveen Raj ECE",
            context_hint="Rohit images save it",
        )
        assert rec_named is not None
        assert rec_named.get("needs_naming") is False
        assert rec_named.get("subject") == "Rohit"
        assert "rohit" in rec_named.get("filename", "").lower()

    def test_rename_recent_media(self, tmp_path):
        mgr = WhatsAppMediaManager(media_root=tmp_path)
        jfif_bytes = _make_test_jpeg_bytes("green")
        import base64
        b64 = "data:image/jpeg;base64," + base64.b64encode(jfif_bytes).decode()

        # Save unnamed photo
        mgr.save_image_from_base64_text(
            text=b64,
            sender_name="MIT Naveen Raj ECE",
            context_hint="",
        )

        # User renames recent photo to Rohit
        renamed = mgr.rename_recent_media(
            chat_name="MIT Naveen Raj ECE",
            new_name="Rohit",
            entity_name="Rohit",
        )
        assert renamed is not None
        assert renamed["filename"] == "rohit.jpg"
        assert "Rohit" in renamed["entities"]
        assert Path(renamed["path"]).name == "rohit.jpg"
        assert Path(renamed["path"]).exists()

    def test_parse_llm_action_response(self):
        from src.integrations.whatsapp.router import parse_llm_action_response

        # 1. Code-fenced JSON
        fenced = """```json
{
  "thought": "User wants photo of Rohit which is in Available Photos",
  "action": "SEND_IMAGE",
  "action_params": {"file_path": "rohit.jpg"},
  "reply_text": "Here is the photo of Rohit bro 📸"
}
```"""
        p1 = parse_llm_action_response(fenced)
        assert p1["action"] == "SEND_IMAGE"
        assert p1["action_params"]["file_path"] == "rohit.jpg"
        assert "Rohit" in p1["reply_text"]

        # 2. Raw JSON
        raw_json = '{"thought": "timetable requested", "action": "SEND_DOCUMENT", "action_params": {"file_path": "Schedule for First Assessment Test -16.09.2026.pdf"}, "reply_text": "Here is the timetable bro 📄"}'
        p2 = parse_llm_action_response(raw_json)
        assert p2["action"] == "SEND_DOCUMENT"
        assert "Assessment" in p2["action_params"]["file_path"]
        assert "timetable" in p2["reply_text"]

        # 3. Rename action
        rename_json = '{"action": "RENAME_MEDIA", "action_params": {"new_name": "Rohit"}, "reply_text": "Got it! Saved as Rohit"}'
        p3 = parse_llm_action_response(rename_json)
        assert p3["action"] == "RENAME_MEDIA"
        assert p3["action_params"]["new_name"] == "Rohit"

        # 4. Ask name action
        ask_json = '{"action": "ASK_MEDIA_NAME", "reply_text": "Who is this photo of?"}'
        p4 = parse_llm_action_response(ask_json)
        assert p4["action"] == "ASK_MEDIA_NAME"
        assert "Who is this" in p4["reply_text"]

        # 5. Plain text fallback
        plain = "Hello bro, how are you doing today?"
        p5 = parse_llm_action_response(plain)
        assert p5["action"] == "REPLY"
        assert p5["reply_text"] == plain

    @pytest.mark.asyncio
    async def test_router_executes_llm_send_image_action(self, tmp_path):
        from unittest.mock import AsyncMock, MagicMock
        from src.integrations.whatsapp.router import WhatsAppMessageRouter
        from src.integrations.whatsapp.models import ChatConfig, ChatMode, WhatsAppMessage

        # Setup dummy photo
        img_dir = tmp_path / "images"
        img_dir.mkdir(parents=True)
        photo_file = img_dir / "rohit.jpg"
        photo_file.write_bytes(_make_test_jpeg_bytes("yellow"))

        mock_policy = MagicMock()
        mock_policy.should_process.return_value = True
        mock_policy.get_chat_config.return_value = ChatConfig(chat_name="MIT Naveen Raj ECE", mode=ChatMode.AUTO)

        mock_sender = MagicMock()
        mock_sender.send_image = AsyncMock(return_value=True)
        mock_sender.send_message = AsyncMock(return_value=True)

        mock_storage = MagicMock()
        mock_storage.is_message_replied.return_value = False
        mock_storage.find_media_items.return_value = []
        mock_storage.get_recent_messages.return_value = []

        mock_config = MagicMock()
        mock_context = MagicMock()
        mock_persona = MagicMock()
        mock_training = MagicMock()
        mock_safety = MagicMock()
        mock_safety.evaluate_message.return_value = (MagicMock(value="high"), "ok")
        mock_safety.evaluate_response.return_value = (MagicMock(value="high"), "ok")
        mock_safety.should_escalate.return_value = False
        mock_queue = MagicMock()

        router = WhatsAppMessageRouter(
            policy=mock_policy,
            sender=mock_sender,
            storage=mock_storage,
            config=mock_config,
            context=mock_context,
            persona=mock_persona,
            training=mock_training,
            safety=mock_safety,
            approval_queue=mock_queue,
        )

        # Mock media manager index with rohit.jpg
        from src.integrations.whatsapp.media_manager import get_media_manager
        mm = get_media_manager(tmp_path)
        mm._index.append({
            "id": "img_rohit",
            "filename": "rohit.jpg",
            "title": "Rohit Photo",
            "path": str(photo_file.resolve()),
            "is_image": True,
            "entities": ["Rohit"],
            "timestamp": time.time(),
        })

        # LLM returns structured SEND_IMAGE response
        llm_reply = """```json
{
  "thought": "Rohit photo is available in JuliusData",
  "action": "SEND_IMAGE",
  "action_params": {"file_path": "rohit.jpg"},
  "reply_text": "Here is the photo of Rohit bro 📸"
}
```"""
        router._generate_reply = AsyncMock(return_value=llm_reply)

        msg = WhatsAppMessage(
            id="test_msg_1",
            chat_id="test_chat_id",
            chat_name="MIT Naveen Raj ECE",
            sender_id="test_sender_id",
            sender_name="MIT Naveen Raj ECE",
            text="send me rohit image",
            timestamp=time.time(),
        )

        await router._handle_auto(msg, mock_policy.get_chat_config("MIT Naveen Raj ECE"))

        # Verify send_image was called with rohit.jpg!
        mock_sender.send_image.assert_called_once()
        call_kwargs = mock_sender.send_image.call_args[1]
        assert "rohit.jpg" in call_kwargs["file_path"]
        assert "Rohit" in call_kwargs["caption"]

