"""
Julius WhatsApp Integration — Configuration.

Loads WhatsApp settings from environment variables and provides
sensible defaults. Per-chat configs are stored in SQLite via storage.py.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .models import ChatMode


@dataclass
class WhatsAppConfig:
    """Global WhatsApp integration configuration."""

    # ── Master toggle ─────────────────────────────────────────────
    enabled: bool = False

    # ── Default policies ──────────────────────────────────────────
    default_mode: ChatMode = ChatMode.AUTO
    unknown_chats_mode: ChatMode = ChatMode.OFF

    # ── Auto-start ────────────────────────────────────────────────
    auto_start: bool = True  # start WhatsApp when Julius server starts

    # ── Browser ───────────────────────────────────────────────────
    profile_dir: str = field(
        default_factory=lambda: str(Path.home() / ".julius" / "whatsapp_profile")
    )
    headless: bool = True  # run WhatsApp browser headless on server
    browser_timeout: int = 30  # seconds to wait for browser operations

    # ── Rate limiting ─────────────────────────────────────────────
    max_auto_replies_per_chat_per_hour: int = 120
    max_auto_replies_global_per_hour: int = 500

    # ── Training ──────────────────────────────────────────────────
    training_enabled: bool = True
    min_training_examples_for_auto: int = 0  # 0 to allow instant auto mode without delay

    # ── Safety ────────────────────────────────────────────────────
    require_approval_for_low_confidence: bool = True
    require_approval_for_commitments: bool = True
    require_approval_for_financial: bool = True

    # ── Response (zero delay for instant response) ─────────────────
    typing_delay_short_min: float = 0.0  # instant reply
    typing_delay_short_max: float = 0.0
    typing_delay_medium_min: float = 0.0
    typing_delay_medium_max: float = 0.0
    typing_delay_long_min: float = 0.0
    typing_delay_long_max: float = 0.0

    # ── Context ───────────────────────────────────────────────────
    default_context_window: int = 20  # recent messages to include
    max_context_window: int = 50

    # ── Watchdog ──────────────────────────────────────────────────
    watchdog_interval: int = 30  # seconds between health checks
    max_retry_backoff: int = 300  # 5 minutes maximum backoff

    # ── Paths ─────────────────────────────────────────────────────
    data_dir: str = field(
        default_factory=lambda: str(Path.home() / ".julius")
    )

    # ── LLM Provider ──────────────────────────────────────────────
    llm_provider: Optional[str] = None  # use Julius's active provider if None
    llm_profile_dir: str = field(
        default_factory=lambda: str(Path.home() / ".julius" / "whatsapp_llm_profile")
    )
    llm_timeout: int = 90

    def __post_init__(self) -> None:
        Path(self.profile_dir).mkdir(parents=True, exist_ok=True)
        # Restrict profile directory permissions
        try:
            os.chmod(self.profile_dir, 0o700)
        except OSError:
            pass

    @classmethod
    def from_env(cls) -> "WhatsAppConfig":
        """Load configuration from environment variables."""
        def _bool(key: str, default: bool) -> bool:
            val = os.getenv(key, str(default)).lower()
            return val in ("true", "1", "yes")

        def _int(key: str, default: int) -> int:
            try:
                return int(os.getenv(key, str(default)))
            except (ValueError, TypeError):
                return default

        def _float(key: str, default: float) -> float:
            try:
                return float(os.getenv(key, str(default)))
            except (ValueError, TypeError):
                return default

        return cls(
            enabled=_bool("WHATSAPP_ENABLED", False),
            default_mode=ChatMode(os.getenv("WHATSAPP_DEFAULT_MODE", "auto")),
            unknown_chats_mode=ChatMode(os.getenv("WHATSAPP_UNKNOWN_CHATS_MODE", "off")),
            auto_start=_bool("WHATSAPP_AUTO_START", True),
            profile_dir=os.getenv(
                "WHATSAPP_PROFILE_DIR",
                str(Path.home() / ".julius" / "whatsapp_profile"),
            ),
            headless=_bool("WHATSAPP_HEADLESS", True),
            browser_timeout=_int("WHATSAPP_BROWSER_TIMEOUT", 30),
            max_auto_replies_per_chat_per_hour=_int("WHATSAPP_MAX_REPLIES_PER_CHAT_HOUR", 120),
            max_auto_replies_global_per_hour=_int("WHATSAPP_MAX_REPLIES_GLOBAL_HOUR", 500),
            training_enabled=_bool("WHATSAPP_TRAINING_ENABLED", True),
            min_training_examples_for_auto=_int("WHATSAPP_MIN_TRAINING_EXAMPLES", 0),
            require_approval_for_low_confidence=_bool("WHATSAPP_REQUIRE_APPROVAL_LOW_CONF", False),
            require_approval_for_commitments=_bool("WHATSAPP_REQUIRE_APPROVAL_COMMITMENTS", True),
            require_approval_for_financial=_bool("WHATSAPP_REQUIRE_APPROVAL_FINANCIAL", True),
            typing_delay_short_min=_float("WHATSAPP_TYPING_DELAY_SHORT_MIN", 0.0),
            typing_delay_short_max=_float("WHATSAPP_TYPING_DELAY_SHORT_MAX", 0.0),
            typing_delay_medium_min=_float("WHATSAPP_TYPING_DELAY_MEDIUM_MIN", 0.0),
            typing_delay_medium_max=_float("WHATSAPP_TYPING_DELAY_MEDIUM_MAX", 0.0),
            typing_delay_long_min=_float("WHATSAPP_TYPING_DELAY_LONG_MIN", 0.0),
            typing_delay_long_max=_float("WHATSAPP_TYPING_DELAY_LONG_MAX", 0.0),
            watchdog_interval=_int("WHATSAPP_WATCHDOG_INTERVAL", 30),
            max_retry_backoff=_int("WHATSAPP_MAX_RETRY_BACKOFF", 300),
            llm_provider=os.getenv("WHATSAPP_LLM_PROVIDER"),
            llm_profile_dir=os.getenv(
                "WHATSAPP_LLM_PROFILE_DIR",
                str(Path.home() / ".julius" / "whatsapp_llm_profile"),
            ),
            llm_timeout=_int("WHATSAPP_LLM_TIMEOUT", 90),
        )


TARGET_PEERS_CONFIG: list[dict] = [
    {
        "canonical": "Contact Alex",
        "aliases": ["Alex", "Contact Alex"],
        "tokens": ["alex"],
        "dept": "Engineering",
        "notes": "Colleague in Engineering Team (Room 205).",
    },
    {
        "canonical": "Contact Alexander",
        "aliases": ["Alexander", "Contact Alexander"],
        "tokens": ["alexander"],
        "dept": "Product",
        "notes": "Collaborator in Product Team (distinct person from Alex).",
    },
    {
        "canonical": "Contact Charlie",
        "aliases": ["Charlie", "Contact Charlie"],
        "tokens": ["charlie"],
        "dept": "Operations",
        "notes": "Teammate in Operations (Room 004).",
    },
    {
        "canonical": "Contact Dave",
        "aliases": ["Dave", "Contact Dave"],
        "tokens": ["dave"],
        "dept": "Design",
        "notes": "Teammate in Design (Room 101).",
    },
    {
        "canonical": "Contact Eve",
        "aliases": ["Eve", "Contact Eve"],
        "tokens": ["eve"],
        "dept": "Operations",
        "notes": "Collaborator in Operations (Room 004).",
    },
    {
        "canonical": "Contact Frank",
        "aliases": ["Frank", "Contact Frank"],
        "tokens": ["frank"],
        "dept": "Design",
        "notes": "Collaborator in Design (Room 101).",
    },
    {
        "canonical": "Contact Grace",
        "aliases": ["Grace", "Contact Grace"],
        "tokens": ["grace"],
        "dept": "Software",
        "notes": "Collaborator in Software (Room 201).",
    },
    {
        "canonical": "Contact Henry",
        "aliases": ["Henry", "Contact Henry"],
        "tokens": ["henry"],
        "dept": "Hardware",
        "notes": "Collaborator in Hardware (Room 004).",
    },
    {
        "canonical": "Contact Ian",
        "aliases": ["Ian", "Contact Ian"],
        "tokens": ["ian"],
        "dept": "Security",
        "notes": "Collaborator in Security (Room 004).",
    },
    {
        "canonical": "Contact Jack",
        "aliases": ["Jack", "Contact Jack"],
        "tokens": ["jack"],
        "dept": "Infrastructure",
        "notes": "Collaborator in Infrastructure (Room 004).",
    },
    {
        "canonical": "Contact Kevin",
        "aliases": ["Kevin", "Contact Kevin"],
        "tokens": ["kevin"],
        "dept": "Research",
        "notes": "Collaborator in Research (Room 001).",
    },
    {
        "canonical": "Contact Leo",
        "aliases": ["Leo", "Contact Leo"],
        "tokens": ["leo"],
        "dept": "Analytics",
        "notes": "Collaborator in Analytics (Room 004).",
    },
    {
        "canonical": "Contact Max",
        "aliases": ["Max", "Contact Max"],
        "tokens": ["max"],
        "dept": "RPT",
        "notes": "Collaborator in Materials & RPT.",
    },
    {
        "canonical": "Contact Nathan",
        "aliases": ["Nathan", "Contact Nathan"],
        "tokens": ["nathan"],
        "dept": "Support",
        "notes": "Collaborator in Support.",
    },
    {
        "canonical": "User (Self)",
        "aliases": [
            "User (YOU)",
            "User (You)",
            "User(YOU)",
            "User(You)",
            "User",
            "You",
            "Message yourself",
        ],
        "tokens": ["user", "(you)", "message yourself", "self"],
        "dept": "Admin",
        "notes": "User's personal self-note chat for alerts and escalation.",
    },
]

DEFAULT_SELF_CHAT_NAME = "User (Self)"
DAVID_SELF_CHAT_NAME = "User (Self)"

SELF_CHAT_NAMES = [
    "User (Self)",
    "User (YOU)",
    "User (You)",
    "User",
    "You",
    "Self",
    "Message yourself",
]


def is_self_chat(chat_name: str) -> bool:
    """Check if chat_name matches user's self-chat on WhatsApp."""
    if not chat_name:
        return False
    c = chat_name.lower().strip()
    if "(you)" in c or "message yourself" in c:
        return True
    if c in ("you", "self", "user", "me", "david", "david julius") or c.startswith("user") or c.startswith("david"):
        return True
    return any(c == name.lower() for name in SELF_CHAT_NAMES)


