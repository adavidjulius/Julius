"""
Julius WhatsApp Integration — Resilient WhatsApp Adapter & Media Engine.

Provides an isolated, fault-tolerant interface to WhatsApp Web:
- Decouples DOM manipulation and selectors from high-level reasoning.
- Resilient SelectorStrategy with accessibility, semantic, and structural fallbacks.
- Complete 11-step media transmission protocol (validation, file selection, preview
  synchronization, captioning, transmission, and post-send bubble verification).
- Robust error recovery if WhatsApp Web UI state rejects files or disconnects.
"""

from __future__ import annotations

import asyncio
import logging
import mimetypes
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .browser import WhatsAppBrowserAdapter

logger = logging.getLogger(__name__)


# ── Resilient Selector Registry ───────────────────────────────────────────────

@dataclass(frozen=True)
class SelectorStrategy:
    """Multi-tier fallback selector with validation."""
    name: str
    candidates: Tuple[str, ...]

    async def locate(self, page: Any, timeout: float = 3000) -> Optional[Any]:
        """Try each candidate selector in order and return the first visible match."""
        per_candidate_ms = max(400, int(timeout / max(len(self.candidates), 1)))
        for sel in self.candidates:
            try:
                loc = page.locator(sel).first
                await loc.wait_for(state="visible", timeout=per_candidate_ms)
                return loc
            except Exception:
                continue
        # Second pass: check if any element exists in DOM even if not initially visible
        for sel in self.candidates:
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0:
                    return loc
            except Exception:
                continue
        return None


ATTACH_BUTTON_STRATEGY = SelectorStrategy(
    name="attach_menu_button",
    candidates=(
        'button[title="Attach"]',
        'div[aria-label="Attach"]',
        'span[data-icon="plus"]',
        'span[data-icon="attach-menu-plus"]',
        '[data-testid="attach-menu-plus"]',
        '#main footer div[role="button"]:has(span[data-icon])',
    ),
)

DOCUMENT_INPUT_STRATEGY = SelectorStrategy(
    name="document_file_input",
    candidates=(
        'input[type="file"][accept="*"]',
        'input[type="file"]:not([accept*="image"])',
        'input[type="file"]',
    ),
)

IMAGE_INPUT_STRATEGY = SelectorStrategy(
    name="image_file_input",
    candidates=(
        'input[type="file"][accept*="image"]',
        'input[type="file"][accept*="video"]',
        'input[type="file"]',
    ),
)

PREVIEW_DIALOG_STRATEGY = SelectorStrategy(
    name="media_preview_dialog",
    candidates=(
        'div[data-animate-media-viewer="true"]',
        'div[role="dialog"]',
        'div[data-testid="media-viewer"]',
        'div[data-testid="media-caption-input-container"]',
        'div[data-testid="image-thumb-list"]',
    ),
)

PREVIEW_CAPTION_STRATEGY = SelectorStrategy(
    name="preview_caption_box",
    candidates=(
        'div[data-testid="media-caption-input"]',
        'div[role="dialog"] div[contenteditable="true"][role="textbox"]',
        'div[data-animate-media-viewer="true"] div[contenteditable="true"]',
        'div[role="dialog"] div[aria-label*="caption" i]',
        'div[role="dialog"] [contenteditable="true"]',
    ),
)

PREVIEW_SEND_BUTTON_STRATEGY = SelectorStrategy(
    name="preview_send_button",
    candidates=(
        'button[aria-label="Send"]',
        'div[role="button"][aria-label*="Send" i]',
        'span[data-icon="wds-ic-send-filled"]',
        'div[role="button"]:has(span[data-icon="wds-ic-send-filled"])',
        'button:has(span[data-icon="wds-ic-send-filled"])',
        'div[role="button"]:has(span[data-icon*="send"])',
        'span[data-icon*="send"]',
        'div[role="dialog"] span[data-icon="send"]',
        'div[role="dialog"] div[aria-label="Send"]',
        'div[role="dialog"] button[aria-label="Send"]',
        'div[data-testid="send"]',
        'span[data-icon="send"]',
        'div[role="button"][aria-label="Send"]',
    ),
)


