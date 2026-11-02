"""
Local Stats & Metrics Reporting for Single-Seat Users (WS5).

Powers the `julius stats` CLI command with local SQLite metrics queries.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.telemetry.cost import CostTracker


def print_local_stats(db_path: Optional[str] = None) -> None:
    """Query and render local usage statistics in terminal."""
    tracker = CostTracker(db_path=db_path)
    summary = tracker.get_daily_summary()

    print("\n📊 Julius Local Usage & Cost Summary")
    print("=" * 45)
    print(f" Date              : {summary['date']}")
    print(f" Prompt Tokens     : {summary['prompt_tokens']:,}")
    print(f" Completion Tokens : {summary['completion_tokens']:,}")
    print(f" Total Tokens      : {summary['total_tokens']:,}")
    print(f" Estimated Spend   : ${summary['cost_usd']:.4f}")
    print("=" * 45)
    print(" Local-first: all statistics stored strictly on your machine.\n")

