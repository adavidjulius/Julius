#!/usr/bin/env python3
"""
Open Gmail in Playwright WebKit (Safari engine) and report new mail.
Uses a persistent profile so login is remembered between runs.
The window is visible so the user can sign in themselves if needed.
"""
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


PROFILE_DIR = Path(__file__).resolve().parent.parent / "webkit_profile"
SHOT_DIR = Path(__file__).resolve().parent.parent / "logs"


def main() -> int:
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    SHOT_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        context = p.webkit.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            viewport={"width": 1400, "height": 900},
            locale="en-US",
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto("https://mail.google.com/mail/u/0/#inbox", wait_until="domcontentloaded")

        print("Waiting up to 5 minutes for the Gmail inbox to be visible.")
        print("If a sign-in screen appears, please log in in the open WebKit window.")

        deadline = time.time() + 300
        inbox_ready = False
        while time.time() < deadline:
            try:
                rows = page.locator("tr.zA")
                if rows.count() > 0:
                    inbox_ready = True
                    break
            except Exception:
                pass
            time.sleep(2)

        shot = SHOT_DIR / "gmail_inbox.png"
        page.screenshot(path=str(shot), full_page=False)
        print(f"Screenshot: {shot}")

        if not inbox_ready:
            print("INBOX_NOT_LOADED")
            print("Current URL:", page.url)
            print("Current title:", page.title())
            context.close()
            return 2

        rows = page.locator("tr.zA")
        count = min(rows.count(), 20)
        print(f"UNREAD_OR_INBOX_ROWS: {rows.count()}")
        print("---- first rows ----")
        for i in range(count):
            row = rows.nth(i)
            try:
                unread = "unread" in (row.get_attribute("class") or "")
                subject = row.locator(".bog").inner_text(timeout=1000).strip()
            except Exception:
                subject = "(no subject)"
                unread = False
            try:
                sender = row.locator(".yW span[email], .yW span[name]").first.inner_text(timeout=1000).strip()
            except Exception:
                sender = "(unknown sender)"
            flag = "* " if unread else "  "
            print(f"{flag}{i + 1:2d}. {sender}  |  {subject}")

        context.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
