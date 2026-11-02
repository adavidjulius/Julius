#!/usr/bin/env python3
"""
Julius Browser Login & Session Sync Tool.
Opens a headful Chromium browser on your Mac for the chosen provider (DeepSeek, ChatGPT, etc.).
Once logged in, it cleanly synchronizes your authenticated session directly to the remote Julius server.
"""

import argparse
import asyncio
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

# Available chat providers and their initial URLs & chat input selectors
PROVIDERS = {
    "deepseek": {
        "name": "DeepSeek",
        "url": "https://chat.deepseek.com/",
        "input_selector": 'textarea[placeholder], textarea#chat-input, div[role="textbox"]',
    },
    "chatgpt": {
        "name": "ChatGPT",
        "url": "https://chatgpt.com/",
        "input_selector": '#prompt-textarea, [contenteditable="true"], textarea',
    },
    "gemini": {
        "name": "Gemini",
        "url": "https://gemini.google.com/app",
        "input_selector": 'rich-textarea, .ql-editor, div[contenteditable="true"]',
    },
    "grok": {
        "name": "Grok",
        "url": "https://x.com/i/grok",
        "input_selector": 'textarea[aria-label*="Grok"], div[role="textbox"]',
    },
    "perplexity": {
        "name": "Perplexity",
        "url": "https://www.perplexity.ai/",
        "input_selector": 'textarea[placeholder*="Ask"]',
    },
}


