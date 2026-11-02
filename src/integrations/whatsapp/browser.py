"""
Julius WhatsApp Integration — Browser Adapter.

Manages a single persistent Chromium instance connected to WhatsApp Web.
Handles QR login, session persistence, login detection, and centralized
DOM selectors.

Runs dedicated browser automation for WhatsApp Web transport in an isolated
browser profile at ~/.julius/whatsapp_profile/.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

WHATSAPP_WEB_URL = "https://web.whatsapp.com"


class WhatsAppSelectors:
    """
    Centralized DOM selectors for WhatsApp Web.

    All selectors are kept here so that when WhatsApp updates its UI,
    only this class needs to be updated. Prefer accessible roles,
    data attributes, and aria labels over fragile class names.
    """

    # ── Login / QR ────────────────────────────────────────────────
    QR_CANVAS = 'canvas[aria-label="Scan this QR code to link a device!"]'
    QR_CANVAS_FALLBACK = "div[data-ref] canvas"
    QR_CONTAINER = "div._akau"  # QR code container wrapper
    LANDING_PAGE = '[data-testid="intro-md-beta-text"]'

    # ── Main app (logged in) ─────────────────────────────────────
    SIDE_PANEL = "#pane-side"
    CHAT_LIST = '[aria-label="Chat list"]'
    SEARCH_INPUT = 'input[data-tab="3"]'
    SEARCH_INPUT_FALLBACK = '[data-testid="chat-list-search"], div[contenteditable="true"][data-tab="3"]'

    # ── Chat pane ─────────────────────────────────────────────────
    CONVERSATION_HEADER = "header._amid"
    CHAT_TITLE = '[data-testid="conversation-info-header-chat-title"]'
    CHAT_TITLE_FALLBACK = "header span[title]"
    MESSAGE_LIST = '[data-testid="conversation-panel-messages"]'
    MESSAGE_LIST_FALLBACK = 'div[role="application"]'

    # ── Individual messages ───────────────────────────────────────
    MESSAGE_ROW = 'div.message-in, div.message-out, div[role="row"], div[data-testid="msg-container"]'
    MESSAGE_ROW_FALLBACK = "div.message-in, div.message-out"
    MESSAGE_TEXT = "span.selectable-text, span._11JPr, div.copyable-text"
    MESSAGE_TEXT_FALLBACK = 'span[dir="ltr"]'
    MESSAGE_TIMESTAMP = '[data-testid="msg-meta"] span'
    MESSAGE_SENDER = "span._ahxt"  # group chat sender name
    MESSAGE_SENDER_FALLBACK = 'span[data-testid="msg-author"]'
    QUOTED_MESSAGE = '[data-testid="quoted-message"]'
    MESSAGE_OUT = "div.message-out"
    MESSAGE_IN = "div.message-in"

    # ── Composer ──────────────────────────────────────────────────
    COMPOSE_BOX = '[data-testid="conversation-compose-box-input"]'
    COMPOSE_BOX_FALLBACK = 'div[contenteditable="true"][data-tab="10"]'
    SEND_BUTTON = '[data-testid="compose-btn-send"]'
    SEND_BUTTON_FALLBACK = 'button[aria-label="Send"]'

    # ── Unread indicators ─────────────────────────────────────────
    UNREAD_BADGE = 'span[data-testid="icon-unread-count"]'
    UNREAD_BADGE_FALLBACK = "span.aumms1qt"

    # ── Media indicators ──────────────────────────────────────────
    MEDIA_IMAGE = '[data-testid="media-url-provider"]'
    MEDIA_VOICE = '[data-testid="audio-play"]'
    MEDIA_DOCUMENT = '[data-testid="document-thumb"]'


class WhatsAppBrowserAdapter:
    """
    Manages a persistent Chromium browser instance for WhatsApp Web.

    Features:
    - Dedicated profile at ~/.julius/whatsapp_profile/ (isolated from all other subsystems)
    - PID lock to prevent duplicate sessions
    - QR code extraction for display in Julius UI/TUI
    - Login state detection
    - Graceful shutdown and crash recovery
    """

    def __init__(self, profile_dir: str, headless: bool = True) -> None:
        self._profile_dir = str(Path(profile_dir).expanduser().resolve())
        self._headless = headless
        self._playwright = None
        self._context = None
        self._page = None
        self._is_connected = False
        self._lock_path = Path(self._profile_dir) / ".julius_wa_lock"
        self._start_time: float = 0.0

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    @property
    def page(self):
        return self._page

    @property
    def uptime_seconds(self) -> float:
        if self._start_time == 0:
            return 0.0
        return time.time() - self._start_time

    async def start(self) -> None:
        """Launch Chromium and navigate to WhatsApp Web."""
        from playwright.async_api import async_playwright

        Path(self._profile_dir).mkdir(parents=True, exist_ok=True)

        # Ensure permissions on profile directory
        try:
            os.chmod(self._profile_dir, 0o700)
        except OSError:
            pass

        # Acquire process lock
        self._acquire_lock()

        # Kill any orphaned browser processes using this profile
        self._kill_orphans()

        # Clean stale lock files
        self._clean_stale_locks()

        logger.info("Launching WhatsApp browser (profile: %s, headless: %s)",
                     self._profile_dir, self._headless)

        browser_args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
        ]
        if self._headless:
            browser_args.append("--start-minimized")

        try:
            self._playwright = await async_playwright().start()
            self._context = await self._playwright.chromium.launch_persistent_context(
                user_data_dir=self._profile_dir,
                headless=self._headless,
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 900},
                args=browser_args,
                ignore_default_args=["--enable-automation"],
            )

            # Use existing page or create one
            if self._context.pages:
                self._page = self._context.pages[0]
            else:
                self._page = await self._context.new_page()

            # Auto-handle browser dialogs (alert, confirm) to prevent freezes
            self._page.on("dialog", lambda d: asyncio.create_task(d.accept()))
            self._page.on("crash", lambda p: setattr(self, "_is_connected", False))

            # Navigate to WhatsApp Web
            await self._page.goto(WHATSAPP_WEB_URL, wait_until="domcontentloaded")
            self._start_time = time.time()
            logger.info("WhatsApp Web page loaded")
        except Exception as e:
            logger.error("Failed to start WhatsApp browser: %s", e)
            await self.stop()
            raise

    async def stop(self) -> None:
        """Gracefully close the browser and release the lock."""
        self._is_connected = False
        if self._context:
            try:
                await self._context.close()
            except Exception as e:
                logger.debug("Error closing WhatsApp browser context: %s", e)
            self._context = None

        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

        self._page = None
        self._release_lock()
        self._start_time = 0.0
        logger.info("WhatsApp browser stopped")

    async def detect_login_state(self) -> str:
        """
        Detect current WhatsApp Web login state.

        Returns:
            'connected' — logged in and chat list visible
            'qr_required' — QR code visible, needs scanning
            'loading' — page still loading
            'error' — unexpected state
        """
        if not self._page:
            return "error"

        try:
            # Reclaim session and dismiss interruption modals first
            await self.handle_interruption_popups()

            # Check for chat list (logged in)
            side_panel = self._page.locator(WhatsAppSelectors.SIDE_PANEL)
            if await side_panel.count() > 0:
                try:
                    await side_panel.wait_for(state="visible", timeout=2000)
                    self._is_connected = True
                    return "connected"
                except Exception:
                    pass

            # Check for QR code (needs login)
            for qr_sel in [WhatsAppSelectors.QR_CANVAS, WhatsAppSelectors.QR_CANVAS_FALLBACK]:
                qr = self._page.locator(qr_sel)
                if await qr.count() > 0:
                    self._is_connected = False
                    return "qr_required"

            # Check for landing page
            landing = self._page.locator(WhatsAppSelectors.LANDING_PAGE)
            if await landing.count() > 0:
                self._is_connected = False
                return "qr_required"

            return "loading"
        except Exception as e:
            logger.error("Error detecting login state: %s", e)
            return "error"

    async def wait_for_login(self, timeout: int = 120) -> bool:
        """
        Wait for WhatsApp Web to become authenticated.

        Returns True if login succeeded within timeout.
        """
        if not self._page:
            return False

        logger.info("Waiting for WhatsApp Web login (timeout: %ds)...", timeout)
        try:
            await self._page.wait_for_selector(
                WhatsAppSelectors.SIDE_PANEL,
                state="visible",
                timeout=timeout * 1000,
            )
            self._is_connected = True
            logger.info("WhatsApp Web login successful")
            return True
        except Exception:
            logger.warning("WhatsApp Web login timed out after %ds", timeout)
            return False

    async def get_qr_code_base64(self, force_reload: bool = False) -> Optional[str]:
        """
        Extract the QR code as a base64 PNG string for display in UI/TUI.
        Detects if the QR code is expired and automatically clicks the reload button,
        or reloads the page if force_reload is True.

        Returns None if QR is not visible.
        """
        if not self._page:
            return None

        try:
            # If force reload requested, reload the page to get a fresh QR
            if force_reload:
                try:
                    logger.info("Force refreshing WhatsApp Web page for new QR code...")
                    await self._page.reload(wait_until="domcontentloaded")
                    try:
                        await self._page.wait_for_selector(WhatsAppSelectors.QR_CANVAS, timeout=8000)
                    except Exception:
                        await asyncio.sleep(2.0)
                except Exception as e:
                    logger.debug("Page reload error: %s", e)

            # Check if there is an expired/reload button over the QR code
            # WhatsApp Web puts a button or role="button" overlay when QR code expires
            reload_selectors = [
                'button:has-text("reload")',
                'button:has-text("Reload")',
                'span[role="button"]:has-text("reload")',
                'span[role="button"]:has-text("Reload")',
                'div[role="button"]:has-text("reload")',
                'div[data-ref] button',
                'div[data-ref] [role="button"]',
                '[data-testid="qrcode"] button',
            ]
            for r_sel in reload_selectors:
                btn = self._page.locator(r_sel)
                if await btn.count() > 0:
                    try:
                        if await btn.first.is_visible():
                            logger.info("WhatsApp QR expired; clicking reload button for fresh QR...")
                            await btn.first.click()
                            await asyncio.sleep(1.5)
                            break
                    except Exception:
                        pass

            for qr_sel in [WhatsAppSelectors.QR_CANVAS, WhatsAppSelectors.QR_CANVAS_FALLBACK, "canvas"]:
                qr = self._page.locator(qr_sel)
                if await qr.count() > 0:
                    try:
                        await qr.first.wait_for(state="visible", timeout=2000)
                        screenshot_bytes = await qr.first.screenshot()
                        return base64.b64encode(screenshot_bytes).decode("utf-8")
                    except Exception:
                        continue
            return None
        except Exception as e:
            logger.error("Failed to capture QR code: %s", e)
            return None

    # Alias
    get_qr_code_image = get_qr_code_base64

    async def fetch_chat_history(self, chat_name: str, max_scrolls: int = 5) -> list:
        """
        Navigate to a chat and scroll up to load older messages from WhatsApp Web history.
        Returns a list of all visible message dicts after scrolling up.
        """
        if not self._page or not self._is_connected:
            return []

        try:
            # 1. Navigate to chat if not already there
            current = await self.get_current_chat_name()
            if not current or current.lower() != chat_name.lower():
                navigated = await self.navigate_to_chat(chat_name)
                if not navigated:
                    logger.warning("Could not navigate to chat '%s' for history fetch", chat_name)
                    return []
                await asyncio.sleep(1.0)

            # 2. Locate message list container
            container = None
            for sel in [WhatsAppSelectors.MESSAGE_LIST, WhatsAppSelectors.MESSAGE_LIST_FALLBACK]:
                el = self._page.locator(sel)
                if await el.count() > 0:
                    container = el.first
                    break

            # 3. Scroll up progressively to trigger lazy loading of old messages
            if container:
                for s in range(max_scrolls):
                    try:
                        # Scroll to top of message list to trigger loading older messages
                        await container.evaluate("el => el.scrollTop = 0")
                        await asyncio.sleep(0.8)
                    except Exception:
                        break

            # 4. Extract all loaded messages
            return await self.get_visible_messages(limit=100)
        except Exception as e:
            logger.error("Error fetching chat history for '%s': %s", chat_name, e)
            return []

    async def screenshot(self) -> Optional[bytes]:
        """Take a full-page screenshot for diagnostics."""
        if not self._page:
            return None
        try:
            return await self._page.screenshot()
        except Exception as e:
            logger.error("Failed to take screenshot: %s", e)
            return None

    async def handle_interruption_popups(self) -> bool:
        """
        Detect and resolve interruptions, session takeovers, and connection warnings.
        
        Handles:
        1. Session takeover ("Use Here" modal when WhatsApp is opened elsewhere)
        2. Connection retry banners ("Retry now", "Computer not connected", "Trying to reach phone")
        3. Push notification prompts ("Not now", "Later")
        4. Standard modal overlays ("Continue", "OK", "Got it", "Close")
        
        Returns True if any interruption popup was handled/dismissed.
        """
        if not self._page:
            return False

        try:
            if self._page.is_closed():
                return False
        except Exception:
            return False

        handled = False
        try:
            # 1. Session takeover ("Use Here" / "USE HERE")
            takeover_selectors = [
                'button:has-text("Use Here")',
                'button:has-text("USE HERE")',
                'div[role="button"]:has-text("Use Here")',
                'div[role="button"]:has-text("USE HERE")',
                '[data-testid="popup-controls-ok"]',
            ]
            for sel in takeover_selectors:
                btn = self._page.locator(sel)
                if await btn.count() > 0 and await btn.first.is_visible():
                    logger.warning("WhatsApp takeover modal detected! Clicking 'Use Here' to reclaim session...")
                    await btn.first.click()
                    await asyncio.sleep(1.0)
                    handled = True
                    break

            # 2. Connection retry / reconnect banners
            retry_selectors = [
                'button:has-text("Retry now")',
                'button:has-text("RETRY NOW")',
                'span:has-text("Retry now")',
                'span:has-text("Click to reload")',
                'button:has-text("Reconnect")',
                'button:has-text("Reload WhatsApp")',
            ]
            for sel in retry_selectors:
                btn = self._page.locator(sel)
                if await btn.count() > 0 and await btn.first.is_visible():
                    logger.warning("WhatsApp connection retry banner detected! Clicking 'Retry now'...")
                    await btn.first.click()
                    await asyncio.sleep(1.0)
                    handled = True
                    break

            # 3. Notification prompts ("Turn on desktop notifications" -> "Not now")
            notif_selectors = [
                'button:has-text("Not now")',
                'button:has-text("NOT NOW")',
                'button:has-text("Later")',
                'div[role="dialog"] button:has-text("Not now")',
            ]
            for sel in notif_selectors:
                btn = self._page.locator(sel)
                if await btn.count() > 0 and await btn.first.is_visible():
                    logger.info("Dismissing notification prompt ('Not now')...")
                    await btn.first.click()
                    await asyncio.sleep(0.3)
                    handled = True
                    break

            # 4. Generic dialog buttons
            dialog_selectors = [
                'button:has-text("Continue")',
                'button:has-text("Got it")',
                'button:has-text("OK")',
                'div[role="dialog"] button[aria-label="Close"]',
                'button[aria-label="Close"]',
            ]
            for sel in dialog_selectors:
                btn = self._page.locator(sel)
                if await btn.count() > 0 and await btn.first.is_visible():
                    await btn.first.click()
                    await asyncio.sleep(0.3)
                    handled = True
                    break

        except Exception as e:
            logger.debug("Error while checking interruption popups: %s", e)

        return handled

    async def dismiss_modals(self) -> None:
        """Dismiss any onboarding, feature update, takeover, or notification popups."""
        await self.handle_interruption_popups()

    async def clear_search(self) -> None:
        """Clear search query in the left pane without closing open chats."""
        if not self._page:
            return
        try:
            # 1. Click cancel/close buttons if visible (including WhatsApp's new "End icon button")
            cancel_btns = self._page.locator(
                'button[aria-label="End icon button"], button[aria-label="Cancel search"], '
                'button[aria-label="Clear search"], span[data-icon="x-alt"], span[data-icon="x"], '
                '[data-testid="search-cancel"], button:has(span[data-icon="x-alt"]), '
                'button:has(span[data-icon="x"])'
            )
            if await cancel_btns.count() > 0 and await cancel_btns.first.is_visible():
                await cancel_btns.first.click()
                await asyncio.sleep(0.1)

            # 2. Reset input value in DOM and dispatch input event
            await self._page.evaluate("""() => {
                const inputs = document.querySelectorAll('input[data-tab="3"], input[placeholder*="Search"], div[contenteditable="true"][data-tab="3"]');
                for (const input of inputs) {
                    if (input.value) {
                        input.value = '';
                        input.dispatchEvent(new Event('input', { bubbles: true }));
                    }
                    if (input.innerText) {
                        input.innerText = '';
                        input.dispatchEvent(new Event('input', { bubbles: true }));
                    }
                }
            }""")

            # 3. Press Escape twice to dismiss any search dropdown
            await self._page.keyboard.press("Escape")
            await asyncio.sleep(0.05)
            await self._page.keyboard.press("Escape")
        except Exception:
            pass

    async def select_unread_tab(self) -> bool:
        """Filter the left pane to display only unread chats."""
        if not self._page or not self._is_connected:
            return False
        try:
            return await self._page.evaluate("""() => {
                const unreadBtn = Array.from(document.querySelectorAll('button')).find(b => {
                    const txt = (b.innerText || '').trim();
                    return txt.startsWith('Unread') || b.id === 'label_item_1';
                });
                if (unreadBtn) {
                    unreadBtn.click();
                    return true;
                }
                return false;
            }""")
        except Exception:
            return False

    async def select_all_tab(self) -> bool:
        """Switch back to displaying all chats in the left pane."""
        if not self._page or not self._is_connected:
            return False
        try:
            return await self._page.evaluate("""() => {
                const allBtn = document.querySelector('button#all-filter') ||
                               Array.from(document.querySelectorAll('button')).find(b => (b.innerText || '').trim() === 'All');
                if (allBtn) {
                    allBtn.click();
                    return true;
                }
                return false;
            }""")
        except Exception:
            return False

    async def get_unread_tab_count(self) -> int:
        """Extract unread count from the Unread tab header (e.g. 'Unread\\n4' -> 4)."""
        if not self._page or not self._is_connected:
            return 0
        try:
            return await self._page.evaluate("""() => {
                const unreadBtn = Array.from(document.querySelectorAll('button')).find(b => {
                    const txt = (b.innerText || '').trim();
                    return txt.startsWith('Unread') || b.id === 'label_item_1';
                });
                if (unreadBtn) {
                    const txt = (unreadBtn.innerText || '').trim();
                    const match = txt.match(/\\d+/);
                    return match ? parseInt(match[0], 10) : 0;
                }
                return 0;
            }""")
        except Exception:
            return 0

    async def navigate_to_chat(self, chat_name: str, jid: Optional[str] = None) -> bool:
        """
        Navigate to a specific chat safely without false positives.
        
        Strategy:
        1. If already open (exact name, canonical peer name, or self-chat match), return True.
        2. Fast path: Direct open via WhatsApp Web internal module (WAWebCmd.Cmd.openChatBottom).
        3. Visible pane-side list: Match ONLY exact title attribute or complete-word match (NEVER message text!).
        4. Search box: Type exact query, match search result ONLY by title attribute with word boundaries.
        """
        if not self._page or not self._is_connected:
            return False

        try:
            await self.dismiss_modals()

            # 1. Check if already open
            current = await self.get_current_chat_name()
            from .config import (
                is_self_chat,
                is_target_peer_chat,
                get_canonical_target_peer_name,
            )
            target_is_self = is_self_chat(chat_name)
            current_is_self = is_self_chat(current or "")

            if target_is_self and current_is_self:
                return True

            if current:
                c_clean = current.lower().strip()
                t_clean = chat_name.lower().strip()
                if c_clean == t_clean:
                    return True
                curr_canonical = get_canonical_target_peer_name(current)
                target_canonical = get_canonical_target_peer_name(chat_name)
                if curr_canonical and target_canonical and curr_canonical == target_canonical:
                    return True

            # 2. Fast-path: Direct open via WhatsApp Web internal bridge (no UI search/typing)
            direct_opened = await self._page.evaluate("""([targetName, targetJid]) => {
                try {
                    if (typeof window.require !== "function") return false;
                    const ChatCol = window.require("WAWebChatCollection")?.ChatCollection;
                    const Cmd = window.require("WAWebCmd")?.Cmd;
                    if (!ChatCol || !ChatCol._models || !Cmd) return false;

                    const tn = (targetName || "").toLowerCase().trim();
                    const chat = ChatCol._models.find(c => {
                        const id = c.id ? (c.id._serialized || c.id) : "";
                        if (targetJid && id === targetJid) return true;
                        const title = (c.formattedTitle || c.name || c.__x_name || "").toLowerCase().trim();
                        return title === tn;
                    });

                    if (chat) {
                        if (typeof Cmd.openChatBottom === "function") {
                            Cmd.openChatBottom({ chat: chat });
                            return true;
                        } else if (typeof Cmd.openChatAt === "function") {
                            Cmd.openChatAt({ chat: chat });
                            return true;
                        }
                    }
                    return false;
                } catch (e) {
                    return false;
                }
            }""", [chat_name, jid or ""])

            if direct_opened:
                await asyncio.sleep(0.3)
                current = await self.get_current_chat_name()
                if current:
                    c_clean = current.lower().strip()
                    t_clean = chat_name.lower().strip()
                    if c_clean == t_clean or (target_is_self and is_self_chat(current)):
                        return True
                    curr_canonical = get_canonical_target_peer_name(current)
                    target_canonical = get_canonical_target_peer_name(chat_name)
                    if curr_canonical and target_canonical and curr_canonical == target_canonical:
                        return True

            # 3. Check if chat is already visible in #pane-side list without searching
            clicked = await self._page.evaluate("""([name, targetJid, isSelf]) => {
                const spans = Array.from(document.querySelectorAll('#pane-side span[title]'));
                const n = (name || "").toLowerCase().trim();
                const nWords = n.split(/\\s+/).filter(w => !['mit', 'the', 'dept', 'it', 'ece'].includes(w) && w.length >= 3);

                const target = spans.find(s => {
                    const t = (s.getAttribute('title') || '').toLowerCase().trim();
                    if (!t) return false;
                    if (isSelf && (t.includes('david julius') || t === 'you' || t === 'message yourself')) return true;
                    if (t === n) return true;
                    const tWords = t.split(/\\s+/);
                    if (nWords.length > 0 && nWords.every(w => tWords.includes(w))) return true;
                    return false;
                });
                if (target) {
                    const row = target.closest('[role="listitem"], [role="row"], [data-testid="cell-frame-container"]') || target;
                    row.dispatchEvent(new MouseEvent('mousedown', {bubbles: true, cancelable: true, view: window}));
                    row.dispatchEvent(new MouseEvent('mouseup', {bubbles: true, cancelable: true, view: window}));
                    row.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true, view: window}));
                    return true;
                }
                return false;
            }""", [chat_name, jid or "", target_is_self])

            if clicked:
                await asyncio.sleep(0.4)
                current = await self.get_current_chat_name()
                if current:
                    c_clean = current.lower().strip()
                    t_clean = chat_name.lower().strip()
                    if c_clean == t_clean or (target_is_self and is_self_chat(current)):
                        return True
                    curr_canonical = get_canonical_target_peer_name(current)
                    target_canonical = get_canonical_target_peer_name(chat_name)
                    if curr_canonical and target_canonical and curr_canonical == target_canonical:
                        return True

            # 4. Fallback: Search box navigation (exact title match ONLY, NEVER match message previews)
            await self.clear_search()
            search_selectors = [
                'input[data-tab="3"]',
                WhatsAppSelectors.SEARCH_INPUT,
                'p.selectable-text[data-tab="3"]',
                '[placeholder="Search or start a new chat"]',
                '[placeholder="Search"]',
                WhatsAppSelectors.SEARCH_INPUT_FALLBACK,
            ]
            search = None
            for sel in search_selectors:
                el = self._page.locator(sel)
                if await el.count() > 0 and await el.first.is_visible():
                    search = el.first
                    await search.click()
                    await asyncio.sleep(0.1)
                    break

            if not search:
                logger.warning("Could not find search input")
                return False

            search_query = "David Julius" if target_is_self else chat_name
            if search_query.startswith("MIT ") and len(search_query) > 4:
                search_query_core = search_query[4:].strip()
            else:
                search_query_core = search_query

            try:
                await search.fill(search_query_core)
            except Exception:
                await search.click()
                await self._page.keyboard.type(search_query_core, delay=15)
            await asyncio.sleep(0.6)

            # Click matching chat result in search list — STRICT TITLE MATCHING ONLY
            clicked_result = await self._page.evaluate("""([targetName, isSelf]) => {
                const rows = Array.from(document.querySelectorAll('#pane-side [role="listitem"], #pane-side [role="row"], #pane-side [data-testid="cell-frame-container"]'));
                const tn = (targetName || '').toLowerCase().trim();
                const tnWords = tn.split(/\\s+/).filter(w => !['mit', 'the', 'dept', 'it', 'ece'].includes(w) && w.length >= 3);

                for (const row of rows) {
                    const titleEl = row.querySelector('span[title]');
                    const title = (titleEl ? titleEl.getAttribute('title') || '' : '').toLowerCase().trim();
                    if (!title) continue;

                    if (isSelf) {
                        if (title.includes('david julius') || title === 'you' || title.includes('(you)')) {
                            row.dispatchEvent(new MouseEvent('mousedown', {bubbles: true, cancelable: true, view: window}));
                            row.dispatchEvent(new MouseEvent('mouseup', {bubbles: true, cancelable: true, view: window}));
                            row.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true, view: window}));
                            return true;
                        }
                    }

                    // Check exact title match
                    if (title === tn) {
                        row.dispatchEvent(new MouseEvent('mousedown', {bubbles: true, cancelable: true, view: window}));
                        row.dispatchEvent(new MouseEvent('mouseup', {bubbles: true, cancelable: true, view: window}));
                        row.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true, view: window}));
                        return true;
                    }

                    // Check whole-word match on title ONLY (never innerText/message body)
                    const titleWords = title.split(/\\s+/);
                    if (tnWords.length > 0 && tnWords.every(w => titleWords.includes(w))) {
                        row.dispatchEvent(new MouseEvent('mousedown', {bubbles: true, cancelable: true, view: window}));
                        row.dispatchEvent(new MouseEvent('mouseup', {bubbles: true, cancelable: true, view: window}));
                        row.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true, view: window}));
                        return true;
                    }
                }
                return false;
            }""", [chat_name, target_is_self])

            if clicked_result:
                await asyncio.sleep(0.4)
                await self.clear_search()
                current = await self.get_current_chat_name()
                if current:
                    c_clean = current.lower().strip()
                    t_clean = chat_name.lower().strip()
                    if c_clean == t_clean or (target_is_self and is_self_chat(current)):
                        return True
                    curr_canonical = get_canonical_target_peer_name(current)
                    target_canonical = get_canonical_target_peer_name(chat_name)
                    if curr_canonical and target_canonical and curr_canonical == target_canonical:
                        return True

            logger.warning("Chat '%s' not found in search results", chat_name)
            await self.clear_search()
            return False
        except Exception as e:
            logger.error("Error navigating to chat '%s': %s", chat_name, e)
            await self.clear_search()
            return False

    async def get_current_chat_name(self) -> Optional[str]:
        """Get the name of the currently open chat."""
        if not self._page:
            return None
        try:
            return await self._page.evaluate("""() => {
                const main = document.querySelector('#main');
                if (!main) return null;
                const header = main.querySelector('header');
                if (!header) return null;

                // Look for span[dir="auto"] in header that contains the actual name
                const spans = header.querySelectorAll('span[dir="auto"]');
                for (const s of spans) {
                    const txt = (s.innerText || '').trim();
                    if (txt && txt.length > 1 && !txt.toLowerCase().includes('click here for contact info')) {
                        return txt;
                    }
                }

                // Check title attribute in header
                const titled = header.querySelector('[title]');
                if (titled) {
                    const title = (titled.getAttribute('title') || '').trim();
                    if (title && title !== 'Profile details' && title.length > 1) return title;
                }

                // Header text fallback
                const lines = header.innerText.split('\\n').map(l => l.trim()).filter(l => l.length > 1 && l !== 'M');
                if (lines.length > 0) return lines[0];

                return null;
            }""")
        except Exception:
            return None

    async def type_and_send(self, text: str, expected_chat: Optional[str] = None) -> bool:
        """
        Type a message into the composer and send it.
        Includes composer verification and retry to guarantee no unsent drafts get stuck.

        Returns True if the message was sent successfully.
        """
        if not self._page or not self._is_connected:
            return False

        try:
            # STRICT SAFETY CHECK: Verify that active chat matches target (with alias/token support)
            if expected_chat:
                current = await self.get_current_chat_name()
                exp_clean = expected_chat.lower().strip()
                cur_clean = (current or "").lower().strip()
                matches = (exp_clean in cur_clean or cur_clean in exp_clean)
                if not matches:
                    from .config import is_self_chat
                    if is_self_chat(expected_chat) and is_self_chat(current or ""):
                        matches = True
                    else:
                        exp_tokens = [t for t in exp_clean.split() if t not in ('mit', 'the', 'dept', 'it', 'ece') and len(t) >= 4]
                        if any(t in cur_clean for t in exp_tokens):
                            matches = True
                if not matches:
                    logger.critical(
                        "SAFETY BLOCK: Refusing to send message intended for '%s' because active chat is '%s'!",
                        expected_chat, current,
                    )
                    return False

            # Find composer box
            composer_selectors = [
                '#main footer div[contenteditable="true"][data-tab="10"]',
                '#main footer div[contenteditable="true"]',
                '#main footer div[role="textbox"]',
                'div[contenteditable="true"][data-tab="10"]',
                '[placeholder="Type a message"]',
                'div[role="textbox"][aria-label="Type a message"]',
                WhatsAppSelectors.COMPOSE_BOX,
                WhatsAppSelectors.COMPOSE_BOX_FALLBACK,
                'footer div[contenteditable="true"]',
            ]
            composer = None
            for sel in composer_selectors:
                el = self._page.locator(sel)
                if await el.count() > 0 and await el.first.is_visible():
                    composer = el.first
                    break

            if not composer:
                logger.error("Could not find WhatsApp composer box")
                return False

            # Clear any existing draft before typing
            existing_text = await self._page.evaluate("""() => {
                const comp = document.querySelector('#main footer div[contenteditable="true"]');
                return comp ? (comp.innerText || '').trim() : '';
            }""")
            if existing_text:
                await composer.click()
                import sys
                await self._page.keyboard.press("Meta+A" if sys.platform == "darwin" else "Control+A")
                await self._page.keyboard.press("Backspace")
                await asyncio.sleep(0.05)

            # Click composer and type text using native keyboard typing (firing keydown, input, keyup for Lexical React state)
            await composer.click()
            await asyncio.sleep(0.05)
            await self._page.keyboard.type(text, delay=0)
            await asyncio.sleep(0.1)

            # Attempt send via Send button or Enter
            send_btn_selectors = (
                'button[aria-label="Send"], span[data-icon="send"], [data-testid="compose-btn-send"], '
                '[data-testid="send"], button:has(span[data-icon="send"]), footer button:has-text("Send")'
            )

            send_clicked = False
            send_btns = self._page.locator(send_btn_selectors)
            if await send_btns.count() > 0 and await send_btns.first.is_visible():
                await send_btns.first.click()
                send_clicked = True
            else:
                await self._page.keyboard.press("Enter")

            # Verification loop: verify composer is empty (retry if text remains)
            is_sent = False
            for retry_idx in range(4):
                await asyncio.sleep(0.2)
                composer_text = await self._page.evaluate("""() => {
                    const comp = document.querySelector('#main footer div[contenteditable="true"]');
                    return comp ? (comp.innerText || '').trim() : '';
                }""")
                if not composer_text or composer_text == "\n":
                    is_sent = True
                    break

                # If text is still in composer, retry clicking send button and Enter
                retry_btns = self._page.locator(send_btn_selectors)
                if await retry_btns.count() > 0 and await retry_btns.first.is_visible():
                    await retry_btns.first.click()
                else:
                    await composer.click()
                    await self._page.keyboard.press("Enter")

            if not is_sent:
                logger.warning("Composer still had text after retries, clearing to avoid stuck draft")
                await self._page.evaluate("""() => {
                    const comp = document.querySelector('#main footer div[contenteditable="true"]');
                    if (comp) {
                        comp.innerText = '';
                        comp.dispatchEvent(new Event('input', { bubbles: true }));
                    }
                }""")
                return False

            return True
        except Exception as e:
            logger.error("Failed to send message: %s", e)
            return False

    async def react_to_message(self, emoji: str) -> bool:
        """
        React to the last incoming message in the active chat using the specified emoji.
        Supported WhatsApp reactions: 👍, ❤️, 😂, 😮, 😢, 🙏
        """
        if not self._page or not self._is_connected:
            return False
        try:
            emoji_clean = emoji.strip()
            # Map common aliases or text to actual reaction emojis
            emoji_map = {
                "👍": "👍", "thumbsup": "👍", "like": "👍", "agree": "👍",
                "❤️": "❤️", "heart": "❤️", "love": "❤️",
                "😂": "😂", "laugh": "😂", "joy": "😂", "lol": "😂", "rofl": "😂",
                "😮": "😮", "wow": "😮", "surprised": "😮", "shock": "😮",
                "😢": "😢", "sad": "😢", "cry": "😢",
                "🙏": "🙏", "pray": "🙏", "thanks": "🙏", "namaste": "🙏",
            }
            target_emoji = emoji_map.get(emoji_clean, emoji_clean)

            opened_menu = await self._page.evaluate("""() => {
                const rows = Array.from(document.querySelectorAll('#main [role="row"], [role="row"]'));
                if (!rows.length) return false;

                // Find last incoming message (not sent by David) or fallback to last row
                let targetRow = null;
                for (let i = rows.length - 1; i >= 0; i--) {
                    const r = rows[i];
                    const isOutgoing = r.querySelector('[data-icon*="check"], [aria-label*="Sent"], [aria-label*="Delivered"]');
                    if (!isOutgoing) {
                        targetRow = r;
                        break;
                    }
                }
                if (!targetRow) targetRow = rows[rows.length - 1];

                const container = targetRow.querySelector('[data-testid="msg-container"]') || targetRow;
                const rect = container.getBoundingClientRect();
                const clientX = rect.left + rect.width / 2;
                const clientY = rect.top + rect.height / 2;
                container.dispatchEvent(new MouseEvent('contextmenu', { bubbles: true, cancelable: true, clientX, clientY }));
                return true;
            }""")

            if not opened_menu:
                return False

            await asyncio.sleep(0.2)

            # Click 'React' item in context menu
            clicked_react = await self._page.evaluate("""() => {
                const items = Array.from(document.querySelectorAll('[role="menuitem"], li, div[tabindex]'));
                const reactItem = items.find(el => (el.innerText || '').trim() === 'React');
                if (!reactItem) return false;
                reactItem.click();
                return true;
            }""")

            if not clicked_react:
                await self._page.keyboard.press("Escape")
                return False

            await asyncio.sleep(0.2)

            # In reaction popup dialog, click matching emoji
            reacted = await self._page.evaluate("""(targetEmoji) => {
                const dialog = document.querySelector('div[role="dialog"]');
                if (!dialog) return false;
                const emojiImg = dialog.querySelector(`img[alt="${targetEmoji}"]`);
                if (emojiImg) {
                    const btn = emojiImg.closest('button') || emojiImg;
                    btn.click();
                    return true;
                }
                return false;
            }""", target_emoji)

            # Close any lingering dialog
            await asyncio.sleep(0.1)
            await self._page.evaluate("""() => {
                const dialog = document.querySelector('div[role="dialog"]');
                if (dialog) {
                    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', code: 'Escape', bubbles: true }));
                }
            }""")
            return bool(reacted)
        except Exception as e:
            logger.error("Failed to react to message: %s", e)
            return False

    async def send_sticker(self, sticker_theme: str = "") -> bool:
        """
        Send a fitting sticker from the WhatsApp sticker drawer to the active chat.
        """
        if not self._page or not self._is_connected:
            return False
        try:
            # 1. Open media drawer if not open
            opened = await self._page.evaluate("""() => {
                const btn = document.querySelector('button[aria-label="Emojis, GIFs, Stickers"], [aria-label="Emojis, GIFs, Stickers"]');
                if (btn) {
                    btn.click();
                    return true;
                }
                return false;
            }""")
            if not opened:
                return False

            await asyncio.sleep(0.25)

            # 2. Click Stickers tab
            await self._page.evaluate("""() => {
                const tab = document.querySelector('[data-testid="expressions-btn-sticker"], button[aria-label="Stickers selector"], [aria-label="Stickers selector"]');
                if (tab) tab.click();
            }""")

            await asyncio.sleep(0.35)

            # 3. Click sticker item with full mouse events
            sent = await self._page.evaluate("""() => {
                const img = document.querySelector('[data-testid="sticker-item"] img, img[alt*="Sticker"]');
                if (!img) return false;
                img.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true }));
                img.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true }));
                img.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
                return true;
            }""")

            await asyncio.sleep(0.3)

            # 4. Close media drawer by clicking composer / escape
            await self._page.evaluate("""() => {
                const comp = document.querySelector('footer div[contenteditable="true"]');
                if (comp) comp.click();
                window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', code: 'Escape', bubbles: true }));
            }""")
            return bool(sent)
        except Exception as e:
            logger.error("Failed to send sticker: %s", e)
            await self.dismiss_modals()
            return False

    async def send_gif(self, search_query: str) -> bool:
        """
        Search and send a fitting GIF via GIPHY on WhatsApp Web.
        """
        if not self._page or not self._is_connected:
            return False
        try:
            # 1. Open media drawer
            opened = await self._page.evaluate("""() => {
                const btn = document.querySelector('button[aria-label="Emojis, GIFs, Stickers"], [aria-label="Emojis, GIFs, Stickers"]');
                if (btn) {
                    btn.click();
                    return true;
                }
                return false;
            }""")
            if not opened:
                return False

            await asyncio.sleep(0.2)

            # 2. Click Gifs selector tab
            await self._page.evaluate("""() => {
                const tab = document.querySelector('[data-testid="expressions-btn-gif"], button[aria-label="Gifs selector"], [aria-label="Gifs selector"]');
                if (tab) tab.click();
            }""")

            await asyncio.sleep(0.25)

            # 3. Enter search query in GIPHY input
            typed = await self._page.evaluate("""(query) => {
                const input = document.querySelector('input[aria-label="Search GIFs via GIPHY"]');
                if (!input) return false;
                input.focus();
                input.value = query;
                input.dispatchEvent(new Event('input', { bubbles: true }));
                input.dispatchEvent(new Event('change', { bubbles: true }));
                return true;
            }""", search_query)

            if not typed:
                await self.dismiss_modals()
                return False

            # Wait for GIPHY results to populate
            await asyncio.sleep(0.6)

            # 4. Click the top GIF result
            sent = await self._page.evaluate("""() => {
                const gifs = Array.from(document.querySelectorAll('div[data-testid*="gif"], img[src*="giphy"], img[src*="tenor"]'));
                if (!gifs.length) return false;
                gifs[0].click();
                return true;
            }""")

            await asyncio.sleep(0.35)

            # 5. Send button in media preview (if present)
            await self._page.evaluate("""() => {
                const sendBtn = document.querySelector('button[aria-label="Send"], span[data-icon="send"]');
                if (sendBtn) {
                    const btn = sendBtn.closest('button') || sendBtn;
                    btn.click();
                }
                const comp = document.querySelector('footer div[contenteditable="true"]');
                if (comp) comp.click();
                window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', code: 'Escape', bubbles: true }));
            }""")
            return bool(sent)
        except Exception as e:
            logger.error("Failed to send GIF: %s", e)
            await self.dismiss_modals()
            return False

    async def get_active_unreplied_chats(self, max_recent_seconds: int = 86400) -> list:
        """
        Directly inspect WhatsApp Web's internal WAWebChatCollection in memory.
        Finds all 1-on-1 chats where the latest message is an incoming unreplied message from the contact.
        
        STRICT: Skips ALL group chats (isGroup=true or @g.us JID).
        Includes is_group flag in results for downstream verification.
        Supports self-chat ("Message yourself" / "David Julius") for AI personal notes & chat.
        
        Runs in ~10ms across all 270+ contacts without scrolling or switching UI chats!
        """
        if not self._page or not self._is_connected:
            return []
        try:
            return await self._page.evaluate("""(maxRecentSec) => {
                try {
                    if (typeof window.require !== "function") return [];
                    const ChatCol = window.require("WAWebChatCollection")?.ChatCollection;
                    if (!ChatCol || !ChatCol._models) return [];
                    
                    const now = Math.floor(Date.now() / 1000);
                    const cutoff = maxRecentSec > 0 ? (now - maxRecentSec) : 0;
                    const results = [];

                    for (const c of ChatCol._models) {
                        const id = c.id ? (c.id._serialized || c.id) : "";
                        if (!id) continue;
                        
                        // STRICT GROUP DETECTION: Use WhatsApp's internal isGroup property
                        // and JID suffix @g.us (definitive group indicators)
                        const isGroup = Boolean(
                            c.isGroup ||
                            (typeof id === "string" && id.endsWith("@g.us")) ||
                            c.groupMetadata ||
                            (c.id && c.id.server === "g.us")
                        );
                        
                        // STRICT: Skip ALL group chats unconditionally
                        if (isGroup) continue;
                        
                        const msgs = c.msgs ? (c.msgs._models || c.msgs.models) : [];
                        if (!msgs || msgs.length === 0) continue;
                        
                        const last = msgs[msgs.length - 1];
                        if (!last) continue;
                        
                        const chatTitle = c.formattedTitle || c.name || c.__x_name || id;
                        const cleanTitle = (chatTitle || "").toLowerCase().trim();
                        const isSelf = Boolean(
                            c.isSelf ||
                            c.__x_isSelf ||
                            (c.contact && c.contact.isMe) ||
                            (c.id && c.id.server === "lid" && cleanTitle.includes("david julius")) ||
                            ["david julius", "david (you)", "david(you)", "you", "message yourself"].some(n => cleanTitle.includes(n))
                        );

                        const fromMe = Boolean(last.id && last.id.fromMe);
                        if (fromMe && !isSelf) continue; // We already replied to this chat (allow self-chat)

                        // For self-chat, skip if the last message was already a bot reply
                        if (isSelf) {
                            const lastBody = (last.body || last.__x_body || "").trim();
                            if (lastBody.startsWith("🤖") || lastBody.startsWith("✅") || lastBody.startsWith("❓") || lastBody.startsWith("👍")) {
                                continue;
                            }
                        }
                        
                        const t = last.t || last.__x_t || 0;
                        if (cutoff > 0 && t < cutoff) continue; // Message too old
                        
                        // Extract recent conversation history for deep context
                        const historySlice = msgs.slice(-15);
                        const recentTurns = historySlice.map(m => {
                            const isOut = Boolean(m.id && m.id.fromMe);
                            const text = m.body || m.__x_body || (m.caption ? m.caption : (m.type === "image" ? "[Image]" : (m.type === "sticker" ? "[Sticker]" : "")));
                            return {
                                id: m.id ? (m.id._serialized || m.id.id || String(m.id)) : "",
                                sender: isOut ? "David" : chatTitle,
                                text: text,
                                timestamp: m.t || m.__x_t || now,
                                is_from_me: isOut,
                                media_type: m.type || "text"
                            };
                        });

                        const lastText = last.body || last.__x_body || (last.caption ? last.caption : (last.type === "image" ? "[Image]" : (last.type === "sticker" ? "[Sticker]" : "")));
                        if (!lastText && !last.type) continue;

                        results.push({
                            chat_id: id,
                            chat_name: chatTitle,
                            is_group: false,
                            unread_count: c.__x_unreadCount || 0,
                            last_message: {
                                id: last.id ? (last.id._serialized || last.id.id || String(last.id)) : "",
                                sender: chatTitle,
                                text: lastText,
                                timestamp: t || now,
                                is_from_me: fromMe,
                                media_type: last.type || "text"
                            },
                            recent_messages: recentTurns
                        });
                    }
                    return results;
                } catch (e) {
                    return [];
                }
            }""", max_recent_seconds)
        except Exception as e:
            logger.debug("get_active_unreplied_chats direct evaluation error: %s", e)
            return []

    async def send_direct_message(self, chat_id_or_name: str, text: str) -> bool:
        """
        Send a text message directly to any contact via WhatsApp Web internal WAWebSendTextMsgChatAction.
        Executes in < 30ms WITHOUT navigating or altering the currently active chat in the browser UI!
        """
        if not self._page or not self._is_connected or not text:
            return False
        try:
            result = await self._page.evaluate("""async ([target, msgText]) => {
                try {
                    if (typeof window.require !== "function") return { success: false, reason: "no require" };
                    const ChatCol = window.require("WAWebChatCollection")?.ChatCollection;
                    const sendTextMod = window.require("WAWebSendTextMsgChatAction");
                    if (!ChatCol || !sendTextMod || typeof sendTextMod.sendTextMsgToChat !== "function") {
                        return { success: false, reason: "modules missing" };
                    }
                    
                    const tClean = (target || "").toLowerCase().trim();
                    // Match by serialized ID, formattedTitle, or name
                    const chat = ChatCol._models.find(c => {
                        const id = c.id ? (c.id._serialized || c.id) : "";
                        if (id === target) return true;
                        const title = (c.formattedTitle || c.name || "").toLowerCase().trim();
                        if (title === tClean) return true;
                        if (tClean.length > 3 && (title.includes(tClean) || tClean.includes(title))) return true;
                        return false;
                    });
                    
                    if (!chat) return { success: false, reason: "chat not found" };
                    
                    const res = await sendTextMod.sendTextMsgToChat(chat, msgText);
                    const ok = Boolean(res && res.messageSendResult === "OK");
                    return { success: ok, res: res ? res.messageSendResult : "empty" };
                } catch (e) {
                    return { success: false, error: e.toString() };
                }
            }""", [chat_id_or_name, text])
            
            if isinstance(result, dict) and result.get("success"):
                logger.info("Direct message sent to '%s' via WhatsApp Web internal bridge", chat_id_or_name)
                return True
            else:
                logger.debug("Direct send fallback needed for '%s': %s", chat_id_or_name, result)
                return False
        except Exception as e:
            logger.debug("Direct send error for '%s': %s", chat_id_or_name, e)
            return False

    async def send_document(
        self, chat_name: str, file_path: str, caption: str = "", jid: str = ""
    ) -> bool:
        """
        Send a document/PDF to a chat via WhatsApp Web's file attachment input.
        """
        if not self._page or not self._is_connected:
            return False

        path_obj = Path(file_path)
        if not path_obj.exists():
            logger.error("Document file not found: %s", file_path)
            return False

        try:
            # 1. Navigate to chat
            navigated = await self.navigate_to_chat(chat_name, jid=jid)
            if not navigated:
                logger.error("Failed to navigate to '%s' for document sending", chat_name)
                return False

            await asyncio.sleep(0.5)

            # 2. Attach Document via expect_file_chooser
            attach_btn = self._page.locator(
                'button[aria-label="Attach"], button[title="Attach"], div[aria-label="Attach"], span[data-icon="plus"], span[data-icon="attach-menu-plus"]'
            ).first
            if await attach_btn.count() > 0:
                is_open = (await attach_btn.get_attribute("aria-expanded")) == "true"
                if not is_open:
                    await attach_btn.click()
                    await asyncio.sleep(0.5)

            doc_btn = self._page.locator(
                'button[aria-label="Document"], button:has-text("Document"), li:has-text("Document"), div[role="button"]:has-text("Document")'
            ).first

            attached = False
            if await doc_btn.count() > 0 and await doc_btn.is_visible():
                try:
                    async with self._page.expect_file_chooser(timeout=8000) as fc_info:
                        await doc_btn.click()
                    file_chooser = await fc_info.value
                    await file_chooser.set_files(str(path_obj.resolve()))
                    logger.info("Attached document file '%s' via file chooser", path_obj.name)
                    attached = True
                    await asyncio.sleep(1.5)
                except Exception as e:
                    logger.warning("expect_file_chooser failed for document: %s", e)

            if not attached:
                # Fallback to direct input
                inputs = self._page.locator('input[type="file"]')
                if await inputs.count() > 0:
                    await inputs.first.set_input_files(str(path_obj.resolve()))
                    attached = True
                    await asyncio.sleep(1.5)

            if not attached:
                logger.error("No suitable method found to attach document '%s'", path_obj.name)
                return False

            # 4. Wait for media preview / send button
            send_btn = self._page.locator(
                'span[data-icon="send"], div[role="button"][aria-label="Send"], button[aria-label="Send"], div[data-testid="send"], span[data-icon="wds-ic-send-filled"]'
            ).first
            try:
                await send_btn.wait_for(state="visible", timeout=6000)
            except Exception:
                logger.debug("Send button not visible yet, proceeding with keyboard fallback...")

            # 5. Add caption if provided and caption input exists
            if caption:
                try:
                    caption_box = self._page.locator(
                        'div[role="dialog"] div[contenteditable="true"][role="textbox"], div[data-testid="media-caption-input"], div[data-animate-media-viewer="true"] div[contenteditable="true"]'
                    ).first
                    if await caption_box.is_visible(timeout=2000):
                        await caption_box.click()
                        await caption_box.fill(caption)
                        await asyncio.sleep(0.3)
                except Exception as e:
                    logger.debug("Could not fill document caption: %s", e)

            # 6. Click send button or press Enter
            send_clicked = False
            try:
                clicked = await self._page.evaluate("""() => {
                    const btn = document.querySelector('button[aria-label="Send"], div[role="button"][aria-label*="Send" i], span[data-icon="wds-ic-send-filled"], span[data-icon*="send"], div[role="button"]:has(span[data-icon*="send"])');
                    if (btn) {
                        btn.dispatchEvent(new MouseEvent('mousedown', {bubbles: true, cancelable: true, view: window}));
                        btn.dispatchEvent(new MouseEvent('mouseup', {bubbles: true, cancelable: true, view: window}));
                        btn.click();
                        return true;
                    }
                    return false;
                }""")
                if clicked:
                    send_clicked = True
            except Exception:
                pass

            if not send_clicked:
                try:
                    send_btn = self._page.locator(
                        'button[aria-label="Send"], div[role="button"][aria-label*="Send" i], '
                        'span[data-icon="wds-ic-send-filled"], span[data-icon*="send"], '
                        'div[data-testid="send"]'
                    ).first
                    if await send_btn.count() > 0:
                        await send_btn.click()
                        send_clicked = True
                except Exception:
                    pass

            if not send_clicked:
                await self._page.keyboard.press("Enter")

            await asyncio.sleep(2.5)
            logger.info("Successfully sent document '%s' to '%s'", path_obj.name, chat_name)
            return True
        except Exception as e:
            logger.error("Failed to send document '%s' to '%s': %s", file_path, chat_name, e)
            return False

    async def send_image(
        self, chat_name: str, file_path: str, caption: str = "", jid: str = ""
    ) -> bool:
        """
        Send an image/photo to a chat via WhatsApp Web's file attachment input.
        Supports .png, .jpg, .jpeg, .gif, .webp, .bmp formats.
        """
        if not self._page or not self._is_connected:
            return False

        path_obj = Path(file_path)
        if not path_obj.exists():
            logger.error("Image file not found: %s", file_path)
            return False

        image_exts = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
        if path_obj.suffix.lower() not in image_exts:
            logger.error("File '%s' is not a supported image format", file_path)
            return False

        try:
            # 1. Navigate to chat
            navigated = await self.navigate_to_chat(chat_name, jid=jid)
            if not navigated:
                logger.error("Failed to navigate to '%s' for image sending", chat_name)
                return False

            await asyncio.sleep(0.5)

            # 2. Attach Image via expect_file_chooser (Photos & videos)
            attach_btn = self._page.locator(
                'button[aria-label="Attach"], button[title="Attach"], div[aria-label="Attach"], span[data-icon="plus"], span[data-icon="attach-menu-plus"]'
            ).first
            if await attach_btn.count() > 0:
                is_open = (await attach_btn.get_attribute("aria-expanded")) == "true"
                if not is_open:
                    await attach_btn.click()
                    await asyncio.sleep(0.5)

            photo_btn = self._page.locator(
                'button[aria-label="Photos & videos"], button:has-text("Photos & videos"), li:has-text("Photos & videos"), div[role="button"][aria-label="Photos & videos"], button:has-text("Photos")'
            ).first

            attached = False
            if await photo_btn.count() > 0 and await photo_btn.is_visible():
                try:
                    async with self._page.expect_file_chooser(timeout=8000) as fc_info:
                        await photo_btn.click()
                    file_chooser = await fc_info.value
                    await file_chooser.set_files(str(path_obj.resolve()))
                    logger.info("Attached image file '%s' via file chooser (Photos & videos)", path_obj.name)
                    attached = True
                    await asyncio.sleep(1.5)
                except Exception as e:
                    logger.warning("expect_file_chooser failed for image: %s", e)

            if not attached:
                # Fallback to direct input: ONLY use file input that accepts images
                inputs = self._page.locator('input[type="file"]')
                count = await inputs.count()
                for i in range(count):
                    inp = inputs.nth(i)
                    accept = (await inp.get_attribute("accept") or "").lower()
                    if "image" in accept:
                        await inp.set_input_files(str(path_obj.resolve()))
                        attached = True
                        logger.info("Attached image file '%s' via input[accept*='image'] fallback", path_obj.name)
                        await asyncio.sleep(1.5)
                        break

            if not attached:
                logger.error("No suitable image input found to attach image '%s'", path_obj.name)
                return False

            # 5. Add caption if provided
            if caption:
                try:
                    caption_box = self._page.locator(
                        'div[role="dialog"] div[contenteditable="true"][role="textbox"], div[data-testid="media-caption-input"], div[data-animate-media-viewer="true"] div[contenteditable="true"]'
                    ).first
                    if await caption_box.is_visible(timeout=2000):
                        await caption_box.click()
                        await self._page.keyboard.type(caption, delay=0)
                        await asyncio.sleep(0.3)
                except Exception as e:
                    logger.debug("Could not fill image caption: %s", e)

            # 6. Click send button
            send_clicked = False
            try:
                clicked = await self._page.evaluate("""() => {
                    const btn = document.querySelector('button[aria-label="Send"], div[role="button"][aria-label*="Send" i], span[data-icon="wds-ic-send-filled"], span[data-icon*="send"], div[role="button"]:has(span[data-icon*="send"])');
                    if (btn) {
                        btn.dispatchEvent(new MouseEvent('mousedown', {bubbles: true, cancelable: true, view: window}));
                        btn.dispatchEvent(new MouseEvent('mouseup', {bubbles: true, cancelable: true, view: window}));
                        btn.click();
                        return true;
                    }
                    return false;
                }""")
                if clicked:
                    send_clicked = True
            except Exception:
                pass

            if not send_clicked:
                try:
                    send_btn = self._page.locator(
                        'button[aria-label="Send"], div[role="button"][aria-label*="Send" i], '
                        'span[data-icon="wds-ic-send-filled"], span[data-icon*="send"], '
                        'div[data-testid="send"]'
                    ).first
                    if await send_btn.count() > 0:
                        await send_btn.click()
                        send_clicked = True
                except Exception:
                    pass

            if not send_clicked:
                await self._page.keyboard.press("Enter")

            await asyncio.sleep(2.5)
            logger.info("Successfully sent image '%s' to '%s'", path_obj.name, chat_name)
            return True
        except Exception as e:
            logger.error("Failed to send image '%s' to '%s': %s", file_path, chat_name, e)
            return False

    async def get_visible_messages(self, limit: int = 30) -> list:
        """
        Extract visible messages from the current chat.
        Uses fast browser-side evaluation to extract clean structured messages in a single call,
        with fallback to element-by-element iteration.

        Returns a list of dicts: {sender, text, timestamp, is_from_me, quoted_text, message_id}
        """
        if not self._page:
            return []

        try:
            # Fast, atomic DOM evaluation in browser with image & document support
            js_extract = """
            (limit) => {
                let rows = Array.from(document.querySelectorAll('#main [role="row"]'));
                if (rows.length === 0) {
                    rows = Array.from(document.querySelectorAll('[role="row"]'));
                }
                const results = [];
                for (const r of rows) {
                    const copyable = r.querySelector('.copyable-text[data-pre-plain-text]');
                    const pre = copyable ? (copyable.getAttribute('data-pre-plain-text') || '') : '';

                    const textEl = r.querySelector('span.selectable-text, span[dir="ltr"], div.copyable-text');
                    let text = textEl ? textEl.innerText.trim() : '';

                    const sticker = r.querySelector('[data-testid*="sticker"], img[alt*="Sticker"]');
                    const img = r.querySelector('img[src*="blob:"], [data-testid*="image"], [data-testid="media-caption"]');
                    const gif = r.querySelector('[data-testid*="gif"], [data-icon*="gif"]');
                    const docEl = r.querySelector('[data-testid*="document"], [data-icon*="document"], span[title*="."], div[title*="."], [data-icon*="pdf"]');
                    const videoEl = r.querySelector('video, [data-testid*="video"], [data-icon*="video"], [data-icon="media-play"], span[data-icon="status-vcard-video"]');

                    let mediaType = 'text';
                    let imgData = null;
                    let docName = '';

                    if (docEl) {
                        const titleEl = r.querySelector('span[title], div[title], [data-testid="document-thumb"] + div span, span[dir="ltr"]');
                        if (titleEl) {
                            docName = titleEl.getAttribute('title') || titleEl.innerText.trim();
                        }
                        if (!docName) {
                            const anySpan = r.querySelector('span[title*="."]');
                            if (anySpan) docName = anySpan.getAttribute('title') || anySpan.innerText.trim();
                        }
                        if (!docName && docEl.getAttribute('title')) {
                            docName = docEl.getAttribute('title');
                        }
                        if (!docName) docName = 'document.pdf';
                        mediaType = 'document';
                        text = text ? `${text} [Document: ${docName}]` : `[Document: ${docName}]`;
                    } else if (videoEl) {
                        mediaType = 'video';
                        text = text ? `${text} [Video]` : '[Sent a video]';
                    } else if (sticker) {
                        mediaType = 'sticker';
                        const alt = sticker.getAttribute('alt') || sticker.querySelector('img')?.getAttribute('alt') || '';
                        const stickerDesc = alt.replace(/^Sticker with:\\s*/i, '').trim();
                        const tag = stickerDesc ? `[Sticker: ${stickerDesc}]` : '[Sticker]';
                        text = text ? `${text} ${tag}` : tag;
                    } else if (gif) {
                        mediaType = 'gif';
                        text = text ? `${text} [GIF]` : '[Sent a GIF]';
                    } else if (img) {
                        mediaType = 'image';
                        text = text ? `${text} [Image]` : '[Sent an image]';
                        try {
                            const imgEl = r.querySelector('img[src*="blob:"], img');
                            if (imgEl && (imgEl.naturalWidth > 20 || imgEl.width > 20)) {
                                const canvas = document.createElement('canvas');
                                canvas.width = Math.min(imgEl.naturalWidth || imgEl.width || 800, 1600);
                                canvas.height = Math.min(imgEl.naturalHeight || imgEl.height || 800, 1600);
                                const ctx = canvas.getContext('2d');
                                ctx.drawImage(imgEl, 0, 0, canvas.width, canvas.height);
                                imgData = canvas.toDataURL('image/jpeg', 0.95);
                            }
                        } catch(e) {}
                    }

                    if (!text) continue;

                    const hasYou = !!r.querySelector('[aria-label*="You"]');
                    const hasCheck = !!r.querySelector('[data-icon*="check"], [aria-label*="read"], [aria-label*="Delivered"], [aria-label*="Sent"], [data-icon*="msg-check"], [data-icon*="msg-dblcheck"]');
                    const hasMsgOut = !!r.querySelector('.message-out') || r.classList.contains('message-out');
                    
                    const mainEl = document.querySelector('#main');
                    const mainRect = mainEl ? mainEl.getBoundingClientRect() : { left: 0, width: 1000 };
                    const bRect = r.getBoundingClientRect();
                    const isRightAligned = (bRect.left - mainRect.left) > (mainRect.width * 0.25);

                    const isFromMe = Boolean(
                        hasYou || hasCheck || hasMsgOut || isRightAligned ||
                        (pre && (pre.includes('David Julius') || pre.includes('You:') || pre.includes('David:')))
                    );

                    let sender = '';
                    if (pre) {
                        const match = pre.match(/\\]\\s*(.*?):\\s*$/);
                        if (match) sender = match[1].trim();
                    }
                    if (!sender) {
                        const authorEl = r.querySelector('span._ahxt, span[data-testid="msg-author"]');
                        if (authorEl) sender = authorEl.innerText.trim();
                    }

                    let timestamp = '';
                    const timeEl = r.querySelector('[data-testid="msg-meta"] span, span[data-testid*="meta"]');
                    if (timeEl) {
                        timestamp = timeEl.innerText.trim();
                    } else if (pre) {
                        const timeMatch = pre.match(/^\\[([^\\]]+)\\]/);
                        if (timeMatch) timestamp = timeMatch[1].trim();
                    }

                    let quotedText = null;
                    const quotedEl = r.querySelector('[data-testid="quoted-message"]');
                    if (quotedEl) quotedText = quotedEl.innerText.trim();

                    const msgId = r.getAttribute('data-id') || r.querySelector('[data-id]')?.getAttribute('data-id') || '';

                    results.push({
                        sender: sender,
                        text: text,
                        timestamp: timestamp,
                        is_from_me: isFromMe,
                        quoted_text: quotedText,
                        message_id: msgId,
                        media_type: mediaType,
                        image_data: imgData,
                        document_name: docName
                    });
                }
                return results.slice(-limit);
            }
            """
            extracted = await self._page.evaluate(js_extract, limit)
            if extracted and isinstance(extracted, list):
                return extracted
        except Exception as e:
            logger.debug("Fast DOM extraction failed, falling back: %s", e)

        # Fallback to Playwright element-by-element extraction
        try:
            messages = []
            rows = self._page.locator('[role="row"]')
            count = await rows.count()
            if count == 0:
                rows = self._page.locator(WhatsAppSelectors.MESSAGE_ROW)
                count = await rows.count()
            start = max(0, count - limit)

            for i in range(start, count):
                row = rows.nth(i)
                try:
                    msg_data = await self._extract_message_from_row(row)
                    if msg_data:
                        messages.append(msg_data)
                except Exception:
                    continue

            return messages
        except Exception as e:
            logger.error("Error extracting messages: %s", e)
            return []

    async def _extract_message_from_row(self, row) -> Optional[dict]:
        """Extract message data from a single message row element."""
        try:
            # Determine if incoming or outgoing with multiple heuristics
            classes = await row.get_attribute("class") or ""
            has_you = await row.locator('[aria-label*="You"]').count() > 0
            has_check = await row.locator('[data-icon*="check"]').count() > 0
            is_from_me = (
                has_you or
                has_check or
                "message-out" in classes or
                await row.locator(".message-out").count() > 0
            )

            # Get text content
            text_el = row.locator(WhatsAppSelectors.MESSAGE_TEXT)
            if await text_el.count() == 0:
                text_el = row.locator(WhatsAppSelectors.MESSAGE_TEXT_FALLBACK)
            if await text_el.count() == 0:
                text_el = row.locator('span[dir="ltr"], div.copyable-text')
            if await text_el.count() == 0:
                return None

            text = (await text_el.first.inner_text()).strip()
            if not text:
                return None

            # Check pre-plain-text for sender and outgoing confirmation
            sender = ""
            copyable = row.locator('.copyable-text[data-pre-plain-text]')
            if await copyable.count() > 0:
                pre = await copyable.first.get_attribute("data-pre-plain-text") or ""
                if "David Julius" in pre or "You:" in pre:
                    is_from_me = True
                import re
                m = re.search(r"\]\s*(.*?):\s*$", pre)
                if m:
                    sender = m.group(1).strip()

            # Get sender (group chats) if not already found
            if not sender:
                sender_el = row.locator(WhatsAppSelectors.MESSAGE_SENDER)
                if await sender_el.count() == 0:
                    sender_el = row.locator(WhatsAppSelectors.MESSAGE_SENDER_FALLBACK)
                if await sender_el.count() > 0:
                    sender = (await sender_el.first.inner_text()).strip()

            # Get timestamp
            timestamp = ""
            ts_el = row.locator(WhatsAppSelectors.MESSAGE_TIMESTAMP)
            if await ts_el.count() > 0:
                timestamp = (await ts_el.first.inner_text()).strip()

            # Get quoted message
            quoted_text = None
            quoted_el = row.locator(WhatsAppSelectors.QUOTED_MESSAGE)
            if await quoted_el.count() > 0:
                quoted_text = (await quoted_el.first.inner_text()).strip()

            message_id = await row.get_attribute("data-id")
            if not message_id:
                id_node = row.locator("[data-id]")
                if await id_node.count() > 0:
                    message_id = await id_node.first.get_attribute("data-id")

            return {
                "message_id": message_id,
                "sender": sender,
                "text": text,
                "timestamp": timestamp,
                "is_from_me": is_from_me,
                "quoted_text": quoted_text,
            }
        except Exception:
            return None

    # ── Internal helpers ──────────────────────────────────────────

    def _acquire_lock(self) -> None:
        """Acquire PID lock to prevent duplicate sessions."""
        Path(self._profile_dir).mkdir(parents=True, exist_ok=True)
        if self._lock_path.exists():
            try:
                old_pid = int(self._lock_path.read_text().strip())
                if old_pid == os.getpid():
                    return
                # Check if old process is still running
                try:
                    os.kill(old_pid, 0)
                    logger.warning("Another WhatsApp session (PID %d) is using this profile", old_pid)
                    # Kill the stale process
                    os.kill(old_pid, 9)
                    logger.info("Killed stale WhatsApp process PID %d", old_pid)
                except OSError:
                    pass  # Process doesn't exist
            except (ValueError, OSError):
                pass
        self._lock_path.write_text(str(os.getpid()))

    def _release_lock(self) -> None:
        """Release PID lock."""
        try:
            if self._lock_path.exists():
                current_pid = self._lock_path.read_text().strip()
                if current_pid == str(os.getpid()):
                    self._lock_path.unlink()
        except Exception:
            pass

    def _kill_orphans(self) -> None:
        """Kill any orphaned browser processes using this profile."""
        try:
            subprocess.run(
                ["pkill", "-f", f"--user-data-dir={self._profile_dir}"],
                check=False, capture_output=True,
            )
        except Exception:
            pass

    def _clean_stale_locks(self) -> None:
        """Clean up stale Chromium lock files."""
        for lock_name in ["SingletonLock", "lockfile", "SingletonCookie", "SingletonSocket"]:
            lock_path = Path(self._profile_dir) / lock_name
            if lock_path.exists():
                try:
                    if lock_path.is_symlink():
                        lock_path.unlink()
                    else:
                        lock_path.unlink(missing_ok=True)
                except Exception:
                    pass
