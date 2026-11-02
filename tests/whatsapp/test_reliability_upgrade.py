"""
Julius WhatsApp Integration — Full Reliability & Intelligence Upgrade Tests.

Covers:
1. Exact person & entity resolution (Naveen vs Narendra vs Sumanth vs Gova vs Govardhan).
2. Deterministic MediaResolver (zero cross-person substitution, ambiguity detection, NOT_FOUND).
3. Image renaming & entity tagging ("This is naveen image save the photo name as naveen").
4. Timetable & Schedule Engine (exact Asia/Kolkata date/time, scheduled phrasing, free period/lunch).
5. Document Safety & Exact Retrieval (no accidental send on mentions, semester accuracy).
6. ActionGuard & AnswerVerifier (receipt generation, fake success suppression).
7. Persistent Memory (survives chat clear).
"""

import os
from pathlib import Path
import shutil
import tempfile
import time
import pytest

from src.integrations.whatsapp.models import (
    ActionReceipt,
    ActionType,
    EntityRecord,
    MediaResolution,
    ReceiptStatus,
    ResolutionStatus,
    WhatsAppMessage,
)
from src.integrations.whatsapp.storage import WhatsAppStorage
from src.integrations.whatsapp.entity_resolver import EntityResolver
from src.integrations.whatsapp.media_resolver import MediaResolver
from src.integrations.whatsapp.timetable_engine import TimetableEngine
from src.integrations.whatsapp.action_guard import ActionGuard
from src.integrations.whatsapp.answer_verifier import AnswerVerifier
from src.integrations.whatsapp.intent_engine import IntentEngine, MessageIntent
from src.integrations.whatsapp.media_manager import WhatsAppMediaManager
from src.integrations.whatsapp.tools import get_current_datetime


@pytest.fixture
def temp_dir():
    d = tempfile.mkdtemp(prefix="wa_reliability_test_")
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def storage(temp_dir):
    db_path = os.path.join(temp_dir, "test_wa.db")
    s = WhatsAppStorage(db_path=db_path)
    return s


@pytest.fixture
def media_manager(temp_dir):
    media_root = Path(temp_dir) / "received_media"
    return WhatsAppMediaManager(media_root=media_root)


# =========================================================================
# 1. Exact Person & Entity Resolution
# =========================================================================

class TestEntityResolution:
    def test_known_peers_resolution(self, storage):
        resolver = EntityResolver(storage)
        
        # Test Dave resolution
        e_nav = resolver.resolve_person("Dave")
        assert e_nav is not None
        assert "Dave" in e_nav["canonical_name"]
        assert e_nav["metadata"]["dept"] == "Design"
        
        # Test Alex vs Alexander disambiguation
        e_gova = resolver.resolve_person("Alex")
        assert e_gova is not None
        assert e_gova["canonical_name"] == "Contact Alex"
        assert e_gova["metadata"]["dept"] == "Engineering"
        
        e_govardhan = resolver.resolve_person("Alexander")
        assert e_govardhan is not None
        assert e_govardhan["canonical_name"] == "Contact Alexander"
        assert e_govardhan["metadata"]["dept"] != "Engineering"
        
        # Test UnknownPerson (not fabricated)
        e_unknown = resolver.resolve_person("UnknownPerson")
        assert e_unknown is None

    def test_text_mention_extraction(self, storage):
        resolver = EntityResolver(storage)
        
        # Extracts only real entities, disambiguating alex and alexander
        entities = resolver.extract_entities_from_text("Hey is alexander with dave today?")
        names = [e["canonical_name"] for e in entities]
        assert "Contact Alexander" in names
        assert "Contact Dave" in names
        assert "Contact Alex" not in names  # Should not falsely match alex inside alexander


# =========================================================================
# 2. MediaResolver: Zero Cross-Person Substitution & Exact Retrieval
# =========================================================================

