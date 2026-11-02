#!/usr/bin/env python3
"""
Julius Multi-Provider Session Manager & Remote Sync.
Allows you to log in to DeepSeek, Gemini, ChatGPT, etc. locally on macOS,
and automatically pushes the authenticated session and cookies to the remote Julius server.
"""

import argparse
import asyncio
import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

PROVIDERS = {
    "deepseek": {
        "name": "DeepSeek",
        "url": "https://chat.deepseek.com/",
        "cookie_domains": ["deepseek.com"],
    },
    "gemini": {
        "name": "Google Gemini",
        "url": "https://gemini.google.com/app",
        "cookie_domains": ["gemini.google.com", "google.com"],
    },
    "chatgpt": {
        "name": "ChatGPT",
        "url": "https://chatgpt.com/",
        "cookie_domains": ["chatgpt.com", "openai.com"],
    },
    "grok": {
        "name": "Grok",
        "url": "https://x.com/i/grok",
        "cookie_domains": ["x.com", "twitter.com"],
    },
}

PROJECT_DIR = Path(__file__).resolve().parent.parent
LOCAL_PROFILE = PROJECT_DIR / "chrome_profile"
REMOTE_HOST = os.getenv("JULIUS_REMOTE_HOST", "127.0.0.1")
REMOTE_USER = "ct2026503517"


def get_active_profile_name() -> str:
    local_state = LOCAL_PROFILE / "Local State"
    if local_state.exists():
        try:
            ls_data = json.loads(local_state.read_text(encoding="utf-8"))
            last = ls_data.get("profile", {}).get("last_used")
            if last and (LOCAL_PROFILE / last).is_dir():
                return last
        except Exception:
            pass
    if (LOCAL_PROFILE / "Profile 1").is_dir():
        return "Profile 1"
    return "Default"


def check_local_cookies() -> dict:
    status = {}
    active_prof = get_active_profile_name()
    cookie_db = LOCAL_PROFILE / active_prof / "Cookies"
    if not cookie_db.exists():
        cookie_db = LOCAL_PROFILE / active_prof / "Network" / "Cookies"
    if not cookie_db.exists():
        return status

    try:
        con = sqlite3.connect(f"file:{cookie_db}?immutable=1", uri=True)
        cur = con.cursor()
        cur.execute("SELECT DISTINCT host_key FROM cookies")
        hosts = [r[0] for r in cur.fetchall()]
        for prov_id, prov_info in PROVIDERS.items():
            has_cookie = any(
                any(d in h for d in prov_info["cookie_domains"])
                for h in hosts
            )
            status[prov_id] = has_cookie
        con.close()
    except Exception as e:
        status["error"] = str(e)
    return status


def push_to_remote() -> bool:
    print(f"\n🚀 Pushing session to remote Julius server ({REMOTE_HOST})...")
    # Clean lock files
    for lock in ["SingletonLock", "lockfile", "SingletonCookie", "SingletonSocket"]:
        for p in [LOCAL_PROFILE / lock, LOCAL_PROFILE / get_active_profile_name() / lock]:
            if p.exists():
                try:
                    p.unlink()
                except Exception:
                    pass

    expect_script = f"""#!/usr/bin/expect -f
set timeout 120
spawn rsync -avz --exclude="Singleton*" --exclude="lockfile" --exclude="*Cache*" --exclude="*.tflite" --exclude="optimization_guide*" {LOCAL_PROFILE}/ {REMOTE_USER}@{REMOTE_HOST}:~/.Julius/chrome_profile/
expect {{
    -re "(?i)password:" {{
        send "{REMOTE_USER}\\r"
        exp_continue
    }}
    eof
}}
catch wait result
exit [lindex $result 3]
"""
    scratch_dir = PROJECT_DIR / "scratch"
    scratch_dir.mkdir(exist_ok=True)
    exp_file = scratch_dir / "sync_profile_fast.exp"
    exp_file.write_text(expect_script)
    exp_file.chmod(0o755)

    res = subprocess.run([str(exp_file)], capture_output=True, text=True)
    if res.returncode == 0:
        # Also mirror to ~/.julius/browser_profile
        mirror_cmd = f"expect {scratch_dir}/remote_cmd.exp \"mkdir -p ~/.julius/browser_profile; cp -r ~/.Julius/chrome_profile/* ~/.julius/browser_profile/ 2>/dev/null; echo 'OK'\""
        subprocess.run(mirror_cmd, shell=True, capture_output=True)
        print("✅ Session successfully pushed to remote server!")
        return True
    else:
        print(f"❌ Rsync error:\n{res.stderr or res.stdout}")
        return False


