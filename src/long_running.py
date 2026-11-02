"""
long_running.py — Intelligent long-running command management for the Julius agent.

Implements Stages 1 and 2 of the failure-diagnosis plan:
  Stage 1: Classify commands likely to be long-running (large downloads,
           builds, ML training) and launch them in the background instead
           of using a single blocking call with a short timeout.
  Stage 2: Poll background jobs for real progress (log growth / PID liveness)
           instead of treating silence as failure.

A job is only reported as STALLED when there has been no new output AND no
live process activity for `stall_window` seconds — not just because a fixed
timeout elapsed. Completed jobs are reported as COMPLETED (exit 0) or FAILED
(exit ≠ 0). Nothing is ever suppressed: all results are reported honestly.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stage 1 — Command Classifier
# ---------------------------------------------------------------------------

# Patterns that strongly suggest a long-running, network-bound or
# compute-heavy operation. Each entry is a compiled regex applied to the
# full command string (case-insensitive).
_LONG_RUNNING_PATTERNS: list[re.Pattern] = [p for p in [
    # Docker operations
    re.compile(r'\bdocker\s+build\b', re.IGNORECASE),
    re.compile(r'\bdocker\s+pull\b', re.IGNORECASE),
    re.compile(r'\bdocker\s+run\b', re.IGNORECASE),
    re.compile(r'\bdocker-compose\s+(up|build|pull)\b', re.IGNORECASE),
    # Python package management (large packages)
    re.compile(r'\bpip\s+install\b', re.IGNORECASE),
    re.compile(r'\bpip3\s+install\b', re.IGNORECASE),
    re.compile(r'\bconda\s+install\b', re.IGNORECASE),
    re.compile(r'\bpoetry\s+install\b', re.IGNORECASE),
    re.compile(r'\buv\s+pip\s+install\b', re.IGNORECASE),
    # Node/JS package management
    re.compile(r'\bnpm\s+install\b', re.IGNORECASE),
    re.compile(r'\byarn\s+(install|add)\b', re.IGNORECASE),
    re.compile(r'\bpnpm\s+install\b', re.IGNORECASE),
    re.compile(r'\bbun\s+install\b', re.IGNORECASE),
    # System package management
    re.compile(r'\bapt(-get)?\s+(install|update|upgrade)\b', re.IGNORECASE),
    re.compile(r'\bbrew\s+(install|upgrade)\b', re.IGNORECASE),
    # Build systems
    re.compile(r'\bcargo\s+build\b', re.IGNORECASE),
    re.compile(r'\bcargo\s+test\b', re.IGNORECASE),
    re.compile(r'\bmake\b', re.IGNORECASE),
    re.compile(r'\bcmake\b', re.IGNORECASE),
    re.compile(r'\bbazel\s+build\b', re.IGNORECASE),
    re.compile(r'\bgradle\b', re.IGNORECASE),
    re.compile(r'\bmvn\s+(install|package|compile)\b', re.IGNORECASE),
    # Large ML frameworks by name
    re.compile(r'\btorch\b', re.IGNORECASE),
    re.compile(r'\btensorflow\b', re.IGNORECASE),
    re.compile(r'\bjax\b', re.IGNORECASE),
    re.compile(r'\bflax\b', re.IGNORECASE),
    re.compile(r'\btransformers\b', re.IGNORECASE),
    re.compile(r'\bdiffusers\b', re.IGNORECASE),
    re.compile(r'\bxformers\b', re.IGNORECASE),
    re.compile(r'\bcuda\b', re.IGNORECASE),
    # Generic download / model pulling
    re.compile(r'\bwget\b', re.IGNORECASE),
    re.compile(r'\bcurl\b.*-[oO]\b', re.IGNORECASE),   # curl downloading a file
    re.compile(r'\bgit\s+clone\b', re.IGNORECASE),
    re.compile(r'\bgit\s+pull\b', re.IGNORECASE),
    # ML training keywords
    re.compile(r'\btrain(ing|er)?\b', re.IGNORECASE),
    re.compile(r'finetune|fine[_-]?tun(e|ing)', re.IGNORECASE),
    re.compile(r'pretrain|pre[_-]?trai?n', re.IGNORECASE),
    re.compile(r'\bepoch\b', re.IGNORECASE),
    # Playwright / browser setup
    re.compile(r'\bplaywright\s+install\b', re.IGNORECASE),
] if p]


def classify_command(command: str) -> bool:
    """Return True if *command* is likely to be a long-running operation.

    Uses lightweight pattern matching — no execution, no heuristics.
    False negatives are safe (they fall back to the short blocking path).
    False positives are also safe (background polling is strictly more
    capable than blocking with a short timeout).
    """
    for pattern in _LONG_RUNNING_PATTERNS:
        if pattern.search(command):
            logger.debug(f'classify_command: LONG_RUNNING matched {pattern.pattern!r} in {command[:60]!r}')
            return True
    return False


# ---------------------------------------------------------------------------
# Stage 1 — Background Job Launcher
# ---------------------------------------------------------------------------

@dataclass
class BackgroundJob:
    """Represents a command launched in the background."""
    pid: int
    command: str
    log_path: str
    started_at: float = field(default_factory=time.time)
    workspace: str = ''
    # True if this command is network-bound (triggers Stage 3 network probe)
    is_network_bound: bool = False
    # The underlying Popen object — used for reliable exit code detection
    _proc: object = field(default=None, compare=False, repr=False)


_NETWORK_BOUND_PATTERNS: list[re.Pattern] = [
    re.compile(r'\bpip\s+install\b', re.IGNORECASE),
    re.compile(r'\bpip3\s+install\b', re.IGNORECASE),
    re.compile(r'\bdocker\s+(build|pull)\b', re.IGNORECASE),
    re.compile(r'\bapt(-get)?\s+(install|update|upgrade)\b', re.IGNORECASE),
    re.compile(r'\bnpm\s+install\b', re.IGNORECASE),
    re.compile(r'\byarn\s+(install|add)\b', re.IGNORECASE),
    re.compile(r'\bgit\s+(clone|pull)\b', re.IGNORECASE),
    re.compile(r'\bcurl\b.*-[oO]\b', re.IGNORECASE),
    re.compile(r'\bwget\b', re.IGNORECASE),
    re.compile(r'\bconda\s+install\b', re.IGNORECASE),
]


def _is_network_bound(command: str) -> bool:
    return any(p.search(command) for p in _NETWORK_BOUND_PATTERNS)


def launch_background(
    command: str,
    workspace: str = '.',
    log_path: Optional[str] = None,
) -> BackgroundJob:
    """Launch *command* in the background, capturing stdout+stderr to a log file.

    Returns a BackgroundJob with the PID and log file path.
    Does NOT block — the caller must poll via poll_job().
    """
    if log_path is None:
        fd, log_path = tempfile.mkstemp(prefix='julius_bg_', suffix='.log')
        os.close(fd)

    workspace_abs = str(Path(workspace).resolve())

    # Use subprocess so we get a real PID we can poll
    with open(log_path, 'w') as log_fh:
        proc = subprocess.Popen(
            command,
            shell=True,
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            cwd=workspace_abs,
            env={**os.environ, 'PYTHONUNBUFFERED': '1', 'TERM': 'dumb'},
        )

    job = BackgroundJob(
        pid=proc.pid,
        command=command,
        log_path=log_path,
        started_at=time.time(),
        workspace=workspace_abs,
        is_network_bound=_is_network_bound(command),
        _proc=proc,
    )
    logger.info(
        f'launch_background: PID={proc.pid} log={log_path!r} cmd={command[:80]!r}'
    )
    return job


# ---------------------------------------------------------------------------
# Stage 2 — Poll Job for Real Progress
# ---------------------------------------------------------------------------

class PollStatus(str, Enum):
    IN_PROGRESS = 'IN_PROGRESS'
    STALLED     = 'STALLED'
    COMPLETED   = 'COMPLETED'
    FAILED      = 'FAILED'


@dataclass
class PollResult:
    status: PollStatus
    elapsed_sec: float
    log_bytes: int
    exit_code: Optional[int]
    message: str          # human-readable, evidence-backed
    network_summary: Optional[str] = None


def _pid_alive(pid: int) -> bool:
    """Return True if the process with *pid* is still running."""
    try:
        os.kill(pid, 0)   # signal 0 = existence check, no actual signal
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but we don't own it (shouldn't happen for our child)
        return True


def _get_exit_code(pid: int) -> Optional[int]:
    """Attempt a non-blocking waitpid to get the exit code. Returns None if still running."""
    try:
        result_pid, status = os.waitpid(pid, os.WNOHANG)
        if result_pid == 0:
            return None  # still running
        if os.WIFEXITED(status):
            return os.WEXITSTATUS(status)
        if os.WIFSIGNALED(status):
            return -(os.WTERMSIG(status))
        return None
    except ChildProcessError:
        # Process already reaped or not our child — check if it still exists
        if _pid_alive(pid):
            return None
        # We can't get the exit code — assume success if log has output
        return None
    except Exception:
        return None


def poll_job(
    job: BackgroundJob,
    check_interval: float = 15.0,
    stall_window: float = 300.0,
    network_probe_after: float = 120.0,
    progress_callback=None,
) -> PollResult:
    """Poll *job* until it completes, stalls, or fails.

    Checks every *check_interval* seconds:
    - If log grew since last check → IN_PROGRESS, reset stall timer
    - If proc.poll() returns exit code → COMPLETED (0) or FAILED (non-zero)
    - If no new log bytes AND no exit for > *stall_window* → STALLED

    When *job.is_network_bound* and elapsed > *network_probe_after*, runs
    a one-time Stage 3 network measurement and includes it in progress output.

    *progress_callback(message: str)* is called with each status update, if provided.
    """
    log_path = Path(job.log_path)
    last_log_size = 0
    last_growth_time = job.started_at
    network_probed = False
    network_summary: Optional[str] = None
    proc = getattr(job, '_proc', None)  # Popen object if available

    def _emit(msg: str) -> None:
        logger.info(msg)
        print(f'   {msg}', flush=True)
        if progress_callback:
            progress_callback(msg)

    while True:
        now = time.time()
        elapsed = now - job.started_at
        elapsed_str = _fmt_elapsed(elapsed)

        # Read current log size
        try:
            current_log_size = log_path.stat().st_size
        except FileNotFoundError:
            current_log_size = 0

        log_grew = current_log_size > last_log_size
        if log_grew:
            last_growth_time = now
            last_log_size = current_log_size

        # --- Check if process has exited ---
        # Primary: use proc.poll() which correctly handles the shell=True wrapper process.
        # proc.poll() returns None when running and the exit code when done.
        # Fallback: _pid_alive for jobs without a stored Popen reference.
        if proc is not None:
            exit_code = proc.poll()   # None if still running, int if exited
            process_running = (exit_code is None)
        else:
            process_running = _pid_alive(job.pid)
            exit_code = None

        # --- Stage 3: Network probe (one-time, when applicable) ---
        if (
            job.is_network_bound
            and not network_probed
            and elapsed > network_probe_after
        ):
            network_probed = True
            try:
                from .network_probe import measure_network
                measurement = measure_network()
                network_summary = measurement.summary
                _emit(
                    f'🌐 Network check (triggered by slow download): {network_summary}'
                )
            except Exception as exc:
                logger.warning(f'poll_job: network probe failed: {exc}')
                network_summary = f'network probe unavailable: {exc}'

        # --- Determine status ---
        if not process_running:
            # Process has exited — we have exit_code from proc.poll()
            # For the fallback path (no proc), use log heuristic
            if exit_code is None:
                log_tail = _read_log_tail(log_path, n_bytes=2000)
                if _log_indicates_failure(log_tail):
                    exit_code = 1
                else:
                    exit_code = 0

            log_tail = _read_log_tail(log_path, n_bytes=2000)
            elapsed_final = time.time() - job.started_at
            elapsed_str_final = _fmt_elapsed(elapsed_final)

            if exit_code == 0:
                msg = (
                    f'✅ COMPLETED — {job.command[:60]!r} — '
                    f'elapsed {elapsed_str_final} — exit 0'
                )
                _emit(msg)
                return PollResult(
                    status=PollStatus.COMPLETED,
                    elapsed_sec=elapsed_final,
                    log_bytes=current_log_size,
                    exit_code=0,
                    message=msg,
                    network_summary=network_summary,
                )
            else:
                # Real failure — report honestly with log tail
                msg = (
                    f'❌ FAILED — {job.command[:60]!r} — '
                    f'exit {exit_code} — elapsed {elapsed_str_final}\n'
                    f'Last log output:\n{log_tail}'
                )
                _emit(msg)
                return PollResult(
                    status=PollStatus.FAILED,
                    elapsed_sec=elapsed_final,
                    log_bytes=current_log_size,
                    exit_code=exit_code,
                    message=msg,
                    network_summary=network_summary,
                )
        else:
            # Process is still running
            silence_duration = now - last_growth_time
            if silence_duration > stall_window:
                # No new output AND running for too long without progress → STALLED
                msg = (
                    f'⚠️  STALLED — {job.command[:60]!r} — no new output for '
                    f'{silence_duration:.0f}s (stall_window={stall_window}s) — '
                    f'PID {job.pid} still running but appears hung'
                )
                _emit(msg)
                return PollResult(
                    status=PollStatus.STALLED,
                    elapsed_sec=elapsed,
                    log_bytes=current_log_size,
                    exit_code=None,
                    message=msg,
                    network_summary=network_summary,
                )
            else:
                # Making progress (or hasn't hit stall window yet)
                net_note = f' — {network_summary}' if network_summary else ''
                msg = (
                    f'⏳ In progress: {job.command[:50]!r} — '
                    f'elapsed {elapsed_str} — log: {current_log_size:,} bytes — '
                    f'PID {job.pid} alive{net_note}'
                )
                _emit(msg)
                time.sleep(check_interval)
                continue


def _fmt_elapsed(seconds: float) -> str:
    """Format elapsed seconds as 'Xm Ys' or 'Xs'."""
    if seconds >= 60:
        m = int(seconds // 60)
        s = int(seconds % 60)
        return f'{m}m {s}s'
    return f'{seconds:.0f}s'


def _read_log_tail(log_path: Path, n_bytes: int = 2000) -> str:
    """Read the last n_bytes from the log file."""
    try:
        size = log_path.stat().st_size
        with open(log_path, 'r', errors='replace') as f:
            if size > n_bytes:
                f.seek(size - n_bytes)
            return f.read()
    except Exception:
        return '(log unreadable)'


_FAILURE_KEYWORDS = [
    'error:', 'error occurred', 'failed', 'traceback', 'exception',
    'exitcode', 'exit code', 'permission denied', 'no such file',
    'command not found', 'killed', 'aborted',
]


def _log_indicates_failure(log_tail: str) -> bool:
    """Heuristic: check if log tail contains common failure indicators."""
    lower = log_tail.lower()
    return any(kw in lower for kw in _FAILURE_KEYWORDS)


# ---------------------------------------------------------------------------
# Convenience: run_long_running_blocking
# ---------------------------------------------------------------------------

def run_long_running_blocking(
    command: str,
    workspace: str = '.',
    check_interval: float = 15.0,
    stall_window: float = 300.0,
    network_probe_after: float = 120.0,
    progress_callback=None,
) -> tuple[bool, str]:
    """Launch *command* in background and poll to completion.

    Returns (success: bool, output: str) matching the StatefulShell API.
    - success=True on exit 0 or COMPLETED
    - success=False on FAILED or STALLED (with diagnosis in output)
    - Never times out due to a fixed deadline — only fails on real errors or stalls
    """
    job = launch_background(command, workspace=workspace)
    result = poll_job(
        job,
        check_interval=check_interval,
        stall_window=stall_window,
        network_probe_after=network_probe_after,
        progress_callback=progress_callback,
    )

    # Read full log for output
    log_content = _read_log_tail(Path(job.log_path), n_bytes=8000)

    if result.status == PollStatus.COMPLETED:
        return True, log_content
    elif result.status == PollStatus.FAILED:
        return False, f'{result.message}\n\n--- Log ---\n{log_content}'
    elif result.status == PollStatus.STALLED:
        net_note = f'\nNetwork check: {result.network_summary}' if result.network_summary else ''
        return False, (
            f'Command stalled (no output for {stall_window}s): {command}\n'
            f'{result.message}{net_note}\n\n--- Partial log ---\n{log_content}'
        )
    else:
        # Should not reach here, but handle defensively
        return False, f'Unexpected poll status {result.status}: {result.message}'
