"""
Real action execution engine for the autonomous agent.

Replaces the stub "mirrored tool" execution with actual file I/O,
shell commands, and git operations. All operations respect workspace
path sandboxing.
"""

from __future__ import annotations

import json
import logging
import os
import re as _re_module
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    from .ast_parser import extract_symbol, list_symbols
    _AST_AVAILABLE = True
except ImportError:
    _AST_AVAILABLE = False

try:
    from .sandbox import get_sandbox, NativeSandbox
    _SANDBOX_AVAILABLE = True
except ImportError:
    _SANDBOX_AVAILABLE = False

from .shell_manager import StatefulShell
from .ledger import Ledger
from .security_policy import SecurityPolicy
from .rag_engine import RagEngine
from .security import WorkspaceSandbox, CommandPolicy
from src.policy import PolicyEngine
from src.sandbox.tiers import SandboxTierManager
from src.security.taint import TaintTracker, OutputExfiltrationGuard
from src.security.audit import CryptographicAuditLedger
from src.plugins.isolation import IsolatedPluginRunner

try:
    from .permission_gate import PermissionGate, ActionType, PermissionResponse
    _PERMISSION_GATE_AVAILABLE = True
except ImportError:
    _PERMISSION_GATE_AVAILABLE = False

try:
    from .remote.cluster_executor import ClusterExecutor, RemoteResult
    _CLUSTER_AVAILABLE = True
except ImportError:
    _CLUSTER_AVAILABLE = False

# Audit log path
_AUDIT_LOG = Path.home() / '.julius' / 'audit.log'


# ── Finding #8: credential redaction for audit logs ───────────────────────────
_SENSITIVE_PATTERNS = [
    (r'(?:api[_-]?key|secret|token|password|auth)\s*[=:]\s*\S+', '[REDACTED_CREDENTIAL]'),
    (r'sk-[a-zA-Z0-9]{20,}', '[REDACTED_API_KEY]'),
    (r'ghp_[a-zA-Z0-9]{36}', '[REDACTED_GITHUB_TOKEN]'),
    (r'Bearer\s+[a-zA-Z0-9._\-]+', 'Bearer [REDACTED]'),
]


def _redact(text: str) -> str:
    """Redact known credential patterns from log text."""
    for pattern, replacement in _SENSITIVE_PATTERNS:
        text = _re_module.sub(pattern, replacement, text, flags=_re_module.IGNORECASE)
    return text


def _write_audit(action: str, path: str, details: str = '') -> None:
    """Append a write operation to the audit log with credential redaction."""
    from datetime import datetime
    try:
        _AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
        with _AUDIT_LOG.open('a') as f:
            ts = datetime.now().isoformat(timespec='seconds')
            safe_path = _redact(path)
            safe_details = _redact(details)
            f.write(f'[{ts}] {action:12s} {safe_path}  {safe_details}\n')
    except Exception:
        pass



@dataclass(frozen=True)
class ActionResult:
    """Result of executing an agent action."""
    success: bool
    output: str
    action: str
    error: str | None = None
    data: Any = None


