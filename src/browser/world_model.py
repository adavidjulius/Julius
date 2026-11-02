"""
World Model — persistent browser facts across the agent session.

The agent treats browser state as part of its world model rather than
isolated per-turn observations. Persistent facts like:
  "I am logged in"
  "The shopping cart contains 3 items"
  "Checkout failed because payment was rejected"
  "The form submitted successfully"

…survive across multiple browser actions and are automatically injected
into the agent's observation context so it always has current browser state.

WorldModel is a singleton per-session, persisted to .julius/world_model.json
so facts survive server restarts and crash recovery.

FactExtractor runs after every BrowserObservation to update facts using
structural heuristics — no LLM calls required.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .structured_obs import BrowserObservation

logger = logging.getLogger(__name__)


# ── WorldFact ─────────────────────────────────────────────────────────────────

@dataclass
class WorldFact:
    """A single persistent browser fact."""
    key: str
    value: Any
    source_url: str = ""
    confidence: float = 1.0          # 0.0–1.0
    timestamp: float = field(default_factory=time.time)
    ttl_seconds: float | None = None  # None = permanent

    @property
    def is_expired(self) -> bool:
        if self.ttl_seconds is None:
            return False
        return (time.time() - self.timestamp) > self.ttl_seconds

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "value": self.value,
            "source_url": self.source_url,
            "confidence": self.confidence,
            "timestamp": self.timestamp,
            "ttl_seconds": self.ttl_seconds,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "WorldFact":
        return cls(
            key=d["key"],
            value=d["value"],
            source_url=d.get("source_url", ""),
            confidence=d.get("confidence", 1.0),
            timestamp=d.get("timestamp", time.time()),
            ttl_seconds=d.get("ttl_seconds"),
        )


# ── WorldModel ────────────────────────────────────────────────────────────────

class WorldModel:
    """
    Singleton that stores persistent browser facts across the agent session.

    Facts are automatically extracted from BrowserObservations by FactExtractor
    and can also be set manually by the agent via `browser_assert_fact`.

    Persisted to .julius/world_model.json — survives restarts.
    """

    def __init__(self, workspace_root: str, persist: bool = True) -> None:
        self.workspace_root = Path(workspace_root)
        self.persist = persist
        self._facts: dict[str, WorldFact] = {}
        self._persist_path = self.workspace_root / ".julius" / "world_model.json"
        if persist:
            self._load()

    # ── CRUD ─────────────────────────────────────────────────────────────────

    def assert_fact(
        self,
        key: str,
        value: Any,
        source_url: str = "",
        confidence: float = 1.0,
        ttl_seconds: float | None = None,
    ) -> WorldFact:
        """Set or update a fact."""
        fact = WorldFact(
            key=key,
            value=value,
            source_url=source_url,
            confidence=confidence,
            ttl_seconds=ttl_seconds,
        )
        self._facts[key] = fact
        if self.persist:
            self._save()
        logger.debug(f"WorldModel: asserted {key!r} = {value!r} (confidence={confidence})")
        return fact

    def retract_fact(self, key: str) -> bool:
        """Remove a fact. Returns True if it existed."""
        existed = key in self._facts
        self._facts.pop(key, None)
        if existed and self.persist:
            self._save()
        return existed

    def get_fact(self, key: str) -> WorldFact | None:
        """Get a fact by exact key, returning None if absent or expired."""
        fact = self._facts.get(key)
        if fact and fact.is_expired:
            del self._facts[key]
            if self.persist:
                self._save()
            return None
        return fact

    def get_value(self, key: str, default: Any = None) -> Any:
        fact = self.get_fact(key)
        return fact.value if fact else default

    def query(self, pattern: str) -> list[WorldFact]:
        """
        Return all facts whose key starts with the given prefix pattern.
        E.g. query("cart") returns cart_item_count, cart_total, etc.
        """
        import fnmatch
        self._evict_expired()
        return [f for k, f in self._facts.items() if fnmatch.fnmatch(k, pattern)]

    def keys(self) -> list[str]:
        self._evict_expired()
        return list(self._facts.keys())

    def clear(self) -> None:
        self._facts.clear()
        if self.persist:
            self._save()

    # ── Rendering ─────────────────────────────────────────────────────────────

    def to_text(self) -> str:
        self._evict_expired()
        if not self._facts:
            return "BROWSER WORLD MODEL: (no facts yet)"

        lines = ["BROWSER WORLD MODEL"]
        lines.append("─" * 36)
        for key, fact in sorted(self._facts.items()):
            conf_tag = f" (confidence={fact.confidence:.0%})" if fact.confidence < 1.0 else ""
            ttl_tag = f" [expires in {int(fact.ttl_seconds - (time.time() - fact.timestamp))}s]" if fact.ttl_seconds else ""
            lines.append(f"  {key}: {fact.value!r}{conf_tag}{ttl_tag}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        self._evict_expired()
        return {k: f.to_dict() for k, f in self._facts.items()}

    # ── Persistence ───────────────────────────────────────────────────────────

    def _save(self) -> None:
        try:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            self._persist_path.write_text(
                json.dumps(self.to_dict(), indent=2, default=str),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning(f"WorldModel: failed to save to {self._persist_path}: {exc}")

    def _load(self) -> None:
        if not self._persist_path.exists():
            return
        try:
            data = json.loads(self._persist_path.read_text(encoding="utf-8"))
            for key, fact_data in data.items():
                fact = WorldFact.from_dict(fact_data)
                if not fact.is_expired:
                    self._facts[key] = fact
            logger.info(f"WorldModel: loaded {len(self._facts)} facts from disk")
        except Exception as exc:
            logger.warning(f"WorldModel: failed to load from {self._persist_path}: {exc}")

    def _evict_expired(self) -> None:
        expired = [k for k, f in self._facts.items() if f.is_expired]
        for k in expired:
            del self._facts[k]
        if expired and self.persist:
            self._save()


# ── FactExtractor — heuristic rule engine ─────────────────────────────────────

_AUTH_PATTERNS = [
    "/login", "/signin", "/sign-in", "/auth/login", "/account/login",
    "session_expired", "please log in", "you must be logged in",
]

_LOGOUT_PATTERNS = [
    "/logout", "/signout", "/sign-out", "you have been logged out",
    "signed out successfully",
]

_CART_SELECTORS = [
    ".cart-count", "#cart-count", "[data-cart-count]",
    ".cart-quantity", ".cart-item-count", ".badge-cart",
    "[aria-label*='cart']",
]

_SUCCESS_PATTERNS = [
    "thank you for your order", "order confirmed", "order placed",
    "payment successful", "checkout complete", "success",
    "successfully submitted", "your request has been received",
]

_ERROR_PATTERNS = [
    "payment failed", "payment declined", "card declined",
    "invalid card", "transaction failed", "error processing",
    "something went wrong", "please try again",
]

_FORM_ERROR_SELECTORS = [
    ".error-message", ".alert-danger", ".form-error", "[role=alert]",
    ".field-error", ".validation-error", ".error",
]


class FactExtractor:
    """
    Extracts world model facts from a BrowserObservation using structural heuristics.

    No LLM calls — purely pattern matching on URL, title, text content.
    Called automatically after every browser action.
    """

    def __init__(self, world_model: WorldModel) -> None:
        self.wm = world_model

    def extract(self, obs: "BrowserObservation") -> list[str]:
        """
        Analyse the observation and update WorldModel facts.
        Returns a list of fact keys that were changed.
        """
        changed: list[str] = []
        url = obs.url.lower()
        title = obs.title.lower()
        dom = obs.dom_snapshot.lower()

        # ── Authentication state ──────────────────────────────────────────────
        if any(p in url or p in title or p in dom for p in _AUTH_PATTERNS):
            if self.wm.get_value("auth_status") != "logged_out":
                self.wm.assert_fact("auth_status", "logged_out", source_url=obs.url)
                changed.append("auth_status")

        if any(p in url or p in title or p in dom for p in _LOGOUT_PATTERNS):
            self.wm.assert_fact("auth_status", "logged_out", source_url=obs.url)
            changed.append("auth_status")

        # User-account pages → likely logged in
        if any(p in url for p in ["/account", "/dashboard", "/profile", "/my-"]):
            if self.wm.get_value("auth_status") != "logged_in":
                self.wm.assert_fact("auth_status", "logged_in", source_url=obs.url,
                                    confidence=0.8)
                changed.append("auth_status")

        # ── Current URL / page tracking ───────────────────────────────────────
        if obs.url:
            self.wm.assert_fact("current_url", obs.url, source_url=obs.url, ttl_seconds=300)
            changed.append("current_url")
        if obs.title:
            self.wm.assert_fact("current_page_title", obs.title, source_url=obs.url, ttl_seconds=300)
            changed.append("current_page_title")

        # ── Checkout / order success ──────────────────────────────────────────
        if any(p in title or p in dom for p in _SUCCESS_PATTERNS):
            self.wm.assert_fact("last_action_success", True, source_url=obs.url,
                                ttl_seconds=600)
            self.wm.assert_fact("checkout_complete", True, source_url=obs.url)
            changed.append("checkout_complete")

        # ── Payment / submission errors ───────────────────────────────────────
        if any(p in title or p in dom for p in _ERROR_PATTERNS):
            self.wm.assert_fact("last_action_success", False, source_url=obs.url,
                                ttl_seconds=120)
            # Extract the specific error message from the DOM
            for el in obs.interactive_elements:
                if "error" in el.role.lower() or "alert" in el.role.lower():
                    self.wm.assert_fact("last_error", el.label[:200], source_url=obs.url,
                                        ttl_seconds=120)
                    changed.append("last_error")
                    break

        # ── Cart item count ───────────────────────────────────────────────────
        # Try to parse cart count from interactive elements
        for el in obs.interactive_elements:
            if "cart" in el.label.lower() and any(c.isdigit() for c in el.label):
                import re
                nums = re.findall(r"\d+", el.label)
                if nums:
                    count = int(nums[0])
                    self.wm.assert_fact("cart_item_count", count, source_url=obs.url,
                                        ttl_seconds=600)
                    changed.append("cart_item_count")
                    break

        # ── Bot detection ─────────────────────────────────────────────────────
        if obs.bot_detection.detected:
            self.wm.assert_fact("captcha_blocking", True, source_url=obs.url,
                                ttl_seconds=300)
            self.wm.assert_fact("captcha_type", obs.bot_detection.detection_type,
                                source_url=obs.url, ttl_seconds=300)
            changed.extend(["captcha_blocking", "captcha_type"])
        else:
            # Clear captcha fact if we got past it
            if self.wm.get_value("captcha_blocking") and "captcha" not in url:
                self.wm.retract_fact("captcha_blocking")
                changed.append("captcha_blocking")

        # ── HTTP errors in network log ────────────────────────────────────────
        for req in obs.network_requests:
            if req.status == 401:
                self.wm.assert_fact("auth_status", "logged_out", source_url=obs.url)
                changed.append("auth_status")
                break
            if req.status == 403:
                self.wm.assert_fact("access_denied", True, source_url=req.url, ttl_seconds=60)
                changed.append("access_denied")
                break

        return list(set(changed))