class TestMediaResolver:
    def test_no_cross_person_substitution(self, storage, temp_dir):
        # Create an image for Kevin
        kevin_img = os.path.join(temp_dir, "kevin_photo.jpg")
        with open(kevin_img, "wb") as f:
            f.write(b"FAKE_IMAGE_DATA_KEVIN")

        storage.save_media_item({
            "file_path": kevin_img,
            "filename": "kevin_photo.jpg",
            "storage_path": kevin_img,
            "media_type": "image",
            "sender": "Nathan",
            "caption": "Kevin photo",
            "entities": ["Contact Kevin", "Kevin"],
            "verified": True,
        })

        resolver = MediaResolver(storage)
        
        # Request Dave's image
        res_nav = resolver.resolve_image(person_query="Dave")
        # MUST NOT substitute Kevin's image!
        assert res_nav.status == ResolutionStatus.NOT_FOUND
        assert res_nav.item is None
        assert "Dave" in res_nav.reason or "No verified image" in res_nav.reason

        # Request Kevin's image -> matches exactly
        res_sum = resolver.resolve_image(person_query="Kevin")
        assert res_sum.status == ResolutionStatus.EXACT_MATCH
        assert res_sum.item is not None
        assert res_sum.item["filename"] == "kevin_photo.jpg"

    def test_ambiguity_detection(self, storage, temp_dir):
        # Create two photos for Goa trip
        img1 = os.path.join(temp_dir, "goa_beach.jpg")
        img2 = os.path.join(temp_dir, "goa_sunset.jpg")
        with open(img1, "wb") as f: f.write(b"GOA1")
        with open(img2, "wb") as f: f.write(b"GOA2")

        storage.save_media_item({
            "file_path": img1,
            "filename": "goa_beach.jpg",
            "storage_path": img1,
            "media_type": "image",
            "caption": "Goa trip beach",
            "entities": ["Goa"],
            "verified": True,
        })
        storage.save_media_item({
            "file_path": img2,
            "filename": "goa_sunset.jpg",
            "storage_path": img2,
            "media_type": "image",
            "caption": "Goa trip sunset",
            "entities": ["Goa"],
            "verified": True,
        })

        resolver = MediaResolver(storage)
        res = resolver.resolve_image(person_query="Goa")
        
        # Must detect ambiguity instead of randomly picking one
        assert res.status == ResolutionStatus.AMBIGUOUS
        assert len(res.candidates) >= 2

    def test_semester_timetable_accuracy(self, storage, temp_dir):
        # 1st semester timetable exists
        doc1 = os.path.join(temp_dir, "First_Semester_Timetable_2026.pdf")
        with open(doc1, "wb") as f: f.write(b"PDF1")
        storage.save_document_record({
            "filename": "First_Semester_Timetable_2026.pdf",
            "storage_path": doc1,
            "doc_type": "timetable",
            "semester": 1,
            "title": "MIT IT First Semester Timetable",
            "entities": ["Timetable", "Semester 1"],
            "verified": True,
        })

        resolver = MediaResolver(storage)
        
        # Request second semester timetable
        res_sem2 = resolver.resolve_document(
            query="Send me the second semester timetable",
            semester=2,
        )
        # Must return NOT_FOUND and explain that only first semester is available
        assert res_sem2.status == ResolutionStatus.NOT_FOUND
        assert "first semester" in res_sem2.reason.lower() or "second semester" in res_sem2.reason.lower()


# =========================================================================
# 3. Dynamic Image Renaming & Entity Tagging
# =========================================================================

class TestMediaRenaming:
    def test_user_corrects_image_name(self, media_manager, temp_dir):
        # Simulate incoming photo saved as "gova_image.jpg"
        import base64
        b64_dummy = base64.b64encode(b"PHOTO_OF_NAVEEN").decode("utf-8")
        saved = media_manager.save_image(
            image_data=b64_dummy,
            sender_name="Latchuman",
            caption="Gova Image",
            filename="gova_image.jpg",
            chat_id="MIT Latchuman",
        )
        assert saved is not None
        raw_path = Path(saved["path"])
        assert raw_path.exists()

        # Latchuman says: "This is naveen image save the photo name as naveen"
        intent_engine = IntentEngine()
        intent, params = intent_engine.classify_intent(
            "This is naveen image save the photo name as naveen",
            chat_name="MIT Latchuman",
        )
        assert intent == MessageIntent.RENAME_MEDIA_OR_DOCUMENT
        assert "naveen" in params["new_name"].lower()

        # Execute rename via MediaManager
        res_item = media_manager.rename_recent_media(
            chat_name="MIT Latchuman",
            new_name=params["new_name"],
            entity_name=params.get("entity_name", "Naveen"),
        )
        assert res_item is not None
        assert os.path.exists(res_item["path"])
        assert "naveen" in res_item["filename"].lower()
        assert not raw_path.exists()  # old path deleted


# =========================================================================
# 4. Deterministic Timetable & Schedule Engine
# =========================================================================

class TestTimetableEngine:
    def test_exact_scheduled_location(self, storage):
        engine = TimetableEngine(storage)
        
        # Test Monday 10:00 (Engineering Physics in Room 004)
        status = engine.get_schedule_status(weekday="Monday", hour=10, minute=0)
        assert status["is_free"] is False
        assert "Physics" in status["activity"]
        # Mandatory phrasing requirement: must state "According to the schedule..."
        assert "According to the schedule" in status["formatted_message"]
        assert "is scheduled" in status["formatted_message"]
        # Must never claim physical certainty
        assert "physically" not in status["formatted_message"].lower()

    def test_free_period_and_lunch(self, storage):
        engine = TimetableEngine(storage)
        
        # Monday 12:45 is Lunch Break
        lunch_status = engine.get_schedule_status(weekday="Monday", hour=12, minute=45)
        assert lunch_status["is_free"] is True
        assert "Lunch" in lunch_status["activity"]

        # Monday 15:45 is Free Period / Library
        free_status = engine.get_schedule_status(weekday="Monday", hour=15, minute=45)
        assert free_status["is_free"] is True
        assert "Free" in free_status["activity"] or "Library" in free_status["activity"]


