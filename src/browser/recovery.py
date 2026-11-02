"""
Recovery Engine — automatic recovery from common browser failure modes.

Handles the following without involving the LLM whenever possible:

  1. Modal / cookie banners — auto-dismiss
  2. Session expiry — detect redirect to login, update world model
  3. Stale element — wait + retry with alternative selector
  4. Unexpected navigation — warn the agent without crashing
  5. CAPTCHA detected — surface structured result (never silently retry)
  6. Alert dialogs — auto-accept or dismiss
  7. Overlay / spinner — wait for it to disappear

Each recovery is attempted once; if it fails the structured RecoveryResult
tells the agent exactly what happened and what to do next.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from playwright.async_api import Page
    from .structured_obs import BrowserObservation
    from .memory import BrowserMemory
    from .world_model import WorldModel

logger = logging.getLogger(__name__)


# ── Modal / banner dismiss patterns ──────────────────────────────────────────

_DISMISS_SELECTORS = [
    # Cookie banners
    "button[id*='accept']", "button[id*='cookie']", "button[id*='consent']",
    "button[class*='accept']", "button[class*='cookie']",
    "[aria-label*='Accept']", "[aria-label*='Dismiss']",
    # Generic modals — primary button first, then close
    "button[class*='close']", "[aria-label='Close']", "button.modal-close",
    "[data-dismiss='modal']", ".modal-backdrop", "#modal-close",
    # Overlays
    "button[class*='overlay-close']", ".lightbox-close",
]

_SPINNER_SELECTORS = [
    ".spinner", ".loading", "[class*='loading']", "[class*='spinner']",
    "[aria-label='Loading']", ".sk-circle", ".lds-ring",
]

_SESSION_EXPIRED_PATTERNS = [
    "/login", "/signin", "/sign-in", "/auth/login", "/session/new",
    "session expired", "your session has expired", "please log in again",
]

_STALE_ELEMENT_ERRORS = [
    "element is not attached to the dom",
    "stale element reference",
    "detached",
    "cannot find",
]


# ── RecoveryResult ────────────────────────────────────────────────────────────

@dataclass
class RecoveryResult:
    recovered: bool = False
    issue_type: str = ""      # "modal_dismissed", "session_expired", "stale_element", etc.
    action_taken: str = ""    # human-readable description
    new_obs: "BrowserObservation | None" = None
    agent_message: str = ""   # message to surface in the observation if not recovered


# ── RecoveryEngine ────────────────────────────────────────────────────────────

class RecoveryEngine:
    """
    Runs after every browser action to detect and silently fix common problems.

    Call `check_and_recover(page, obs, ...)` — it returns a RecoveryResult
    indicating what (if anything) was fixed. The caller decides whether to
    surface the result to the agent.
    """

    async def check_and_recover(
        self,
        page: "Page",
        obs: "BrowserObservation",
        memory: "BrowserMemory",
        world_model: "WorldModel",
        context_id: str = "default",
    ) -> RecoveryResult:
        """
        Run all recovery checks in priority order.
        Returns the first successful recovery, or a no-op result.
        """
        # Priority 1: CAPTCHA — always surface, never silently retry
        if obs.bot_detection.detected:
            return RecoveryResult(
                recovered=False,
                issue_type="captcha",
                action_taken="CAPTCHA detected — cannot auto-recover",
                agent_message=(
                    f"⚠ Bot-wall detected ({obs.bot_detection.detection_type}). "
                    f"Suggested action: {obs.bot_detection.suggested_action}"
                ),
            )

        # Priority 2: Alert dialogs (JS alerts block further interaction)
        r = await self._handle_js_alert(page)
        if r.recovered:
            return r

        # Priority 3: Session expiry
        r = await self._handle_session_expiry(page, obs, world_model)
        if r.recovered or r.issue_type == "session_expired":
            return r

        # Priority 4: Cookie / modal overlay blocking interaction
        r = await self._handle_modal(page, obs)
        if r.recovered:
            return r

        # Priority 5: Loading spinner blocking interaction
        r = await self._handle_spinner(page)
        if r.recovered:
            return r

        # Priority 6: Unexpected navigation
        r = self._handle_unexpected_navigation(obs, memory)
        if r.issue_type:
            return r

        return RecoveryResult(recovered=False, issue_type="none")

    async def recover_stale_element(
        self,
        page: "Page",
        selector: str,
        error: str,
        memory: "BrowserMemory",
    ) -> RecoveryResult:
        """
        Recover from a stale/detached element error.
        Called by actions.py on ElementNotFound / StaleElementReference.
        """
        is_stale = any(p in error.lower() for p in _STALE_ELEMENT_ERRORS)
        if not is_stale:
            return RecoveryResult(recovered=False, issue_type="not_stale")

        # Wait for DOM to settle
        await asyncio.sleep(0.5)

        # Try alternative selector from memory
        alt = memory.suggest_alternative_selector(selector)
        if alt:
            try:
                await page.wait_for_selector(alt, timeout=3000)
                return RecoveryResult(
                    recovered=True,
                    issue_type="stale_element",
                    action_taken=f"Found alternative selector: {alt!r}",
                    agent_message=f"Stale element recovered using {alt!r} instead of {selector!r}",
                )
            except Exception:
                pass

        return RecoveryResult(
            recovered=False,
            issue_type="stale_element",
            action_taken="Could not recover stale element",
            agent_message=(
                f"Element {selector!r} is stale/detached. "
                f"The page may have re-rendered. Call browser_get_snapshot for current state."
            ),
        )

    # ── Internal handlers ─────────────────────────────────────────────────────

    async def _handle_js_alert(self, page: "Page") -> RecoveryResult:
        """Accept any pending JS alert/confirm dialogs."""
        try:
            # Check for pending dialogs by listening briefly
            dialog_handled = {"yes": False}

            async def on_dialog(dialog: Any) -> None:
                try:
                    dialog_handled["yes"] = True
                    await dialog.accept()
                except Exception:
                    pass

            page.on("dialog", on_dialog)
            await asyncio.sleep(0.2)
            page.remove_listener("dialog", on_dialog)

            if dialog_handled["yes"]:
                return RecoveryResult(
                    recovered=True,
                    issue_type="js_alert",
                    action_taken="Auto-accepted JS alert/confirm dialog",
                )
        except Exception:
            pass
        return RecoveryResult(recovered=False)

    async def _handle_modal(self, page: "Page", obs: "BrowserObservation") -> RecoveryResult:
        """Try to dismiss modal overlays and cookie banners."""
        for sel in _DISMISS_SELECTORS:
            try:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    await el.click(timeout=2000)
                    await asyncio.sleep(0.3)
                    logger.info(f"Recovery: dismissed modal/banner via {sel!r}")
                    return RecoveryResult(
                        recovered=True,
                        issue_type="modal_dismissed",
                        action_taken=f"Dismissed overlay using selector {sel!r}",
                    )
            except Exception:
                continue

        # Also try pressing Escape
        try:
            # Only if a modal role is detected in the observation DOM
            if "[role=dialog]" in obs.dom_snapshot or "modal" in obs.dom_snapshot.lower():
                await page.keyboard.press("Escape")
                await asyncio.sleep(0.3)
                return RecoveryResult(
                    recovered=True,
                    issue_type="modal_dismissed",
                    action_taken="Dismissed modal with Escape key",
                )
        except Exception:
            pass

        return RecoveryResult(recovered=False)

    async def _handle_spinner(self, page: "Page") -> RecoveryResult:
        """Wait for loading spinners to disappear (up to 5s)."""
        for sel in _SPINNER_SELECTORS:
            try:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    await page.wait_for_selector(sel, state="hidden", timeout=5000)
                    logger.info(f"Recovery: waited for spinner {sel!r} to disappear")
                    return RecoveryResult(
                        recovered=True,
                        issue_type="spinner_cleared",
                        action_taken=f"Waited for loading spinner to disappear ({sel!r})",
                    )
            except Exception:
                continue
        return RecoveryResult(recovered=False)

    async def _handle_session_expiry(
        self,
        page: "Page",
        obs: "BrowserObservation",
        world_model: "WorldModel",
    ) -> RecoveryResult:
        """Detect session expiry / redirect to login page."""
        url_lower = obs.url.lower()
        title_lower = obs.title.lower()
        dom_lower = obs.dom_snapshot.lower()

        is_session_expired = any(
            p in url_lower or p in title_lower or p in dom_lower
            for p in _SESSION_EXPIRED_PATTERNS
        )

        if not is_session_expired:
            return RecoveryResult(recovered=False)

        was_logged_in = world_model.get_value("auth_status") == "logged_in"
        world_model.assert_fact("auth_status", "logged_out", source_url=obs.url)
        world_model.retract_fact("session_token")

        if was_logged_in:
            return RecoveryResult(
                recovered=False,   # agent must handle re-auth
                issue_type="session_expired",
                action_taken="Updated world model: auth_status → logged_out",
                agent_message=(
                    "⚠ Session expired — redirected to login page. "
                    "World model updated. Use browser_load_session to restore "
                    "a saved session, or navigate to login page and authenticate."
                ),
            )
        return RecoveryResult(recovered=False)

    def _handle_unexpected_navigation(
        self,
        obs: "BrowserObservation",
        memory: "BrowserMemory",
    ) -> RecoveryResult:
        """Detect if we navigated to a completely unexpected URL."""
        current_page = memory.current_page()
        if not current_page or not obs.url:
            return RecoveryResult(recovered=False)

        # Check if the URL changed drastically (different domain)
        try:
            from urllib.parse import urlparse
            prev_domain = urlparse(current_page.url).netloc
            curr_domain = urlparse(obs.url).netloc
            if prev_domain and curr_domain and prev_domain != curr_domain:
                return RecoveryResult(
                    recovered=False,
                    issue_type="unexpected_navigation",
                    action_taken="",
                    agent_message=(
                        f"⚠ Unexpected cross-domain navigation: "
                        f"{prev_domain} → {curr_domain}. "
                        "You may have followed an external link unintentionally."
                    ),
                )
        except Exception:
            pass
        return RecoveryResult(recovered=False)
