"""
DOM Diff Engine — compare two BrowserObservations and summarize what changed.

Instead of dumping the full DOM snapshot into the agent's context on every
browser action, this module produces a compact change summary:

  "DOM DIFF: +2 elements (modal appeared: 'Confirm Order', 'Cancel').
   -1 element ('Add to Cart' button removed). URL unchanged. Title unchanged."

This dramatically reduces context usage on multi-step browser tasks where
most of the page stays the same between actions.

Rules:
  - First observation of a page: always return full snapshot (no diff)
  - Subsequent observations: return diff summary + only new/changed elements
  - Agent can always call browser_get_snapshot for a full fresh observation
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .structured_obs import BrowserObservation, InteractiveElement, NetworkEntry


# ── DiffResult ────────────────────────────────────────────────────────────────

@dataclass
class DiffResult:
    """Summary of what changed between two BrowserObservations."""
    url_changed: bool = False
    title_changed: bool = False
    old_url: str = ""
    new_url: str = ""
    old_title: str = ""
    new_title: str = ""

    # Element changes
    added_elements: list["InteractiveElement"] = field(default_factory=list)
    removed_elements: list["InteractiveElement"] = field(default_factory=list)
    changed_elements: list["InteractiveElement"] = field(default_factory=list)  # value changed

    # Console / network deltas
    new_console_errors: list[str] = field(default_factory=list)
    new_network_calls: list["NetworkEntry"] = field(default_factory=list)
    error_appeared: bool = False
    error_text: str = ""

    # Magnitude
    is_major_change: bool = False   # True when >30% of elements changed or URL changed

    @property
    def has_changes(self) -> bool:
        return any([
            self.url_changed,
            self.title_changed,
            self.added_elements,
            self.removed_elements,
            self.changed_elements,
            self.new_console_errors,
            self.error_appeared,
        ])

    def to_text(self) -> str:
        if not self.has_changes:
            return "DOM DIFF: No meaningful changes detected."

        parts = ["DOM DIFF:"]

        if self.url_changed:
            parts.append(f"  URL changed: {self.old_url} → {self.new_url}")
        if self.title_changed:
            parts.append(f"  Title changed: {self.old_title!r} → {self.new_title!r}")

        if self.added_elements:
            labels = [f"{e.role}:{e.label!r}" for e in self.added_elements[:5]]
            extra = f" +{len(self.added_elements) - 5} more" if len(self.added_elements) > 5 else ""
            parts.append(f"  +{len(self.added_elements)} elements appeared: {', '.join(labels)}{extra}")

        if self.removed_elements:
            labels = [f"{e.role}:{e.label!r}" for e in self.removed_elements[:5]]
            extra = f" +{len(self.removed_elements) - 5} more" if len(self.removed_elements) > 5 else ""
            parts.append(f"  -{len(self.removed_elements)} elements disappeared: {', '.join(labels)}{extra}")

        if self.changed_elements:
            for el in self.changed_elements[:3]:
                parts.append(f"  ~ {el.role}:{el.label!r} value changed to {el.value!r}")

        if self.new_console_errors:
            for err in self.new_console_errors[:3]:
                parts.append(f"  Console error: {err[:100]}")

        if self.error_appeared:
            parts.append(f"  ⚠ Error message appeared: {self.error_text[:120]}")

        if self.new_network_calls:
            for req in self.new_network_calls[:5]:
                parts.append(f"  Network: {req.method} {req.url[:60]} → {req.status}")

        if self.is_major_change:
            parts.append("  [MAJOR CHANGE — page structure significantly altered]")

        return "\n".join(parts)


# ── DOMDiff engine ────────────────────────────────────────────────────────────

class DOMDiff:
    """
    Stateless diff engine that compares two BrowserObservations.

    Usage
    -----
    diff = DOMDiff.diff(before_obs, after_obs)
    if diff.is_major_change:
        # Page changed unexpectedly — GoalNavigator should replan
        ...
    print(diff.to_text())
    """

    # Threshold: if this fraction of elements changed, it's a "major change"
    MAJOR_CHANGE_THRESHOLD = 0.30

    @classmethod
    def diff(
        cls,
        before: "BrowserObservation",
        after: "BrowserObservation",
    ) -> DiffResult:
        result = DiffResult()

        # URL / title
        if before.url != after.url:
            result.url_changed = True
            result.old_url = before.url
            result.new_url = after.url

        if before.title != after.title:
            result.title_changed = True
            result.old_title = before.title
            result.new_title = after.title

        # Interactive element diff
        before_by_sel = {e.selector: e for e in before.interactive_elements}
        after_by_sel = {e.selector: e for e in after.interactive_elements}

        before_keys = set(before_by_sel.keys())
        after_keys = set(after_by_sel.keys())

        result.added_elements = [after_by_sel[k] for k in after_keys - before_keys]
        result.removed_elements = [before_by_sel[k] for k in before_keys - after_keys]

        # Elements that exist in both but changed value
        for key in before_keys & after_keys:
            b = before_by_sel[key]
            a = after_by_sel[key]
            if b.value != a.value and a.value:
                result.changed_elements.append(a)

        # Error detection — look for error-like elements that appeared
        before_labels = {e.label.lower() for e in before.interactive_elements}
        error_keywords = {"error", "invalid", "failed", "declined", "wrong", "expired"}
        for el in result.added_elements:
            if any(kw in el.label.lower() for kw in error_keywords):
                result.error_appeared = True
                result.error_text = el.label
                break

        # Console delta — new errors that weren't in before
        before_console = set(before.console_logs)
        new_console = [m for m in after.console_logs if m not in before_console]
        result.new_console_errors = [m for m in new_console if "[error]" in m.lower()]

        # Network delta — calls that appeared in after but weren't in before
        before_net_urls = {(r.url, r.method, r.status) for r in before.network_requests}
        result.new_network_calls = [
            r for r in after.network_requests
            if (r.url, r.method, r.status) not in before_net_urls
        ]

        # Determine if this is a major change
        total_before = len(before_by_sel) or 1
        delta = len(result.added_elements) + len(result.removed_elements)
        result.is_major_change = (
            result.url_changed
            or (delta / total_before) >= cls.MAJOR_CHANGE_THRESHOLD
        )

        return result

    @staticmethod
    def format_observation_with_diff(
        obs: "BrowserObservation",
        diff: DiffResult | None,
    ) -> str:
        """
        Format an observation for the agent.

        If diff is None (first visit), returns the full observation text.
        If diff has changes, returns the diff summary + only new elements.
        If nothing changed, returns a minimal "no change" summary.
        """
        if diff is None:
            return obs.to_text()

        if not diff.has_changes:
            # Almost nothing happened — minimal output to save context
            lines = [
                f"BROWSER OBSERVATION (after action, no significant change)",
                f"URL: {obs.url}",
                f"Title: {obs.title}",
            ]
            if obs.screenshot_path:
                lines.append(f"Screenshot: {obs.screenshot_path}")
            return "\n".join(lines)

        # Changes found — show diff then only the new/changed elements
        lines = [diff.to_text(), ""]
        lines.append(f"URL: {obs.url}")
        lines.append(f"Title: {obs.title}")

        if diff.added_elements:
            lines.append("\nNEW INTERACTIVE ELEMENTS:")
            for el in diff.added_elements[:10]:
                disabled_tag = " [disabled]" if el.disabled else ""
                lines.append(f"  [{el.role}] {el.label!r} → {el.selector}{disabled_tag}")

        if obs.screenshot_path:
            lines.append(f"\nScreenshot: {obs.screenshot_path}")

        if diff.is_major_change:
            lines.append("\n[Full DOM snapshot available via browser_get_snapshot]")

        return "\n".join(lines)
