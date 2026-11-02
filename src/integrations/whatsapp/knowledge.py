"""
Julius WhatsApp Integration — Evolving Personal Knowledge Engine.

Maintains structured, evidence-based knowledge graphs per contact:
- Status lifecycle: CURRENT, HISTORICAL, SUPERSEDED, UNCERTAIN, PLANNED.
- Contradiction detection and automated superseding of outdated facts.
- Longitudinal learning over time with confidence calibration.
- Explicit correction handling ("No bro, that's not what I meant").
- Structured observable logging ([MEMORY], [KNOWLEDGE_UPDATE]).
"""

from __future__ import annotations

import logging
import re
import time
import uuid
from typing import List, Optional, Tuple

from .models import MemoryCategory, MemoryStatus, PersonMemory, WhatsAppMessage
from .storage import WhatsAppStorage

logger = logging.getLogger(__name__)


# ── Pattern matchers for candidate fact extraction ────────────────────────────

_LOCATION_CURRENT_PATTERNS = [
    (r"\b(?:i\s+live\s+in|i(?:'m|\s+am)\s+living\s+in|i\s+stay\s+in|i(?:'m|\s+am)\s+staying\s+in|i\s+reside\s+in)\s+([A-Za-z\s]+?)(?:\.|\,|$|\s+now|\s+with)", "residence_city"),
    (r"\b(?:my\s+hometown\s+is|i(?:'m|\s+am)\s+from)\s+([A-Za-z\s]+?)(?:\.|\,|$)", "hometown"),
]

_LOCATION_UPDATE_PATTERNS = [
    (r"\b(?:i\s+moved\s+to|shifted\s+to|relocated\s+to)\s+([A-Za-z\s]+?)(?:\.|\,|$|\s+yesterday|\s+recently|\s+now)", "residence_city"),
    (r"\b(?:changed\s+(?:my\s+)?(?:house|room|hostel|place)|now\s+staying\s+at|now\s+in)\s+([A-Za-z\s]+?)(?:\.|\,|$)", "residence_city"),
]

_LOCATION_PLANNED_PATTERNS = [
    (r"\b(?:thinking\s+of\s+moving\s+to|planning\s+to\s+move\s+to|might\s+shift\s+to|will\s+move\s+to)\s+([A-Za-z\s]+?)(?:\.|\,|$)", "residence_city"),
]

_EDUCATION_PATTERNS = [
    (r"\b(?:i\s+study\s+at|i(?:'m|\s+am)\s+studying\s+at|i\s+joined)\s+([A-Za-z0-9\s]+?)(?:\.|\,|$)", "college"),
    (r"\b(?:my\s+branch\s+is|my\s+dept\s+is|i(?:'m|\s+am)\s+in)\s+([A-Za-z0-9\s]+?)(?:\.|\,|$|\s+batch|\s+dept)", "department"),
    (r"\b(?:room\s*(?:no\.?|number)?\s*([0-9]{3}))\b", "room_number"),
]

_PREFERENCE_PATTERNS = [
    (r"\b(?:i\s+love|i\s+really\s+like|my\s+favorite\s+is)\s+([A-Za-z0-9\s]+?)(?:\.|\,|$)", "favorite"),
    (r"\b(?:i\s+hate|i\s+dislike|i\s+don'?t\s+like)\s+([A-Za-z0-9\s]+?)(?:\.|\,|$)", "dislike"),
]

_PROJECT_PATTERNS = [
    (r"\b(?:i(?:'m|\s+am)\s+working\s+on|building|developing|coding)\s+([A-Za-z0-9\s\-_]+?)(?:\.|\,|$|\s+project)", "active_project"),
]

_CORRECTION_PATTERNS = [
    r"\b(?:no\s+bro|not\s+really|that(?:'s|\s+is)\s+not\s+what\s+i\s+meant|actually\s+no|i\s+meant|not\s+true)\b",
]
_COMPILED_CORRECTIONS = [re.compile(p, re.IGNORECASE) for p in _CORRECTION_PATTERNS]


