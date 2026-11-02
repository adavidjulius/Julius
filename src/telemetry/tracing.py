"""
OpenTelemetry Distributed Tracing Instrumentation (WS5).

Strictly opt-in (disabled by default).
Provides standard span contexts for:
- agent.step
- llm.call
- tool.exec
- pkb.query
- policy.decide
"""

from __future__ import annotations

import contextlib
import logging
import time
from typing import Any, Dict, Iterator, Optional

logger = logging.getLogger(__name__)

_OTEL_AVAILABLE = False
try:
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode
    _OTEL_AVAILABLE = True
except ImportError:
    pass


class Tracer:
    """Wrapper around OpenTelemetry with zero-overhead fallback when disabled."""

    def __init__(self, service_name: str = "julius", enabled: bool = False) -> None:
        self.enabled = enabled and _OTEL_AVAILABLE
        self._tracer = trace.get_tracer(service_name) if self.enabled else None

    @contextlib.contextmanager
    def span(self, name: str, attributes: Optional[Dict[str, Any]] = None) -> Iterator[Any]:
        """Context manager creating an OpenTelemetry span or no-op block."""
        if not self.enabled or not self._tracer:
            yield None
            return

        with self._tracer.start_as_current_span(name) as sp:
            if attributes:
                for k, v in attributes.items():
                    # Enforce label hygiene: never record passwords, raw tokens, or high-cardinality keys
                    if not any(sec in k.lower() for sec in ("key", "secret", "token", "password")):
                        sp.set_attribute(k, str(v))
            try:
                yield sp
            except Exception as exc:
                sp.set_status(Status(StatusCode.ERROR, str(exc)))
                sp.record_exception(exc)
                raise


# Global singleton tracer
_GLOBAL_TRACER: Optional[Tracer] = None


def get_tracer() -> Tracer:
    global _GLOBAL_TRACER
    if _GLOBAL_TRACER is None:
        from src.settings import get_settings
        settings = get_settings()
        _GLOBAL_TRACER = Tracer(enabled=settings.telemetry.enabled)
    return _GLOBAL_TRACER

