"""
Julius WhatsApp Integration — Training Mode & Style Learning.

Captures incoming messages, generates predictions, stores the user's
actual replies, and learns communication patterns from approved examples.
"""

from __future__ import annotations

import logging
import re
import statistics
from collections import Counter
from typing import Any, Dict, List, Optional

from .models import StyleProfile, TrainingExample
from .storage import WhatsAppStorage

logger = logging.getLogger(__name__)

# Curriculum steps for guided training
TRAINING_CURRICULUM = [
    {
        "step": 1,
        "name": "Short Replies",
        "description": "Simple short responses (yes/no, times, one-liners)",
        "examples_needed": 3,
    },
    {
        "step": 2,
        "name": "Casual Conversations",
        "description": "Informal chat with friends/family",
        "examples_needed": 3,
    },
    {
        "step": 3,
        "name": "Work Conversations",
        "description": "Professional or semi-formal messages",
        "examples_needed": 2,
    },
    {
        "step": 4,
        "name": "Group Conversations",
        "description": "Replies in group chats",
        "examples_needed": 2,
    },
    {
        "step": 5,
        "name": "Emoji Usage",
        "description": "Messages where emojis are natural",
        "examples_needed": 2,
    },
    {
        "step": 6,
        "name": "Questions & Scheduling",
        "description": "Answering questions, making plans",
        "examples_needed": 2,
    },
    {
        "step": 7,
        "name": "Humor & Informal",
        "description": "Jokes, sarcasm, casual banter",
        "examples_needed": 1,
    },
]


