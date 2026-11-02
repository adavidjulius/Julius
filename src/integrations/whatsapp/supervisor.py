"""
Julius WhatsApp Integration — Production-Grade Self-Healing Supervisor.

Replaces the simple WhatsAppWatchdog with a stateful, failure-aware,
hierarchical recovery system.

Architecture:
    ┌──────────────────────┐
    │ WhatsAppSupervisor   │   — orchestrates health + recovery
    └──────────┬───────────┘
               │
       ┌───────▼────────┐
       │  HealthEngine   │   — probes subsystems, builds HealthSnapshot
       └───────┬────────┘
               │
   ┌───────────┼────────────────┐
   │           │                │
   ▼           ▼                ▼
Infra      Pipeline        End-to-End
   │           │                │
   └───────────┼────────────────┘
               ▼
      ┌────────────────┐
      │ State Machine  │   — deterministic state transitions
      └───────┬────────┘
              │
       failure classification
              │
              ▼
      ┌────────────────┐
      │ RecoveryEngine │   — hierarchical, verified, rate-limited
      └───────┬────────┘
              │
    verify → success | escalate → CircuitBreaker
"""

from __future__ import annotations

import asyncio
import logging
import os
import socket
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Deque, Dict, List, Optional, Set

from .browser import WhatsAppBrowserAdapter
from .health import WhatsAppHealth
from .models import HealthState

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. SUBSYSTEM STATUS & HEALTH SNAPSHOT
# ═══════════════════════════════════════════════════════════════════════════════