def login_provider(provider_key: str):
    prov = PROVIDERS.get(provider_key.lower())
    if not prov:
        print(f"❌ Unknown provider '{provider_key}'. Available: {list(PROVIDERS.keys())}")
        return

    active_profile = get_active_profile_name()
    LOCAL_PROFILE.mkdir(parents=True, exist_ok=True)

    print("=" * 65)
    print(f"  Julius Authentication: {prov['name']}")
    print("=" * 65)
    print(f"▶ Target URL       : {prov['url']}")
    print(f"▶ Profile          : {active_profile}")
    print("-" * 65)

    chrome_binary = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    if not Path(chrome_binary).exists():
        print(f"❌ Google Chrome not found at {chrome_binary}")
        return

    cmd = [
        chrome_binary,
        f"--user-data-dir={LOCAL_PROFILE}",
        "--no-first-run",
        "--no-default-browser-check",
        f"--profile-directory={active_profile}",
        prov["url"],
    ]

    print("🌐 Launching native Google Chrome on your Mac...")
    print("\n" + "🔑" * 30)
    print(f"  1. Log in to {prov['name']} in the opened Chrome window.")
    print("  2. Complete login until you see the main chat interface.")
    print("  3. Press [ENTER] in this terminal (or close Chrome).")
    print("🔑" * 30 + "\n")

    proc = subprocess.Popen(cmd)
    try:
        input("👉 Press [ENTER] once you have logged in to save & sync:\n")
    except KeyboardInterrupt:
        print("\nAborting...")
    finally:
        if proc.poll() is None:
            print("💾 Closing browser to flush session cookies...")
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:
                proc.kill()

    time.sleep(1)
    (LOCAL_PROFILE / ".logged_in").touch()

    # Verify cookies
    cookies = check_local_cookies()
    if cookies.get(provider_key.lower()):
        print(f"🎉 Verified: {prov['name']} cookies detected locally!")
    else:
        print(f"⚠️ Note: {prov['name']} cookies may not have settled, pushing session data anyway...")

    push_to_remote()


def show_status():
    print("=" * 65)
    print("  Julius Account & Session Status")
    print("=" * 65)
    cookies = check_local_cookies()
    for prov_id, prov_info in PROVIDERS.items():
        has_local = cookies.get(prov_id, False)
        status_str = "✅ Logged in" if has_local else "❌ Not logged in"
        print(f"  {prov_info['name']:<18}: {status_str}")
    print("-" * 65)


def interactive_menu():
    while True:
        print("\n" + "=" * 55)
        print("  Julius Browser Session Manager")
        print("=" * 55)
        cookies = check_local_cookies()
        for i, (k, v) in enumerate(PROVIDERS.items(), 1):
            stat = " [Logged In ✅]" if cookies.get(k) else " [Not Logged In ❌]"
            print(f"  [{i}] Login to {v['name']}{stat}")
        print(f"  [{len(PROVIDERS) + 1}] Push Current Local Session to Remote Server")
        print(f"  [{len(PROVIDERS) + 2}] Show Session Status")
        print("  [0] Exit")
        print("-" * 55)

        choice = input("Select an option (0-6): ").strip()
        if choice == "0":
            break
        elif choice == "1":
            login_provider("deepseek")
        elif choice == "2":
            login_provider("gemini")
        elif choice == "3":
            login_provider("chatgpt")
        elif choice == "4":
            login_provider("grok")
        elif choice == str(len(PROVIDERS) + 1):
            push_to_remote()
        elif choice == str(len(PROVIDERS) + 2):
            show_status()
        else:
            print("Invalid option, try again.")


def main():
    parser = argparse.ArgumentParser(description="Julius Session Manager & Remote Sync")
    parser.add_argument("provider", nargs="?", default=None, help="deepseek, gemini, chatgpt, status, or push")
    args = parser.parse_args()

    if not args.provider:
        interactive_menu()
    elif args.provider == "status":
        show_status()
    elif args.provider in ("push", "sync"):
        push_to_remote()
    elif args.provider in PROVIDERS:
        login_provider(args.provider)
    else:
        print(f"Unknown command: {args.provider}")
        print(f"Choose from: {list(PROVIDERS.keys())}, status, push")


if __name__ == "__main__":
    main()
