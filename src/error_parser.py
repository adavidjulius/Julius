"""
Stderr error parser for the healing agent loop.

Parses raw stderr output from failing bash commands to extract structured
error context: the offending file, line number, and error message. Supports
Python tracebacks, Node.js/JavaScript stack traces, and common compiler
errors (TypeScript tsc, gcc, rustc).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class ErrorContext:
    """Structured error information extracted from a stderr stream."""
    file: Optional[str]        # Path to the offending file (may be None)
    line: Optional[int]        # 1-indexed line number (may be None)
    column: Optional[int]      # Column number if available
    message: str               # Human-readable error message
    error_type: str            # 'python' | 'node' | 'typescript' | 'gcc' | 'generic'
    raw_stderr: str            # The original stderr text


# ── Pattern library ──────────────────────────────────────────────────────────

# Python traceback:
#   File "/path/to/file.py", line 42, in <function>
_PY_TRACEBACK = re.compile(
    r'File "(?P<file>[^"]+)", line (?P<line>\d+)',
    re.MULTILINE,
)

# Python exception type + message on the last line
_PY_EXCEPTION = re.compile(
    r'^(?P<exc_type>\w+(?:\.\w+)*Error|\w+Exception|SyntaxError|TypeError|ValueError|ImportError)[:\s](?P<msg>.+)$',
    re.MULTILINE,
)

# Node.js / JavaScript stack trace:
#   at Object.<anonymous> (/path/to/file.js:42:10)
_NODE_STACK = re.compile(
    r'at .+\((?P<file>[^)]+):(?P<line>\d+):(?P<col>\d+)\)',
    re.MULTILINE,
)

# TypeScript compiler (tsc):
#   src/file.ts(42,10): error TS2345: Argument of type ...
_TSC_ERROR = re.compile(
    r'^(?P<file>[^\s(]+)\((?P<line>\d+),(?P<col>\d+)\): error (?P<code>TS\d+): (?P<msg>.+)$',
    re.MULTILINE,
)

# GCC / Clang:
#   src/file.c:42:10: error: 'x' undeclared
_GCC_ERROR = re.compile(
    r'^(?P<file>[^\s:]+):(?P<line>\d+):(?P<col>\d+): (?:error|fatal error): (?P<msg>.+)$',
    re.MULTILINE,
)

# Rust (rustc):
#   --> src/main.rs:42:10
_RUST_ERROR = re.compile(
    r'-->\s+(?P<file>[^\s:]+):(?P<line>\d+):(?P<col>\d+)',
    re.MULTILINE,
)

# Generic "error" line (last resort)
_GENERIC_ERROR = re.compile(
    r'(?:error|Error|ERROR)[:\s]+(?P<msg>.+)',
    re.MULTILINE,
)


# ── Public API ────────────────────────────────────────────────────────────────

def parse_error(stderr: str) -> ErrorContext:
    """
    Parse a stderr string and return structured error context.

    Tries each pattern in priority order. Falls back to a generic
    ``ErrorContext`` with just the raw message if nothing matches.

    Args:
        stderr: The raw stderr text from a failed command.

    Returns:
        ErrorContext with the best available structured error info.
    """
    stderr = stderr.strip()

    # 1 — Python traceback (most specific: last File reference wins)
    py_matches = list(_PY_TRACEBACK.finditer(stderr))
    if py_matches:
        last = py_matches[-1]
        # Try to extract the exception message
        exc_match = _PY_EXCEPTION.search(stderr)
        message = f'{exc_match.group("exc_type")}: {exc_match.group("msg")}' if exc_match else _last_line(stderr)
        return ErrorContext(
            file=last.group('file'),
            line=int(last.group('line')),
            column=None,
            message=message,
            error_type='python',
            raw_stderr=stderr,
        )

    # 2 — TypeScript compiler
    tsc_match = _TSC_ERROR.search(stderr)
    if tsc_match:
        return ErrorContext(
            file=tsc_match.group('file'),
            line=int(tsc_match.group('line')),
            column=int(tsc_match.group('col')),
            message=f"{tsc_match.group('code')}: {tsc_match.group('msg')}",
            error_type='typescript',
            raw_stderr=stderr,
        )

    # 3 — GCC/Clang
    gcc_match = _GCC_ERROR.search(stderr)
    if gcc_match:
        return ErrorContext(
            file=gcc_match.group('file'),
            line=int(gcc_match.group('line')),
            column=int(gcc_match.group('col')),
            message=gcc_match.group('msg'),
            error_type='gcc',
            raw_stderr=stderr,
        )

    # 4 — Rust
    rust_match = _RUST_ERROR.search(stderr)
    if rust_match:
        return ErrorContext(
            file=rust_match.group('file'),
            line=int(rust_match.group('line')),
            column=int(rust_match.group('col')),
            message=_last_line(stderr),
            error_type='rust',
            raw_stderr=stderr,
        )

    # 5 — Node.js stack trace
    node_matches = list(_NODE_STACK.finditer(stderr))
    if node_matches:
        first = node_matches[0]
        return ErrorContext(
            file=first.group('file'),
            line=int(first.group('line')),
            column=int(first.group('col')),
            message=_first_line(stderr),
            error_type='node',
            raw_stderr=stderr,
        )

    # 6 — Generic fallback
    generic_match = _GENERIC_ERROR.search(stderr)
    message = generic_match.group('msg').strip() if generic_match else _first_line(stderr) or stderr[:200]
    return ErrorContext(
        file=None,
        line=None,
        column=None,
        message=message,
        error_type='generic',
        raw_stderr=stderr,
    )


def is_recoverable(error: ErrorContext) -> bool:
    """
    Return True if the error looks like something that could be auto-fixed.

    Non-recoverable errors (e.g. network failures, missing commands) are
    better handled by asking the human instead.
    """
    unrecoverable_patterns = [
        'command not found',
        'No such file or directory',
        'Permission denied',
        'Connection refused',
        'No module named',
        'cannot connect',
        'Network is unreachable',
    ]
    lower = error.raw_stderr.lower()
    for pat in unrecoverable_patterns:
        if pat.lower() in lower:
            return False
    # Only auto-fix if we have a file reference
    return error.file is not None


# ── Helpers ──────────────────────────────────────────────────────────────────

def _first_line(text: str) -> str:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    return lines[0] if lines else ''


def _last_line(text: str) -> str:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    return lines[-1] if lines else ''
