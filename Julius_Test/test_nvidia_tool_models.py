import asyncio
import os
import aiohttp
from typing import List, Tuple
from src.providers.nim import resolve_nvidia_api_key

tools = [
    {
        "type": "function",
        "function": {
            "name": "run_bash",
            "description": "Execute a shell command",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Command to run"},
                },
                "required": ["command"],
            },
        },
    }
]

# Candidate chat / instruct models from the NVIDIA catalog
CANDIDATES = [
    "nvidia/nemotron-3-ultra-550b-a55b",
    "nvidia/nemotron-3.5-lightning-30b-a3b",
    "nvidia/nemotron-nano-3-30b-a3b",
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
    "nvidia/nemotron-3.5-bolt-e4b",
    "nvidia/nemotron-3.5-super-vl-120b-a12b",
    "nvidia/llama-3.1-nemotron-51b-instruct",
    "nvidia/mistral-nemo-minitron-8b-8k-instruct",
    "nv-mistralai/mistral-nemo-12b-instruct",
    "deepseek-ai/deepseek-v4.1-flash",
    "deepseek-ai/deepseek-coder-6.7b-instruct",
    "google/gemma-3-12b-it",
    "google/gemma-3-4b-it",
    "google/gemma-4-31b-it",
    "ibm/granite-3.0-8b-instruct",
    "ibm/granite-34b-code-instruct",
    "meta/llama-3.2-90b-vision-instruct",
    "meta/muse-glimmer-30b",
    "minimaxai/minimax-m3.1-flash",
    "mistralai/codestral-22b-instruct-v0.1",
    "mistralai/mistral-7b-instruct-v0.3",
    "mistralai/mixtral-8x22b-v0.1",
    "stepfun-ai/step-5-preview",
    "writer/palmyra-creative-122b",
]

async def check_model(session: aiohttp.ClientSession, key: str, model: str) -> Tuple[str, bool, str]:
    url = "https://integrate.api.nvidia.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Run ls command using the run_bash tool."}],
        "tools": tools,
    }
    try:
        async with session.post(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            data = await resp.json()
            if resp.status == 200:
                choices = data.get("choices", [])
                if choices:
                    msg = choices[0].get("message", {})
                    tc = msg.get("tool_calls")
                    return model, bool(tc), f"tool_calls: {bool(tc)}"
                return model, False, "No choices"
            else:
                msg = data.get("message") or data.get("detail") or str(data)[:60]
                return model, False, f"HTTP {resp.status}: {msg}"
    except Exception as exc:
        return model, False, f"Error: {exc}"

async def main():
    key = resolve_nvidia_api_key()
    if not key:
        print("ERROR: No NVIDIA API key found")
        return

    async with aiohttp.ClientSession() as session:
        for m in CANDIDATES:
            model, ok, info = await check_model(session, key, m)
            status = "✅ SUPPORTED" if ok else "❌"
            print(f"{status} | {model:45} | {info}")
            await asyncio.sleep(1.5)  # Enforce NVIDIA 40 RPM pacing

if __name__ == "__main__":
    asyncio.run(main())

