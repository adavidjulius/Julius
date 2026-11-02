#!/usr/bin/env python3
"""Send an email with an attachment from Gmail using Playwright WebKit.

Reuses webkit_profile (Safari engine) so the Gmail session is already
authenticated. This mirrors scripts/send_gmail_attachment_webkit.py, which
worked to send an attachment to recipient@example.com, but
accepts the recipient and attachment on the command line.

Usage:
    .venv/bin/python scripts/send_gmail_image_webkit.py \\
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
    p = LOG_DIR / f"gmail_webkit_send_{name}.png"
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


def wait_for_inbox(page, timeout_s: int) -> bool:
    log("waiting for inbox to load (log in manually if the window is on the sign-in page)...")
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            if page.locator("div[role='main']").count() > 0 and "mail.google.com" in (page.url or ""):
                return True
        except Exception:  # noqa: BLE001
            pass
        time.sleep(2)
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--to", required=True)
    ap.add_argument(
        "--attachment",
        required=False,
        default=[],
        action="append",
        help="Path to a file to attach (optional). Pass this flag once per file.",
    )
    ap.add_argument("--subject", default="")
    ap.add_argument("--body", default="")
    ap.add_argument("--login-timeout", type=int, default=300)
    args = ap.parse_args()

    raw_attachments = args.attachment or []
    attachments = [Path(p).expanduser().resolve() for p in raw_attachments]
    missing = [p for p in attachments if not p.exists()]
    if missing:
        for p in missing:
            log(f"ATTACHMENT_MISSING: {p}")
        return 2
    for a in attachments:
        log(f"attachment ready: {a} ({a.stat().st_size} bytes)")

    if not PROFILE_DIR.exists():
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

        if not wait_for_inbox(page, args.login_timeout):
            shot(page, "99_login_timeout")
            log("LOGIN_TIMEOUT")
            context.close()
            return 3
        shot(page, "01_inbox")
        log(f"inbox url: {page.url}")

        try:
            page.locator("div[role='main']").first.click(position={"x": 20, "y": 20}, timeout=5000)
        except Exception:  # noqa: BLE001
            pass

        log("opening compose via keyboard shortcut 'c'...")
        page.keyboard.press("c")
        page.wait_for_timeout(2500)
        shot(page, "02_after_c")

        to_selectors = [
            "textarea[name='to']",
            "input[name='to']",
            "input[peoplekit-id]",
            "div[aria-label='To recipients']",
            "div[aria-label*='To recipients'] input",
        ]
        compose_to = first_visible(page, to_selectors, timeout_ms=5000)
        if compose_to is None:
            log("compose not open after shortcut; trying Compose button...")
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
            shot(page, "03_after_compose_click")
            compose_to = first_visible(page, to_selectors, timeout_ms=15000)

        if compose_to is None:
            log("COMPOSE_NOT_OPEN")
            shot(page, "99_compose_failed")
            context.close()
            return 4

        log("compose window is open")
        compose_to.click()
        compose_to.fill(args.to)
        page.keyboard.press("Tab")
        page.wait_for_timeout(500)

        if args.subject:
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

        if attachments:
            names = ", ".join(a.name for a in attachments)
            log(f"attaching {names}...")
            try:
                file_input = page.locator("input[type='file']").first
                file_input.set_input_files([str(a) for a in attachments], timeout=30000)
                log("set_input_files called")
            except Exception as exc:  # noqa: BLE001
                log(f"attach failed: {exc}")
                shot(page, "99_attach_failed")
                context.close()
                return 6

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
            return 7
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

        shot(page, "05_after_send")
        context.close()

    if sent:
        log("SEND_OK")
        return 0
    log("SEND_UNCONFIRMED")
    return 8


if __name__ == "__main__":
    sys.exit(main())
