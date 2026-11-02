#!/usr/bin/env python3
"""
Send an email with an attachment from Gmail using Playwright WebKit (Safari engine).
Reuses the persistent webkit_profile so the Gmail session is already authenticated.
Produces intermediate screenshots so failures can be diagnosed.
"""
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parent.parent
PROFILE_DIR = ROOT / "webkit_profile"
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

RECIPIENT = "recipient@example.com"
SUBJECT = "Document"
BODY = "Hello,\n\nAttaching the requested document.\n\n- Julius\n"
ATTACHMENT = Path.home() / "Desktop" / "document.pdf"


def log(msg: str) -> None:
    print(msg, flush=True)


def shot(page, name: str) -> None:
    p = LOG_DIR / f"gmail_{name}.png"
    try:
        page.screenshot(path=str(p), full_page=False)
        log(f"[shot] {p}")
    except Exception as exc:
        log(f"[shot-failed] {name}: {exc}")


def first_visible(page, selectors, timeout_ms=10000):
    """Return the first locator that becomes visible, or None."""
    deadline = time.time() + timeout_ms / 1000.0
    while time.time() < deadline:
        for sel in selectors:
            try:
                loc = page.locator(sel).first
                if loc.count() > 0 and loc.is_visible():
                    return loc
            except Exception:
                pass
        time.sleep(0.5)
    return None


def main() -> int:
    if not ATTACHMENT.exists():
        log(f"ATTACHMENT_MISSING: {ATTACHMENT}")
        return 2
    log(f"attachment ready: {ATTACHMENT} ({ATTACHMENT.stat().st_size} bytes)")

    with sync_playwright() as p:
        context = p.webkit.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            viewport={"width": 1500, "height": 950},
            locale="en-US",
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto("https://mail.google.com/mail/u/0/#inbox", wait_until="domcontentloaded")

        log("waiting for inbox to load...")
        deadline = time.time() + 180
        while time.time() < deadline:
            try:
                if page.locator("div[role='main']").count() > 0:
                    url = page.url
                    if "mail.google.com" in url:
                        break
            except Exception:
                pass
            time.sleep(2)
        shot(page, "01_inbox")
        log(f"inbox url: {page.url}")

        # Focus the page body so keyboard shortcuts work, then press 'c'.
        try:
            page.locator("div[role='main']").first.click(position={"x": 20, "y": 20}, timeout=5000)
        except Exception:
            pass

        log("opening compose via keyboard shortcut 'c'...")
        page.keyboard.press("c")
        page.wait_for_timeout(2500)
        shot(page, "02_after_c")

        # If compose didn't open, try clicking the compose button via aria-label.
        compose_to = first_visible(
            page,
            [
                "textarea[name='to']",
                "input[name='to']",
                "input[peoplekit-id]",
                "div[aria-label='To recipients']",
                "div[aria-label*='To recipients'] input",
            ],
            timeout_ms=5000,
        )
        if compose_to is None:
            log("compose not open after shortcut; trying to click Compose button...")
            for sel in [
                "div[role='button'][gh='cm']",
                "div.T-I.T-I-KE.L3",
                "div[aria-label='Compose']",
            ]:
                try:
                    btn = page.locator(sel).first
                    if btn.count() > 0 and btn.is_visible():
                        btn.click()
                        log(f"clicked compose via: {sel}")
                        break
                except Exception:
                    pass
            page.wait_for_timeout(2500)
            shot(page, "03_after_compose_click")
            compose_to = first_visible(
                page,
                [
                    "textarea[name='to']",
                    "input[name='to']",
                    "input[peoplekit-id]",
                    "div[aria-label='To recipients']",
                    "div[aria-label*='To recipients'] input",
                ],
                timeout_ms=15000,
            )

        if compose_to is None:
            log("COMPOSE_NOT_OPEN")
            shot(page, "99_compose_failed")
            context.close()
            return 4

        log("compose window is open")
        compose_to.click()
        compose_to.fill(RECIPIENT)
        page.keyboard.press("Tab")
        page.wait_for_timeout(500)

        log("filling subject...")
        subject_field = first_visible(
            page,
            ["input[name='subjectbox']", "input[aria-label='Subject']", "input[placeholder='Subject']"],
            timeout_ms=10000,
        )
        if subject_field is None:
            log("SUBJECT_FIELD_NOT_FOUND")
            shot(page, "99_subject_failed")
            context.close()
            return 5
        subject_field.click()
        subject_field.fill(SUBJECT)

        log("filling body...")
        body_field = first_visible(
            page,
            [
                "div[aria-label='Message Body']",
                "div[role='textbox'][aria-label*='Message Body']",
                "div[role='textbox'][g_editable='true']",
            ],
            timeout_ms=10000,
        )
        if body_field is not None:
            body_field.click()
            page.keyboard.type(BODY)
        else:
            log("BODY_FIELD_NOT_FOUND (continuing)")

        log(f"attaching {ATTACHMENT.name}...")
        file_input = page.locator("input[type='file']").first
        try:
            file_input.set_input_files(str(ATTACHMENT), timeout=15000)
            log("set_input_files called")
        except Exception as exc:
            log(f"attach failed: {exc}")

        # Wait for attachment chip or a small delay for upload.
        page.wait_for_timeout(6000)
        shot(page, "04_before_send")

        log("clicking Send...")
        send_btn = first_visible(
            page,
            [
                "div[role='button'][aria-label*='Send']",
                "div[role='button'][data-tooltip*='Send']",
                "div.T-I.J-J5-Ji.aoO",
            ],
            timeout_ms=10000,
        )
        if send_btn is None:
            log("SEND_BUTTON_NOT_FOUND")
            shot(page, "99_send_button_failed")
            context.close()
            return 6
        send_btn.click()
        log("send clicked; waiting for compose to close...")

        sent = False
        deadline = time.time() + 60
        while time.time() < deadline:
            try:
                # compose dialog gone?
                dialog = page.locator("div[role='dialog']")
                body = page.locator("div[aria-label='Message Body']")
                if dialog.count() == 0 or body.count() == 0:
                    sent = True
                    break
            except Exception:
                pass
            time.sleep(1)

        shot(page, "05_after_send")
        context.close()

    if sent:
        log("SEND_OK")
        return 0
    log("SEND_UNCONFIRMED")
    return 3


if __name__ == "__main__":
    sys.exit(main())
