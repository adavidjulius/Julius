"""
Browser Memory — per-context semantic memory of what the agent has done.

Tracks:
  - Semantic page history (URL + title + actions taken, not raw HTML)
  - Forms already filled (selector → last typed value)
  - Buttons/links already clicked (selector → count)
  - Failed selectors (selector → list of error messages)
  - Known elements across pages (selector → ElementMemory)

Attached to BrowserContextRecord; updated automatically by actions.py
helper `record_browser_action()` after every interaction.

No LLM calls — purely structural bookkeeping.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class PageVisit:
    """Semantic summary of a single page visit."""
    url: str
    title: str
    timestamp: float = field(default_factory=time.monotonic)
    # Short human-readable description of what the agent did here
    actions_taken: list[str] = field(default_factory=list)
    # Key facts extracted from the page (populated by FactExtractor)
    observed_facts: dict[str, Any] = field(default_factory=dict)

    def to_text(self) -> str:
        parts = [f"• {self.title} ({self.url})"]
        if self.actions_taken:
            parts.append("  Actions: " + "; ".join(self.actions_taken[-5:]))
        return "\n".join(parts)


@dataclass
class ElementMemory:
    """Memory of a specific interactive element across visits."""
    selector: str
    role: str
    label: str
    last_value: str = ""          # last value typed into this element
    click_count: int = 0
    failed_count: int = 0         # times selector was tried but failed
    last_seen_url: str = ""
    last_error: str = ""          # most recent failure message

    @property
    def reliability_score(self) -> float:
        """0.0 (always fails) to 1.0 (always works)."""
        total = self.click_count + self.failed_count
        if total == 0:
            return 1.0
        return self.click_count / total


# ── Main memory class ─────────────────────────────────────────────────────────

class BrowserMemory:
    """
    Per-context semantic memory of what the agent has done in this browser context.

    Lifetime: one BrowserContextRecord — cleared when the context is closed.
    Persisted to disk via WorldModel if disk persistence is enabled.
    """

    MAX_PAGE_HISTORY = 50
    MAX_ELEMENT_ENTRIES = 200

    def __init__(self) -> None:
        self.page_history: list[PageVisit] = []
        self.filled_forms: dict[str, str] = {}         # selector → last typed value
        self.clicked_elements: dict[str, int] = {}     # selector → click count
        self.failed_selectors: dict[str, list[str]] = {}  # selector → errors
        self.known_elements: dict[str, ElementMemory] = {}

    # ── Recording ────────────────────────────────────────────────────────────

    def record_navigation(self, url: str, title: str) -> PageVisit:
        """Record a page navigation. Returns the new PageVisit."""
        visit = PageVisit(url=url, title=title)
        self.page_history.append(visit)
        if len(self.page_history) > self.MAX_PAGE_HISTORY:
            self.page_history.pop(0)
        return visit

    def record_action_on_current_page(self, description: str) -> None:
        """Append a short action description to the current page visit."""
        if self.page_history:
            self.page_history[-1].actions_taken.append(description)

    def record_click(self, selector: str, label: str = "", url: str = "") -> None:
        self.clicked_elements[selector] = self.clicked_elements.get(selector, 0) + 1
        mem = self._get_or_create_element(selector, "button", label)
        mem.click_count += 1
        mem.last_seen_url = url
        self.record_action_on_current_page(f"clicked {(label or selector)!r}")

    def record_type(self, selector: str, value: str, label: str = "", url: str = "") -> None:
        self.filled_forms[selector] = value
        mem = self._get_or_create_element(selector, "input", label)
        mem.last_value = value
        mem.last_seen_url = url
        self.record_action_on_current_page(f"typed into {(label or selector)!r}")

    def record_failure(self, selector: str, error: str) -> None:
        if selector not in self.failed_selectors:
            self.failed_selectors[selector] = []
        self.failed_selectors[selector].append(error)
        if selector in self.known_elements:
            self.known_elements[selector].failed_count += 1
            self.known_elements[selector].last_error = error

    def record_select(self, selector: str, value: str, label: str = "", url: str = "") -> None:
        self.filled_forms[selector] = value
        mem = self._get_or_create_element(selector, "select", label)
        mem.last_value = value
        mem.last_seen_url = url
        self.record_action_on_current_page(f"selected {value!r} in {(label or selector)!r}")

    # ── Querying ─────────────────────────────────────────────────────────────

    def already_filled(self, selector: str) -> str | None:
        """Return the last value typed into a selector, or None."""
        return self.filled_forms.get(selector)

    def already_clicked(self, selector: str) -> int:
        """Return how many times a selector was clicked (0 = never)."""
        return self.clicked_elements.get(selector, 0)

    def is_known_bad_selector(self, selector: str) -> bool:
        """True if this selector has failed more than once."""
        return len(self.failed_selectors.get(selector, [])) > 1

    def suggest_alternative_selector(self, failed_selector: str) -> str | None:
        """
        Look up the known element and suggest an alternative locator.
        Returns None if no alternative is known.
        """
        mem = self.known_elements.get(failed_selector)
        if not mem or not mem.label:
            return None
        # Build progressive alternatives based on what we know about the element
        label = mem.label
        role = mem.role
        alternatives = [
            f"[aria-label=\"{label}\"]",
            f"[placeholder=\"{label}\"]",
            f"[name=\"{label.lower().replace(' ', '_')}\"]",
        ]
        if role in ("button", "link"):
            alternatives.insert(0, f"text={label}")
        # Return the first alternative that hasn't already failed
        for alt in alternatives:
            if alt not in self.failed_selectors or len(self.failed_selectors[alt]) == 0:
                return alt
        return None

    def current_page(self) -> PageVisit | None:
        return self.page_history[-1] if self.page_history else None

    def visited_url(self, url: str) -> bool:
        return any(v.url == url or v.url.rstrip("/") == url.rstrip("/") for v in self.page_history)

    # ── Text output for agent ─────────────────────────────────────────────────

    def to_text(self) -> str:
        lines = ["BROWSER MEMORY"]
        lines.append("─" * 36)

        # Page history (last 5)
        if self.page_history:
            lines.append(f"Page history ({len(self.page_history)} visits):")
            for visit in self.page_history[-5:]:
                lines.append("  " + visit.to_text().replace("\n", "\n  "))
        else:
            lines.append("Page history: (none)")

        # Forms already filled
        if self.filled_forms:
            lines.append(f"\nForms filled ({len(self.filled_forms)}):")
            for sel, val in list(self.filled_forms.items())[-10:]:
                lines.append(f"  {sel} = {val!r}")

        # Buttons clicked
        if self.clicked_elements:
            lines.append(f"\nElements clicked ({len(self.clicked_elements)}):")
            for sel, count in list(self.clicked_elements.items())[-10:]:
                lines.append(f"  {sel} ×{count}")

        # Failed selectors
        if self.failed_selectors:
            lines.append(f"\nFailed selectors ({len(self.failed_selectors)}):")
            for sel, errors in list(self.failed_selectors.items())[-5:]:
                lines.append(f"  {sel}: {errors[-1][:60]}")

        return "\n".join(lines)

    # ── Serialization ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "page_history": [
                {
                    "url": v.url, "title": v.title,
                    "actions_taken": v.actions_taken[-10:],
                    "observed_facts": v.observed_facts,
                }
                for v in self.page_history[-20:]
            ],
            "filled_forms": dict(self.filled_forms),
            "clicked_elements": dict(self.clicked_elements),
            "failed_selectors": {k: v[-3:] for k, v in self.failed_selectors.items()},
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BrowserMemory":
        mem = cls()
        for v in data.get("page_history", []):
            visit = PageVisit(url=v["url"], title=v["title"])
            visit.actions_taken = v.get("actions_taken", [])
            visit.observed_facts = v.get("observed_facts", {})
            mem.page_history.append(visit)
        mem.filled_forms = data.get("filled_forms", {})
        mem.clicked_elements = data.get("clicked_elements", {})
        mem.failed_selectors = data.get("failed_selectors", {})
        return mem

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _get_or_create_element(self, selector: str, role: str, label: str) -> ElementMemory:
        if selector not in self.known_elements:
            self.known_elements[selector] = ElementMemory(
                selector=selector, role=role, label=label
            )
            if len(self.known_elements) > self.MAX_ELEMENT_ENTRIES:
                # Evict the oldest entry
                oldest = next(iter(self.known_elements))
                del self.known_elements[oldest]
        return self.known_elements[selector]


# ── Action recording helper (called from actions.py) ─────────────────────────

def record_browser_action(
    memory: BrowserMemory,
    action: str,
    args: dict,
    url: str = "",
) -> None:
    """
    Update BrowserMemory based on a completed action.
    Called from actions.py after every successful interaction.
    """
    sel = args.get("selector", "")
    label = args.get("text", "") or args.get("label", "")

    if action == "browser_click":
        memory.record_click(sel or label, label=label, url=url)
    elif action == "browser_type":
        memory.record_type(sel, args.get("text", ""), label=label, url=url)
    elif action == "browser_select":
        memory.record_select(sel, args.get("value", ""), label=label, url=url)
    elif action == "browser_navigate":
        memory.record_navigation(args.get("url", url), "")  # title updated later
    # Other actions (scroll, hover, press) are low-level and not semantically tracked


def record_browser_failure(
    memory: BrowserMemory,
    selector: str,
    error: str,
) -> None:
    """Record a selector failure in memory."""
    if selector:
        memory.record_failure(selector, error)
