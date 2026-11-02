#!/usr/bin/env python3
"""
End-to-end test script verifying:
1. AgentConfig construction with confirm_writes=True, deferred_writes=False, use_perception=True
2. Permission Gate triggering on write_file
3. Human approval via set_confirmation_result(True)
4. Successful creation of test_agent.txt containing 'Julius agent test passed.'
5. Playwright Chromium headless execution opening a public webpage and retrieving its page title.
"""
import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agent_config import AgentConfig
from src.web_agent import WebAgent
from src.llm_web_client import LLMResponse


async def test_full_pipeline():
    print("=" * 65)
    print("  Julius Full Agent Pipeline & Permission Gate Verification")
    print("=" * 65)

    workspace = Path.cwd()
    test_file = workspace / "test_agent.txt"
    if test_file.exists():
        test_file.unlink()

    # 1. Initialize AgentConfig with the exact parameters julius_gui.py passes
    print("\n[Step 1] Initializing AgentConfig with confirm_writes=True...")
    config = AgentConfig(
        provider="deepseek",
        max_steps=10,
        headless=True,
        confirm_actions=True,
        confirm_destructive_only=True,
        confirm_writes=True,
        deferred_writes=False,
        allowed_directory=str(workspace),
        profile_dir=str(workspace / "chrome_profile"),
        abort_hotkey="",
        use_perception=True,
    )
    print(f"✅ AgentConfig initialized successfully! Mode: {config.execution_mode}")
    print(f"   confirm_writes: {config.confirm_writes}")
    print(f"   confirm_actions: {config.confirm_actions}")

    # 2. Setup mock LLM responses to simulate step 1 (write_file), step 2 (browser via playwright), and step 3 (done)
    mock_client = MagicMock()
    mock_client.is_initialized = True
    mock_client.provider_name = "deepseek"
    mock_client.new_chat = AsyncMock()
    mock_client.close = AsyncMock()
    mock_client.check_login_status = AsyncMock(return_value=True)

    responses = [
        # Step 1: Write test_agent.txt
        LLMResponse(
            raw_text='{"thought": "Creating test_agent.txt with required content", "action": "write_file", "args": {"path": "test_agent.txt", "content": "Julius agent test passed."}}',
            parsed_json={"thought": "Creating test_agent.txt with required content", "action": "write_file", "args": {"path": "test_agent.txt", "content": "Julius agent test passed."}},
        ),
        # Step 2: Open webpage using Playwright Chromium and get title
        LLMResponse(
            raw_text=f'''{{"thought": "Using Playwright Chromium to fetch title of public webpage", "action": "run_bash", "args": {{"command": "{sys.executable} -c \\"import asyncio\\nfrom playwright.async_api import async_playwright\\nasync def check():\\n    async with async_playwright() as p:\\n        b = await p.chromium.launch(headless=True, args=['--no-sandbox'])\\n        page = await b.new_page()\\n        await page.goto('https://example.com')\\n        print('FETCHED_TITLE: ' + await page.title())\\n        await b.close()\\nasyncio.run(check())\\""}}}}''',
            parsed_json={"thought": "Using Playwright Chromium to fetch title of public webpage", "action": "run_bash", "args": {"command": f"{sys.executable} -c \"import asyncio\nfrom playwright.async_api import async_playwright\nasync def check():\n    async with async_playwright() as p:\n        b = await p.chromium.launch(headless=True, args=['--no-sandbox'])\n        page = await b.new_page()\n        await page.goto('https://example.com')\n        print('FETCHED_TITLE: ' + await page.title())\n        await b.close()\nasyncio.run(check())\""}},
        ),
        # Step 3: Done
        LLMResponse(
            raw_text='{"thought": "Task complete!", "action": "done", "args": {"summary": "Successfully created test_agent.txt and verified Playwright browser navigation."}}',
            parsed_json={"thought": "Task complete!", "action": "done", "args": {"summary": "Successfully created test_agent.txt and verified Playwright browser navigation."}},
        ),
    ]

    call_index = 0
    async def mock_send_message(*args, **kwargs):
        nonlocal call_index
        resp = responses[min(call_index, len(responses) - 1)]
        call_index += 1
        return resp

    mock_client.send_message = mock_send_message

    # 3. Create WebAgent and capture emitted events
    events = []
    def on_event(event):
        events.append(event)
        event_type = event.get("type")
        print(f"▶ Event Emitted: {event_type}")

    agent = WebAgent(config=config, on_event=on_event, shared_client=mock_client)

    # 4. Asynchronously handle the Permission Gate approval when confirm_action fires
    async def auto_approver():
        for _ in range(50):
            await asyncio.sleep(0.1)
            if agent._confirm_future and not agent._confirm_future.done():
                print("🔐 Permission Gate detected pending confirmation!")
                print(f"   In-flight action: {agent._current_in_flight_action}")
                print("👉 Approving action through Permission Gate...")
                agent.set_confirmation_result(True)

    approver_task = asyncio.create_task(auto_approver())

    # 5. Run agent task
    print("\n[Step 2] Executing Agent task...")
    result = await agent.run('Create a file called test_agent.txt containing: "Julius agent test passed."')
    await approver_task

    print(f"\n[Step 3] Agent Execution Result:")
    print(f"   Success: {result.success}")
    print(f"   Summary: {result.summary}")
    print(f"   Steps Count: {len(agent._steps)}")

    # 6. Verify Permission Gate fired
    confirm_events = [e for e in events if e.get("type") == "confirm_action"]
    print(f"\n[Step 4] Checking Permission Gate Events: {len(confirm_events)} found.")
    assert len(confirm_events) >= 1, "Expected at least one confirm_action event!"
    print(f"   Action confirmed: {confirm_events[0].get('action')}")

    # 7. Verify test_agent.txt was created and has exact content
    print("\n[Step 5] Verifying test_agent.txt on disk...")
    assert test_file.exists(), "test_agent.txt was not created!"
    content = test_file.read_text().strip()
    print(f"   File Content: '{content}'")
    assert content == "Julius agent test passed.", f"Unexpected file content: {content}"
    print("✅ test_agent.txt verified with exact expected content!")

    # 8. Verify Playwright Chromium step
    print("\n[Step 6] Verifying Playwright Chromium execution step...")
    step_results = [s.result for s in agent._steps if s.action == "run_bash"]
    print(f"   Bash step results: {step_results}")
    assert any("FETCHED_TITLE: Example Domain" in r for r in step_results), "Playwright page title was not found in step results!"
    print("✅ Playwright Chromium public webpage title verified: 'Example Domain'!")

    print("\n" + "=" * 65)
    print("🎉 ALL END-TO-END VERIFICATION CHECKS PASSED!")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(test_full_pipeline())
