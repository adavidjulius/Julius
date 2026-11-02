"""
Julius WhatsApp Integration — SQLite Persistence Layer.

Stores chat configs, messages, training examples, style profiles,
audit entries, and sent-message records for loop prevention.
Uses the existing ~/.julius/julius.db with WAL mode.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import (
    AuditEntry,
    ChatConfig,
    ChatMode,
    Confidence,
    ContactProfile,
    GroupTrigger,
    SentMessageRecord,
    StyleProfile,
    TrainingExample,
    WhatsAppMessage,
    MessageType,
    ConversationState,
    ConversationStateRecord,
    MemoryCategory,
    MemoryStatus,
    PersonMemory,
    StyleObservation,
)

logger = logging.getLogger(__name__)

_SCHEMA_VERSION = 1

_SCHEMA_SQL = """
-- WhatsApp chat configurations (allowlist)
CREATE TABLE IF NOT EXISTS whatsapp_chats (
    chat_name       TEXT PRIMARY KEY,
    chat_id         TEXT DEFAULT '',
    enabled         INTEGER DEFAULT 1,
    mode            TEXT DEFAULT 'approval',
    persona         TEXT,
    response_style  TEXT,
    auto_reply_delay_min  REAL DEFAULT 1.0,
    auto_reply_delay_max  REAL DEFAULT 8.0,
    allowed_hours_start   INTEGER,
    allowed_hours_end     INTEGER,
    max_messages_per_hour INTEGER DEFAULT 20,
    escalation_policy     TEXT DEFAULT 'approval',
    context_window        INTEGER DEFAULT 20,
    memory_enabled        INTEGER DEFAULT 1,
    group_trigger         TEXT DEFAULT 'when_mentioned',
    mark_as_read          INTEGER DEFAULT 1,
    created_at            REAL,
    updated_at            REAL
);

