"""
Julius WhatsApp Integration — Models & Data Types.

Defines all core data structures: messages, policies, health states,
approval items, training examples, style profiles, and confidence levels.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


# ── Enums ─────────────────────────────────────────────────────────────────────

class ChatMode(str, Enum):
    """Operating mode for a configured chat."""
    OFF = "off"
    APPROVAL = "approval"
    AUTO = "auto"
    TRAINING = "training"


class HealthState(str, Enum):
    """WhatsApp integration health states."""
    DISABLED = "disabled"
    STARTING = "starting"
    WAITING_FOR_QR = "waiting_for_qr"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    SESSION_EXPIRED = "session_expired"
    BROWSER_ERROR = "browser_error"
    STOPPED = "stopped"
    ERROR = "error"


class Confidence(str, Enum):
    """Response confidence classification."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class MessageType(str, Enum):
    """WhatsApp message content type."""
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    VOICE = "voice"
    DOCUMENT = "document"
    STICKER = "sticker"
    CONTACT = "contact"
    LOCATION = "location"
    UNKNOWN = "unknown"


class GroupTrigger(str, Enum):
    """When to respond in group chats."""
    WHEN_MENTIONED = "when_mentioned"
    WHEN_REPLYING_TO_ME = "when_replying_to_me"
    EVERY_RELEVANT = "every_relevant"
    NEVER = "never"


# ── Core Message Model ────────────────────────────────────────────────────────

@dataclass
class WhatsAppMessage:
    """Normalized internal representation of a WhatsApp message."""
    id: str
    chat_id: str
    chat_name: str
    sender_id: str
    sender_name: str
    timestamp: float
    text: str
    quoted_message_id: Optional[str] = None
    quoted_text: Optional[str] = None
    is_group: bool = False
    is_from_me: bool = False
    message_type: MessageType = MessageType.TEXT
    attachment_metadata: Optional[Dict[str, Any]] = None
    raw_reference: Optional[str] = None  # minimal DOM reference, not full page

    @property
    def dedup_key(self) -> str:
        """Stable key for a WhatsApp message, falling back only when the DOM lacks an ID."""
        # WhatsApp's data-id survives browser and service restarts.  Text alone
        # is not safe here: a contact can legitimately send the same text twice.
        if self.raw_reference:
            content = f"{self.chat_id}:{self.raw_reference}"
        else:
            content = f"{self.chat_id}:{self.sender_id}:{self.id}:{self.text.strip()}"
        return hashlib.sha256(content.encode()).hexdigest()[:32]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "chat_id": self.chat_id,
            "chat_name": self.chat_name,
            "sender_id": self.sender_id,
            "sender_name": self.sender_name,
            "timestamp": self.timestamp,
            "text": self.text,
            "quoted_message_id": self.quoted_message_id,
            "quoted_text": self.quoted_text,
            "is_group": self.is_group,
            "is_from_me": self.is_from_me,
            "message_type": self.message_type.value,
            "attachment_metadata": self.attachment_metadata,
        }


# ── Chat Configuration ────────────────────────────────────────────────────────

@dataclass
class ChatConfig:
    """Per-chat configuration."""
    chat_name: str
    chat_id: str = ""
    enabled: bool = True
    mode: ChatMode = ChatMode.APPROVAL
    persona: Optional[str] = None  # persona profile name override
    response_style: Optional[str] = None
    auto_reply_delay_min: float = 1.0  # seconds
    auto_reply_delay_max: float = 8.0
    allowed_hours_start: Optional[int] = None  # 0-23, None = always
    allowed_hours_end: Optional[int] = None
    max_messages_per_hour: int = 20
    escalation_policy: str = "approval"  # "approval" or "ignore"
    context_window: int = 20  # number of recent messages to include
    memory_enabled: bool = True
    group_trigger: GroupTrigger = GroupTrigger.WHEN_MENTIONED
    mark_as_read: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chat_name": self.chat_name,
            "chat_id": self.chat_id,
            "enabled": self.enabled,
            "mode": self.mode.value,
            "persona": self.persona,
            "response_style": self.response_style,
            "auto_reply_delay_min": self.auto_reply_delay_min,
            "auto_reply_delay_max": self.auto_reply_delay_max,
            "allowed_hours_start": self.allowed_hours_start,
            "allowed_hours_end": self.allowed_hours_end,
            "max_messages_per_hour": self.max_messages_per_hour,
            "escalation_policy": self.escalation_policy,
            "context_window": self.context_window,
            "memory_enabled": self.memory_enabled,
            "group_trigger": self.group_trigger.value,
            "mark_as_read": self.mark_as_read,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChatConfig":
        return cls(
            chat_name=data["chat_name"],
            chat_id=data.get("chat_id", ""),
            enabled=data.get("enabled", True),
            mode=ChatMode(data.get("mode", "approval")),
            persona=data.get("persona"),
            response_style=data.get("response_style"),
            auto_reply_delay_min=data.get("auto_reply_delay_min", 1.0),
            auto_reply_delay_max=data.get("auto_reply_delay_max", 8.0),
            allowed_hours_start=data.get("allowed_hours_start"),
            allowed_hours_end=data.get("allowed_hours_end"),
            max_messages_per_hour=data.get("max_messages_per_hour", 20),
            escalation_policy=data.get("escalation_policy", "approval"),
            context_window=data.get("context_window", 20),
            memory_enabled=data.get("memory_enabled", True),
            group_trigger=GroupTrigger(data.get("group_trigger", "when_mentioned")),
            mark_as_read=data.get("mark_as_read", True),
        )


