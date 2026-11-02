"""
Julius WhatsApp Integration — Pipeline Telemetry.

Lightweight structured metrics for measuring latency across the
message processing pipeline. Records per-stage timestamps and
computes latency breakdowns.

Usage:
    span = PipelineSpan.start("MIT Gova", message_id="msg_abc")
    span.mark("dedup_check")
    span.mark("context_built")
    span.mark("llm_start")
    span.mark("llm_done")
    span.mark("send_complete")
    span.finish()
    print(span.report())
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Rolling window for aggregate stats
_MAX_SPANS_PER_CHAT = 50
_chat_spans: Dict[str, List["PipelineSpan"]] = {}


@dataclass
class PipelineSpan:
    """
    A single message processing span with per-stage timestamps.
    """
    chat_name: str = ""
    message_id: str = ""
    start_time: float = 0.0
    end_time: float = 0.0
    marks: Dict[str, float] = field(default_factory=dict)

    @classmethod
    def start(cls, chat_name: str, message_id: str = "") -> "PipelineSpan":
        return cls(
            chat_name=chat_name,
            message_id=message_id,
            start_time=time.time(),
        )

    def mark(self, stage: str) -> None:
        """Record a timestamp for a pipeline stage."""
        self.marks[stage] = time.time()

    def finish(self) -> None:
        """Finalize the span and record aggregate stats."""
        self.end_time = time.time()
        # Store in rolling window
        key = self.chat_name.lower().strip()
        if key not in _chat_spans:
            _chat_spans[key] = []
        spans = _chat_spans[key]
        spans.append(self)
        if len(spans) > _MAX_SPANS_PER_CHAT:
            _chat_spans[key] = spans[-_MAX_SPANS_PER_CHAT:]

        # Log latency breakdown
        total_ms = (self.end_time - self.start_time) * 1000
        logger.info(
            "PIPELINE [%s] total=%.0fms | %s",
            self.chat_name,
            total_ms,
            self._format_stages(),
        )

    def _format_stages(self) -> str:
        """Format stage durations as a readable string."""
        parts = []
        prev_time = self.start_time
        for stage, ts in self.marks.items():
            delta_ms = (ts - prev_time) * 1000
            parts.append(f"{stage}={delta_ms:.0f}ms")
            prev_time = ts
        return " | ".join(parts)

    @property
    def total_ms(self) -> float:
        if self.end_time <= 0:
            return (time.time() - self.start_time) * 1000
        return (self.end_time - self.start_time) * 1000

    def stage_ms(self, stage: str) -> Optional[float]:
        """Get milliseconds for a specific stage (from previous mark to this mark)."""
        ts = self.marks.get(stage)
        if ts is None:
            return None

        # Find the previous mark
        prev = self.start_time
        for s, t in self.marks.items():
            if s == stage:
                break
            prev = t
        return (ts - prev) * 1000

    def report(self) -> Dict[str, float]:
        """Generate a full latency report dict."""
        result = {
            "total_ms": self.total_ms,
            "chat_name": self.chat_name,
            "message_id": self.message_id,
        }
        prev = self.start_time
        for stage, ts in self.marks.items():
            result[f"T_{stage}"] = round((ts - prev) * 1000, 1)
            prev = ts
        return result


class LLMCircuitBreaker:
    """
    Simple circuit breaker for LLM calls.

    States:
    - CLOSED: Normal operation, calls pass through.
    - OPEN: Too many failures, calls are rejected immediately.
    - HALF_OPEN: After cooldown, allow one test call.

    Prevents cascade failures when the LLM provider is down.
    """

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(
        self,
        failure_threshold: int = 5,
        cooldown_seconds: float = 30.0,
        success_threshold: int = 2,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._cooldown_seconds = cooldown_seconds
        self._success_threshold = success_threshold
        self._state = self.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: float = 0.0

    @property
    def state(self) -> str:
        if self._state == self.OPEN:
            # Check if cooldown has elapsed
            if time.time() - self._last_failure_time >= self._cooldown_seconds:
                self._state = self.HALF_OPEN
                self._success_count = 0
        return self._state

    def can_execute(self) -> bool:
        """Check if a call should be allowed."""
        state = self.state
        if state == self.CLOSED:
            return True
        if state == self.HALF_OPEN:
            return True
        return False  # OPEN

    def record_success(self) -> None:
        """Record a successful call."""
        if self._state == self.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self._success_threshold:
                self._state = self.CLOSED
                self._failure_count = 0
                logger.info("LLM circuit breaker CLOSED (recovered)")
        else:
            self._failure_count = 0

    def record_failure(self) -> None:
        """Record a failed call."""
        self._failure_count += 1
        self._last_failure_time = time.time()

        if self._state == self.HALF_OPEN:
            self._state = self.OPEN
            logger.warning("LLM circuit breaker OPEN (half-open test failed)")
        elif self._failure_count >= self._failure_threshold:
            self._state = self.OPEN
            logger.warning(
                "LLM circuit breaker OPEN (failures=%d, cooldown=%.0fs)",
                self._failure_count, self._cooldown_seconds,
            )

    def to_dict(self) -> Dict[str, any]:
        return {
            "state": self.state,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "cooldown_seconds": self._cooldown_seconds,
        }


def get_aggregate_stats(chat_name: Optional[str] = None) -> Dict[str, any]:
    """
    Get aggregate pipeline stats.

    If chat_name is provided, returns stats for that chat.
    Otherwise returns global stats across all chats.
    """
    if chat_name:
        key = chat_name.lower().strip()
        spans = _chat_spans.get(key, [])
    else:
        spans = []
        for v in _chat_spans.values():
            spans.extend(v)

    if not spans:
        return {"count": 0}

    totals = [s.total_ms for s in spans]
    totals.sort()
    n = len(totals)

    return {
        "count": n,
        "avg_ms": round(sum(totals) / n, 1),
        "p50_ms": round(totals[n // 2], 1),
        "p95_ms": round(totals[int(n * 0.95)], 1) if n >= 20 else None,
        "p99_ms": round(totals[int(n * 0.99)], 1) if n >= 100 else None,
        "min_ms": round(totals[0], 1),
        "max_ms": round(totals[-1], 1),
    }