class TrainingManager:
    """
    Manages training mode: captures message pairs, learns style patterns,
    and provides a guided curriculum.
    """

    def __init__(
        self,
        storage: WhatsAppStorage,
        persona_engine: Optional[Any] = None,
    ) -> None:
        self._storage = storage
        self._persona_engine = persona_engine

    def add_example(self, example: TrainingExample) -> TrainingExample:
        """Record a pre-constructed training example."""
        self._storage.save_training_example(example)
        if self._persona_engine:
            # Re-analyze style profile and update
            new_profile = self.analyze_style()
            self._persona_engine.update_default_profile(new_profile)
        logger.info("Training example added (%d total)", self.get_example_count())
        return example

    def add_training_example(
        self,
        incoming_text: str,
        actual_reply: str,
        predicted_reply: str = "",
        chat_name: str = "",
        chat_id: str = "",
        sender_name: str = "",
        is_group: bool = False,
    ) -> TrainingExample:
        """Record a training example (incoming → user's actual reply)."""
        example = TrainingExample(
            incoming_text=incoming_text,
            actual_reply=actual_reply,
            predicted_reply=predicted_reply,
            chat_name=chat_name,
            chat_id=chat_id,
            sender_name=sender_name,
            is_group=is_group,
        )
        return self.add_example(example)

    def get_stats(self) -> Dict[str, Any]:
        """Alias for get_training_stats()."""
        return self.get_training_stats()

    def get_example_count(self) -> int:
        return self._storage.get_training_count()

    def get_examples(self, limit: int = 100) -> List[TrainingExample]:
        return self._storage.get_training_examples(limit=limit)

    def train_from_chat_history(self, user_messages: List[str]) -> StyleProfile:
        """Analyze a batch of historical user messages and update default persona profile."""
        if not user_messages:
            return self.analyze_style()
        for msg in user_messages:
            example = TrainingExample(
                incoming_text="[history]",
                actual_reply=msg,
                is_group=False,
            )
            self._storage.save_training_example(example)
        new_profile = self.analyze_style()
        if self._persona_engine:
            self._persona_engine.update_default_profile(new_profile)
        return new_profile

    def delete_example(self, example_id: str) -> bool:
        return self._storage.delete_training_example(example_id)

    def get_curriculum_progress(self) -> List[Dict[str, Any]]:
        """Get the current progress through the training curriculum."""
        examples = self.get_examples(limit=500)
        total = len(examples)
        progress = []
        examples_used = 0

        for step in TRAINING_CURRICULUM:
            remaining = max(0, step["examples_needed"] - max(0, total - examples_used))
            completed = remaining == 0
            progress.append({
                "step": step["step"],
                "name": step["name"],
                "description": step["description"],
                "examples_needed": step["examples_needed"],
                "completed": completed,
                "remaining": remaining,
            })
            examples_used += step["examples_needed"]

        return progress

    def analyze_style(self, examples: Optional[List[TrainingExample]] = None) -> StyleProfile:
        """
        Analyze training examples to build/update a style profile.

        Extracts: message length, punctuation, capitalization, emoji usage,
        common phrases, abbreviations, greeting/closing patterns.
        """
        if examples is None:
            examples = self.get_examples(limit=500)

        if not examples:
            return StyleProfile(name="default")

        replies = [e.actual_reply for e in examples if e.actual_reply.strip()]
        if not replies:
            return StyleProfile(name="default")

        profile = StyleProfile(name="default")

        # ── Message length ────────────────────────────────────────
        word_counts = [len(r.split()) for r in replies]
        profile.avg_message_length = statistics.mean(word_counts) if word_counts else 0.0

        # ── Formality ─────────────────────────────────────────────
        formal_indicators = sum(
            1 for r in replies
            if any(f in r.lower() for f in ["please", "thank you", "regards", "sincerely", "dear"])
        )
        formal_ratio = formal_indicators / len(replies) if replies else 0
        if formal_ratio > 0.5:
            profile.formality = "high"
        elif formal_ratio > 0.2:
            profile.formality = "medium"
        else:
            profile.formality = "low"

        # ── Capitalization ────────────────────────────────────────
        lowercase_count = sum(1 for r in replies if r == r.lower())
        uppercase_start = sum(1 for r in replies if r and r[0].isupper())
        if lowercase_count / len(replies) > 0.7:
            profile.capitalization = "lowercase"
        elif uppercase_start / len(replies) > 0.7:
            profile.capitalization = "standard"
        else:
            profile.capitalization = "mixed"

        # ── Punctuation ───────────────────────────────────────────
        punct_counts = [
            sum(1 for c in r if c in ".,!?;:") for r in replies
        ]
        avg_punct = statistics.mean(punct_counts) if punct_counts else 0
        if avg_punct < 0.5:
            profile.punctuation_style = "minimal"
        elif avg_punct < 2.0:
            profile.punctuation_style = "standard"
        else:
            profile.punctuation_style = "heavy"

        # ── Emoji ─────────────────────────────────────────────────
        emoji_pattern = re.compile(
            "[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF"
            "\U0001F900-\U0001F9FF\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF"
            "\U00002702-\U000027B0\U0000FE00-\U0000FE0F\U0001F1E0-\U0001F1FF"
            "👍👋😂❤️🔥💯✨🎉👀🤔]+",
            re.UNICODE,
        )
        emoji_counts = [len(emoji_pattern.findall(r)) for r in replies]
        avg_emoji = statistics.mean(emoji_counts) if emoji_counts else 0
        if avg_emoji == 0:
            profile.emoji_frequency = "never"
        elif avg_emoji < 0.3:
            profile.emoji_frequency = "rare"
        elif avg_emoji < 0.8:
            profile.emoji_frequency = "occasional"
        else:
            profile.emoji_frequency = "frequent"

        # ── Tone ──────────────────────────────────────────────────
        casual_indicators = sum(
            1 for r in replies
            if any(w in r.lower() for w in [
                "yeah", "yep", "nah", "lol", "haha", "bruh",
                "gonna", "wanna", "gotta", "kinda", "btw",
                "nope", "yup", "dude", "bro", "mate",
            ])
        )
        casual_ratio = casual_indicators / len(replies) if replies else 0
        if casual_ratio > 0.3:
            profile.tone = "casual"
        elif casual_ratio > 0.1:
            profile.tone = "neutral"
        else:
            profile.tone = "formal"

        # ── Common phrases ────────────────────────────────────────
        all_words = " ".join(replies).lower().split()
        word_freq = Counter(all_words)
        common_phrases = [
            word for word, count in word_freq.most_common(20)
            if count >= 3 and len(word) > 2 and word not in {
                "the", "and", "for", "that", "this", "with", "you",
                "are", "was", "not", "but", "have", "has", "had",
            }
        ]
        profile.preferred_phrases = common_phrases[:10]

        # ── Abbreviations ─────────────────────────────────────────
        abbrev_pattern = re.compile(r'\b[a-z]{2,4}\b')
        common_abbrevs = ["brb", "idk", "tbh", "imo", "btw", "lmk", "nvm", "omg", "wtf"]
        found_abbrevs = [
            a for a in common_abbrevs
            if any(a in r.lower() for r in replies)
        ]
        profile.common_abbreviations = found_abbrevs

        # ── Greeting habit ────────────────────────────────────────
        greetings = ["hi", "hey", "hello", "yo", "sup"]
        greeting_count = sum(
            1 for r in replies
            if any(r.lower().startswith(g) for g in greetings)
        )
        greeting_ratio = greeting_count / len(replies) if replies else 0
        if greeting_ratio > 0.5:
            profile.greeting_habit = "always"
        elif greeting_ratio > 0.2:
            profile.greeting_habit = "sometimes"
        else:
            profile.greeting_habit = "usually_omitted"

        # ── Response directness ───────────────────────────────────
        if profile.avg_message_length < 8:
            profile.response_directness = "direct"
        elif profile.avg_message_length < 20:
            profile.response_directness = "moderate"
        else:
            profile.response_directness = "verbose"

        # ── Sentence fragmentation ────────────────────────────────
        fragment_count = sum(
            1 for r in replies
            if len(r.split(".")) <= 1 and len(r.split()) <= 10
        )
        fragment_ratio = fragment_count / len(replies) if replies else 0
        if fragment_ratio > 0.6:
            profile.sentence_fragmentation = "frequent"
        elif fragment_ratio > 0.3:
            profile.sentence_fragmentation = "occasional"
        else:
            profile.sentence_fragmentation = "none"

        # ── Confidence scores ─────────────────────────────────────
        n = len(replies)
        profile.confidence_scores = {
            "tone": min(1.0, n / 20),
            "length": min(1.0, n / 10),
            "emoji": min(1.0, n / 15),
            "vocabulary": min(1.0, n / 25),
            "punctuation": min(1.0, n / 10),
            "formality": min(1.0, n / 15),
        }

        return profile

    def get_training_stats(self) -> Dict[str, Any]:
        """Get training statistics for display."""
        examples = self.get_examples(limit=500)
        profile = self.analyze_style(examples)
        curriculum = self.get_curriculum_progress()

        return {
            "total_examples": len(examples),
            "confidence_scores": profile.confidence_scores,
            "curriculum": curriculum,
            "style_summary": {
                "tone": profile.tone,
                "length": f"{profile.avg_message_length:.1f} words avg",
                "emoji": profile.emoji_frequency,
                "formality": profile.formality,
                "punctuation": profile.punctuation_style,
                "capitalization": profile.capitalization,
            },
        }

    def compare_prediction(self, predicted: str, actual: str) -> Dict[str, Any]:
        """Compare a prediction with the actual reply for feedback."""
        pred_words = len(predicted.split())
        actual_words = len(actual.split())
        word_diff = pred_words - actual_words

        return {
            "predicted": predicted,
            "actual": actual,
            "predicted_length": pred_words,
            "actual_length": actual_words,
            "length_difference": f"Julius is {abs(word_diff)} words {'longer' if word_diff > 0 else 'shorter'}",
            "exact_match": predicted.strip().lower() == actual.strip().lower(),
        }