# ── Approval Queue Item ──────────────────────────────────────────────────────

@dataclass
class ApprovalItem:
    """A pending message approval in the queue."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    incoming_message: Optional[WhatsAppMessage] = None
    draft_reply: str = ""
    confidence: Confidence = Confidence.MEDIUM
    reason: str = ""
    chat_name: str = ""
    chat_id: str = ""
    created_at: float = field(default_factory=time.time)
    status: str = "pending"  # pending, approved, rejected, expired

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "incoming_message": self.incoming_message.to_dict() if self.incoming_message else None,
            "draft_reply": self.draft_reply,
            "confidence": self.confidence.value,
            "reason": self.reason,
            "chat_name": self.chat_name,
            "chat_id": self.chat_id,
            "created_at": self.created_at,
            "status": self.status,
        }


# ── Training Example ─────────────────────────────────────────────────────────

@dataclass
class TrainingExample:
    """A single training input-output pair."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    incoming_text: str = ""
    predicted_reply: str = ""
    actual_reply: str = ""
    chat_name: str = ""
    chat_id: str = ""
    sender_name: str = ""
    is_group: bool = False
    timestamp: float = field(default_factory=time.time)
    is_important: bool = False
    is_disabled: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "incoming_text": self.incoming_text,
            "predicted_reply": self.predicted_reply,
            "actual_reply": self.actual_reply,
            "chat_name": self.chat_name,
            "chat_id": self.chat_id,
            "sender_name": self.sender_name,
            "is_group": self.is_group,
            "timestamp": self.timestamp,
            "is_important": self.is_important,
            "is_disabled": self.is_disabled,
        }


# ── Style Profile ─────────────────────────────────────────────────────────────

