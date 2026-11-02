"""
Julius Structured Error Taxonomy (WS4.2).

Defines standard error codes (JUL-xxx), user-safe error messages,
actionable remediation hints, and retryable flags.
"""

from __future__ import annotations

from typing import Any, Optional


class JuliusError(Exception):
    """
    Standard base exception for all Julius subsystems.

    Attributes:
        code: Machine-readable error code (e.g. 'JUL-PROV-001', 'JUL-POL-003').
        message: User-safe, human-readable error description.
        hint: Optional actionable hint guiding user resolution.
        retryable: Whether this error can be retried automatically.
        details: Redacted diagnostic dictionary for logging and support bundles.
    """

    def __init__(
        self,
        code: str,
        message: str,
        hint: Optional[str] = None,
        retryable: bool = False,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message
        self.hint = hint
        self.retryable = retryable
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        """Convert error to a structured dictionary representation."""
        return {
            "code": self.code,
            "message": self.message,
            "hint": self.hint,
            "retryable": self.retryable,
            "details": self.details,
        }


# ── Domain-Specific Error Subclasses ──────────────────────────────────────────

class ProviderError(JuliusError):
    """LLM provider API, communication, authentication or rate-limit error."""

    def __init__(
        self,
        code: str = "JUL-PROV-000",
        message: str = "Provider error occurred",
        hint: Optional[str] = None,
        retryable: bool = False,
        provider: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        det = details or {}
        if provider:
            det["provider"] = provider
        super().__init__(code=code, message=message, hint=hint, retryable=retryable, details=det)


class PolicyViolationError(JuliusError):
    """Security policy enforcement or sandbox boundary violation."""

    def __init__(
        self,
        code: str = "JUL-POL-000",
        message: str = "Operation denied by security policy",
        hint: Optional[str] = None,
        rule: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        det = details or {}
        if rule:
            det["rule"] = rule
        super().__init__(code=code, message=message, hint=hint, retryable=False, details=det)


class ConfigError(JuliusError):
    """Configuration parsing, validation, or schema failure."""

    def __init__(
        self,
        code: str = "JUL-CFG-000",
        message: str = "Configuration error",
        hint: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(code=code, message=message, hint=hint, retryable=False, details=details)


class DatabaseError(JuliusError):
    """Database connection, transaction, schema migration or integrity failure."""

    def __init__(
        self,
        code: str = "JUL-DB-000",
        message: str = "Database error",
        hint: Optional[str] = None,
        retryable: bool = False,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(code=code, message=message, hint=hint, retryable=retryable, details=details)


class AgentBudgetError(JuliusError):
    """Agent budget exceeded or infinite loop detected."""

    def __init__(
        self,
        code: str = "JUL-AGT-000",
        message: str = "Agent execution budget exceeded",
        hint: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(code=code, message=message, hint=hint, retryable=False, details=details)


class LicenseError(JuliusError):
    """License validation, expiration, or entitlement verification failure."""

    def __init__(
        self,
        code: str = "JUL-LIC-000",
        message: str = "License validation failure",
        hint: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(code=code, message=message, hint=hint, retryable=False, details=details)


# ── Canonical Error Catalog ───────────────────────────────────────────────────

# Provider errors
JUL_PROV_AUTH_FAILED = "JUL-PROV-001"
JUL_PROV_RATE_LIMITED = "JUL-PROV-002"
JUL_PROV_TIMEOUT = "JUL-PROV-003"
JUL_PROV_CONTEXT_TOO_LARGE = "JUL-PROV-004"
JUL_PROV_UNAVAILABLE = "JUL-PROV-005"
JUL_PROV_BAD_REQUEST = "JUL-PROV-006"

# Policy errors
JUL_POL_PATH_DENIED = "JUL-POL-001"
JUL_POL_APPROVAL_REQUIRED = "JUL-POL-002"
JUL_POL_HARD_DENY_PATH = "JUL-POL-003"
JUL_POL_COMMAND_FORBIDDEN = "JUL-POL-004"
JUL_POL_TAINT_RESTRICTION = "JUL-POL-005"

# Config errors
JUL_CFG_INVALID_SETTING = "JUL-CFG-001"
JUL_CFG_MISSING_KEY = "JUL-CFG-002"
JUL_CFG_SYNTAX_ERROR = "JUL-CFG-003"

# Database errors
JUL_DB_MIGRATION_FAILED = "JUL-DB-001"
JUL_DB_INTEGRITY_CHECK_FAILED = "JUL-DB-002"
JUL_DB_LOCKED = "JUL-DB-003"

# Agent loop errors
JUL_AGT_BUDGET_EXCEEDED = "JUL-AGT-001"
JUL_AGT_LOOP_DETECTED = "JUL-AGT-002"
JUL_AGT_CHECKPOINT_FAILED = "JUL-AGT-003"

# License errors
JUL_LIC_EXPIRED = "JUL-LIC-001"
JUL_LIC_INVALID = "JUL-LIC-002"
JUL_LIC_SEAT_EXCEEDED = "JUL-LIC-003"