class WhatsAppAdapter:
    """Isolated, resilient abstraction over WhatsApp Web Playwright operations."""

    def __init__(self, browser: WhatsAppBrowserAdapter) -> None:
        self._browser = browser

    @property
    def browser(self) -> WhatsAppBrowserAdapter:
        return self._browser

    @property
    def is_connected(self) -> bool:
        return self._browser.is_connected

    async def connect(self) -> bool:
        """Ensure WhatsApp Web is connected and authenticated."""
        return await self._browser.is_authenticated()

    async def find_chat(self, chat_name: str, jid: str = "") -> bool:
        """Locate and open chat by name or JID."""
        return await self._browser.navigate_to_chat(chat_name, jid=jid)

    async def open_chat(self, chat_name: str, jid: str = "") -> bool:
        """Alias for find_chat."""
        return await self.find_chat(chat_name, jid=jid)

    async def read_messages(self, limit: int = 30) -> list:
        """Read visible messages from currently opened conversation."""
        return await self._browser.get_visible_messages(limit=limit)

    async def send_text(self, chat_name: str, text: str, jid: str = "") -> bool:
        """Send a plain text message to a contact."""
        return await self._browser.send_message(chat_name, text, jid=jid)

    async def send_media(
        self,
        chat_name: str,
        file_path: str,
        media_type: str = "auto",
        caption: str = "",
        jid: str = "",
    ) -> bool:
        """Robust, unified media-sending protocol for images, PDFs, and documents.

        Protocol Steps:
        1. Verify file exists on local filesystem.
        2. Detect and validate media type (image vs document/pdf).
        3. Navigate to chat and verify composer readiness.
        4. Open attachment menu to mount file inputs into DOM.
        5. Locate the appropriate file input element via SelectorStrategy.
        6. Set input files via Playwright.
        7. Wait for WhatsApp Web media preview overlay to appear.
        8. Inject caption if specified.
        9. Locate and click preview send button (with Ctrl+Enter fallback).
        10. Wait for preview dialog to dismiss (confirming upload handoff).
        11. Verify outgoing bubble in message list.
        """
        path_obj = Path(file_path).resolve()
        if not path_obj.exists() or not path_obj.is_file():
            logger.error("[MEDIA] File does not exist on disk: %s", file_path)
            return False

        file_size = path_obj.stat().st_size
        if file_size == 0:
            logger.error("[MEDIA] File is empty (0 bytes): %s", file_path)
            return False

        # 100 MB max safety boundary for WhatsApp Web
        if file_size > 100 * 1024 * 1024:
            logger.error("[MEDIA] File exceeds WhatsApp 100MB limit (%d bytes): %s", file_size, file_path)
            return False

        # Classify media type
        ext = path_obj.suffix.lower()
        image_exts = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
        document_exts = {".pdf", ".docx", ".doc", ".xlsx", ".csv", ".txt", ".zip", ".rar", ".mp3", ".wav"}

        resolved_type = media_type.lower()
        if resolved_type == "auto":
            if ext in image_exts:
                resolved_type = "image"
            else:
                resolved_type = "document"

        logger.info(
            "[MEDIA] Starting transmission: file='%s' (size=%d, type=%s) -> chat='%s'",
            path_obj.name,
            file_size,
            resolved_type,
            chat_name,
        )

        if resolved_type == "image":
            try:
                raw_head = path_obj.read_bytes()[:16]
                is_valid = (
                    len(raw_head) >= 4
                    and (
                        raw_head[:3] == b"\xff\xd8\xff"
                        or raw_head[:4] == b"\x89PNG"
                        or (raw_head[:4] == b"RIFF" and raw_head[8:12] == b"WEBP")
                    )
                )
                if not is_valid:
                    logger.error("[MEDIA] File '%s' does not have valid JPEG/PNG magic bytes. Aborting send.", path_obj.name)
                    return False
                try:
                    from PIL import Image
                    with Image.open(str(path_obj)) as im:
                        im.verify()
                except ImportError:
                    pass
            except Exception as e:
                logger.error("[MEDIA] File '%s' is not a valid decodable image: %s. Aborting send.", path_obj.name, e)
                return False

        page = self._browser.page
        if not page or not self._browser.is_connected:
            logger.error("[MEDIA] Browser page not connected — cannot send media")
            return False

        try:
            # Step 1: Open chat
            navigated = await self.find_chat(chat_name, jid=jid)
            if not navigated:
                logger.error("[MEDIA] Failed to navigate to chat '%s'", chat_name)
                return False

            await asyncio.sleep(0.5)

            # Record baseline message count for verification
            baseline_rows = await page.locator('#main [role="row"]').count()

            # Step 2: Mount attachment inputs
            await self._mount_attachment_menu(page)

            # Step 3: Trigger file chooser and attach file (with file input fallback)
            attached = False
            try:
                attached = await self._attach_file(page, str(path_obj), resolved_type)
            except Exception as e:
                logger.debug("[MEDIA] _attach_file exception: %s", e)

            if not attached:
                file_input = await self._locate_file_input(page, resolved_type)
                if file_input:
                    await file_input.set_input_files(str(path_obj))
                    attached = True

            if not attached:
                logger.error("[MEDIA] Failed attaching file '%s' (type=%s)", path_obj.name, resolved_type)
                return False

            # Step 5: Wait for WhatsApp preview overlay
            preview_visible = await self._wait_for_preview(page)
            if not preview_visible:
                logger.warning("[MEDIA] Preview overlay did not signal visibility within timeout; attempting send")

            # Step 6: Add caption if provided
            if caption:
                await self._inject_caption(page, caption)

            # Step 7: Click preview send button
            sent_clicked = await self._dispatch_preview_send(page)
            if not sent_clicked:
                logger.error("[MEDIA] Failed to click or trigger preview send button")
                await self._dismiss_any_stuck_dialog(page)
                return False

            # Step 8: Wait for preview dialog to disappear (handoff complete)
            await self._wait_for_preview_dismissal(page)

            # Step 9: Verify message transmission
            verified = await self.verify_message_sent(baseline_rows, timeout=12.0)
            if verified:
                logger.info(
                    "[MEDIA] VERIFIED: Successfully transmitted '%s' to '%s'",
                    path_obj.name,
                    chat_name,
                )
                return True
            else:
                logger.error(
                    "[MEDIA] Upload verification failed: row count did not increment in time for '%s' to '%s'. Aborting.",
                    path_obj.name,
                    chat_name,
                )
                await self._dismiss_any_stuck_dialog(page)
                return False

        except Exception as e:
            logger.error("[MEDIA] Failed during media sending protocol: %s", e)
            await self._dismiss_any_stuck_dialog(page)
            return False

    async def send_image(self, chat_name: str, file_path: str, caption: str = "", jid: str = "") -> bool:
        """Convenience method for images."""
        return await self.send_media(chat_name, file_path, media_type="image", caption=caption, jid=jid)

    async def send_document(self, chat_name: str, file_path: str, caption: str = "", jid: str = "") -> bool:
        """Convenience method for PDFs and documents."""
        return await self.send_media(chat_name, file_path, media_type="document", caption=caption, jid=jid)

    async def _attach_file(self, page: Any, file_path: str, media_type: str) -> bool:
        """
        Open WhatsApp attach menu and trigger file chooser for Document or Photos & videos.
        In modern WhatsApp Web, Document and Photos & videos are BUTTONs that trigger
        the browser's file picker dialog. Playwright's expect_file_chooser handles them cleanly.
        """
        try:
            # 1. Open attach menu if not already open
            attach_btn = page.locator(
                'button[aria-label="Attach"], button[title="Attach"], div[aria-label="Attach"], span[data-icon="plus"], span[data-icon="attach-menu-plus"]'
            ).first

            is_open = False
            if await attach_btn.count() > 0:
                is_open = (await attach_btn.get_attribute("aria-expanded")) == "true"
                if not is_open:
                    await attach_btn.click()
                    await asyncio.sleep(0.5)

            # 2. Locate target menu item button
            if media_type == "image":
                btn_locators = [
                    'button[aria-label="Photos & videos"]',
                    'button:has-text("Photos & videos")',
                    'li:has-text("Photos & videos")',
                    'div[role="button"][aria-label="Photos & videos"]',
                    'button:has-text("Photos")',
                    'li:has-text("Photos")',
                ]
            else:
                btn_locators = [
                    'button[aria-label="Document"]',
                    'button:has-text("Document")',
                    'li:has-text("Document")',
                    'div[role="button"][aria-label="Document"]',
                    'div[role="button"]:has-text("Document")',
                ]

            target_btn = None
            for sel in btn_locators:
                loc = page.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible():
                    target_btn = loc
                    break

            if target_btn:
                async with page.expect_file_chooser(timeout=8000) as fc_info:
                    await target_btn.click()
                file_chooser = await fc_info.value
                await file_chooser.set_files(file_path)
                logger.info("[MEDIA] Successfully attached '%s' via file chooser (%s)", Path(file_path).name, media_type)
                await asyncio.sleep(1.2)
                return True

            logger.warning("[MEDIA] Target button for '%s' not visible in attach menu; trying file input fallback", media_type)
            inp = await self._locate_file_input(page, media_type)
            if inp:
                await inp.set_input_files(file_path)
                logger.info("[MEDIA] Supplied file '%s' to input fallback", Path(file_path).name)
                await asyncio.sleep(1.2)
                return True

            return False
        except Exception as e:
            logger.warning("[MEDIA] expect_file_chooser error: %s; trying file input fallback", e)
            try:
                inp = await self._locate_file_input(page, media_type)
                if inp:
                    await inp.set_input_files(file_path)
                    await asyncio.sleep(1.2)
                    return True
            except Exception as e2:
                logger.error("[MEDIA] File input fallback also failed: %s", e2)
            return False

    async def _mount_attachment_menu(self, page: Any) -> None:
        """Click the attach (+) button to mount file input elements in the DOM if needed."""
        # Check if file inputs are already present
        inputs = page.locator('input[type="file"]')
        if await inputs.count() >= 2:
            return

        attach_btn = await ATTACH_BUTTON_STRATEGY.locate(page, timeout=2000)
        if attach_btn:
            try:
                await attach_btn.click()
                await asyncio.sleep(0.6)
            except Exception as e:
                logger.debug("[MEDIA] Attach button click error: %s", e)

    async def _locate_file_input(self, page: Any, media_type: str) -> Optional[Any]:
        """Locate the target file input based on media type."""
        inputs = page.locator('input[type="file"]')
        count = await inputs.count()
        if count == 0:
            # Try mounting again
            await self._mount_attachment_menu(page)
            count = await inputs.count()

        if media_type == "image":
            for i in range(count):
                inp = inputs.nth(i)
                accept = (await inp.get_attribute("accept") or "").lower()
                if "image" in accept:
                    return inp
            return None
        else:
            # Document / PDF
            for i in range(count):
                inp = inputs.nth(i)
                accept = (await inp.get_attribute("accept") or "").lower()
                if accept == "*" or "image" not in accept:
                    return inp
            return inputs.last if count > 0 else None

    async def _wait_for_preview(self, page: Any, timeout: float = 8.0) -> bool:
        """Wait for the media preview modal to render."""
        dialog = await PREVIEW_DIALOG_STRATEGY.locate(page, timeout=int(timeout * 1000))
        return dialog is not None

    async def _inject_caption(self, page: Any, caption: str) -> bool:
        """Fill caption inside the media preview modal."""
        caption_box = await PREVIEW_CAPTION_STRATEGY.locate(page, timeout=3000)
        if caption_box:
            try:
                await caption_box.click()
                await caption_box.fill(caption)
                await asyncio.sleep(0.3)
                logger.info("[MEDIA] Injected caption: '%s'", caption[:60])
                return True
            except Exception as e:
                logger.debug("[MEDIA] Failed to inject caption via fill: %s", e)
                try:
                    await page.keyboard.type(caption, delay=5)
                    return True
                except Exception:
                    pass
        return False

    async def _dispatch_preview_send(self, page: Any) -> bool:
        """Click the green Send button inside the media preview overlay."""
        # 1. Playwright locator strategy
        send_btn = await PREVIEW_SEND_BUTTON_STRATEGY.locate(page, timeout=3000)
        if send_btn:
            try:
                await send_btn.click(timeout=2000)
                await asyncio.sleep(0.5)
                return True
            except Exception as e:
                logger.debug("[MEDIA] Send button locator click error: %s", e)

        # 2. Browser DOM click evaluation
        try:
            clicked = await page.evaluate("""() => {
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
                await asyncio.sleep(0.5)
                return True
        except Exception as e:
            logger.debug("[MEDIA] DOM evaluation send click error: %s", e)

        # 3. Check for chat footer send button (if media was attached to composer input)
        try:
            footer_clicked = await page.evaluate("""() => {
                const btn = document.querySelector('#main footer button[aria-label="Send"], #main footer div[role="button"][aria-label*="Send" i], #main footer span[data-icon*="send"]');
                if (btn) {
                    btn.dispatchEvent(new MouseEvent('mousedown', {bubbles: true, cancelable: true, view: window}));
                    btn.dispatchEvent(new MouseEvent('mouseup', {bubbles: true, cancelable: true, view: window}));
                    btn.click();
                    return true;
                }
                return false;
            }""")
            if footer_clicked:
                await asyncio.sleep(0.5)
                return True
        except Exception:
            pass

        # 4. Fallback: Ctrl+Enter / Enter inside preview
        try:
            await page.keyboard.press("Control+Enter")
            await asyncio.sleep(0.5)
            return True
        except Exception:
            try:
                await page.keyboard.press("Enter")
                return True
            except Exception:
                return False

    async def _wait_for_preview_dismissal(self, page: Any, timeout: float = 8.0) -> None:
        """Wait for the media viewer dialog to close after send."""
        t0 = time.time()
        while time.time() - t0 < timeout:
            preview = await PREVIEW_DIALOG_STRATEGY.locate(page, timeout=500)
            if not preview:
                return
            await asyncio.sleep(0.4)
        # If still visible, dismiss via Escape or Close button to clear the overlay
        try:
            await page.keyboard.press("Escape")
            await page.evaluate("""() => {
                const closeBtn = document.querySelector('button[aria-label="Close"], div[role="button"][aria-label="Close"], span[data-icon="x"]');
                if (closeBtn) closeBtn.click();
            }""")
        except Exception:
            pass

    async def verify_message_sent(self, baseline_rows: int, timeout: float = 8.0) -> bool:
        """Verify that a new outgoing message bubble exists in the chat."""
        page = self._browser.page
        if not page:
            return False

        t0 = time.time()
        while time.time() - t0 < timeout:
            current_rows = await page.locator('#main [role="row"]').count()
            if current_rows > baseline_rows:
                return True
            # Also check if recent outgoing message contains a document or media card
            try:
                has_card = await page.evaluate("""() => {
                    const rows = document.querySelectorAll('#main div[role="row"]');
                    if (rows.length === 0) return false;
                    const last = rows[rows.length - 1];
                    return !!(last.querySelector('span[data-icon*="pdf"], span[data-icon*="document"], [data-testid="media-card"], img') || last.innerText.includes('.pdf'));
                }""")
                if has_card:
                    return True
            except Exception:
                pass
            await asyncio.sleep(0.5)
        return False

    async def _dismiss_any_stuck_dialog(self, page: Any) -> None:
        """Dismiss stuck popups or preview dialogs if upload aborted."""
        try:
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.2)
            await page.keyboard.press("Escape")
            await page.evaluate("""() => {
                const closeBtn = document.querySelector('div[role="button"][aria-label="Close"], button[aria-label="Close"], span[data-icon="x"]');
                if (closeBtn) closeBtn.click();
            }""")
        except Exception:
            pass

    async def recover(self) -> bool:
        """Attempt recovery of browser page/session if in faulted state."""
        try:
            logger.info("[ADAPTER] Performing recovery of WhatsApp browser...")
            return await self._browser.reconnect()
        except Exception as e:
            logger.error("[ADAPTER] Recovery failed: %s", e)
            return False