@dataclass
class StyleProfile:
    """User's learned communication style profile."""
    name: str = "default"
    tone: str = "casual"  # casual, neutral, formal
    avg_message_length: float = 0.0  # words
    formality: str = "low"  # low, medium, high
    emoji_frequency: str = "occasional"  # never, rare, occasional, frequent
    emoji_placement: str = "end"  # end, inline, start
    punctuation_style: str = "minimal"  # minimal, standard, heavy
    capitalization: str = "lowercase"  # lowercase, standard, mixed
    greeting_habit: str = "usually_omitted"  # always, sometimes, usually_omitted
    closing_habit: str = "usually_omitted"
    preferred_phrases: List[str] = field(default_factory=list)
    common_abbreviations: List[str] = field(default_factory=list)
    avoid_patterns: List[str] = field(default_factory=lambda: [
        "corporate language",
        "excessive explanation",
        "excessive emojis",
        "AI-style wording",
        "fake enthusiasm",
        "Certainly!",
        "Absolutely!",
        "I hope you're doing well",
    ])
    humor_level: str = "occasional"  # never, occasional, frequent
    response_directness: str = "direct"  # direct, moderate, verbose
    sentence_fragmentation: str = "frequent"  # none, occasional, frequent
    multi_message_tendency: str = "rare"  # never, rare, sometimes, often
    max_consecutive_messages: int = 1
    confidence_scores: Dict[str, float] = field(default_factory=lambda: {
        "tone": 0.0,
        "length": 0.0,
        "emoji": 0.0,
        "vocabulary": 0.0,
        "punctuation": 0.0,
        "formality": 0.0,
    })

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "tone": self.tone,
            "avg_message_length": self.avg_message_length,
            "formality": self.formality,
            "emoji_frequency": self.emoji_frequency,
            "emoji_placement": self.emoji_placement,
            "punctuation_style": self.punctuation_style,
            "capitalization": self.capitalization,
            "greeting_habit": self.greeting_habit,
            "closing_habit": self.closing_habit,
            "preferred_phrases": self.preferred_phrases,
            "common_abbreviations": self.common_abbreviations,
            "avoid_patterns": self.avoid_patterns,
            "humor_level": self.humor_level,
            "response_directness": self.response_directness,
            "sentence_fragmentation": self.sentence_fragmentation,
            "multi_message_tendency": self.multi_message_tendency,
            "max_consecutive_messages": self.max_consecutive_messages,
            "confidence_scores": self.confidence_scores,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StyleProfile":
        return cls(
            name=data.get("name", "default"),
            tone=data.get("tone", "casual"),
            avg_message_length=data.get("avg_message_length", 0.0),
            formality=data.get("formality", "low"),
            emoji_frequency=data.get("emoji_frequency", "occasional"),
            emoji_placement=data.get("emoji_placement", "end"),
            punctuation_style=data.get("punctuation_style", "minimal"),
            capitalization=data.get("capitalization", "lowercase"),
            greeting_habit=data.get("greeting_habit", "usually_omitted"),
            closing_habit=data.get("closing_habit", "usually_omitted"),
            preferred_phrases=data.get("preferred_phrases", []),
            common_abbreviations=data.get("common_abbreviations", []),
            avoid_patterns=data.get("avoid_patterns", cls().avoid_patterns),
            humor_level=data.get("humor_level", "occasional"),
            response_directness=data.get("response_directness", "direct"),
            sentence_fragmentation=data.get("sentence_fragmentation", "frequent"),
            multi_message_tendency=data.get("multi_message_tendency", "rare"),
            max_consecutive_messages=data.get("max_consecutive_messages", 1),
            confidence_scores=data.get("confidence_scores", {}),
        )


# ── Audit Log Entry ───────────────────────────────────────────────────────────

