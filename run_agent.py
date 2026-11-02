#!/usr/bin/env python3
# Tell the operating system shell to execute this file using Python 3
"""
Julius CLI Main Runner (run_agent.py).
Provides a minimal, professional terminal interface.
Supports continuous REPL session, persistent browser context, and /new chat reset.
"""

import argparse
import asyncio
import os
from pathlib import Path
import sys
from typing import Optional, List, Dict, Any, Union

# Safely load configuration settings from .env file if available
try:
    from dotenv import load_dotenv
    # Loop over candidate .env configuration paths
    for _env_cand in [
        # Check for .env file in the current project root directory
        Path(__file__).resolve().parent / ".env",
        # Check for .env file in the user's home ~/.Julius folder
        Path.home() / ".Julius" / ".env",
        # Check for .env file in the current working directory
        Path.cwd() / ".env"
    ]:
        # If candidate .env file exists on disk
        if _env_cand.exists():
            # Load environment variables and allow overriding defaults
            load_dotenv(dotenv_path=_env_cand, override=True)
            # Break search loop
            break
    # Run generic dotenv load for any remaining environment variables
    load_dotenv(override=False)
# Catch ImportError if dotenv is not present
except ImportError:
    # Pass silently
    pass

from src.web_agent import WebAgent
from src.agent_config import AgentConfig, get_default_provider, SUPPORTED_PROVIDERS
from src.prompt_linter import lint_prompt
from src.cli.mode_registry import global_mode_registry
from src.cli.presenter import render_final_answer, render_error, HAS_RICH, console
from src.telemetry.logging import configure_logging
from src.telemetry.tracing import get_tracer

import shutil


def print_julius_banner():
    # Measure the current terminal width in columns, defaulting to 80 if undetermined
    width = shutil.get_terminal_size((80, 24)).columns
    # Define ASCII art lines for the JULIUS wordmark
    banner_lines = [
        # Banner row 1
        "╔═════╗ ╔╗   ╔╗ ╔╗      ╔═════╗ ╔╗   ╔╗ ╔═════╗",
        # Banner row 2
        "╚══╗  ║ ║║   ║║ ║║      ╚═╗ ╔═╝ ║║   ║║ ║ ╔═══╝",
        # Banner row 3
        "   ║  ║ ║║   ║║ ║║        ║ ║   ║║   ║║ ║ ╚═══╗",
        # Banner row 4
        "   ║  ║ ║║   ║║ ║║        ║ ║   ║║   ║║ ╚═══╗ ║",
        # Banner row 5
        "╔══╝  ║ ║╚═══╝║ ║╚════╗ ╔═╝ ╚═╗ ║╚═══╝║ ╔═══╝ ║",
        # Banner row 6
        "╚═════╝ ╚═════╝ ╚═════╝ ╚═════╝ ╚═════╝ ╚═════╝"
    ]
    # Center each banner line across the measured terminal column width
    centered_str = "\n".join(line.center(width) for line in banner_lines)
    # Check if Rich terminal output is available
    if HAS_RICH and console:
        # Print styled gold banner using Rich console
        console.print(f"\n[bold #c8b896]{centered_str}[/bold #c8b896]\n")
    # Otherwise use plain standard print
    else:
        # Print plain text banner
        print(f"\n{centered_str}\n")


def print_help():
    # Multi-line string detailing all available slash commands
    help_text = """
Available Commands:
  /plan <task>   Analyze task and propose step-by-step plan without executing changes
  /act <task>    Execute task directly
  /experiments   Query research experiment history & metrics
  /status        Show system health, Docker status, and environment metrics
  /resume        View and select from active/incomplete tasks for resumption
  /undo          Rollback last file mutations using workspace ledger
  /new           Reset to a fresh chat conversation on the active browser session
  /exit          Close browser and exit Julius CLI
  /help          Show this help message
"""
    # Check if Rich console is available
    if HAS_RICH and console:
        # Print color-formatted help box
        console.print(f"[bold #f59e0b]{help_text}[/bold #f59e0b]")
    # Otherwise print plain help text
    else:
        # Print plain help text
        print(help_text)


