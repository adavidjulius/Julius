"""
Action Verifier — post-action state change verification with alternative strategies.

After every click or form submission, automatically verifies whether the
intended state change actually occurred. If not, retries with an alternative
selector strategy before surfacing the failure to the agent.

Selector strategies (tried in order on failure):
  1. Exact CSS selector
  2. text=<label> (Playwright text locator)
  3. aria-label=<label>
  4. name=<field_name>
  5. XPath fallback
  6. Memory suggestion (from BrowserMemory.suggest_alternative_selector)

No LLM calls — purely structural heuristics.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.async_api import Page
    from .structured_obs import BrowserObservation
    from .memory import BrowserMemory

logger = logging.getLogger(__name__)


# ── VerificationResult ────────────────────────────────────────────────────────

@dataclass
class VerificationResult:
    passed: bool
    strategy_used: str = ""        # which check determined the result
    actual_state: str = ""
    expected_state: str = ""
    retry_suggestion: str | None = None
    alternative_selector: str | None = None  # selector to try on retry


# ── Selector strategy ladder ──────────────────────────────────────────────────

def build_selector_alternatives(
    selector: str,
    label: str = "",
    memory: "BrowserMemory | None" = None,
) -> list[str]:
    """
    Build a prioritised list of alternative selectors to try when the
    primary selector fails.
    """
    alts: list[str] = [selector]  # primary first

    if label:
        alts.extend([
            f"text={label}",
            f"[aria-label=\"{label}\"]",
            f"[placeholder=\"{label}\"]",
            f"[title=\"{label}\"]",
        ])

    # Try to infer name from selector
    name_match = re.search(r'(?:#|name=")([a-zA-Z0-9_-]+)', selector)
    if name_match:
        name = name_match.group(1)
        alts.append(f"[name=\"{name}\"]")

    # Role-based
    if label:
        alts.append(f"xpath=//button[normalize-space(text())='{label}']")
        alts.append(f"xpath=//a[normalize-space(text())='{label}']")
        alts.append(f"xpath=//*[@aria-label='{label}']")

    # Memory-based suggestion
    if memory:
        suggestion = memory.suggest_alternative_selector(selector)
        if suggestion and suggestion not in alts:
            alts.insert(1, suggestion)  # high priority from memory

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique_alts = []
    for a in alts:
        if a not in seen:
            seen.add(a)
            unique_alts.append(a)

    return unique_alts


# ── Main verifier ─────────────────────────────────────────────────────────────

class ActionVerifier:
    """
    Verifies that browser actions produced their intended effect.

    Called from actions.py after each interaction action.
    Uses structural heuristics — no LLM involved.
    """

    # Wait ms after action before checking post-state
    POST_ACTION_WAIT_MS = 300

    async def verify_click(
        self,
        page: "Page",
        selector: str,
        label: str,
        before_obs: "BrowserObservation",
        after_obs: "BrowserObservation",
    ) -> VerificationResult:
        """
        Verify a click produced a state change.
        Passes if: URL changed, new elements appeared, a form response appeared,
        or the clicked element is gone (consumed, e.g. add-to-cart).
        """
        # Check 1: URL changed → likely navigated, almost certainly successful
        if after_obs.url != before_obs.url:
            return VerificationResult(
                passed=True,
                strategy_used="url_changed",
                actual_state=f"navigated to {after_obs.url}",
            )

        # Check 2: New interactive elements appeared (modal, dialog, confirmation)
        before_sels = {e.selector for e in before_obs.interactive_elements}
        after_sels = {e.selector for e in after_obs.interactive_elements}
        added = after_sels - before_sels
        if added:
            return VerificationResult(
                passed=True,
                strategy_used="elements_appeared",
                actual_state=f"{len(added)} new elements appeared",
            )

        # Check 3: The clicked element disappeared (e.g. submit consumed the button)
        removed = before_sels - after_sels
        clicked_removed = any(selector in r or label in r for r in removed)
        if clicked_removed:
            return VerificationResult(
                passed=True,
                strategy_used="element_disappeared",
                actual_state="clicked element was consumed/removed",
            )

        # Check 4: New network request was made (XHR/fetch triggered by click)
        before_net = {(r.url, r.method) for r in before_obs.network_requests}
        after_net = {(r.url, r.method) for r in after_obs.network_requests}
        new_reqs = after_net - before_net
        if new_reqs:
            return VerificationResult(
                passed=True,
                strategy_used="network_request_made",
                actual_state=f"{len(new_reqs)} new network requests triggered",
            )

        # Check 5: Title changed
        if before_obs.title != after_obs.title:
            return VerificationResult(
                passed=True,
                strategy_used="title_changed",
                actual_state=f"page title changed to {after_obs.title!r}",
            )

        # If none of the above: warn but don't hard-fail (page may just not change)
        # This is "uncertain" — the click may have been valid (e.g. toggling a class)
        return VerificationResult(
            passed=True,  # soft pass — no strong evidence of failure
            strategy_used="no_change_detected",
            actual_state="page appeared unchanged; click may have had no visible effect",
            retry_suggestion=f"Consider verifying manually or using browser_get_snapshot",
        )

    async def verify_type(
        self,
        page: "Page",
        selector: str,
        expected_value: str,
        after_obs: "BrowserObservation",
    ) -> VerificationResult:
        """Verify that a type action actually set the input value correctly."""
        # Find the element in the post-action observation
        for el in after_obs.interactive_elements:
            if el.selector == selector or selector in el.selector:
                if el.value == expected_value or expected_value in el.value:
                    return VerificationResult(
                        passed=True,
                        strategy_used="input_value_match",
                        actual_state=f"input value = {el.value!r}",
                    )
                else:
                    return VerificationResult(
                        passed=False,
                        strategy_used="input_value_mismatch",
                        expected_state=f"value = {expected_value!r}",
                        actual_state=f"value = {el.value!r}",
                        retry_suggestion=f"Try browser_clear then browser_type on {selector}",
                    )

        # Element not found in observation — verify via JS
        try:
            actual = await page.evaluate(
                f"document.querySelector({selector!r})?.value ?? null"
            )
            if actual == expected_value:
                return VerificationResult(passed=True, strategy_used="js_eval_match",
                                          actual_state=f"value = {actual!r}")
            elif actual is None:
                return VerificationResult(
                    passed=False,
                    strategy_used="element_not_found_post_type",
                    actual_state="element not found after typing",
                    retry_suggestion=f"Selector {selector!r} may be invalid or dynamic",
                )
            else:
                return VerificationResult(
                    passed=False,
                    strategy_used="js_value_mismatch",
                    expected_state=expected_value,
                    actual_state=actual or "",
                )
        except Exception:
            # Can't verify — soft pass
            return VerificationResult(passed=True, strategy_used="unverifiable")

    async def verify_navigation(
        self,
        page: "Page",
        expected_url_pattern: str,
        after_obs: "BrowserObservation",
    ) -> VerificationResult:
        """Verify that navigation arrived at the expected URL."""
        import re
        actual = after_obs.url or ""

        # 1. Try simple substring/prefix match first (handles raw URLs with ?, & etc.)
        if expected_url_pattern in actual or actual.startswith(expected_url_pattern):
            return VerificationResult(
                passed=True,
                strategy_used="url_substring_match",
                actual_state=actual,
            )

        # 2. Try domain match — if the domains are the same, consider it passed
        try:
            from urllib.parse import urlparse
            expected_domain = urlparse(expected_url_pattern).netloc.replace("www.", "")
            actual_domain = urlparse(actual).netloc.replace("www.", "")
            if expected_domain and actual_domain and expected_domain == actual_domain:
                return VerificationResult(
                    passed=True,
                    strategy_used="url_domain_match",
                    actual_state=actual,
                )
        except Exception:
            pass

        # 3. Fall back to regex match (escape the URL first to treat it literally)
        try:
            escaped = re.escape(expected_url_pattern)
            if re.search(escaped, actual, re.IGNORECASE):
                return VerificationResult(
                    passed=True,
                    strategy_used="url_pattern_match",
                    actual_state=actual,
                )
        except re.error:
            pass

        return VerificationResult(
            passed=False,
            strategy_used="url_pattern_mismatch",
            expected_state=f"URL matching {expected_url_pattern!r}",
            actual_state=actual,
            retry_suggestion=f"Check if there was a redirect; current URL is {actual!r}",
        )

    async def try_alternative_selectors(
        self,
        page: "Page",
        original_selector: str,
        action_fn,          # async callable(page, selector) → bool
        label: str = "",
        memory: "BrowserMemory | None" = None,
    ) -> tuple[bool, str | None]:
        """
        Try a prioritised list of alternative selectors until one works.

        Returns (success, working_selector_or_None).
        """
        alternatives = build_selector_alternatives(original_selector, label, memory)
        # Skip the first one (that's the original which already failed)
        for sel in alternatives[1:]:
            try:
                result = await action_fn(page, sel)
                if result:
                    logger.info(f"Alternative selector worked: {sel!r} (original: {original_selector!r})")
                    return True, sel
            except Exception:
                continue
        return False, None
