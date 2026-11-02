"""
Token Cost Tracking & Budget Enforcement (WS5).

Computes real-time costs using pricing.yaml, tracks cumulative daily/run spend,
and raises AgentBudgetError if cost limits are exceeded.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Tuple

from src.errors import JUL_AGT_BUDGET_EXCEEDED, AgentBudgetError

logger = logging.getLogger(__name__)


class CostTracker:
    """Tracks token expenses and enforces budget hard stops."""

    def __init__(
        self,
        db_path: Optional[str] = None,
        max_run_cost_usd: float = 5.0,
        max_daily_budget_usd: float = 25.0,
    ) -> None:
        if db_path:
            self.db_path = Path(db_path)
        else:
            self.db_path = Path.home() / ".julius" / "stats.db"
        self.max_run_cost = max_run_cost_usd
        self.max_daily_budget = max_daily_budget_usd
        self.current_run_cost = 0.0
        self._init_db()

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS token_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                date_str TEXT NOT NULL,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                prompt_tokens INTEGER NOT NULL,
                completion_tokens INTEGER NOT NULL,
                cost_usd REAL NOT NULL
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_date ON token_usage(date_str);")
        conn.commit()
        conn.close()

    def record_usage(
        self,
        provider: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: float,
    ) -> None:
        """Record token usage and enforce budget constraints."""
        self.current_run_cost += cost_usd

        now = time.time()
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO token_usage (ts, date_str, provider, model, prompt_tokens, completion_tokens, cost_usd)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (now, date_str, provider, model, prompt_tokens, completion_tokens, cost_usd),
        )
        conn.commit()

        # Check daily cumulative spend
        cursor.execute("SELECT SUM(cost_usd) FROM token_usage WHERE date_str = ?", (date_str,))
        row = cursor.fetchone()
        daily_total = row[0] or 0.0
        conn.close()

        # Enforce budget limits
        if self.current_run_cost > self.max_run_cost:
            raise AgentBudgetError(
                code=JUL_AGT_BUDGET_EXCEEDED,
                message=f"Run cost budget exceeded: ${self.current_run_cost:.4f} > limit ${self.max_run_cost:.2f}",
                hint="Increase budgets.max_cost_usd_per_run in config if larger runs are intended.",
                details={"run_cost": self.current_run_cost, "limit": self.max_run_cost},
            )

        if daily_total > self.max_daily_budget:
            logger.warning(f"Daily budget alert: ${daily_total:.2f} spent today (limit ${self.max_daily_budget:.2f})")

    def get_daily_summary(self) -> Dict[str, Any]:
        """Return today's token and cost summary."""
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT SUM(prompt_tokens), SUM(completion_tokens), SUM(cost_usd)
            FROM token_usage WHERE date_str = ?
            """,
            (date_str,),
        )
        row = cursor.fetchone()
        conn.close()
        return {
            "date": date_str,
            "prompt_tokens": row[0] or 0,
            "completion_tokens": row[1] or 0,
            "total_tokens": (row[0] or 0) + (row[1] or 0),
            "cost_usd": round(row[2] or 0.0, 4),
        }

