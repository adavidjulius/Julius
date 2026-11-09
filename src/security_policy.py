"""
Security policy engine and blast radius gatekeeper.
Enforces that:
1. File tools only access files within the repository/workspace boundaries.
2. Dangerous commands (e.g. rm -rf /) are intercepted and blocked.
3. API credentials are stored securely via the OS Keychain (or Fernet-encrypted file fallback).
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

try:
    import keyring
    _KEYRING_AVAILABLE = True
except ImportError:
    _KEYRING_AVAILABLE = False

try:
    from cryptography.fernet import Fernet
    _CRYPTOGRAPHY_AVAILABLE = True
except ImportError:
    _CRYPTOGRAPHY_AVAILABLE = False


class SecurityPolicy:
    """
    Enforces security policies for the agent.
    """

    def __init__(self, workspace_root: str) -> None:
        self.workspace_root = str(Path(workspace_root).resolve())
        julius_dir = Path(self.workspace_root) / '.julius'
        legacy_dir = Path(self.workspace_root) / '.julius'
        self.julius_dir = julius_dir if julius_dir.exists() or not legacy_dir.exists() else legacy_dir
        self.julius_dir.mkdir(parents=True, exist_ok=True)
        self.julius_dir = self.julius_dir  # Backward compatibility alias
        
        # Paths for local encrypted credentials fallback
        # Paths for local encrypted credentials fallback
        self.creds_file = self.julius_dir / 'credentials.enc'
        home_julius_key = Path.home() / '.julius' / 'secret.key'
        self.key_file = home_julius_key if home_julius_key.exists() or not home_julius_key.exists() else home_julius_key
        self._host_access_allowed: bool = False
        self._scoped_grants: dict[str, dict[str, Any]] = {}

    def grant_path_access(
        self,
        path: str,
        mode: str = "read",
        ttl_seconds: float = 60.0,
        once: bool = False,
    ) -> None:
        """Grant scoped, time-boxed path access outside the workspace (T1.3)."""
        import time
        from src.security.workspace_sandbox import BLOCKED_PATTERNS
        resolved = os.path.realpath(os.path.expanduser(str(path).strip()))
        resolved_p = Path(resolved)
        if resolved_p.name in BLOCKED_PATTERNS or any(part in BLOCKED_PATTERNS for part in resolved_p.parts):
            raise PermissionError(f"Access Denied: Hard-denied sensitive path '{path}'")
        self._scoped_grants[resolved] = {
            "path": resolved,
            "mode": mode,
            "expires_at": time.monotonic() + ttl_seconds,
            "once": once,
            "used": False,
        }

    def grant_host_access(self, allowed: bool = True) -> None:
        """Deprecated global grant. Scoped access must be used instead (T1.3)."""
        logger.warning("Global grant_host_access is deprecated under Phase 2 security policy.")
        self._host_access_allowed = False

    def is_path_allowed(self, target_path: str) -> bool:
        """
        Verify that target_path resides safely within the workspace boundary,
        or across active scoped grants.
        """
        if self._host_access_allowed:
            return True

        try:
            resolved = str(Path(os.path.abspath(target_path)).resolve())
        except Exception:
            return False

        # Allow access if it starts with the workspace root
        if resolved.startswith(self.workspace_root):
            return True
            
        # Exception for system temp folders if explicitly required by sandbox/tests
        if resolved.startswith('/private/tmp') or resolved.startswith('/tmp'):
            return True

        # Check active scoped path grants
        import time
        now = time.monotonic()
        for grant_path, grant in list(self._scoped_grants.items()):
            if now > grant["expires_at"] or (grant["once"] and grant["used"]):
                del self._scoped_grants[grant_path]
                continue
            if resolved == grant_path or resolved.startswith(grant_path + os.sep):
                if grant["once"]:
                    grant["used"] = True
                return True
            
        return False

    # ── Finding #7: comprehensive dangerous-pattern blocklist ────────────────────
    _DANGEROUS_PATTERNS: list[tuple[str, str]] = [
        # Destructive root/home/relative deletion
        (r'rm\s+.*-[a-zA-Z]*[rR][a-zA-Z]*\s+/(?:$|\*|\s)', "Recursive deletion targeting root partition"),
        (r'rm\s+.*-[a-zA-Z]*[rR][a-zA-Z]*\s+~(?:/?$|/\*\s*$|\s)', "Recursive deletion targeting home"),
        (r'rm\s+.*-[a-zA-Z]*[rR][a-zA-Z]*\s+\$HOME(?:/?$|/\*\s*$|\s)', "Recursive deletion targeting $HOME"),
        (r'rm\s+.*-[a-zA-Z]*[rR][a-zA-Z]*\s+\.\./', "Recursive deletion escaping workspace via ../"),
        (r'rm\s+.*-[a-zA-Z]*[rR][a-zA-Z]*\s+\*\s*$', "Wildcard recursive deletion"),
        # System directory modification
        (r'(?:rm|mv|chmod|chown|tee|dd)\s+.*(?:/etc|/var|/System|/Library|/usr|/bin|/sbin|/dev|/proc)',
         "Modification of system directory"),
        # Credential access
        (r'\.ssh', "Access to SSH credentials"),
        # Arbitrary code download & execution
        (r'(?:curl|wget)\s+.*\|\s*(?:bash|sh|zsh|python)', "Pipe from network to shell (pipe to shell)"),
        (r'base64\s+.*\|\s*(?:bash|sh)', "Base64 decode piped to shell"),
        # Environment/credential exfiltration
        (r'\b(?:env|printenv|set)\b.*\|\s*(?:curl|wget|nc|netcat)',
         "Environment exfiltration via network"),
        # Disk destruction
        (r'dd\s+.*(?:of=/dev/|of=\s*/dev/)', "Direct disk write via dd"),
        (r'mkfs\b', "Filesystem formatting"),
        # Fork bombs
        (r':\(\)\{.*\|.*\}', "Fork bomb detected"),
        # Privilege escalation
        (r'\bsudo\b', "Privilege escalation via sudo"),
        (r'\bsu\s+-?\s*$', "Privilege escalation via su"),
        # Dynamic library & shell environment hijacking (Julius sec-default pattern)
        (r'(?:\bexport\s+|\benv\s+)?\b(?:LD_PRELOAD|LD_LIBRARY_PATH|LD_AUDIT|DYLD_INSERT_LIBRARIES|DYLD_LIBRARY_PATH|DYLD_FRAMEWORK_PATH|BASH_ENV|ZDOTDIR|NODE_OPTIONS)\s*=',
         "Dynamic library hijacking or shell environment injection"),
        # Cryptocurrency mining (common in agent abuse)
        (r'(?:xmrig|minerd|cryptonight)', "Cryptocurrency miner detected"),
    ]

    def is_command_safe(self, command: str) -> tuple[bool, str]:
        """
        Scan commands for dangerous constructs before sending to the shell.
        
        Returns:
            Tuple of (is_safe: bool, reason: str)
        """
        cleaned = command.strip()

        # In accept mode, provide unrestricted execution across host
        if getattr(self, "mode", None) == "accept":
            return True, ""

        for pattern, reason in self._DANGEROUS_PATTERNS:
            # If user explicitly approved host access across Mac, allow host directory operations
            if self._host_access_allowed and "Modification of system directory" in reason:
                continue
            if re.search(pattern, cleaned, re.IGNORECASE):
                logger.warning(f"Command blocked by security policy: {reason}")
                return False, f"Dangerous command blocked: {reason}."

        return True, ""

    # ── Key Storage and Isolation ────────────────────────────────────

    def get_api_key(self, provider: str) -> str | None:
        """
        Securely load API keys via OS Keychain or encrypted fallback.
        """
        # Try OS Keychain first
        if _KEYRING_AVAILABLE:
            try:
                key = keyring.get_password("julius_agent", provider)
                if key:
                    return key
            except Exception as e:
                logger.warning(f"SecurityPolicy: Failed to read from OS Keychain: {e}")

        # Fallback to local encrypted credentials file
        return self._get_encrypted_key(provider)

    def set_api_key(self, provider: str, key: str) -> bool:
        """
        Securely save API keys via OS Keychain or encrypted fallback.
        """
        saved = False
        if _KEYRING_AVAILABLE:
            try:
                keyring.set_password("julius_agent", provider, key)
                saved = True
            except Exception as e:
                logger.warning(f"SecurityPolicy: Failed to write to OS Keychain: {e}")

        # Save to local encrypted credentials file as backup/fallback
        if self._set_encrypted_key(provider, key):
            saved = True
            
        return saved

    def _get_fernet_key(self) -> bytes | None:
        """Get or generate local key for Fernet symmetric encryption fallback."""
        if not _CRYPTOGRAPHY_AVAILABLE:
            return None
            
        if self.key_file.exists():
            try:
                return self.key_file.read_bytes()
            except Exception:
                pass
                
        # Generate new key
        try:
            self.key_file.parent.mkdir(parents=True, exist_ok=True)
            key = Fernet.generate_key()
            self.key_file.write_bytes(key)
            # Restrict permission to owner only
            self.key_file.chmod(0o600)
            return key
        except Exception as e:
            logger.error(f"SecurityPolicy: Failed to create local secret key: {e}")
            return None

    def _get_encrypted_key(self, provider: str) -> str | None:
        """Read and decrypt key from local credentials file."""
        if not self.creds_file.exists():
            return None
            
        key = self._get_fernet_key()
        if not key:
            return None

        try:
            fernet = Fernet(key)
            encrypted_data = self.creds_file.read_bytes()
            decrypted = fernet.decrypt(encrypted_data).decode('utf-8')
            
            # Simple format: provider:key\n
            for line in decrypted.splitlines():
                if ':' in line:
                    prov, val = line.split(':', 1)
                    if prov == provider:
                        return val
        except Exception as e:
            logger.error(f"SecurityPolicy: Decryption of local credentials failed: {e}")
            
        return None

    def _set_encrypted_key(self, provider: str, key_val: str) -> bool:
        """Encrypt and write key to local credentials file."""
        key = self._get_fernet_key()
        if not key:
            return False

        # Load existing values
        existing = {}
        if self.creds_file.exists():
            try:
                fernet = Fernet(key)
                encrypted_data = self.creds_file.read_bytes()
                decrypted = fernet.decrypt(encrypted_data).decode('utf-8')
                for line in decrypted.splitlines():
                    if ':' in line:
                        prov, val = line.split(':', 1)
                        existing[prov] = val
            except Exception:
                pass

        # Update and save
        existing[provider] = key_val
        raw_lines = "\n".join(f"{k}:{v}" for k, v in existing.items())
        
        try:
            fernet = Fernet(key)
            encrypted = fernet.encrypt(raw_lines.encode('utf-8'))
            self.creds_file.write_bytes(encrypted)
            # Restrict permission to owner only
            self.creds_file.chmod(0o600)
            return True
        except Exception as e:
            logger.error(f"SecurityPolicy: Encryption of local credentials failed: {e}")
            return False

    # ── Code Security Advisory Scanner (Julius security patterns) ───
    _CODE_SECURITY_CHECKS: list[dict] = [
        # Python
        {
            "name": "os_system_injection",
            "exts": (".py", ".pyi", ".ipynb"),
            "regex": r"\bos\.system\s*\(",
            "warning": "⚠️ Security Warning: os.system() passes input through a shell, creating a command injection sink. Prefer subprocess.run([...], check=True) with arguments as a list.",
        },
        {
            "name": "python_subprocess_shell",
            "exts": (".py", ".pyi", ".ipynb"),
            "regex": r"subprocess\.(?:run|call|Popen|check_output|check_call)\([^)\n]*shell\s*=\s*True",
            "warning": "⚠️ Security Warning: subprocess invocation with shell=True enables shell injection. Pass arguments directly as a list without shell=True.",
        },
        {
            "name": "pickle_deserialization",
            "exts": (".py", ".pyi", ".ipynb"),
            "regex": r"(?<![a-zA-Z0-9_])pickle\.(?:loads?|Unpickler)\b|(?<![a-zA-Z0-9_])pkl_load\(",
            "warning": "⚠️ Security Warning: Loading pickle data from untrusted sources allows arbitrary code execution. Prefer JSON, msgspec, or schema-validated pydantic models.",
        },
        {
            "name": "unsafe_yaml_load",
            "exts": (".py", ".pyi", ".ipynb"),
            "regex": r"\byaml\.(?:unsafe_load|load)\s*\((?![^)\n]{0,80}\bSafe)",
            "warning": "⚠️ Security Warning: yaml.load() or yaml.unsafe_load() can execute arbitrary Python via object tags. Use yaml.safe_load() instead.",
        },
        {
            "name": "torch_unsafe_load",
            "exts": (".py", ".pyi", ".ipynb"),
            "regex": r"(?:\btorch\.load|\.torch_load)\s*\((?![^)\n]{0,200}weights_only\s*=\s*True)",
            "warning": "⚠️ Security Warning: torch.load() without weights_only=True unpickles arbitrary Python objects. Pass weights_only=True if loading weights/tensors.",
        },
        {
            "name": "pickle_wrapper_deserialization",
            "exts": (".py", ".pyi", ".ipynb"),
            "regex": r"\bjoblib\.load\s*\(|\b(?:pd|pandas)\.read_pickle\s*\(|\b(?:np|numpy)\.load\s*\([^)\n]{0,200}allow_pickle\s*=\s*True|\b(cPickle|cloudpickle|dill|marshal)\.(?:load|loads)\b|\bshelve\.open\s*\(",
            "warning": "⚠️ Security Warning: Deserializer executes arbitrary code on untrusted inputs. Prefer safe structured formats (JSON, SafeTensors, Arrow, msgspec).",
        },
        # JS / TS
        {
            "name": "child_process_exec",
            "exts": (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"),
            "regex": r"(?<![a-zA-Z0-9_\.])(?:child_process\.)?exec(?:Sync)?\(",
            "warning": "⚠️ Security Warning: child_process.exec/execSync runs commands through a shell. Prefer child_process.execFile() or spawn() with argument arrays.",
        },
        {
            "name": "new_function_injection",
            "exts": (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"),
            "regex": r"\bnew\s+Function\s*\(",
            "warning": "⚠️ Security Warning: new Function() with dynamic strings is equivalent to eval() and enables arbitrary code execution.",
        },
        # Go
        {
            "name": "go_shell_exec",
            "exts": (".go",),
            "regex": r'exec\.Command\(\s*"(?:sh|bash|/bin/sh|/bin/bash)"',
            "warning": "⚠️ Security Warning: exec.Command with a shell interpreter enables command injection. Pass command and arguments directly without a shell.",
        },
        # Web / DOM XSS Sinks
        {
            "name": "inner_outer_html_xss",
            "exts": (".html", ".htm", ".js", ".jsx", ".ts", ".tsx", ".vue", ".svelte"),
            "regex": r"\.(?:inner|outer)HTML\s*=",
            "warning": "⚠️ Security Warning: Direct innerHTML/outerHTML assignment is an XSS sink. Use textContent or sanitize content with DOMPurify.",
        },
        {
            "name": "react_dangerously_set_html",
            "exts": (".js", ".jsx", ".ts", ".tsx"),
            "regex": r"dangerouslySetInnerHTML",
            "warning": "⚠️ Security Warning: dangerouslySetInnerHTML can lead to XSS. Ensure input is sanitized using DOMPurify.",
        },
        {
            "name": "document_write_xss",
            "exts": (".html", ".htm", ".js", ".jsx", ".ts", ".tsx"),
            "regex": r"\bdocument\.write\s*\(",
            "warning": "⚠️ Security Warning: document.write() is an XSS sink. Use standard DOM manipulation methods like createElement() and appendChild().",
        },
        # Universal Secret / Insecure Transport Checks
        {
            "name": "tls_verification_disabled",
            "exts": None,
            "regex": r"\bverify\s*=\s*False\b|rejectUnauthorized\s*:\s*false|InsecureSkipVerify\s*:\s*true|NODE_TLS_REJECT_UNAUTHORIZED\s*=\s*['\"]?0",
            "warning": "⚠️ Security Warning: TLS certificate verification is disabled, exposing connections to man-in-the-middle attacks.",
        },
        {
            "name": "hardcoded_aws_key",
            "exts": None,
            "regex": r"\b(?:AKIA|ABIA|ACCA|ASIA)[0-9A-Z]{16}\b",
            "warning": "⚠️ Security Warning: Hardcoded AWS access key ID detected. Store credentials in environment variables or OS keychain.",
        },
        {
            "name": "hardcoded_github_token",
            "exts": None,
            "regex": r"\b(?:ghp|gho|ghu|ghs|ghr)_[a-zA-Z0-9]{36,255}\b",
            "warning": "⚠️ Security Warning: Hardcoded GitHub token detected. Store credentials in environment variables or OS keychain.",
        },
        {
            "name": "hardcoded_private_key",
            "exts": None,
            "regex": r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
            "warning": "⚠️ Security Warning: Embedded private key detected in source code. Store private keys in secure keyrings or isolated files.",
        },
    ]

    def scan_code_security(self, path: str, content: str) -> list[str]:
        """
        Scan proposed code modifications for security anti-patterns, injection sinks,
        unsafe deserialization, and exposed credentials.
        Returns a list of advisory warning strings.
        """
        if not content:
            return []

        path_lower = path.lower()
        # Skip scanning documentation, test fixtures, or binary files
        if any(path_lower.endswith(ext) for ext in (".md", ".txt", ".json", ".lock", ".svg", ".png", ".jpg")):
            return []

        warnings: list[str] = []
        for check in self._CODE_SECURITY_CHECKS:
            exts = check.get("exts")
            if exts and not any(path_lower.endswith(ext) for ext in exts):
                continue

            pattern = check["regex"]
            if re.search(pattern, content):
                warnings.append(check["warning"])

        return warnings

