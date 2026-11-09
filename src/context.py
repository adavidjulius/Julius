"""
Context and token management engine for Julius (WS1.1 / WS1.2).
Includes prompt-cache TTL awareness, micro-compaction, and backward-compatible port context.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


@dataclass
class TokenUsageStats:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    total_tokens: int = 0


class AgentContextManager:
    """
    Manages token budgeting, prompt caching TTL alignment (5-minute window),
    and per-turn micro-compaction for LLM context windows.
    """

    DEFAULT_CACHE_TTL_SECONDS: float = 300.0  # 5 minutes prompt-cache TTL
    WARM_CACHE_CEILING_SECONDS: float = 270.0  # Safely within prompt-cache window
    LONG_HOLD_FLOOR_SECONDS: float = 1200.0  # Amortize cache miss over >=20 mins

    def __init__(
        self,
        context_window_limit: int = 128_000,
        compaction_threshold: float = 0.75,
        model_name: str = "nvidia/nemotron-3-ultra-550b-a55b",
    ) -> None:
        self.context_window_limit = context_window_limit
        self.compaction_threshold = compaction_threshold
        self.model_name = model_name
        self.usage = TokenUsageStats()
        self.last_api_timestamp: float = 0.0
        self.compaction_count: int = 0

    def record_usage(
        self,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_read_tokens: int = 0,
        cache_creation_tokens: int = 0,
        timestamp: Optional[float] = None,
    ) -> None:
        """Record token consumption from an API response and update cache timer."""
        self.usage.input_tokens += input_tokens
        self.usage.output_tokens += output_tokens
        self.usage.cache_read_tokens += cache_read_tokens
        self.usage.cache_creation_tokens += cache_creation_tokens
        self.usage.total_tokens += (input_tokens + output_tokens)
        self.last_api_timestamp = timestamp or time.time()

    def is_cache_warm(self, now: Optional[float] = None) -> bool:
        """Return True if prompt cache is still warm (< 270s elapsed)."""
        if self.last_api_timestamp <= 0.0:
            return False
        elapsed = (now or time.time()) - self.last_api_timestamp
        return elapsed < self.WARM_CACHE_CEILING_SECONDS

    def time_to_cache_expiry(self, now: Optional[float] = None) -> float:
        """Seconds remaining before prompt cache expires (clamped to 0)."""
        if self.last_api_timestamp <= 0.0:
            return 0.0
        elapsed = (now or time.time()) - self.last_api_timestamp
        return max(0.0, self.DEFAULT_CACHE_TTL_SECONDS - elapsed)

    def recommend_pacing_delay(self, requested_seconds: float) -> Tuple[float, str]:
        """
        Enforce prompt-cache TTL alignment:
        - Never sleep around ~300s (cache misses without amortization).
        - Under 5 mins: clamp to <= 270s to keep cache warm.
        - Over 5 mins: round up to >= 1200s to amortize the cache miss.
        """
        if requested_seconds <= self.WARM_CACHE_CEILING_SECONDS:
            return requested_seconds, "cache_warm"
        if requested_seconds < self.LONG_HOLD_FLOOR_SECONDS:
            # Dangerous middle zone: recommends either 270s or 1200s
            if requested_seconds < 600.0:
                return self.WARM_CACHE_CEILING_SECONDS, "clamped_to_keep_cache_warm"
            return self.LONG_HOLD_FLOOR_SECONDS, "promoted_to_amortize_cache_miss"
        return requested_seconds, "amortized_long_hold"

    def needs_compaction(self, current_tokens: Optional[int] = None) -> bool:
        """Check if active tokens exceed the compaction threshold."""
        tokens = current_tokens if current_tokens is not None else self.usage.input_tokens
        return tokens >= int(self.context_window_limit * self.compaction_threshold)

    @staticmethod
    def micro_compact_tool_output(
        output: str,
        max_chars: int = 8000,
        max_lines: int = 2000,
    ) -> str:
        """
        Micro-compact large tool outputs before injecting into conversation history:
        Preserves head (70%) and tail (30%) with a concise truncation notice.
        """
        if not output:
            return ""

        lines = output.splitlines()
        if len(lines) > max_lines:
            head_lines = int(max_lines * 0.7)
            tail_lines = max_lines - head_lines
            dropped = len(lines) - max_lines
            lines = (
                lines[:head_lines]
                + [f"\n... [{dropped} lines truncated for context budget] ...\n"]
                + lines[-tail_lines:]
            )
            output = "\n".join(lines)

        if len(output) > max_chars:
            head_chars = int(max_chars * 0.7)
            tail_chars = max_chars - head_chars
            dropped = len(output) - max_chars
            output = (
                output[:head_chars]
                + f"\n\n... [{dropped} characters truncated for context budget] ...\n\n"
                + output[-tail_chars:]
            )

        return output

    def get_context_gauge_data(self) -> Dict[str, Any]:
        """Data structure for statusline context token gauge."""
        pct = min(100.0, (self.usage.input_tokens / max(1, self.context_window_limit)) * 100)
        return {
            "current_tokens": self.usage.input_tokens,
            "max_tokens": self.context_window_limit,
            "percentage": pct,
            "is_warm": self.is_cache_warm(),
            "cache_read": self.usage.cache_read_tokens,
            "cache_created": self.usage.cache_creation_tokens,
        }


# ── Backward Compatibility: PortContext ──────────────────────────────────────


@dataclass(frozen=True)
class PortContext:
    source_root: Path
    tests_root: Path
    assets_root: Path
    archive_root: Path
    python_file_count: int
    test_file_count: int
    asset_file_count: int
    archive_available: bool


def build_port_context(base: Path | None = None) -> PortContext:
    root = base or Path(__file__).resolve().parent.parent
    source_root = root / 'src'
    tests_root = root / 'tests'
    assets_root = root / 'assets'
    archive_root = root / 'archive' / 'julius_ts_snapshot' / 'src'
    return PortContext(
        source_root=source_root,
        tests_root=tests_root,
        assets_root=assets_root,
        archive_root=archive_root,
        python_file_count=sum(1 for path in source_root.rglob('*.py') if path.is_file()),
        test_file_count=sum(1 for path in tests_root.rglob('*.py') if path.is_file()),
        asset_file_count=sum(1 for path in assets_root.rglob('*') if path.is_file()),
        archive_available=archive_root.exists(),
    )


def render_context(context: PortContext) -> str:
    return '\n'.join([
        f'Source root: {context.source_root}',
        f'Test root: {context.tests_root}',
        f'Assets root: {context.assets_root}',
        f'Archive root: {context.archive_root}',
        f'Python files: {context.python_file_count}',
        f'Test files: {context.test_file_count}',
        f'Assets: {context.asset_file_count}',
        f'Archive available: {context.archive_available}',
    ])