class PersonalKnowledgeEngine:
    """Manages the evolving knowledge graph for all contacts."""

    def __init__(self, storage: WhatsAppStorage) -> None:
        self._storage = storage

    def extract_and_update_knowledge(
        self, message: WhatsAppMessage
    ) -> List[PersonMemory]:
        """Analyze an incoming message turn, extract candidate observations,
        resolve contradictions against existing facts, and persist updates.

        Returns list of created or updated PersonMemory records.
        """
        text = message.text.strip()
        chat_name = message.chat_name
        if not text or len(text) < 3:
            return []

        candidates = self._extract_candidates(text, message.id)
        if not candidates:
            return []

        updated_memories: List[PersonMemory] = []

        for candidate in candidates:
            persisted = self._process_candidate_memory(chat_name, candidate)
            if persisted:
                updated_memories.append(persisted)

        return updated_memories

    def _extract_candidates(self, text: str, message_id: str) -> List[PersonMemory]:
        """Extract candidate facts from raw text using calibrated confidence."""
        candidates: List[PersonMemory] = []

        # 1. Location updates (explicit change: e.g. "I moved to Bangalore")
        for pat, subj in _LOCATION_UPDATE_PATTERNS:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                val = m.group(1).strip()
                if len(val) > 2 and len(val.split()) <= 4:
                    candidates.append(
                        PersonMemory(
                            category=MemoryCategory.LOCATION.value,
                            subject=subj,
                            fact=f"Resides in {val.title()}",
                            status=MemoryStatus.CURRENT.value,
                            confidence=0.95,
                            evidence_text=m.group(0),
                            source_message_id=message_id,
                        )
                    )

        # 2. Planned locations (e.g. "I'm thinking of moving to Bangalore")
        for pat, subj in _LOCATION_PLANNED_PATTERNS:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                val = m.group(1).strip()
                if len(val) > 2 and len(val.split()) <= 4:
                    candidates.append(
                        PersonMemory(
                            category=MemoryCategory.LOCATION.value,
                            subject=subj,
                            fact=f"Planning or considering moving to {val.title()}",
                            status=MemoryStatus.PLANNED.value,
                            confidence=0.6,
                            evidence_text=m.group(0),
                            source_message_id=message_id,
                        )
                    )

        # 3. Current locations (e.g. "I live in Chennai")
        for pat, subj in _LOCATION_CURRENT_PATTERNS:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                val = m.group(1).strip()
                if len(val) > 2 and len(val.split()) <= 4:
                    candidates.append(
                        PersonMemory(
                            category=MemoryCategory.LOCATION.value,
                            subject=subj,
                            fact=f"Lives in {val.title()}" if subj == "residence_city" else f"Hometown is {val.title()}",
                            status=MemoryStatus.CURRENT.value,
                            confidence=0.9,
                            evidence_text=m.group(0),
                            source_message_id=message_id,
                        )
                    )

        # 4. Education / College / Department
        for pat, subj in _EDUCATION_PATTERNS:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                val = m.group(1).strip()
                if len(val) >= 2 and len(val.split()) <= 5:
                    fact_str = f"Studies at {val.upper() if len(val) <= 4 else val.title()}"
                    if subj == "department":
                        fact_str = f"Department is {val.title()}"
                    elif subj == "room_number":
                        fact_str = f"Hostel Room {val}"

                    candidates.append(
                        PersonMemory(
                            category=MemoryCategory.EDUCATION.value,
                            subject=subj,
                            fact=fact_str,
                            status=MemoryStatus.CURRENT.value,
                            confidence=0.92,
                            evidence_text=m.group(0),
                            source_message_id=message_id,
                        )
                    )

        # 5. Preferences / Likes & Dislikes
        for pat, subj in _PREFERENCE_PATTERNS:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                val = m.group(1).strip()
                if len(val) >= 2 and len(val.split()) <= 6:
                    candidates.append(
                        PersonMemory(
                            category=MemoryCategory.PREFERENCE.value,
                            subject=f"{subj}_{val.lower().replace(' ', '_')[:20]}",
                            fact=f"{'Likes' if subj == 'favorite' else 'Dislikes'} {val.lower()}",
                            status=MemoryStatus.CURRENT.value,
                            confidence=0.85,
                            evidence_text=m.group(0),
                            source_message_id=message_id,
                        )
                    )

        # 6. Projects & Tech Activities
        for pat, subj in _PROJECT_PATTERNS:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                val = m.group(1).strip()
                if len(val) >= 2 and len(val.split()) <= 5:
                    candidates.append(
                        PersonMemory(
                            category=MemoryCategory.PROJECT.value,
                            subject=subj,
                            fact=f"Working on {val.title()} project",
                            status=MemoryStatus.CURRENT.value,
                            confidence=0.88,
                            evidence_text=m.group(0),
                            source_message_id=message_id,
                        )
                    )

        return candidates

    def _process_candidate_memory(
        self, chat_name: str, candidate: PersonMemory
    ) -> Optional[PersonMemory]:
        """Check for conflicts with existing memory, supersede old facts if needed,
        and save the candidate to persistent storage."""
        candidate.chat_name = chat_name
        now = time.time()

        # Find existing active memory with matching category and subject
        existing = self._storage.find_conflicting_memory(
            chat_name=chat_name,
            category=candidate.category,
            subject=candidate.subject,
        )

        if existing:
            # Check if this is an identical confirmation
            if existing.fact.lower().strip() == candidate.fact.lower().strip():
                # Reconfirm: increase confidence slightly and update timestamp
                existing.confidence = min(0.99, existing.confidence + 0.05)
                existing.updated_at = now
                self._storage.save_person_memory(existing)
                logger.info(
                    "[MEMORY] Person: %s | Reconfirmed existing fact: '%s' (conf=%.2f)",
                    chat_name,
                    existing.fact,
                    existing.confidence,
                )
                return existing

            # Conflicting / differing information!
            if candidate.status == MemoryStatus.PLANNED.value:
                # A planned future state does NOT supersede the current reality yet!
                self._storage.save_person_memory(candidate)
                logger.info(
                    "[MEMORY] Person: %s | Added planned fact '%s' alongside current '%s'",
                    chat_name,
                    candidate.fact,
                    existing.fact,
                )
                return candidate

            # Supersede old fact: mark as SUPERSEDED or HISTORICAL
            self._storage.supersede_person_memory(
                old_memory_id=existing.id,
                new_memory_id=candidate.id,
                new_status=MemoryStatus.SUPERSEDED.value,
            )

            # Insert new fact as CURRENT
            candidate.valid_from = now
            self._storage.save_person_memory(candidate)

            logger.info(
                "[KNOWLEDGE_UPDATE] Person: %s | Superseded old fact: '%s' (id=%s) -> New current: '%s' (conf=%.2f, evidence='%s')",
                chat_name,
                existing.fact,
                existing.id[:8],
                candidate.fact,
                candidate.confidence,
                candidate.evidence_text,
            )
            return candidate

        else:
            # First time seeing this fact
            self._storage.save_person_memory(candidate)
            logger.info(
                "[MEMORY] Person: %s | Learned new fact: '%s' [category=%s, status=%s, conf=%.2f]",
                chat_name,
                candidate.fact,
                candidate.category,
                candidate.status,
                candidate.confidence,
            )
            return candidate

    def get_contextual_memories(
        self, chat_name: str, incoming_query: str, limit: int = 6
    ) -> List[PersonMemory]:
        """Retrieve the most relevant, non-superseded memories for a contact."""
        return self._storage.search_relevant_memories(
            chat_name=chat_name,
            query=incoming_query,
            limit=limit,
        )

    def is_user_correction(self, text: str) -> bool:
        """Detect whether the incoming message is correcting a previous statement."""
        clean = text.lower()
        for pat in _COMPILED_CORRECTIONS:
            if pat.search(clean):
                return True
        return False