@dataclass
class AuditEntry:
    """Record of a WhatsApp action for audit trail."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    timestamp: float = field(default_factory=time.time)
    chat_name: str = ""
    chat_id: str = ""
    sender_name: str = ""
    incoming_message_id: Optional[str] = None
    mode: str = ""
    generated_reply: str = ""
    final_reply: str = ""
    edited_by_user: bool = False
    sent: bool = False
    rejected: bool = False
    approved: bool = False
    model_provider: str = ""
    latency_ms: int = 0
    reason_code: str = ""
    confidence: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "chat_name": self.chat_name,
            "chat_id": self.chat_id,
            "sender_name": self.sender_name,
            "incoming_message_id": self.incoming_message_id,
            "mode": self.mode,
            "generated_reply": self.generated_reply,
            "final_reply": self.final_reply,
            "edited_by_user": self.edited_by_user,
            "sent": self.sent,
            "rejected": self.rejected,
            "approved": self.approved,
            "model_provider": self.model_provider,
            "latency_ms": self.latency_ms,
            "reason_code": self.reason_code,
            "confidence": self.confidence,
        }


# ── Sent Message Record (Loop Prevention) ─────────────────────────────────────

@dataclass
class SentMessageRecord:
    """Record of an outgoing message for loop prevention."""
    message_id: str = ""
    chat_id: str = ""
    content_hash: str = ""
    timestamp: float = field(default_factory=time.time)
    text: str = ""

    @staticmethod
    def compute_hash(text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()[:32]


# ── Dynamic Contact Profile (Evolving Memory & Social Graph) ──────────────────

@dataclass
class ContactProfile:
    """
    Dynamic, evolving memory profile for a WhatsApp contact.
    Learned and continuously updated from ongoing conversation history.
    """
    chat_name: str
    display_name: str = ""
    contact_type: str = "friend"  # friend, classmate, peer, junior, senior, self
    tone_style: str = "casual"  # casual, sarcastic, energetic, respectful, playful, humorous
    slang_used: List[str] = field(default_factory=list)  # e.g. ["da", "machi", "bro", "machan"]
    favorite_topics: List[str] = field(default_factory=list)  # e.g. ["hostel", "calculus", "coding", "food", "exams"]
    last_status_update: str = ""  # e.g. "chillin in hostel room studying for calculus"
    interconnected_notes: str = ""  # safe context shareable with mutual friends
    important_facts: List[str] = field(default_factory=list)  # specific facts learned about this person
    total_messages_exchanged: int = 0
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chat_name": self.chat_name,
            "display_name": self.display_name,
            "contact_type": self.contact_type,
            "tone_style": self.tone_style,
            "slang_used": self.slang_used,
            "favorite_topics": self.favorite_topics,
            "last_status_update": self.last_status_update,
            "interconnected_notes": self.interconnected_notes,
            "important_facts": self.important_facts,
            "total_messages_exchanged": self.total_messages_exchanged,
            "updated_at": self.updated_at,
        }


# ── Structured Person Knowledge Models ───────────────────────────────────────

class MemoryStatus(str, Enum):
    CURRENT = "current"
    HISTORICAL = "historical"
    SUPERSEDED = "superseded"
    UNCERTAIN = "uncertain"
    PLANNED = "planned"


class MemoryCategory(str, Enum):
    IDENTITY = "identity"
    LOCATION = "location"
    EDUCATION = "education"
    WORK = "work"
    PROJECT = "project"
    PREFERENCE = "preference"
    RELATIONSHIP = "relationship"
    EVENT = "event"
    SITUATION = "situation"
    COMMUNICATION = "communication"
    OTHER = "other"


@dataclass
class PersonMemory:
    """Individual atomic fact in the person's knowledge graph."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    chat_name: str = ""
    category: str = MemoryCategory.OTHER.value
    subject: str = ""
    fact: str = ""
    status: str = MemoryStatus.CURRENT.value
    confidence: float = 0.9
    evidence_text: str = ""
    source_message_id: str = ""
    valid_from: float = field(default_factory=time.time)
    valid_until: Optional[float] = None
    superseded_by: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "chat_name": self.chat_name,
            "category": self.category,
            "subject": self.subject,
            "fact": self.fact,
            "status": self.status,
            "confidence": self.confidence,
            "evidence_text": self.evidence_text,
            "source_message_id": self.source_message_id,
            "valid_from": self.valid_from,
            "valid_until": self.valid_until,
            "superseded_by": self.superseded_by,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PersonMemory:
        return cls(
            id=data.get("id") or str(uuid.uuid4()),
            chat_name=data.get("chat_name", ""),
            category=data.get("category", MemoryCategory.OTHER.value),
            subject=data.get("subject", ""),
            fact=data.get("fact", ""),
            status=data.get("status", MemoryStatus.CURRENT.value),
            confidence=float(data.get("confidence", 0.9)),
            evidence_text=data.get("evidence_text", ""),
            source_message_id=data.get("source_message_id", ""),
            valid_from=float(data.get("valid_from", time.time())),
            valid_until=float(data["valid_until"]) if data.get("valid_until") is not None else None,
            superseded_by=data.get("superseded_by"),
            created_at=float(data.get("created_at", time.time())),
            updated_at=float(data.get("updated_at", time.time())),
        )


# ── Conversation State Models ────────────────────────────────────────────────

class ConversationState(str, Enum):
    NEW = "NEW"
    GREETING = "GREETING"
    ACTIVE = "ACTIVE"
    TOPIC_DISCUSSION = "TOPIC_DISCUSSION"
    WAITING_FOR_REPLY = "WAITING_FOR_REPLY"
    ENDING = "ENDING"
    ENDED = "ENDED"
    REOPENED = "REOPENED"


@dataclass
class ConversationStateRecord:
    """State record for a chat conversation."""
    chat_name: str
    state: str = ConversationState.NEW.value
    previous_state: str = ""
    last_message_at: float = field(default_factory=time.time)
    last_sender: str = ""
    turn_count: int = 0
    active_topic: str = ""
    termination_phrase: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chat_name": self.chat_name,
            "state": self.state,
            "previous_state": self.previous_state,
            "last_message_at": self.last_message_at,
            "last_sender": self.last_sender,
            "turn_count": self.turn_count,
            "active_topic": self.active_topic,
            "termination_phrase": self.termination_phrase,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ConversationStateRecord:
        return cls(
            chat_name=data.get("chat_name", ""),
            state=data.get("state", ConversationState.NEW.value),
            previous_state=data.get("previous_state", ""),
            last_message_at=float(data.get("last_message_at", time.time())),
            last_sender=data.get("last_sender", ""),
            turn_count=int(data.get("turn_count", 0)),
            active_topic=data.get("active_topic", ""),
            termination_phrase=data.get("termination_phrase", ""),
            created_at=float(data.get("created_at", time.time())),
            updated_at=float(data.get("updated_at", time.time())),
        )


# ── Latent Communication Style Observation ───────────────────────────────────

