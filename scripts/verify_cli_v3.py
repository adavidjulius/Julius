"""
Verification script for Julius CLI v3.
Launches JuliusCLIV3App in test mode across different widths and interactions,
capturing real screenshots for verification evidence.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
import time

from src.agent_config import AgentConfig
from src.cli.v3_tui import JuliusCLIV3App
from src.memory.storage import MemoryStorage
from src.memory.working_state import WorkingStateManager, TaskWorkingState
from src.ledger import Ledger


async def main():
    workspace_dir = Path(".").resolve()
    artifacts_dir = Path(os.environ.get("ARTIFACT_DIR", "/tmp/artifacts"))
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    # 1. Seed a real task into MemoryStorage & WorkingStateManager to verify Recent Activity
    storage = MemoryStorage(str(workspace_dir))
    storage.save_task(
        task_id="v3_verify_task_001",
        summary="Refactor CLI v3 layout and fix ask-user question UI",
        status="completed",
        files_modified=["src/cli/v3_tui.py", "src/cli/mode_registry.py"]
    )

    mgr = WorkingStateManager(workspace_dir)
    state = TaskWorkingState(
        task_id="v3_resume_task_002",
        project_id=str(workspace_dir),
        goal="Implement deep blue design system & slash commands",
        current_plan="1. Apply deep blue theme\n2. Add /experiments, /status, /resume, /undo",
        completed_subtasks=["1. Apply deep blue theme"],
        remaining_subtasks=["2. Add slash commands"],
        last_known_good_state="Deep blue theme applied successfully.",
        files_in_progress=["src/cli/v3_tui.py"],
        status="in_progress"
    )
    mgr.save_working_state(state)

    # Seed an experiment record into MemoryStorage
    storage.save_research_experiment({
        "experiment_id": "exp_v3_blue_identity",
        "hypothesis": "Deep Blue primary palette improves brand contrast and readability over Julius reskin",
        "mechanism_description": "Custom Textual CSS with double borders (#2563eb) and cyan/violet status badges",
        "nearest_known_architecture": "Julius Design System v3",
        "implementation_summary": "Created src/cli/v3_tui.py with double border MainSessionBox",
        "result_metrics": {"readability": 0.98, "visual_distinction": 1.0},
        "outcome": "passed",
    })

    # Seed a file mutation in Ledger for /undo test
    ledger = Ledger(str(workspace_dir))
    action_id = ledger.start_action("test edit", "Verification test edit")
    test_file = workspace_dir / "scratch" / "undo_test.txt"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text("Original content\n")
    ledger.snapshot_file(action_id, str(test_file))
    test_file.write_text("Modified content\n")

    config = AgentConfig(provider="deepseek", confirm_actions=False)

    print("▶ Capturing Screenshot 1: 80 Column Welcome Screen & Recent Activity...")
    app_80 = JuliusCLIV3App(workspace_dir=str(workspace_dir), config=config)
    async with app_80.run_test(size=(80, 24)) as pilot:
        await pilot.pause(0.5)
        path_80 = artifacts_dir / "welcome_screen_80col.svg"
        app_80.save_screenshot(str(path_80))
        print(f"✓ Saved: {path_80}")

    print("▶ Capturing Screenshot 2: 120 Column Welcome Screen Banner Alignment...")
    app_120 = JuliusCLIV3App(workspace_dir=str(workspace_dir), config=config)
    async with app_120.run_test(size=(120, 28)) as pilot:
        await pilot.pause(0.5)
        path_120 = artifacts_dir / "welcome_screen_120col.svg"
        app_120.save_screenshot(str(path_120))
        print(f"✓ Saved: {path_120}")

    print("▶ Capturing Screenshot 3: Triggered Ask-User Question UI...")
    app_q = JuliusCLIV3App(workspace_dir=str(workspace_dir), config=config)
    async with app_q.run_test(size=(100, 28)) as pilot:
        await pilot.pause(0.2)
        # Emit an ask_user_question event to trigger Magenta UI
        app_q._handle_agent_event({
            "type": "ask_user_question",
            "question": "The requested migration will overwrite database schemas. Which strategy would you prefer?",
            "options": [
                "1. Apply automatic schema migration with WAL backup",
                "2. Create a clean secondary database table",
                "3. Cancel migration and keep current schema"
            ]
        })
        await pilot.pause(0.5)
        path_q = artifacts_dir / "ask_user_question_ui.svg"
        app_q.save_screenshot(str(path_q))
        print(f"✓ Saved: {path_q}")

    print("▶ Capturing Screenshot 4: Slash Command /experiments...")
    app_exp = JuliusCLIV3App(workspace_dir=str(workspace_dir), config=config)
    async with app_exp.run_test(size=(100, 28)) as pilot:
        await pilot.pause(0.2)
        await pilot.press(*"/experiments")
        await pilot.press("enter")
        await pilot.pause(0.5)
        path_exp = artifacts_dir / "slash_command_experiments.svg"
        app_exp.save_screenshot(str(path_exp))
        print(f"✓ Saved: {path_exp}")

    print("▶ Capturing Screenshot 5: Slash Command /status...")
    app_st = JuliusCLIV3App(workspace_dir=str(workspace_dir), config=config)
    async with app_st.run_test(size=(100, 28)) as pilot:
        await pilot.pause(0.2)
        await pilot.press(*"/status")
        await pilot.press("enter")
        await pilot.pause(0.5)
        path_st = artifacts_dir / "slash_command_status.svg"
        app_st.save_screenshot(str(path_st))
        print(f"✓ Saved: {path_st}")

    print("▶ Capturing Screenshot 6: Slash Command /resume...")
    app_res = JuliusCLIV3App(workspace_dir=str(workspace_dir), config=config)
    async with app_res.run_test(size=(100, 28)) as pilot:
        await pilot.pause(0.2)
        await pilot.press(*"/resume")
        await pilot.press("enter")
        await pilot.pause(0.5)
        path_res = artifacts_dir / "slash_command_resume.svg"
        app_res.save_screenshot(str(path_res))
        print(f"✓ Saved: {path_res}")

    print("▶ Capturing Screenshot 7: Slash Command /undo...")
    app_un = JuliusCLIV3App(workspace_dir=str(workspace_dir), config=config)
    async with app_un.run_test(size=(100, 28)) as pilot:
        await pilot.pause(0.2)
        await pilot.press(*"/undo")
        await pilot.press("enter")
        await pilot.pause(0.5)
        path_un = artifacts_dir / "slash_command_undo.svg"
        app_un.save_screenshot(str(path_un))
        print(f"✓ Saved: {path_un}")

    print("\n✅ All 7 verification screenshots captured successfully.")


if __name__ == "__main__":
    asyncio.run(main())
