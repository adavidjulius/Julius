"""
Julius WhatsApp Integration — Latent Communication Style Learner.

Extracts linguistic patterns from user messages over days and conversation turns:
- Formality score (0.0 to 1.0)
- Slang frequency (0.0 to 1.0)
- Emoji frequency
- Average message length / verbosity
- Tamil/Tanglish mixing level
- Humor/playfulness index

Computes rolling averages across turns to update the per-chat StyleProfile
without robotic phrase copying.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Dict, List, Optional

from .context import TANGLISH_VOCAB_REGEX
from .models import StyleObservation, StyleProfile, WhatsAppMessage
from .persona import PersonaEngine
from .storage import WhatsAppStorage

logger = logging.getLogger(__name__)

# Common Indian/Tamil college peer slang tokens
_SLANG_TOKENS = {
    "bro", "da", "machi", "machan", "thala", "thalaiva", "seri", "serida",
    "dei", "nanba", "enna", "ethu", "solra", "sollu", "podhum", "semma",
    "paaru", "kelambu", "scene", "matter", "lite", "mokka", "kidu", "vera level"
}

_FORMAL_INDICATORS = {
    "please", "kindly", "regards", "sir", "madam", "request", "sincerely",
    "appreciate", "thank you", "dear", "grateful", "assistance", "cordially"
}

_EMOJI_REGEX = re.compile(
    r"[\U00010000-\U0010ffff]|[\u2600-\u27bf]|[\u2300-\u23ff]",
    flags=re.UNICODE,
)

_HUMOR_TOKENS = {
    "haha", "hahaha", "hehe", "lol", "lmao", "rofl", "😂", "🤣", "💀", "dead"
}


class CommunicationStyleLearner:
    """Extracts linguistic signals and updates latent persona style profiles."""

    def __init__(self, storage: WhatsAppStorage, persona: PersonaEngine) -> None:
        self._storage = storage
        self._persona = persona

    def observe_turn(self, message: WhatsAppMessage) -> Optional[StyleObservation]:
        """Analyze an incoming message turn and record an observation."""
        if message.is_from_me or not message.text or len(message.text.strip()) == 0:
            return None

        text = message.text.strip()
        words = text.split()
        word_count = len(words)
        lower_text = text.lower()

        # 1. Emoji count
        emojis = _EMOJI_REGEX.findall(text)
        emoji_count = len(emojis)

        # 2. Formality score: 0.0 (very casual) to 1.0 (formal)
        formal_hits = sum(1 for w in _FORMAL_INDICATORS if w in lower_text)
        informal_hits = sum(1 for w in _SLANG_TOKENS if w in lower_text)
        if formal_hits > 0 and informal_hits == 0:
            formality = min(1.0, 0.6 + (formal_hits * 0.15))
        elif informal_hits > 0:
            formality = max(0.0, 0.4 - (informal_hits * 0.1))
        else:
            formality = 0.45  # neutral baseline

        # 3. Slang score: 0.0 (none) to 1.0 (heavy slang)
        slang_hits = sum(1 for tok in _SLANG_TOKENS if tok in lower_text)
        slang_score = min(1.0, slang_hits * 0.25)

        # 4. Tamil / Tanglish mix: 0.0 (pure English) to 1.0 (heavy Tanglish)
        tanglish_matches = TANGLISH_VOCAB_REGEX.findall(lower_text)
        tamil_mix = min(1.0, len(tanglish_matches) * 0.3)

        # 5. Humor score: 0.0 to 1.0
        humor_hits = sum(1 for h in _HUMOR_TOKENS if h in lower_text)
        humor_score = min(1.0, humor_hits * 0.35)

        obs = StyleObservation(
            chat_name=message.chat_name,
            message_id=message.id,
            formality_score=round(formality, 2),
            slang_score=round(slang_score, 2),
            emoji_count=emoji_count,
            avg_word_count=float(word_count),
            tamil_english_mix=round(tamil_mix, 2),
            humor_score=round(humor_score, 2),
            observed_at=time.time(),
        )

        self._storage.save_style_observation(obs)
        self._update_latent_style_profile(message.chat_name)
        return obs

    def _update_latent_style_profile(self, chat_name: str) -> None:
        """Compute rolling aggregate style features and update the chat's StyleProfile."""
        observations = self._storage.get_recent_style_observations(chat_name, limit=20)
        if not observations or len(observations) < 2:
            return

        n = len(observations)
        avg_formality = sum(o.formality_score for o in observations) / n
        avg_slang = sum(o.slang_score for o in observations) / n
        avg_emoji = sum(o.emoji_count for o in observations) / n
        avg_len = sum(o.avg_word_count for o in observations) / n
        avg_tamil = sum(o.tamil_english_mix for o in observations) / n
        avg_humor = sum(o.humor_score for o in observations) / n

        current_profile = self._persona.get_profile(chat_name)

        # Update formality
        if avg_formality > 0.65:
            current_profile.formality = "formal"
        elif avg_formality < 0.35:
            current_profile.formality = "very casual"
        else:
            current_profile.formality = "casual"

        # Update emoji frequency
        if avg_emoji > 1.5:
            current_profile.emoji_frequency = "frequent"
        elif avg_emoji > 0.5:
            current_profile.emoji_frequency = "moderate"
        else:
            current_profile.emoji_frequency = "rare"

        # Update directness/verbosity
        if avg_len < 6:
            current_profile.response_directness = "terse"
        elif avg_len > 25:
            current_profile.response_directness = "detailed"
        else:
            current_profile.response_directness = "conversational"

        # Update tone
        if avg_humor > 0.4:
            current_profile.tone = "playful and witty"
        elif avg_slang > 0.4:
            current_profile.tone = "chill college peer"
        else:
            current_profile.tone = "friendly"

        # Store latent style parameters in custom_adjustments
        current_profile.custom_adjustments = {
            "slang_level": "high" if avg_slang > 0.4 else ("medium" if avg_slang > 0.15 else "low"),
            "tamil_english_mix": "high" if avg_tamil > 0.3 else ("medium" if avg_tamil > 0.1 else "low"),
            "humor_level": "high" if avg_humor > 0.4 else "moderate",
            "samples_analyzed": n,
        }

        self._persona.update_chat_profile(chat_name, current_profile)
        logger.info(
            "[STYLE] Contact: %s | Updated latent style (formality=%s, emoji=%s, slang=%s, sample_count=%d)",
            chat_name,
            current_profile.formality,
            current_profile.emoji_frequency,
            current_profile.custom_adjustments.get("slang_level"),
            n,
        )

    def get_style_instructions_for_llm(self, chat_name: str) -> str:
        """Produce natural prompting instructions based on learned style."""
        prof = self._persona.get_profile(chat_name)
        adj = prof.custom_adjustments or {}

        instructions = [
            f"- Formality: {prof.formality}.",
            f"- Length: {prof.response_directness} (match peer's conversational brevity).",
            f"- Emojis: {prof.emoji_frequency}.",
        ]

        if adj.get("slang_level") == "high":
            instructions.append("- Peer uses casual college slang (bro, da, machi) — match this energy naturally.")
        if adj.get("tamil_english_mix") == "high":
            instructions.append("- Peer mixes Tanglish/Tamil words — understand them effortlessly while replying in casual English.")
        if adj.get("humor_level") == "high":
            instructions.append("- Tone is playful/witty — be responsive and keep it lighthearted.")

        return "\n".join(instructions)
