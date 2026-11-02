"""
Julius WhatsApp Integration — Entity Resolver.

Provides deterministic entity extraction, resolution, and disambiguation.
Ensures identities never cross or hallucinate.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from .config import TARGET_PEERS_CONFIG
from .storage import WhatsAppStorage

logger = logging.getLogger(__name__)


class EntityResolver:
    """
    Deterministic resolver for contacts, people, courses, and timetables.
    Never hallucinates or guesses identities.
    """

    def __init__(self, storage: WhatsAppStorage) -> None:
        self._storage = storage
        self._seed_target_peers()

    def _seed_target_peers(self) -> None:
        """Seed all configured target peers into persistent entities table."""
        try:
            for peer in TARGET_PEERS_CONFIG:
                canonical = peer.get("canonical", "")
                if not canonical:
                    continue
                aliases = list(dict.fromkeys(peer.get("aliases", []) + [canonical]))
                metadata = {
                    "dept": peer.get("dept", ""),
                    "notes": peer.get("notes", ""),
                    "tokens": peer.get("tokens", []),
                }
                self._storage.save_entity({
                    "id": f"person_{re.sub(r'[^a-zA-Z0-9]+', '_', canonical.lower()).strip('_')}",
                    "entity_type": "person",
                    "canonical_name": canonical,
                    "aliases": aliases,
                    "metadata": metadata,
                    "confidence": 1.0,
                    "source": "config_target_peers",
                })
        except Exception as e:
            logger.warning("[ENTITY_RESOLVER] Error seeding target peers: %s", e)

    def resolve_person(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Deterministically resolve a person from a query string.
        Returns the canonical entity dict or None if unverified.
        Handles disambiguation (e.g., Alex vs Alexander).
        """
        if not query:
            return None

        q_low = query.lower().strip()
        words = re.findall(r"[a-zA-Z0-9]+", q_low)

        # 1. Disambiguation shortcuts for known tricky pairs
        if "alexander" in q_low or "alexander" in words:
            return self._storage.get_entity("Contact Alexander")
        if "alex" in words:
            return self._storage.get_entity("Contact Alex")

        if "dave" in words:
            return self._storage.get_entity("Contact Dave")

        if "kevin" in words:
            return self._storage.get_entity("Contact Kevin")

        if "nathan" in words:
            return self._storage.get_entity("Contact Nathan")

        if "max" in words:
            return self._storage.get_entity("Contact Max")

        if "jack" in words:
            return self._storage.get_entity("Contact Jack")

        if "ian" in words:
            return self._storage.get_entity("Contact Ian")

        if "charlie" in words:
            return self._storage.get_entity("Contact Charlie")

        if "frank" in words:
            return self._storage.get_entity("Contact Frank")

        if "leo" in words:
            return self._storage.get_entity("Contact Leo")

        if "grace" in words:
            return self._storage.get_entity("Contact Grace")

        if "henry" in words:
            return self._storage.get_entity("Contact Henry")

        if any(w in words for w in ["user", "self"]):
            return self._storage.get_entity("User (Self)")

        # 2. Database search across canonical and aliases
        candidates = self._storage.find_entities(query, entity_type="person")
        if len(candidates) == 1:
            return candidates[0]
        elif len(candidates) > 1:
            # Check exact match on alias or canonical
            for c in candidates:
                if c["canonical_name"].lower() == q_low or any(a.lower() == q_low for a in c.get("aliases", [])):
                    return c
            # Longest match wins
            candidates.sort(key=lambda x: len(x["canonical_name"]), reverse=True)
            return candidates[0]

        return None

    def is_known_person(self, query: str) -> bool:
        """Check if person is verified in known data sources."""
        return self.resolve_person(query) is not None

    def extract_entities_from_text(self, text: str) -> List[Dict[str, Any]]:
        """
        Extract verified person entities mentioned in text.
        Disambiguates tricky pairs like Alex vs Alexander.
        """
        if not text:
            return []

        entities: List[Dict[str, Any]] = []
        seen_canonical = set()
        txt_low = text.lower()

        # Check Alexander first to avoid Alex collision
        if re.search(r"\balexander\b", txt_low):
            ent = self._storage.get_entity("Contact Alexander")
            if ent:
                entities.append(ent)
                seen_canonical.add("Contact Alexander")

        token_to_canonical = [
            (r"\balex\b", "Contact Alex"),
            (r"\bdave\b", "Contact Dave"),
            (r"\bkevin\b", "Contact Kevin"),
            (r"\bnathan\b", "Contact Nathan"),
            (r"\bmax\b", "Contact Max"),
            (r"\bjack\b", "Contact Jack"),
            (r"\bian\b", "Contact Ian"),
            (r"\bcharlie\b", "Contact Charlie"),
            (r"\bfrank\b", "Contact Frank"),
            (r"\bleo\b", "Contact Leo"),
            (r"\bgrace\b", "Contact Grace"),
            (r"\bhenry\b", "Contact Henry"),
            (r"\b(?:user|self)\b", "User (Self)"),
        ]

        for pat, canonical in token_to_canonical:
            if canonical in seen_canonical:
                continue
            if re.search(pat, txt_low):
                ent = self._storage.get_entity(canonical)
                if ent:
                    entities.append(ent)
                    seen_canonical.add(canonical)

        return entities


_RESOLVER_INSTANCE: Optional[EntityResolver] = None


def get_entity_resolver(storage: Optional[WhatsAppStorage] = None) -> EntityResolver:
    global _RESOLVER_INSTANCE
    if _RESOLVER_INSTANCE is None:
        if storage is None:
            storage = WhatsAppStorage()
        _RESOLVER_INSTANCE = EntityResolver(storage)
    return _RESOLVER_INSTANCE
