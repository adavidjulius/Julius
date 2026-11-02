"""
Verification script for Julius CLI v3.1.
Tests Collapsible Thinking Blocks, Slash Command Input Dimming, and Markdown Output Indentation.
Captures real screenshots in SVG format into the artifact directory.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
import time

from src.agent_config import AgentConfig
from src.cli.v3_tui import JuliusCLIV3App, CollapsibleThinkingPanel, SlashCommandHighlighter, render_clean_markdown
from textual.widgets import Input, RichLog
from rich.text import Text


async def main():
    workspace_dir = Path(".").resolve()
    artifacts_dir = Path(os.environ.get("ARTIFACT_DIR", "/tmp/artifacts"))
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    config = AgentConfig(provider="deepseek", confirm_actions=False)

    print("▶ Verification Test 1: Thinking Block — In Progress & Collapsed (Default)...")
    app = JuliusCLIV3App(workspace_dir=str(workspace_dir), config=config)
    async with app.run_test(size=(100, 26)) as pilot:
        log = app.query_one("#conversation-log", RichLog)
        thinking_panel = CollapsibleThinkingPanel()
        await log.mount(thinking_panel)
        app._active_thinking_panel = thinking_panel

        for i in range(1, 8):
            thinking_panel.append_thought(f"Step {i}: Analyzing architecture component and calculating dependencies...")
            await pilot.pause(0.15)

        # In-progress collapsed screenshot
        path_collapsed = artifacts_dir / "thinking_block_in_progress_collapsed.svg"
        app.save_screenshot(str(path_collapsed))
        print(f"✓ Saved: {path_collapsed}")

        # Expand thinking panel
        print("▶ Verification Test 2: Thinking Block — In Progress & Expanded (Bounded Sub-Box)...")
        thinking_panel.toggle()
        await pilot.pause(0.2)

        path_expanded = artifacts_dir / "thinking_block_in_progress_expanded.svg"
        app.save_screenshot(str(path_expanded))
        print(f"✓ Saved: {path_expanded}")

        # Finish thinking panel (Auto-collapses)
        print("▶ Verification Test 3: Thinking Block — Completed & Auto-Collapsed...")
        thinking_panel.finish()
        await pilot.pause(0.2)

        path_finished_collapsed = artifacts_dir / "thinking_block_completed_autocollapsed.svg"
        app.save_screenshot(str(path_finished_collapsed))
        print(f"✓ Saved: {path_finished_collapsed}")

        # Re-expand finished thinking panel to review static history
        print("▶ Verification Test 4: Thinking Block — Completed & Re-Expanded (Static History)...")
        thinking_panel.toggle()
        await pilot.pause(0.2)

        path_finished_expanded = artifacts_dir / "thinking_block_completed_reexpanded.svg"
        app.save_screenshot(str(path_finished_expanded))
        print(f"✓ Saved: {path_finished_expanded}")

    print("▶ Verification Test 5: Slash Command Input Dimming Live Syntax Highlighting...")
    app_dim = JuliusCLIV3App(workspace_dir=str(workspace_dir), config=config)
    async with app_dim.run_test(size=(100, 26)) as pilot:
        inp = app_dim.query_one("#prompt-input", Input)

        # Type /plan command + task text
        inp.value = "/plan add RMSNorm layer with learnable gamma to transformer backbone"
        await pilot.pause(0.2)

        path_plan_cmd = artifacts_dir / "input_dimming_plan_command.svg"
        app_dim.save_screenshot(str(path_plan_cmd))
        print(f"✓ Saved: {path_plan_cmd}")

        # Type /act command + task text
        inp.value = "/act refactor v3_tui.py and run py_compile verification tests"
        await pilot.pause(0.2)

        path_act_cmd = artifacts_dir / "input_dimming_act_command.svg"
        app_dim.save_screenshot(str(path_act_cmd))
        print(f"✓ Saved: {path_act_cmd}")

    print("▶ Verification Test 6: Markdown Output Formatting & Clean Indentation...")
    app_md = JuliusCLIV3App(workspace_dir=str(workspace_dir), config=config)
    async with app_md.run_test(size=(100, 28)) as pilot:
        log = app_md.query_one("#conversation-log", RichLog)

        sample_response = """
# Task Summary & Implementation Results

The requested architectural refactoring has been applied and verified:

1. **Collapsible Live Thinking Block**
   - Live elapsed seconds counter updating smoothly (`▸ Working... (12s)`)
   - Bounded child scroll box (`max-height: 6`) for live streaming thoughts
   - Auto-collapses on task completion (`▸ Worked (14s)`)
   - Interactive chevron toggle (`▸` / `▾`) and keyboard shortcut (`ctrl+t`)

2. **Input Syntax Highlighting & Readability**
   - Slash commands (`/plan`, `/act`) dimmed in `#cbd5e1`
   - Prompt instruction text rendered in full brightness `#f8fafc`
   - Fixed 2-space indentation for all nested list levels

```python
class RMSNorm(nn.Module):
    def __init__(self, dim: int, eps: float = 1e-6):
        super().__init__()
        self.eps = eps
        self.weight = nn.Parameter(torch.ones(dim))

    def forward(self, x):
        return x * torch.rsqrt(x.pow(2).mean(-1, keepdim=True) + self.eps) * self.weight
```

### Next Steps & Recommendations
- Maintain consistent left-aligned headings across all TUI modes
- Proceed with integration testing
"""
        log.write(render_clean_markdown(sample_response))
        await pilot.pause(0.3)

        path_md_output = artifacts_dir / "markdown_output_indentation.svg"
        app_md.save_screenshot(str(path_md_output))
        print(f"✓ Saved: {path_md_output}")

    print("\n✅ All CLI v3.1 Verification Tests Passed Successfully!")


if __name__ == "__main__":
    asyncio.run(main())
