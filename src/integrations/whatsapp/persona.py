"""
Julius WhatsApp Integration — Persona & Style Engine.

Manages user communication style profiles with per-chat adjustments.
Provides a global identity foundation that can be customized per chat.
"""

from __future__ import annotations

import logging
from typing import Dict, Optional

from .models import ChatConfig, StyleProfile
from .storage import WhatsAppStorage

logger = logging.getLogger(__name__)


class PersonaEngine:
    """
    Manages the user's communication style profile.

    One global style foundation + per-chat adjustments.
    Profiles are learned from training examples and editable by the user.
    """

    def __init__(self, storage: WhatsAppStorage) -> None:
        self._storage = storage
        self._default_profile: Optional[StyleProfile] = None
        self._chat_profiles: Dict[str, StyleProfile] = {}
        self._load_profiles()

    def _load_profiles(self) -> None:
        """Load all profiles from storage."""
        self._default_profile = self._storage.get_style_profile("default")
        if self._default_profile is None:
            self._default_profile = StyleProfile(name="default")
            self._storage.save_style_profile(self._default_profile)

    def get_profile(self, chat_name: Optional[str] = None) -> StyleProfile:
        """
        Get the effective style profile for a chat.

        If the chat has a custom persona, merge it with the default.
        Otherwise return the default profile.
        """
        if chat_name:
            key = chat_name.lower()
            if key in self._chat_profiles:
                return self._chat_profiles[key]

            # Check for a saved chat-specific profile
            profile = self._storage.get_style_profile(f"chat:{key}")
            if profile:
                self._chat_profiles[key] = profile
                return profile

        return self._default_profile or StyleProfile(name="default")

    def update_default_profile(self, profile: StyleProfile) -> None:
        """Update the global default style profile."""
        profile.name = "default"
        self._default_profile = profile
        self._storage.save_style_profile(profile)
        logger.info("Updated default WhatsApp style profile")

    def update_chat_profile(self, chat_name: str, profile: StyleProfile) -> None:
        """Update a chat-specific style profile."""
        key = chat_name.lower()
        profile.name = f"chat:{key}"
        self._chat_profiles[key] = profile
        self._storage.save_style_profile(profile)
        logger.info("Updated style profile for chat '%s'", chat_name)

    def get_all_profiles(self) -> Dict[str, StyleProfile]:
        """Get all profiles (default + per-chat)."""
        result = {"default": self._default_profile or StyleProfile(name="default")}
        result.update(self._chat_profiles)
        return result

    def build_style_instructions(
        self, profile: StyleProfile, chat_config: Optional[ChatConfig] = None
    ) -> str:
        """Build human-readable style instructions for display."""
        lines = [
            f"📝 Style: {profile.name}",
            f"   Tone: {profile.tone}",
            f"   Length: {profile.response_directness}",
            f"   Formality: {profile.formality}",
            f"   Emoji: {profile.emoji_frequency}",
            f"   Punctuation: {profile.punctuation_style}",
            f"   Capitalization: {profile.capitalization}",
            f"   Greetings: {profile.greeting_habit}",
        ]
        if profile.preferred_phrases:
            lines.append(f"   Phrases: {', '.join(profile.preferred_phrases[:5])}")
        if profile.confidence_scores:
            confidence_str = ", ".join(
                f"{k}: {v:.0%}" for k, v in profile.confidence_scores.items() if v > 0
            )
            if confidence_str:
                lines.append(f"   Confidence: {confidence_str}")
        return "\n".join(lines)