# =========================================================================
# 5. Intent Separation & Safety (No Accidental Dispatch)
# =========================================================================

class TestIntentSeparation:
    def test_person_question_does_not_trigger_media(self):
        engine = IntentEngine()
        
        # "Who is Alex?" -> ASK_PERSON_INFO, NOT SEND_IMAGE
        intent, params = engine.classify_intent("Who is Alex?")
        assert intent == MessageIntent.ASK_PERSON_INFO
        assert intent != MessageIntent.SEND_PERSON_IMAGE

        # "Show me Alex's image" -> SEND_PERSON_IMAGE
        intent2, params2 = engine.classify_intent("Show me Alex's image")
        assert intent2 == MessageIntent.SEND_PERSON_IMAGE
        assert params2.get("person").lower() == "alex"

    def test_document_mention_does_not_send(self):
        engine = IntentEngine()
        
        # "I have the exam timetable" -> INFORMATIONAL_STATEMENT, NOT SEND_DOCUMENT
        intent, _ = engine.classify_intent("I have the exam timetable")
        assert intent == MessageIntent.INFORMATIONAL_STATEMENT
        assert intent != MessageIntent.SEND_DOCUMENT

        # "Send me the exam timetable" -> SEND_DOCUMENT
        intent2, params2 = engine.classify_intent("Send me the exam timetable")
        assert intent2 == MessageIntent.SEND_DOCUMENT


# =========================================================================
# 6. ActionGuard & AnswerVerifier (Machine-Readable Receipts)
# =========================================================================

class TestActionGuardAndVerifier:
    def test_action_guard_blocks_unverified(self, storage):
        guard = ActionGuard(storage)
        
        # Attempt to send a non-existent image
        rec = guard.authorize_media_send(
            requester="Latchuman",
            target_chat="MIT Latchuman",
            resolution=MediaResolution(
                status=ResolutionStatus.EXACT_MATCH,
                item={"filename": "fake.jpg", "storage_path": "/tmp/non_existent_image_12345.jpg"},
                media_type="image",
                target_entity="Naveen",
            ),
            explicit_intent=True,
        )
        assert rec.execution_status == ReceiptStatus.FAILED
        assert "does not exist on disk" in rec.result.get("error", "")

    def test_answer_verifier_prevents_fake_success(self, storage):
        verifier = AnswerVerifier()
        
        # If receipt failed, verifier must detect inconsistency with a claim of success
        receipt = ActionReceipt(
            action_id="act_001",
            requested_by="Monish",
            intent="send_document",
            target="MIT Monish",
            execution_status=ReceiptStatus.FAILED,
            result={"error": "WhatsApp send button timed out"},
        )
        
        fake_claim = "Done! I sent the timetable to you bro."
        grounded_answer = verifier.verify_and_ground(fake_claim, action_receipt=receipt)
        
        # Must refuse the fake claim and state actual failure
        assert "Done! I sent" not in grounded_answer
        assert "could not confirm sending" in grounded_answer.lower() or "timed out" in grounded_answer.lower()


# =========================================================================
# 7. Persistent Memory Survives Chat Clear
# =========================================================================

class TestPersistentMemory:
    def test_clear_chat_preserves_entities_and_media(self, storage, temp_dir):
        # Save a contact message
        storage.save_message(
            WhatsAppMessage(
                id="msg_001",
                chat_id="chat_latchuman",
                sender_id="sender_latchuman",
                sender_name="Latchuman",
                chat_name="MIT Latchuman",
                text="Hello David",
                timestamp=time.time(),
                is_from_me=False,
            )
        )
        
        # Save persistent entity & media
        storage.save_entity({
            "id": "person_mit_naveen_raj_ece",
            "canonical_name": "MIT Naveen Raj ECE",
            "entity_type": "person",
            "metadata": {"dept": "ECE"},
        })
        storage.save_media_item({
            "file_path": os.path.join(temp_dir, "naveen.jpg"),
            "filename": "naveen.jpg",
            "storage_path": os.path.join(temp_dir, "naveen.jpg"),
            "media_type": "image",
            "entities": ["Naveen"],
            "verified": True,
        })
        
        # Clear chat
        del_count = storage.clear_chat(chat_name="MIT Latchuman")
        assert del_count >= 1
        
        # Verify messages are cleared
        recent = storage.get_recent_messages("MIT Latchuman")
        assert len(recent) == 0
        
        # Verify entities and media are PRESERVED
        nav_entity = storage.get_entity("MIT Naveen Raj ECE")
        assert nav_entity is not None
        assert nav_entity["canonical_name"] == "MIT Naveen Raj ECE"
        
        nav_media = storage.find_media_items(entity="Naveen")
        assert len(nav_media) >= 1