@dataclass
class StyleObservation:
    """Observation extracted from incoming message turns for longitudinal style learning."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    chat_name: str = ""
    message_id: str = ""
    formality_score: float = 0.5  # 0.0 (very informal) to 1.0 (formal)
    slang_score: float = 0.5       # 0.0 (none) to 1.0 (heavy slang)
    emoji_count: int = 0
    avg_word_count: float = 0.0
    tamil_english_mix: float = 0.0  # 0.0 (pure english) to 1.0 (heavy tanglish/tamil)
    humor_score: float = 0.0        # 0.0 (serious) to 1.0 (humorous/laughing)
    observed_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "chat_name": self.chat_name,
            "message_id": self.message_id,
            "formality_score": self.formality_score,
            "slang_score": self.slang_score,
            "emoji_count": self.emoji_count,
            "avg_word_count": self.avg_word_count,
            "tamil_english_mix": self.tamil_english_mix,
            "humor_score": self.humor_score,
            "observed_at": self.observed_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> StyleObservation:
        return cls(
            id=data.get("id") or str(uuid.uuid4()),
            chat_name=data.get("chat_name", ""),
            message_id=data.get("message_id", ""),
            formality_score=float(data.get("formality_score", 0.5)),
            slang_score=float(data.get("slang_score", 0.5)),
            emoji_count=int(data.get("emoji_count", 0)),
            avg_word_count=float(data.get("avg_word_count", 0.0)),
            tamil_english_mix=float(data.get("tamil_english_mix", 0.0)),
            humor_score=float(data.get("humor_score", 0.0)),
            observed_at=float(data.get("observed_at", time.time())),
        )


# ── Action Planning Models ───────────────────────────────────────────────────

# ── Action Planning & Reliability Models ───────────────────────────────────────

class ActionType(str, Enum):
    SEND_TEXT = "send_text"
    SEND_IMAGE = "send_image"
    SEND_DOCUMENT = "send_document"
    SEND_MEDIA = "send_media"
    ASK_CLARIFICATION = "ask_clarification"
    RENAME_MEDIA = "rename_media"
    TAG_ENTITY = "tag_entity"
    WAIT = "wait"
    END_CONVERSATION = "end_conversation"
    NO_RESPONSE = "no_response"


class ResolutionStatus(str, Enum):
    EXACT_MATCH = "exact_match"
    AMBIGUOUS = "ambiguous"
    NOT_FOUND = "not_found"
    REJECTED = "rejected"


@dataclass
class MediaResolution:
    """Deterministic result from MediaResolver."""
    status: ResolutionStatus = ResolutionStatus.NOT_FOUND
    item: Optional[Dict[str, Any]] = None
    candidates: List[Dict[str, Any]] = field(default_factory=list)
    reason: str = ""
    target_entity: Optional[str] = None
    media_type: str = "media"


class ReceiptStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    AMBIGUOUS = "AMBIGUOUS"
    NOT_FOUND = "NOT_FOUND"
    UNAUTHORIZED = "UNAUTHORIZED"
    TIMEOUT = "TIMEOUT"
    BLOCKED = "BLOCKED"


@dataclass
class ActionReceipt:
    """Machine-readable receipt for every side-effecting WhatsApp operation."""
    action_id: str
    requested_by: str
    intent: str
    target: str
    arguments: Dict[str, Any] = field(default_factory=dict)
    authorization_status: str = "AUTHORIZED"
    execution_status: ReceiptStatus = ReceiptStatus.SUCCESS
    result: Dict[str, Any] = field(default_factory=dict)
    whatsapp_message_id: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_id": self.action_id,
            "requested_by": self.requested_by,
            "intent": self.intent,
            "target": self.target,
            "arguments": self.arguments,
            "authorization_status": self.authorization_status,
            "execution_status": self.execution_status.value if isinstance(self.execution_status, ReceiptStatus) else str(self.execution_status),
            "result": self.result,
            "whatsapp_message_id": self.whatsapp_message_id,
            "timestamp": self.timestamp,
        }


@dataclass
class EntityRecord:
    """Structured knowledge entity (Person, Contact, Course, Subject, Location)."""
    id: str
    entity_type: str  # person, contact, course, subject, timetable, location
    canonical_name: str
    aliases: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    source: str = "system"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


@dataclass
class AgentAction:
    """Structured action decided by reasoning pipeline before execution."""
    action_type: ActionType = ActionType.SEND_TEXT
    text: str = ""
    media_path: Optional[str] = None
    media_type: Optional[str] = None  # image, document, pdf
    caption: str = ""
    reaction_emoji: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