def parse_args():
    # Create argument parser describing Julius CLI
    parser = argparse.ArgumentParser(
        description="Julius - Autonomous web-chat coding and reasoning agent",
        # Use argument defaults formatter
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    # Add optional positional argument for initial task / command
    parser.add_argument(
        "task",
        nargs="*",
        default=[],
        help="Initial task, prompt, or command (e.g. 'doctor', 'config validate', 'audit verify')"
    )
    # Add verbose flag for step-by-step debugging traces
    parser.add_argument(
        # Short and long flag
        "-v", "--verbose",
        action="store_true",
        # Help text
        help="Enable verbose step-by-step trace mode for debugging"
    )
    # Add execution mode argument choice
    parser.add_argument(
        # Flag name
        "--mode",
        # Allowed mode choices
        choices=["Autonomous", "Supervised", "Manual"],
        # Default to Autonomous
        default="Autonomous",
        # Help text
        help="Agent execution mode: Autonomous (no prompts), Supervised (confirm destructive), Manual (step-by-step)"
    )
    # Add no-confirm flag to run completely autonomously
    parser.add_argument(
        # Short and long flag
        "-y", "--no-confirm",
        action="store_true",
        # Default value is True
        default=True,
        # Help text
        help="Run completely autonomously without asking confirmation for file edits/bash (default: True)"
    )
    # Query the default provider dynamically
    default_prov = get_default_provider()
    # Add provider argument allowing selection among canonical models
    parser.add_argument(
        # Short and long flag
        "-p", "--provider",
        # Default to dynamic default provider
        default=default_prov,
        # Restrict choices to supported Julius providers
        choices=list(SUPPORTED_PROVIDERS),
        # Help text showing current default
        help=f"LLM provider to use for reasoning (default: {default_prov})"
    )
    # Add max-steps argument to limit execution loop iterations
    parser.add_argument(
        # Short and long flag
        "-m", "--max-steps",
        # Cast value to integer
        type=int,
        # Default 0 means unlimited
        default=0,
        # Help text
        help="Maximum number of steps/loops per task (0 for unlimited until job completes)"
    )
    # Add headless flag to run browser invisibly
    parser.add_argument(
        # Flag name
        "--headless",
        action="store_true",
        # Help text
        help="Run browser in headless mode"
    )
    # Add screenshot flag to enable visual perception
    parser.add_argument(
        # Flag name
        "--screenshot",
        action="store_true",
        # Help text
        help="Enable screenshot observation mode"
    )
    # Add websocket URL argument for remote Julius server connection
    parser.add_argument(
        # Flag name
        "--ws",
        # Default to None
        default=None,
        # Help text
        help="Connect to remote Julius server WebSocket (e.g. ws://localhost:8080/ws)",
    )
    # Add profile directory argument for custom browser user data
    parser.add_argument(
        # Flag name
        "--profile-dir",
        # Default to None
        default=None,
        # Help text
        help="Custom browser profile directory (bypasses default profile rotation)",
    )
    # Add interactive TUI engine choice argument
    parser.add_argument(
        # Flag name
        "--tui-engine",
        # Supported TUI engines
        choices=["ts", "python", "auto"],
        # Default to auto detection
        default="auto",
        # Help text
        help="Interactive TUI engine: 'ts' (Fast React Ink), 'python' (Textual), or 'auto' (TS if node is present)",
    )
    # Add shortcut flag to force TypeScript React Ink TUI
    parser.add_argument(
        # Flag name
        "--ts",
        action="store_true",
        # Help text
        help="Shortcut to force high-speed TypeScript React Ink TUI",
    )
    # Add shortcut flag to force Python Textual TUI
    parser.add_argument(
        # Flag name
        "--python-tui",
        action="store_true",
        # Help text
        help="Shortcut to force legacy Python Textual TUI",
    )
    # Add first-run setup wizard flag
    parser.add_argument(
        "--setup",
        action="store_true",
        help="Run interactive first-run onboarding setup and health check",
    )
    # Parse and return the argument namespace
    return parser.parse_args()


# Helper function to discover the Node.js executable on the host system
def find_node_executable() -> Optional[str]:
    """Discover node binary in PATH or user cache/homebrew runtimes."""
    import shutil
    # Check if node is directly in system PATH
    cand = shutil.which("node")
    # If found in PATH
    if cand:
        # Return node binary path
        return cand
    # Search common runtime locations on macOS
    for p in [
        str(Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node"),
        "/opt/homebrew/bin/node",
        # Check Intel Homebrew / standard /usr/local path
        "/usr/local/bin/node",
    ]:
        # If file exists and has executable permissions
        if os.path.isfile(p) and os.access(p, os.X_OK):
            # Return discovered executable path
            return p
    # Return None if node was not found
    return None


# Function to spawn and run the compiled TypeScript React Ink TUI
def launch_ts_tui(node_bin: str, model: Optional[str] = None) -> int:
    """Launch the high-performance TypeScript React Ink TUI."""
    import subprocess
    import shutil

    tui_ts_dir = Path(__file__).resolve().parent / "src" / "tui_ts"
    dist_index = tui_ts_dir / "dist" / "index.js"
    src_index = tui_ts_dir / "src" / "index.tsx"

    # Auto-compile if dist/index.js is missing or older than any source file in src/tui_ts/src
    needs_build = not dist_index.exists()
    if not needs_build and tui_ts_dir.exists():
        try:
            src_files = list((tui_ts_dir / "src").rglob("*.ts*"))
            if src_files:
                latest_src_mtime = max(p.stat().st_mtime for p in src_files)
                needs_build = latest_src_mtime > dist_index.stat().st_mtime
        except Exception:
            pass

    if needs_build:
        npm_bin = shutil.which("npm") or str(Path(node_bin).parent / "npm") or shutil.which("pnpm") or shutil.which("yarn")
        built = False
        if npm_bin and (shutil.which(npm_bin) or os.path.exists(npm_bin)):
            try:
                res = subprocess.run(
                    [npm_bin, "run", "build"],
                    cwd=str(tui_ts_dir),
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                built = res.returncode == 0
            except Exception:
                pass
        if not built:
            tsc_bin = tui_ts_dir / "node_modules" / "typescript" / "bin" / "tsc"
            if tsc_bin.exists():
                try:
                    subprocess.run(
                        [node_bin, str(tsc_bin), "--project", "tsconfig.json"],
                        cwd=str(tui_ts_dir),
                        check=False,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                except Exception:
                    pass

    # Extract the directory containing the node binary
    node_dir = str(Path(node_bin).parent)
    # Copy current environment variables
    env = os.environ.copy()
    # Read current PATH string
    current_path = env.get("PATH", "")
    # If node directory is not in PATH
    if node_dir not in current_path:
        # Prepend node directory to PATH
        env["PATH"] = f"{node_dir}:{current_path}"
    # Force unbuffered Python stdout
    env["PYTHONUNBUFFERED"] = "1"
    # Enable 256-color support for Ink
    env["FORCE_COLOR"] = "2"
    # Remove COLORTERM to prevent terminal color misconfigurations
    env.pop("COLORTERM", None)

    if not dist_index.exists():
        # Fall back to tsx if available
        tsx_cand = shutil.which("tsx") or str(tui_ts_dir / "node_modules" / ".bin" / "tsx")
        if os.path.isfile(tsx_cand) and os.access(tsx_cand, os.X_OK):
            cmd = [tsx_cand, str(src_index)]
            if model:
                cmd.extend(["--model", model])
            res = subprocess.run(cmd, env=env)
            return res.returncode
        return 1

    cmd = [node_bin, str(dist_index)]
    # If a specific model was requested
    if model:
        # Append --model argument and model name
        cmd.extend(["--model", model])

    # Run the subprocess and wait for user session termination
    res = subprocess.run(cmd, env=env)
    # Return the process exit code
    return res.returncode


# Asynchronous function to execute a prompt on the agent instance and handle slash commands
async def execute_task_on_agent(agent: WebAgent, raw_prompt: str, verbose: bool = False):
    """Execute a task prompt on the shared agent instance."""
    # Resolve any slash command prefixes using the global mode registry
    mode_res = global_mode_registry.resolve(raw_prompt)
    # Extract the sanitized task prompt
    task_prompt = mode_res.task

    # Handle /exit slash command
    if mode_res.mode == 'exit':
        # Return EXIT signal
        return 'EXIT'

    # Handle /new slash command to start a fresh chat on the browser session
    if mode_res.mode == 'new':
        # Start new chat session on active browser tab
        await agent.start_new_chat()
        # Print confirmation message using Rich if available
        if HAS_RICH and console:
            # Print styled confirmation
            console.print("[bold green]✨ Started a new chat session.[/bold green]\n")
        # Otherwise print plain text confirmation
        else:
            # Print plain text confirmation
            print("✨ Started a new chat session.\n")
        # Return NEW signal
        return 'NEW'

    # Handle /help slash command
    if mode_res.mode == 'help':
        # Print the help message
        print_help()
        # Return HELP signal
        return 'HELP'

    # Handle /copy slash command to copy previous response to system clipboard
    if mode_res.mode == 'copy':
        from src.platform_compat import copy_to_clipboard
        # Retrieve previous assistant answer summary or fallback message
        msg = getattr(agent, 'last_summary', None) or "No output available to copy."
        # Attempt to copy string to OS clipboard
        if copy_to_clipboard(msg):
            # Print success message with character count using Rich if available
            if HAS_RICH and console:
                # Print styled success message
                console.print(f"[bold green]📋 Copied response ({len(msg)} chars) to system clipboard![/bold green]\n")
            # Otherwise print plain text success message
            else:
                # Print plain text success message
                print(f"📋 Copied response ({len(msg)} chars) to system clipboard!\n")
        # If clipboard copy failed
        else:
            # Print error message using Rich if available
            if HAS_RICH and console:
                # Print styled error message
                console.print("[bold red]❌ Failed to copy to clipboard.[/bold red]\n")
            # Otherwise print plain text error message
            else:
                # Print plain text error message
                print("❌ Failed to copy to clipboard.\n")
        # Return COPY signal
        return 'COPY'

    # Print debug information if verbose flag is set
    if verbose:
        # Print mode details
        print(f"Mode: {mode_res.mode} | Requires Plan: {mode_res.requires_plan} | High Risk: {mode_res.is_destructive}")

    # Handle /plan mode where user wants an implementation plan before execution
    if mode_res.requires_plan:
        # Compose planning prompt instruction
        plan_task = (
            # Planning mode header
            f"[PLANNING MODE] Do NOT execute file changes or shell commands yet. "
            # Instruction to analyze task
            f"Analyze the task and return a clear, step-by-step implementation plan. "
            # Instruction on closing action
            f"End with the converse or done action summarizing your proposed plan.\n\n"
            # Appended task prompt
            f"Task: {task_prompt}"
        )
        # Execute the planning prompt on the agent
        await agent.run(plan_task)

        # If running interactively, ask user for approval to execute the plan
        if sys.stdin.isatty():
            # Prompt user for input
            ans = input("\nProceed to execute this plan? [a]ccept (/act) / [d]ecline: ").strip().lower()
            # If user accepted the plan
            if ans in ('a', 'accept', 'y', 'yes', '/act'):
                # Print execution notification
                print("\n▶ Executing plan...")
                # Run the actual task prompt
                await agent.run(task_prompt)
            # If user declined the plan
            else:
                # Print cancellation notice
                print("Execution cancelled.")
    # Standard task execution mode without pre-planning
    else:
        # Run prompt directly on the agent
        await agent.run(task_prompt)

    # Return OK signal
    return 'OK'


# Main asynchronous application entry point
async def main():
    # Parse CLI flags and arguments
    args = parse_args()

    # Determine confirm_actions setting based on mode and flags
    confirm_actions = False if args.no_confirm or args.mode.lower() == "autonomous" else True

    # Build dictionary of configuration options
    config_args = {
        # Model provider name
        "provider": args.provider,
        # Maximum execution steps
        "max_steps": args.max_steps,
        # Confirmation flag
        "confirm_actions": confirm_actions,
        # Screenshot observation flag
        "screenshot_mode": args.screenshot,
        # Headless browser flag
        "headless": args.headless,
        # Verbose logging flag
        "verbose": args.verbose,
    }
    # If custom browser profile directory was supplied
    if args.profile_dir:
        # Add profile directory to configuration dictionary
        config_args["profile_dir"] = args.profile_dir

    # Instantiate AgentConfig object with configuration dictionary
    config = AgentConfig(**config_args)
    config.set_execution_mode(args.mode)

    # Normalize task string from arguments
    task_str = " ".join(args.task).strip() if isinstance(args.task, list) else (args.task or "").strip()

    # First-run setup check
    if getattr(args, "setup", False) or (task_str and task_str.lower() in ("setup", "--setup")):
        from src.cli.setup_wizard import run_first_run_setup
        run_first_run_setup()
        return

    # Check for dedicated CLI utility commands
    if task_str:
        task_tokens = task_str.split()
        cmd = task_tokens[0].lower()
        subcmd = task_tokens[1].lower() if len(task_tokens) > 1 else None

        if cmd == "doctor":
            from src.cli.doctor import run_doctor
            sys.exit(run_doctor())
        elif cmd == "config":
            from src.cli.config import validate_config, show_resolved_config
            if subcmd == "validate":
                ok = validate_config()
                sys.exit(0 if ok else 1)
            else:
                show_resolved_config()
                return
        elif cmd == "audit":
            from src.cli.audit import run_audit_verify
            sys.exit(run_audit_verify())
        elif cmd == "stats":
            from src.telemetry.local_stats import print_local_stats
            print_local_stats()
            return
        elif cmd == "jobs":
            from src.cli.jobs import (
                list_jobs_cli,
                cancel_job_cli,
                show_job_logs,
                submit_job_cli,
                resume_job_cli,
                run_worker_cli,
            )
            if subcmd == "submit" and len(task_tokens) > 2:
                submit_job_cli(" ".join(task_tokens[2:]))
            elif subcmd == "resume" and len(task_tokens) > 2:
                resume_job_cli(task_tokens[2])
            elif subcmd in ("worker", "start-worker"):
                run_worker_cli()
            elif subcmd == "cancel" and len(task_tokens) > 2:
                cancel_job_cli(task_tokens[2])
            elif subcmd == "logs" and len(task_tokens) > 2:
                show_job_logs(task_tokens[2])
            else:
                list_jobs_cli()
            return
        elif cmd == "update":
            from src.updater.manifest import fetch_latest_manifest
            from src.updater.verify import verify_update_signature
            from src.updater.swap import apply_atomic_update
            print("🔍 Checking for updates (WS7)...")
            try:
                manifest = fetch_latest_manifest()
                if manifest:
                    print(f"Latest release: v{manifest.version}")
                else:
                    print("Julius is up to date.")
            except Exception as e:
                print(f"Update check completed: {e}")
            return
        elif cmd == "license":
            from src.licensing.store import get_installed_license, install_license
            from src.licensing.verify import verify_license_offline
            if subcmd == "status" or not subcmd:
                lic = get_installed_license()
                if lic:
                    ok, res = verify_license_offline(lic)
                    tier_name = res.tier.value if (ok and res) else "Invalid"
                    print(f"📋 License Status: {tier_name.upper()} (Valid: {ok})")
                else:
                    print("📋 License Status: Community Edition (No license key installed)")
            elif subcmd == "activate" and len(task_tokens) > 2:
                install_license(task_tokens[2])
                print("✅ License key installed successfully.")
            return
        elif cmd == "auth":
            from src.auth.apikeys import ApiKeyStore
            store = ApiKeyStore()
            if subcmd == "create":
                name = task_tokens[2] if len(task_tokens) > 2 else "default"
                raw, rec = store.generate_key(name=name, user_id=1)
                print(f"✅ Created API Key: {raw}")
            elif subcmd == "list":
                keys = store.list_keys(user_id=1)
                for k in keys:
                    print(f"{k.prefix}... ({k.name}) - Active: {not k.revoked}")
            return
        elif cmd == "backup":
            import time
            from src.cli.backup import perform_online_backup
            src_db = Path.cwd() / ".julius" / "memory.db"
            dst_db = Path.cwd() / ".julius" / f"backup_memory_{int(time.time())}.db"
            perform_online_backup(src_db, dst_db)
            return
        elif cmd == "restore" and subcmd:
            from src.cli.backup import perform_online_restore
            target_db = Path.cwd() / ".julius" / "memory.db"
            perform_online_restore(task_tokens[1], target_db)
            return
        elif cmd == "diagnostics":
            from src.cli.diagnostics import generate_support_bundle
            generate_support_bundle()
            return

    # Check if a single task prompt was provided via command line
    if task_str:
        # Create WebAgent configured to close browser upon completion
        agent = WebAgent(config, keep_browser_open=False)
        # Protect task execution in try-finally block
        try:
            # Execute prompt on agent
            await execute_task_on_agent(agent, lint_prompt(task_str), verbose=args.verbose)
        # Ensure agent browser is closed cleanly
        finally:
            # Close agent and browser
            await agent.close()
        # Exit main function
        return

    # Check if interactive session can launch full TUI
    if sys.stdin.isatty() or args.ts:
        # Check if user forced Python Textual TUI
        force_python = args.python_tui or args.tui_engine == "python"
        # Check if user forced TypeScript TUI
        force_ts = args.ts or args.tui_engine == "ts"

        # If Python Textual TUI was not forced
        if not force_python:
            # Attempt to discover Node.js executable
            node_bin = find_node_executable()
            # If Node.js is installed
            if node_bin:
                # Launch the TypeScript React Ink TUI
                ret = launch_ts_tui(node_bin, model=args.provider)
                # If TUI exited cleanly or was explicitly forced
                if ret == 0 or force_ts:
                    # Return cleanly
                    return

        # Fallback to Python Textual TUI if Node is missing or failed
        try:
            from src.cli.v3_tui import launch_v3_tui_async
            # Launch Python Textual TUI asynchronously
            await launch_v3_tui_async(workspace_dir=".", config=config, initial_task=args.task, ws_url=args.ws)
            # Return after Textual exits
            return
        # If Textual is not installed
        except ImportError:
            # Fall through to standard terminal REPL
            pass

    # Fallback interactive terminal REPL mode
    print_julius_banner()

    # Create long-running WebAgent with browser kept open between turns
    agent = WebAgent(config, keep_browser_open=True)

    # Protect interactive REPL loop in try-finally block
    try:
        # Loop indefinitely accepting user prompts
        while True:
            # Protect individual turn in try-block
            try:
                # Prompt user for input with colorful prompt string using Rich if available
                if HAS_RICH and console:
                    # Read input using Rich console
                    prompt_input = console.input("[bold red]j[/][bold yellow]u[/][bold green]l[/][bold cyan]i[/][bold blue]u[/][bold magenta]s[/]>[/] ").strip()
                # Otherwise read input using standard input
                else:
                    # Read input using standard input
                    prompt_input = input("julius> ").strip()

                # If prompt is empty
                if not prompt_input:
                    # Skip to next iteration
                    continue

                # Execute prompt on agent
                res = await execute_task_on_agent(agent, lint_prompt(prompt_input), verbose=args.verbose)
                # If user entered /exit command
                if res == 'EXIT':
                    # Print farewell message
                    print("👋 Goodbye!")
                    # Break loop to exit
                    break

            # Handle Ctrl+C interrupt gracefully
            except KeyboardInterrupt:
                # Print hint on how to exit
                print("\n(Use /exit or Ctrl+D to exit Julius CLI)")
                # Continue loop
                continue
            # Handle Ctrl+D / EOF interrupt gracefully
            except EOFError:
                # Print farewell message
                print("\n👋 Goodbye!")
                # Break loop to exit
                break
            # Handle unexpected runtime exceptions
            except Exception as e:
                # If verbose mode is enabled, print full error
                if args.verbose:
                    # Print error details
                    print(f"\n❌ Task failed: {e}")
                # Otherwise render clean error notification
                else:
                    # Render error notification
                    render_error(str(e))

    # Ensure agent is closed when exiting REPL loop
    finally:
        # Close agent and browser resources cleanly
        await agent.close()


# Check if script is run as main module
if __name__ == "__main__":
    # Protect asyncio run in try-block
    try:
        # Run main async coroutine until completion
        asyncio.run(main())
    # Catch keyboard interrupt
    except KeyboardInterrupt:
        # Print exit notice
        print("\nCLI exited.")