async def login_and_sync(provider_key: str, remote_host: str = os.getenv("JULIUS_REMOTE_HOST", "127.0.0.1"), remote_user: str = "ct2026503517"):
    provider = PROVIDERS.get(provider_key.lower())
    if not provider:
        print(f"❌ Unknown provider '{provider_key}'. Choose from: {list(PROVIDERS.keys())}")
        sys.exit(1)

    project_dir = Path(__file__).resolve().parent.parent
    julius_home_profile = Path(os.path.expanduser("~/.julius/browser_profile"))
    julius_home_profile.mkdir(parents=True, exist_ok=True)
    local_profile = julius_home_profile
    legacy_profile = project_dir / "chrome_profile"
    legacy_profile.mkdir(parents=True, exist_ok=True)

    print("=" * 65)
    print(f"  Julius Authentication Portal: {provider['name']}")
    print("=" * 65)
    print(f"▶ Target URL       : {provider['url']}")
    print(f"▶ Active Profile   : {local_profile}")
    print(f"▶ Remote Sync Dest : {remote_user}@{remote_host}:~/Julius/chrome_profile/")
    print("-" * 65)

    # Detect active profile directory
    active_profile = "Default"
    local_state = local_profile / "Local State"
    if local_state.exists():
        try:
            import json
            ls_data = json.loads(local_state.read_text(encoding="utf-8"))
            last = ls_data.get("profile", {}).get("last_used")
            if last and (local_profile / last).is_dir():
                active_profile = last
        except Exception:
            pass
    elif (local_profile / "Profile 1").is_dir() and not (local_profile / "Default" / "IndexedDB").is_dir():
        active_profile = "Profile 1"

    chrome_binary = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    if Path(chrome_binary).exists():
        print("🌐 Launching native Google Chrome on your Mac (zero automation flags)...")
        print("   This bypasses Cloudflare/Arkose CAPTCHA loops and Google OAuth restrictions.")
        cmd = [
            chrome_binary,
            f"--user-data-dir={local_profile}",
            "--no-first-run",
            "--no-default-browser-check",
            f"--profile-directory={active_profile}",
            provider["url"],
        ]
        proc = subprocess.Popen(cmd)

        print("\n" + "🔑" * 30)
        print(f"  PLEASE LOG IN TO {provider['name'].upper()} IN THE GOOGLE CHROME WINDOW")
        print("  Solve any CAPTCHA challenge normally (it will pass without looping).")
        print("  Sign in with your email/password or Google account.")
        print("  Once you are on the main chat page, press [ENTER] below (or close Chrome).")
        print("🔑" * 30 + "\n")

        loop = asyncio.get_running_loop()
        enter_future = loop.run_in_executor(None, lambda: input("👉 Press [ENTER] once you have logged in to sync session to server:\n"))

        while proc.poll() is None and not enter_future.done():
            await asyncio.sleep(0.5)

        if proc.poll() is None:
            print("💾 Flushing session data and closing browser...")
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:
                proc.kill()
        else:
            print("💾 Browser closed by user. Saving session data...")

        (local_profile / ".logged_in").touch()
        (legacy_profile / ".logged_in").touch()
        # Mirror files to project legacy_profile for compatibility
        try:
            shutil.copytree(local_profile, legacy_profile, dirs_exist_ok=True, ignore=shutil.ignore_patterns("Singleton*", "lockfile"))
        except Exception:
            pass
        await asyncio.sleep(1)
    else:
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            print("❌ Playwright is required locally. Run: pip install playwright && playwright install chromium")
            sys.exit(1)

        print("🌐 Launching Chromium browser on your Mac (headful mode)...")
        async with async_playwright() as p:
            browser_args = [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                f"--profile-directory={active_profile}",
            ]

            context = await p.chromium.launch_persistent_context(
                user_data_dir=str(local_profile),
                headless=False,
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 900},
                args=browser_args,
                ignore_default_args=["--enable-automation"],
            )

            page = context.pages[0] if context.pages else await context.new_page()
            print(f"▶ Navigating to {provider['url']}...")
            await page.goto(provider["url"])

            input_sel = provider["input_selector"]
            print("\n" + "🔑" * 30)
            print(f"  PLEASE LOG IN TO {provider['name'].upper()} IN THE BROWSER WINDOW")
            print("  You can sign in with your email, password, phone, or Google account.")
            print("  This script is actively monitoring for the chat interface...")
            print("🔑" * 30 + "\n")

            async def is_authenticated() -> bool:
                url = page.url
                if "/sign_in" in url or "/login" in url:
                    return False
                try:
                    cnt = await page.locator(input_sel).count()
                    if cnt > 0 and await page.locator(input_sel).first.is_visible():
                        return True
                except Exception:
                    pass
                return False

            logged_in = False
            loop = asyncio.get_running_loop()
            enter_future = loop.run_in_executor(None, lambda: input("\n👉 Press [ENTER] after you finish logging in and see the chat box, or wait for auto-detection...\n"))

            for elapsed in range(300):
                if await is_authenticated():
                    logged_in = True
                    print("🎉 Chat interface detected! Authenticated session confirmed.")
                    break

                if enter_future.done():
                    if await is_authenticated():
                        logged_in = True
                        print("🎉 Authentication verified successfully!")
                        break
                    else:
                        print(f"⚠️ Not logged in yet! Current URL: {page.url}")
                        print("   Please complete login in the browser window first.")
                        enter_future = loop.run_in_executor(None, lambda: input("\n👉 Press [ENTER] once you are actually on the chat page...\n"))

                await asyncio.sleep(1)

            if not logged_in:
                print("⚠️ Timeout waiting for login. Closing browser...")
                await context.close()
                sys.exit(1)

            print(f"✅ Logged in successfully to {provider['name']}!")
            (local_profile / ".logged_in").touch()
            (legacy_profile / ".logged_in").touch()
            state_json = local_profile / "storage_state.json"
            try:
                await context.storage_state(path=str(state_json))
                shutil.copy2(state_json, legacy_profile / "storage_state.json")
                print(f"💾 Snapshot session state saved to {state_json}")
            except Exception as exc:
                print(f"⚠️ Could not dump storage_state: {exc}")

            await asyncio.sleep(2)
            print("💾 Saving session data...")
            await context.close()

            try:
                shutil.copytree(local_profile, legacy_profile, dirs_exist_ok=True, ignore=shutil.ignore_patterns("Singleton*", "lockfile"))
            except Exception:
                pass

    print("\n🚀 Synchronizing authenticated session to remote server...")
    
    # Clean up lock files before syncing
    for lock in ["SingletonLock", "lockfile", "SingletonCookie", "SingletonSocket"]:
        lock_path = local_profile / lock
        if lock_path.exists():
            try:
                lock_path.unlink()
            except Exception:
                pass

    # Run through expect to handle password ct2026503517
    expect_payload = f"""#!/usr/bin/expect -f
set timeout 120
spawn rsync -avz -e "ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null" --exclude=Singleton* --exclude=lockfile {local_profile}/ {remote_user}@{remote_host}:~/.Julius/chrome_profile/
expect {{
    -re "(?i)are you sure you want to continue" {{
        send "yes\\r"
        exp_continue
    }}
    -re "(?i)password:" {{
        send "{remote_user}\\r"
        exp_continue
    }}
    eof
}}
catch wait result
exit [lindex $result 3]
"""
    exp_file = project_dir / "scratch" / "sync_profile.exp"
    exp_file.write_text(expect_payload)
    exp_file.chmod(0o755)

    result = subprocess.run([str(exp_file)], capture_output=True, text=True)
    if result.returncode == 0:
        print(f"🎉 SUCCESS! {provider['name']} session is now active locally and on the remote server!")
        print(f"   Julius agent tasks will now execute with your authenticated account.")
    else:
        print(f"✅ Local session saved successfully in {local_profile}!")
        print(f"   Julius agent tasks on your Mac will now execute with your authenticated account.")
        print(f"   (Remote sync note: could not mirror to {remote_host}, which is normal if running locally)")


def main():
    parser = argparse.ArgumentParser(description="Julius Browser Login & Session Sync")
    parser.add_argument("provider", nargs="?", default="deepseek", help="Provider name (deepseek, chatgpt, gemini, grok, perplexity)")
    parser.add_argument("--host", default=os.getenv("JULIUS_REMOTE_HOST", "127.0.0.1"), help="Remote server host (default: loopback)")
    parser.add_argument("--user", default="ct2026503517", help="Remote server username (default: ct2026503517)")
    args = parser.parse_args()

    asyncio.run(login_and_sync(args.provider, args.host, args.user))


if __name__ == "__main__":
    main()
