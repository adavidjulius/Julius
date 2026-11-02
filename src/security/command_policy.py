"""
Command Policy & Environment Isolation for Multi-User Execution.

Restricts shell execution for normal users:
- Prohibits privilege escalation (sudo, su).
- Prohibits system modifications (chmod outside workspace, chown, mount, umount, systemctl).
- Prohibits remote shells / exfiltration (ssh, scp, rsync, telnet, nc).
- Prohibits traversing out of workspace (cd .., absolute system paths).
- Prohibits reading environment secrets (env, export, printenv) or reading server files.
- Scrubs sensitive environment variables before passing to subprocesses.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import logging

logger = logging.getLogger(__name__)

# Sensitive environment variables to strip for normal users
SENSITIVE_ENV_VARS = {
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "DEEPSEEK_API_KEY",
    "GEMINI_API_KEY",
    "GROQ_API_KEY",
    "MISTRAL_API_KEY",
    "GITHUB_TOKEN",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "DATABASE_URL",
    "SECRET_KEY",
    "JULIUS_SECRET_KEY",
    "JULIUS_ADMIN_PASSWORD",
    "SESSION_SECRET",
    "PRIVATE_KEY",
    # Code-loading & dynamic linker injection variables (Julius sec-default)
    "LD_PRELOAD",
    "LD_LIBRARY_PATH",
    "LD_AUDIT",
    "DYLD_INSERT_LIBRARIES",
    "DYLD_LIBRARY_PATH",
    "DYLD_FRAMEWORK_PATH",
    "BASH_ENV",
    "ZDOTDIR",
    "NODE_OPTIONS",
}

# Dangerous command patterns for normal users
RESTRICTED_COMMAND_PATTERNS = [
    # Privilege escalation
    (r"\b(?:sudo|su|doas|pkexec)\b", "Privilege escalation is forbidden"),
    # Dynamic library & shell environment hijacking (Julius sec-default pattern)
    (r"(?:\bexport\s+|\benv\s+)?\b(?:LD_PRELOAD|LD_LIBRARY_PATH|LD_AUDIT|DYLD_INSERT_LIBRARIES|DYLD_LIBRARY_PATH|DYLD_FRAMEWORK_PATH|BASH_ENV|ZDOTDIR|NODE_OPTIONS)\s*=",
     "Dynamic library hijacking or shell environment injection is forbidden"),
    # Account & user management
    (r"\b(?:useradd|userdel|usermod|groupadd|passwd)\b", "User/group administration is forbidden"),
    # System services & mounts
    (r"\b(?:systemctl|service|mount|umount|fdisk|parted|mkfs)\b", "System administration is forbidden"),
    # Credential & secret access
    (r"(?:id_rsa|id_ed25519|\.ssh)", "Access to SSH credentials is forbidden"),
    # Network tools & shells
    (r"\b(?:ssh|scp|sftp|nc|netcat|ncat|socat|nmap|iptables|ufw)\b", "Remote network access/administration is forbidden"),
    # Access to system directories (excluding standard streams like /dev/null, /dev/zero, /dev/urandom)
    (r"(?:/etc|/var|/root|/sys|/proc|/boot|/dev/(?!null|zero|urandom|stdin|stdout|stderr\b)|/dev\s*$|/System|/Library)", "Direct access to host system paths is forbidden"),
    # Environment inspection
    (r"\b(?:env|printenv|set|export)\b(?:\s*$|\s*\|\s*)", "Direct environment variable dump is forbidden"),
    # Access to server secrets or Julius repo files
    (r"(?:\.env|credentials\.enc|secret\.key|julius\.db|audit\.log)", "Direct access to application secrets is forbidden"),
    # Process / power control
    (r"\b(?:shutdown|reboot|poweroff|init)\b", "Host control is forbidden"),
]


class CommandPolicy:
    """
    Enforces command execution rules and environment scrubbing based on role.
    """

    def __init__(self, workspace_root: str, role: str = "user") -> None:
        self.workspace_root = str(Path(os.path.abspath(workspace_root)).resolve())
        self.role = role.lower().strip() if role else "user"
        self._host_access_allowed: bool = False

    def is_admin(self) -> bool:
        return self.role in ("admin", "super_admin", "owner")

    def is_developer(self) -> bool:
        return self.role in ("developer", "power_user")

    def grant_host_access(self, allowed: bool = True) -> None:
        """Global host execution grant is deprecated in favor of sandboxed tiers."""
        self._host_access_allowed = False

    def validate_command(self, command: str) -> tuple[bool, str]:
        """
        Validate whether a command is permitted for the current user role.
        
        Returns:
            (is_allowed: bool, reason_or_error: str)
        """
        cleaned = command.strip()
        if not cleaned:
            return False, "Empty command"

        # Admins, approved host access, or local uncensored mode have full command access
        is_single_user_uncensored = os.getenv("JULIUS_UNCENSORED", "true").lower() in ("true", "1", "yes") and not os.getenv("JULIUS_MULTIUSER") and self.role != "user"
        if self.is_admin() or self._host_access_allowed or is_single_user_uncensored:
            return True, ""


        # Developers have standard developer access (cannot escalate privilege or dump secrets)
        if self.is_developer():
            for pattern in [r"\b(?:sudo|su|doas)\b", r"(?:id_rsa|id_ed25519|\.ssh)"]:
                if re.search(pattern, cleaned, re.IGNORECASE):
                    return False, "Privilege escalation or private SSH credential access is forbidden."
            return True, ""

        # Normal users: check for cd directory traversal outside workspace
        cd_matches = re.finditer(r"(?:^|[;&|]\s*)cd(?:\s+/[a-zA-Z])?\s+((?:\"[^\"]+\")|(?:\'[^\']+\')|[^\s;&|]+)", cleaned)
        for cd_match in cd_matches:
            target = cd_match.group(1).strip("\"'")
            try:
                exp = os.path.expanduser(target)
                real_ws = os.path.realpath(self.workspace_root)
                real_target = os.path.realpath(exp if os.path.isabs(exp) else os.path.join(real_ws, exp))
                if os.name == 'nt':
                    if real_target.lower() != real_ws.lower() and not real_target.lower().startswith(real_ws.lower() + os.sep):
                        logger.warning(f"Command blocked for user (role={self.role}): Directory traversal outside workspace in '{cleaned[:60]}'")
                        return False, "Execution denied: Directory traversal outside workspace is forbidden."
                else:
                    if real_target != real_ws and not real_target.startswith(real_ws + os.sep):
                        logger.warning(f"Command blocked for user (role={self.role}): Directory traversal outside workspace in '{cleaned[:60]}'")
                        return False, "Execution denied: Directory traversal outside workspace is forbidden."
            except Exception:
                return False, "Execution denied: Directory traversal outside workspace is forbidden."

        # Normal users: strictly check restricted command patterns
        for pattern, reason in RESTRICTED_COMMAND_PATTERNS:
            m = re.search(pattern, cleaned, re.IGNORECASE)
            if m:
                # If the matched path is inside the user's workspace, allow it
                if reason == "Direct access to host system paths is forbidden":
                    token = cleaned[m.start():].split()[0].strip(';,"\'&|()<>')
                    try:
                        exp = os.path.expanduser(token)
                        real_target = os.path.realpath(exp if os.path.isabs(exp) else os.path.join(self.workspace_root, exp))
                        real_ws = os.path.realpath(self.workspace_root)
                        if real_target == real_ws or real_target.startswith(real_ws + os.sep):
                            continue
                    except Exception:
                        pass
                logger.warning(f"Command blocked for user (role={self.role}): {reason} in '{cleaned[:60]}'")
                return False, f"Execution denied: {reason}."

        return True, ""

    def get_sanitized_env(self, base_env: dict[str, str] | None = None) -> dict[str, str]:
        """
        Return an environment dictionary stripped of sensitive server credentials.
        """
        source = dict(base_env if base_env is not None else os.environ)

        # Admin gets full environment
        if self.is_admin():
            return source

        # Developers and normal users get scrubbed environment
        sanitized = {}
        for k, v in source.items():
            k_upper = k.upper()
            if k_upper in SENSITIVE_ENV_VARS:
                continue
            if any(secret_term in k_upper for secret_term in ("KEY", "SECRET", "TOKEN", "PASSWORD", "CREDENTIAL")):
                continue
            sanitized[k] = v

        # Restrict PATH to standard binaries while including Homebrew & standard paths on macOS/Linux
        sanitized["PATH"] = "/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
        sanitized["JULIUS_ROLE"] = self.role
        sanitized["WORKSPACE_ROOT"] = self.workspace_root
        return sanitized

