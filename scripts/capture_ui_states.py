"""
Script to capture SVG snapshots of all key UI states in JuliusApp:
1. Standard UI states (welcome_dark, welcome_light, thinking, streaming, done, error, collapsed_tools, expanded_tools)
2. Full-bleed layout pilot snapshots at widths [60, 80, 120, 160, 220] for:
   - welcome screen
   - thinking
   - finished answer
   - long answer with code block
"""

import asyncio
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rich.text import Text
from textual.containers import ScrollableContainer

from src.agent_config import AgentConfig
from src.tui.app import JuliusApp
from src.tui.components.message import UserMessage, AssistantMessage, ThinkingDot
from src.tui.components.tool_summary import ToolSummary
from src.tui.state import ToolExecutionRecord


DOCS_DIR = Path("docs/screenshots")
DOCS_DIR.mkdir(parents=True, exist_ok=True)

ARTIFACT_DIR = Path(os.environ.get("ARTIFACT_DIR", "/tmp/artifacts/screenshots"))
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)


async def capture_state(name: str, app: JuliusApp, setup_fn=None, width: int = 80, height: int = 24):
    async with app.run_test(size=(width, height)) as pilot:
        if setup_fn:
            await setup_fn(app, pilot)
        await pilot.pause(0.1)
        svg_content = app.export_screenshot(title=f"Julius - {name}")
        out_file = DOCS_DIR / f"{name}.svg"
        out_file.write_text(svg_content, encoding="utf-8")
        # Also copy to artifacts directory
        artifact_file = ARTIFACT_DIR / f"{name}.svg"
        artifact_file.write_text(svg_content, encoding="utf-8")
        print(f"Captured: {out_file} (size: {width}x{height})")