class SubsystemStatus(str, Enum):
    """Health status for each independently monitored subsystem."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"
    UNKNOWN = "unknown"
    RECOVERING = "recovering"
    DISABLED = "disabled"
    WAITING_FOR_AUTH = "waiting_for_auth"


@dataclass
class SubsystemState:
    """State of a single monitored subsystem."""
    status: SubsystemStatus = SubsystemStatus.UNKNOWN
    last_check: float = 0.0
    last_healthy: float = 0.0
    last_failure: float = 0.0
    failure_count: int = 0
    detail: str = ""

    def mark_healthy(self, detail: str = "") -> None:
        now = time.time()
        self.status = SubsystemStatus.HEALTHY
        self.last_check = now
        self.last_healthy = now
        self.failure_count = 0
        self.detail = detail

    def mark_degraded(self, detail: str = "") -> None:
        self.status = SubsystemStatus.DEGRADED
        self.last_check = time.time()
        self.detail = detail

    def mark_failed(self, detail: str = "") -> None:
        now = time.time()
        self.status = SubsystemStatus.FAILED
        self.last_check = now
        self.last_failure = now
        self.failure_count += 1
        self.detail = detail

    def mark_waiting(self, detail: str = "") -> None:
        self.status = SubsystemStatus.WAITING_FOR_AUTH
        self.last_check = time.time()
        self.detail = detail

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "last_check": self.last_check,
            "last_healthy": self.last_healthy,
            "last_failure": self.last_failure,
            "failure_count": self.failure_count,
            "detail": self.detail,
        }


@dataclass
class HealthSnapshot:
    """
    Structured health snapshot — every subsystem tracked independently.

    Infrastructure: network, browser, page, memory, event_loop
    Session: authentication
    Pipeline: listener, scanner, queue, processor, sender
    Service: end_to_end
    """
    network: SubsystemState = field(default_factory=SubsystemState)
    browser: SubsystemState = field(default_factory=SubsystemState)
    page: SubsystemState = field(default_factory=SubsystemState)
    authentication: SubsystemState = field(default_factory=SubsystemState)
    listener: SubsystemState = field(default_factory=SubsystemState)
    scanner: SubsystemState = field(default_factory=SubsystemState)
    queue: SubsystemState = field(default_factory=SubsystemState)
    processor: SubsystemState = field(default_factory=SubsystemState)
    sender: SubsystemState = field(default_factory=SubsystemState)
    memory: SubsystemState = field(default_factory=SubsystemState)
    event_loop: SubsystemState = field(default_factory=SubsystemState)
    end_to_end: SubsystemState = field(default_factory=SubsystemState)
    timestamp: float = field(default_factory=time.time)

    def infrastructure_healthy(self) -> bool:
        return all(s.status == SubsystemStatus.HEALTHY
                   for s in [self.network, self.browser, self.page])

    def pipeline_healthy(self) -> bool:
        return all(s.status in (SubsystemStatus.HEALTHY, SubsystemStatus.UNKNOWN)
                   for s in [self.listener, self.scanner, self.queue,
                             self.processor, self.sender])

    def service_healthy(self) -> bool:
        return (self.infrastructure_healthy()
                and self.authentication.status in (SubsystemStatus.HEALTHY,)
                and self.pipeline_healthy())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "infrastructure": {
                "network": self.network.to_dict(),
                "browser": self.browser.to_dict(),
                "page": self.page.to_dict(),
                "memory": self.memory.to_dict(),
                "event_loop": self.event_loop.to_dict(),
            },
            "session": {
                "authentication": self.authentication.to_dict(),
            },
            "pipeline": {
                "listener": self.listener.to_dict(),
                "scanner": self.scanner.to_dict(),
                "queue": self.queue.to_dict(),
                "processor": self.processor.to_dict(),
                "sender": self.sender.to_dict(),
            },
            "service": {
                "end_to_end": self.end_to_end.to_dict(),
            },
            "timestamp": self.timestamp,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 2. FAILURE CLASSIFICATION
# ═══════════════════════════════════════════════════════════════════════════════


class FailureClass(str, Enum):
    """Classified failure types with distinct recovery policies."""
    NONE = "none"
    NETWORK_FAILURE = "network_failure"
    BROWSER_CRASH = "browser_crash"
    PAGE_UNRESPONSIVE = "page_unresponsive"
    WHATSAPP_LOADING_STALL = "whatsapp_loading_stall"
    SESSION_EXPIRED = "session_expired"
    QR_REQUIRED = "qr_required"
    LISTENER_DEAD = "listener_dead"
    SCANNER_STALLED = "scanner_stalled"
    QUEUE_BACKLOG = "queue_backlog"
    PROCESSOR_STALLED = "processor_stalled"
    SENDER_FAILURE = "sender_failure"
    MEMORY_PRESSURE = "memory_pressure"
    EVENT_LOOP_STALLED = "event_loop_stalled"
    END_TO_END_FAILURE = "end_to_end_failure"
    UNKNOWN = "unknown"


# ═══════════════════════════════════════════════════════════════════════════════
# 3. SUPERVISOR STATE MACHINE
# ═══════════════════════════════════════════════════════════════════════════════


class SupervisorState(str, Enum):
    """State machine for the supervisor lifecycle."""
    STOPPED = "stopped"
    STARTING = "starting"
    CONNECTING = "connecting"
    AUTHENTICATING = "authenticating"
    CONNECTED = "connected"
    DEGRADED = "degraded"
    RECOVERING = "recovering"
    CIRCUIT_OPEN = "circuit_open"
    SHUTTING_DOWN = "shutting_down"


# ═══════════════════════════════════════════════════════════════════════════════
# 4. RECOVERY LEVELS & RECORDS
# ═══════════════════════════════════════════════════════════════════════════════


class RecoveryLevel(int, Enum):
    """Hierarchical recovery levels — smallest safe action first."""
    OBSERVE = 0          # Wait/retry, do nothing
    REPAIR_COMPONENT = 1 # Restart listener, drain queue, reconnect sender
    RELOAD_PAGE = 2      # Reload WhatsApp page
    RECREATE_CONTEXT = 3 # Recreate browser context/page
    RESTART_BROWSER = 4  # Full Chromium restart
    RESTART_SUBSYSTEM = 5  # Full subsystem recreate
    ESCALATE = 6         # Cannot recover — escalate to application


# Recovery policy: failure_class → (initial_level, max_level)
RECOVERY_POLICY: Dict[FailureClass, tuple] = {
    FailureClass.NONE:                  (RecoveryLevel.OBSERVE, RecoveryLevel.OBSERVE),
    FailureClass.NETWORK_FAILURE:       (RecoveryLevel.OBSERVE, RecoveryLevel.OBSERVE),
    FailureClass.QR_REQUIRED:           (RecoveryLevel.OBSERVE, RecoveryLevel.OBSERVE),
    FailureClass.SESSION_EXPIRED:       (RecoveryLevel.RELOAD_PAGE, RecoveryLevel.RESTART_BROWSER),
    FailureClass.LISTENER_DEAD:         (RecoveryLevel.REPAIR_COMPONENT, RecoveryLevel.RESTART_BROWSER),
    FailureClass.SCANNER_STALLED:       (RecoveryLevel.REPAIR_COMPONENT, RecoveryLevel.RELOAD_PAGE),
    FailureClass.PAGE_UNRESPONSIVE:     (RecoveryLevel.RELOAD_PAGE, RecoveryLevel.RESTART_BROWSER),
    FailureClass.WHATSAPP_LOADING_STALL:(RecoveryLevel.RELOAD_PAGE, RecoveryLevel.RESTART_BROWSER),
    FailureClass.BROWSER_CRASH:         (RecoveryLevel.RESTART_BROWSER, RecoveryLevel.RESTART_SUBSYSTEM),
    FailureClass.QUEUE_BACKLOG:         (RecoveryLevel.REPAIR_COMPONENT, RecoveryLevel.REPAIR_COMPONENT),
    FailureClass.PROCESSOR_STALLED:     (RecoveryLevel.REPAIR_COMPONENT, RecoveryLevel.RELOAD_PAGE),
    FailureClass.SENDER_FAILURE:        (RecoveryLevel.REPAIR_COMPONENT, RecoveryLevel.RELOAD_PAGE),
    FailureClass.MEMORY_PRESSURE:       (RecoveryLevel.RELOAD_PAGE, RecoveryLevel.RESTART_BROWSER),
    FailureClass.EVENT_LOOP_STALLED:    (RecoveryLevel.OBSERVE, RecoveryLevel.RESTART_SUBSYSTEM),
    FailureClass.END_TO_END_FAILURE:    (RecoveryLevel.REPAIR_COMPONENT, RecoveryLevel.RESTART_BROWSER),
    FailureClass.UNKNOWN:               (RecoveryLevel.RELOAD_PAGE, RecoveryLevel.RESTART_SUBSYSTEM),
}


@dataclass
class RecoveryRecord:
    """Audit record for a single recovery attempt."""
    recovery_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    failure_class: FailureClass = FailureClass.UNKNOWN
    level: RecoveryLevel = RecoveryLevel.OBSERVE
    attempt: int = 0
    started_at: float = field(default_factory=time.time)
    ended_at: float = 0.0
    result: str = ""       # "success", "failed", "timeout", "cancelled"
    failure_reason: str = ""
    duration_ms: float = 0.0

    def finish(self, result: str, reason: str = "") -> None:
        self.ended_at = time.time()
        self.result = result
        self.failure_reason = reason
        self.duration_ms = (self.ended_at - self.started_at) * 1000

    def to_dict(self) -> Dict[str, Any]:
        return {
            "recovery_id": self.recovery_id,
            "failure_class": self.failure_class.value,
            "level": self.level.name,
            "attempt": self.attempt,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "result": self.result,
            "failure_reason": self.failure_reason,
            "duration_ms": round(self.duration_ms, 1),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 5. HEARTBEAT TIMESTAMPS
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class HeartbeatTimestamps:
    """Heartbeat timestamps for silent stall detection."""
    last_listener_activity: float = 0.0
    last_successful_scan: float = 0.0
    last_message_received: float = 0.0
    last_processing_started: float = 0.0
    last_processing_completed: float = 0.0
    last_send_attempt: float = 0.0
    last_successful_send: float = 0.0
    last_queue_progress: float = 0.0
    last_browser_response: float = 0.0
    last_end_to_end_success: float = 0.0
    last_event_loop_heartbeat: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        now = time.time()
        result = {}
        for name in [
            "last_listener_activity", "last_successful_scan",
            "last_message_received", "last_processing_started",
            "last_processing_completed", "last_send_attempt",
            "last_successful_send", "last_queue_progress",
            "last_browser_response", "last_end_to_end_success",
            "last_event_loop_heartbeat",
        ]:
            ts = getattr(self, name)
            result[name] = ts
            result[f"{name}_age_s"] = round(now - ts, 1) if ts > 0 else -1
        return result


# ═══════════════════════════════════════════════════════════════════════════════
# 6. FAILURE HISTORY (bounded windowed metrics)
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class FailureHistoryEntry:
    """A single failure event for history tracking."""
    timestamp: float = 0.0
    failure_class: FailureClass = FailureClass.UNKNOWN
    recovery_level: RecoveryLevel = RecoveryLevel.OBSERVE
    recovery_result: str = ""


class FailureHistory:
    """Bounded sliding-window failure history."""

    def __init__(self, max_entries: int = 200) -> None:
        self._entries: Deque[FailureHistoryEntry] = deque(maxlen=max_entries)
        self._recovery_records: Deque[RecoveryRecord] = deque(maxlen=100)
        self._browser_restarts: int = 0
        self._session_losses: int = 0
        self._listener_restarts: int = 0
        self._total_recoveries: int = 0

    def record_failure(self, entry: FailureHistoryEntry) -> None:
        self._entries.append(entry)

    def record_recovery(self, record: RecoveryRecord) -> None:
        self._recovery_records.append(record)
        self._total_recoveries += 1
        if record.level >= RecoveryLevel.RESTART_BROWSER:
            self._browser_restarts += 1
        if record.failure_class == FailureClass.SESSION_EXPIRED:
            self._session_losses += 1
        if record.failure_class in (FailureClass.LISTENER_DEAD, FailureClass.SCANNER_STALLED):
            self._listener_restarts += 1

    def failures_in_window(self, window_seconds: float) -> int:
        cutoff = time.time() - window_seconds
        return sum(1 for e in self._entries if e.timestamp > cutoff)

    def recoveries_in_window(self, window_seconds: float) -> int:
        cutoff = time.time() - window_seconds
        return sum(1 for r in self._recovery_records if r.started_at > cutoff)

    def last_successful_recovery(self) -> Optional[RecoveryRecord]:
        for r in reversed(self._recovery_records):
            if r.result == "success":
                return r
        return None

    def last_failed_recovery(self) -> Optional[RecoveryRecord]:
        for r in reversed(self._recovery_records):
            if r.result in ("failed", "timeout"):
                return r
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "failures_5m": self.failures_in_window(300),
            "failures_1h": self.failures_in_window(3600),
            "recoveries_1h": self.recoveries_in_window(3600),
            "browser_restarts": self._browser_restarts,
            "session_losses": self._session_losses,
            "listener_restarts": self._listener_restarts,
            "total_recoveries": self._total_recoveries,
            "recent_recoveries": [
                r.to_dict() for r in list(self._recovery_records)[-5:]
            ],
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 7. CIRCUIT BREAKER FOR RECOVERY
# ═══════════════════════════════════════════════════════════════════════════════


class RecoveryCircuitBreaker:
    """
    Circuit breaker preventing aggressive restart loops.

    CLOSED → repeated failures → OPEN → cooldown → HALF_OPEN → success → CLOSED
    """

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(
        self,
        failure_threshold: int = 5,
        cooldown_seconds: float = 120.0,
        success_threshold: int = 2,
        window_seconds: float = 600.0,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._cooldown_seconds = cooldown_seconds
        self._success_threshold = success_threshold
        self._window_seconds = window_seconds
        self._state = self.CLOSED
        self._failure_timestamps: Deque[float] = deque(maxlen=50)
        self._success_count = 0
        self._last_state_change: float = time.time()

    @property
    def state(self) -> str:
        if self._state == self.OPEN:
            if time.time() - self._last_state_change >= self._cooldown_seconds:
                self._transition(self.HALF_OPEN)
        return self._state

    def can_recover(self) -> bool:
        """Check if a recovery attempt is allowed."""
        state = self.state
        return state in (self.CLOSED, self.HALF_OPEN)

    def record_recovery_success(self) -> None:
        if self._state == self.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self._success_threshold:
                self._transition(self.CLOSED)
                self._failure_timestamps.clear()
        elif self._state == self.CLOSED:
            self._failure_timestamps.clear()

    def record_recovery_failure(self) -> None:
        now = time.time()
        self._failure_timestamps.append(now)

        if self._state == self.HALF_OPEN:
            self._transition(self.OPEN)
        elif self._state == self.CLOSED:
            # Count failures in window
            cutoff = now - self._window_seconds
            recent = sum(1 for t in self._failure_timestamps if t > cutoff)
            if recent >= self._failure_threshold:
                self._transition(self.OPEN)

    def _transition(self, new_state: str) -> None:
        if self._state != new_state:
            logger.warning(
                "Recovery circuit breaker: %s → %s",
                self._state, new_state,
            )
            self._state = new_state
            self._last_state_change = time.time()
            if new_state == self.HALF_OPEN:
                self._success_count = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "state": self.state,
            "failure_threshold": self._failure_threshold,
            "cooldown_seconds": self._cooldown_seconds,
            "recent_failures": len(self._failure_timestamps),
            "success_count": self._success_count,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 8. SUPERVISOR CONFIGURATION (tunable thresholds)
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class SupervisorConfig:
    """All tunable thresholds for the supervisor."""
    check_interval_seconds: float = 20.0
    browser_heartbeat_timeout: float = 15.0
    loading_stall_timeout: float = 90.0
    listener_stall_timeout: float = 90.0
    scanner_stall_timeout: float = 120.0
    processing_timeout: float = 300.0
    queue_age_threshold: float = 600.0
    memory_warning_mb: float = 500.0
    memory_critical_mb: float = 1000.0
    event_loop_lag_threshold: float = 2.0
    event_loop_lag_critical: float = 5.0
    listener_restart_timeout: float = 15.0
    page_reload_timeout: float = 20.0
    browser_restart_timeout: float = 60.0
    subsystem_restart_timeout: float = 90.0
    recovery_cooldown: float = 10.0
    circuit_breaker_threshold: int = 5
    circuit_breaker_cooldown: float = 120.0
    circuit_breaker_window: float = 600.0
    scheduled_recycle_interval: float = 86400.0  # 24h
    debounce_failure_count: int = 2  # require N consecutive before action
    network_check_host: str = "web.whatsapp.com"
    network_check_port: int = 443
    network_check_timeout: float = 3.0
    network_poll_interval: float = 5.0
    network_poll_max_wait: float = 60.0
    stabilization_wait_seconds: float = 3.0

    @classmethod
    def from_config(cls, config: Any) -> "SupervisorConfig":
        """Build from existing WhatsAppConfig."""
        sc = cls()
        if hasattr(config, "watchdog_interval"):
            sc.check_interval_seconds = float(config.watchdog_interval)
        if hasattr(config, "max_retry_backoff"):
            sc.circuit_breaker_cooldown = float(config.max_retry_backoff)
        if hasattr(config, "browser_timeout"):
            sc.browser_heartbeat_timeout = float(config.browser_timeout) / 2
        for attr in [
            "supervisor_loading_stall_timeout",
            "supervisor_listener_stall_timeout",
            "supervisor_scanner_stall_timeout",
            "supervisor_processing_timeout",
            "supervisor_circuit_breaker_threshold",
            "supervisor_circuit_breaker_cooldown",
            "supervisor_memory_critical_mb",
        ]:
            if hasattr(config, attr):
                target_field = attr.replace("supervisor_", "")
                if hasattr(sc, target_field):
                    val = getattr(config, attr)
                    field_type = type(getattr(sc, target_field))
                    setattr(sc, target_field, field_type(val))
        return sc


# ═══════════════════════════════════════════════════════════════════════════════
# 9. HEALTH ENGINE — probes every subsystem
# ═══════════════════════════════════════════════════════════════════════════════


class HealthEngine:
    """
    Probes every subsystem and builds a HealthSnapshot.

    Separates infrastructure health from service health.
    Uses heartbeat timestamps for silent stall detection.
    """

    def __init__(
        self,
        browser: WhatsAppBrowserAdapter,
        listener: Optional[Any] = None,
        config: Optional[SupervisorConfig] = None,
        network_check_fn: Optional[Callable[[], bool]] = None,
    ) -> None:
        self._browser = browser
        self._listener = listener
        self._config = config or SupervisorConfig()
        self._network_check_fn = network_check_fn
        self._heartbeats = HeartbeatTimestamps()
        self._event_loop_expected_wake: float = 0.0
        self._event_loop_lag_samples: Deque[float] = deque(maxlen=30)
        self._consecutive_failures: Dict[str, int] = {}

    @property
    def heartbeats(self) -> HeartbeatTimestamps:
        return self._heartbeats

    def update_heartbeat(self, name: str) -> None:
        """Update a heartbeat timestamp by name."""
        if hasattr(self._heartbeats, name):
            setattr(self._heartbeats, name, time.time())

    async def probe_all(self) -> HealthSnapshot:
        """Run all health probes and return a structured snapshot."""
        snap = HealthSnapshot(timestamp=time.time())

        # Event-loop health (measured inline — must be first)
        self._probe_event_loop(snap)

        # Infrastructure
        self._probe_network(snap)
        await self._probe_browser(snap)
        await self._probe_page(snap)
        self._probe_memory(snap)

        # Session
        await self._probe_authentication(snap)

        # Pipeline
        self._probe_listener(snap)
        self._probe_scanner(snap)
        self._probe_queue(snap)
        self._probe_processor(snap)
        self._probe_sender(snap)

        # End-to-end
        self._probe_end_to_end(snap)

        return snap

    def record_event_loop_wake(self) -> None:
        """Called at the top of each supervisor cycle to measure event-loop lag."""
        now = time.time()
        if self._event_loop_expected_wake > 0:
            lag = now - self._event_loop_expected_wake
            self._event_loop_lag_samples.append(lag)
        self._heartbeats.last_event_loop_heartbeat = now

    def set_expected_wake(self, expected: float) -> None:
        self._event_loop_expected_wake = expected

    # ── Infrastructure probes ─────────────────────────────────────────────────

    def _probe_network(self, snap: HealthSnapshot) -> None:
        if self._network_check_fn is not None:
            try:
                if self._network_check_fn():
                    snap.network.mark_healthy()
                else:
                    snap.network.mark_failed("Network check returned False")
            except Exception as e:
                snap.network.mark_failed(f"Network check error: {e}")
            return

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(self._config.network_check_timeout)
            s.connect((self._config.network_check_host, self._config.network_check_port))
            s.close()
            snap.network.mark_healthy()
        except Exception:
            try:
                s2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s2.settimeout(self._config.network_check_timeout)
                s2.connect(("8.8.8.8", 53))
                s2.close()
                snap.network.mark_degraded("WhatsApp unreachable but DNS works")
            except Exception:
                snap.network.mark_failed("Network offline")

    async def _probe_browser(self, snap: HealthSnapshot) -> None:
        page = self._browser.page
        if page is None:
            snap.browser.mark_failed("No browser page")
            return
        try:
            if page.is_closed():
                snap.browser.mark_failed("Page is closed")
                return
        except Exception:
            snap.browser.mark_failed("Cannot check page state")
            return
        snap.browser.mark_healthy()

    async def _probe_page(self, snap: HealthSnapshot) -> None:
        page = self._browser.page
        if page is None or snap.browser.status == SubsystemStatus.FAILED:
            snap.page.mark_failed("No live page")
            return
        try:
            result = await asyncio.wait_for(
                page.evaluate("() => document.readyState"),
                timeout=self._config.browser_heartbeat_timeout,
            )
            self._heartbeats.last_browser_response = time.time()
            if result in ("complete", "interactive"):
                snap.page.mark_healthy(f"readyState={result}")
            else:
                snap.page.mark_degraded(f"readyState={result}")
        except asyncio.TimeoutError:
            snap.page.mark_failed("Page evaluate timed out")
        except Exception as e:
            snap.page.mark_failed(f"Page unresponsive: {e}")

    def _probe_memory(self, snap: HealthSnapshot) -> None:
        try:
            pid = os.getpid()
            # macOS/Linux: read RSS from /proc or ps
            try:
                import resource
                usage = resource.getrusage(resource.RUSAGE_SELF)
                rss_mb = usage.ru_maxrss / (1024 * 1024) if hasattr(usage, 'ru_maxrss') else 0
                # macOS ru_maxrss is in bytes, Linux in KB
                import platform
                if platform.system() == "Darwin":
                    rss_mb = usage.ru_maxrss / (1024 * 1024)
                else:
                    rss_mb = usage.ru_maxrss / 1024
            except ImportError:
                rss_mb = 0

            if rss_mb <= 0:
                snap.memory.status = SubsystemStatus.UNKNOWN
                snap.memory.detail = "Cannot measure memory"
            elif rss_mb > self._config.memory_critical_mb:
                snap.memory.mark_failed(f"RSS={rss_mb:.0f}MB (critical)")
            elif rss_mb > self._config.memory_warning_mb:
                snap.memory.mark_degraded(f"RSS={rss_mb:.0f}MB (warning)")
            else:
                snap.memory.mark_healthy(f"RSS={rss_mb:.0f}MB")
        except Exception:
            snap.memory.status = SubsystemStatus.UNKNOWN

    def _probe_event_loop(self, snap: HealthSnapshot) -> None:
        if not self._event_loop_lag_samples:
            snap.event_loop.status = SubsystemStatus.UNKNOWN
            return

        recent_lags = list(self._event_loop_lag_samples)[-5:]
        avg_lag = sum(recent_lags) / len(recent_lags)

        if avg_lag > self._config.event_loop_lag_critical:
            snap.event_loop.mark_failed(f"avg_lag={avg_lag:.2f}s (critical)")
        elif avg_lag > self._config.event_loop_lag_threshold:
            snap.event_loop.mark_degraded(f"avg_lag={avg_lag:.2f}s")
        else:
            snap.event_loop.mark_healthy(f"avg_lag={avg_lag:.3f}s")

    # ── Session probes ────────────────────────────────────────────────────────

    async def _probe_authentication(self, snap: HealthSnapshot) -> None:
        if snap.page.status == SubsystemStatus.FAILED:
            snap.authentication.mark_failed("No live page to check auth")
            return
        try:
            status = await self._browser.detect_login_state()
            if status == "connected":
                snap.authentication.mark_healthy()
            elif status == "qr_required":
                snap.authentication.mark_waiting("QR scan required")
            elif status == "loading":
                snap.authentication.mark_degraded("WhatsApp page loading")
            elif status == "session_expired":
                snap.authentication.mark_failed("Session expired")
            else:
                snap.authentication.mark_failed(f"Login state: {status}")
        except Exception as e:
            snap.authentication.mark_failed(f"Auth check error: {e}")

    # ── Pipeline probes ───────────────────────────────────────────────────────

    def _probe_listener(self, snap: HealthSnapshot) -> None:
        if self._listener is None:
            snap.listener.status = SubsystemStatus.UNKNOWN
            return

        is_running = getattr(self._listener, "is_running", False)
        liveness = {}
        if hasattr(self._listener, "get_liveness"):
            liveness = self._listener.get_liveness()

        task_alive = liveness.get("task_alive", is_running)

        if not is_running or not task_alive:
            snap.listener.mark_failed(
                "task_alive=False" if is_running else "not running"
            )
        else:
            snap.listener.mark_healthy()
            self._heartbeats.last_listener_activity = time.time()

    def _probe_scanner(self, snap: HealthSnapshot) -> None:
        if self._listener is None:
            snap.scanner.status = SubsystemStatus.UNKNOWN
            return

        is_running = getattr(self._listener, "is_running", False)
        if not is_running:
            snap.scanner.status = SubsystemStatus.UNKNOWN
            return

        last_scan = getattr(self._listener, "last_successful_scan", 0.0)
        age = getattr(self._listener, "liveness_age_seconds", 0.0)
        consec_errors = getattr(self._listener, "_consecutive_scan_errors", 0)

        if last_scan > 0:
            self._heartbeats.last_successful_scan = last_scan

        if consec_errors >= 10:
            snap.scanner.mark_failed(f"consecutive_errors={consec_errors}")
        elif last_scan > 0 and age > self._config.scanner_stall_timeout:
            snap.scanner.mark_failed(f"stalled {age:.0f}s")
        elif last_scan > 0 and age > self._config.listener_stall_timeout:
            snap.scanner.mark_degraded(f"slow {age:.0f}s")
        elif last_scan > 0:
            snap.scanner.mark_healthy(f"age={age:.0f}s")
        else:
            snap.scanner.status = SubsystemStatus.UNKNOWN
            snap.scanner.detail = "No scan yet"

    def _probe_queue(self, snap: HealthSnapshot) -> None:
        if self._listener is None:
            snap.queue.status = SubsystemStatus.UNKNOWN
            return

        active = getattr(self._listener, "_active_processing", set())
        count = len(active)

        if count > 10:
            snap.queue.mark_degraded(f"active_processing={count}")
        else:
            snap.queue.mark_healthy(f"active_processing={count}")

    def _probe_processor(self, snap: HealthSnapshot) -> None:
        # Processor health is inferred from heartbeat age
        last_started = self._heartbeats.last_processing_started
        last_completed = self._heartbeats.last_processing_completed
        now = time.time()

        if last_started <= 0:
            snap.processor.status = SubsystemStatus.UNKNOWN
            snap.processor.detail = "No processing recorded yet"
            return

        if last_started > last_completed and last_completed > 0:
            in_progress_duration = now - last_started
            if in_progress_duration > self._config.processing_timeout:
                snap.processor.mark_failed(
                    f"Processing stuck for {in_progress_duration:.0f}s"
                )
                return

        snap.processor.mark_healthy()

    def _probe_sender(self, snap: HealthSnapshot) -> None:
        last_attempt = self._heartbeats.last_send_attempt
        last_success = self._heartbeats.last_successful_send

        if last_attempt <= 0:
            snap.sender.status = SubsystemStatus.UNKNOWN
            snap.sender.detail = "No send recorded yet"
            return

        if last_attempt > 0 and last_success <= 0:
            snap.sender.mark_degraded("Sent but no confirmed success")
        elif last_attempt > last_success:
            # Most recent send failed
            snap.sender.mark_degraded("Last send unconfirmed")
        else:
            snap.sender.mark_healthy()

    # ── End-to-end probe ──────────────────────────────────────────────────────

    def _probe_end_to_end(self, snap: HealthSnapshot) -> None:
        """
        End-to-end health: all of infrastructure + auth + pipeline must work.

        Uses internal heartbeat tracking — does NOT send unsolicited messages.
        """
        if not snap.infrastructure_healthy():
            snap.end_to_end.mark_failed("Infrastructure unhealthy")
            return

        if snap.authentication.status == SubsystemStatus.WAITING_FOR_AUTH:
            snap.end_to_end.status = SubsystemStatus.WAITING_FOR_AUTH
            snap.end_to_end.detail = "Awaiting QR authentication"
            return

        if snap.authentication.status != SubsystemStatus.HEALTHY:
            snap.end_to_end.mark_failed(f"Auth: {snap.authentication.detail}")
            return

        if not snap.pipeline_healthy():
            failed_components = [
                name for name, ss in [
                    ("listener", snap.listener), ("scanner", snap.scanner),
                    ("queue", snap.queue), ("processor", snap.processor),
                    ("sender", snap.sender),
                ]
                if ss.status == SubsystemStatus.FAILED
            ]
            snap.end_to_end.mark_failed(f"Pipeline: {','.join(failed_components)}")
            return

        last_e2e = self._heartbeats.last_end_to_end_success
        if last_e2e > 0:
            snap.end_to_end.mark_healthy(f"last_success={time.time() - last_e2e:.0f}s ago")
        else:
            # Connected and pipeline OK but no E2E success recorded yet — healthy but unverified
            snap.end_to_end.mark_healthy("Connected, awaiting first E2E")


# ═══════════════════════════════════════════════════════════════════════════════
# 10. THE SUPERVISOR
# ═══════════════════════════════════════════════════════════════════════════════


class WhatsAppSupervisor:
    """
    Production-grade self-healing WhatsApp supervisor.

    Replaces WhatsAppWatchdog with:
    - Structured health (HealthSnapshot per subsystem)
    - Failure classification (FailureClass)
    - State machine (SupervisorState)
    - Hierarchical recovery (RecoveryLevel 0–6)
    - Recovery verification (detect → recover → verify → escalate)
    - Circuit breaker (prevent restart loops)
    - Silent stall detection (heartbeat timestamps)
    - Failure history (bounded windowed metrics)
    - Event-loop health monitoring
    - Memory/resource monitoring
    - Adaptive browser recycling
    - Recovery concurrency safety
    - Recovery timeouts
    - Structured telemetry
    """

    def __init__(
        self,
        browser: WhatsAppBrowserAdapter,
        health: WhatsAppHealth,
        restart_callback: Optional[Callable[[], Awaitable[None]]] = None,
        listener: Optional[Any] = None,
        config: Optional[SupervisorConfig] = None,
        check_interval_seconds: float = 20.0,
        network_check_fn: Optional[Callable[[], bool]] = None,
    ) -> None:
        self._browser = browser
        self._legacy_health = health  # backward compat: update both
        self._restart_callback = restart_callback

        # Handle flexible argument orders (e.g. if 4th arg was check_interval_seconds)
        if isinstance(listener, (int, float)) and not isinstance(listener, bool):
            check_interval_seconds = float(listener)
            listener = None
        if isinstance(config, (int, float)) and not isinstance(config, bool):
            check_interval_seconds = float(config)
            config = None

        self._listener = listener
        self._config = config or SupervisorConfig()
        if check_interval_seconds != 20.0:
            self._config.check_interval_seconds = check_interval_seconds

        # Core engines
        self._health_engine = HealthEngine(
            browser=browser,
            listener=listener,
            config=self._config,
            network_check_fn=network_check_fn,
        )
        self._circuit_breaker = RecoveryCircuitBreaker(
            failure_threshold=self._config.circuit_breaker_threshold,
            cooldown_seconds=self._config.circuit_breaker_cooldown,
            window_seconds=self._config.circuit_breaker_window,
        )
        self._failure_history = FailureHistory()

        # State
        self._state = SupervisorState.STOPPED
        self._task: Optional[asyncio.Task] = None
        self._background_tasks: Set[asyncio.Task] = set()
        self._running = False
        self._is_recovering = False
        self._recovery_lock = asyncio.Lock()
        self._loading_since: Optional[float] = None
        self._last_recycle: float = time.time()
        self._last_snapshot: Optional[HealthSnapshot] = None

        # Debouncing: track consecutive failure detections per class
        self._consecutive_detections: Dict[FailureClass, int] = {}

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        return self._running and self._task is not None and not self._task.done()

    @property
    def supervisor_state(self) -> SupervisorState:
        return self._state

    @property
    def last_snapshot(self) -> Optional[HealthSnapshot]:
        return self._last_snapshot

    @property
    def heartbeats(self) -> HeartbeatTimestamps:
        return self._health_engine.heartbeats

    @property
    def _consecutive_failures(self) -> int:
        return sum(self._consecutive_detections.values())

    @_consecutive_failures.setter
    def _consecutive_failures(self, value: int) -> None:
        if value == 0:
            self._consecutive_detections.clear()

    def update_heartbeat(self, name: str) -> None:
        """Update a heartbeat timestamp (called by other components)."""
        self._health_engine.update_heartbeat(name)

    async def start(self) -> None:
        """Start the supervisor background loop."""
        if self._running or self.is_running:
            return

        self._running = True
        self._state = SupervisorState.STARTING
        self._legacy_health.set_watchdog_running(True)
        self._task = asyncio.create_task(
            self._supervisor_loop(), name="whatsapp_supervisor"
        )
        logger.info(
            "WhatsApp supervisor started (interval=%.0fs)",
            self._config.check_interval_seconds,
        )

        # Run an immediate health probe after brief grace period
        probe_task = asyncio.create_task(self._initial_probe(), name="whatsapp_supervisor_initial_probe")
        self._background_tasks.add(probe_task)
        probe_task.add_done_callback(self._background_tasks.discard)

    async def _initial_probe(self) -> None:
        await asyncio.sleep(3.0)
        if self._running:
            try:
                await self._run_health_cycle()
            except Exception as e:
                logger.debug("Initial supervisor probe error: %s", e)

    async def stop(self) -> None:
        """Stop the supervisor cleanly."""
        if not self._running and self._state == SupervisorState.STOPPED:
            return

        self._running = False
        self._state = SupervisorState.SHUTTING_DOWN
        self._legacy_health.set_watchdog_running(False)

        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            self._task = None

        # Clean up any pending background tasks
        for bg in list(self._background_tasks):
            if not bg.done():
                bg.cancel()
        if self._background_tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self._background_tasks, return_exceptions=True),
                    timeout=5.0,
                )
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            self._background_tasks.clear()

        self._state = SupervisorState.STOPPED
        logger.info("WhatsApp supervisor stopped")

    async def trigger_check(self) -> bool:
        """Run an immediate health check. Returns True if healthy."""
        snap = await self._run_health_cycle()
        return snap is not None and snap.service_healthy()

    async def _check_health(self) -> bool:
        """Backward compatibility alias for trigger_check."""
        return await self.trigger_check()

    def get_diagnostics(self) -> Dict[str, Any]:
        """Get comprehensive supervisor diagnostics."""
        return {
            "state": self._state.value,
            "is_recovering": self._is_recovering,
            "circuit_breaker": self._circuit_breaker.to_dict(),
            "failure_history": self._failure_history.to_dict(),
            "heartbeats": self._health_engine.heartbeats.to_dict(),
            "last_snapshot": self._last_snapshot.to_dict() if self._last_snapshot else None,
            "consecutive_detections": {
                k.value: v for k, v in self._consecutive_detections.items() if v > 0
            },
        }

    # ── Main Loop ─────────────────────────────────────────────────────────────

    async def _supervisor_loop(self) -> None:
        """Main supervisor loop — health probe + failure classification + recovery."""
        while self._running:
            try:
                # Measure event-loop lag
                self._health_engine.record_event_loop_wake()

                await self._run_health_cycle()

                # Schedule next wake
                expected_wake = time.time() + self._config.check_interval_seconds
                self._health_engine.set_expected_wake(expected_wake)
                await asyncio.sleep(self._config.check_interval_seconds)

                if not self._running:
                    break

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Supervisor loop error: %s", e, exc_info=True)
                self._legacy_health.record_error(f"Supervisor loop error: {e}")
                await asyncio.sleep(5.0)

    async def _run_health_cycle(self) -> Optional[HealthSnapshot]:
        """Single health cycle: probe → classify → recover."""
        if self._is_recovering:
            return self._last_snapshot

        # 1. Probe all subsystems
        snap = await self._health_engine.probe_all()
        self._last_snapshot = snap

        # 2. Sync legacy health object for backward compatibility
        self._sync_legacy_health(snap)

        # 3. Classify failures
        failure = self._classify_failure(snap)

        # 4. Update supervisor state machine
        self._update_state(snap, failure)

        if failure == FailureClass.NONE:
            # Clear consecutive detections on full health
            self._consecutive_detections.clear()
            if self._state == SupervisorState.CONNECTED:
                await self._check_adaptive_recycle(snap)
            return snap

        # 5. Debounce: require consecutive detections before acting
        count = self._consecutive_detections.get(failure, 0) + 1
        self._consecutive_detections[failure] = count

        required = self._config.debounce_failure_count
        # Special cases: some failures need instant action
        if failure in (FailureClass.BROWSER_CRASH, FailureClass.NETWORK_FAILURE):
            required = 1

        if count < required:
            logger.info(
                "Supervisor: %s detected (%d/%d, debouncing)",
                failure.value, count, required,
            )
            return snap

        # 6. Check circuit breaker
        if not self._circuit_breaker.can_recover():
            cb_state = self._circuit_breaker.state
            if self._state != SupervisorState.CIRCUIT_OPEN:
                self._state = SupervisorState.CIRCUIT_OPEN
                logger.warning(
                    "Supervisor: circuit breaker %s — suppressing recovery for %s",
                    cb_state, failure.value,
                )
            return snap

        # 7. Determine recovery level
        initial_level, max_level = RECOVERY_POLICY.get(
            failure, (RecoveryLevel.RELOAD_PAGE, RecoveryLevel.RESTART_SUBSYSTEM)
        )

        # If observe-only policy, don't attempt recovery
        if initial_level == RecoveryLevel.OBSERVE and max_level == RecoveryLevel.OBSERVE:
            self._log_telemetry(
                "observe", failure_class=failure.value,
                detail="Policy is observe-only",
            )
            return snap

        # 8. Execute hierarchical recovery
        await self._execute_hierarchical_recovery(failure, initial_level, max_level)

        # 9. Clear debounce counter after recovery attempt
        self._consecutive_detections[failure] = 0

        return snap

    # ── Failure Classification ────────────────────────────────────────────────

    def _classify_failure(self, snap: HealthSnapshot) -> FailureClass:
        """Classify the most significant failure from the health snapshot."""

        # Priority order: infrastructure → session → pipeline → e2e

        # Network
        if snap.network.status == SubsystemStatus.FAILED:
            return FailureClass.NETWORK_FAILURE

        # Browser
        if snap.browser.status == SubsystemStatus.FAILED:
            return FailureClass.BROWSER_CRASH

        # Page
        if snap.page.status == SubsystemStatus.FAILED:
            return FailureClass.PAGE_UNRESPONSIVE

        # Memory
        if snap.memory.status == SubsystemStatus.FAILED:
            return FailureClass.MEMORY_PRESSURE

        # Event loop
        if snap.event_loop.status == SubsystemStatus.FAILED:
            return FailureClass.EVENT_LOOP_STALLED

        # Authentication
        if snap.authentication.status == SubsystemStatus.WAITING_FOR_AUTH:
            return FailureClass.QR_REQUIRED
        if snap.authentication.status == SubsystemStatus.FAILED:
            detail = snap.authentication.detail.lower()
            if "unknown" in detail:
                return FailureClass.UNKNOWN
            return FailureClass.SESSION_EXPIRED
        if snap.authentication.status == SubsystemStatus.DEGRADED:
            detail = snap.authentication.detail.lower()
            if "loading" in detail:
                # Check loading stall
                now = time.time()
                if self._loading_since is None:
                    self._loading_since = now
                elif (now - self._loading_since) > self._config.loading_stall_timeout:
                    return FailureClass.WHATSAPP_LOADING_STALL
                return FailureClass.NONE  # Still loading, not a failure yet
            return FailureClass.SESSION_EXPIRED

        # Clear loading tracker if auth is not degraded-loading
        self._loading_since = None

        # Listener
        if snap.listener.status == SubsystemStatus.FAILED:
            return FailureClass.LISTENER_DEAD

        # Scanner
        if snap.scanner.status == SubsystemStatus.FAILED:
            return FailureClass.SCANNER_STALLED

        # Queue
        if snap.queue.status == SubsystemStatus.FAILED:
            return FailureClass.QUEUE_BACKLOG

        # Processor
        if snap.processor.status == SubsystemStatus.FAILED:
            return FailureClass.PROCESSOR_STALLED

        # Sender
        if snap.sender.status == SubsystemStatus.FAILED:
            return FailureClass.SENDER_FAILURE

        # End-to-end
        if snap.end_to_end.status == SubsystemStatus.FAILED:
            return FailureClass.END_TO_END_FAILURE

        return FailureClass.NONE

    # ── State Machine ─────────────────────────────────────────────────────────

    def _update_state(self, snap: HealthSnapshot, failure: FailureClass) -> None:
        """Update the supervisor state machine based on health and failure."""
        old = self._state
        if self._state == SupervisorState.SHUTTING_DOWN:
            return

        if self._is_recovering:
            self._state = SupervisorState.RECOVERING
        elif failure == FailureClass.NONE and snap.service_healthy():
            self._state = SupervisorState.CONNECTED
        elif failure == FailureClass.QR_REQUIRED:
            self._state = SupervisorState.AUTHENTICATING
        elif failure == FailureClass.NETWORK_FAILURE:
            self._state = SupervisorState.CONNECTING
        elif failure != FailureClass.NONE:
            if not self._circuit_breaker.can_recover():
                self._state = SupervisorState.CIRCUIT_OPEN
            else:
                self._state = SupervisorState.DEGRADED
        elif snap.authentication.status == SubsystemStatus.DEGRADED:
            self._state = SupervisorState.CONNECTING

        if old != self._state:
            self._log_telemetry(
                "state_transition", old=old.value, new=self._state.value,
                failure=failure.value,
            )

    # ── Hierarchical Recovery ─────────────────────────────────────────────────

    async def _execute_hierarchical_recovery(
        self,
        failure: FailureClass,
        initial_level: RecoveryLevel,
        max_level: RecoveryLevel,
    ) -> None:
        """Execute recovery starting at initial_level, escalating to max_level."""
        if self._is_recovering or self._recovery_lock.locked():
            return  # Another recovery in progress

        async with self._recovery_lock:
            self._is_recovering = True
            level = initial_level
            recovery_id = uuid.uuid4().hex[:12]

            try:
                attempt = 0
                while level <= max_level and self._running:
                    attempt += 1
                    record = RecoveryRecord(
                        recovery_id=recovery_id,
                        failure_class=failure,
                        level=level,
                        attempt=attempt,
                    )

                    self._log_telemetry(
                        "recovery_start",
                        recovery_id=recovery_id,
                        failure_class=failure.value,
                        level=level.name,
                        attempt=attempt,
                    )

                    # Protect active work before disruptive recovery
                    if level >= RecoveryLevel.RELOAD_PAGE:
                        await self._protect_active_work()

                    # Execute recovery action with timeout
                    success = await self._execute_recovery_action(level, failure, record)

                    if success:
                        # Verify recovery
                        verified = await self._verify_recovery(failure, level)
                        if verified:
                            record.finish("success")
                            self._failure_history.record_recovery(record)
                            self._circuit_breaker.record_recovery_success()
                            self._log_telemetry(
                                "recovery_success",
                                recovery_id=recovery_id,
                                level=level.name,
                                attempt=attempt,
                                duration_ms=record.duration_ms,
                            )
                            return
                        else:
                            record.finish("failed", "Verification failed")
                            self._log_telemetry(
                                "recovery_verify_failed",
                                recovery_id=recovery_id,
                                level=level.name,
                            )
                    else:
                        record.finish("failed", record.failure_reason or "Action failed")

                    self._failure_history.record_recovery(record)
                    self._failure_history.record_failure(FailureHistoryEntry(
                        timestamp=time.time(),
                        failure_class=failure,
                        recovery_level=level,
                        recovery_result=record.result,
                    ))
                    self._circuit_breaker.record_recovery_failure()

                    # Escalate to next level
                    next_val = level.value + 1
                    if next_val > max_level.value:
                        break
                    level = RecoveryLevel(next_val)

                    # Cooldown between escalation levels
                    await asyncio.sleep(self._config.recovery_cooldown)

                # All levels exhausted
                self._log_telemetry(
                    "recovery_exhausted",
                    recovery_id=recovery_id,
                    failure_class=failure.value,
                    final_level=level.name,
                )

            except asyncio.CancelledError:
                self._log_telemetry("recovery_cancelled", recovery_id=recovery_id)
            except Exception as e:
                logger.error(
                    "Recovery error (id=%s): %s", recovery_id, e, exc_info=True,
                )
                self._legacy_health.record_error(f"Recovery error: {e}")
            finally:
                self._is_recovering = False

    async def _execute_recovery_action(
        self,
        level: RecoveryLevel,
        failure: FailureClass,
        record: RecoveryRecord,
    ) -> bool:
        """Execute a single recovery action. Returns True if action completed."""
        timeout = self._get_recovery_timeout(level)

        try:
            if level == RecoveryLevel.OBSERVE:
                # Wait and re-check
                await asyncio.sleep(self._config.recovery_cooldown)
                return True

            elif level == RecoveryLevel.REPAIR_COMPONENT:
                return await asyncio.wait_for(
                    self._repair_component(failure), timeout=timeout,
                )

            elif level == RecoveryLevel.RELOAD_PAGE:
                return await asyncio.wait_for(
                    self._reload_page(), timeout=timeout,
                )

            elif level == RecoveryLevel.RECREATE_CONTEXT:
                # Same as reload for current architecture
                return await asyncio.wait_for(
                    self._reload_page(), timeout=timeout,
                )

            elif level == RecoveryLevel.RESTART_BROWSER:
                return await asyncio.wait_for(
                    self._restart_browser(), timeout=timeout,
                )

            elif level == RecoveryLevel.RESTART_SUBSYSTEM:
                return await asyncio.wait_for(
                    self._restart_subsystem(), timeout=timeout,
                )

            elif level == RecoveryLevel.ESCALATE:
                logger.critical(
                    "WhatsApp supervisor: escalation required for %s — "
                    "all recovery levels exhausted",
                    failure.value,
                )
                self._legacy_health.record_error(
                    f"ESCALATION: {failure.value} unrecoverable"
                )
                return False

        except asyncio.TimeoutError:
            record.finish("timeout", f"Recovery timed out after {timeout:.0f}s")
            self._log_telemetry(
                "recovery_timeout", level=level.name, timeout=timeout,
            )
            return False
        except Exception as e:
            record.failure_reason = str(e)
            logger.error("Recovery action error (level=%s): %s", level.name, e)
            return False

        return False

    async def _repair_component(self, failure: FailureClass) -> bool:
        """Level 1: Repair a specific component without page/browser restart."""
        if failure in (FailureClass.LISTENER_DEAD, FailureClass.SCANNER_STALLED):
            return await self._restart_listener()
        elif failure == FailureClass.QUEUE_BACKLOG:
            # Clear stuck processing items
            if self._listener and hasattr(self._listener, "_active_processing"):
                self._listener._active_processing.clear()
                logger.info("Supervisor: cleared active processing set")
            return True
        elif failure == FailureClass.PROCESSOR_STALLED:
            # Reset processing heartbeats
            self._health_engine.heartbeats.last_processing_started = 0.0
            self._health_engine.heartbeats.last_processing_completed = 0.0
            return True
        elif failure == FailureClass.SENDER_FAILURE:
            logger.info("Supervisor: sender failure — will retry on next cycle")
            return True
        elif failure == FailureClass.END_TO_END_FAILURE:
            return await self._restart_listener()
        else:
            logger.info("Supervisor: component repair not applicable for %s", failure.value)
            return True

    async def _restart_listener(self) -> bool:
        """Restart the listener task safely."""
        if self._listener is None:
            return False

        logger.info("Supervisor: restarting listener...")

        # Stop existing listener
        try:
            if hasattr(self._listener, "stop"):
                await self._listener.stop()
        except Exception as e:
            logger.debug("Error stopping listener: %s", e)

        await asyncio.sleep(1.0)

        # Start fresh listener
        try:
            if hasattr(self._listener, "start"):
                await self._listener.start()
                logger.info("Supervisor: listener restarted successfully")
                return True
        except Exception as e:
            logger.error("Supervisor: listener restart failed: %s", e)

        return False

    async def _reload_page(self) -> bool:
        """Level 2: Reload the WhatsApp Web page."""
        page = self._browser.page
        if page is None or page.is_closed():
            return False

        logger.info("Supervisor: reloading WhatsApp page...")
        try:
            await page.reload(
                wait_until="domcontentloaded",
                timeout=int(self._config.page_reload_timeout * 1000),
            )
            self._loading_since = None
            logger.info("Supervisor: page reload completed")
            return True
        except (asyncio.TimeoutError, TimeoutError):
            raise
        except Exception as e:
            logger.error("Supervisor: page reload failed: %s", e)
            return False

    async def _restart_browser(self) -> bool:
        """Level 4: Full Chromium browser restart via restart_callback."""
        if not self._restart_callback:
            logger.warning("Supervisor: no restart callback configured")
            return False

        # Check network before browser restart
        if not self._is_network_online():
            logger.warning("Supervisor: network offline, waiting before browser restart...")
            if not await self._wait_for_network():
                logger.warning("Supervisor: network still offline, proceeding anyway")

        logger.info("Supervisor: executing browser restart...")
        self._legacy_health.record_restart()

        try:
            await self._restart_callback()
            logger.info("Supervisor: browser restart completed")
            return True
        except Exception as e:
            logger.error("Supervisor: browser restart failed: %s", e)
            return False

    async def _restart_subsystem(self) -> bool:
        """Level 5: Full subsystem restart."""
        logger.warning("Supervisor: executing full subsystem restart...")
        return await self._restart_browser()

    async def _protect_active_work(self) -> None:
        """Pause intake and allow safe operations to finish before disruption."""
        if self._listener is None:
            return

        active = getattr(self._listener, "_active_processing", set())
        if active:
            logger.info(
                "Supervisor: waiting for %d active operations to finish...",
                len(active),
            )
            # Wait up to 10s for active work to finish
            for _ in range(20):
                active = getattr(self._listener, "_active_processing", set())
                if not active:
                    break
                await asyncio.sleep(0.5)
            else:
                logger.warning(
                    "Supervisor: proceeding with recovery, %d operations still active",
                    len(active),
                )

    # ── Recovery Verification ─────────────────────────────────────────────────

    async def _verify_recovery(
        self, failure: FailureClass, level: RecoveryLevel,
    ) -> bool:
        """Verify recovery succeeded: wait → re-probe → check."""
        # Stabilization wait
        stabilize_time = self._config.stabilization_wait_seconds
        if level >= RecoveryLevel.RESTART_BROWSER:
            stabilize_time *= 2.0
        elif level >= RecoveryLevel.RELOAD_PAGE:
            stabilize_time *= 1.5

        await asyncio.sleep(stabilize_time)

        if not self._running:
            return False

        # Re-probe
        snap = await self._health_engine.probe_all()
        self._last_snapshot = snap
        self._sync_legacy_health(snap)

        # Check if the specific failure is resolved
        new_failure = self._classify_failure(snap)

        if new_failure == FailureClass.NONE:
            return True

        # For listener repairs, also check listener is alive
        if failure in (FailureClass.LISTENER_DEAD, FailureClass.SCANNER_STALLED):
            if snap.listener.status == SubsystemStatus.HEALTHY:
                return True

        # For page/browser restarts, check page is responsive
        if level >= RecoveryLevel.RELOAD_PAGE:
            if snap.page.status == SubsystemStatus.HEALTHY:
                # The original failure may not be fully resolved yet,
                # but the infrastructure is recovered
                if new_failure in (FailureClass.QR_REQUIRED,):
                    return True  # QR required is expected after restart

        # Accept if new failure is less severe
        if new_failure != failure:
            logger.info(
                "Supervisor: recovery shifted failure from %s to %s",
                failure.value, new_failure.value,
            )
            # If it's a non-actionable state (QR required), consider recovered
            if new_failure in (FailureClass.QR_REQUIRED, FailureClass.NETWORK_FAILURE):
                return True

        return False

    # ── Adaptive Browser Recycling ────────────────────────────────────────────

    async def _check_adaptive_recycle(self, snap: HealthSnapshot) -> None:
        """Adaptive browser recycle — considers memory, age, activity, queue."""
        now = time.time()
        age = now - self._last_recycle

        if age < self._config.scheduled_recycle_interval:
            return

        # Don't recycle if active processing
        if self._listener:
            active = getattr(self._listener, "_active_processing", set())
            if active:
                return

        # Don't recycle during memory pressure — that's handled by recovery
        if snap.memory.status == SubsystemStatus.FAILED:
            return

        # Don't recycle if recent messages (within 5 min)
        if self._health_engine.heartbeats.last_message_received > 0:
            msg_age = now - self._health_engine.heartbeats.last_message_received
            if msg_age < 300:
                return

        # Safe to recycle
        logger.info("Supervisor: executing adaptive browser hygiene recycle...")
        try:
            page = self._browser.page
            if page and not page.is_closed():
                await page.reload(
                    wait_until="domcontentloaded", timeout=20000,
                )
                self._last_recycle = now
                logger.info("Supervisor: browser hygiene recycle completed")
        except Exception as e:
            logger.warning("Supervisor: browser recycle failed: %s", e)

    # ── Network Utilities ─────────────────────────────────────────────────────

    def _is_network_online(self) -> bool:
        if self._health_engine._network_check_fn is not None:
            try:
                return bool(self._health_engine._network_check_fn())
            except Exception:
                return False
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(self._config.network_check_timeout)
            s.connect((self._config.network_check_host, self._config.network_check_port))
            s.close()
            return True
        except Exception:
            try:
                s2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s2.settimeout(self._config.network_check_timeout)
                s2.connect(("8.8.8.8", 53))
                s2.close()
                return True
            except Exception:
                return False

    async def _wait_for_network(self) -> bool:
        """Poll network connectivity. Returns True if network comes online."""
        max_polls = int(self._config.network_poll_max_wait / self._config.network_poll_interval)
        for _ in range(max_polls):
            await asyncio.sleep(self._config.network_poll_interval)
            if not self._running:
                return False
            if self._is_network_online():
                logger.info("Supervisor: network connectivity restored")
                return True
        return False

    # ── Recovery Timeout ──────────────────────────────────────────────────────

    def _get_recovery_timeout(self, level: RecoveryLevel) -> float:
        timeouts = {
            RecoveryLevel.OBSERVE: 30.0,
            RecoveryLevel.REPAIR_COMPONENT: self._config.listener_restart_timeout,
            RecoveryLevel.RELOAD_PAGE: self._config.page_reload_timeout,
            RecoveryLevel.RECREATE_CONTEXT: self._config.page_reload_timeout,
            RecoveryLevel.RESTART_BROWSER: self._config.browser_restart_timeout,
            RecoveryLevel.RESTART_SUBSYSTEM: self._config.subsystem_restart_timeout,
            RecoveryLevel.ESCALATE: 10.0,
        }
        return timeouts.get(level, 60.0)

    # ── Legacy Health Sync ────────────────────────────────────────────────────

    def _sync_legacy_health(self, snap: HealthSnapshot) -> None:
        """Sync structured health snapshot back to legacy WhatsAppHealth object."""
        self._legacy_health.update_browser(
            alive=snap.browser.status == SubsystemStatus.HEALTHY,
            ready=snap.page.status == SubsystemStatus.HEALTHY,
        )
        self._legacy_health.set_authenticated(
            snap.authentication.status == SubsystemStatus.HEALTHY,
        )
        if self._listener:
            self._legacy_health.set_listener_running(
                snap.listener.status == SubsystemStatus.HEALTHY,
            )

        # Map supervisor state to legacy HealthState
        state_map = {
            SupervisorState.STOPPED: HealthState.STOPPED,
            SupervisorState.STARTING: HealthState.STARTING,
            SupervisorState.CONNECTING: HealthState.RECONNECTING,
            SupervisorState.AUTHENTICATING: HealthState.WAITING_FOR_QR,
            SupervisorState.CONNECTED: HealthState.CONNECTED,
            SupervisorState.DEGRADED: HealthState.ERROR,
            SupervisorState.RECOVERING: HealthState.RECONNECTING,
            SupervisorState.CIRCUIT_OPEN: HealthState.ERROR,
            SupervisorState.SHUTTING_DOWN: HealthState.STOPPED,
        }
        legacy_state = state_map.get(self._state, HealthState.ERROR)
        self._legacy_health.set_state(legacy_state)

    # ── Structured Telemetry ──────────────────────────────────────────────────

    def _log_telemetry(self, event: str, **kwargs: Any) -> None:
        """Emit structured supervisor telemetry."""
        parts = [f"SUPERVISOR:{event}"]
        for k, v in kwargs.items():
            parts.append(f"{k}={v}")
        logger.info(" | ".join(parts))
