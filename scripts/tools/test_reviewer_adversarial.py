"""
Adversarial Stress Test Script for Milestone M1
Reviewed Target: src/llm_web_client.py
"""

import asyncio
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.llm_web_client import WebLLMClient, LLMResponse


async def stress_test():
    print("=== STARTING ADVERSARIAL STRESS TEST SUITE ===")
    client = WebLLMClient()
    await client.initialize("nvidia")

    # 1. Test empty prompt
    print("\n[TEST 1] Empty prompt")
    t0 = time.time()
    resp1 = await client.send_message("", timeout=45)
    print(f"Empty prompt status: success={resp1.success}, len={len(resp1.raw_text)}, elapsed={time.time() - t0:.2f}s")
    assert resp1.success, "Empty prompt failed"

    # 2. Test prompt with special chars & Unicode (indic, emojis, quotes)
    print("\n[TEST 2] Unicode, Indic & nested quotes")
    unicode_prompt = "Say 'Hello World' in Tamil (வணக்கம் உலகம்) and echo this JSON: {\"key\": \"value with 'quotes' & \\\"escapes\\\"\"}."
    t0 = time.time()
    resp2 = await client.send_message(unicode_prompt, timeout=45)
    print(f"Unicode prompt response preview: {resp2.raw_text[:120]} (elapsed={time.time() - t0:.2f}s)")
    assert resp2.success, "Unicode prompt failed"

    # 3. Test /plan prompt (plan mode)
    print("\n[TEST 3] /plan mode trigger")
    t0 = time.time()
    resp3 = await client.send_message("/plan Refactor logging subsystem in Julius", timeout=45)
    print(f"Plan mode response preview: {resp3.raw_text[:120]} (elapsed={time.time() - t0:.2f}s)")
    assert resp3.success, "Plan mode failed"

    # 4. Test send_message_with_image
    print("\n[TEST 4] send_message_with_image")
    t0 = time.time()
    resp4 = await client.send_message_with_image("What is in this image?", "/tmp/non_existent_dummy_image.png", timeout=45)
    print(f"Image prompt response preview: {resp4.raw_text[:120]} (elapsed={time.time() - t0:.2f}s)")
    assert resp4.success, "Image prompt failed"

    # 5. Test sequential rate limiter spacing
    print("\n[TEST 5] Sequential request pacing (checking >= 1.5s interval)")
    t_start = time.time()
    resp5_a = await client.send_message("Ping 1", timeout=30)
    t_mid = time.time()
    resp5_b = await client.send_message("Ping 2", timeout=30)
    t_end = time.time()
    interval = t_end - t_mid
    print(f"Spacing between sequential calls: {interval:.2f}s (must be >= 1.5s)")
    assert interval >= 1.45, f"Rate limiter spacing violation: {interval:.2f}s < 1.5s"

    # 6. Test conversation history reset
    print("\n[TEST 6] Conversation history reset")
    assert len(client._api_messages) > 0, "Messages should exist before reset"
    count_before = len(client._api_messages)
    await client.start_new_conversation()
    assert len(client._api_messages) == 0, "Messages should be empty after start_new_conversation()"
    assert client.message_count == 0, "Message count should be 0 after reset"
    print(f"History successfully reset from {count_before} messages to {len(client._api_messages)}.")

    # 7. Test clean close and re-initialization
    print("\n[TEST 7] Clean close & re-open")
    await client.close()
    assert not client.is_initialized, "Client should be uninitialized after close()"
    assert client._session is None, "Session should be None after close()"

    # Re-initialize and call
    await client.initialize("nvidia")
    assert client.is_initialized, "Client should be initialized after re-init"
    resp7 = await client.send_message("Reconnected test", timeout=30)
    assert resp7.success, "Reconnected call failed"
    print("Re-init after close successful!")

    await client.close()
    print("\n=== ALL ADVERSARIAL STRESS TESTS PASSED SUCCESSFULLY ===")


if __name__ == "__main__":
    asyncio.run(stress_test())