def is_target_peer_chat(chat_name: str) -> bool:
    """Check if chat_name matches any priority peer contact.

    Uses EXACT alias matching and WORD-BOUNDARY token matching to prevent
    false positives (e.g. 'alex' must never match 'Alexander').
    """
    if not chat_name:
        return False
    c = chat_name.lower().strip()
    c_words = set(c.split())
    is_alexander_chat = "alexander" in c
    for peer in TARGET_PEERS_CONFIG:
        # Strict disambiguation: Alex != Alexander
        if is_alexander_chat and peer["canonical"] == "Contact Alex":
            continue
        if not is_alexander_chat and peer["canonical"] == "Contact Alexander" and "alexander" not in c:
            continue

        if c == peer["canonical"].lower().strip():
            return True
        for alias in peer["aliases"]:
            if c == alias.lower().strip():
                return True
        # Word-boundary token matching: token must appear as a complete word
        for tok in peer["tokens"]:
            tok_words = tok.lower().split()
            if all(tw in c_words for tw in tok_words):
                return True
    return False


def get_canonical_target_peer_name(chat_name: str) -> Optional[str]:
    """Resolve any alias or token to the canonical contact name.

    Uses EXACT alias matching and WORD-BOUNDARY token matching.
    Strictly keeps Alex and Alexander separate.
    """
    if not chat_name:
        return None
    c = chat_name.lower().strip()
    c_words = set(c.split())
    is_alexander_chat = "alexander" in c
    for peer in TARGET_PEERS_CONFIG:
        if is_alexander_chat and peer["canonical"] == "Contact Alex":
            continue
        if not is_alexander_chat and peer["canonical"] == "Contact Alexander" and "alexander" not in c:
            continue

        if c == peer["canonical"].lower().strip():
            return peer["canonical"]
        for alias in peer["aliases"]:
            if c == alias.lower().strip():
                return peer["canonical"]
        for tok in peer["tokens"]:
            tok_words = tok.lower().split()
            if all(tw in c_words for tw in tok_words):
                return peer["canonical"]
    return None


def get_all_target_peer_names() -> list[str]:
    """Return all target peer names and aliases."""
    names: list[str] = []
    for peer in TARGET_PEERS_CONFIG:
        if peer["canonical"] not in names:
            names.append(peer["canonical"])
        for alias in peer["aliases"]:
            if alias not in names:
                names.append(alias)
    return names


