"""
Rate limiter and intelligent request spacing for API providers.

Implements token bucket / sliding window rate limiting, minimum spacing intervals
between consecutive requests, and adaptive backoff for rate-limited (HTTP 429) APIs.
Specially tuned for NVIDIA Build NIM Free API (40 RPM limit).
"""

from __future__ import annotations

import asyncio
from collections import deque
import logging
import os
import random
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class NvidiaRateLimiter:
    """
    Intelligent rate limiter and request pacer for NVIDIA Build NIM API.
    
    NVIDIA Build free tier provides ~40 RPM (Requests Per Minute).
    To guarantee zero 429 throttling and zero crashes under continuous agent usage:
      1. Sliding 60-second window enforcing a maximum cap (default 36-40 RPM).
      2. Minimum inter-request spacing ("easy space" of 1.5s - 2.0s) to prevent burst clusters.
      3. Async mutex lock to prevent concurrent requests from colliding.
      4. Exponential backoff + jitter on HTTP 429 with Retry-After header parsing.
      5. Header-aware adaptive pacing if rate limit headers are received.
    """

    def __init__(
        self,
        max_rpm: int = 40,
        min_spacing: float = 1.5,
        safety_buffer_rpm: int = 36,
    ) -> None:
        self.max_rpm = int(os.getenv("NVIDIA_RPM", str(max_rpm)))
        self.min_spacing = float(os.getenv("NVIDIA_MIN_SPACING", str(min_spacing)))
        # Target operational threshold slightly below hard cap to absorb timing fluctuations
        self.safety_cap = min(int(os.getenv("NVIDIA_SAFETY_RPM", str(safety_buffer_rpm))), self.max_rpm)

        self._lock = asyncio.Lock()
        self._timestamps: deque[float] = deque()
        self._last_request_time: float = 0.0
        self._cooldown_until: float = 0.0
        self._total_requests: int = 0
        self._total_throttles: int = 0
        self._total_429_retries: int = 0

    async def acquire(self) -> float:
        """
        Pace the upcoming request. Blocks asynchronously until it is safe to send.
        Returns the delay (in seconds) that was waited.
        """
        total_delay = 0.0

        async with self._lock:
            now = time.time()

            # 1. Check if we are in a 429 or explicit cooldown period
            if now < self._cooldown_until:
                cooldown_wait = self._cooldown_until - now
                logger.info(
                    f"⏳ [NVIDIA NIM RateLimiter] In cool-off period. Giving space: waiting {cooldown_wait:.2f}s..."
                )
                await asyncio.sleep(cooldown_wait)
                total_delay += cooldown_wait
                now = time.time()

            # 2. Enforce minimum inter-request spacing ("easy space giving")
            time_since_last = now - self._last_request_time
            if time_since_last < self.min_spacing:
                spacing_wait = self.min_spacing - time_since_last
                logger.debug(
                    f"⏱️ [NVIDIA NIM RateLimiter] Spacing requests ({time_since_last:.2f}s elapsed < {self.min_spacing}s min). Waiting {spacing_wait:.2f}s..."
                )
                await asyncio.sleep(spacing_wait)
                total_delay += spacing_wait
                now = time.time()

            # 3. Clean up sliding window (older than 60 seconds)
            cutoff = now - 60.0
            while self._timestamps and self._timestamps[0] <= cutoff:
                self._timestamps.popleft()

            # 4. Check if rolling 60-second window has reached capacity
            if len(self._timestamps) >= self.safety_cap:
                self._total_throttles += 1
                oldest = self._timestamps[0]
                window_wait = max(0.1, (oldest + 60.0) - now + 0.15)
                logger.warning(
                    f"🛑 [NVIDIA NIM RateLimiter] Window near limit ({len(self._timestamps)}/{self.max_rpm} RPM). "
                    f"Giving space: sleeping {window_wait:.2f}s to respect 40 RPM quota..."
                )
                await asyncio.sleep(window_wait)
                total_delay += window_wait
                now = time.time()

                # Re-clean after sleep
                cutoff = now - 60.0
                while self._timestamps and self._timestamps[0] <= cutoff:
                    self._timestamps.popleft()

            # 5. Record this execution timestamp
            now = time.time()
            self._timestamps.append(now)
            self._last_request_time = now
            self._total_requests += 1

        return total_delay

    def record_response(self, status: int, headers: Optional[Dict[str, Any]] = None) -> None:
        """Inspect response status and headers for adaptive rate control."""
        if headers is None:
            return

        # Check for standard rate-limit remaining headers
        for k, v in headers.items():
            k_lower = k.lower()
            if "ratelimit-remaining" in k_lower or "rate-limit-remaining" in k_lower:
                try:
                    remaining = int(v)
                    if remaining <= 2:
                        # Extra caution: if server reports nearly 0 remaining, pace next request by 2.5s
                        self._last_request_time = time.time() + 1.0
                        logger.warning(f"⚠️ [NVIDIA NIM RateLimiter] Server reports {remaining} requests remaining. Increasing spacing.")
                except (ValueError, TypeError):
                    pass

    async def handle_429(self, headers: Optional[Dict[str, Any]] = None, attempt: int = 1) -> float:
        """
        Handle HTTP 429 Too Many Requests response.
        Calculates required backoff duration, updates cool-off, and sleeps.
        Returns the duration waited.
        """
        async with self._lock:
            self._total_429_retries += 1
            now = time.time()

            retry_after_sec: Optional[float] = None
            if headers:
                for k, v in headers.items():
                    if k.lower() == "retry-after":
                        try:
                            retry_after_sec = float(v)
                            break
                        except (ValueError, TypeError):
                            pass

            if retry_after_sec is not None and retry_after_sec > 0:
                wait_time = retry_after_sec + 0.5
                logger.warning(
                    f"⚠️ [NVIDIA NIM RateLimiter] HTTP 429 received! Retry-After specified: {retry_after_sec}s. "
                    f"Backing off for {wait_time:.2f}s (attempt {attempt})..."
                )
            else:
                # Exponential backoff with random jitter: 2s, 4s, 8s, 16s...
                jitter = random.uniform(0.2, 0.8)
                base = 2.0
                wait_time = (base ** attempt) + jitter
                logger.warning(
                    f"⚠️ [NVIDIA NIM RateLimiter] HTTP 429 received! Backing off for {wait_time:.2f}s "
                    f"with exponential spacing (attempt {attempt})..."
                )

            self._cooldown_until = now + wait_time
            # Evict timestamps to reflect rate limiter state
            self._timestamps.clear()

        await asyncio.sleep(wait_time)
        return wait_time

    def get_stats(self) -> Dict[str, Any]:
        """Return rate limiter operational metrics."""
        now = time.time()
        active_in_window = sum(1 for t in self._timestamps if (now - t) < 60.0)
        return {
            "current_rpm": active_in_window,
            "max_rpm": self.max_rpm,
            "safety_cap": self.safety_cap,
            "min_spacing_seconds": self.min_spacing,
            "total_requests": self._total_requests,
            "total_throttles": self._total_throttles,
            "total_429_retries": self._total_429_retries,
            "seconds_since_last_call": round(now - self._last_request_time, 2) if self._last_request_time else None,
        }


# Global shared instance for the process
_NVIDIA_LIMITER: Optional[NvidiaRateLimiter] = None


def get_nvidia_rate_limiter() -> NvidiaRateLimiter:
    """Get or create the singleton NvidiaRateLimiter instance."""
    global _NVIDIA_LIMITER
    if _NVIDIA_LIMITER is None:
        _NVIDIA_LIMITER = NvidiaRateLimiter()
    return _NVIDIA_LIMITER

