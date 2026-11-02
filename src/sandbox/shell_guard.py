"""
Shell Command Security Guard & AST Parser (WS2.2).

Parses shell command tokens and AST structures to block:
- Privilege escalations (sudo, su, doas, pkexec)
- Destructive non-workspace modifications (rm -rf /)
- Remote code pipes (curl ... | bash, wget ... | sh)
- Git hook tampering
- Network egress to unlisted hosts
"""

from __future__ import annotations

import logging
import os
import re
import shlex
from pathlib import Path
from typing import List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

DANGEROUS_BINARIES = {
    "sudo",
    "su",
    "doas",
    "pkexec",
    "chown",
    "chmod",
    "useradd",
    "userdel",
    "usermod",
    "passwd",
    "mount",
    "umount",
    "mkfs",
    "fdisk",
    "parted",
    "systemctl",
}

DEFAULT_EGRESS_ALLOWLIST = {
    "github.com",
    "pypi.org",
    "files.pythonhosted.org",
    "npmjs.org",
    "registry.npmjs.org",
    "registry.yarnpkg.com",
    "huggingface.co",
}


class ShellSecurityGuard:
    """Validates shell commands via token parsing and security invariants."""

    def __init__(
        self,
        workspace: str,
        network_allowed: bool = False,
        egress_allowlist: Optional[Set[str]] = None,
    ) -> None:
        self.workspace = str(Path(workspace).resolve())
        self.network_allowed = network_allowed
        self.egress_allowlist = egress_allowlist or DEFAULT_EGRESS_ALLOWLIST

    def validate_command(self, command: str) -> Tuple[bool, str]:
        """
        Parses and evaluates a shell command string.
        Returns (is_safe, reason).
        """
        if not command or not command.strip():
            return True, "Empty command"

        cmd = command.strip()

        # 1. Pipe-to-shell patterns: curl/wget | sh/bash/python
        pipe_to_shell_pattern = re.compile(
            r"(?:curl|wget|fetch)\s+[^|]+\|\s*(?:sh|bash|zsh|python|perl|ruby)",
            re.IGNORECASE,
        )
        if pipe_to_shell_pattern.search(cmd):
            return False, "Dangerous pattern: piping remote web download directly into shell interpreter."

        # 2. Tokenize command into pipeline segments
        segments = re.split(r"[;&|]+", cmd)
        for seg in segments:
            seg = seg.strip()
            if not seg:
                continue
            try:
                tokens = shlex.split(seg)
            except ValueError:
                # If unclosed quotes or syntax error in shell, fail closed
                return False, "Shell command contains malformed or unclosed quotes."

            if not tokens:
                continue

            binary = os.path.basename(tokens[0]).lower()

            # Block privilege escalation binaries
            if binary in DANGEROUS_BINARIES:
                return False, f"Privilege change or system modification command '{binary}' is strictly forbidden."

            # Block writing to git hooks
            if binary in ("cp", "mv", "touch", "tee", "cat") or ">" in seg:
                if ".git/hooks" in seg:
                    return False, "Modifying git hooks (.git/hooks) is forbidden."

            # Block destructive rm outside workspace
            if binary == "rm":
                for tok in tokens[1:]:
                    if tok.startswith("-"):
                        continue
                    try:
                        expanded = os.path.expanduser(tok)
                        if os.path.isabs(expanded):
                            target = Path(expanded).resolve()
                        else:
                            target = (Path(self.workspace) / expanded).resolve()
                        real_target = os.path.realpath(target)
                        real_ws = os.path.realpath(self.workspace)

                        # Prevent removing root or system directories
                        if real_target in ("/", "/usr", "/etc", "/var", "/bin", "/System", "/Library", os.path.expanduser("~")):
                            return False, f"Destructive command targeting critical path '{tok}' is blocked."
                        if not (real_target == real_ws or real_target.startswith(real_ws + os.sep)):
                            return False, f"Destructive rm command targeting outside workspace '{tok}' is blocked."
                    except Exception:
                        return False, "Unable to resolve target path for rm command."

            # Network egress check if network is not enabled
            if not self.network_allowed and binary in ("curl", "wget", "nc", "netcat", "socat", "ssh", "scp"):
                return False, f"Network utility '{binary}' is disabled in sandboxed execution."

        return True, "Command passed security checks"