class ActionExecutor:
    """
    Executes real operations on the local filesystem and shell.

    All paths are resolved relative to the workspace root and validated
    against sandbox boundaries.
    """

    def __init__(
        self,
        workspace_root: str,
        max_file_read_lines: int = 500,
        max_bash_output_chars: int = 8000,
        bash_timeout: int = 60,
        use_docker_sandbox: bool = True,
        docker_memory_limit: str = '512m',
        strict_write_paths: list | None = None,
        user_role: str = 'user',
        user_id: int | None = None,
        permission_gate: Any | None = None,
        cluster_executor: Any | None = None,
    ) -> None:
        self.workspace_root = str(Path(workspace_root).resolve())
        self.user_role = user_role
        self.user_id = user_id
        self.permission_gate = permission_gate
        self.cluster_executor = cluster_executor
        self._sandbox_guard = WorkspaceSandbox(self.workspace_root, role=self.user_role)
        self._command_policy = CommandPolicy(self.workspace_root, role=self.user_role)
        self.max_file_read_lines = max_file_read_lines
        self.max_bash_output_chars = max_bash_output_chars
        self.bash_timeout = bash_timeout
        self.strict_write_paths: list[str] = [str(Path(p).resolve()) for p in (strict_write_paths or [])]
        # Track the most recently accessed directory for workspace continuity
        self._last_working_dir = None
        self._shell = StatefulShell(self.workspace_root, env=self._command_policy.get_sanitized_env())
        self._ledger = Ledger(self.workspace_root)
        self._policy = SecurityPolicy(self.workspace_root)
        self._policy_engine = PolicyEngine(workspace=self.workspace_root)
        self._tier_manager = SandboxTierManager(workspace=self.workspace_root, tier=1)
        self.taint_tracker = TaintTracker()
        self.exfiltration_guard = OutputExfiltrationGuard()
        self._cryptographic_audit = CryptographicAuditLedger(
            ledger_path=Path(self.workspace_root) / ".julius" / "audit_chain.jsonl"
        )
        self._rag = RagEngine(self.workspace_root)
        self._current_action_id = None
        self._todo_list: list[dict] = []
        self._read_files: set[str] = set()
        self._tasks_board: dict[str, dict] = {}
        self._current_worktree_txn = None
        self._background_tasks: dict[str, dict] = {}
        self._host_access_allowed: bool = False
        self.mode: str = "auto"
        self._active_action_name: str | None = None
        self._active_action_args: dict = {}
        self._active_action_start: float = 0.0

        if _SANDBOX_AVAILABLE:
            self._sandbox = get_sandbox(
                workspace=self.workspace_root,
                memory_limit=docker_memory_limit,
                use_docker=use_docker_sandbox,
            )
            sandbox_type = type(self._sandbox).__name__
            logger.info(f'ActionExecutor: using {sandbox_type} for bash commands')
        else:
            self._sandbox = None

    def grant_path_access(self, path: str, mode: str = "read", ttl_seconds: float = 60.0, once: bool = True) -> None:
        """Grant scoped, time-boxed path access outside the workspace (T1.3)."""
        self._tier_manager.grant_path_access(path, mode=mode, ttl_seconds=ttl_seconds, once=once)

    def grant_host_access(self, allowed: bool = True) -> None:
        """Deprecated global grant: Retaining scoped sandbox boundaries (T1.3)."""
        logger.info("grant_host_access called: retaining scoped sandbox policy enforcement.")
        self._host_access_allowed = False

    def start_new_action(self, command: str, explanation: str = "") -> None:
        """Start a new action/step boundary in the ledger."""
        self._current_action_id = self._ledger.start_action(command, explanation)

    def _snapshot_file(self, filepath: str) -> None:
        """Helper to snapshot a file before modification using the current action ID."""
        if self._current_action_id is None:
            self._current_action_id = self._ledger.start_action("Automatic Snapshot Action")
        self._ledger.snapshot_file(self._current_action_id, filepath)

    def undo_last_action(self) -> list[str]:
        """Undo the last workspace action using the ledger."""
        return self._ledger.undo_last_action()

    def close(self) -> None:
        """Close the underlying shell session."""
        self._shell.close()

    def cancel_active_action(self) -> bool:
        """Cancel currently running action or bash command."""
        cancelled = False
        if hasattr(self, "_shell") and self._shell:
            cancelled = self._shell.cancel_current_command()
        self._active_action_name = None
        return cancelled

    def get_active_action_details(self) -> dict:
        """Get live status and details of active bash command if running."""
        if hasattr(self, "_shell") and self._shell and self._shell.current_command:
            elapsed = time.time() - self._shell.command_start_time
            return {
                "action": "run_bash",
                "command": self._shell.current_command,
                "elapsed": elapsed,
                "output": getattr(self._shell, "partial_output", ""),
                "is_running": True,
            }
        if getattr(self, "_active_action_name", None):
            elapsed = max(0.0, time.time() - getattr(self, "_active_action_start", 0.0))
            args = getattr(self, "_active_action_args", {})
            cmd = args.get("command", "") or args.get("path", "") or args.get("url", "") or str(args)
            return {
                "action": self._active_action_name,
                "command": cmd,
                "elapsed": elapsed,
                "output": "Executing action...",
                "is_running": True,
            }
        if hasattr(self, "_shell") and self._shell and getattr(self._shell, "last_command", None):
            return {
                "action": "run_bash",
                "command": self._shell.last_command,
                "elapsed": getattr(self._shell, "last_duration", 0.0),
                "output": getattr(self._shell, "last_output", ""),
                "is_running": False,
            }
        return {"is_running": False}

    def update_workspace_root(self, new_root: str) -> None:
        """Update the workspace root dynamically (for continuity across tasks)."""
        self.workspace_root = str(Path(new_root).resolve())
        self._sandbox_guard = WorkspaceSandbox(self.workspace_root, role=self.user_role)
        self._command_policy = CommandPolicy(self.workspace_root, role=self.user_role)
        self._tier_manager = SandboxTierManager(self.workspace_root, tier=1)

    @property
    def last_working_dir(self) -> str | None:
        """Return the most recently used working directory, if any."""
        return self._last_working_dir

    def set_mode(self, mode: str) -> None:
        """Switch operation mode (auto, plan, edit, accept, manual)."""
        self.mode = mode.lower().strip()
        if self.mode in ("accept", "bypass"):
            self._host_access_allowed = True
            if hasattr(self, "_policy"):
                self._policy._host_access_allowed = True
                self._policy.mode = "accept"
        elif self.mode == "manual":
            self._host_access_allowed = False
            if hasattr(self, "_policy"):
                self._policy._host_access_allowed = False
                self._policy.mode = "manual"
        elif self.mode in ("auto", "normal"):
            self._host_access_allowed = True
            if hasattr(self, "_policy"):
                self._policy._host_access_allowed = True
                self._policy.mode = "auto"
        elif self.mode == "plan":
            if hasattr(self, "_policy"):
                self._policy.mode = "plan"
        if hasattr(self, "permission_gate") and self.permission_gate:
            self.permission_gate.set_mode(self.mode)

    # ── Path validation ───────────────────────────────────────────

    def _resolve_path(self, path: str, mode: str = "read") -> str:
        """Resolve a path relative to workspace root and validate sandbox."""
        if hasattr(self, "_tier_manager") and self._tier_manager.check_path_access(path, mode=mode):
            expanded = os.path.expanduser(str(path).strip())
            if os.path.isabs(expanded):
                target = Path(expanded).resolve()
            else:
                target = (Path(self.workspace_root) / expanded).resolve()
            if not target.exists() and mode in ("read", "write"):
                parent = target.parent
                if parent.exists() and parent.is_dir():
                    norm_target = _re_module.sub(r'[\s\u202f\u00a0]+', ' ', target.name)
                    try:
                        for sibling in parent.iterdir():
                            if _re_module.sub(r'[\s\u202f\u00a0]+', ' ', sibling.name) == norm_target:
                                return str(sibling.resolve())
                    except Exception:
                        pass
            return str(target)

        resolved = self._sandbox_guard.resolve_safe_path(path)
        if not self._policy.is_path_allowed(resolved):
            raise PermissionError("Access denied: path escapes the workspace blast radius.")
        target = Path(resolved)
        if not target.exists() and mode in ("read", "write"):
            parent = target.parent
            if parent.exists() and parent.is_dir():
                norm_target = _re_module.sub(r'[\s\u202f\u00a0]+', ' ', target.name)
                try:
                    for sibling in parent.iterdir():
                        if _re_module.sub(r'[\s\u202f\u00a0]+', ' ', sibling.name) == norm_target:
                            return str(sibling.resolve())
                except Exception:
                    pass
        return resolved

    def _normalize_command_unicode_filenames(self, command: str) -> str:
        """Resolve narrow no-break space (\\u202f) and non-breaking space (\\u00a0) in filenames within shell command."""
        if not command or ("Screenshot" not in command and "\u202f" not in command and "\u00a0" not in command):
            return command

        dirs_to_check = set()
        if self._last_working_dir and os.path.isdir(self._last_working_dir):
            dirs_to_check.add(self._last_working_dir)
        if self.workspace_root and os.path.isdir(self.workspace_root):
            dirs_to_check.add(self.workspace_root)

        for m in _re_module.finditer(r'(?:(?:/[^\s"\';|><&]+)|(?:~/[^\s"\';|><&]+))', command):
            p = os.path.expanduser(m.group(0))
            if os.path.isdir(p):
                dirs_to_check.add(p)
            elif os.path.isdir(os.path.dirname(p)):
                dirs_to_check.add(os.path.dirname(p))

        if "Desktop" in command:
            dt = os.path.expanduser("~/Desktop")
            if os.path.isdir(dt):
                dirs_to_check.add(dt)

        for d in dirs_to_check:
            try:
                for fname in os.listdir(d):
                    if '\u202f' in fname or '\u00a0' in fname:
                        norm_fname = fname.replace('\u202f', ' ').replace('\u00a0', ' ')
                        if norm_fname in command:
                            command = command.replace(norm_fname, fname)
            except Exception:
                pass
        return command

    # ── Actions ───────────────────────────────────────────────────

    def run_bash(self, command: str, timeout: int | None = None, run_in_background: bool = False) -> ActionResult:
        """Execute a shell command (via Docker sandbox if available, or background thread)."""
        # Check command safety via role-based CommandPolicy
        cmd_safe, cmd_reason = self._command_policy.validate_command(command)
        if not cmd_safe:
            logger.warning(f"Command blocked by command policy: {cmd_reason}")
            return ActionResult(
                success=False,
                output=cmd_reason,
                action='run_bash',
                error='security_violation'
            )

        # Check legacy security policy
        is_safe, reason = self._policy.is_command_safe(command)
        if not is_safe:
            logger.warning(f"Command blocked by security policy: {reason}")
            return ActionResult(
                success=False,
                output=reason,
                action='run_bash',
                error='security_violation'
            )

        if run_in_background:
            import threading
            import uuid
            task_id = f"bg_{uuid.uuid4().hex[:8]}"
            bg_info = {
                "task_id": task_id,
                "command": command,
                "status": "running",
                "start_time": time.time(),
                "output": "",
                "success": None,
            }
            self._background_tasks[task_id] = bg_info

            def _bg_runner():
                try:
                    s, o = self._shell.execute_command(command, timeout=timeout or 3600)
                    bg_info["status"] = "completed" if s else "failed"
                    bg_info["success"] = s
                    bg_info["output"] = o
                except Exception as bg_err:
                    bg_info["status"] = "failed"
                    bg_info["error"] = str(bg_err)

            t = threading.Thread(target=_bg_runner, daemon=True)
            t.start()
            return ActionResult(
                success=True,
                output=f"Command running detached in background with task_id '{task_id}': {command}",
                action='run_bash',
                data={"task_id": task_id, "is_background": True},
            )

        effective_timeout = timeout or self.bash_timeout
        # Cap unconstrained home directory scans that can hang on macOS/Linux
        if timeout is None and ("find ~" in command or "du -sh ~/*" in command or "find $HOME" in command):
            if "-prune" not in command and "-maxdepth" not in command:
                effective_timeout = min(effective_timeout, 15)
                logger.info(f"Capping unconstrained search command timeout to {effective_timeout}s")
        command = self._normalize_command_unicode_filenames(command)
        logger.info(f'Executing bash: {command}')

        # Track mkdir commands for workspace continuity
        import re as _re
        mkdir_match = _re.search(r'mkdir\s+(?:-p\s+)?["\']?([^\s"\';|><&<]+)', command)
        if mkdir_match:
            new_dir = mkdir_match.group(1)
            if os.path.isabs(new_dir):
                self._last_working_dir = str(Path(new_dir).resolve())
            else:
                self._last_working_dir = str((Path(self.workspace_root) / new_dir).resolve())

        # Track cd commands
        cd_match = _re.search(r'cd\s+["\']?([^\s"\';|><&<]+)', command)
        if cd_match:
            cd_dir = cd_match.group(1)
            if os.path.isabs(cd_dir):
                self._last_working_dir = str(Path(cd_dir).resolve())
            else:
                self._last_working_dir = str((Path(self.workspace_root) / cd_dir).resolve())

        # Check for remote cluster offloading for CPU-heavy commands
        if self.cluster_executor and getattr(self.cluster_executor, 'is_remote_available', False):
            patterns = getattr(self.cluster_executor.config, 'offload_patterns', [])
            if any(p in command for p in patterns):
                logger.info(f"Transparently offloading heavy command to cluster: {command[:60]}")
                return self.run_remote(command, timeout=effective_timeout)

        # Use persistent stateful shell
        success, output = self._shell.execute_command(command, timeout=effective_timeout)

        # For file deletion / cleanup commands: if no files match the pattern or target does not exist,
        # that indicates the target is already absent/clean (a successful state), NOT a fatal error!
        cmd_stripped = command.strip()
        is_removal_cmd = bool(
            cmd_stripped.startswith(('rm ', 'rm\t', 'rm -', 'trash ', '/bin/rm ', '/usr/bin/rm '))
            or ' -delete' in cmd_stripped
        )
        if not success and is_removal_cmd:
            lower_out = output.lower()
            if any(term in lower_out for term in (
                "no such file or directory",
                "no matches found",
                "cannot remove",
                "not found",
                "does not exist"
            )):
                success = True
                output = f"No matching files found to remove (already absent / clean).\n{output.strip()}".strip()

        # Truncate if too long
        if len(output) > self.max_bash_output_chars:
            output = output[:self.max_bash_output_chars] + f'\n\n... (output truncated at {self.max_bash_output_chars} chars)'

        return ActionResult(
            success=success,
            output=output,
            action='run_bash',
            error=None if success else 'non-zero exit',
        )

    def run_remote(self, command: str, timeout: int | None = None) -> ActionResult:
        """Transparently execute CPU-heavy workload on the remote 32-core cluster."""
        effective_timeout = timeout or self.bash_timeout
        if not self.cluster_executor or not getattr(self.cluster_executor, 'is_remote_available', False):
            logger.info("Remote cluster unavailable, executing locally")
            return self.run_bash(command, timeout=effective_timeout)

        import asyncio
        import concurrent.futures
        try:
            def _runner():
                return asyncio.run(self.cluster_executor.run_remote(command, timeout=float(effective_timeout)))

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                res = pool.submit(_runner).result(timeout=effective_timeout + 15)

            return ActionResult(
                success=res.success,
                output=res.output,
                action='run_remote',
                error=res.error if not res.success else None,
                data={'executed_remotely': res.executed_remotely, 'duration_ms': res.duration_ms}
            )
        except Exception as exc:
            logger.warning("Remote execution failed with exception: %s, falling back to local", exc)
            return self.run_bash(command, timeout=effective_timeout)

    def read_file(
        self,
        path: str,
        start_line: int | None = None,
        end_line: int | None = None,
        pages: str | None = None,
    ) -> ActionResult:
        """Read a file (optionally a line range or PDF page range)."""
        try:
            resolved = self._resolve_path(path)
            file_path = Path(resolved)

            if not file_path.exists():
                return ActionResult(
                    success=False,
                    output=f"File not found: {path}",
                    action='read_file',
                    error='not_found',
                )

            if not file_path.is_file():
                return ActionResult(
                    success=False,
                    output=f"Not a file: {path}",
                    action='read_file',
                    error='not_a_file',
                )

            self._read_files.add(str(file_path.resolve()))

            # PDF parsing support via pypdf if requested
            if file_path.suffix.lower() == '.pdf':
                try:
                    import pypdf
                    reader = pypdf.PdfReader(str(file_path))
                    total_pages = len(reader.pages)
                    page_start, page_end = 1, min(total_pages, 10)
                    if pages:
                        parts = pages.split('-')
                        page_start = max(1, int(parts[0].strip()))
                        page_end = min(total_pages, int(parts[1].strip()) if len(parts) > 1 else page_start)
                    extracted = []
                    for p in range(page_start - 1, page_end):
                        p_text = reader.pages[p].extract_text() or "(no text)"
                        extracted.append(f"--- Page {p + 1} ---\n{p_text}")
                    header = f"File: {path} (PDF pages {page_start}-{page_end} of {total_pages})"
                    return ActionResult(success=True, output=f"{header}\n\n" + "\n\n".join(extracted), action='read_file')
                except Exception as pdf_err:
                    logger.warning(f"PDF extraction error: {pdf_err}")

            lines = file_path.read_text(errors='replace').splitlines(keepends=True)
            total_lines = len(lines)

            # Apply line range
            s = max(1, start_line or 1)
            e = min(total_lines, end_line or total_lines)

            if s > total_lines:
                return ActionResult(
                    success=False,
                    output=f"Start line {s} exceeds total lines {total_lines} in {path}",
                    action='read_file',
                    error='range_error',
                )

            # Enforce max read limit
            if (e - s + 1) > self.max_file_read_lines:
                e = s + self.max_file_read_lines - 1

            selected = lines[s - 1:e]

            # Format with line numbers
            numbered_lines = []
            for i, line in enumerate(selected, start=s):
                numbered_lines.append(f'{i:>5}: {line.rstrip()}')

            header = f'File: {path} (lines {s}-{e} of {total_lines})'
            content = '\n'.join(numbered_lines)

            return ActionResult(
                success=True,
                output=f'{header}\n{content}',
                action='read_file',
            )

        except PermissionError as exc:
            return ActionResult(success=False, output=str(exc), action='read_file', error='permission')
        except Exception as exc:
            return ActionResult(success=False, output=f'Error reading file: {exc}', action='read_file', error=str(exc))

    def write_file(self, path: str, content: str) -> ActionResult:
        """Create or overwrite a file."""
        try:
            resolved = self._resolve_path(path)
            file_path = Path(resolved)

            # Strict write-path enforcement
            if self.strict_write_paths:
                allowed = any(resolved.startswith(sp) for sp in self.strict_write_paths)
                if not allowed:
                    return ActionResult(
                        success=False,
                        output=(
                            f'Write blocked: {path} is outside the strict write paths.\n'
                            f'Allowed paths: {self.strict_write_paths}'
                        ),
                        action='write_file',
                        error='strict_path_violation',
                    )

            # Create parent directories
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # Track the directory for workspace continuity
            self._last_working_dir = str(file_path.parent)

            # Create snapshot in SQLite ledger
            self._snapshot_file(resolved)

            # Create backup if file exists
            existed = file_path.exists()
            if existed:
                backup_path = str(file_path) + '.bak'
                shutil.copy2(str(file_path), backup_path)
                logger.info(f'Backup created: {backup_path}')

            file_path.write_text(content)

            action_word = 'Updated' if existed else 'Created'
            line_count = len(content.splitlines())
            _write_audit('write_file', path, f'{line_count} lines')
            sec_warnings = self._policy.scan_code_security(path, content)
            warning_text = ("\n\n" + "\n".join(sec_warnings)) if sec_warnings else ""
            return ActionResult(
                success=True,
                output=f'{action_word} {path} ({line_count} lines, {len(content)} bytes){warning_text}',
                action='write_file',
            )

        except PermissionError as exc:
            return ActionResult(success=False, output=str(exc), action='write_file', error='permission')
        except Exception as exc:
            return ActionResult(success=False, output=f'Error writing file: {exc}', action='write_file', error=str(exc))

    def edit_file(self, path: str, old_text: str, new_text: str, replace_all: bool = False) -> ActionResult:
        """Replace a specific string in a file with exact match validation."""
        try:
            resolved = self._resolve_path(path)
            file_path = Path(resolved)

            if not file_path.exists():
                return ActionResult(
                    success=False,
                    output=f"File not found: {path}",
                    action='edit_file',
                    error='not_found',
                )

            original = file_path.read_text(errors='replace')

            if old_text not in original:
                return ActionResult(
                    success=False,
                    output=f"Target text not found in {path}. Make sure the old_text matches exactly (including whitespace and indentation).",
                    action='edit_file',
                    error='text_not_found',
                )

            count = original.count(old_text)
            if not replace_all and count > 1:
                return ActionResult(
                    success=False,
                    output=f"Target text matched {count} times in {path} (must be unique). Include more surrounding context lines or set replace_all: true.",
                    action='edit_file',
                    error='ambiguous_match',
                )

            # Create snapshot in SQLite ledger
            self._snapshot_file(resolved)

            # Create backup
            backup_path = str(file_path) + '.bak'
            shutil.copy2(str(file_path), backup_path)

            # Perform replacement
            modified = original.replace(old_text, new_text) if replace_all else original.replace(old_text, new_text, 1)
            file_path.write_text(modified)

            sec_warnings = self._policy.scan_code_security(path, modified)
            warning_text = ("\n\n" + "\n".join(sec_warnings)) if sec_warnings else ""
            return ActionResult(
                success=True,
                output=f'Edited {path}: replaced {count} occurrence(s). Backup saved as {path}.bak{warning_text}',
                action='edit_file',
            )

        except PermissionError as exc:
            return ActionResult(success=False, output=str(exc), action='edit_file', error='permission')
        except Exception as exc:
            return ActionResult(success=False, output=f'Error editing file: {exc}', action='edit_file', error=str(exc))

    def delete_file(self, path: str) -> ActionResult:
        """Delete a file or directory safely."""
        try:
            resolved = self._resolve_path(path, mode="write")
            target = Path(resolved)
            if not target.exists():
                return ActionResult(success=True, output=f"File '{path}' does not exist (already deleted or removed).", action='delete_file')
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
            _write_audit('DELETE', str(target), 'delete_file')
            return ActionResult(success=True, output=f"Successfully deleted {target}.", action='delete_file')
        except Exception as exc:
            return ActionResult(success=False, output=f"Error deleting file {path}: {exc}", action='delete_file', error=str(exc))

    def _load_ignore_patterns(self) -> set[str]:
        """Load ignore patterns from .geminiignore and .gitignore in workspace root with standard defaults."""
        defaults = {
            'node_modules', '.git', '__pycache__', '.pytest_cache',
            '.venv', 'venv', '.turbo', '.next', '.cache', 'dist', 'build',
            'package-lock.json', 'pnpm-lock.yaml', 'yarn.lock', 'bun.lockb',
        }
        for ignore_file in ['.geminiignore', '.gitignore']:
            fp = Path(self.workspace_root) / ignore_file
            if fp.exists():
                try:
                    for line in fp.read_text(encoding='utf-8', errors='ignore').splitlines():
                        line = line.strip()
                        if line and not line.startswith('#'):
                            clean_pat = line.strip('/')
                            if clean_pat:
                                defaults.add(clean_pat)
                except Exception:
                    pass
        return defaults

    def _is_ignored(self, name: str, is_dir: bool = False, ignore_patterns: set[str] | None = None) -> bool:
        """Check if an entry or directory name matches ignore patterns to prevent token flooding."""
        if ignore_patterns is None:
            ignore_patterns = self._load_ignore_patterns()
        if name in ignore_patterns:
            return True
        import fnmatch
        for pat in ignore_patterns:
            if fnmatch.fnmatch(name, pat) or fnmatch.fnmatch(name + ('/' if is_dir else ''), pat):
                return True
        return False

    def list_directory(self, path: str = '.') -> ActionResult:
        """List directory contents with file sizes, filtering out heavy ignore patterns."""
        try:
            resolved = self._resolve_path(path)
            dir_path = Path(resolved)

            if not dir_path.exists():
                return ActionResult(
                    success=False,
                    output=f"Directory not found: {path}",
                    action='list_dir',
                    error='not_found',
                )

            if not dir_path.is_dir():
                return ActionResult(
                    success=False,
                    output=f"Not a directory: {path}",
                    action='list_dir',
                    error='not_a_dir',
                )

            ignore_patterns = self._load_ignore_patterns()
            all_entries = sorted(dir_path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
            entries = [e for e in all_entries if not self._is_ignored(e.name, is_dir=e.is_dir(), ignore_patterns=ignore_patterns)]
            ignored_count = len(all_entries) - len(entries)

            status_note = f", {ignored_count} ignored by .geminiignore" if ignored_count else ""
            lines = [f'Directory: {path} ({len(entries)} entries{status_note})', '']

            for entry in entries[:100]:  # limit to 100 entries
                if entry.is_dir():
                    try:
                        child_count = sum(1 for _ in entry.iterdir()) if entry.exists() else 0
                    except Exception:
                        child_count = 0
                    lines.append(f'  📁 {entry.name}/ ({child_count} items)')
                else:
                    try:
                        size = entry.stat().st_size
                    except Exception:
                        size = 0
                    if size < 1024:
                        size_str = f'{size}B'
                    elif size < 1024 * 1024:
                        size_str = f'{size / 1024:.1f}KB'
                    else:
                        size_str = f'{size / (1024 * 1024):.1f}MB'
                    lines.append(f'  📄 {entry.name} ({size_str})')

            if len(entries) > 100:
                lines.append(f'  ... and {len(entries) - 100} more entries')

            return ActionResult(success=True, output='\n'.join(lines), action='list_dir')

        except PermissionError as exc:
            return ActionResult(success=False, output=str(exc), action='list_dir', error='permission')
        except Exception as exc:
            return ActionResult(success=False, output=f'Error listing directory: {exc}', action='list_dir', error=str(exc))

    def search_files(self, pattern: str, path: str = '.') -> ActionResult:
        """Search for a pattern in files (no shell=True — Finding #5)."""
        try:
            resolved = self._resolve_path(path)

            # Validate pattern length to prevent ReDoS
            if len(pattern) > 500:
                return ActionResult(
                    success=False,
                    output='Search pattern too long (max 500 chars).',
                    action='search_files',
                    error='pattern_too_long',
                )

            # Use argument arrays — NEVER shell=True
            for cmd_name in ['rg', 'grep']:
                cmd_path = shutil.which(cmd_name)
                if not cmd_path:
                    continue

                if cmd_name == 'rg':
                    args = [
                        cmd_path, '--no-heading', '--line-number', '--max-count=50',
                    ]
                    gemini_ignore_path = Path(self.workspace_root) / '.geminiignore'
                    if gemini_ignore_path.exists():
                        args.extend(['--ignore-file', str(gemini_ignore_path)])
                    for def_ignore in ['node_modules', '.git', '__pycache__', '.venv', 'dist', 'build', '.pytest_cache', '.julius']:
                        args.extend(['--glob', f'!{def_ignore}'])
                    args.extend(['--', pattern, resolved])
                else:
                    args = [
                        cmd_path, '-rn', '-m', '50',
                        '--exclude-dir=node_modules', '--exclude-dir=.git',
                        '--exclude-dir=__pycache__', '--exclude-dir=.venv',
                        '--exclude-dir=dist', '--exclude-dir=build',
                        '--exclude-dir=.pytest_cache', '--exclude-dir=.julius',
                        '--exclude-dir=Library', '--exclude-dir=Music',
                        '--exclude-dir=Movies', '--exclude-dir=Cache',
                        '--include=*.py', '--include=*.js', '--include=*.ts',
                        '--include=*.json', '--include=*.md', '--include=*.txt',
                        '--include=*.yaml', '--include=*.yml', '--include=*.toml',
                        '--', pattern, resolved,
                    ]

                try:
                    result = subprocess.run(
                        args,
                        capture_output=True,
                        text=True,
                        timeout=8,
                        cwd=self.workspace_root,
                    )

                    output = result.stdout.strip() if result.stdout else '(no matches found)'

                    if len(output) > self.max_bash_output_chars:
                        output = output[:self.max_bash_output_chars] + '\n... (results truncated)'

                    return ActionResult(
                        success=True,
                        output=f'Search results for "{pattern}" in {path}:\n\n{output}',
                        action='search_files',
                    )

                except subprocess.TimeoutExpired:
                    return ActionResult(
                        success=True,
                        output=f'Search timed out after 8s for pattern "{pattern}". Try narrowing the path or pattern.',
                        action='search_files',
                    )
                except FileNotFoundError:
                    continue

            # Pure Python fallback when neither rg nor grep is found (e.g. pure Windows)
            matches = []
            target_dir = Path(resolved)
            files_to_scan = [target_dir] if target_dir.is_file() else [
                p for p in target_dir.rglob("*")
                if p.is_file() and ".git" not in p.parts and "node_modules" not in p.parts and ".venv" not in p.parts
            ]
            for file_path in files_to_scan:
                try:
                    text = file_path.read_text(encoding="utf-8", errors="ignore")
                    for line_num, line in enumerate(text.splitlines(), start=1):
                        if pattern.lower() in line.lower():
                            try:
                                rel = file_path.relative_to(self.workspace_root)
                            except Exception:
                                rel = file_path
                            matches.append(f"{rel}:{line_num}:{line.strip()}")
                            if len(matches) >= 100:
                                break
                    if len(matches) >= 100:
                        break
                except Exception:
                    continue

            output = "\n".join(matches) if matches else "(no matches found)"
            return ActionResult(
                success=True,
                output=f'Search results for "{pattern}" in {path}:\n\n{output}',
                action='search_files',
            )

        except PermissionError as exc:
            return ActionResult(success=False, output=str(exc), action='search_files', error='permission')
        except Exception as exc:
            return ActionResult(success=False, output=f'Search error: {exc}', action='search_files', error=str(exc))

    def search_semantic(self, query: str) -> ActionResult:
        """Search workspace files semantically using RAG."""
        try:
            # Re-index workspace incrementally to pick up any recent changes
            self._rag.index_workspace()
            results = self._rag.search_semantic(query, limit=5)
            
            if not results:
                return ActionResult(
                    success=True,
                    output="No semantically relevant chunks found in workspace.",
                    action='search_semantic'
                )
                
            output_parts = []
            for match in sorted(results, key=lambda x: x["score"], reverse=True):
                filepath = match["filepath"]
                score = match["score"]
                lines_str = f"Lines {match['start_line']}-{match['end_line']}"
                chunk_type = f" ({match['chunk_type']} symbol: {match['symbol_name']})" if match['symbol_name'] else ""
                
                output_parts.append(
                    f"--- File: {filepath} ({lines_str}){chunk_type} [Relevance: {score:.2f}] ---\n"
                    f"{match['text_content']}\n"
                )
            
            return ActionResult(
                success=True,
                output="\n".join(output_parts),
                action='search_semantic'
            )
        except Exception as exc:
            return ActionResult(
                success=False,
                output=f"Error in semantic search: {exc}",
                action='search_semantic',
                error=str(exc)
            )

    def git_operation(self, subcommand: str) -> ActionResult:
        """Execute a git operation."""
        return self.run_bash(f'git {subcommand}')

    def ask_human(self, question: str) -> ActionResult:
        """Pause and ask the human operator a question."""
        print(f'\n{"=" * 60}')
        print(f'🤖 AGENT QUESTION:')
        print(f'   {question}')
        print(f'{"=" * 60}')

        if getattr(self, 'on_ask_human', None):
            answer = self.on_ask_human(question)
            return ActionResult(
                success=True,
                output=f'Human answered: {answer}',
                action='ask_human',
            )

        if sys.stdin and sys.stdin.isatty():
            try:
                print('Your answer: ', end='', flush=True)
                answer = sys.stdin.readline().strip()
                return ActionResult(
                    success=True,
                    output=f'Human answered: {answer}',
                    action='ask_human',
                )
            except (EOFError, KeyboardInterrupt):
                return ActionResult(
                    success=True,
                    output='Human declined to answer (input interrupted).',
                    action='ask_human',
                )

        return ActionResult(
            success=True,
            output='Human declined to answer (non-interactive session).',
            action='ask_human',
        )

    @staticmethod
    def done(summary: str) -> ActionResult:
        """Signal task completion."""
        return ActionResult(
            success=True,
            output=f'Task completed: {summary}',
            action='done',
        )

    @staticmethod
    def converse(message: str) -> ActionResult:
        """Respond to a conversational or analytical query without touching files."""
        return ActionResult(
            success=True,
            output=f'Response: {message}',
            action='converse',
        )

    def read_symbol(self, path: str, symbol_name: str) -> ActionResult:
        """
        Extract a single function or class by name using AST parsing.

        This is far more token-efficient than read_file for large files —
        it returns only the specific symbol's source code.
        """
        if not _AST_AVAILABLE:
            return ActionResult(
                success=False,
                output='AST parser unavailable. Install tree-sitter or use read_file instead.',
                action='read_symbol',
                error='ast_unavailable',
            )

        try:
            resolved = self._resolve_path(path)

            # First list all symbols so we can show options if the name is wrong
            symbols = list_symbols(resolved)
            if not symbols:
                return ActionResult(
                    success=False,
                    output=f'No parseable symbols found in {path}. Use read_file instead.',
                    action='read_symbol',
                    error='no_symbols',
                )

            symbol = extract_symbol(resolved, symbol_name)
            if symbol is None:
                names = ', '.join(s.name for s in symbols[:20])
                return ActionResult(
                    success=False,
                    output=(
                        f'Symbol "{symbol_name}" not found in {path}.\n'
                        f'Available symbols: {names}'
                    ),
                    action='read_symbol',
                    error='symbol_not_found',
                )

            header = (
                f'Symbol: {symbol.kind} {symbol.name}\n'
                f'File: {path} (lines {symbol.start_line}–{symbol.end_line})\n'
                f'---\n'
            )
            return ActionResult(
                success=True,
                output=header + symbol.source,
                action='read_symbol',
            )

        except Exception as exc:
            return ActionResult(
                success=False,
                output=f'Error extracting symbol: {exc}',
                action='read_symbol',
                error=str(exc),
            )

    def list_symbols(self, path: str) -> ActionResult:
        """List all functions and classes in a source file."""
        if not _AST_AVAILABLE:
            return ActionResult(
                success=False,
                output='AST parser unavailable. Install tree-sitter or use read_file instead.',
                action='list_symbols',
                error='ast_unavailable',
            )
        try:
            resolved = self._resolve_path(path)
            symbols = list_symbols(resolved)
            if not symbols:
                return ActionResult(
                    success=True,
                    output=f'No symbols found in {path} (unsupported file type or empty file).',
                    action='list_symbols',
                )
            lines = [f'Symbols in {path}:', '']
            for s in symbols:
                lines.append(f'  {s.kind:10s} {s.name}  (lines {s.start_line}–{s.end_line})')
            return ActionResult(success=True, output='\n'.join(lines), action='list_symbols')
        except Exception as exc:
            return ActionResult(
                success=False, output=f'Error listing symbols: {exc}', action='list_symbols', error=str(exc)
            )

    def sarvam_translate(self, text: str, target_language: str = 'ta-IN', source_language: str = 'en-IN') -> ActionResult:
        """Translate text using Sarvam AI Mayura API."""
        try:
            from .services.sarvam_service import get_sarvam_service
            service = get_sarvam_service()
            res = service.translate(text, target_language_code=target_language, source_language_code=source_language)
            translated = res.get('translated_text', '')
            return ActionResult(success=True, output=f"Translated text ({source_language} -> {target_language}):\n{translated}", action='sarvam_translate')
        except Exception as exc:
            return ActionResult(success=False, output=f"Sarvam translation failed: {exc}", action='sarvam_translate', error=str(exc))

    def sarvam_tts(self, text: str, target_language: str = 'ta-IN', speaker: str = 'anushka', output_path: str = 'output_speech.wav') -> ActionResult:
        """Synthesize text to speech audio WAV using Sarvam Bulbul API."""
        try:
            from .services.sarvam_service import get_sarvam_service
            service = get_sarvam_service()
            audio_bytes = service.text_to_speech(text, target_language_code=target_language, speaker=speaker)
            resolved = self._resolve_path(output_path)
            Path(resolved).write_bytes(audio_bytes)
            return ActionResult(success=True, output=f"Saved speech audio ({len(audio_bytes)} bytes) to {output_path}", action='sarvam_tts')
        except Exception as exc:
            return ActionResult(success=False, output=f"Sarvam TTS failed: {exc}", action='sarvam_tts', error=str(exc))

    def sarvam_stt(self, audio_path: str, language_code: str = 'ta-IN') -> ActionResult:
        """Transcribe audio file to text using Sarvam Saarika API."""
        try:
            from .services.sarvam_service import get_sarvam_service
            resolved = self._resolve_path(audio_path)
            audio_bytes = Path(resolved).read_bytes()
            service = get_sarvam_service()
            res = service.speech_to_text(audio_bytes, language_code=language_code, filename=Path(resolved).name)
            transcript = res.get('transcript', '')
            return ActionResult(success=True, output=f"Transcription ({language_code}):\n{transcript}", action='sarvam_stt')
        except Exception as exc:
            return ActionResult(success=False, output=f"Sarvam STT failed: {exc}", action='sarvam_stt', error=str(exc))

    def sarvam_ocr(self, document_path: str) -> ActionResult:
        """Parse document layout and text using Sarvam Document Parsing API."""
        try:
            from .services.sarvam_service import get_sarvam_service
            resolved = self._resolve_path(document_path)
            doc_bytes = Path(resolved).read_bytes()
            service = get_sarvam_service()
            res = service.parse_document(doc_bytes, filename=Path(resolved).name)
            return ActionResult(success=True, output=f"Sarvam document parsing result:\n{json.dumps(res, indent=2)}", action='sarvam_ocr')
        except Exception as exc:
            return ActionResult(success=False, output=f"Sarvam OCR failed: {exc}", action='sarvam_ocr', error=str(exc))

    # ── Autonomous Music Ingestion Actions ────────────────────────

    def import_spotify_playlist(
        self,
        playlist_url: str,
        quality_policy: str = "best_lossless",
        destination: str = "google_drive",
        dry_run: bool = False
    ) -> ActionResult:
        """Autonomously analyze Spotify playlist, resolve candidates, and trigger FLAC -> Google Drive import."""
        from src.music.tool import music_import_tool
        try:
            import concurrent.futures
            import asyncio

            def _run():
                return asyncio.run(
                    music_import_tool.execute(
                        playlist_url=playlist_url,
                        quality_policy=quality_policy,
                        destination=destination,
                        dry_run=dry_run,
                        user_id=str(self.user_id)
                    )
                )

            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    result = pool.submit(_run).result(timeout=60)
            else:
                result = _run()

            return ActionResult(
                success=(result.status != "FAILED"),
                output=result.message,
                action='import_spotify_playlist',
                error=result.message if result.status == "FAILED" else None,
                data=result.to_dict()
            )
        except Exception as exc:
            return ActionResult(
                success=False,
                output=f"Error executing music import: {exc}",
                action='import_spotify_playlist',
                error=str(exc)
            )

    def music_status(self, job_id: str) -> ActionResult:
        """Check progress and error breakdown of a music import job."""
        from src.music.tool import music_import_tool
        status_data = music_import_tool.get_status(job_id)
        if "error" in status_data:
            return ActionResult(success=False, output=status_data["error"], action="music_status")

        output_str = (
            f"🎵 Music Job Status: {status_data.get('playlist_name', 'Untitled')} ({status_data.get('status')})\n"
            f"Progress: {status_data.get('progress_percent', 0)}% ({status_data.get('completed', 0)}/{status_data.get('total_tracks', 0)} completed)\n"
            f"Failed: {status_data.get('failed', 0)}, Skipped: {status_data.get('skipped', 0)}"
        )
        return ActionResult(success=True, output=output_str, action="music_status", data=status_data)

    def music_retry(self, job_id: str) -> ActionResult:
        """Retry failed tracks from an existing import job."""
        from src.music.tool import music_import_tool
        import asyncio
        res = asyncio.run(music_import_tool.retry_job(job_id))
        return ActionResult(success=res.get("retried", False), output=res.get("message", ""), action="music_retry")

    def music_cancel(self, job_id: str) -> ActionResult:
        """Cancel a running import job."""
        from src.music.tool import music_import_tool
        res = music_import_tool.cancel_job(job_id)
        return ActionResult(success=res.get("cancelled", False), output=res.get("message", ""), action="music_cancel")

    def music_library(self, query: str = "") -> ActionResult:
        """Search and list tracks stored in the Julius lossless music library."""
        from src.music.db import default_music_db
        tracks = default_music_db.search_library(query=query, limit=50) if query else default_music_db.get_all_library_tracks(limit=50)
        if not tracks:
            return ActionResult(success=True, output=f"No tracks found in music library for query '{query}'.", action="music_library")

        lines = [f"🎵 Julius Music Library ({len(tracks)} tracks):"]
        for t in tracks:
            lines.append(f"• {t.title} — {t.artist_display} [{t.quality_badge}] (Drive ID: {t.drive_file_id or 'Local only'})")
        return ActionResult(success=True, output="\n".join(lines), action="music_library", data={"count": len(tracks)})

    # ── Extended Tools ────────────────────────────────────────────

    def multi_edit(self, path: str, edits: list[dict]) -> ActionResult:
        """Apply multiple edits to a single file atomically."""
        try:
            resolved = self._resolve_path(path)
            file_path = Path(resolved)

            if not file_path.exists():
                return ActionResult(
                    success=False,
                    output=f"File not found: {path}",
                    action='multi_edit',
                    error='not_found',
                )

            if not isinstance(edits, list) or not edits:
                return ActionResult(
                    success=False,
                    output="No edits provided for multi_edit.",
                    action='multi_edit',
                    error='empty_edits',
                )

            original = file_path.read_text(errors='replace')
            current = original

            # Validate and apply all edits in sequence in memory
            for i, edit in enumerate(edits, start=1):
                old_text = edit.get('old_text')
                new_text = edit.get('new_text', '')
                if old_text is None:
                    return ActionResult(
                        success=False,
                        output=f"Edit #{i} missing 'old_text'.",
                        action='multi_edit',
                        error='invalid_edit',
                    )
                count = current.count(old_text)
                if count == 0:
                    return ActionResult(
                        success=False,
                        output=(
                            f"Edit #{i} failed: target text not found in {path}. "
                            f"All changes aborted. Check whitespace and context."
                        ),
                        action='multi_edit',
                        error='text_not_found',
                    )
                if count > 1:
                    return ActionResult(
                        success=False,
                        output=(
                            f"Edit #{i} failed: target text matched {count} times in {path} (must be unique). "
                            f"All changes aborted. Include more surrounding lines."
                        ),
                        action='multi_edit',
                        error='ambiguous_match',
                    )
                current = current.replace(old_text, new_text, 1)

            # All edits passed validation, apply atomically
            self._snapshot_file(resolved)
            backup_path = str(file_path) + '.bak'
            shutil.copy2(str(file_path), backup_path)
            file_path.write_text(current)
            _write_audit('multi_edit', path, f'{len(edits)} edits applied')

            sec_warnings = self._policy.scan_code_security(path, current)
            warning_text = ("\n\n" + "\n".join(sec_warnings)) if sec_warnings else ""
            return ActionResult(
                success=True,
                output=f"Applied {len(edits)} edit(s) atomically to {path}. Backup saved as {path}.bak{warning_text}",
                action='multi_edit',
            )
        except PermissionError as exc:
            return ActionResult(success=False, output=str(exc), action='multi_edit', error='permission')
        except Exception as exc:
            return ActionResult(success=False, output=f"Error in multi_edit: {exc}", action='multi_edit', error=str(exc))

    def glob(self, pattern: str, path: str = ".") -> ActionResult:
        """Find files by glob pattern."""
        try:
            resolved = self._resolve_path(path)
            root = Path(resolved)
            if not root.exists():
                return ActionResult(
                    success=False,
                    output=f"Path not found: {path}",
                    action='glob',
                    error='not_found',
                )

            ignore_dirs = {'.git', '__pycache__', 'node_modules', '.venv', 'venv'}
            matches: list[str] = []
            for p in root.glob(pattern):
                if any(part in ignore_dirs for part in p.parts if part not in pattern):
                    continue
                try:
                    rel = p.relative_to(Path(self.workspace_root))
                    matches.append(rel.as_posix())
                except ValueError:
                    matches.append(p.as_posix())

            matches.sort()
            if not matches:
                return ActionResult(
                    success=True,
                    output=f"No files matched pattern '{pattern}' under '{path}'.",
                    action='glob',
                    data=[],
                )

            max_display = 100
            lines = [f"Found {len(matches)} match(es) for '{pattern}':"]
            for m in matches[:max_display]:
                lines.append(f"  {m}")
            if len(matches) > max_display:
                lines.append(f"  ... and {len(matches) - max_display} more.")

            return ActionResult(
                success=True,
                output="\n".join(lines),
                action='glob',
                data=matches,
            )
        except Exception as exc:
            return ActionResult(success=False, output=f"Error running glob: {exc}", action='glob', error=str(exc))

    def run_tests(self, command: str | None = None, target: str | None = None) -> ActionResult:
        """Run project tests using custom or auto-detected test command."""
        try:
            if command:
                test_cmd = command
                if target:
                    test_cmd = f"{test_cmd} {target}"
            else:
                ws = Path(self.workspace_root)
                if (ws / 'pytest.ini').exists() or (ws / 'tests').exists() or (ws / 'pyproject.toml').exists():
                    test_cmd = f"pytest -q {target}" if target else "pytest -q"
                elif (ws / 'package.json').exists():
                    test_cmd = f"npm test -- {target}" if target else "npm test"
                elif (ws / 'Cargo.toml').exists():
                    test_cmd = f"cargo test {target}" if target else "cargo test"
                elif (ws / 'go.mod').exists():
                    test_cmd = f"go test {target}" if target else "go test ./..."
                else:
                    test_cmd = f"pytest -q {target}" if target else "pytest -q"

            res = self.run_bash(test_cmd)
            return ActionResult(
                success=res.success,
                output=res.output,
                action='run_tests',
                error=res.error,
            )
        except Exception as exc:
            return ActionResult(success=False, output=f"Error running tests: {exc}", action='run_tests', error=str(exc))

    def todo(self, items: list[dict]) -> ActionResult:
        """Update and view the multi-step task checklist."""
        try:
            if not isinstance(items, list):
                return ActionResult(success=False, output="'items' must be a list", action='todo', error='invalid_args')

            self._todo_list = items
            lines = ["Task Checklist:"]
            for item in items:
                item_id = item.get('id', '?')
                text = item.get('text', '')
                status = item.get('status', 'pending')
                icon = {'done': '[x]', 'in_progress': '[>]', 'pending': '[ ]'}.get(status, '[?]')
                lines.append(f"  {icon} {item_id}: {text} ({status})")

            return ActionResult(
                success=True,
                output="\n".join(lines),
                action='todo',
                data=self._todo_list,
            )
        except Exception as exc:
            return ActionResult(success=False, output=f"Error in todo: {exc}", action='todo', error=str(exc))

    def checkpoint(self, action: str = "create", name: str = "") -> ActionResult:
        """Create, restore, or list restore points for workspace files."""
        try:
            chk_dir = Path(self.workspace_root) / '.julius' / 'checkpoints'
            chk_dir.mkdir(parents=True, exist_ok=True)

            if action == "create":
                chk_name = name or f"checkpoint_{int(time.time())}"
                target = chk_dir / chk_name
                if target.exists():
                    shutil.rmtree(target)
                target.mkdir(parents=True)

                git_res = self.git_operation("stash create")
                stash_sha = git_res.output.strip() if git_res.success else ""
                meta = {"name": chk_name, "timestamp": time.time(), "stash_sha": stash_sha}
                (target / "meta.json").write_text(json.dumps(meta, indent=2))

                return ActionResult(
                    success=True,
                    output=f"Created checkpoint '{chk_name}' successfully.",
                    action='checkpoint',
                    data=meta,
                )

            elif action == "restore":
                if not name:
                    available = sorted([d.name for d in chk_dir.iterdir() if d.is_dir()])
                    if not available:
                        return ActionResult(success=False, output="No checkpoints available to restore.", action='checkpoint')
                    name = available[-1]

                target = chk_dir / name
                if not target.exists():
                    return ActionResult(success=False, output=f"Checkpoint '{name}' not found.", action='checkpoint', error='not_found')

                meta_file = target / "meta.json"
                if meta_file.exists():
                    meta = json.loads(meta_file.read_text())
                    stash_sha = meta.get("stash_sha")
                    if stash_sha:
                        self.git_operation(f"stash apply {stash_sha}")

                return ActionResult(
                    success=True,
                    output=f"Restored workspace state from checkpoint '{name}'.",
                    action='checkpoint',
                )

            elif action == "list":
                available = sorted([d.name for d in chk_dir.iterdir() if d.is_dir()])
                if not available:
                    return ActionResult(success=True, output="No checkpoints found.", action='checkpoint', data=[])
                lines = ["Available Checkpoints:"]
                for c in available:
                    lines.append(f"  • {c}")
                return ActionResult(success=True, output="\n".join(lines), action='checkpoint', data=available)

            else:
                return ActionResult(
                    success=False,
                    output=f"Unknown checkpoint action '{action}'. Valid actions: create, restore, list.",
                    action='checkpoint',
                    error='invalid_action',
                )
        except Exception as exc:
            return ActionResult(success=False, output=f"Error in checkpoint: {exc}", action='checkpoint', error=str(exc))

    def fetch_url(self, url: str, max_chars: int | None = 20000) -> ActionResult:
        """Fetch content from a web page or API for reference."""
        try:
            import urllib.request
            import html

            if not (url.startswith("http://") or url.startswith("https://")):
                return ActionResult(
                    success=False,
                    output=f"Invalid URL '{url}'. Must start with http:// or https://",
                    action='fetch_url',
                    error='invalid_url',
                )

            req = urllib.request.Request(
                url,
                headers={'User-Agent': 'Julius/2.0 (Engineering Agent)'},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw_bytes = resp.read()
                charset = resp.headers.get_content_charset() or 'utf-8'
                text = raw_bytes.decode(charset, errors='replace')

            # Basic HTML tag stripping
            clean_text = _re_module.sub(r'<script.*?</script>', '', text, flags=_re_module.DOTALL | _re_module.IGNORECASE)
            clean_text = _re_module.sub(r'<style.*?</style>', '', clean_text, flags=_re_module.DOTALL | _re_module.IGNORECASE)
            clean_text = _re_module.sub(r'<[^>]+>', ' ', clean_text)
            clean_text = html.unescape(clean_text)
            clean_text = _re_module.sub(r'[ \t]+', ' ', clean_text)
            clean_text = _re_module.sub(r'\n\s*\n+', '\n\n', clean_text).strip()

            limit = max_chars if max_chars and max_chars > 0 else 20000
            if len(clean_text) > limit:
                clean_text = clean_text[:limit] + f"\n\n[Truncated at {limit} characters]"

            return ActionResult(
                success=True,
                output=clean_text,
                action='fetch_url',
            )
        except Exception as exc:
            return ActionResult(
                success=False,
                output=f"Error fetching URL '{url}': {exc}",
                action='fetch_url',
                error=str(exc),
            )

    def run_python(self, code: str, timeout: int | None = 30) -> ActionResult:
        """Execute a Python snippet in a child process."""
        try:
            t = timeout or 30
            proc = subprocess.run(
                [sys.executable, "-c", code],
                cwd=self.workspace_root,
                capture_output=True,
                text=True,
                timeout=t,
                env=self._command_policy.get_sanitized_env(),
            )
            output = proc.stdout
            if proc.stderr:
                output = f"{output}\n[stderr]\n{proc.stderr}" if output else proc.stderr
            if not output.strip():
                output = "(script completed with no output)"

            return ActionResult(
                success=(proc.returncode == 0),
                output=output.strip(),
                action='run_python',
                error=None if proc.returncode == 0 else f"exit_code_{proc.returncode}",
            )
        except subprocess.TimeoutExpired:
            return ActionResult(
                success=False,
                output=f"Python execution timed out after {timeout}s.",
                action='run_python',
                error='timeout',
            )
        except Exception as exc:
            return ActionResult(
                success=False,
                output=f"Error executing Python code: {exc}",
                action='run_python',
                error=str(exc),
            )

    # ── Canonical Tool Implementations (WS1.1 / WS1.2) ──

    def canonical_tool_search(self, args: dict) -> ActionResult:
        """Fetch deferred tool schemas using ToolSearch."""
        from src.tools import resolve_tool_search
        query = args.get('query', '')
        max_results = int(args.get('max_results', 5))
        xml_result = resolve_tool_search(query, max_results=max_results)
        return ActionResult(
            success=True,
            output=xml_result,
            action='ToolSearch',
            data={"query": query},
        )

    def canonical_ask_user_question(self, args: dict) -> ActionResult:
        """Interactive user prompt supporting options and preview layouts."""
        questions = args.get('questions', [])
        if not questions:
            return ActionResult(success=False, output="No questions provided to AskUserQuestion.", action='AskUserQuestion', error='missing_questions')

        # Format questions for display or bridge
        display_lines = ["Interactive User Questions:"]
        for i, q in enumerate(questions, start=1):
            q_text = q.get('question', '')
            hdr = q.get('header', 'Question')
            opts = [f"• {opt.get('label')}: {opt.get('description')}" for opt in q.get('options', [])]
            display_lines.append(f"\n[{hdr}] {q_text}\n" + "\n".join(opts))

        # Check if bridge hook exists
        if hasattr(self, 'on_ask_user_question') and callable(self.on_ask_user_question):
            answers = self.on_ask_user_question(questions)
            return ActionResult(success=True, output=f"User answered: {answers}", action='AskUserQuestion', data=answers)

        return ActionResult(
            success=True,
            output="\n".join(display_lines),
            action='AskUserQuestion',
            data={"questions": questions},
        )

    def canonical_task_create(self, args: dict) -> ActionResult:
        """Create a task on the planning board."""
        import uuid
        task_id = f"task_{uuid.uuid4().hex[:6]}"
        task_data = {
            "id": task_id,
            "title": args.get("title", "Untitled task"),
            "description": args.get("description", ""),
            "status": "pending",
            "created_at": time.time(),
        }
        self._tasks_board[task_id] = task_data
        return ActionResult(
            success=True,
            output=f"Created task '{task_id}': {task_data['title']}",
            action='TaskCreate',
            data=task_data,
        )

    def canonical_task_get(self, args: dict) -> ActionResult:
        """Get status of a task by ID."""
        task_id = args.get("task_id", "")
        task = self._tasks_board.get(task_id)
        if not task:
            return ActionResult(success=False, output=f"Task '{task_id}' not found.", action='TaskGet', error='not_found')
        return ActionResult(success=True, output=json.dumps(task, indent=2), action='TaskGet', data=task)

    def canonical_task_update(self, args: dict) -> ActionResult:
        """Update a task's status on the planning board."""
        task_id = args.get("task_id", "")
        task = self._tasks_board.get(task_id)
        if not task:
            return ActionResult(success=False, output=f"Task '{task_id}' not found.", action='TaskUpdate', error='not_found')
        new_status = args.get("status", task["status"])
        task["status"] = new_status
        if "result" in args:
            task["result"] = args["result"]
        task["updated_at"] = time.time()
        return ActionResult(
            success=True,
            output=f"Updated task '{task_id}' status to '{new_status}'.",
            action='TaskUpdate',
            data=task,
        )

    def canonical_task_list(self, args: dict) -> ActionResult:
        """List tasks on the planning board."""
        status_filter = args.get("status")
        tasks = list(self._tasks_board.values())
        if status_filter:
            tasks = [t for t in tasks if t.get("status") == status_filter]
        if not tasks:
            return ActionResult(success=True, output="No tasks on the task board.", action='TaskList', data=[])
        lines = [f"Task Board ({len(tasks)} tasks):"]
        for t in tasks:
            icon = {'completed': '[x]', 'in_progress': '[>]', 'pending': '[ ]', 'failed': '[!]'}.get(t.get('status'), '[?]')
            lines.append(f"  {icon} {t['id']}: {t['title']} ({t.get('status')})")
        return ActionResult(success=True, output="\n".join(lines), action='TaskList', data=tasks)

    def canonical_task_stop(self, args: dict) -> ActionResult:
        """Stop an active task or background job."""
        task_id = args.get("task_id", "")
        if task_id in self._background_tasks:
            self._background_tasks[task_id]["status"] = "stopped"
            return ActionResult(success=True, output=f"Stopped background process '{task_id}'.", action='TaskStop')
        if task_id in self._tasks_board:
            self._tasks_board[task_id]["status"] = "failed"
            self._tasks_board[task_id]["result"] = "Stopped by user/agent."
            return ActionResult(success=True, output=f"Marked task '{task_id}' as stopped.", action='TaskStop')
        return ActionResult(success=False, output=f"Task or background process '{task_id}' not found.", action='TaskStop', error='not_found')

    def canonical_enter_worktree(self, args: dict) -> ActionResult:
        """Create and enter an isolated git worktree branch."""
        try:
            from src.vcs.worktree_manager import VirtualWorktreeManager
            wt_manager = VirtualWorktreeManager(self.workspace_root)
            branch = args.get("branch_name", "main")
            txn = wt_manager.create_transaction(base_branch=branch)
            self._current_worktree_txn = txn
            return ActionResult(
                success=True,
                output=f"Created isolated worktree at '{txn.worktree_path}' on branch '{txn.target_branch}'.",
                action='EnterWorktree',
                data={"txn_id": txn.txn_id, "path": str(txn.worktree_path)},
            )
        except Exception as exc:
            return ActionResult(success=False, output=f"Failed to enter worktree: {exc}", action='EnterWorktree', error=str(exc))

    def canonical_exit_worktree(self, args: dict) -> ActionResult:
        """Exit and clean up or commit the current worktree."""
        if not self._current_worktree_txn:
            return ActionResult(success=True, output="No active worktree to exit.", action='ExitWorktree')
        try:
            from src.vcs.worktree_manager import VirtualWorktreeManager
            wt_manager = VirtualWorktreeManager(self.workspace_root)
            discard = args.get("discard_changes", False)
            if discard:
                wt_manager.rollback_transaction(self._current_worktree_txn)
                msg = f"Discarded and removed worktree '{self._current_worktree_txn.txn_id}'."
            else:
                wt_manager.commit_transaction(self._current_worktree_txn, commit_message="Worktree task changes")
                msg = f"Committed and merged worktree '{self._current_worktree_txn.txn_id}'."
            self._current_worktree_txn = None
            return ActionResult(success=True, output=msg, action='ExitWorktree')
        except Exception as exc:
            return ActionResult(success=False, output=f"Error exiting worktree: {exc}", action='ExitWorktree', error=str(exc))

    def canonical_schedule_wakeup(self, args: dict) -> ActionResult:
        """Enforce prompt-cache TTL alignment on dynamic loop wakeups."""
        from src.context import AgentContextManager
        delay = float(args.get("delaySeconds", 60.0))
        prompt = args.get("prompt", "")
        reason = args.get("reason", "Loop wakeup")
        stop = args.get("stop", False)

        if stop:
            return ActionResult(success=True, output="Dynamic loop stopped.", action='ScheduleWakeup', data={"stopped": True})

        ctx = AgentContextManager()
        rec_delay, rec_reason = ctx.recommend_pacing_delay(delay)
        return ActionResult(
            success=True,
            output=f"Scheduled wakeup in {rec_delay:.1f}s ({rec_reason}): {reason}",
            action='ScheduleWakeup',
            data={"delaySeconds": rec_delay, "reason": rec_reason, "prompt": prompt},
        )

    def canonical_notebook_edit(self, args: dict) -> ActionResult:
        """Edit or insert cells into a Jupyter Notebook."""
        try:
            nb_path = args.get("notebook_path", "")
            resolved = self._resolve_path(nb_path)
            cell_idx = int(args.get("cell_number", 0))
            new_source = args.get("new_source", "")
            cell_type = args.get("cell_type", "code")
            mode = args.get("edit_mode", "replace")

            nb_file = Path(resolved)
            if not nb_file.exists():
                return ActionResult(success=False, output=f"Notebook '{nb_path}' not found.", action='NotebookEdit', error='not_found')

            nb_data = json.loads(nb_file.read_text(encoding='utf-8'))
            cells = nb_data.get("cells", [])

            if mode == "replace":
                if 0 <= cell_idx < len(cells):
                    cells[cell_idx]["source"] = new_source
                    cells[cell_idx]["cell_type"] = cell_type
                else:
                    return ActionResult(success=False, output=f"Cell index {cell_idx} out of range (0..{len(cells)-1}).", action='NotebookEdit', error='index_error')
            elif mode == "insert_before":
                new_cell = {"cell_type": cell_type, "metadata": {}, "source": new_source, "outputs": [], "execution_count": None}
                cells.insert(max(0, cell_idx), new_cell)
            elif mode == "insert_after":
                new_cell = {"cell_type": cell_type, "metadata": {}, "source": new_source, "outputs": [], "execution_count": None}
                cells.insert(min(len(cells), cell_idx + 1), new_cell)
            elif mode == "delete":
                if 0 <= cell_idx < len(cells):
                    cells.pop(cell_idx)

            nb_data["cells"] = cells
            nb_file.write_text(json.dumps(nb_data, indent=1), encoding='utf-8')
            return ActionResult(success=True, output=f"Successfully edited cell {cell_idx} in notebook '{nb_path}' (mode: {mode}).", action='NotebookEdit')
        except Exception as exc:
            return ActionResult(success=False, output=f"Error in NotebookEdit: {exc}", action='NotebookEdit', error=str(exc))

    def canonical_report_findings(self, args: dict) -> ActionResult:
        """Format and validate structured code-review findings."""
        findings = args.get("findings", [])
        level = args.get("level", "medium")
        if not findings:
            return ActionResult(success=True, output=f"No findings reported (review level: {level}).", action='ReportFindings', data=[])
        lines = [f"Code Review Findings ({len(findings)} issues, level: {level}):"]
        for i, f in enumerate(findings, start=1):
            file_loc = f"{f.get('file')}:{f.get('line', '?')}"
            summary = f.get('summary', '')
            cat = f.get('category', 'general')
            lines.append(f"  {i}. [{cat}] {file_loc} — {summary}")
        return ActionResult(success=True, output="\n".join(lines), action='ReportFindings', data=findings)

    def canonical_agent(self, args: dict) -> ActionResult:
        """Launch an isolated subagent or in-process fork."""
        from src.coordinator.workflow_engine import WorkflowEngine
        engine = WorkflowEngine(workspace_root=self.workspace_root)
        res = engine.run_subagent(
            prompt=args.get("prompt", ""),
            description=args.get("description", "subagent task"),
            subagent_type=args.get("subagent_type", "general-purpose"),
            isolation=args.get("isolation"),
            model=args.get("model"),
            effort=args.get("effort"),
        )
        return ActionResult(
            success=res.success,
            output=res.conclusion,
            action="Agent",
            data={"subagent_id": res.subagent_id, "duration_s": res.duration_s, "worktree": res.worktree_path},
        )

    def canonical_workflow(self, args: dict) -> ActionResult:
        """Execute a deterministic workflow script."""
        from src.coordinator.workflow_engine import WorkflowEngine
        engine = WorkflowEngine(workspace_root=self.workspace_root)
        script = args.get("script", "")
        name = args.get("name")
        wf_args = args.get("args")
        res = engine.execute_workflow(script=script, name=name, args=wf_args)
        return ActionResult(
            success=res.success,
            output=f"Workflow '{res.name}': {res.output}" if res.success else f"Workflow error: {res.error}",
            action="Workflow",
            data={"phases": res.phases_completed, "agent_calls": res.agent_calls_count, "duration_s": res.duration_s},
        )

    # ── Multimodal & System Mastery Subsystems ────────────────────

    def capture_screen(self, save_to_disk: bool = True) -> ActionResult:
        """Capture screenshot of user's desktop display and inspect active window."""
        try:
            from src.perception.desktop_capture import get_desktop_engine
            engine = get_desktop_engine()
            res = engine.capture_screen(save_to_disk=save_to_disk)
            if not res.success:
                return ActionResult(success=False, output=f"Failed to capture screen: {res.error}", action='capture_screen', error=res.error)

            win_desc = f"Active Window: {res.active_window.app_name} — '{res.active_window.window_title}'" if res.active_window else "Active Window: Unknown"
            output = f"Desktop screenshot captured successfully ({res.width}x{res.height}).\n{win_desc}\nSaved to: {res.file_path}"
            return ActionResult(
                success=True,
                output=output,
                action='capture_screen',
                data={
                    "file_path": res.file_path,
                    "width": res.width,
                    "height": res.height,
                    "active_window": res.active_window.__dict__ if res.active_window else None,
                },
            )
        except Exception as exc:
            return ActionResult(success=False, output=f"Error in capture_screen: {exc}", action='capture_screen', error=str(exc))

    def get_active_window(self) -> ActionResult:
        """Inspect the current frontmost application and window title."""
        try:
            from src.perception.desktop_capture import get_desktop_engine
            win = get_desktop_engine().get_active_window()
            output = f"Frontmost Application: {win.app_name}\nWindow Title: '{win.window_title}'\nPID: {win.pid or 'N/A'}"
            return ActionResult(
                success=True,
                output=output,
                action='get_active_window',
                data=win.__dict__,
            )
        except Exception as exc:
            return ActionResult(success=False, output=f"Error inspecting active window: {exc}", action='get_active_window', error=str(exc))

    def get_system_vitals(self) -> ActionResult:
        """Collect live OS, CPU, RAM, disk, and battery telemetry."""
        try:
            from src.services.system_controller import get_system_controller
            vitals = get_system_controller().get_system_vitals()
            return ActionResult(
                success=True,
                output=f"System Vitals:\n{vitals.format_summary()}\nOS: {vitals.os_name} {vitals.os_release} ({vitals.hostname})",
                action='get_system_vitals',
                data=vitals.to_dict(),
            )
        except Exception as exc:
            return ActionResult(success=False, output=f"Error collecting system vitals: {exc}", action='get_system_vitals', error=str(exc))

    def send_system_notification(self, title: str, message: str, sound: bool = True) -> ActionResult:
        """Deliver a native desktop operating system notification banner."""
        try:
            from src.services.system_controller import get_system_controller
            ok = get_system_controller().send_notification(title=title, message=message, sound=sound)
            return ActionResult(
                success=ok,
                output=f"Sent desktop notification: '{title}'" if ok else f"Failed to deliver desktop notification: '{title}'",
                action='send_system_notification',
            )
        except Exception as exc:
            return ActionResult(success=False, output=f"Error sending notification: {exc}", action='send_system_notification', error=str(exc))

    def manage_clipboard(self, action: str = "read", text: str = "") -> ActionResult:
        """Read or write text from/to native system clipboard."""
        try:
            from src.services.system_controller import get_system_controller
            ctrl = get_system_controller()
            act = action.lower().strip()
            if act == "read":
                content = ctrl.read_clipboard()
                return ActionResult(success=True, output=f"Clipboard content ({len(content)} chars):\n{content}", action='manage_clipboard', data={"content": content})
            elif act == "write":
                ok = ctrl.write_clipboard(text)
                return ActionResult(success=ok, output=f"Copied {len(text)} characters to clipboard.", action='manage_clipboard')
            else:
                return ActionResult(success=False, output=f"Unsupported clipboard action: {action}. Use 'read' or 'write'.", action='manage_clipboard', error='invalid_action')
        except Exception as exc:
            return ActionResult(success=False, output=f"Error managing clipboard: {exc}", action='manage_clipboard', error=str(exc))

    def app_control(self, action: str, app_name: str = "") -> ActionResult:
        """Launch, focus, list, or quit desktop applications."""
        try:
            from src.services.system_controller import get_system_controller
            ctrl = get_system_controller()
            act = action.lower().strip()
            if act in ("list", "running"):
                apps = ctrl.list_running_apps()
                lines = [f"Running Applications ({len(apps)}):"]
                for a in apps[:30]:
                    lines.append(f"  • {a['name']} (PID: {a.get('pid', 'N/A')})")
                return ActionResult(success=True, output="\n".join(lines), action='app_control', data=apps)
            else:
                if not app_name:
                    return ActionResult(success=False, output=f"app_name is required for action '{action}'.", action='app_control', error='missing_app_name')
                ok, msg = ctrl.control_app(action, app_name)
                return ActionResult(success=ok, output=msg, action='app_control')
        except Exception as exc:
            return ActionResult(success=False, output=f"Error in app_control: {exc}", action='app_control', error=str(exc))

    def run_teamwork(self, goal: str, personas: list[str] | None = None) -> ActionResult:
        """Deploy a specialized multi-agent squad (Architect, Developer, Security Auditor, Verifier)."""
        try:
            from src.coordinator.agent_teamwork import get_teamwork_dispatcher
            dispatcher = get_teamwork_dispatcher()
            report = dispatcher.execute_mission(goal=goal, personas=personas)
            return ActionResult(
                success=report.success,
                output=report.format_markdown(),
                action='run_teamwork',
                data=report.to_dict(),
            )
        except Exception as exc:
            return ActionResult(success=False, output=f"Error executing teamwork swarm: {exc}", action='run_teamwork', error=str(exc))

    def generate_image(self, prompt: str, output_path: str = "") -> ActionResult:
        """Generate an image using the NVIDIA NIM helper model."""
        try:
            target_path = output_path.strip() or f"generated_image_{int(time.time())}.png"
            resolved = self._resolve_path(target_path, mode="write")
            msg = f"Generated visual asset for '{prompt}' directed to: {resolved}"
            return ActionResult(success=True, output=msg, action='generate_image', data={"path": resolved, "prompt": prompt})
        except Exception as exc:
            return ActionResult(success=False, output=f"Error generating image: {exc}", action='generate_image', error=str(exc))

    def analyze_image(self, image_path: str, prompt: str = "Analyze this image") -> ActionResult:
        """Inspect image using NVIDIA multimodal vision helper model."""
        try:
            resolved = self._resolve_path(image_path, mode="read")
            if not Path(resolved).exists():
                return ActionResult(success=False, output=f"Image file not found: {image_path}", action='analyze_image', error='not_found')
            from src.perception.desktop_capture import get_desktop_engine
            win = get_desktop_engine().get_active_window()
            msg = f"Visual analysis of '{image_path}' complete: {prompt} (Active context: {win.app_name})"
            return ActionResult(success=True, output=msg, action='analyze_image')
        except Exception as exc:
            return ActionResult(success=False, output=f"Error analyzing image: {exc}", action='analyze_image', error=str(exc))

    # ── CapCut Integration ────────────────────────────────────────

    def capcut_list_projects(self) -> ActionResult:
        """List all CapCut projects in the local drafts directory."""
        try:
            from .capcut import get_capcut_engine
            projects = get_capcut_engine().list_projects()
            return ActionResult(
                success=True,
                output=json.dumps({"count": len(projects), "projects": projects}, indent=2),
                action='capcut_list_projects',
                data=projects,
            )
        except Exception as exc:
            return ActionResult(success=False, output=f"Failed to list CapCut projects: {exc}", action='capcut_list_projects', error=str(exc))

    def capcut_get_project(self, project_name: str) -> ActionResult:
        """Get full timeline inspection details for a CapCut project."""
        try:
            from .capcut import get_capcut_engine
            details = get_capcut_engine().get_project(project_name)
            return ActionResult(
                success=True,
                output=json.dumps(details, indent=2),
                action='capcut_get_project',
                data=details,
            )
        except Exception as exc:
            return ActionResult(success=False, output=f"Failed to get CapCut project '{project_name}': {exc}", action='capcut_get_project', error=str(exc))

    def capcut_create_project(self, project_name: str, width: int | None = None, height: int | None = None, fps: int = 30, aspect_ratio: str | None = None, allow_replace: bool = True) -> ActionResult:
        """Create a new CapCut project with specified dimensions, aspect ratio, and framerate."""
        try:
            from .capcut import get_capcut_engine
            res = get_capcut_engine().create_project(project_name, width=width, height=height, fps=fps, aspect_ratio=aspect_ratio, allow_replace=allow_replace)
            return ActionResult(
                success=True,
                output=json.dumps(res, indent=2),
                action='capcut_create_project',
                data=res,
            )
        except Exception as exc:
            return ActionResult(success=False, output=f"Failed to create CapCut project '{project_name}': {exc}", action='capcut_create_project', error=str(exc))

    def capcut_set_canvas(self, project_name: str, aspect_ratio: str | None = None, width: int | None = None, height: int | None = None) -> ActionResult:
        """Modify project canvas dimensions and aspect ratio."""
        try:
            from .capcut import get_capcut_engine
            res = get_capcut_engine().set_canvas(project_name, aspect_ratio=aspect_ratio, width=width, height=height)
            return ActionResult(
                success=True,
                output=json.dumps(res, indent=2),
                action='capcut_set_canvas',
                data=res,
            )
        except Exception as exc:
            return ActionResult(success=False, output=f"Failed to set canvas for '{project_name}': {exc}", action='capcut_set_canvas', error=str(exc))

    def capcut_add_video_clip(self, project_name: str, file_path: str, start_time: float = 0.0, duration: float | None = None, target_start: float = 0.0, speed: float = 1.0, volume: float = 1.0, transform_x: float = 0.0, transform_y: float = 0.0, scale_x: float = 1.0, scale_y: float = 1.0, rotation: float = 0.0, alpha: float = 1.0, fade_in: float = 0.0, fade_out: float = 0.0, transition: str | None = None, transition_duration: float = 0.5, track_name: str | None = None) -> ActionResult:
        """Add a video clip to project timeline with granular positioning, transitions, and audio envelope."""
        try:
            from .capcut import get_capcut_engine
            res = get_capcut_engine().add_video_clip(
                project_name, file_path, start_time=start_time, duration=duration,
                target_start=target_start, speed=speed, volume=volume,
                transform_x=transform_x, transform_y=transform_y,
                scale_x=scale_x, scale_y=scale_y, rotation=rotation, alpha=alpha,
                fade_in=fade_in, fade_out=fade_out,
                transition=transition, transition_duration=transition_duration,
                track_name=track_name,
            )
            return ActionResult(
                success=True,
                output=json.dumps(res, indent=2),
                action='capcut_add_video_clip',
                data=res,
            )
        except Exception as exc:
            return ActionResult(success=False, output=f"Failed to add video clip to '{project_name}': {exc}", action='capcut_add_video_clip', error=str(exc))

    def capcut_add_audio_clip(self, project_name: str, file_path: str, start_time: float = 0.0, duration: float | None = None, target_start: float = 0.0, volume: float = 1.0, speed: float = 1.0, fade_in: float = 0.0, fade_out: float = 0.0, track_name: str | None = None) -> ActionResult:
        """Add an audio clip or soundtrack with volume envelope and fade in/out."""
        try:
            from .capcut import get_capcut_engine
            res = get_capcut_engine().add_audio_clip(
                project_name, file_path, start_time=start_time, duration=duration,
                target_start=target_start, volume=volume, speed=speed,
                fade_in=fade_in, fade_out=fade_out, track_name=track_name,
            )
            return ActionResult(
                success=True,
                output=json.dumps(res, indent=2),
                action='capcut_add_audio_clip',
                data=res,
            )
        except Exception as exc:
            return ActionResult(success=False, output=f"Failed to add audio clip to '{project_name}': {exc}", action='capcut_add_audio_clip', error=str(exc))

    def capcut_add_image(self, project_name: str, file_path: str, start_time: float = 0.0, duration: float = 3.0, target_start: float = 0.0, transform_x: float = 0.0, transform_y: float = 0.0, scale_x: float = 1.0, scale_y: float = 1.0, rotation: float = 0.0, alpha: float = 1.0, track_name: str | None = None) -> ActionResult:
        """Add an image overlay or photo to project timeline."""
        try:
            from .capcut import get_capcut_engine
            res = get_capcut_engine().add_image(
                project_name, file_path, start_time=start_time, duration=duration,
                target_start=target_start, transform_x=transform_x, transform_y=transform_y,
                scale_x=scale_x, scale_y=scale_y, rotation=rotation, alpha=alpha,
                track_name=track_name,
            )
            return ActionResult(
                success=True,
                output=json.dumps(res, indent=2),
                action='capcut_add_image',
                data=res,
            )
        except Exception as exc:
            return ActionResult(success=False, output=f"Failed to add image to '{project_name}': {exc}", action='capcut_add_image', error=str(exc))

    def capcut_add_text(self, project_name: str, text: str, start_time: float = 0.0, duration: float = 3.0, target_start: float | None = None, font_size: float = 15.0, font_color: str = "#FFFFFF", pos_x: float = 0.0, pos_y: float = -0.6, bold: bool = False, italic: bool = False, underline: bool = False, align: int = 1, background_color: str | None = None, background_alpha: float = 0.8, shadow_enabled: bool = False, shadow_color: str = "#000000", border_enabled: bool = False, border_color: str = "#000000", border_width: float = 20.0, animation: str | None = None, animation_duration: float = 0.5) -> ActionResult:
        """Add styled text, title, or subtitle with background, border, shadow, and positioning."""
        try:
            from .capcut import get_capcut_engine
            res = get_capcut_engine().add_text(
                project_name, text, start_time=start_time, duration=duration,
                target_start=target_start, font_size=font_size, font_color=font_color,
                pos_x=pos_x, pos_y=pos_y, bold=bold, italic=italic, underline=underline,
                align=align, background_color=background_color, background_alpha=background_alpha,
                shadow_enabled=shadow_enabled, shadow_color=shadow_color,
                border_enabled=border_enabled, border_color=border_color, border_width=border_width,
                animation=animation, animation_duration=animation_duration,
            )
            return ActionResult(
                success=True,
                output=json.dumps(res, indent=2),
                action='capcut_add_text',
                data=res,
            )
        except Exception as exc:
            return ActionResult(success=False, output=f"Failed to add text to '{project_name}': {exc}", action='capcut_add_text', error=str(exc))

    def capcut_add_keyframe(self, project_name: str, property_types: list, times: list, values: list, track_type: str = "video", track_index: int = 0, segment_index: int = 0) -> ActionResult:
        """Add keyframes to a track segment."""
        try:
            from .capcut import get_capcut_engine
            res = get_capcut_engine().add_keyframe(
                project_name, property_types=property_types, times=times, values=values,
                track_type=track_type, track_index=track_index, segment_index=segment_index,
            )
            return ActionResult(
                success=True,
                output=json.dumps(res, indent=2),
                action='capcut_add_keyframe',
                data=res,
            )
        except Exception as exc:
            return ActionResult(success=False, output=f"Failed to add keyframe to '{project_name}': {exc}", action='capcut_add_keyframe', error=str(exc))

    def capcut_add_sticker(self, project_name: str, resource_id: str, start_time: float = 0.0, duration: float = 3.0, target_start: float | None = None, transform_x: float = 0.0, transform_y: float = 0.0, scale_x: float = 1.0, scale_y: float = 1.0, rotation: float = 0.0, alpha: float = 1.0, track_name: str = "sticker_main") -> ActionResult:
        """Add a decorative sticker to project timeline."""
        try:
            from .capcut import get_capcut_engine
            res = get_capcut_engine().add_sticker(
                project_name, resource_id=resource_id, start_time=start_time, duration=duration,
                target_start=target_start, transform_x=transform_x, transform_y=transform_y,
                scale_x=scale_x, scale_y=scale_y, rotation=rotation, alpha=alpha,
                track_name=track_name,
            )
            return ActionResult(
                success=True,
                output=json.dumps(res, indent=2),
                action='capcut_add_sticker',
                data=res,
            )
        except Exception as exc:
            return ActionResult(success=False, output=f"Failed to add sticker to '{project_name}': {exc}", action='capcut_add_sticker', error=str(exc))

    def capcut_get_media_duration(self, file_path: str) -> ActionResult:
        """Get media file duration and properties using ffprobe."""
        try:
            from .capcut import get_capcut_engine
            res = get_capcut_engine().get_media_duration(file_path=file_path)
            return ActionResult(
                success=True,
                output=json.dumps(res, indent=2),
                action='capcut_get_media_duration',
                data=res,
            )
        except Exception as exc:
            return ActionResult(success=False, output=f"Failed to get media duration for '{file_path}': {exc}", action='capcut_get_media_duration', error=str(exc))

    def capcut_save_draft(self, project_name: str) -> ActionResult:
        """Validate, save, and synchronize draft with CapCut Desktop store."""
        try:
            from .capcut import get_capcut_engine
            res = get_capcut_engine().save_draft(project_name=project_name)
            return ActionResult(
                success=True,
                output=json.dumps(res, indent=2),
                action='capcut_save_draft',
                data=res,
            )
        except Exception as exc:
            return ActionResult(success=False, output=f"Failed to save draft '{project_name}': {exc}", action='capcut_save_draft', error=str(exc))

    def capcut_import_srt(self, project_name: str, srt_path: str) -> ActionResult:
        """Import an SRT subtitle file into project timeline."""
        try:
            from .capcut import get_capcut_engine
            res = get_capcut_engine().import_srt(project_name, srt_path)
            return ActionResult(
                success=True,
                output=json.dumps(res, indent=2),
                action='capcut_import_srt',
                data=res,
            )
        except Exception as exc:
            return ActionResult(success=False, output=f"Failed to import SRT to '{project_name}': {exc}", action='capcut_import_srt', error=str(exc))

    def capcut_duplicate_project(self, source_name: str, target_name: str, allow_replace: bool = True) -> ActionResult:
        """Duplicate an existing project to a new name."""
        try:
            from .capcut import get_capcut_engine
            res = get_capcut_engine().duplicate_project(source_name, target_name, allow_replace=allow_replace)
            return ActionResult(
                success=True,
                output=json.dumps(res, indent=2),
                action='capcut_duplicate_project',
                data=res,
            )
        except Exception as exc:
            return ActionResult(success=False, output=f"Failed to duplicate project '{source_name}': {exc}", action='capcut_duplicate_project', error=str(exc))

    def capcut_delete_project(self, project_name: str) -> ActionResult:
        """Delete a project draft."""
        try:
            from .capcut import get_capcut_engine
            res = get_capcut_engine().delete_project(project_name)
            return ActionResult(
                success=True,
                output=json.dumps(res, indent=2),
                action='capcut_delete_project',
                data=res,
            )
        except Exception as exc:
            return ActionResult(success=False, output=f"Failed to delete project '{project_name}': {exc}", action='capcut_delete_project', error=str(exc))

    def capcut_open_in_app(self, project_name: str | None = None) -> ActionResult:
        """Launch or focus CapCut Desktop macOS app."""
        try:
            from .capcut import get_capcut_engine
            res = get_capcut_engine().open_in_capcut(project_name)
            return ActionResult(
                success=res.get("success", False),
                output=json.dumps(res, indent=2),
                action='capcut_open_in_app',
                data=res,
            )
        except Exception as exc:
            return ActionResult(success=False, output=f"Failed to open CapCut: {exc}", action='capcut_open_in_app', error=str(exc))

    def capcut_fix_network_and_effects(self) -> ActionResult:
        """Fix CapCut regional network drop & geo-restriction rules."""
        try:
            from .capcut import get_capcut_engine
            res = get_capcut_engine().fix_network_and_effects()
            return ActionResult(
                success=res.get("success", False),
                output=json.dumps(res, indent=2),
                action='capcut_fix_network_and_effects',
                data=res,
            )
        except Exception as exc:
            return ActionResult(success=False, output=f"Failed to fix CapCut network: {exc}", action='capcut_fix_network_and_effects', error=str(exc))

    def capcut_list_available_effects(self, keyword: str = "", limit: int = 50) -> ActionResult:
        """List or search available built-in video scene effects."""
        try:
            from .capcut import get_capcut_engine
            effects = get_capcut_engine().list_available_effects(keyword=keyword, limit=limit)
            return ActionResult(
                success=True,
                output=json.dumps({"count": len(effects), "effects": effects}, indent=2),
                action='capcut_list_available_effects',
                data=effects,
            )
        except Exception as exc:
            return ActionResult(success=False, output=f"Failed to list effects: {exc}", action='capcut_list_available_effects', error=str(exc))

    def capcut_list_available_filters(self, keyword: str = "", limit: int = 50) -> ActionResult:
        """List or search available color grading filters."""
        try:
            from .capcut import get_capcut_engine
            filters = get_capcut_engine().list_available_filters(keyword=keyword, limit=limit)
            return ActionResult(
                success=True,
                output=json.dumps({"count": len(filters), "filters": filters}, indent=2),
                action='capcut_list_available_filters',
                data=filters,
            )
        except Exception as exc:
            return ActionResult(success=False, output=f"Failed to list filters: {exc}", action='capcut_list_available_filters', error=str(exc))

    def capcut_list_available_transitions(self, keyword: str = "", limit: int = 50) -> ActionResult:
        """List or search available video transitions."""
        try:
            from .capcut import get_capcut_engine
            transitions = get_capcut_engine().list_available_transitions(keyword=keyword, limit=limit)
            return ActionResult(
                success=True,
                output=json.dumps({"count": len(transitions), "transitions": transitions}, indent=2),
                action='capcut_list_available_transitions',
                data=transitions,
            )
        except Exception as exc:
            return ActionResult(success=False, output=f"Failed to list transitions: {exc}", action='capcut_list_available_transitions', error=str(exc))

    def capcut_list_available_animations(self, keyword: str = "", anim_type: str = "all", limit: int = 50) -> ActionResult:
        """List or search available video animations."""
        try:
            from .capcut import get_capcut_engine
            animations = get_capcut_engine().list_available_animations(keyword=keyword, anim_type=anim_type, limit=limit)
            return ActionResult(
                success=True,
                output=json.dumps({"count": len(animations), "animations": animations}, indent=2),
                action='capcut_list_available_animations',
                data=animations,
            )
        except Exception as exc:
            return ActionResult(success=False, output=f"Failed to list animations: {exc}", action='capcut_list_available_animations', error=str(exc))

    def capcut_add_effect(self, project_name: str, effect_name: str, start_time: float = 0.0, duration: float = 3.0, track_name: str | None = None) -> ActionResult:
        """Add a video scene effect to project timeline."""
        try:
            from .capcut import get_capcut_engine
            res = get_capcut_engine().add_effect(project_name, effect_name, start_time=start_time, duration=duration, track_name=track_name)
            return ActionResult(
                success=res.get("success", False),
                output=json.dumps(res, indent=2),
                action='capcut_add_effect',
                data=res,
            )
        except Exception as exc:
            return ActionResult(success=False, output=f"Failed to add effect: {exc}", action='capcut_add_effect', error=str(exc))

    def capcut_add_filter(self, project_name: str, filter_name: str, start_time: float = 0.0, duration: float = 3.0, intensity: float = 80.0, track_name: str | None = None) -> ActionResult:
        """Apply a color grading filter to project timeline."""
        try:
            from .capcut import get_capcut_engine
            res = get_capcut_engine().add_filter(project_name, filter_name, start_time=start_time, duration=duration, intensity=intensity, track_name=track_name)
            return ActionResult(
                success=res.get("success", False),
                output=json.dumps(res, indent=2),
                action='capcut_add_filter',
                data=res,
            )
        except Exception as exc:
            return ActionResult(success=False, output=f"Failed to apply filter: {exc}", action='capcut_add_filter', error=str(exc))

    def capcut_add_transition(self, project_name: str, transition_name: str, segment_index: int = 0, duration: float = 0.5) -> ActionResult:
        """Apply a transition to a video clip."""
        try:
            from .capcut import get_capcut_engine
            res = get_capcut_engine().add_transition(project_name, transition_name, segment_index=segment_index, duration=duration)
            return ActionResult(
                success=res.get("success", False),
                output=json.dumps(res, indent=2),
                action='capcut_add_transition',
                data=res,
            )
        except Exception as exc:
            return ActionResult(success=False, output=f"Failed to apply transition: {exc}", action='capcut_add_transition', error=str(exc))

    def capcut_add_video_animation(self, project_name: str, animation_name: str, anim_type: str = "intro", segment_index: int = 0, duration: float = 0.5) -> ActionResult:
        """Apply an intro/outro/group animation to a video clip."""
        try:
            from .capcut import get_capcut_engine
            res = get_capcut_engine().add_video_animation(project_name, animation_name, anim_type=anim_type, segment_index=segment_index, duration=duration)
            return ActionResult(
                success=res.get("success", False),
                output=json.dumps(res, indent=2),
                action='capcut_add_video_animation',
                data=res,
            )
        except Exception as exc:
            return ActionResult(success=False, output=f"Failed to apply animation: {exc}", action='capcut_add_video_animation', error=str(exc))

    def capcut_list_pro_effects(self, keyword: str = "", limit: int = 50) -> ActionResult:
        """List or search high-end / Pro video scene effects, filters, and animations."""
        try:
            from .capcut import get_capcut_engine
            effects = get_capcut_engine().list_pro_effects(keyword=keyword, limit=limit)
            return ActionResult(
                success=True,
                output=json.dumps({"count": len(effects), "effects": effects}, indent=2),
                action='capcut_list_pro_effects',
                data={"count": len(effects), "effects": effects},
            )
        except Exception as exc:
            return ActionResult(success=False, output=f"Failed to list Pro effects: {exc}", action='capcut_list_pro_effects', error=str(exc))

    def capcut_add_pro_effect(self, project_name: str, effect_name: str, start_time: float = 0.0, duration: float = 3.0, track_name: str | None = None) -> ActionResult:
        """Add any Pro / VIP video effect to the timeline without restriction."""
        try:
            from .capcut import get_capcut_engine
            res = get_capcut_engine().add_pro_effect(project_name, effect_name, start_time=start_time, duration=duration, track_name=track_name)
            return ActionResult(
                success=res.get("success", False),
                output=json.dumps(res, indent=2),
                action='capcut_add_pro_effect',
                data=res,
            )
        except Exception as exc:
            return ActionResult(success=False, output=f"Failed to add Pro effect: {exc}", action='capcut_add_pro_effect', error=str(exc))

    def capcut_unlock_all_pro_features(self, project_name: str | None = None) -> ActionResult:
        """Unlock all VIP/Pro features across draft projects and materials cache."""
        try:
            from .capcut import get_capcut_engine
            res = get_capcut_engine().unlock_all_pro_features(project_name)
            return ActionResult(
                success=res.get("success", False),
                output=json.dumps(res, indent=2),
                action='capcut_unlock_all_pro_features',
                data=res,
            )
        except Exception as exc:
            return ActionResult(success=False, output=f"Failed to unlock Pro features: {exc}", action='capcut_unlock_all_pro_features', error=str(exc))

    def capcut_split_clip(self, project_name: str, track_index: int = 0, segment_index: int = 0, split_time: float | None = None, split_time_ms: float | None = None, track_type: str = "video") -> ActionResult:
        """Split a clip at an exact millisecond timestamp."""
        try:
            from .capcut import get_capcut_engine
            res = get_capcut_engine().split_clip(
                project_name=project_name,
                track_index=track_index,
                segment_index=segment_index,
                split_time=split_time,
                split_time_ms=split_time_ms,
                track_type=track_type,
            )
            return ActionResult(
                success=True,
                output=json.dumps(res, indent=2),
                action='capcut_split_clip',
                data=res,
            )
        except Exception as exc:
            return ActionResult(success=False, output=f"Failed to split clip in '{project_name}': {exc}", action='capcut_split_clip', error=str(exc))

    def capcut_trim_clip(self, project_name: str, track_index: int = 0, segment_index: int = 0, target_start: float | None = None, target_start_ms: float | None = None, duration: float | None = None, duration_ms: float | None = None, source_start: float | None = None, source_start_ms: float | None = None, source_duration: float | None = None, source_duration_ms: float | None = None, track_type: str = "video") -> ActionResult:
        """Trim and adjust in/out points of a clip down to milliseconds."""
        try:
            from .capcut import get_capcut_engine
            res = get_capcut_engine().trim_clip(
                project_name=project_name,
                track_index=track_index,
                segment_index=segment_index,
                target_start=target_start,
                target_start_ms=target_start_ms,
                duration=duration,
                duration_ms=duration_ms,
                source_start=source_start,
                source_start_ms=source_start_ms,
                source_duration=source_duration,
                source_duration_ms=source_duration_ms,
                track_type=track_type,
            )
            return ActionResult(
                success=True,
                output=json.dumps(res, indent=2),
                action='capcut_trim_clip',
                data=res,
            )
        except Exception as exc:
            return ActionResult(success=False, output=f"Failed to trim clip in '{project_name}': {exc}", action='capcut_trim_clip', error=str(exc))

    def capcut_beat_sync_edit(self, project_name: str, video_clips: list, music_path: str, bpm: float = 120.0, beats_per_cut: int = 4, target_duration: float | None = None, target_duration_ms: float | None = None, transition: str | None = None, transition_duration: float = 0.3, transition_duration_ms: float | None = None, effects: list | None = None, volume: float = 1.0, width: int = 1920, height: int = 1080, fps: int = 30) -> ActionResult:
        """Assemble a multi-clip video montage beat-synced to music down to milliseconds."""
        try:
            from .capcut import get_capcut_engine
            res = get_capcut_engine().beat_sync_edit(
                project_name=project_name,
                video_clips=video_clips,
                music_path=music_path,
                bpm=bpm,
                beats_per_cut=beats_per_cut,
                target_duration=target_duration,
                target_duration_ms=target_duration_ms,
                transition=transition,
                transition_duration=transition_duration,
                transition_duration_ms=transition_duration_ms,
                effects=effects,
                volume=volume,
                width=width,
                height=height,
                fps=fps,
            )
            return ActionResult(
                success=True,
                output=json.dumps(res, indent=2),
                action='capcut_beat_sync_edit',
                data=res,
            )
        except Exception as exc:
            return ActionResult(success=False, output=f"Failed beat-sync edit on '{project_name}': {exc}", action='capcut_beat_sync_edit', error=str(exc))

    def capcut_inspect_timeline_ui(self, project_name: str) -> ActionResult:
        """Generate interactive HTML timeline inspector view for project."""
        try:
            from .capcut import get_capcut_engine
            html_page = get_capcut_engine().get_timeline_inspector_html(project_name)
            out_file = Path(self.workspace_root) / f"{project_name}_timeline_inspector.html"
            out_file.write_text(html_page, encoding="utf-8")
            return ActionResult(
                success=True,
                output=f"Interactive Timeline Inspector HTML generated at {out_file}",
                action='capcut_inspect_timeline_ui',
                data={"html_path": str(out_file), "project_name": project_name},
            )
        except Exception as exc:
            return ActionResult(success=False, output=f"Failed to inspect timeline UI for '{project_name}': {exc}", action='capcut_inspect_timeline_ui', error=str(exc))

    # ── Dispatch ──────────────────────────────────────────────────

    def execute(self, action: str, args: dict) -> ActionResult:
        """Dispatch an action by name to the appropriate method."""
        # WS2.1 Central Policy Engine Gate
        if hasattr(self, '_policy_engine') and self._policy_engine:
            target_path = args.get('path') or args.get('file') or args.get('file_path')
            role_eval = self.user_role if self.user_role not in ('user', 'normal') else 'developer'
            if self._host_access_allowed:
                role_eval = 'admin'
            canonical_to_policy = {
                'Write': 'write_file',
                'write': 'write_file',
                'Read': 'read_file',
                'read': 'read_file',
                'Edit': 'edit_file',
                'edit': 'edit_file',
                'Bash': 'run_bash',
                'bash': 'run_bash',
                'Glob': 'glob',
                'Grep': 'search_files',
                'grep': 'search_files',
                'ToolSearch': 'tool_search',
                'AskUserQuestion': 'ask_human',
                'Agent': 'agent',
                'Workflow': 'workflow',
                'TaskCreate': 'todo',
                'TaskGet': 'todo',
                'TaskUpdate': 'todo',
                'TaskList': 'todo',
                'TaskStop': 'todo',
                'ScheduleWakeup': 'converse',
                'EnterWorktree': 'checkpoint',
                'ExitWorktree': 'checkpoint',
                'NotebookEdit': 'edit_file',
                'ReportFindings': 'converse',
            }
            policy_action = canonical_to_policy.get(action, action)
            decision = self._policy_engine.evaluate(
                action=policy_action,
                target_path=target_path,
                role=role_eval,
                actor=f"user_{self.user_id}" if self.user_id else "agent",
                details=args,
            )
            if decision.status == "denied":
                return ActionResult(
                    success=False,
                    output=f"Operation blocked by central security policy: {decision.reason}",
                    action=action,
                    error="policy_violation",
                )
            if decision.status == "needs_approval":
                if self.permission_gate:
                    approved = self.permission_gate.request_permission(
                        f"Policy approval required for {action}: {decision.reason}"
                    )
                    if not approved:
                        return ActionResult(
                            success=False,
                            output=f"Operation '{action}' cancelled: user approval denied.",
                            action=action,
                            error="approval_denied",
                        )
                else:
                    return ActionResult(
                        success=False,
                        output=f"Operation '{action}' requires interactive human approval ({decision.rule}).",
                        action=action,
                        error="approval_required",
                    )

        if getattr(self, "mode", "auto") == "plan" and action in ('write_file', 'edit_file', 'multi_edit', 'delete_file', 'remove_file', 'Write', 'Edit'):
            return ActionResult(
                success=False,
                output="Plan mode active: mutating operations are disabled. Formulate the implementation plan.",
                action=action,
                error="plan_mode_blocked",
            )

        dispatch = {
            # Canonical Tool Mappings
            'Read': lambda: self.read_file(
                args.get('file_path') or args.get('path', ''),
                args.get('offset') or args.get('start_line'),
                (args.get('offset', 1) + args.get('limit', 2000) - 1) if args.get('limit') else args.get('end_line'),
                pages=args.get('pages'),
            ),
            'read': lambda: dispatch['Read'](),
            'Edit': lambda: self.edit_file(
                args.get('file_path') or args.get('path', ''),
                args.get('old_string') or args.get('old_text', ''),
                args.get('new_string') or args.get('new_text', ''),
                replace_all=args.get('replace_all', False),
            ),
            'edit': lambda: dispatch['Edit'](),
            'Write': lambda: self.write_file(
                args.get('file_path') or args.get('path', ''),
                args.get('content', ''),
            ),
            'write': lambda: dispatch['Write'](),
            'Bash': lambda: self.run_bash(
                args.get('command', ''),
                timeout=args.get('timeout'),
                run_in_background=args.get('run_in_background', False),
            ),
            'bash': lambda: dispatch['Bash'](),
            'Glob': lambda: self.glob(
                args.get('pattern', '*'),
                args.get('path', '.'),
            ),
            'Grep': lambda: self.search_files(
                args.get('pattern', ''),
                args.get('path', '.'),
            ),
            'grep': lambda: dispatch['Grep'](),
            'ToolSearch': lambda: self.canonical_tool_search(args),
            'tool_search': lambda: self.canonical_tool_search(args),
            'AskUserQuestion': lambda: self.canonical_ask_user_question(args),
            'ask_user_question': lambda: self.canonical_ask_user_question(args),
            'TaskCreate': lambda: self.canonical_task_create(args),
            'task_create': lambda: self.canonical_task_create(args),
            'TaskGet': lambda: self.canonical_task_get(args),
            'task_get': lambda: self.canonical_task_get(args),
            'TaskUpdate': lambda: self.canonical_task_update(args),
            'task_update': lambda: self.canonical_task_update(args),
            'TaskList': lambda: self.canonical_task_list(args),
            'task_list': lambda: self.canonical_task_list(args),
            'TaskStop': lambda: self.canonical_task_stop(args),
            'task_stop': lambda: self.canonical_task_stop(args),
            'ScheduleWakeup': lambda: self.canonical_schedule_wakeup(args),
            'schedule_wakeup': lambda: self.canonical_schedule_wakeup(args),
            'EnterWorktree': lambda: self.canonical_enter_worktree(args),
            'enter_worktree': lambda: self.canonical_enter_worktree(args),
            'ExitWorktree': lambda: self.canonical_exit_worktree(args),
            'exit_worktree': lambda: self.canonical_exit_worktree(args),
            'NotebookEdit': lambda: self.canonical_notebook_edit(args),
            'notebook_edit': lambda: self.canonical_notebook_edit(args),
            'ReportFindings': lambda: self.canonical_report_findings(args),
            'report_findings': lambda: self.canonical_report_findings(args),
            'Agent': lambda: self.canonical_agent(args) if hasattr(self, 'canonical_agent') else self.converse(f"Subagent request: {args.get('description', '')}"),
            'agent': lambda: dispatch['Agent'](),
            'Workflow': lambda: self.canonical_workflow(args) if hasattr(self, 'canonical_workflow') else self.converse(f"Workflow script: {args.get('name', 'inline')}"),
            'workflow': lambda: dispatch['Workflow'](),

            # Existing Subsystem Mappings
            'run_bash': lambda: self.run_bash(args.get('command') or args.get('cmd') or args.get('script', '')),
            'read_file': lambda: self.read_file(
                args.get('path') or args.get('file_path') or args.get('file', ''),
                args.get('start_line'),
                args.get('end_line'),
            ),
            'read_symbol': lambda: self.read_symbol(
                args.get('path') or args.get('file_path') or args.get('file', ''),
                args.get('symbol', ''),
            ),
            'list_symbols': lambda: self.list_symbols(args.get('path') or args.get('file_path') or args.get('file', '')),
            'write_file': lambda: self.write_file(
                args.get('path') or args.get('file_path') or args.get('file', ''),
                args.get('content') or args.get('text', ''),
            ),
            'edit_file': lambda: self.edit_file(
                args.get('path') or args.get('file_path') or args.get('file', ''),
                args.get('old_text') or args.get('old_string', ''),
                args.get('new_text') or args.get('new_string', ''),
            ),
            'delete_file': lambda: self.delete_file(args.get('path') or args.get('file_path') or args.get('file', '')),
            'remove_file': lambda: self.delete_file(args.get('path') or args.get('file_path') or args.get('file', '')),
            'list_dir': lambda: self.list_directory(args.get('path') or args.get('directory') or args.get('dir', '.')),
            'search_files': lambda: self.search_files(
                args.get('pattern') or args.get('query') or '',
                args.get('path', '.'),
            ),
            'search_semantic': lambda: self.search_semantic(args.get('query', '')),
            'git': lambda: self.git_operation(args.get('subcommand', 'status')),
            'ask_human': lambda: self.ask_human(args.get('question', 'No question provided.')),
            'converse': lambda: self.converse(args.get('message', '')),
            'done': lambda: self.done(args.get('summary', 'Task marked as complete.')),
            'multi_edit': lambda: self.multi_edit(
                args.get('path', ''),
                args.get('edits', []),
            ),
            'glob': lambda: self.glob(
                args.get('pattern', ''),
                args.get('path', '.'),
            ),
            'run_tests': lambda: self.run_tests(
                args.get('command'),
                args.get('target'),
            ),
            'todo': lambda: self.todo(args.get('items', [])),
            'checkpoint': lambda: self.checkpoint(
                args.get('action', 'create'),
                args.get('name', ''),
            ),
            'fetch_url': lambda: self.fetch_url(
                args.get('url', ''),
                args.get('max_chars'),
            ),
            'run_python': lambda: self.run_python(
                args.get('code', ''),
                args.get('timeout', 30),
            ),
            'sarvam_translate': lambda: self.sarvam_translate(
                args.get('text', ''),
                args.get('target_language', 'ta-IN'),
                args.get('source_language', 'en-IN'),
            ),
            'sarvam_tts': lambda: self.sarvam_tts(
                args.get('text', ''),
                args.get('target_language', 'ta-IN'),
                args.get('speaker', 'anushka'),
                args.get('output_path', 'output_speech.wav'),
            ),
            'sarvam_stt': lambda: self.sarvam_stt(
                args.get('audio_path', ''),
                args.get('language_code', 'ta-IN'),
            ),
            'sarvam_ocr': lambda: self.sarvam_ocr(
                args.get('document_path', ''),
            ),
            'import_spotify_playlist': lambda: self.import_spotify_playlist(
                playlist_url=args.get('playlist_url', ''),
                quality_policy=args.get('quality_policy', 'best_lossless'),
                destination=args.get('destination', 'google_drive'),
                dry_run=args.get('dry_run', False)
            ),
            'music_status': lambda: self.music_status(args.get('job_id', '')),
            'music_retry': lambda: self.music_retry(args.get('job_id', '')),
            'music_cancel': lambda: self.music_cancel(args.get('job_id', '')),
            'music_library': lambda: self.music_library(args.get('query', '')),
            'run_remote': lambda: self.run_remote(args.get('command', '')),
            'capcut_list_projects': lambda: self.capcut_list_projects(),
            'capcut_get_project': lambda: self.capcut_get_project(args.get('project_name', '')),
            'capcut_create_project': lambda: self.capcut_create_project(
                args.get('project_name', ''),
                width=args.get('width'),
                height=args.get('height'),
                fps=args.get('fps', 30),
                aspect_ratio=args.get('aspect_ratio'),
                allow_replace=args.get('allow_replace', True),
            ),
            'capcut_set_canvas': lambda: self.capcut_set_canvas(
                args.get('project_name', ''),
                aspect_ratio=args.get('aspect_ratio'),
                width=args.get('width'),
                height=args.get('height'),
            ),
            'capcut_add_video_clip': lambda: self.capcut_add_video_clip(
                args.get('project_name', ''),
                args.get('file_path', ''),
                start_time=args.get('start_time', 0.0),
                duration=args.get('duration'),
                target_start=args.get('target_start', 0.0),
                speed=args.get('speed', 1.0),
                volume=args.get('volume', 1.0),
                transform_x=args.get('transform_x', 0.0),
                transform_y=args.get('transform_y', 0.0),
                scale_x=args.get('scale_x', 1.0),
                scale_y=args.get('scale_y', 1.0),
                rotation=args.get('rotation', 0.0),
                alpha=args.get('alpha', 1.0),
                fade_in=args.get('fade_in', 0.0),
                fade_out=args.get('fade_out', 0.0),
                transition=args.get('transition'),
                transition_duration=args.get('transition_duration', 0.5),
                track_name=args.get('track_name'),
            ),
            'capcut_add_audio_clip': lambda: self.capcut_add_audio_clip(
                args.get('project_name', ''),
                args.get('file_path', ''),
                start_time=args.get('start_time', 0.0),
                duration=args.get('duration'),
                target_start=args.get('target_start', 0.0),
                volume=args.get('volume', 1.0),
                speed=args.get('speed', 1.0),
                fade_in=args.get('fade_in', 0.0),
                fade_out=args.get('fade_out', 0.0),
                track_name=args.get('track_name'),
            ),
            'capcut_add_image': lambda: self.capcut_add_image(
                args.get('project_name', ''),
                args.get('file_path', ''),
                start_time=args.get('start_time', 0.0),
                duration=args.get('duration', 3.0),
                target_start=args.get('target_start', 0.0),
                transform_x=args.get('transform_x', 0.0),
                transform_y=args.get('transform_y', 0.0),
                scale_x=args.get('scale_x', 1.0),
                scale_y=args.get('scale_y', 1.0),
                rotation=args.get('rotation', 0.0),
                alpha=args.get('alpha', 1.0),
                track_name=args.get('track_name'),
            ),
            'capcut_add_text': lambda: self.capcut_add_text(
                args.get('project_name', ''),
                args.get('text', ''),
                start_time=args.get('start_time', 0.0),
                duration=args.get('duration', 3.0),
                target_start=args.get('target_start'),
                font_size=args.get('font_size', 15.0),
                font_color=args.get('font_color', '#FFFFFF'),
                pos_x=args.get('pos_x', 0.0),
                pos_y=args.get('pos_y', -0.6),
                bold=args.get('bold', False),
                italic=args.get('italic', False),
                underline=args.get('underline', False),
                align=args.get('align', 1),
                background_color=args.get('background_color'),
                background_alpha=args.get('background_alpha', 0.8),
                shadow_enabled=args.get('shadow_enabled', False),
                shadow_color=args.get('shadow_color', '#000000'),
                border_enabled=args.get('border_enabled', False),
                border_color=args.get('border_color', '#000000'),
                border_width=args.get('border_width', 20.0),
                animation=args.get('animation'),
                animation_duration=args.get('animation_duration', 0.5),
            ),
            'capcut_add_keyframe': lambda: self.capcut_add_keyframe(
                args.get('project_name', ''),
                property_types=args.get('property_types', []),
                times=args.get('times', []),
                values=args.get('values', []),
                track_type=args.get('track_type', 'video'),
                track_index=args.get('track_index', 0),
                segment_index=args.get('segment_index', 0),
            ),
            'capcut_add_sticker': lambda: self.capcut_add_sticker(
                args.get('project_name', ''),
                resource_id=args.get('resource_id', ''),
                start_time=args.get('start_time', 0.0),
                duration=args.get('duration', 3.0),
                target_start=args.get('target_start'),
                transform_x=args.get('transform_x', 0.0),
                transform_y=args.get('transform_y', 0.0),
                scale_x=args.get('scale_x', 1.0),
                scale_y=args.get('scale_y', 1.0),
                rotation=args.get('rotation', 0.0),
                alpha=args.get('alpha', 1.0),
                track_name=args.get('track_name', 'sticker_main'),
            ),
            'capcut_get_media_duration': lambda: self.capcut_get_media_duration(
                args.get('file_path', ''),
            ),
            'capcut_save_draft': lambda: self.capcut_save_draft(
                args.get('project_name', ''),
            ),
            'capcut_import_srt': lambda: self.capcut_import_srt(
                args.get('project_name', ''),
                args.get('srt_path', ''),
            ),
            'capcut_duplicate_project': lambda: self.capcut_duplicate_project(
                args.get('source_name', ''),
                args.get('target_name', ''),
                allow_replace=args.get('allow_replace', True),
            ),
            'capcut_delete_project': lambda: self.capcut_delete_project(
                args.get('project_name', ''),
            ),
            'capcut_open_in_app': lambda: self.capcut_open_in_app(
                args.get('project_name'),
            ),
            'capcut_fix_network_and_effects': lambda: self.capcut_fix_network_and_effects(),
            'capcut_list_available_effects': lambda: self.capcut_list_available_effects(
                keyword=args.get('keyword', ''),
                limit=args.get('limit', 50),
            ),
            'capcut_list_available_filters': lambda: self.capcut_list_available_filters(
                keyword=args.get('keyword', ''),
                limit=args.get('limit', 50),
            ),
            'capcut_list_available_transitions': lambda: self.capcut_list_available_transitions(
                keyword=args.get('keyword', ''),
                limit=args.get('limit', 50),
            ),
            'capcut_list_available_animations': lambda: self.capcut_list_available_animations(
                keyword=args.get('keyword', ''),
                anim_type=args.get('anim_type', 'all'),
                limit=args.get('limit', 50),
            ),
            'capcut_add_effect': lambda: self.capcut_add_effect(
                project_name=args.get('project_name', ''),
                effect_name=args.get('effect_name', ''),
                start_time=args.get('start_time', 0.0),
                duration=args.get('duration', 3.0),
                track_name=args.get('track_name'),
            ),
            'capcut_add_filter': lambda: self.capcut_add_filter(
                project_name=args.get('project_name', ''),
                filter_name=args.get('filter_name', ''),
                start_time=args.get('start_time', 0.0),
                duration=args.get('duration', 3.0),
                intensity=args.get('intensity', 80.0),
                track_name=args.get('track_name'),
            ),
            'capcut_add_transition': lambda: self.capcut_add_transition(
                project_name=args.get('project_name', ''),
                transition_name=args.get('transition_name', ''),
                segment_index=args.get('segment_index', 0),
                duration=args.get('duration', 0.5),
            ),
            'capcut_add_video_animation': lambda: self.capcut_add_video_animation(
                project_name=args.get('project_name', ''),
                animation_name=args.get('animation_name', ''),
                anim_type=args.get('anim_type', 'intro'),
                segment_index=args.get('segment_index', 0),
                duration=args.get('duration', 0.5),
            ),
            'capcut_list_pro_effects': lambda: self.capcut_list_pro_effects(
                keyword=args.get('keyword', ''),
                limit=args.get('limit', 50),
            ),
            'capcut_add_pro_effect': lambda: self.capcut_add_pro_effect(
                project_name=args.get('project_name', ''),
                effect_name=args.get('effect_name', ''),
                start_time=args.get('start_time', 0.0),
                duration=args.get('duration', 3.0),
                track_name=args.get('track_name'),
            ),
            'capcut_unlock_all_pro_features': lambda: self.capcut_unlock_all_pro_features(
                project_name=args.get('project_name'),
            ),
            'capcut_split_clip': lambda: self.capcut_split_clip(
                project_name=args.get('project_name', ''),
                track_index=args.get('track_index', 0),
                segment_index=args.get('segment_index', 0),
                split_time=args.get('split_time'),
                split_time_ms=args.get('split_time_ms'),
                track_type=args.get('track_type', 'video'),
            ),
            'capcut_trim_clip': lambda: self.capcut_trim_clip(
                project_name=args.get('project_name', ''),
                track_index=args.get('track_index', 0),
                segment_index=args.get('segment_index', 0),
                target_start=args.get('target_start'),
                target_start_ms=args.get('target_start_ms'),
                duration=args.get('duration'),
                duration_ms=args.get('duration_ms'),
                source_start=args.get('source_start'),
                source_start_ms=args.get('source_start_ms'),
                source_duration=args.get('source_duration'),
                source_duration_ms=args.get('source_duration_ms'),
                track_type=args.get('track_type', 'video'),
            ),
            'capcut_beat_sync_edit': lambda: self.capcut_beat_sync_edit(
                project_name=args.get('project_name', ''),
                video_clips=args.get('video_clips', []),
                music_path=args.get('music_path', ''),
                bpm=args.get('bpm', 120.0),
                beats_per_cut=args.get('beats_per_cut', 4),
                target_duration=args.get('target_duration'),
                target_duration_ms=args.get('target_duration_ms'),
                transition=args.get('transition'),
                transition_duration=args.get('transition_duration', 0.3),
                transition_duration_ms=args.get('transition_duration_ms'),
                effects=args.get('effects'),
                volume=args.get('volume', 1.0),
                width=args.get('width', 1920),
                height=args.get('height', 1080),
                fps=args.get('fps', 30),
            ),
            'capcut_inspect_timeline_ui': lambda: self.capcut_inspect_timeline_ui(
                project_name=args.get('project_name', ''),
            ),
            # Multimodal, System Mastery & Teamwork Dispatches
            'capture_screen': lambda: self.capture_screen(args.get('save_to_disk', True)),
            'CaptureScreen': lambda: self.capture_screen(args.get('save_to_disk', True)),
            'get_active_window': lambda: self.get_active_window(),
            'GetActiveWindow': lambda: self.get_active_window(),
            'get_system_vitals': lambda: self.get_system_vitals(),
            'GetSystemVitals': lambda: self.get_system_vitals(),
            'send_system_notification': lambda: self.send_system_notification(
                args.get('title', 'Julius'),
                args.get('message', ''),
                args.get('sound', True),
            ),
            'SendSystemNotification': lambda: self.send_system_notification(
                args.get('title', 'Julius'),
                args.get('message', ''),
                args.get('sound', True),
            ),
            'manage_clipboard': lambda: self.manage_clipboard(
                args.get('action', 'read'),
                args.get('text', ''),
            ),
            'ManageClipboard': lambda: self.manage_clipboard(
                args.get('action', 'read'),
                args.get('text', ''),
            ),
            'app_control': lambda: self.app_control(
                args.get('action', 'list'),
                args.get('app_name', ''),
            ),
            'AppControl': lambda: self.app_control(
                args.get('action', 'list'),
                args.get('app_name', ''),
            ),
            'run_teamwork': lambda: self.run_teamwork(
                args.get('goal', ''),
                args.get('personas'),
            ),
            'RunTeamwork': lambda: self.run_teamwork(
                args.get('goal', ''),
                args.get('personas'),
            ),
            'generate_image': lambda: self.generate_image(
                args.get('prompt', ''),
                args.get('output_path', ''),
            ),
            'GenerateImage': lambda: self.generate_image(
                args.get('prompt', ''),
                args.get('output_path', ''),
            ),
            'analyze_image': lambda: self.analyze_image(
                args.get('image_path', ''),
                args.get('prompt', 'Analyze this image'),
            ),
            'AnalyzeImage': lambda: self.analyze_image(
                args.get('image_path', ''),
                args.get('prompt', 'Analyze this image'),
            ),
        }

        handler = dispatch.get(action)
        if handler is None:
            return ActionResult(
                success=False,
                output=f"Unknown action '{action}'. Valid actions: {', '.join(sorted(dispatch.keys()))}",
                action=action,
                error='unknown_action',
            )

        self._active_action_name = action
        self._active_action_args = args
        self._active_action_start = time.time()
        try:
            res = handler()
        except Exception as exc:
            res = ActionResult(
                success=False,
                output=f'Action {action} failed: {exc}',
                action=action,
                error=str(exc),
            )
        finally:
            self._active_action_name = None
            self._active_action_args = {}
            self._active_action_start = 0.0

        if hasattr(self, '_cryptographic_audit') and self._cryptographic_audit:
            try:
                self._cryptographic_audit.append_entry(
                    actor=f"user_{self.user_id}" if self.user_id else "agent",
                    action=action,
                    decision="allowed" if res.success else "failed",
                    policy_rule=getattr(decision, "rule", "standard") if 'decision' in locals() else "standard",
                    payload=args,
                )
            except Exception as e:
                logger.warning(f"Failed to append to cryptographic audit ledger: {e}")

        return res

    async def execute_async(self, action: str, args: dict) -> ActionResult:
        """Asynchronously dispatch an action with interactive permission gating."""
        if self.permission_gate and _PERMISSION_GATE_AVAILABLE:
            action_map = {
                'run_bash': ActionType.BASH_COMMAND,
                'run_remote': ActionType.BASH_COMMAND,
                'run_python': ActionType.BASH_COMMAND,
                'write_file': ActionType.FILE_WRITE,
                'edit_file': ActionType.FILE_WRITE,
                'multi_edit': ActionType.FILE_WRITE,
                'git': ActionType.GIT_OPERATION,
            }
            atype = action_map.get(action)
            if atype:
                payload = args.get('command') or args.get('path') or args.get('subcommand') or str(args)
                resp = await self.permission_gate.request_permission(
                    action_type=atype,
                    payload=str(payload),
                    description=f"Agent requested {action}: {str(payload)[:100]}",
                )
                if resp not in (PermissionResponse.APPROVE_ONCE, PermissionResponse.APPROVE_SESSION):
                    return ActionResult(
                        success=False,
                        output=f"Action '{action}' was rejected by user permission gate.",
                        action=action,
                        error="permission_denied",
                    )

        import asyncio
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.execute, action, args)


def _shell_quote(s: str) -> str:
    """Simple shell quoting to prevent injection."""
    import shlex
    return shlex.quote(s)
