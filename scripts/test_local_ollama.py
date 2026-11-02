#!/usr/bin/env python3
"""
Diagnostic & Connection Tool for Local LAN Ollama LLM.
Discovers and tests Ollama running on another laptop over the local Wi-Fi.
"""

import argparse
import asyncio
import json
import os
import re
import socket
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path
from dotenv import load_dotenv

# Ensure root .env is loaded
env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path, override=True)


def get_local_ip() -> str:
    """Get the local Wi-Fi IP address of this Mac."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Doesn't need to actually reach 8.8.8.8, just triggers route lookup
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


async def probe_ip(ip: str, port: int = 11434, timeout: float = 0.8) -> tuple[str, bool]:
    """Test TCP connection to an IP and port."""
    try:
        fut = asyncio.open_connection(ip, port)
        reader, writer = await asyncio.wait_for(fut, timeout=timeout)
        writer.close()
        await writer.wait_closed()
        return ip, True
    except Exception:
        return ip, False


async def scan_subnet_for_ollama(subnet_prefix: str) -> list[str]:
    """Scan /24 subnet for open Ollama port 11434."""
    tasks = [probe_ip(f"{subnet_prefix}.{i}") for i in range(1, 255)]
    results = await asyncio.gather(*tasks)
    return [ip for ip, is_open in results if is_open]


def query_ollama_tags(url: str, timeout: float = 4.0) -> list[str] | None:
    """Fetch installed model names from Ollama /api/tags."""
    clean_url = url.rstrip("/")
    api_url = f"{clean_url}/api/tags"
    req = urllib.request.Request(api_url, headers={"User-Agent": "Julius-LAN-Probe"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                return [m.get("name", "") for m in data.get("models", [])]
    except Exception as exc:
        return None
    return None


def test_ollama_generation(url: str, model: str) -> tuple[bool, str, float]:
    """Send a short test prompt to verify inference and measure speed."""
    clean_url = url.rstrip("/")
    api_url = f"{clean_url}/api/generate"
    payload = json.dumps({
        "model": model,
        "prompt": "Respond with the single word: READY",
        "stream": False,
        "options": {"num_predict": 10, "temperature": 0.1}
    }).encode("utf-8")
    req = urllib.request.Request(
        api_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            elapsed = time.time() - start
            data = json.loads(resp.read().decode("utf-8"))
            return True, data.get("response", "").strip(), elapsed
    except Exception as exc:
        return False, str(exc), time.time() - start


def update_env_file(ollama_url: str, model_name: str) -> None:
    """Update .env with detected OLLAMA_HOST and OLLAMA_MODEL."""
    if not env_path.exists():
        return
    text = env_path.read_text(encoding="utf-8")
    
    # Update OLLAMA_HOST
    if re.search(r'^OLLAMA_HOST=.*$', text, flags=re.MULTILINE):
        text = re.sub(r'^OLLAMA_HOST=.*$', f'OLLAMA_HOST="{ollama_url}"', text, flags=re.MULTILINE)
    else:
        text += f'\nOLLAMA_HOST="{ollama_url}"\n'

    # Update OLLAMA_MODEL
    if re.search(r'^OLLAMA_MODEL=.*$', text, flags=re.MULTILINE):
        text = re.sub(r'^OLLAMA_MODEL=.*$', f'OLLAMA_MODEL="{model_name}"', text, flags=re.MULTILINE)
    else:
        text += f'OLLAMA_MODEL="{model_name}"\n'

    env_path.write_text(text, encoding="utf-8")
    print(f"✅ Saved OLLAMA_HOST=\"{ollama_url}\" and OLLAMA_MODEL=\"{model_name}\" to {env_path}")


async def main():
    parser = argparse.ArgumentParser(description="Test local/LAN Ollama connection for Julius")
    parser.add_argument("--host", help="Specific host or IP (e.g. 127.0.0.1 or http://127.0.0.1:11434)")
    parser.add_argument("--scan", action="store_true", help="Scan local Wi-Fi subnet for Ollama devices")
    parser.add_argument("--save", action="store_true", help="Save discovered host & model to .env")
    args = parser.parse_args()

    mac_ip = get_local_ip()
    print("=" * 65)
    print(" 📡 JULIUS LOCAL LAN OLLAMA DIAGNOSTIC")
    print("=" * 65)
    print(f"💻 This MacBook IP: {mac_ip}")

    target_host = args.host or os.getenv("OLLAMA_HOST", "").strip()
    discovered_endpoints = []

    # If specific host provided or configured
    if target_host:
        clean = target_host if target_host.startswith("http") else f"http://{target_host}"
        if ":" not in clean.split("//")[1]:
            clean = f"{clean}:11434"
        print(f"🎯 Checking configured Ollama host: {clean} ...")
        models = query_ollama_tags(clean)
        if models is not None:
            discovered_endpoints.append((clean, models))
        else:
            print(f"   ❌ Could not reach Ollama at {clean}")

    # Multi-subnet discovery if requested or if configured host not responding
    if not discovered_endpoints or args.scan:
        subnets_to_scan = ["192.168.0", "192.168.195"]
        parts = mac_ip.split(".")
        if len(parts) == 4 and mac_ip != "127.0.0.1":
            local_prefix = ".".join(parts[:3])
            if local_prefix not in subnets_to_scan:
                subnets_to_scan.append(local_prefix)

        for prefix in subnets_to_scan:
            print(f"🔍 Scanning subnet {prefix}.0/24 for Ollama on port 11434...")
            active_ips = await scan_subnet_for_ollama(prefix)
            for ip in active_ips:
                url = f"http://{ip}:11434"
                models = query_ollama_tags(url)
                if models is not None and not any(e[0] == url for e in discovered_endpoints):
                    discovered_endpoints.append((url, models))

    # Also test localhost
    if not discovered_endpoints:
        local_models = query_ollama_tags("http://localhost:11434", timeout=1.0)
        if local_models is not None:
            discovered_endpoints.append(("http://localhost:11434", local_models))

    # Report results
    if not discovered_endpoints:
        print("\n❌ No active Ollama server detected on local network or configured host.")
        print("\n📋 TROUBLESHOOTING CHECKLIST FOR YOUR OTHER LAPTOP:")
        print("  1. Is Ollama running on that laptop?")
        print("     - Run in terminal: ollama serve (or check system tray)")
        print("  2. Did you set OLLAMA_HOST=0.0.0.0:11434 on that laptop?")
        print("     - Windows (PowerShell):")
        print("       [System.Environment]::SetEnvironmentVariable('OLLAMA_HOST', '0.0.0.0:11434', 'User')")
        print("       [System.Environment]::SetEnvironmentVariable('OLLAMA_ORIGINS', '*', 'User')")
        print("       (Then restart Ollama from the Windows taskbar tray!)")
        print("     - Linux:")
        print("       sudo systemctl edit ollama.service -> add Environment=\"OLLAMA_HOST=0.0.0.0:11434\"")
        print("     - macOS:")
        print("       launchctl setenv OLLAMA_HOST \"0.0.0.0:11434\"")
        print("  3. Windows Firewall:")
        print("     - Ensure port 11434 TCP is allowed through Windows Firewall on Private networks.")
        print(f"  4. Confirm both laptops are connected to the same Wi-Fi (Subnet {mac_ip[:mac_ip.rfind('.')]}.X).")
        return

    print(f"\n🎉 FOUND {len(discovered_endpoints)} OLLAMA SERVER(S):")
    for url, models in discovered_endpoints:
        print(f"\n  • Host: {url}")
        print(f"    Available Models ({len(models)}): {', '.join(models) if models else 'None (still pulling?)'}")
        
        if models:
            test_model = os.getenv("OLLAMA_MODEL", models[0])
            if test_model not in models:
                test_model = models[0]
            print(f"    ⚡ Testing inference with '{test_model}'...")
            ok, resp, duration = test_ollama_generation(url, test_model)
            if ok:
                print(f"    ✅ Inference response ({duration:.2f}s): {resp}")
                if args.save or not os.getenv("OLLAMA_HOST"):
                    update_env_file(url, test_model)
            else:
                print(f"    ❌ Inference failed: {resp}")


if __name__ == "__main__":
    asyncio.run(main())
