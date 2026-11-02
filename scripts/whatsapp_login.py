#!/usr/bin/env python3
"""
WhatsApp Web login session capture for Julius.

Opens WhatsApp Web in a visible Chromium window so the user can scan the QR code
with their phone. Once login completes, the authenticated session is written to
disk: a persistent Chromium profile plus a portable storage_state.json.

Reuse:
  Persistent profile: workspaces/whatsapp_session/profile
  Storage state:      workspaces/whatsapp_session/storage_state.json
"""

import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright


ROOT = Path(__file__).resolve().parent.parent
SESSION_DIR = ROOT / "workspaces" / "whatsapp_session"
PROFILE_DIR = SESSION_DIR / "profile"
STATE_FILE = SESSION_DIR / "storage_state.json"

LOGIN_TIMEOUT_S = 600  # up to 10 minutes to scan the QR

LOGGED_IN_SELECTORS = [
    'div[aria-label="Chat list"]',
    '[data-testid="chat-list"]',
    '#pane-side',
]


async def wait_for_login(page, timeout_s: int):
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout_s
    while loop.time() < deadline:
        for sel in LOGGED_IN_SELECTORS:
            try:
                await page.wait_for_selector(sel, timeout=1500)
                return sel
            except Exception:
                pass
        await asyncio.sleep(1)
    return None


async def main() -> int:
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
            ],
            viewport={"width": 1280, "height": 900},
        )
        page = context.pages[0] if context.pages else await context.new_page()
        try:
            print("[julius] navigating to https://web.whatsapp.com ...", flush=True)
            await page.goto("https://web.whatsapp.com", wait_until="domcontentloaded")
            print("[julius] browser window is open. Scan the QR code with your phone.", flush=True)
            matched = await wait_for_login(page, LOGIN_TIMEOUT_S)
            if matched:
                print(f"[julius] login detected (selector: {matched})", flush=True)
            else:
                print("[julius] login not detected within timeout; saving whatever state exists.", flush=True)
        finally:
            try:
                await context.storage_state(path=str(STATE_FILE))
                print(f"[julius] storage_state saved: {STATE_FILE}", flush=True)
            except Exception as exc:
                print(f"[julius] storage_state save failed: {exc}", flush=True)
            print(f"[julius] persistent profile: {PROFILE_DIR}", flush=True)
            await context.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
