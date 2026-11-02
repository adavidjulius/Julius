"""Tests for WhatsApp persona style engine and training mode."""

import pytest
from src.integrations.whatsapp.models import StyleProfile, TrainingExample
from src.integrations.whatsapp.persona import PersonaEngine
from src.integrations.whatsapp.storage import WhatsAppStorage
from src.integrations.whatsapp.training import TrainingManager


@pytest.fixture
def persona_and_training(tmp_path):
    db_path = str(tmp_path / "test_wa_persona.db")
    storage = WhatsAppStorage(db_path=db_path)
    persona = PersonaEngine(storage=storage)
    training = TrainingManager(storage=storage, persona_engine=persona)
    return storage, persona, training


def test_default_style_profile_loading(persona_and_training):
    _, persona, _ = persona_and_training
    profile = persona.get_profile()
    assert profile.name == "default"
    assert profile.tone in ("casual", "neutral", "formal")


def test_update_style_profile(persona_and_training):
    storage, persona, _ = persona_and_training
    custom = StyleProfile(name="default", tone="formal", formality="high")
    persona.update_default_profile(custom)

    loaded = persona.get_profile()
    assert loaded.tone == "formal"
    assert loaded.formality == "high"


def test_training_example_ingestion_and_stats(persona_and_training):
    _, _, training = persona_and_training
    ex = TrainingExample(
        incoming_text="Are we still meeting at 3?",
        predicted_reply="Yes, 3 PM works.",
        actual_reply="yes at 3!",
        chat_name="Alice",
    )
    training.add_example(ex)

    stats = training.get_stats()
    assert stats["total_examples"] >= 1
    assert "curriculum" in stats