-- Processed messages (for dedup and context)
CREATE TABLE IF NOT EXISTS whatsapp_messages (
    id              TEXT PRIMARY KEY,
    chat_id         TEXT NOT NULL,
    chat_name       TEXT NOT NULL,
    sender_id       TEXT NOT NULL,
    sender_name     TEXT NOT NULL,
    timestamp       REAL NOT NULL,
    text            TEXT NOT NULL,
    quoted_message_id TEXT,
    quoted_text     TEXT,
    is_group        INTEGER DEFAULT 0,
    is_from_me      INTEGER DEFAULT 0,
    message_type    TEXT DEFAULT 'text',
    dedup_key       TEXT UNIQUE,
    created_at      REAL
);
CREATE INDEX IF NOT EXISTS idx_wa_msg_chat ON whatsapp_messages(chat_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_wa_msg_dedup ON whatsapp_messages(dedup_key);

-- Training examples
CREATE TABLE IF NOT EXISTS whatsapp_training_examples (
    id              TEXT PRIMARY KEY,
    incoming_text   TEXT NOT NULL,
    predicted_reply TEXT DEFAULT '',
    actual_reply    TEXT NOT NULL,
    chat_name       TEXT DEFAULT '',
    chat_id         TEXT DEFAULT '',
    sender_name     TEXT DEFAULT '',
    is_group        INTEGER DEFAULT 0,
    timestamp       REAL,
    is_important    INTEGER DEFAULT 0,
    is_disabled     INTEGER DEFAULT 0
);

-- User style profiles
CREATE TABLE IF NOT EXISTS whatsapp_style_profiles (
    name            TEXT PRIMARY KEY,
    profile_json    TEXT NOT NULL,
    updated_at      REAL
);

-- Audit log
CREATE TABLE IF NOT EXISTS whatsapp_audit_log (
    id              TEXT PRIMARY KEY,
    timestamp       REAL NOT NULL,
    chat_name       TEXT DEFAULT '',
    chat_id         TEXT DEFAULT '',
    sender_name     TEXT DEFAULT '',
    incoming_message_id TEXT,
    mode            TEXT DEFAULT '',
    generated_reply TEXT DEFAULT '',
    final_reply     TEXT DEFAULT '',
    edited_by_user  INTEGER DEFAULT 0,
    sent            INTEGER DEFAULT 0,
    rejected        INTEGER DEFAULT 0,
    approved        INTEGER DEFAULT 0,
    model_provider  TEXT DEFAULT '',
    latency_ms      INTEGER DEFAULT 0,
    reason_code     TEXT DEFAULT '',
    confidence      TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_wa_audit_ts ON whatsapp_audit_log(timestamp);

-- Sent messages (for loop prevention and dedup)
CREATE TABLE IF NOT EXISTS whatsapp_sent_messages (
    message_id      TEXT PRIMARY KEY,
    chat_id         TEXT NOT NULL,
    content_hash    TEXT NOT NULL,
    timestamp       REAL NOT NULL,
    text            TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_wa_sent_chat ON whatsapp_sent_messages(chat_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_wa_sent_hash ON whatsapp_sent_messages(content_hash);

-- Conversation summaries per chat
CREATE TABLE IF NOT EXISTS whatsapp_conversation_summaries (
    chat_id         TEXT PRIMARY KEY,
    summary         TEXT NOT NULL,
    important_facts TEXT DEFAULT '[]',
    ongoing_topics  TEXT DEFAULT '[]',
    pending_questions TEXT DEFAULT '[]',
    relationship_label TEXT DEFAULT '',
    updated_at      REAL
);

-- Track replied incoming messages to guarantee zero duplicate replies
CREATE TABLE IF NOT EXISTS whatsapp_replied_messages (
    dedup_key       TEXT PRIMARY KEY,
    chat_name       TEXT NOT NULL,
    replied_at      REAL NOT NULL
);

-- Pending inquiries waiting for David Julius's direct answer
CREATE TABLE IF NOT EXISTS whatsapp_pending_inquiries (
    id              TEXT PRIMARY KEY,
    friend_chat_name TEXT NOT NULL,
    friend_sender_name TEXT DEFAULT '',
    question        TEXT NOT NULL,
    created_at      REAL NOT NULL,
    status          TEXT DEFAULT 'pending',
    answer          TEXT DEFAULT '',
    answered_at     REAL
);
CREATE INDEX IF NOT EXISTS idx_wa_pending_inq ON whatsapp_pending_inquiries(status, created_at);

-- Rate limiting counters
CREATE TABLE IF NOT EXISTS whatsapp_rate_limits (
    key             TEXT PRIMARY KEY,
    count           INTEGER DEFAULT 0,
    window_start    REAL NOT NULL
);

-- Dynamic evolving contact profiles (learned memory & interconnected social graph)
CREATE TABLE IF NOT EXISTS whatsapp_contact_profiles (
    chat_name       TEXT PRIMARY KEY,
    display_name    TEXT DEFAULT '',
    contact_type    TEXT DEFAULT 'friend',
    tone_style      TEXT DEFAULT 'casual',
    slang_used      TEXT DEFAULT '[]',
    favorite_topics TEXT DEFAULT '[]',
    last_status_update TEXT DEFAULT '',
    interconnected_notes TEXT DEFAULT '',
    important_facts TEXT DEFAULT '[]',
    total_messages_exchanged INTEGER DEFAULT 0,
    updated_at      REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_wa_profiles_name ON whatsapp_contact_profiles(chat_name);

-- Structured evolving person memories
CREATE TABLE IF NOT EXISTS whatsapp_person_memories (
    id                TEXT PRIMARY KEY,
    chat_name         TEXT NOT NULL,
    category          TEXT NOT NULL,
    subject           TEXT NOT NULL,
    fact              TEXT NOT NULL,
    status            TEXT NOT NULL DEFAULT 'current',
    confidence        REAL DEFAULT 0.9,
    evidence_text     TEXT DEFAULT '',
    source_message_id TEXT DEFAULT '',
    valid_from        REAL,
    valid_until       REAL,
    superseded_by     TEXT,
    created_at        REAL NOT NULL,
    updated_at        REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_wa_mem_chat ON whatsapp_person_memories(chat_name, status);
CREATE INDEX IF NOT EXISTS idx_wa_mem_subj ON whatsapp_person_memories(chat_name, category, subject);

-- Conversation state tracking
CREATE TABLE IF NOT EXISTS whatsapp_conversation_states (
    chat_name          TEXT PRIMARY KEY,
    state              TEXT NOT NULL DEFAULT 'NEW',
    previous_state     TEXT DEFAULT '',
    last_message_at    REAL NOT NULL,
    last_sender        TEXT DEFAULT '',
    turn_count         INTEGER DEFAULT 0,
    active_topic       TEXT DEFAULT '',
    termination_phrase TEXT DEFAULT '',
    created_at         REAL NOT NULL,
    updated_at         REAL NOT NULL
);

-- Style observations
CREATE TABLE IF NOT EXISTS whatsapp_style_observations (
    id                 TEXT PRIMARY KEY,
    chat_name          TEXT NOT NULL,
    message_id         TEXT DEFAULT '',
    formality_score    REAL DEFAULT 0.5,
    slang_score        REAL DEFAULT 0.5,
    emoji_count        INTEGER DEFAULT 0,
    avg_word_count     REAL DEFAULT 0.0,
    tamil_english_mix  REAL DEFAULT 0.0,
    humor_score        REAL DEFAULT 0.0,
    observed_at        REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_wa_style_obs ON whatsapp_style_observations(chat_name, observed_at);

-- Schema version tracking
CREATE TABLE IF NOT EXISTS whatsapp_schema_version (
    version         INTEGER PRIMARY KEY
);

-- Structured entities (People, Contacts, Courses, Locations)
CREATE TABLE IF NOT EXISTS whatsapp_entities (
    id              TEXT PRIMARY KEY,
    entity_type     TEXT NOT NULL,
    canonical_name  TEXT NOT NULL,
    aliases         TEXT DEFAULT '[]',
    metadata        TEXT DEFAULT '{}',
    confidence      REAL DEFAULT 1.0,
    source          TEXT DEFAULT 'system',
    created_at      REAL NOT NULL,
    updated_at      REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_wa_ent_type ON whatsapp_entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_wa_ent_name ON whatsapp_entities(canonical_name);

-- Verified media items (Images, Videos, Audios)
CREATE TABLE IF NOT EXISTS whatsapp_media_items (
    media_id        TEXT PRIMARY KEY,
    media_type      TEXT NOT NULL,
    filename        TEXT NOT NULL,
    original_filename TEXT DEFAULT '',
    conversation_id TEXT DEFAULT '',
    message_id      TEXT DEFAULT '',
    sender          TEXT DEFAULT '',
    timestamp       REAL NOT NULL,
    caption         TEXT DEFAULT '',
    entities        TEXT DEFAULT '[]',
    verified        INTEGER DEFAULT 1,
    content_hash    TEXT DEFAULT '',
    storage_path    TEXT NOT NULL,
    thumbnail_path  TEXT DEFAULT '',
    size_bytes      INTEGER DEFAULT 0,
    ocr_text        TEXT DEFAULT '',
    vision_labels   TEXT DEFAULT '[]',
    metadata        TEXT DEFAULT '{}',
    status          TEXT DEFAULT 'VERIFIED',
    created_at      REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_wa_media_type ON whatsapp_media_items(media_type);
CREATE INDEX IF NOT EXISTS idx_wa_media_fname ON whatsapp_media_items(filename);
CREATE INDEX IF NOT EXISTS idx_wa_media_sender ON whatsapp_media_items(sender);

-- Documents & Academic materials
CREATE TABLE IF NOT EXISTS whatsapp_documents (
    document_id     TEXT PRIMARY KEY,
    filename        TEXT NOT NULL,
    original_filename TEXT DEFAULT '',
    doc_type        TEXT DEFAULT 'general',
    owner           TEXT DEFAULT 'David Julius',
    subjects        TEXT DEFAULT '[]',
    semester        INTEGER DEFAULT 1,
    category        TEXT DEFAULT 'academic',
    source_message_id TEXT DEFAULT '',
    created_at      REAL NOT NULL,
    content_hash    TEXT DEFAULT '',
    storage_path    TEXT NOT NULL,
    text_content    TEXT DEFAULT '',
    text_summary    TEXT DEFAULT '',
    verified        INTEGER DEFAULT 1,
    entities        TEXT DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS idx_wa_docs_fname ON whatsapp_documents(filename);
CREATE INDEX IF NOT EXISTS idx_wa_docs_type ON whatsapp_documents(doc_type);

-- Deterministic college timetables
CREATE TABLE IF NOT EXISTS whatsapp_timetables (
    id              TEXT PRIMARY KEY,
    person          TEXT NOT NULL DEFAULT 'David Julius',
    department      TEXT DEFAULT 'IT',
    semester        INTEGER DEFAULT 1,
    day_of_week     TEXT NOT NULL,
    start_time      TEXT NOT NULL,
    end_time        TEXT NOT NULL,
    course_name     TEXT NOT NULL,
    course_code     TEXT DEFAULT '',
    room_location   TEXT DEFAULT '',
    activity_type   TEXT DEFAULT 'class',
    source          TEXT DEFAULT 'verified_schedule',
    confidence      REAL DEFAULT 1.0
);
CREATE INDEX IF NOT EXISTS idx_wa_tt_day ON whatsapp_timetables(person, day_of_week);

-- Granular facts
CREATE TABLE IF NOT EXISTS whatsapp_facts (
    fact_id         TEXT PRIMARY KEY,
    subject         TEXT NOT NULL,
    predicate       TEXT NOT NULL,
    object          TEXT NOT NULL,
    value           TEXT DEFAULT '',
    source_message_id TEXT DEFAULT '',
    confidence      REAL DEFAULT 1.0,
    status          TEXT DEFAULT 'VERIFIED',
    created_at      REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_wa_facts_subj ON whatsapp_facts(subject, predicate);

-- Action receipts
CREATE TABLE IF NOT EXISTS whatsapp_action_receipts (
    action_id           TEXT PRIMARY KEY,
    requested_by        TEXT NOT NULL,
    intent              TEXT NOT NULL,
    target              TEXT NOT NULL,
    arguments           TEXT DEFAULT '{}',
    authorization_status TEXT DEFAULT 'AUTHORIZED',
    execution_status    TEXT NOT NULL,
    result              TEXT DEFAULT '{}',
    whatsapp_message_id TEXT DEFAULT '',
    timestamp           REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_wa_receipt_ts ON whatsapp_action_receipts(timestamp);
CREATE INDEX IF NOT EXISTS idx_wa_receipt_intent ON whatsapp_action_receipts(intent, target);
"""


class WhatsAppStorage:
    """SQLite persistence for WhatsApp integration data."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        if db_path is None:
            db_path = str(Path.home() / ".julius" / "whatsapp.db")
        self._db_path = db_path
        self._lock = threading.Lock()
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=30.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.executescript(_SCHEMA_SQL)
                conn.execute(
                    "INSERT OR REPLACE INTO whatsapp_schema_version (version) VALUES (?)",
                    (_SCHEMA_VERSION,),
                )
                conn.commit()
                logger.info("WhatsApp storage schema initialized (v%d)", _SCHEMA_VERSION)
            except Exception as e:
                logger.error("Failed to initialize WhatsApp schema: %s", e)
                raise
            finally:
                conn.close()

    # ── Chat Configuration ────────────────────────────────────────

    def save_chat_config(self, config: ChatConfig) -> None:
        now = time.time()
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    """INSERT OR REPLACE INTO whatsapp_chats
                       (chat_name, chat_id, enabled, mode, persona, response_style,
                        auto_reply_delay_min, auto_reply_delay_max,
                        allowed_hours_start, allowed_hours_end,
                        max_messages_per_hour, escalation_policy, context_window,
                        memory_enabled, group_trigger, mark_as_read,
                        created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                               COALESCE((SELECT created_at FROM whatsapp_chats WHERE chat_name = ?), ?),
                               ?)""",
                    (
                        config.chat_name, config.chat_id, int(config.enabled),
                        config.mode.value, config.persona, config.response_style,
                        config.auto_reply_delay_min, config.auto_reply_delay_max,
                        config.allowed_hours_start, config.allowed_hours_end,
                        config.max_messages_per_hour, config.escalation_policy,
                        config.context_window, int(config.memory_enabled),
                        config.group_trigger.value, int(config.mark_as_read),
                        config.chat_name, now, now,
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    def get_chat_config(self, chat_name: str) -> Optional[ChatConfig]:
        with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute(
                    "SELECT * FROM whatsapp_chats WHERE chat_name = ? COLLATE NOCASE", (chat_name,)
                ).fetchone()
                if not row:
                    return None
                return self._row_to_chat_config(row)
            finally:
                conn.close()

    def get_all_chat_configs(self) -> List[ChatConfig]:
        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute("SELECT * FROM whatsapp_chats ORDER BY chat_name").fetchall()
                return [self._row_to_chat_config(r) for r in rows]
            finally:
                conn.close()

    def get_enabled_chat_configs(self) -> List[ChatConfig]:
        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    "SELECT * FROM whatsapp_chats WHERE enabled = 1 ORDER BY chat_name"
                ).fetchall()
                return [self._row_to_chat_config(r) for r in rows]
            finally:
                conn.close()

    def delete_chat_config(self, chat_name: str) -> bool:
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.execute(
                    "DELETE FROM whatsapp_chats WHERE chat_name = ?", (chat_name,)
                )
                conn.commit()
                return cursor.rowcount > 0
            finally:
                conn.close()

    def _row_to_chat_config(self, row: sqlite3.Row) -> ChatConfig:
        return ChatConfig(
            chat_name=row["chat_name"],
            chat_id=row["chat_id"] or "",
            enabled=bool(row["enabled"]),
            mode=ChatMode(row["mode"]),
            persona=row["persona"],
            response_style=row["response_style"],
            auto_reply_delay_min=row["auto_reply_delay_min"],
            auto_reply_delay_max=row["auto_reply_delay_max"],
            allowed_hours_start=row["allowed_hours_start"],
            allowed_hours_end=row["allowed_hours_end"],
            max_messages_per_hour=row["max_messages_per_hour"],
            escalation_policy=row["escalation_policy"],
            context_window=row["context_window"],
            memory_enabled=bool(row["memory_enabled"]),
            group_trigger=GroupTrigger(row["group_trigger"]),
            mark_as_read=bool(row["mark_as_read"]),
        )

    # ── Messages ──────────────────────────────────────────────────

    def save_message(self, msg: WhatsAppMessage) -> bool:
        """Save a message. Returns False if duplicate (dedup_key exists)."""
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    """INSERT OR IGNORE INTO whatsapp_messages
                       (id, chat_id, chat_name, sender_id, sender_name,
                        timestamp, text, quoted_message_id, quoted_text,
                        is_group, is_from_me, message_type, dedup_key, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        msg.id, msg.chat_id, msg.chat_name, msg.sender_id,
                        msg.sender_name, msg.timestamp, msg.text,
                        msg.quoted_message_id, msg.quoted_text,
                        int(msg.is_group), int(msg.is_from_me),
                        msg.message_type.value, msg.dedup_key, time.time(),
                    ),
                )
                conn.commit()
                return conn.total_changes > 0
            except sqlite3.IntegrityError:
                return False
            finally:
                conn.close()

    def is_duplicate_message(self, dedup_key: str, within_seconds: Optional[float] = 600.0) -> bool:
        with self._lock:
            conn = self._get_conn()
            try:
                if within_seconds is not None:
                    cutoff = time.time() - within_seconds
                    row = conn.execute(
                        "SELECT 1 FROM whatsapp_messages WHERE dedup_key = ? AND timestamp > ?",
                        (dedup_key, cutoff),
                    ).fetchone()
                else:
                    row = conn.execute(
                        "SELECT 1 FROM whatsapp_messages WHERE dedup_key = ?", (dedup_key,)
                    ).fetchone()
                return row is not None
            finally:
                conn.close()

    def is_message_replied(self, dedup_key: str, within_seconds: Optional[float] = 600.0) -> bool:
        """Check if an incoming message has already been replied to within the sliding window."""
        with self._lock:
            conn = self._get_conn()
            try:
                if within_seconds is not None:
                    cutoff = time.time() - within_seconds
                    row = conn.execute(
                        "SELECT 1 FROM whatsapp_replied_messages WHERE dedup_key = ? AND replied_at > ?",
                        (dedup_key, cutoff),
                    ).fetchone()
                else:
                    row = conn.execute(
                        "SELECT 1 FROM whatsapp_replied_messages WHERE dedup_key = ?", (dedup_key,)
                    ).fetchone()
                return row is not None
            finally:
                conn.close()

    def mark_message_replied(self, dedup_key: str, chat_name: str = "") -> None:
        """Mark an incoming message as replied so it is never re-processed."""
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO whatsapp_replied_messages (dedup_key, chat_name, replied_at) VALUES (?, ?, ?)",
                    (dedup_key, chat_name, time.time()),
                )
                conn.commit()
            finally:
                conn.close()

    def get_recent_messages(self, chat_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    """SELECT * FROM whatsapp_messages
                       WHERE chat_id = ? OR chat_name = ?
                       ORDER BY timestamp DESC LIMIT ?""",
                    (chat_id, chat_id, limit),
                ).fetchall()
                return [dict(r) for r in reversed(rows)]
            finally:
                conn.close()

    # ── Training Examples ─────────────────────────────────────────

    def save_training_example(self, example: TrainingExample) -> None:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    """INSERT OR REPLACE INTO whatsapp_training_examples
                       (id, incoming_text, predicted_reply, actual_reply,
                        chat_name, chat_id, sender_name, is_group,
                        timestamp, is_important, is_disabled)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        example.id, example.incoming_text, example.predicted_reply,
                        example.actual_reply, example.chat_name, example.chat_id,
                        example.sender_name, int(example.is_group),
                        example.timestamp, int(example.is_important),
                        int(example.is_disabled),
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    def get_training_examples(
        self, limit: int = 100, include_disabled: bool = False
    ) -> List[TrainingExample]:
        with self._lock:
            conn = self._get_conn()
            try:
                query = "SELECT * FROM whatsapp_training_examples"
                if not include_disabled:
                    query += " WHERE is_disabled = 0"
                query += " ORDER BY timestamp DESC LIMIT ?"
                rows = conn.execute(query, (limit,)).fetchall()
                return [
                    TrainingExample(
                        id=r["id"],
                        incoming_text=r["incoming_text"],
                        predicted_reply=r["predicted_reply"],
                        actual_reply=r["actual_reply"],
                        chat_name=r["chat_name"],
                        chat_id=r["chat_id"],
                        sender_name=r["sender_name"],
                        is_group=bool(r["is_group"]),
                        timestamp=r["timestamp"],
                        is_important=bool(r["is_important"]),
                        is_disabled=bool(r["is_disabled"]),
                    )
                    for r in rows
                ]
            finally:
                conn.close()

    def get_training_count(self) -> int:
        with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute(
                    "SELECT COUNT(*) as cnt FROM whatsapp_training_examples WHERE is_disabled = 0"
                ).fetchone()
                return row["cnt"] if row else 0
            finally:
                conn.close()

    def delete_training_example(self, example_id: str) -> bool:
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.execute(
                    "DELETE FROM whatsapp_training_examples WHERE id = ?", (example_id,)
                )
                conn.commit()
                return cursor.rowcount > 0
            finally:
                conn.close()

    # ── Style Profiles ────────────────────────────────────────────

    def save_style_profile(self, profile: StyleProfile) -> None:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    """INSERT OR REPLACE INTO whatsapp_style_profiles
                       (name, profile_json, updated_at) VALUES (?, ?, ?)""",
                    (profile.name, json.dumps(profile.to_dict()), time.time()),
                )
                conn.commit()
            finally:
                conn.close()

    def get_style_profile(self, name: str = "default") -> Optional[StyleProfile]:
        with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute(
                    "SELECT profile_json FROM whatsapp_style_profiles WHERE name = ?",
                    (name,),
                ).fetchone()
                if not row:
                    return None
                return StyleProfile.from_dict(json.loads(row["profile_json"]))
            finally:
                conn.close()

    # ── Audit Log ─────────────────────────────────────────────────

    def save_audit_entry(self, entry: AuditEntry) -> None:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    """INSERT INTO whatsapp_audit_log
                       (id, timestamp, chat_name, chat_id, sender_name,
                        incoming_message_id, mode, generated_reply, final_reply,
                        edited_by_user, sent, rejected, approved,
                        model_provider, latency_ms, reason_code, confidence)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        entry.id, entry.timestamp, entry.chat_name, entry.chat_id,
                        entry.sender_name, entry.incoming_message_id, entry.mode,
                        entry.generated_reply, entry.final_reply,
                        int(entry.edited_by_user), int(entry.sent),
                        int(entry.rejected), int(entry.approved),
                        entry.model_provider, entry.latency_ms,
                        entry.reason_code, entry.confidence,
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    def get_audit_log(self, limit: int = 50, chat_name: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self._get_conn()
            try:
                if chat_name:
                    rows = conn.execute(
                        "SELECT * FROM whatsapp_audit_log WHERE chat_name = ? ORDER BY timestamp DESC LIMIT ?",
                        (chat_name, limit),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM whatsapp_audit_log ORDER BY timestamp DESC LIMIT ?",
                        (limit,),
                    ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    def get_audit_entries(self, limit: int = 50, chat_name: Optional[str] = None) -> List[AuditEntry]:
        """Fetch audit log as AuditEntry dataclass instances."""
        dict_rows = self.get_audit_log(limit=limit, chat_name=chat_name)
        entries = []
        for r in dict_rows:
            entries.append(AuditEntry(
                id=r.get("id", ""),
                timestamp=r.get("timestamp", 0.0),
                chat_name=r.get("chat_name", ""),
                chat_id=r.get("chat_id", ""),
                sender_name=r.get("sender_name", ""),
                incoming_message_id=r.get("incoming_message_id"),
                mode=r.get("mode", ""),
                generated_reply=r.get("generated_reply", ""),
                final_reply=r.get("final_reply", ""),
                edited_by_user=bool(r.get("edited_by_user", 0)),
                sent=bool(r.get("sent", 0)),
                rejected=bool(r.get("rejected", 0)),
                approved=bool(r.get("approved", 0)),
                model_provider=r.get("model_provider", ""),
                latency_ms=int(r.get("latency_ms", 0)),
                reason_code=r.get("reason_code", ""),
                confidence=r.get("confidence", ""),
            ))
        return entries

    # ── Sent Messages (Loop Prevention) ───────────────────────────

    def record_sent_message(self, record: SentMessageRecord) -> None:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    """INSERT OR REPLACE INTO whatsapp_sent_messages
                       (message_id, chat_id, content_hash, timestamp, text)
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        record.message_id, record.chat_id,
                        record.content_hash, record.timestamp, record.text,
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    def is_own_message(self, chat_id: str, content_hash: str, window_seconds: float = 60.0) -> bool:
        """Check if a message was recently sent by us (loop prevention)."""
        cutoff = time.time() - window_seconds
        with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute(
                    """SELECT 1 FROM whatsapp_sent_messages
                       WHERE chat_id = ? AND content_hash = ? AND timestamp > ?""",
                    (chat_id, content_hash, cutoff),
                ).fetchone()
                return row is not None
            finally:
                conn.close()

    def is_recently_sent_by_me(self, chat_id: str, text: str, window_seconds: float = 60.0) -> bool:
        """Convenience method using message text directly."""
        content_hash = SentMessageRecord.compute_hash(text)
        return self.is_own_message(chat_id, content_hash, window_seconds=window_seconds)

    # ── Conversation Summaries ────────────────────────────────────

    def save_conversation_summary(
        self,
        chat_id: str,
        summary: str,
        important_facts: Optional[List[str]] = None,
        ongoing_topics: Optional[List[str]] = None,
        pending_questions: Optional[List[str]] = None,
        relationship_label: str = "",
    ) -> None:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    """INSERT OR REPLACE INTO whatsapp_conversation_summaries
                       (chat_id, summary, important_facts, ongoing_topics,
                        pending_questions, relationship_label, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        chat_id, summary,
                        json.dumps(important_facts or []),
                        json.dumps(ongoing_topics or []),
                        json.dumps(pending_questions or []),
                        relationship_label, time.time(),
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    def get_conversation_summary(self, chat_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            conn = self._get_conn()
            try:
                # 1. Exact match
                row = conn.execute(
                    "SELECT * FROM whatsapp_conversation_summaries WHERE chat_id = ?",
                    (chat_id,),
                ).fetchone()
                # 2. Case-insensitive or normalized match (e.g. chat_mit_chandhru)
                if not row:
                    normalized = f"chat_{chat_id.lower().replace(' ', '_')}"
                    row = conn.execute(
                        "SELECT * FROM whatsapp_conversation_summaries WHERE chat_id = ? OR LOWER(chat_id) = LOWER(?)",
                        (normalized, chat_id),
                    ).fetchone()
                # 3. Substring / LIKE match
                if not row and len(chat_id.strip()) >= 3:
                    clean_id = chat_id.replace("chat_", "").strip()
                    row = conn.execute(
                        "SELECT * FROM whatsapp_conversation_summaries WHERE chat_id LIKE ? OR LOWER(relationship_label) LIKE ? LIMIT 1",
                        (f"%{clean_id}%", f"%{clean_id.lower()}%"),
                    ).fetchone()

                if not row:
                    return None
                return {
                    "chat_id": row["chat_id"],
                    "summary": row["summary"],
                    "important_facts": json.loads(row["important_facts"]),
                    "ongoing_topics": json.loads(row["ongoing_topics"]),
                    "pending_questions": json.loads(row["pending_questions"]),
                    "relationship_label": row["relationship_label"],
                    "updated_at": row["updated_at"],
                }
            finally:
                conn.close()

    def clear_conversation_memory(self, chat_id: str) -> None:
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "DELETE FROM whatsapp_conversation_summaries WHERE chat_id = ?",
                    (chat_id,),
                )
                conn.commit()
            finally:
                conn.close()

    # ── Rate Limiting ─────────────────────────────────────────────

    def check_rate_limit(self, key: str, max_count: int, window_seconds: float = 3600.0) -> bool:
        """Returns True if under the limit, False if rate-limited."""
        now = time.time()
        with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute(
                    "SELECT count, window_start FROM whatsapp_rate_limits WHERE key = ?",
                    (key,),
                ).fetchone()
                if row is None or (now - row["window_start"]) > window_seconds:
                    conn.execute(
                        "INSERT OR REPLACE INTO whatsapp_rate_limits (key, count, window_start) VALUES (?, 1, ?)",
                        (key, now),
                    )
                    conn.commit()
                    return True
                if row["count"] >= max_count:
                    return False
                conn.execute(
                    "UPDATE whatsapp_rate_limits SET count = count + 1 WHERE key = ?",
                    (key,),
                )
                conn.commit()
                return True
            finally:
                conn.close()

    # ── Pending Inquiries (Human-in-the-Loop) ──────────────────────

    def add_pending_inquiry(
        self,
        friend_chat_name: str,
        friend_sender_name: str,
        question: str,
    ) -> str:
        """Record an unknown question that needs David Julius's direct input."""
        inquiry_id = str(uuid.uuid4())[:8]
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    """INSERT INTO whatsapp_pending_inquiries
                       (id, friend_chat_name, friend_sender_name, question, created_at, status)
                       VALUES (?, ?, ?, ?, ?, 'pending')""",
                    (inquiry_id, friend_chat_name, friend_sender_name, question, time.time()),
                )
                conn.commit()
                return inquiry_id
            finally:
                conn.close()

    def get_latest_pending_inquiry(self) -> Optional[Dict[str, Any]]:
        """Retrieve the most recent unresolved inquiry waiting for David's answer."""
        with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute(
                    """SELECT * FROM whatsapp_pending_inquiries
                       WHERE status = 'pending'
                       ORDER BY created_at DESC LIMIT 1"""
                ).fetchone()
                return dict(row) if row else None
            finally:
                conn.close()

    def resolve_pending_inquiry(self, inquiry_id: str, answer: str) -> None:
        """Mark an inquiry as answered and record David's answer."""
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    """UPDATE whatsapp_pending_inquiries
                       SET status = 'answered', answer = ?, answered_at = ?
                       WHERE id = ?""",
                    (answer, time.time(), inquiry_id),
                )
                conn.commit()
            finally:
                conn.close()

    def get_pending_inquiries(self, limit: int = 10) -> List[Dict[str, Any]]:
        """List active or recent inquiries."""
        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    """SELECT * FROM whatsapp_pending_inquiries
                       ORDER BY created_at DESC LIMIT ?""",
                    (limit,),
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    # ── Dynamic Contact Profile & Social Graph Persistence ────────────────────

    def save_contact_profile(self, profile: ContactProfile) -> None:
        """Create or update a dynamic contact memory profile."""
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    """INSERT INTO whatsapp_contact_profiles
                       (chat_name, display_name, contact_type, tone_style, slang_used,
                        favorite_topics, last_status_update, interconnected_notes,
                        important_facts, total_messages_exchanged, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(chat_name) DO UPDATE SET
                           display_name = excluded.display_name,
                           contact_type = excluded.contact_type,
                           tone_style = excluded.tone_style,
                           slang_used = excluded.slang_used,
                           favorite_topics = excluded.favorite_topics,
                           last_status_update = excluded.last_status_update,
                           interconnected_notes = excluded.interconnected_notes,
                           important_facts = excluded.important_facts,
                           total_messages_exchanged = excluded.total_messages_exchanged,
                           updated_at = excluded.updated_at""",
                    (
                        profile.chat_name,
                        profile.display_name,
                        profile.contact_type,
                        profile.tone_style,
                        json.dumps(profile.slang_used),
                        json.dumps(profile.favorite_topics),
                        profile.last_status_update,
                        profile.interconnected_notes,
                        json.dumps(profile.important_facts),
                        profile.total_messages_exchanged,
                        profile.updated_at or time.time(),
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    def get_contact_profile(self, chat_name: str) -> Optional[ContactProfile]:
        """Fetch dynamic contact profile by chat name (with case-insensitive / token fallback)."""
        clean_name = chat_name.strip()
        with self._lock:
            conn = self._get_conn()
            try:
                # Direct match
                row = conn.execute(
                    """SELECT * FROM whatsapp_contact_profiles
                       WHERE LOWER(chat_name) = LOWER(?)""",
                    (clean_name,),
                ).fetchone()

                if not row:
                    # Token search fallback
                    tokens = [t for t in clean_name.lower().split() if len(t) >= 4 and t not in ("mit", "the", "dept", "it", "ece")]
                    for tok in tokens:
                        row = conn.execute(
                            """SELECT * FROM whatsapp_contact_profiles
                               WHERE LOWER(chat_name) LIKE ? OR LOWER(display_name) LIKE ?
                               LIMIT 1""",
                            (f"%{tok}%", f"%{tok}%"),
                        ).fetchone()
                        if row:
                            break

                if not row:
                    return None

                d = dict(row)
                return ContactProfile(
                    chat_name=d["chat_name"],
                    display_name=d.get("display_name", ""),
                    contact_type=d.get("contact_type", "friend"),
                    tone_style=d.get("tone_style", "casual"),
                    slang_used=json.loads(d.get("slang_used") or "[]"),
                    favorite_topics=json.loads(d.get("favorite_topics") or "[]"),
                    last_status_update=d.get("last_status_update", ""),
                    interconnected_notes=d.get("interconnected_notes", ""),
                    important_facts=json.loads(d.get("important_facts") or "[]"),
                    total_messages_exchanged=d.get("total_messages_exchanged", 0),
                    updated_at=d.get("updated_at", 0.0),
                )
            finally:
                conn.close()

    def list_contact_profiles(self) -> List[ContactProfile]:
        """List all tracked contact profiles."""
        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    """SELECT * FROM whatsapp_contact_profiles ORDER BY updated_at DESC"""
                ).fetchall()
                profiles = []
                for row in rows:
                    d = dict(row)
                    profiles.append(
                        ContactProfile(
                            chat_name=d["chat_name"],
                            display_name=d.get("display_name", ""),
                            contact_type=d.get("contact_type", "friend"),
                            tone_style=d.get("tone_style", "casual"),
                            slang_used=json.loads(d.get("slang_used") or "[]"),
                            favorite_topics=json.loads(d.get("favorite_topics") or "[]"),
                            last_status_update=d.get("last_status_update", ""),
                            interconnected_notes=d.get("interconnected_notes", ""),
                            important_facts=json.loads(d.get("important_facts") or "[]"),
                            total_messages_exchanged=d.get("total_messages_exchanged", 0),
                            updated_at=d.get("updated_at", 0.0),
                        )
                    )
                return profiles
            finally:
                conn.close()

    def find_peer_status(self, peer_query: str) -> Optional[Dict[str, str]]:
        """
        Cross-contact search: Find safe status updates about a mutual peer.
        Useful when Friend A asks about Friend B (e.g. 'Where is Gova?').
        """
        q = peer_query.lower().strip()
        tokens = [t for t in q.split() if len(t) >= 4 and t not in ("mit", "the", "dept", "it", "ece", "where", "what", "with")]
        if not tokens:
            tokens = [q]

        with self._lock:
            conn = self._get_conn()
            try:
                for tok in tokens:
                    row = conn.execute(
                        """SELECT chat_name, display_name, last_status_update, interconnected_notes, updated_at
                           FROM whatsapp_contact_profiles
                           WHERE (LOWER(chat_name) LIKE ? OR LOWER(display_name) LIKE ?)
                             AND (last_status_update != '' OR interconnected_notes != '')
                           ORDER BY updated_at DESC LIMIT 1""",
                        (f"%{tok}%", f"%{tok}%"),
                    ).fetchone()
                    if row:
                        d = dict(row)
                        return {
                            "peer_name": d.get("display_name") or d.get("chat_name"),
                            "status": d.get("last_status_update") or "",
                            "notes": d.get("interconnected_notes") or "",
                            "updated_at": d.get("updated_at", 0.0),
                        }
                return None
            finally:
                conn.close()

    # ── Evolving Person Memories ──────────────────────────────────

    def save_person_memory(self, memory: PersonMemory) -> None:
        """Insert or update a structured person memory."""
        now = time.time()
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    """INSERT OR REPLACE INTO whatsapp_person_memories
                       (id, chat_name, category, subject, fact, status, confidence,
                        evidence_text, source_message_id, valid_from, valid_until,
                        superseded_by, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        memory.id,
                        memory.chat_name,
                        memory.category,
                        memory.subject,
                        memory.fact,
                        memory.status,
                        memory.confidence,
                        memory.evidence_text,
                        memory.source_message_id,
                        memory.valid_from,
                        memory.valid_until,
                        memory.superseded_by,
                        memory.created_at or now,
                        now,
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    def get_person_memories(
        self, chat_name: str, status: Optional[str] = None
    ) -> List[PersonMemory]:
        """Retrieve memories for a specific contact, optionally filtered by status."""
        with self._lock:
            conn = self._get_conn()
            try:
                if status:
                    rows = conn.execute(
                        """SELECT * FROM whatsapp_person_memories
                           WHERE chat_name = ? AND status = ?
                           ORDER BY updated_at DESC""",
                        (chat_name, status),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        """SELECT * FROM whatsapp_person_memories
                           WHERE chat_name = ?
                           ORDER BY updated_at DESC""",
                        (chat_name,),
                    ).fetchall()
                return [PersonMemory.from_dict(dict(r)) for r in rows]
            finally:
                conn.close()

    def find_conflicting_memory(
        self, chat_name: str, category: str, subject: str
    ) -> Optional[PersonMemory]:
        """Find an active/current memory on the same category and subject."""
        with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute(
                    """SELECT * FROM whatsapp_person_memories
                       WHERE chat_name = ? AND category = ? AND subject = ? AND status = 'current'
                       ORDER BY updated_at DESC LIMIT 1""",
                    (chat_name, category, subject),
                ).fetchone()
                return PersonMemory.from_dict(dict(row)) if row else None
            finally:
                conn.close()

    def supersede_person_memory(
        self, old_memory_id: str, new_memory_id: str, new_status: str = "superseded"
    ) -> None:
        """Mark an older fact as superseded or historical when contradicted or updated."""
        now = time.time()
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    """UPDATE whatsapp_person_memories
                       SET status = ?, superseded_by = ?, valid_until = ?, updated_at = ?
                       WHERE id = ?""",
                    (new_status, new_memory_id, now, now, old_memory_id),
                )
                conn.commit()
            finally:
                conn.close()

    def search_relevant_memories(
        self, chat_name: str, query: str, limit: int = 8
    ) -> List[PersonMemory]:
        """Keyword and topic search across active & historical memories for a contact."""
        tokens = [t.lower() for t in query.split() if len(t) >= 3 and t not in (
            "the", "and", "for", "with", "about", "what", "where", "when", "how", "you", "your"
        )]
        with self._lock:
            conn = self._get_conn()
            try:
                # First fetch current memories
                current_rows = conn.execute(
                    """SELECT * FROM whatsapp_person_memories
                       WHERE chat_name = ? AND status = 'current'
                       ORDER BY confidence DESC, updated_at DESC""",
                    (chat_name,),
                ).fetchall()
                all_current = [PersonMemory.from_dict(dict(r)) for r in current_rows]

                if not tokens:
                    return all_current[:limit]

                # Match by token relevance
                matched = []
                for m in all_current:
                    haystack = f"{m.category} {m.subject} {m.fact} {m.evidence_text}".lower()
                    score = sum(1 for t in tokens if t in haystack)
                    if score > 0:
                        matched.append((score, m))

                matched.sort(key=lambda x: x[0], reverse=True)
                results = [m for _, m in matched]

                # If fewer than limit, fill with highest confidence current memories
                for m in all_current:
                    if len(results) >= limit:
                        break
                    if m not in results:
                        results.append(m)

                return results[:limit]
            finally:
                conn.close()

    # ── Conversation State Tracking ───────────────────────────────

    def save_conversation_state(self, state: ConversationStateRecord) -> None:
        """Persist or update state for a chat."""
        now = time.time()
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    """INSERT OR REPLACE INTO whatsapp_conversation_states
                       (chat_name, state, previous_state, last_message_at, last_sender,
                        turn_count, active_topic, termination_phrase, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        state.chat_name,
                        state.state,
                        state.previous_state,
                        state.last_message_at,
                        state.last_sender,
                        state.turn_count,
                        state.active_topic,
                        state.termination_phrase,
                        state.created_at or now,
                        now,
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    def get_conversation_state(self, chat_name: str) -> Optional[ConversationStateRecord]:
        """Retrieve the current state record for a chat."""
        with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute(
                    """SELECT * FROM whatsapp_conversation_states
                       WHERE chat_name = ?""",
                    (chat_name,),
                ).fetchone()
                return ConversationStateRecord.from_dict(dict(row)) if row else None
            finally:
                conn.close()

    # ── Latent Style Observations ─────────────────────────────────

    def save_style_observation(self, obs: StyleObservation) -> None:
        """Record an observation of linguistic/communication style."""
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    """INSERT OR REPLACE INTO whatsapp_style_observations
                       (id, chat_name, message_id, formality_score, slang_score,
                        emoji_count, avg_word_count, tamil_english_mix, humor_score, observed_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        obs.id,
                        obs.chat_name,
                        obs.message_id,
                        obs.formality_score,
                        obs.slang_score,
                        obs.emoji_count,
                        obs.avg_word_count,
                        obs.tamil_english_mix,
                        obs.humor_score,
                        obs.observed_at or time.time(),
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    def get_recent_style_observations(
        self, chat_name: str, limit: int = 30
    ) -> List[StyleObservation]:
        """Retrieve recent style observations for a chat."""
        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    """SELECT * FROM whatsapp_style_observations
                       WHERE chat_name = ?
                       ORDER BY observed_at DESC LIMIT ?""",
                    (chat_name, limit),
                ).fetchall()
                return [StyleObservation.from_dict(dict(r)) for r in rows]
            finally:
                conn.close()

    # ── Persistent Entities ───────────────────────────────────────

    def save_entity(self, entity: Dict[str, Any]) -> None:
        """Store or update a persistent entity."""
        with self._lock:
            conn = self._get_conn()
            try:
                aliases_json = json.dumps(entity.get("aliases", []), ensure_ascii=False)
                metadata_json = json.dumps(entity.get("metadata", {}), ensure_ascii=False)
                now = time.time()
                conn.execute(
                    """INSERT OR REPLACE INTO whatsapp_entities
                       (id, entity_type, canonical_name, aliases, metadata, confidence, source, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        entity.get("id") or str(uuid.uuid4()),
                        entity.get("entity_type", "person"),
                        entity.get("canonical_name", ""),
                        aliases_json,
                        metadata_json,
                        float(entity.get("confidence", 1.0)),
                        entity.get("source", "system"),
                        float(entity.get("created_at", now)),
                        now,
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    def get_entity(self, identifier: str) -> Optional[Dict[str, Any]]:
        """Look up entity by canonical_name or id."""
        with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute(
                    """SELECT * FROM whatsapp_entities
                       WHERE id = ? OR canonical_name = ? COLLATE NOCASE""",
                    (identifier, identifier),
                ).fetchone()
                if not row:
                    return None
                d = dict(row)
                d["aliases"] = json.loads(d.get("aliases") or "[]")
                d["metadata"] = json.loads(d.get("metadata") or "{}")
                return d
            finally:
                conn.close()

    def find_entities(self, query: str, entity_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Find matching entities by name, alias, or token."""
        q_low = query.lower().strip()
        with self._lock:
            conn = self._get_conn()
            try:
                sql = "SELECT * FROM whatsapp_entities"
                params = []
                if entity_type:
                    sql += " WHERE entity_type = ?"
                    params.append(entity_type)
                rows = conn.execute(sql, params).fetchall()
                results = []
                for r in rows:
                    d = dict(r)
                    d["aliases"] = json.loads(d.get("aliases") or "[]")
                    d["metadata"] = json.loads(d.get("metadata") or "{}")
                    canonical_low = d["canonical_name"].lower()
                    if q_low in canonical_low or canonical_low in q_low:
                        results.append(d)
                        continue
                    if any(q_low in a.lower() or a.lower() in q_low for a in d["aliases"]):
                        results.append(d)
                return results
            finally:
                conn.close()

    def list_entities(self, entity_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all entities of a given type."""
        with self._lock:
            conn = self._get_conn()
            try:
                if entity_type:
                    rows = conn.execute("SELECT * FROM whatsapp_entities WHERE entity_type = ?", (entity_type,)).fetchall()
                else:
                    rows = conn.execute("SELECT * FROM whatsapp_entities").fetchall()
                res = []
                for r in rows:
                    d = dict(r)
                    d["aliases"] = json.loads(d.get("aliases") or "[]")
                    d["metadata"] = json.loads(d.get("metadata") or "{}")
                    res.append(d)
                return res
            finally:
                conn.close()

    # ── Persistent Media Items ────────────────────────────────────

    def save_media_item(self, item: Dict[str, Any]) -> None:
        """Store or update a verified media item."""
        with self._lock:
            conn = self._get_conn()
            try:
                entities_json = json.dumps(item.get("entities", []), ensure_ascii=False)
                vision_json = json.dumps(item.get("vision_labels", []), ensure_ascii=False)
                metadata_json = json.dumps(item.get("metadata", {}), ensure_ascii=False)
                conn.execute(
                    """INSERT OR REPLACE INTO whatsapp_media_items
                       (media_id, media_type, filename, original_filename, conversation_id, message_id,
                        sender, timestamp, caption, entities, verified, content_hash, storage_path,
                        thumbnail_path, size_bytes, ocr_text, vision_labels, metadata, status, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        item.get("media_id") or str(uuid.uuid4()),
                        item.get("media_type", "image"),
                        item.get("filename", ""),
                        item.get("original_filename", ""),
                        item.get("conversation_id", ""),
                        item.get("message_id", ""),
                        item.get("sender", ""),
                        float(item.get("timestamp", time.time())),
                        item.get("caption", ""),
                        entities_json,
                        1 if item.get("verified", True) else 0,
                        item.get("content_hash", ""),
                        item.get("storage_path", ""),
                        item.get("thumbnail_path", ""),
                        int(item.get("size_bytes", 0)),
                        item.get("ocr_text", ""),
                        vision_json,
                        metadata_json,
                        item.get("status", "VERIFIED"),
                        float(item.get("created_at", time.time())),
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    def get_media_item(self, media_id: str) -> Optional[Dict[str, Any]]:
        """Fetch media item by media_id or filename."""
        with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute(
                    """SELECT * FROM whatsapp_media_items
                       WHERE media_id = ? OR filename = ?""",
                    (media_id, media_id),
                ).fetchone()
                if not row:
                    return None
                d = dict(row)
                d["entities"] = json.loads(d.get("entities") or "[]")
                d["vision_labels"] = json.loads(d.get("vision_labels") or "[]")
                d["metadata"] = json.loads(d.get("metadata") or "{}")
                return d
            finally:
                conn.close()

    def update_media_item(self, media_id: str, updates: Dict[str, Any]) -> bool:
        """Update fields of an existing media item."""
        with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute("SELECT * FROM whatsapp_media_items WHERE media_id = ? OR filename = ?", (media_id, media_id)).fetchone()
                if not row:
                    return False
                d = dict(row)
                for k, v in updates.items():
                    if k in ("entities", "vision_labels", "metadata") and isinstance(v, (list, dict)):
                        d[k] = json.dumps(v, ensure_ascii=False)
                    else:
                        d[k] = v
                conn.execute(
                    """UPDATE whatsapp_media_items SET
                       filename = ?, caption = ?, entities = ?, storage_path = ?, status = ?, metadata = ?
                       WHERE media_id = ?""",
                    (
                        d["filename"],
                        d["caption"],
                        d["entities"] if isinstance(d["entities"], str) else json.dumps(d["entities"]),
                        d["storage_path"],
                        d["status"],
                        d["metadata"] if isinstance(d["metadata"], str) else json.dumps(d["metadata"]),
                        d["media_id"],
                    ),
                )
                conn.commit()
                return True
            finally:
                conn.close()

    def find_media_items(
        self,
        entity: Optional[str] = None,
        media_type: Optional[str] = None,
        sender: Optional[str] = None,
        chat_name: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Find media items matching criteria."""
        with self._lock:
            conn = self._get_conn()
            try:
                sql = "SELECT * FROM whatsapp_media_items WHERE 1=1"
                params = []
                if media_type:
                    sql += " AND media_type = ?"
                    params.append(media_type)
                if sender:
                    sql += " AND sender LIKE ?"
                    params.append(f"%{sender}%")
                if chat_name:
                    sql += " AND (conversation_id = ? OR sender = ?)"
                    params.extend([chat_name, chat_name])
                sql += " ORDER BY timestamp DESC LIMIT ?"
                params.append(limit * 2)

                rows = conn.execute(sql, params).fetchall()
                results = []
                e_low = entity.lower().strip() if entity else None

                for r in rows:
                    d = dict(r)
                    d["entities"] = json.loads(d.get("entities") or "[]")
                    d["vision_labels"] = json.loads(d.get("vision_labels") or "[]")
                    d["metadata"] = json.loads(d.get("metadata") or "{}")

                    if e_low:
                        entities_match = any(e_low in str(ent).lower() for ent in d["entities"])
                        name_match = e_low in d["filename"].lower() or e_low in d.get("caption", "").lower()
                        if not entities_match and not name_match:
                            continue
                    results.append(d)
                    if len(results) >= limit:
                        break
                return results
            finally:
                conn.close()

    def get_latest_media_in_chat(
        self, chat_name: str, media_type: Optional[str] = None, max_age_seconds: float = 600.0
    ) -> Optional[Dict[str, Any]]:
        """Get the most recent media item received in a chat."""
        with self._lock:
            conn = self._get_conn()
            try:
                sql = """SELECT * FROM whatsapp_media_items
                         WHERE (conversation_id = ? OR sender = ?)"""
                params: List[Any] = [chat_name, chat_name]
                if media_type:
                    sql += " AND media_type = ?"
                    params.append(media_type)
                sql += " ORDER BY timestamp DESC LIMIT 1"
                row = conn.execute(sql, params).fetchone()
                if not row:
                    return None
                d = dict(row)
                d["entities"] = json.loads(d.get("entities") or "[]")
                d["vision_labels"] = json.loads(d.get("vision_labels") or "[]")
                d["metadata"] = json.loads(d.get("metadata") or "{}")
                if time.time() - d["timestamp"] > max_age_seconds:
                    return None
                return d
            finally:
                conn.close()

    # ── Persistent Documents ──────────────────────────────────────

    def save_document_record(self, doc: Dict[str, Any]) -> None:
        """Store or update a document record."""
        with self._lock:
            conn = self._get_conn()
            try:
                subjects_json = json.dumps(doc.get("subjects", []), ensure_ascii=False)
                entities_json = json.dumps(doc.get("entities", []), ensure_ascii=False)
                conn.execute(
                    """INSERT OR REPLACE INTO whatsapp_documents
                       (document_id, filename, original_filename, doc_type, owner, subjects,
                        semester, category, source_message_id, created_at, content_hash,
                        storage_path, text_content, text_summary, verified, entities)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        doc.get("document_id") or str(uuid.uuid4()),
                        doc.get("filename", ""),
                        doc.get("original_filename", ""),
                        doc.get("doc_type", "general"),
                        doc.get("owner", "David Julius"),
                        subjects_json,
                        int(doc.get("semester", 1)),
                        doc.get("category", "academic"),
                        doc.get("source_message_id", ""),
                        float(doc.get("created_at", time.time())),
                        doc.get("content_hash", ""),
                        doc.get("storage_path", ""),
                        doc.get("text_content", ""),
                        doc.get("text_summary", ""),
                        1 if doc.get("verified", True) else 0,
                        entities_json,
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    def find_documents(
        self, query: str = "", doc_type: Optional[str] = None, semester: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Search documents by keyword, type, or semester."""
        q_low = query.lower().strip()
        with self._lock:
            conn = self._get_conn()
            try:
                sql = "SELECT * FROM whatsapp_documents WHERE 1=1"
                params: List[Any] = []
                if doc_type:
                    sql += " AND doc_type = ?"
                    params.append(doc_type)
                if semester is not None:
                    sql += " AND semester = ?"
                    params.append(semester)
                sql += " ORDER BY created_at DESC"
                rows = conn.execute(sql, params).fetchall()
                results = []
                for r in rows:
                    d = dict(r)
                    d["subjects"] = json.loads(d.get("subjects") or "[]")
                    d["entities"] = json.loads(d.get("entities") or "[]")
                    if q_low:
                        is_exam_req = any(k in q_low for k in ["assessment", "exam", "ca", "cat", "test"])
                        # If query is NOT an exam query, do NOT match exam_timetable documents
                        if not is_exam_req and d.get("doc_type") == "exam_timetable":
                            continue
                        # If query IS an exam query, do NOT match regular class_timetable documents
                        if is_exam_req and d.get("doc_type") in ("class_timetable", "routine"):
                            continue

                        name_match = q_low in d["filename"].lower()
                        subj_match = any(q_low in s.lower() for s in d["subjects"])
                        ent_match = any(q_low in e.lower() for e in d["entities"])
                        type_match = q_low in d["doc_type"].lower()
                        if name_match or subj_match or ent_match or type_match:
                            results.append(d)
                            continue

                        # Token-based flexible matching for conversational queries
                        clean_q = re.sub(r"\b(give|send|share|show|attach|me|please|the|a|an|pdf|document|file)\b", "", q_low).strip()
                        q_tokens = [t for t in re.split(r"[\s,_\-]+", clean_q) if len(t) >= 2]
                        target_text = f"{d['filename']} {' '.join(d['subjects'])} {' '.join(d['entities'])} {d['doc_type']} {d.get('title', '')}".lower()
                        token_hits = sum(1 for t in q_tokens if t in target_text)

                        # Match if significant token overlap exists (e.g. "ca", "assessment", "timetable", "test")
                        if not (q_tokens and token_hits >= max(1, min(2, len(q_tokens)))):
                            continue
                    results.append(d)
                return results
            finally:
                conn.close()

    # ── College Timetables ────────────────────────────────────────

    def save_timetable_entry(self, entry: Dict[str, Any]) -> None:
        """Store a deterministic timetable entry."""
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    """INSERT OR REPLACE INTO whatsapp_timetables
                       (id, person, department, semester, day_of_week, start_time, end_time,
                        course_name, course_code, room_location, activity_type, source, confidence)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        entry.get("id") or str(uuid.uuid4()),
                        entry.get("person", "David Julius"),
                        entry.get("department", "IT"),
                        int(entry.get("semester", 1)),
                        entry.get("day_of_week", ""),
                        entry.get("start_time", ""),
                        entry.get("end_time", ""),
                        entry.get("course_name", ""),
                        entry.get("course_code", ""),
                        entry.get("room_location", ""),
                        entry.get("activity_type", "class"),
                        entry.get("source", "verified_schedule"),
                        float(entry.get("confidence", 1.0)),
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    def get_timetable_for_day(self, person: str, day_of_week: str) -> List[Dict[str, Any]]:
        """Get ordered timetable periods for a specific day."""
        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    """SELECT * FROM whatsapp_timetables
                       WHERE person = ? AND day_of_week = ? COLLATE NOCASE
                       ORDER BY start_time ASC""",
                    (person, day_of_week),
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    def get_all_timetable_entries(self, person: str = "David Julius") -> List[Dict[str, Any]]:
        """Get all timetable periods for a person."""
        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute(
                    """SELECT * FROM whatsapp_timetables
                       WHERE person = ?
                       ORDER BY day_of_week, start_time ASC""",
                    (person,),
                ).fetchall()
                return [dict(r) for r in rows]
            finally:
                conn.close()

    # ── Action Receipts ───────────────────────────────────────────

    def save_action_receipt(self, receipt: Dict[str, Any]) -> None:
        """Store a machine-readable action receipt."""
        with self._lock:
            try:
                conn = self._get_conn()
                try:
                    args_json = json.dumps(receipt.get("arguments", {}), ensure_ascii=False)
                    res_json = json.dumps(receipt.get("result", {}), ensure_ascii=False)
                    conn.execute(
                        """INSERT OR REPLACE INTO whatsapp_action_receipts
                           (action_id, requested_by, intent, target, arguments, authorization_status,
                            execution_status, result, whatsapp_message_id, timestamp)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            receipt.get("action_id") or str(uuid.uuid4()),
                            receipt.get("requested_by", ""),
                            receipt.get("intent", ""),
                            receipt.get("target", ""),
                            args_json,
                            receipt.get("authorization_status", "AUTHORIZED"),
                            receipt.get("execution_status", "SUCCESS"),
                            res_json,
                            receipt.get("whatsapp_message_id", ""),
                            float(receipt.get("timestamp", time.time())),
                        ),
                    )
                    conn.commit()
                finally:
                    conn.close()
            except sqlite3.OperationalError:
                self._create_tables()
                conn = self._get_conn()
                try:
                    args_json = json.dumps(receipt.get("arguments", {}), ensure_ascii=False)
                    res_json = json.dumps(receipt.get("result", {}), ensure_ascii=False)
                    conn.execute(
                        """INSERT OR REPLACE INTO whatsapp_action_receipts
                           (action_id, requested_by, intent, target, arguments, authorization_status,
                            execution_status, result, whatsapp_message_id, timestamp)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            receipt.get("action_id") or str(uuid.uuid4()),
                            receipt.get("requested_by", ""),
                            receipt.get("intent", ""),
                            receipt.get("target", ""),
                            args_json,
                            receipt.get("authorization_status", "AUTHORIZED"),
                            receipt.get("execution_status", "SUCCESS"),
                            res_json,
                            receipt.get("whatsapp_message_id", ""),
                            float(receipt.get("timestamp", time.time())),
                        ),
                    )
                    conn.commit()
                finally:
                    conn.close()

    def get_action_receipt(self, action_id: str) -> Optional[Dict[str, Any]]:
        """Fetch receipt by action_id."""
        with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute("SELECT * FROM whatsapp_action_receipts WHERE action_id = ?", (action_id,)).fetchone()
                if not row:
                    return None
                d = dict(row)
                d["arguments"] = json.loads(d.get("arguments") or "{}")
                d["result"] = json.loads(d.get("result") or "{}")
                return d
            finally:
                conn.close()

    # ── Chat Clearing vs Memory Separation ────────────────────────

    def clear_chat(self, chat_name: str) -> int:
        """
        Clear ephemeral chat messages for a chat.
        Crucial requirement: Persistent knowledge, entities, media_items,
        documents, and facts are PRESERVED and untouched.
        """
        with self._lock:
            conn = self._get_conn()
            try:
                cur = conn.execute(
                    "DELETE FROM whatsapp_messages WHERE chat_name = ? OR chat_id = ?",
                    (chat_name, chat_name),
                )
                deleted = cur.rowcount
                # Reset conversation state
                conn.execute(
                    "DELETE FROM whatsapp_conversation_states WHERE chat_name = ?",
                    (chat_name,),
                )
                conn.commit()
                return deleted
            finally:
                conn.close()

    def clear_memory(self, chat_name: str) -> None:
        """Clear learned personal facts for a chat."""
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "DELETE FROM whatsapp_person_memories WHERE chat_name = ?",
                    (chat_name,),
                )
                conn.execute(
                    "DELETE FROM whatsapp_conversation_summaries WHERE chat_id = ?",
                    (chat_name,),
                )
                conn.commit()
            finally:
                conn.close()




