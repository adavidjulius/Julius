"""
Prometheus Metrics, Label Hygiene & Health Probes (WS5).

Implements:
- Sanitized Prometheus metrics format without high-cardinality labels.
- /healthz (liveness probe).
- /readyz (readiness probe: database, disk space, and memory stores).
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from aiohttp import web


class MetricsRegistry:
    """Thread-safe in-memory metrics registry for Prometheus scraping."""

    def __init__(self) -> None:
        self._counters: Dict[str, float] = {}
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, List[float]] = {}

    def inc_counter(self, name: str, value: float = 1.0, labels: Optional[Dict[str, str]] = None) -> None:
        key = self._format_key(name, labels)
        self._counters[key] = self._counters.get(key, 0.0) + value

    def set_gauge(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        key = self._format_key(name, labels)
        self._gauges[key] = value

    def observe_histogram(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        key = self._format_key(name, labels)
        if key not in self._histograms:
            self._histograms[key] = []
        self._histograms[key].append(value)
        # Keep sliding sample window of 1000
        if len(self._histograms[key]) > 1000:
            self._histograms[key].pop(0)

    @staticmethod
    def _format_key(name: str, labels: Optional[Dict[str, str]] = None) -> str:
        """Format metric name with sanitized labels (hygiene check)."""
        if not labels:
            return name
        # Filter forbidden high-cardinality labels
        safe_labels = {}
        for k, v in labels.items():
            if k.lower() in ("user_id", "prompt", "path", "ip", "session_id"):
                continue  # Strip high cardinality
            safe_labels[k] = str(v)
        if not safe_labels:
            return name
        label_str = ",".join(f'{k}="{v}"' for k, v in sorted(safe_labels.items()))
        return f"{name}{{{label_str}}}"

    def export_prometheus_text(self) -> str:
        """Render all metrics in Prometheus text exposition format."""
        lines = []
        for k, v in sorted(self._counters.items()):
            lines.append(f"# TYPE {k.split('{')[0]} counter")
            lines.append(f"{k} {v}")
        for k, v in sorted(self._gauges.items()):
            lines.append(f"# TYPE {k.split('{')[0]} gauge")
            lines.append(f"{k} {v}")
        for k, samples in sorted(self._histograms.items()):
            base_name = k.split('{')[0]
            lines.append(f"# TYPE {base_name} histogram")
            if samples:
                lines.append(f"{base_name}_count {len(samples)}")
                lines.append(f"{base_name}_sum {sum(samples)}")
                lines.append(f"{base_name}_avg {sum(samples) / len(samples):.4f}")
        return "\n".join(lines) + "\n"


_METRICS = MetricsRegistry()


def get_metrics() -> MetricsRegistry:
    return _METRICS


# ── Health Probes ─────────────────────────────────────────────────────────────

async def handle_healthz(request: web.Request) -> web.Response:
    """Liveness probe: returns 200 if daemon process is responsive."""
    return web.json_response({"status": "ok", "service": "julius", "time": time.time()})


async def handle_readyz(request: web.Request) -> web.Response:
    """Readiness probe: validates database connectivity and disk storage."""
    workspace = request.app.get("workspace", os.getcwd())
    ws_path = Path(workspace)

    # 1. Disk space check
    disk_ok = True
    disk_msg = "OK"
    try:
        usage = shutil.disk_usage(ws_path)
        free_gb = usage.free / (1024 ** 3)
        if free_gb < 0.2:  # 200MB minimum
            disk_ok = False
            disk_msg = f"Insufficient disk space ({free_gb:.2f} GB available)"
    except Exception as e:
        disk_ok = False
        disk_msg = str(e)

    # 2. Database quick check
    db_ok = True
    db_msg = "OK"
    db_candidate = ws_path / ".julius" / "memory.db"
    if db_candidate.exists():
        try:
            conn = sqlite3.connect(str(db_candidate), timeout=2.0)
            res = conn.execute("PRAGMA quick_check;").fetchone()
            conn.close()
            if not res or res[0] != "ok":
                db_ok = False
                db_msg = f"DB check failed: {res[0] if res else 'no result'}"
        except Exception as e:
            db_ok = False
            db_msg = str(e)

    all_ready = disk_ok and db_ok
    status_code = 200 if all_ready else 503
    return web.json_response(
        {
            "status": "ready" if all_ready else "not_ready",
            "checks": {
                "disk": {"ready": disk_ok, "details": disk_msg},
                "database": {"ready": db_ok, "details": db_msg},
            },
        },
        status=status_code,
    )


async def handle_metrics(request: web.Request) -> web.Response:
    """Prometheus exposition endpoint."""
    text = get_metrics().export_prometheus_text()
    return web.Response(text=text, content_type="text/plain; version=0.0.4")

