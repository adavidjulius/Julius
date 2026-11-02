#!/usr/bin/env python3
"""
End-to-end verification of the Julius TUI client against the live Julius server.
Submits: "Hello, explain what Raspberry Pi is in one sentence."
Asserts:
1. WebSocket connection succeeds
2. Gemini connection succeeds
3. Step 1 renders without exception
4. No RichLog.write(... end=...) exception occurs
5. Retries are not triggered by this error
6. Final agent output reaches the TUI
"""

import asyncio
import os
import sys
from pathlib import Path

# Ensure project root is in PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from textual.widgets import Input
from src.tui.app import JuliusTUI, StreamPanel, PermissionPanel


async def main():
    print("=" * 60)
    print("Starting Julius TUI End-to-End Task Verification")
    print("Task: 'Hello, explain what Raspberry Pi is in one sentence.'")
    print("=" * 60)

    ws_url = "ws://localhost:8080/ws"
    workspace = str(Path.cwd())

    app = JuliusTUI(workspace=workspace, ws_url=ws_url)

    connection_succeeded = False
    step_1_rendered = False
    stream_events_received = 0
    no_end_kwarg_error = True
    retry_triggered = False
    task_done = False
    done_summary = ""
    error_occurred = False
    error_msg = ""

    captured_logs = []

    async with app.run_test(size=(120, 40)) as pilot:
        stream_panel = app.query_one("#stream-panel", StreamPanel)
        task_input = app.query_one("#task-input", Input)

        # Hook StreamPanel.write to monitor log output for errors or retries
        orig_write = stream_panel.write

        def monitored_write(*args, **kwargs):
            content = args[0] if args else ""
            s = str(content)
            captured_logs.append(s)
            print(f"[TUI StreamPanel Log] {s[:140]}")
            if "RichLog.write() got an unexpected keyword argument" in s:
                nonlocal no_end_kwarg_error
                no_end_kwarg_error = False
            if "Retrying in 3s" in s:
                nonlocal retry_triggered
                retry_triggered = True
            return orig_write(*args, **kwargs)

        stream_panel.write = monitored_write

        # Hook StreamPanel.add_event to monitor incoming backend events
        orig_add_event = stream_panel.add_event

        def monitored_add_event(event_type: str, data: dict):
            nonlocal connection_succeeded, step_1_rendered, stream_events_received, task_done, done_summary, error_occurred, error_msg
            print(f"[TUI Event Received] Type={event_type} | Data keys={list(data.keys())}")
            if event_type == "step_start" and data.get("step") == 1:
                step_1_rendered = True
            elif event_type == "stream":
                stream_events_received += 1
            elif event_type == "done":
                task_done = True
                done_summary = data.get("summary", "")
            elif event_type == "error":
                error_occurred = True
                error_msg = data.get("message", "")
            return orig_add_event(event_type, data)

        stream_panel.add_event = monitored_add_event

        # Wait for WebSocket connection to establish
        print("Waiting for TUI to establish WebSocket connection...")
        for _ in range(20):
            if app._ws is not None and not app._ws.closed:
                connection_succeeded = True
                break
            await asyncio.sleep(0.5)

        if not connection_succeeded:
            print("❌ FAILED: Could not connect to WebSocket within 10s")
            sys.exit(1)

        print("✅ WebSocket connected successfully!")

        # Submit task
        task_text = "Hello, explain what Raspberry Pi is in one sentence."
        print(f"Submitting task: {task_text}")
        task_input.value = task_text
        await app.on_input_submitted(Input.Submitted(task_input, task_text))

        # Wait for task completion or max 120s
        print("Waiting for task execution...")
        max_wait = 120
        elapsed = 0
        while elapsed < max_wait:
            await asyncio.sleep(1)
            elapsed += 1

            # Auto-approve permission gates if any
            perm_panel = app.query_one("#perm-panel", PermissionPanel)
            if perm_panel.pending_question:
                print(f"🔐 Permission gate prompted: {perm_panel.pending_question} -> Auto-approving...")
                await app.action_allow()

            if task_done:
                print(f"✅ Task reached 'done' state at {elapsed}s!")
                break
            if error_occurred:
                print(f"⚠️ Task emitted error: {error_msg}")
                break

        print("\n" + "=" * 60)
        print("VERIFICATION RESULTS:")
        print(f"- WebSocket connection succeeded: {connection_succeeded}")
        print(f"- Step 1 rendered: {step_1_rendered}")
        print(f"- Stream events received: {stream_events_received}")
        print(f"- No 'end' kwarg exception: {no_end_kwarg_error}")
        print(f"- Retries not triggered: {not retry_triggered}")
        print(f"- Final agent output reached TUI: {task_done}")
        print(f"- Final summary: {done_summary}")
        print("=" * 60)

        assert connection_succeeded, "WebSocket failed to connect"
        assert step_1_rendered, "Step 1 was not rendered"
        assert no_end_kwarg_error, "RichLog.write() 'end' error was raised!"
        assert not retry_triggered, "Retries were triggered by an error!"
        assert task_done, "Task did not complete with 'done' status"

        print("🎉 ALL VERIFICATION CRITERIA PASSED!")


if __name__ == "__main__":
    asyncio.run(main())
