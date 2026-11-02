"""
Julius WhatsApp Personal Agent Integration.

Official WhatsApp Web automation for Julius personal assistant:
- Persistent browser session
- 24/7 background operation
- Per-chat policy allowlist (OFF, APPROVAL, AUTO, TRAINING)
- Style personalization & training curriculum
- Safety gate & human escalation
- Crash recovery & watchdog
"""

from .config import WhatsAppConfig
from .models import (
    ApprovalItem,
    ChatConfig,
    ChatMode,
    Confidence,
    GroupTrigger,
    HealthState,
    MessageType,
    StyleProfile,
    TrainingExample,
    WhatsAppMessage,
)
from .service import WhatsAppService
from .supervisor import (
    FailureClass,
    HealthEngine,
    HealthSnapshot,
    RecoveryCircuitBreaker,
    RecoveryLevel,
    RecoveryRecord,
    SubsystemState,
    SubsystemStatus,
    SupervisorConfig,
    SupervisorState,
    WhatsAppSupervisor,
)

__all__ = [
    "WhatsAppService",
    "WhatsAppConfig",
    "WhatsAppMessage",
    "ChatConfig",
    "ChatMode",
    "HealthState",
    "Confidence",
    "GroupTrigger",
    "MessageType",
    "StyleProfile",
    "TrainingExample",
    "ApprovalItem",
    "WhatsAppSupervisor",
    "HealthEngine",
    "SubsystemStatus",
    "SubsystemState",
    "HealthSnapshot",
    "FailureClass",
    "SupervisorState",
    "RecoveryLevel",
    "RecoveryRecord",
    "SupervisorConfig",
    "RecoveryCircuitBreaker",
]
