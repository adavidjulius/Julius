"""
network_probe.py — Stage 3: Real network condition measurement.

Provides a single function, measure_network(), that runs two cheap real
checks (ping + curl to known endpoints) and returns concrete, numeric
evidence about current network quality.

Every claim produced by this module is backed by an actual measurement.
No assertions are made without evidence. If a measurement fails to run,
the error is reported explicitly rather than substituting a generic
"network seems fine" statement.
"""

from __future__ import annotations

import logging
import re
import subprocess
import time
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# Thresholds for "degraded" classification
_DEGRADED_PING_MS     = 500.0   # avg RTT above this → degraded
_DEGRADED_LOSS_PCT    = 10.0    # packet loss % above this → degraded
_DEGRADED_SPEED_BPS   = 50_000  # download speed below 50 KB/s → degraded

# Probe targets — chosen for reliability and minimal overhead
_PING_HOST   = '8.8.8.8'                           # Google DNS — fast, reliable
_SPEED_URL   = 'https://pypi.org/simple/torch/'    # Small HTML page, tests PyPI reachability
_CURL_TIMEOUT = 10  # seconds max for the speed probe


@dataclass
class NetworkMeasurement:
    """Result of a real network probe. All numeric fields are None if the
    corresponding check could not run (e.g. no ping binary)."""

    ping_ms:          Optional[float]   # avg round-trip time in ms
    packet_loss_pct:  Optional[float]   # packet loss 0–100
    download_bps:     Optional[float]   # bytes/second to _SPEED_URL
    is_degraded:      bool              # True if any threshold is exceeded
    summary:          str               # evidence-backed human-readable string
    ping_error:       Optional[str] = None   # error message if ping failed
    speed_error:      Optional[str] = None   # error message if speed probe failed


def measure_network() -> NetworkMeasurement:
    """Run a real network probe and return concrete measurements.

    Checks:
    1. ping -c 3 to 8.8.8.8 → avg RTT and packet loss
    2. curl HEAD to PyPI → download speed in bytes/sec

    Returns a NetworkMeasurement with numeric evidence. Never fabricates
    or assumes — if a check fails, the failure is reported explicitly.
    """
    ping_ms, packet_loss_pct, ping_error = _probe_ping()
    download_bps, speed_error = _probe_download_speed()

    is_degraded = _compute_degraded(ping_ms, packet_loss_pct, download_bps)
    summary = _build_summary(ping_ms, packet_loss_pct, download_bps,
                             is_degraded, ping_error, speed_error)

    logger.info(f'network_probe: {summary}')

    return NetworkMeasurement(
        ping_ms=ping_ms,
        packet_loss_pct=packet_loss_pct,
        download_bps=download_bps,
        is_degraded=is_degraded,
        summary=summary,
        ping_error=ping_error,
        speed_error=speed_error,
    )


# ---------------------------------------------------------------------------
# Ping probe
# ---------------------------------------------------------------------------

def _probe_ping() -> tuple[Optional[float], Optional[float], Optional[str]]:
    """Ping 8.8.8.8 three times. Return (avg_rtt_ms, loss_pct, error_or_None)."""
    try:
        result = subprocess.run(
            ['ping', '-c', '3', '-W', '2', _PING_HOST],
            capture_output=True,
            text=True,
            timeout=15,
        )
        output = result.stdout + result.stderr

        # Parse packet loss
        loss_pct = None
        loss_match = re.search(r'(\d+(?:\.\d+)?)\s*%\s*packet\s+loss', output, re.IGNORECASE)
        if loss_match:
            loss_pct = float(loss_match.group(1))

        # Parse avg RTT — macOS: "round-trip min/avg/max/stddev = X/Y/Z/W ms"
        #                Linux:  "rtt min/avg/max/mdev = X/Y/Z/W ms"
        avg_ms = None
        rtt_match = re.search(r'(?:round-trip|rtt)\s+\S+\s*=\s*[\d.]+/([\d.]+)/', output)
        if rtt_match:
            avg_ms = float(rtt_match.group(1))

        if avg_ms is None:
            if loss_pct == 100.0:
                return None, 100.0, '100% packet loss (host unreachable or ICMP blocked)'
            if loss_pct is None:
                snippet = output[:200].replace('\n', ' ')
                return None, None, f'ping output unparseable: {snippet!r}'
            return None, loss_pct, f'RTT unavailable ({loss_pct:.1f}% packet loss)'

        return avg_ms, loss_pct, None

    except subprocess.TimeoutExpired:
        return None, None, 'ping timed out after 15s'
    except FileNotFoundError:
        return None, None, 'ping binary not found'
    except Exception as exc:
        return None, None, f'ping failed: {exc}'


