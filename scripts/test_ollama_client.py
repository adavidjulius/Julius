#!/usr/bin/env python3
"""
Seamless Cross-Device Ollama Client & Health-Check Harness for macOS.
Connects to the Windows LLM host over the local Wi-Fi network.
"""

import os
import sys
import time
import json
import urllib.request
import urllib.error

BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
MODEL = os.getenv("OLLAMA_MODEL", "mannix/llama3.1-8b-lexi:latest")
TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "60"))

def check_health():
    url = f"{BASE_URL}/api/tags"
    print(f"[*] Checking server health at {url}...")
    t0 = time.time()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Julius-Client/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            elapsed = (time.time() - t0) * 1000
            print(f"[+] Server reachable ({elapsed:.1f}ms). Found {len(data.get('models', []))} models.")
            model_names = [m["name"] for m in data.get("models", [])]
            for name in model_names:
                print(f"  - {name}")
            if MODEL not in model_names and not any(MODEL in name for name in model_names):
                print(f"[!] Warning: Configured model '{MODEL}' not found in active model list!")
            return True
    except urllib.error.URLError as e:
        print(f"[-] Connection error: {e.reason}")
        return False
    except Exception as e:
        print(f"[-] Unexpected error: {e}")
        return False

def run_inference(prompt="Explain why cross-platform architecture is efficient in 2 sentences."):
    url = f"{BASE_URL}/api/chat"
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "options": {"num_ctx": 8192},
        "stream": True
    }
    print(f"\n[*] Sending streaming inference request to model '{MODEL}'...")
    data_bytes = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data_bytes,
        headers={"Content-Type": "application/json", "User-Agent": "Julius-Client/1.0"}
    )
    
    t0 = time.time()
    first_token_time = None
    tokens_received = 0
    full_response = []
    
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            for line in resp:
                if not line:
                    continue
                chunk = json.loads(line.decode("utf-8"))
                msg = chunk.get("message", {})
                token = msg.get("content", "")
                if token:
                    if first_token_time is None:
                        first_token_time = time.time() - t0
                    print(token, end="", flush=True)
                    full_response.append(token)
                    tokens_received += 1
                if chunk.get("done", False):
                    eval_count = chunk.get("eval_count", tokens_received)
                    eval_duration_ns = chunk.get("eval_duration", 0)
                    print("\n")
                    print("-" * 45)
                    print(f"[+] Time to First Token (TTFT): {first_token_time:.3f}s" if first_token_time else "")
                    print(f"[+] Total Wall Time: {time.time() - t0:.2f}s")
                    if eval_duration_ns > 0:
                        tps = eval_count / (eval_duration_ns / 1e9)
                        print(f"[+] Generation Throughput: {tps:.2f} tokens/sec")
                    print(f"[+] Tokens Generated: {eval_count}")
                    return True
    except Exception as e:
        print(f"\n[-] Inference failed: {e}")
        return False

if __name__ == "__main__":
    if not check_health():
        sys.exit(1)
    success = run_inference()
    sys.exit(0 if success else 1)