async def main():
    # ── 1. Standard States ───────────────────────────────────────────────────
    # 1. Welcome - Dark
    app_welcome_dark = JuliusApp(workspace_dir=".", config=AgentConfig())
    await capture_state("welcome_dark", app_welcome_dark, width=120)

    # 2. Welcome - Light
    from src.tui.config import JuliusConfig
    app_welcome_light = JuliusApp(workspace_dir=".", config=AgentConfig(), app_config=JuliusConfig(theme="light"))
    await capture_state("welcome_light", app_welcome_light, width=120)

    # 3. Thinking State
    app_thinking = JuliusApp(workspace_dir=".", config=AgentConfig())
    async def setup_thinking(app, pilot):
        conv = app.query_one("#conversation-area", ScrollableContainer)
        await conv.mount(UserMessage("Implement Apple-style design tokens and full-bleed layout"))
        dot = ThinkingDot("Thinking")
        await conv.mount(dot)
        await pilot.pause(0.05)
    await capture_state("thinking", app_thinking, setup_thinking, width=120)

    # 4. Streaming State
    app_streaming = JuliusApp(workspace_dir=".", config=AgentConfig())
    async def setup_streaming(app, pilot):
        conv = app.query_one("#conversation-area", ScrollableContainer)
        await conv.mount(UserMessage("What are the core design tokens?"))
        asst = AssistantMessage(
            "The design tokens are organized into three distinct layers:\n\n"
            "* **Background**: Base terminal shade\n"
            "* **Surface**: Derived with ~4% lightness shift\n"
            "* **Raised**: Derived with ~8% lightness shift\n\n"
            "```python\n@dataclass(frozen=True)\nclass ThemeTokens:\n    bg: str\n    surface: str\n    raised: str\n```",
            theme=app.active_theme,
        )
        await conv.mount(asst)
        await pilot.pause(0.05)
    await capture_state("streaming", app_streaming, setup_streaming, width=120)

    # 5. Done State
    app_done = JuliusApp(workspace_dir=".", config=AgentConfig())
    async def setup_done(app, pilot):
        conv = app.query_one("#conversation-area", ScrollableContainer)
        await conv.mount(UserMessage("Verify tests and output deduplication"))
        tools = [
            ToolExecutionRecord("read_file", "Read src/agent_config.py", 0.3),
            ToolExecutionRecord("run_bash", "Ran bash: pytest tests/test_julius_tui.py (1.2s)", 1.2),
        ]
        tool_sum = ToolSummary(tools, total_duration_s=1.5)
        await conv.mount(tool_sum)
        asst = AssistantMessage("I ran the test suite and verified that every response appears exactly once. All unit tests are passing with full bleed width.", theme=app.active_theme)
        await conv.mount(asst)
        await pilot.pause(0.05)
    await capture_state("done", app_done, setup_done, width=120)

    # 6. Error State
    app_error = JuliusApp(workspace_dir=".", config=AgentConfig())
    async def setup_error(app, pilot):
        conv = app.query_one("#conversation-area", ScrollableContainer)
        await conv.mount(UserMessage("Connect to cluster host 127.0.0.1"))
        from textual.widgets import Static
        await conv.mount(Static(Text("I couldn't reach the model. Check your connection and press Enter to try again.", style="bold #ff453a")))
        await pilot.pause(0.05)
    await capture_state("error", app_error, setup_error, width=120)

    # 7. Collapsed Tool Steps
    app_collapsed = JuliusApp(workspace_dir=".", config=AgentConfig())
    async def setup_collapsed(app, pilot):
        conv = app.query_one("#conversation-area", ScrollableContainer)
        tools = [
            ToolExecutionRecord("run_bash", "Ran bash: git status", 0.2),
            ToolExecutionRecord("run_bash", "Ran bash: pytest (0.9s)", 0.9),
        ]
        ts = ToolSummary(tools, total_duration_s=1.1)
        await conv.mount(ts)
        asst = AssistantMessage("Clean git working directory and all unit tests passed.", theme=app.active_theme)
        await conv.mount(asst)
        await pilot.pause(0.05)
    await capture_state("collapsed_tools", app_collapsed, setup_collapsed, width=120)

    # 8. Expanded Tool Steps
    app_expanded = JuliusApp(workspace_dir=".", config=AgentConfig())
    async def setup_expanded(app, pilot):
        conv = app.query_one("#conversation-area", ScrollableContainer)
        tools = [
            ToolExecutionRecord("read_file", "Read src/tui/theme.py", 0.2),
            ToolExecutionRecord("run_bash", "Ran bash: pytest (1.4s)", 1.4),
        ]
        ts = ToolSummary(tools, total_duration_s=1.6)
        ts.expanded = True
        await conv.mount(ts)
        asst = AssistantMessage("Inspected design tokens and verified responsive layout.", theme=app.active_theme)
        await conv.mount(asst)
        await pilot.pause(0.05)
    await capture_state("expanded_tools", app_expanded, setup_expanded, width=120)

    # 9. Clean Julius Conversation Flow (Permission & Clarification)
    app_flow = JuliusApp(workspace_dir=".", config=AgentConfig())
    async def setup_flow(app, pilot):
        conv = app.query_one("#conversation-area", ScrollableContainer)
        # 1. Initial user request
        await conv.mount(UserMessage("i want you to delete all the temprory files in my mac"))
        # 2. Quiet host access request
        await conv.mount(AssistantMessage("Action `run_bash` requested access outside the workspace folder.\n\nAllow un-sandboxed access across your Mac? (y/n)", theme=app.active_theme))
        # 3. User reply
        await conv.mount(UserMessage("y"))
        # 4. Clarification options
        await conv.mount(AssistantMessage("I found ~1.8G of caches on your Mac. Safe to delete (all regenerable):\n\n- **a**: Delete all of the above\n- **b**: Delete only pip, Homebrew, and Python caches\n- **c**: List which ones", theme=app.active_theme))
        # 5. User reply
        await conv.mount(UserMessage("a"))
        # 6. Tool summary
        tools = [ToolExecutionRecord("run_bash", "Cleared ~1.8G temporary files across /Library/Caches", 0.2)]
        ts = ToolSummary(tools, total_duration_s=0.2)
        await conv.mount(ts)
        # 7. Final response
        await conv.mount(AssistantMessage("Done. I cleared temporary files across your Mac and permanently deleted them.\n\nWhat was removed (~1.8 GB):\n\n- ~/Library/Caches shrank from 1.8G to 19M (Homebrew, Playwright, pip, Python)\n- Workspace and user files untouched.", theme=app.active_theme))
        await pilot.pause(0.05)
    await capture_state("conversation_cleanup_flow", app_flow, setup_flow, width=120, height=28)

    # ── 2. Full-Bleed Verification Pilot Snapshots Across Widths ─────────────
    # Widths: 60, 80, 120, 160, 220
    widths = [60, 80, 120, 160, 220]

    for w in widths:
        # A. Welcome screen
        app_w_welcome = JuliusApp(workspace_dir=".", config=AgentConfig())
        await capture_state(f"pilot_welcome_w{w}", app_w_welcome, width=w, height=24)

        # B. Thinking state
        app_w_thinking = JuliusApp(workspace_dir=".", config=AgentConfig())
        async def setup_w_thinking(app, pilot):
            conv = app.query_one("#conversation-area", ScrollableContainer)
            await conv.mount(UserMessage("Refactor the layout to use full terminal bleed across all widths."))
            dot = ThinkingDot("Thinking")
            await conv.mount(dot)
            await pilot.pause(0.05)
        await capture_state(f"pilot_thinking_w{w}", app_w_thinking, setup_w_thinking, width=w, height=24)

        # C. Finished Answer
        app_w_answer = JuliusApp(workspace_dir=".", config=AgentConfig())
        async def setup_w_answer(app, pilot):
            conv = app.query_one("#conversation-area", ScrollableContainer)
            await conv.mount(UserMessage("Check test coverage for the full-bleed terminal redesign."))
            asst = AssistantMessage(
                "All 21 layout, theme, markdown, and resize tests have passed. Julius now occupies the full viewport width and height with calm edge padding.",
                theme=app.active_theme,
            )
            await conv.mount(asst)
            await pilot.pause(0.05)
        await capture_state(f"pilot_finished_answer_w{w}", app_w_answer, setup_w_answer, width=w, height=24)

        # D. Long Answer with Code Block & Table
        app_w_long = JuliusApp(workspace_dir=".", config=AgentConfig())
        async def setup_w_long(app, pilot):
            conv = app.query_one("#conversation-area", ScrollableContainer)
            await conv.mount(UserMessage("Explain the full-bleed layout specifications and show the responsive config."))
            long_content = (
                "# Full-Bleed Terminal Layout\n\n"
                "Julius spans 100% of the available terminal width and height without any narrow centered column.\n\n"
                "### Layout Regions\n"
                "* **Conversation Area**: Fills all remaining height (`1fr`), scrollable, full content width.\n"
                "* **Input Composer**: Rounded dock at the bottom edge with active focus border.\n"
                "* **Status Line**: Single dim line displaying active model and contextual shortcuts.\n\n"
                "### Responsive Breakpoints\n\n"
                "| Viewport Width | Edge Padding | Content Width | Resize Behavior |\n"
                "| :--- | :--- | :--- | :--- |\n"
                "| `< 60 cols` | N/A | N/A | Calm window enlargement notice |\n"
                "| `60 - 159 cols` | 2 cells | `width - 4` | Full bleed with 2-cell margin |\n"
                "| `160+ cols` | 4 cells | `width - 8` | Full bleed with 4-cell margin |\n\n"
                "```python\n"
                "@dataclass\n"
                "class JuliusConfig:\n"
                "    theme: str = 'auto'\n"
                "    max_content_width: int = 0  # 0 means unlimited full-width\n"
                "    show_diff_preview: bool = True\n"
                "```"
            )
            asst = AssistantMessage(long_content, theme=app.active_theme)
            await conv.mount(asst)
            await pilot.pause(0.05)
        await capture_state(f"pilot_long_answer_code_w{w}", app_w_long, setup_w_long, width=w, height=28)


if __name__ == "__main__":
    asyncio.run(main())
