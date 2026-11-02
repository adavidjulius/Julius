#!/usr/bin/env python3
"""
Send an email with an image attachment via Gmail using Playwright WebKit.

Reuses the persistent webkit_profile so an existing Gmail session is honored.
If the user is not logged in, the browser stays open and the script waits for
a manual login before continuing.

Usage:
    .venv/bin/python scripts/send_gmail_image.py \\
        --to recipient@example.com \\
        --attachment ~/Desktop/image.jpg \\
        --subject 'Image' \\
        --body 'Hi, sharing the image.'
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parent.parent
PROFILE_DIR = ROOT / "webkit_profile"
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)


def log(msg: str) -> None:
    print(msg, flush=True)


def shot(page, name: str) -> None:
    p = LOG_DIR / f"gmail_send_{name}.png"
    try:
        page.screenshot(path=str(p), full_page=False)
        log(f"[shot] {p}")
    except Exception as exc:  # noqa: BLE001
        log(f"[shot-failed] {name}: {exc}")


def first_visible(page, selectors, timeout_ms: int = 10000):
    """Return the first locator that becomes visible, or None."""
    deadline = time.time() + timeout_ms / 1000.0
    while time.time() < deadline:
        for sel in selectors:
            try:
                loc = page.locator(sel).first
                if loc.count() > 0 and loc.is_visible():
                    return loc
            except Exception:  # noqa: BLE001
                pass
        time.sleep(0.5)
    return None


def wait_for_login(page, timeout_s: int = 600) -> bool:
    """Wait until the Gmail inbox (not the sign-in page) is visible.

    Returns True if an authenticated inbox was reached.
    """
    log("waiting for Gmail inbox (log in manually in the opened window if needed)...")
    deadline = time.time() + timeout_s
    last_state = None
    while time.time() < deadline:
        try:
            url = page.url or ""
            if "accounts.google.com" in url or "ServiceLogin" in url:
                state = "login"
            elif "mail.google.com" in url and page.locator("div[role='main']").count() > 0:
                # inbox has the main region plus compose control
                if page.locator("div[gh='cm']").count() > 0 or page.locator("div[role='button'][aria-label*='Compose']").count() > 0:
                    return True
                state = "inbox-loading"
            else:
                state = f"other:{url[:60]}"
            if state != last_state:
                log(f"[state] {state}")
                last_state = state
        except Exception:  # noqa: BLE001
            pass
        time.sleep(2)
    return False


def open_compose(page) -> bool:
    # Focus the page body so keyboard shortcuts work, then press 'c'.
    try:
        page.locator("div[role='main']").first.click(position={"x": 20, "y": 20}, timeout=5000)
    except Exception:  # noqa: BLE001
        pass
    page.keyboard.press("c")
    page.wait_for_timeout(2500)

    to_field = first_visible(
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
    if to_field is not None:
        return True

    log("compose not open after 'c'; trying Compose button...")
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
        except Exception:  # noqa: BLE001
            pass
    page.wait_for_timeout(2500)
    return first_visible(
        page,
        [
            "textarea[name='to']",
            "input[name='to']",
            "input[peoplekit-id]",
            "div[aria-label='To recipients']",
            "div[aria-label*='To recipients'] input",
        ],
        timeout_ms=15000,
    ) is not None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--to", required=True, help="recipient email")
    ap.add_argument("--attachment", required=True, help="path to file to attach")
    ap.add_argument("--subject", default="", help="email subject")
    ap.add_argument("--body", default="", help="email body (plain text)")
    ap.add_argument("--login-timeout", type=int, default=600, help="seconds to wait for manual login")
    args = ap.parse_args()

    attachment = Path(args.attachment).expanduser().resolve()
    if not attachment.exists():
        log(f"ATTACHMENT_MISSING: {attachment}")
        return 2
    log(f"attachment ready: {attachment} ({attachment.stat().st_size} bytes)")

    if not PROFILE_DIR.exists():
        log(f"PROFILE_DIR missing, creating: {PROFILE_DIR}")
        PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        context = p.webkit.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            viewport={"width": 1500, "height": 950},
            locale="en-US",
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto("https://mail.google.com/mail/u/0/#inbox", wait_until="domcontentloaded")

        if not wait_for_login(page, timeout_s=args.login_timeout):
            shot(page, "99_login_timeout")
            log("LOGIN_TIMEOUT: no authenticated inbox reached")
            context.close()
            return 3

        shot(page, "01_inbox")
        log(f"inbox url: {page.url}")

        if not open_compose(page):
            shot(page, "99_compose_failed")
            log("COMPOSE_NOT_OPEN")
            context.close()
            return 4

        log("compose window is open")
        shot(page, "02_compose_open")

        to_field = first_visible(
            page,
            [
                "textarea[name='to']",
                "input[name='to']",
                "input[peoplekit-id]",
                "div[aria-label='To recipients']",
                "div[aria-label*='To recipients'] input",
            ],
            timeout_ms=10000,
        )
        if to_field is None:
            log("TO_FIELD_NOT_FOUND")
            shot(page, "99_to_failed")
            context.close()
            return 5
        to_field.click()
        to_field.fill(args.to)
        page.keyboard.press("Tab")
        page.wait_for_timeout(500)

        if args.subject:
            log("filling subject...")
            subject_field = first_visible(
                page,
                [
                    "input[name='subjectbox']",
                    "input[aria-label='Subject']",
                    "input[placeholder='Subject']",
                ],
                timeout_ms=10000,
            )
            if subject_field is None:
                log("SUBJECT_FIELD_NOT_FOUND")
                shot(page, "99_subject_failed")
                context.close()
                return 6
            subject_field.click()
            subject_field.fill(args.subject)

        if args.body:
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
                page.keyboard.type(args.body)
            else:
                log("BODY_FIELD_NOT_FOUND (continuing)")

        log(f"attaching {attachment.name}...")
        try:
            file_input = page.locator("input[type='file']").first
            file_input.set_input_files(str(attachment), timeout=15000)
            log("set_input_files called")
        except Exception as exc:  # noqa: BLE001
            log(f"attach failed: {exc}")
            shot(page, "99_attach_failed")
            context.close()
            return 7

        # Give the upload time to finish before sending.
        page.wait_for_timeout(6000)
        shot(page, "03_before_send")

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
            return 8
        send_btn.click()
        log("send clicked; waiting for compose to close...")

        sent = False
        deadline = time.time() + 60
        while time.time() < deadline:
            try:
                dialog = page.locator("div[role='dialog']")
                body = page.locator("div[aria-label='Message Body']")
                if dialog.count() == 0 or body.count() == 0:
                    sent = True
                    break
            except Exception:  # noqa: BLE001
                pass
            time.sleep(1)

        shot(page, "04_after_send")
        context.close()

    if sent:
        log("SEND_OK")
        return 0
    log("SEND_UNCONFIRMED")
    return 9


if __name__ == "__main__":
    sys.exit(main())
