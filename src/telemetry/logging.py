"""
Structured JSON Logging with Redaction & Correlation IDs (WS5).

Formats logs as JSON when JULIUS_LOG_FORMAT=json or as clean human-readable text.
Attaches correlation IDs: session_id, job_id, step_id.
Enforces Choke Point 3 credential redaction.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from src.security.secrets import get_secrets_manager

# Context variables for correlation IDs
_CORRELATION_CONTEXT: Dict[str, str] = {
    "session_id": "none",
    "job_id": "none",
    "step_id": "0",
}


def set_correlation_context(session_id: Optional[str] = None, job_id: Optional[str] = None, step_id: Optional[str] = None) -> None:
    """Set correlation IDs for subsequent log messages."""
    if session_id:
        _CORRELATION_CONTEXT["session_id"] = session_id
    if job_id:
        _CORRELATION_CONTEXT["job_id"] = job_id
    if step_id:
        _CORRELATION_CONTEXT["step_id"] = str(step_id)


class RedactingJSONFormatter(logging.Formatter):
    """Formats log records as structured JSON with sensitive credentials scrubbed."""

    def __init__(self) -> None:
        super().__init__()
        self.secrets_manager = get_secrets_manager()

    def format(self, record: logging.LogRecord) -> str:
        msg = record.getMessage()
        clean_msg = self.secrets_manager.choke_point_logs(msg)

        log_entry: Dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": clean_msg,
            "session_id": getattr(record, "session_id", _CORRELATION_CONTEXT["session_id"]),
            "job_id": getattr(record, "job_id", _CORRELATION_CONTEXT["job_id"]),
            "step_id": getattr(record, "step_id", _CORRELATION_CONTEXT["step_id"]),
        }

        if record.exc_info:
            log_entry["exception"] = self.secrets_manager.choke_point_logs(self.formatException(record.exc_info))

        return json.dumps(log_entry, ensure_ascii=False)


def configure_logging(level: str = "INFO", log_format: Optional[str] = None) -> None:
    """Configure root logger with either JSON formatter or clean standard formatter."""
    fmt = log_format or os.getenv("JULIUS_LOG_FORMAT", "text").lower()
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove existing handlers to avoid duplicates
    for h in list(root.handlers):
        root.removeHandler(h)

    handler = logging.StreamHandler(sys.stdout)
    if fmt == "json":
        handler.setFormatter(RedactingJSONFormatter())
    else:
        handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s [%(name)s] %(message)s"))

    root.addHandler(handler)

