"""Lightweight trace context for request correlation across the Julius system.

Finding #13: Provides correlation IDs (trace_id) that can be propagated across
dashboard API requests, SearXNG searches, LLM calls, and agent action executions.

Usage:
    from .trace_context import new_trace_id, get_trace_id, TraceIdFilter

    # At the start of a request / agent run:
    tid = new_trace_id()

    # Anywhere in the same async context:
    current = get_trace_id()

    # Add trace IDs to all log messages:
    import logging
    handler = logging.StreamHandler()
    handler.addFilter(TraceIdFilter())
    handler.setFormatter(logging.Formatter('%(asctime)s [%(trace_id)s] %(name)s %(message)s'))
"""

from __future__ import annotations

import contextvars
import logging
import uuid


# Context variable for the current trace/request correlation ID
trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar('trace_id', default='')


def new_trace_id() -> str:
    """Generate a new trace ID and set it in the current context."""
    tid = uuid.uuid4().hex[:12]
    trace_id_var.set(tid)
    return tid


def get_trace_id() -> str:
    """Get the current trace ID, or generate a new one if none exists."""
    current = trace_id_var.get()
    if not current:
        return new_trace_id()
    return current


class TraceIdFilter(logging.Filter):
    """Logging filter that injects the current trace_id into all log records.

    Add this filter to a handler to automatically include trace_id in log output:

        handler.addFilter(TraceIdFilter())
        # Then use %(trace_id)s in your formatter
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = trace_id_var.get() or '-'  # type: ignore[attr-defined]
        return True
