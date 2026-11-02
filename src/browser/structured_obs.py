"""
Structured browser observation schema.

Every browser action returns a BrowserObservation that is serialized into
a compact, LLM-readable text block the agent can reason over directly —
without needing to process a screenshot image.

The agent still gets screenshots for complex visual debugging, but its
primary reasoning is over the structured text form.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class InteractiveElement:
    """A clickable/fillable element discovered on the page."""
    role: str          # "button", "textbox", "link", "select", "checkbox", etc.
    label: str         # visible text or aria-label
    selector: str      # CSS selector or best available locator string
    disabled: bool = False
    value: str = ""    # current value for inputs/selects


@dataclass
class NetworkEntry:
    """A single captured network request/response pair."""
    url: str
    method: str        # GET, POST, PUT, …
    status: int        # HTTP status code (0 if not yet responded)
    duration_ms: int = 0
    resource_type: str = ""   # document, xhr, fetch, image, …


@dataclass
class BotDetection:
    """Populated when bot-blocking is detected on the page."""
    detected: bool = False
    detection_type: str = ""   # cloudflare_challenge, recaptcha, access_denied, …
    page_title: str = ""
    suggested_action: str = ""


@dataclass
class BrowserObservation:
    """
    Rich structured observation returned by every browser action.

    Fields
    ------
    url:                  Final URL after navigation (may differ from requested due to redirects).
    title:                Page <title>.
    dom_snapshot:         Condensed HTML skeleton of the page (pruned to ~2 KB).
    interactive_elements: Buttons, links, inputs, selects detected on the page.
    console_logs:         Browser console messages captured since last navigation.
    network_requests:     Network requests/responses observed during the action.
    screenshot_path:      Workspace-relative path to the screenshot file (if taken).
    bot_detection:        Populated when a bot-wall is detected.
    error:                Non-None when the action failed; describes the failure.
    action:               The browser action that produced this observation.
    extra:                Any action-specific supplemental data (JS eval result, extraction map…).
    """
    url: str = ""
    title: str = ""
    dom_snapshot: str = ""
    interactive_elements: list[InteractiveElement] = field(default_factory=list)
    console_logs: list[str] = field(default_factory=list)
    network_requests: list[NetworkEntry] = field(default_factory=list)
    screenshot_path: str = ""
    bot_detection: BotDetection = field(default_factory=BotDetection)
    error: str | None = None
    action: str = ""
    extra: dict[str, Any] = field(default_factory=dict)
    diff: Any = None

    # ── Serialisers ──────────────────────────────────────────────────────────

    def to_text(self) -> str:
        """
        Compact human/LLM-readable representation.

        This is what gets injected as ``last_result`` in the agent's
        observation template so the model can reason over page state as text.
        """
        if self.diff is not None:
            from .dom_diff import DOMDiff
            return DOMDiff.format_observation_with_diff(self, self.diff)

        lines = ["BROWSER OBSERVATION", "─" * 40]

        lines.append(f"Action : {self.action}")
        lines.append(f"URL    : {self.url or '(none)'}")
        lines.append(f"Title  : {self.title or '(none)'}")
        lines.append(f"Status : {'ERROR — ' + self.error if self.error else 'success'}")

        if self.bot_detection.detected:
            lines += [
                "",
                "⚠️  BOT DETECTION",
                f"  Type      : {self.bot_detection.detection_type}",
                f"  Page title: {self.bot_detection.page_title}",
                f"  Suggestion: {self.bot_detection.suggested_action}",
            ]

        # Interactive elements
        if self.interactive_elements:
            lines += ["", f"INTERACTIVE ELEMENTS ({len(self.interactive_elements)} total):"]
            for el in self.interactive_elements[:20]:   # cap at 20 to keep context short
                disabled_tag = " [disabled]" if el.disabled else ""
                value_tag = f" (value={el.value!r})" if el.value else ""
                lines.append(f"  [{el.role}] {el.label!r}{value_tag} → {el.selector}{disabled_tag}")
            if len(self.interactive_elements) > 20:
                lines.append(f"  … and {len(self.interactive_elements) - 20} more")
        else:
            lines.append("\nINTERACTIVE ELEMENTS: (none found)")

        # Console logs
        if self.console_logs:
            lines += ["", f"CONSOLE ({len(self.console_logs)} messages):"]
            for msg in self.console_logs[-10:]:   # last 10
                lines.append(f"  {msg}")
        
        # Network requests
        if self.network_requests:
            lines += ["", f"NETWORK ({len(self.network_requests)} requests):"]
            for req in self.network_requests[:15]:
                dur = f" ({req.duration_ms}ms)" if req.duration_ms else ""
                lines.append(f"  {req.method} {_truncate_url(req.url)} → {req.status}{dur}")
            if len(self.network_requests) > 15:
                lines.append(f"  … and {len(self.network_requests) - 15} more")

        # DOM snapshot
        if self.dom_snapshot:
            lines += ["", "DOM SNAPSHOT (condensed):"]
            # Cap to ~80 lines to avoid bloating the context
            snapshot_lines = self.dom_snapshot.splitlines()
            if len(snapshot_lines) > 80:
                lines += snapshot_lines[:80]
                lines.append(f"  … ({len(snapshot_lines) - 80} lines truncated)")
            else:
                lines += snapshot_lines

        # Extra action-specific data
        if self.extra:
            lines += ["", "EXTRA DATA:"]
            lines.append(json.dumps(self.extra, indent=2, default=str))

        if self.screenshot_path:
            lines += ["", f"Screenshot: {self.screenshot_path}"]

        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """JSON-serialisable dict — used for tracing and event emission."""
        return {
            "action": self.action,
            "url": self.url,
            "title": self.title,
            "error": self.error,
            "interactive_elements": [
                {"role": e.role, "label": e.label, "selector": e.selector,
                 "disabled": e.disabled, "value": e.value}
                for e in self.interactive_elements
            ],
            "console_logs": self.console_logs,
            "network_requests": [
                {"url": r.url, "method": r.method, "status": r.status,
                 "duration_ms": r.duration_ms, "resource_type": r.resource_type}
                for r in self.network_requests
            ],
            "screenshot_path": self.screenshot_path,
            "bot_detection": {
                "detected": self.bot_detection.detected,
                "detection_type": self.bot_detection.detection_type,
                "page_title": self.bot_detection.page_title,
                "suggested_action": self.bot_detection.suggested_action,
            },
            "extra": self.extra,
        }

    @property
    def success(self) -> bool:
        return self.error is None

    def as_action_result_output(self) -> str:
        """Convenience: the text that goes into ActionResult.output."""
        return self.to_text()


# ── Helpers ──────────────────────────────────────────────────────────────────

def _truncate_url(url: str, max_len: int = 80) -> str:
    if len(url) <= max_len:
        return url
    return url[:max_len - 3] + "..."