# ---------------------------------------------------------------------------
# Download speed probe
# ---------------------------------------------------------------------------

def _probe_download_speed() -> tuple[Optional[float], Optional[str]]:
    """Measure download speed to PyPI via curl. Return (bytes_per_sec, error_or_None)."""
    try:
        result = subprocess.run(
            [
                'curl',
                '-s',                           # silent (no progress bar)
                '-o', '/dev/null',              # discard body
                '-w', '%{speed_download}',      # print speed in bytes/sec
                '--max-time', str(_CURL_TIMEOUT),
                '--connect-timeout', '5',
                _SPEED_URL,
            ],
            capture_output=True,
            text=True,
            timeout=_CURL_TIMEOUT + 5,
        )
        raw = result.stdout.strip()
        if not raw:
            stderr_snippet = result.stderr[:200]
            return None, f'curl returned no speed value; stderr: {stderr_snippet!r}'

        try:
            bps = float(raw)
        except ValueError:
            return None, f'curl speed value unparseable: {raw!r}'

        if bps <= 0:
            return 0.0, None   # 0 is a valid (very slow) measurement

        return bps, None

    except subprocess.TimeoutExpired:
        return None, f'curl speed probe timed out after {_CURL_TIMEOUT + 5}s'
    except FileNotFoundError:
        return None, 'curl binary not found'
    except Exception as exc:
        return None, f'curl speed probe failed: {exc}'


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _compute_degraded(
    ping_ms: Optional[float],
    loss_pct: Optional[float],
    download_bps: Optional[float],
) -> bool:
    """Return True if any measured threshold indicates a degraded connection."""
    if ping_ms is not None and ping_ms > _DEGRADED_PING_MS:
        return True
    if loss_pct is not None and loss_pct > _DEGRADED_LOSS_PCT:
        return True
    if download_bps is not None and download_bps < _DEGRADED_SPEED_BPS:
        return True
    return False


def _fmt_speed(bps: float) -> str:
    """Human-readable speed: 'X.X KB/s' or 'X.X MB/s'."""
    if bps >= 1_000_000:
        return f'{bps / 1_000_000:.1f} MB/s'
    return f'{bps / 1_000:.1f} KB/s'


def _build_summary(
    ping_ms: Optional[float],
    loss_pct: Optional[float],
    download_bps: Optional[float],
    is_degraded: bool,
    ping_error: Optional[str],
    speed_error: Optional[str],
) -> str:
    """Assemble a concise, evidence-backed summary string."""
    parts = []

    # Ping section
    if ping_error:
        parts.append(f'ping: {ping_error}')
    else:
        ping_str = f'{ping_ms:.0f}ms' if ping_ms is not None else 'unknown RTT'
        loss_str = f'{loss_pct:.0f}% loss' if loss_pct is not None else 'unknown loss'
        parts.append(f'ping {ping_str} ({loss_str})')

    # Speed section
    if speed_error:
        parts.append(f'PyPI speed: {speed_error}')
    elif download_bps is not None:
        parts.append(f'PyPI: {_fmt_speed(download_bps)}')

    quality = 'DEGRADED' if is_degraded else 'functional'
    return ', '.join(parts) + f' — connection {quality}'
