#!/usr/bin/env python3
"""
Open Gmail in Playwright WebKit (Safari engine) and dump a structured
summary of the visible inbox rows: sender, subject, snippet, unread flag.
Writes logs/gmail_summary.json and prints a compact listing.
"""
import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parent.parent
PROFILE_DIR = ROOT / "webkit_profile"
LOG_DIR = ROOT / "logs"
OUT_JSON = LOG_DIR / "gmail_summary.json"
SHOT = LOG_DIR / "gmail_inbox_summary.png"

MAX_ROWS = 60


def extract_row(row):
    cls = row.get_attribute("class") or ""
    unread = "unread" in cls
    try:
        subject = row.locator(".bog").inner_text(timeout=1500).strip()
    except Exception:
        subject = ""
    try:
        sender_el = row.locator(".yW span[email], .yW span[name]").first
        sender = sender_el.inner_text(timeout=1500).strip()
        email = sender_el.get_attribute("email") or ""
    except Exception:
        sender, email = "", ""
    try:
        snippet = row.locator(".y2").inner_text(timeout=1500).strip()
    except Exception:
        snippet = ""
    try:
        date = row.locator(".xW span").first.inner_text(timeout=1500).strip()
    except Exception:
        date = ""
    return {
        "unread": unread,
        "sender": sender,
        "email": email,
        "subject": subject,
        "snippet": snippet,
        "date": date,
    }


def main() -> int:
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        context = p.webkit.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            viewport={"width": 1500, "height": 950},
            locale="en-US",
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto("https://mail.google.com/mail/u/0/#inbox", wait_until="domcontentloaded")

        deadline = time.time() + 240
        while time.time() < deadline:
            try:
                if page.locator("tr.zA").count() > 0:
                    break
            except Exception:
                pass
            time.sleep(2)

        rows = page.locator("tr.zA")
        total = rows.count()
        n = min(total, MAX_ROWS)

        items = []
        for i in range(n):
            try:
                items.append(extract_row(rows.nth(i)))
            except Exception as exc:
                items.append({"error": str(exc), "index": i})

        page.screenshot(path=str(SHOT), full_page=False)
        context.close()

    OUT_JSON.write_text(json.dumps({"total_visible": total, "count": len(items), "items": items}, indent=2))

    print(f"TOTAL_VISIBLE: {total}")
    print(f"WROTE: {OUT_JSON}")
    print(f"SHOT: {SHOT}")
    print("----")
    for i, it in enumerate(items, 1):
        flag = "*" if it.get("unread") else " "
        print(f"{flag} {i:2d}. {it.get('sender','')} <{it.get('email','')}> | {it.get('subject','')} | {it.get('date','')}")
        if it.get("snippet"):
            print(f"      {it['snippet']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
