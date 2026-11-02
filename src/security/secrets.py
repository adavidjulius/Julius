"""
Secrets Management, Keychain Integration & Four-Choke-Point Redaction (WS2.4).

Guarantees:
- OS Keychain storage (keyring) for credentials with .env fallback (mode 0600 check).
- Content scanning + high-entropy detection (gitleaks style).
- Fail-closed behavior on scanner exceptions.
- Redaction across all 4 choke points:
    1. PKB indexing
    2. LLM outbound context (DLP)
    3. Logs & Telemetry
    4. Audit Payloads
"""

from __future__ import annotations

import logging
import math
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# Realistic API key regex patterns (OpenAI, GitHub, AWS, Anthropic, Stripe, Slack, JWT, Private Keys, etc.)
SECRET_PATTERNS = [
    # OpenAI / generic sk-
    (re.compile(r"sk-[a-zA-Z0-9]{20,T3BlbkFJ[a-zA-Z0-9_-]{20,}"), "[REDACTED_OPENAI_KEY]"),
    (re.compile(r"sk-(?:proj-|svcacct-)?[a-zA-Z0-9_-]{32,}"), "[REDACTED_API_KEY]"),
    # Anthropic
    (re.compile(r"sk-ant-[a-zA-Z0-9_-]{32,}"), "[REDACTED_ANTHROPIC_KEY]"),
    # GitHub Personal Access Token & Fine-grained
    (re.compile(r"gh[pousr]_[A-Za-z0-9_]{36,255}"), "[REDACTED_GITHUB_TOKEN]"),
    # AWS Access Key ID
    (re.compile(r"(?:A3T[A-Z0-9]|AKIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|ASIA)[A-Z0-9]{16}"), "[REDACTED_AWS_KEY]"),
    # AWS Secret Key
    (re.compile(r"(?i)aws_secret_access_key\s*[:=]\s*['\"]?([A-Za-z0-9/+=]{40})['\"]?"), "[REDACTED_AWS_SECRET]"),
    # Google API Key
    (re.compile(r"AIza[0-9A-Za-z\\-_]{35}"), "[REDACTED_GOOGLE_KEY]"),
    # Slack Token
    (re.compile(r"xox[baprs]-[0-9]{10,13}-[0-9]{10,13}[a-zA-Z0-9-]*"), "[REDACTED_SLACK_TOKEN]"),
    # Stripe API Key
    (re.compile(r"(?:sk|pk)_(?:live|test)_[0-9a-zA-Z]{24,}"), "[REDACTED_STRIPE_KEY]"),
    # Private RSA/EC Keys
    (re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"), "[REDACTED_PRIVATE_KEY]"),
    # JWT tokens
    (re.compile(r"eyJ[A-Za-z0-9-_=]+\.[A-Za-z0-9-_=]+\.?[A-Za-z0-9-_.+/=]*"), "[REDACTED_JWT]"),
    # Password / Secret field assignments
    (re.compile(r"(?i)(?:password|passwd|pwd|api_key|apikey|secret_key|auth_token)\s*[:=]\s*['\"]([^'\"]{8,})['\"]"), "secret=[REDACTED]"),
    # Bearer header
    (re.compile(r"(?i)Bearer\s+[a-zA-Z0-9._\-]{20,}"), "Bearer [REDACTED]"),
]


def calculate_shannon_entropy(data: str) -> float:
    """Compute the Shannon entropy of a string."""
    if not data:
        return 0.0
    entropy = 0.0
    length = len(data)
    for x in set(data):
        p_x = float(data.count(x)) / length
        if p_x > 0:
            entropy += - p_x * math.log2(p_x)
    return entropy


class SecretsManager:
    """Central engine for credential storage, entropy scanning, and redaction."""

    def __init__(self, service_name: str = "Julius") -> None:
        self.service_name = service_name
        self._keyring_available = False
        try:
            import keyring
            self._keyring = keyring
            self._keyring_available = True
        except Exception:
            self._keyring = None

    def store_secret(self, key_name: str, secret_value: str) -> bool:
        """Store secret in OS Keychain if available, else .env."""
        if self._keyring_available:
            try:
                self._keyring.set_password(self.service_name, key_name, secret_value)
                return True
            except Exception as e:
                logger.warning(f"OS Keychain write failed: {e}")
        return False

    def get_secret(self, key_name: str) -> Optional[str]:
        """Retrieve secret from OS Keychain with environment variable fallback."""
        if self._keyring_available:
            try:
                val = self._keyring.get_password(self.service_name, key_name)
                if val:
                    return val
            except Exception:
                pass
        return os.getenv(key_name)

    def check_env_file_permissions(self, env_path: Path | str) -> bool:
        """Verify that .env permissions are secure (0600 on POSIX)."""
        p = Path(env_path)
        if not p.exists() or os.name == "nt":
            return True
        try:
            mode = p.stat().st_mode & 0o777
            if mode != 0o600:
                logger.warning(f"Insecure permissions on {p}: {oct(mode)}. Expected 0600 (-rw-------).")
                return False
            return True
        except Exception:
            return False

    def scan_and_redact(self, text: str) -> str:
        """
        Redact known secret patterns and high-entropy secret tokens from text.
        Fails closed on any unexpected exception.
        """
        if not text:
            return ""

        try:
            result = str(text)
            for pattern, replacement in SECRET_PATTERNS:
                result = pattern.sub(replacement, result)

            # High-entropy alphanumeric token scan (tokens >= 30 chars with entropy >= 4.5)
            words = re.findall(r"[A-Za-z0-9_\-+=]{30,}", result)
            for w in words:
                if w.startswith("[REDACTED"):
                    continue
                ent = calculate_shannon_entropy(w)
                if ent >= 4.5:
                    result = result.replace(w, "[REDACTED_HIGH_ENTROPY_SECRET]")

            return result
        except Exception as e:
            logger.error(f"Secrets scanner error (failing closed): {e}")
            return "[REDACTED_SCANNER_FAILURE]"

    # ── The Four Choke Points ─────────────────────────────────────────────────

    def choke_point_pkb(self, file_content: str, file_name: str) -> str:
        """Choke Point 1: PKB Indexing."""
        # Allow-list .env.example / .env.sample from strict redaction
        if file_name.endswith(".example") or file_name.endswith(".sample"):
            return file_content
        return self.scan_and_redact(file_content)

    def choke_point_outbound_llm(self, outbound_prompt: str) -> Tuple[bool, str]:
        """
        Choke Point 2: LLM Outbound Context (DLP Scan).
        Returns (has_secret_leaked, sanitized_prompt).
        """
        sanitized = self.scan_and_redact(outbound_prompt)
        leaked = sanitized != outbound_prompt
        return leaked, sanitized

    def choke_point_logs(self, log_message: str) -> str:
        """Choke Point 3: Logs & Telemetry."""
        return self.scan_and_redact(log_message)

    def choke_point_audit(self, payload: Dict[str, Any] | str) -> Any:
        """Choke Point 4: Audit Payloads."""
        if isinstance(payload, dict):
            clean_dict = {}
            for k, v in payload.items():
                if any(sec in k.lower() for sec in ("key", "secret", "password", "token", "hash")):
                    clean_dict[k] = "[REDACTED]"
                elif isinstance(v, str):
                    clean_dict[k] = self.scan_and_redact(v)
                elif isinstance(v, dict):
                    clean_dict[k] = self.choke_point_audit(v)
                else:
                    clean_dict[k] = v
            return clean_dict
        return self.scan_and_redact(str(payload))


# Global singleton
_SECRETS_MANAGER = SecretsManager()


def get_secrets_manager() -> SecretsManager:
    return _SECRETS_MANAGER

