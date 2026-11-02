"""
Verification script for Julius CLI matched to Julius Visual Style.
Captures real SVG screenshots across multiple CLI states into the conversation artifact directory.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from src.agent_config import AgentConfig
from src.cli.v3_tui import JuliusCLIV3App, CollapsibleThinkingPanel, render_clean_markdown
from textual.widgets import Input, RichLog
from rich.text import Text


async def main():
    workspace_dir = Path(".").resolve()
    artifacts_dir = Path(os.environ.get("ARTIFACT_DIR", "/tmp/artifacts"))
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    config = AgentConfig(provider="deepseek", confirm_actions=False)

    print("▶ Verification Test 1: Restyled Welcome Screen (2-Column Mascot + Quick Tips + Title Bar + Footer)...")
    app_welcome = JuliusCLIV3App(workspace_dir=str(workspace_dir), config=config)
    async with app_welcome.run_test(size=(110, 30)) as pilot:
        await pilot.pause(0.3)
        path_welcome = artifacts_dir / "julius_style_welcome_screen.svg"
        app_welcome.save_screenshot(str(path_welcome))
        print(f"✓ Saved: {path_welcome}")

    print("▶ Verification Test 2: Thinking Panel & Amber Status Line...")
    app_thinking = JuliusCLIV3App(workspace_dir=str(workspace_dir), config=config)
    async with app_thinking.run_test(size=(110, 30)) as pilot:
        log = app_thinking.query_one("#conversation-log", RichLog)
        
        # User prompt turn
        user_turn = Text()
        user_turn.append("> ", style="bold #f59e0b")
        user_turn.append("/plan ", style="dim #f59e0b")
        user_turn.append("Implement RMSNorm residual connection with learnable parameters", style="bold #f8fafc")
        log.write(user_turn)

        thinking_panel = CollapsibleThinkingPanel()
        await log.mount(thinking_panel)
        app_thinking._active_thinking_panel = thinking_panel

        for i in range(1, 5):
            thinking_panel.append_thought(f"Step {i}: Inspecting attention module parameters and calculating gradient graphs...")
            await pilot.pause(0.15)

        path_thinking = artifacts_dir / "julius_style_thinking_state.svg"
        app_thinking.save_screenshot(str(path_thinking))
        print(f"✓ Saved: {path_thinking}")

    print("▶ Verification Test 3: Real Ask-Human Question UI...")
    app_question = JuliusCLIV3App(workspace_dir=str(workspace_dir), config=config)
    async with app_question.run_test(size=(110, 30)) as pilot:
        app_question._handle_agent_event({
            "type": "ask_user_question",
            "question": "Which optimizer configuration should be applied for training stability?",
            "options": [
                "1. AdamW with Cosine Annealing (lr=3e-4, weight_decay=0.01)",
                "2. Adafactor with Relative Step Size",
                "3. SGD with Momentum & Nesterov"
            ]
        })
        await pilot.pause(0.3)

        path_question = artifacts_dir / "julius_style_ask_human_question.svg"
        app_question.save_screenshot(str(path_question))
        print(f"✓ Saved: {path_question}")

    print("▶ Verification Test 4: Real File-Edit Diff & Assistant Turn Prefix...")
    app_diff = JuliusCLIV3App(workspace_dir=str(workspace_dir), config=config)
    async with app_diff.run_test(size=(110, 32)) as pilot:
        log = app_diff.query_one("#conversation-log", RichLog)

        user_turn = Text()
        user_turn.append("> ", style="bold #f59e0b")
        user_turn.append("/act ", style="dim #f59e0b")
        user_turn.append("Update src/models/rmsnorm.py with epsilon normalization", style="bold #f8fafc")
        log.write(user_turn)

        old_code = "def forward(self, x):\n    return x * self.weight"
        new_code = "def forward(self, x):\n    variance = x.pow(2).mean(-1, keepdim=True)\n    return x * torch.rsqrt(variance + self.eps) * self.weight"

        app_diff._render_stage4_diff("src/models/rmsnorm.py", old_code, new_code)
        
        # Assistant response turn marker
        log.write(Text("● ", style="bold #f59e0b"))
        log.write(render_clean_markdown("Refactored `RMSNorm` forward pass to apply standard RMS scale before multiplying learnable weights."))

        await pilot.pause(0.3)

        path_diff = artifacts_dir / "julius_style_file_diff.svg"
        app_diff.save_screenshot(str(path_diff))
        print(f"✓ Saved: {path_diff}")

    print("▶ Verification Test 5: Slash Command Output (/status)...")
    app_status = JuliusCLIV3App(workspace_dir=str(workspace_dir), config=config)
    async with app_status.run_test(size=(110, 30)) as pilot:
        app_status._handle_status_command()
        await pilot.pause(0.3)

        path_status = artifacts_dir / "julius_style_slash_commands.svg"
        app_status.save_screenshot(str(path_status))
        print(f"✓ Saved: {path_status}")

    print("\n✅ All Julius Visual Style Verification Tests Completed Successfully!")


if __name__ == "__main__":
    asyncio.run(main())
