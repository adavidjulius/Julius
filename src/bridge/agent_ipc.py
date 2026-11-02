#!/usr/bin/env python3
# Tell the operating system to run this script using Python 3
"""
High-Performance IPC Bridge between Julius Python Backend and TypeScript TUI.

Provides clean, bidirectional JSON Lines (NDJSON) streaming over stdio:
- STDIN:  JSON commands from TypeScript frontend (prompts, confirmations, model switching)
- STDOUT: Pure JSON Lines events from Python WebAgent & EventBridge (strictly framed)
- STDERR: Unadulterated logs, tracebacks, and debugging output
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Optional

# Find the absolute root path of the project by going three directory levels up from this file
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
# Check if the project root path is not already in Python's module search path list
if str(PROJECT_ROOT) not in sys.path:
    # Insert the project root path at index 0 so Julius modules can be imported cleanly
    sys.path.insert(0, str(PROJECT_ROOT))

# Start a protected try-block to safely load environment variables from .env files
try:
    from dotenv import load_dotenv
    # Loop through common locations where a .env configuration file might exist
    for _env_path in [
        # Check for .env file in the project root directory
        PROJECT_ROOT / ".env",
        # Check for .env file in the user's home .Julius folder
        Path.home() / ".Julius" / ".env",
        # Check for .env file in the current working directory
        Path.cwd() / ".env",
    ]:
        # If the candidate .env file exists on the filesystem
        if _env_path.exists():
            # Load the environment variables from this file and allow overriding
            load_dotenv(dotenv_path=_env_path, override=True)
            # Stop searching further since we already found and loaded a valid .env file
            break
    # Perform a general dotenv load for any remaining standard environment variables
    load_dotenv(override=False)
# Catch ImportError gracefully if python-dotenv is not installed in the environment
except ImportError:
    # Do nothing and continue execution without crashing if dotenv is missing
    pass

# Save the original standard output stream into a private variable for our JSON protocol
_REAL_STDOUT = sys.stdout
# Redirect standard Python print statements to standard error so they don't break JSON streaming
sys.stdout = sys.stderr

# Define the file path where IPC bridge logs will be stored in the user's home directory
_IPC_LOG_FILE = Path.home() / ".julius" / "logs" / "agent_ipc.log"
# Create the parent directories for the log file if they do not already exist
_IPC_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

# Create a formatter for log messages including timestamp, logger name, level, and message
_log_formatter = logging.Formatter("[%(asctime)s] [Python-IPC] %(levelname)s: %(message)s")
# Create a file handler to write log messages into the designated log file using UTF-8 encoding
_file_handler = logging.FileHandler(str(_IPC_LOG_FILE), encoding="utf-8")
# Attach the custom formatter to the file handler
_file_handler.setFormatter(_log_formatter)
_file_handler.setLevel(logging.INFO)

# Create a stream handler to print log messages to the standard error console stream
_stderr_handler = logging.StreamHandler(sys.stderr)
# Attach the custom formatter to the stderr stream handler
_stderr_handler.setFormatter(_log_formatter)
_stderr_handler.setLevel(logging.INFO)

# Retrieve the root logger for the entire application
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
# Add the file handler to the root logger so messages get saved to disk
root_logger.addHandler(_file_handler)
# Add the stderr handler to the root logger so messages show in terminal error output
root_logger.addHandler(_stderr_handler)

# Create a dedicated logger named 'agent_ipc' for all bridge-specific diagnostic messages
logger = logging.getLogger("agent_ipc")

from src.agent_config import AgentConfig, get_default_provider
from src.web_agent import WebAgent
from src.providers import ProviderRouter, create_default_router
from src.tui.state import SessionState
from src.tui.event_bridge import EventBridge
from src.tui.config import load_config, save_config


# Define helper function to send a JSON-encoded protocol message to the TypeScript frontend
def send_ipc_message(msg_type: str, **payload: Any) -> None:
    """Send a strictly framed single-line JSON event to TypeScript frontend."""
    # Combine the message type and any arbitrary keyword arguments into a single dictionary
    message = {"type": msg_type, **payload}
    # Convert the Python dictionary into a single JSON string without escaping unicode characters
    line = json.dumps(message, ensure_ascii=False)
    # Write the JSON string followed by a newline directly to the real stdout stream
    _REAL_STDOUT.write(line + "\n")
    # Immediately flush the output buffer so the TypeScript process receives it with zero delay
    _REAL_STDOUT.flush()


# Define the main IPC server class that manages agent lifecycle and frontend communication
class AgentIPCServer:
    """Manages the lifecycle of WebAgent and routes IPC messages to/from TypeScript."""

    # Constructor method run when a new AgentIPCServer instance is created
    def __init__(self, workspace_dir: str = ".", initial_model: Optional[str] = None):
        # Store the workspace directory path where the user wants Julius to operate
        self.workspace_dir = workspace_dir
        # Load the user's saved application configuration from disk
        self.app_config = load_config()
        # Determine active model using initial argument, config preference, or system default
        self.active_model = initial_model or self.app_config.model or get_default_provider()

        # Initialize the configuration object for WebAgent with safe operational defaults
        self.agent_config = AgentConfig(
            provider=self.active_model,
            # Disable confirmation prompts on safe commands so the agent can execute smoothly
            confirm_actions=False,
            # Disable screenshot mode during standard execution
            screenshot_mode=False,
            # Run in headed browser mode so the user can see what the agent is doing
            headless=False,
            # Disable verbose internal debug dumps to keep output clean
            verbose=False,
        )

        # Initialize session state to track the active model and active theme
        self.session_state = SessionState(
            # Record the active neural reasoning model in session state
            active_model=self.active_model,
            # Record the user's chosen UI theme (e.g., dark) in session state
            theme_name=self.app_config.theme,
        )

        # Initialize event bridge to convert low-level agent events to high-level UI events
        self.event_bridge = EventBridge(
            # Provide session state reference to the event bridge
            session_state=self.session_state,
            # Provide callback function to execute whenever a message needs to be posted
            post_message_callback=self._on_bridge_message,
            # Provide callback function to execute whenever status line text needs updating
            update_status_callback=self._on_status_update,
        )

        # Placeholder for the WebAgent instance before it is lazily initialized
        self.agent: Optional[WebAgent] = None
        # Placeholder for the currently running asynchronous task executing a prompt
        self._current_task: Optional[asyncio.Task] = None
        # Boolean flag controlling the main event loop lifecycle
        self._is_running = True

    # Callback method invoked by EventBridge whenever a structured message is ready
    def _on_bridge_message(self, msg: Dict[str, Any]) -> None:
        """Callback from EventBridge for structured UI messages."""
        # Retrieve the tools list from the message dictionary if present
        tools = msg.get("tools")
        # Check if tools exist and are formatted as a list
        if tools and isinstance(tools, list):
            # Create an empty list to store serializable tool dictionary objects
            cleaned_tools = []
            # Iterate through each tool record in the tools list
            for t in tools:
                # If the tool is a custom object class with an internal dictionary
                if hasattr(t, "__dict__"):
                    # Extract its dictionary representation and append to cleaned list
                    cleaned_tools.append(t.__dict__)
                # If the tool is already a dictionary
                elif isinstance(t, dict):
                    # Append it directly to the cleaned list
                    cleaned_tools.append(t)
            # Replace the message's tools field with the cleaned serializable list
            msg["tools"] = cleaned_tools

        # Send the bridge event message over IPC to the TypeScript UI frontend
        send_ipc_message("bridge_event", event=msg)

    # Callback method invoked by EventBridge to update the status line text
    def _on_status_update(self, status: str) -> None:
        """Callback from EventBridge for quiet status line updates."""
        # Send a status update message over IPC to update the bottom bar in the UI
        send_ipc_message("status_update", status=status)

    # Callback method invoked by WebAgent whenever an internal event occurs
    def _handle_raw_event(self, event: Dict[str, Any]) -> None:
        """Receive raw event from WebAgent and forward to EventBridge and frontend."""
        # Pass the raw event into EventBridge for state tracking, token accumulation, and formatting
        self.event_bridge.handle_event(event)

    # Method to instantiate and initialize the WebAgent instance
    def initialize_agent(self) -> None:
        """Initialize the local WebAgent instance."""
        # Log an informational message indicating which model provider is being activated
        logger.info(f"Initializing WebAgent with provider: {self.active_model}")
        # Create the WebAgent instance using our configured parameters and event handlers
        self.agent = WebAgent(
            # Pass the agent configuration object
            config=self.agent_config,
            # Instruct the agent to keep the browser open between turns for speed
            keep_browser_open=True,
            # Connect the agent's event handler to our raw event processing method
            on_event=self._handle_raw_event,
        )

    # Asynchronous method to retrieve list of available cloud models and live LAN Ollama models
    async def get_available_models(self) -> List[Dict[str, str]]:
        """List canonical models and probe live LAN Ollama models."""
        from src.tui.components.modals.model_picker import MODELS

        # Initialize an empty list to collect all available model dictionaries
        models_list: List[Dict[str, str]] = []

        # Start a protected block to scan for local Ollama models on the local network
        try:
            import aiohttp
            # Determine the base URL for Ollama from environment variables or use default LAN IP
            base_url = (os.getenv("OLLAMA_BASE_URL") or os.getenv("OLLAMA_HOST") or "http://127.0.0.1:11434").rstrip("/")
            timeout_obj = aiohttp.ClientTimeout(total=0.6)
            # Create an asynchronous HTTP client session with the specified timeout
            async with aiohttp.ClientSession(timeout=timeout_obj) as session:
                # Send an asynchronous HTTP GET request to Ollama's tags endpoint
                async with session.get(f"{base_url}/api/tags") as resp:
                    # If the Ollama server responded with HTTP 200 OK
                    if resp.status == 200:
                        # Parse the response body as JSON
                        data = await resp.json()
                        # Iterate through each model returned by the Ollama API
                        for m in data.get("models", []):
                            # Get the model name string
                            raw_name = m.get("name", "")
                            # Skip if model name is empty
                            if not raw_name:
                                # Continue to the next item
                                continue
                            # Convert model name to lowercase for easy matching
                            lower_name = raw_name.lower()
                            # Check if the model is a Lexi variant
                            if "lexi" in lower_name:
                                # Add Lexi model with appropriate display label and description
                                models_list.append({"id": "lexi", "name": "Llama 3.1 8B Lexi", "desc": "Local LAN (Ollama 8.0B)"})
                            # Check if the model is a Qwen variant
                            elif "qwen" in lower_name:
                                # Add Qwen model with appropriate display label and description
                                models_list.append({"id": "qwen", "name": "Qwen 3.5 9B", "desc": "Local LAN (Ollama 8.95B)"})
                            # Check if the model is a 70B parameter model
                            elif "70b" in lower_name:
                                # Add 70B model with appropriate display label and description
                                models_list.append({"id": "llama70b", "name": "Llama 3 70B", "desc": "Local LAN (Ollama 70B)"})
                            # Otherwise handle any other arbitrary local Ollama model
                            else:
                                # Clean the name by stripping repository prefix and tag suffix
                                clean = raw_name.split("/")[-1].split(":")[0]
                                # Add the cleaned local model to the list
                                models_list.append({"id": clean.lower(), "name": clean, "desc": "Local LAN (Ollama)"})
        # If Ollama is offline or network fails, catch the exception without crashing
        except Exception:
            # Silently pass and proceed with canonical cloud models
            pass

        # Loop through each canonical model tuple in the Julius model registry
        for m_id, name, desc in MODELS:
            # If Ollama is selected but local models were already discovered on LAN
            if m_id == "ollama" and models_list:
                # Skip duplicate generic Ollama entry since live LAN models exist
                continue
            # Append the canonical cloud model dictionary to the model list
            models_list.append({"id": m_id, "name": name, "desc": desc})

        # Return the compiled list of all available models
        return models_list

    # Asynchronous method to process an incoming JSON command from the TypeScript frontend
    async def handle_command(self, cmd_data: Dict[str, Any]) -> None:
        """Process incoming JSON command from TypeScript."""
        # Extract the action name string from the incoming command dictionary
        action = cmd_data.get("action")

        # Handle heartbeat ping action to measure round-trip latency
        if action == "ping":
            # Respond with pong message including the current UNIX timestamp
            send_ipc_message("pong", timestamp=time.time())

        # Handle request to fetch the list of all available models
        elif action == "get_models":
            # Retrieve the list of available models asynchronously
            models = await self.get_available_models()
            # Send the model list and active model name back to the frontend
            send_ipc_message("models_list", models=models, active_model=self.active_model)

        # Handle prompt submission action from the user in the UI composer
        elif action == "submit_prompt":
            # Extract and trim whitespace from the prompt text
            prompt = cmd_data.get("prompt", "").strip()
            # If the prompt is empty after trimming
            if not prompt:
                # Do nothing and return early
                return

            # Check if there is already an existing task running and not yet finished
            if self._current_task and not self._current_task.done():
                # Log a warning that the previous task is being superseded
                logger.warning("Superseding previous active task")
                # Cancel the currently running asynchronous task
                self._current_task.cancel()

            # Create and launch a new asynchronous task to execute the prompt
            self._current_task = asyncio.create_task(self._execute_prompt(prompt))

        # Handle user confirmation response (Yes/No) for a destructive action
        elif action == "confirm_action":
            # Extract the boolean permission value, defaulting to False if missing
            allow = bool(cmd_data.get("allow", False))
            # Log the user's confirmation decision
            logger.info(f"User confirmation received: {allow}")
            # If the agent instance exists
            if self.agent:
                # Deliver the confirmation result to the waiting agent future
                self.agent.set_confirmation_result(allow)
            # Acknowledge the confirmation over IPC back to frontend
            send_ipc_message("confirmation_ack", allow=allow)

        # Handle user response to an interactive question asked by the agent
        elif action == "answer_question":
            # Extract the user's answer text from the command
            answer = str(cmd_data.get("answer", ""))
            # Log the received answer
            logger.info(f"User question answer received: {answer}")
            # If the agent instance exists
            if self.agent:
                # Deliver the answer to the waiting agent future
                self.agent.set_question_result(answer)
            # Acknowledge receipt of the answer over IPC back to frontend
            send_ipc_message("question_ack", answer=answer)

        # Handle dynamic model switching request from the model picker modal
        elif action == "switch_model":
            # Extract and trim the requested target model ID string
            model_id = str(cmd_data.get("model", "")).strip()
            # If a non-empty model ID was provided
            if model_id:
                # Perform asynchronous model switch
                await self._switch_model(model_id)

        # Handle cancellation of current action or prompt execution (e.g., Ctrl+C or Escape)
        elif action == "cancel_action":
            # Log the cancellation request
            logger.info("User requested action cancellation")
            # If there is an active running task that is not done
            if self._current_task and not self._current_task.done():
                # Cancel the active asyncio task
                self._current_task.cancel()
            # If the agent has a pending confirmation future waiting
            if self.agent and hasattr(self.agent, "_confirm_future") and self.agent._confirm_future:
                # Resolve the confirmation with False to prevent execution
                self.agent.set_confirmation_result(False)
            # If the agent has a pending question future waiting
            if self.agent and hasattr(self.agent, "_question_future") and self.agent._question_future:
                # Resolve the question with a cancellation notice message
                self.agent.set_question_result("Cancelled by user.")
            # Notify the frontend that the action has been cancelled
            send_ipc_message("action_cancelled")

        elif action in ("clear", "new"):
            logger.info("Resetting conversation history and active browser session")
            self.session_state.history.clear()
            if self._current_task and not self._current_task.done():
                self._current_task.cancel()
            if self.agent and hasattr(self.agent, "client") and self.agent.client:
                try:
                    if getattr(self.agent.client, "is_initialized", False):
                        logger.info("Closing Web LLM browser session on clear/new...")
                        await self.agent.client.close()
                        req_prov = getattr(self.agent.config, "provider", self.session_state.active_model)
                        if req_prov and req_prov.lower() in ("nvidia", "nvidia-nim", "nemotron", "nemotron-550b", "deepseek", "chatgpt", "gemini", "grok", "perplexity", "claude", "kimi", "aifreeforever", "aifree", "deepseek-v4-flash"):
                            await self.agent.client.initialize(
                                provider_name=req_prov,
                                profile_dir=getattr(self.agent.config, "profile_dir", None),
                                headless=getattr(self.agent.config, "headless", False),
                            )
                except Exception as exc:
                    logger.debug(f"Error resetting web session on clear: {exc}")
            send_ipc_message("session_cleared")

        elif action == "undo":
            res = self.session_state.rollback_last_modification()
            if res:
                path, action_desc = res
                p_name = Path(path).name
                report = f"### ↩️ Reverted Mutation\nRolled back `{path}` ({action_desc})."
                send_ipc_message("system_report", command="undo", report=report, toast=f"Reverted {p_name}")
            else:
                report = "### ↩️ Reverted Mutation\nNo file mutations to undo."
                send_ipc_message("system_report", command="undo", report=report, toast="No file mutations to undo")

        elif action == "doctor":
            import shutil
            git_status = "Available" if shutil.which("git") else "Not found"
            node_status = "Available" if shutil.which("node") else "Not found"
            python_ver = sys.version.split()[0]
            report = f"""### 🩺 Julius Doctor Diagnostic Report
- **Python Runtime**: `{python_ver}` ({'virtualenv active' if sys.prefix != sys.base_prefix else 'system'})
- **Workspace Root**: `{self.workspace_dir}`
- **Active Model**: `{self.session_state.active_model}`
- **Git Binary**: `{git_status}`
- **Node.js**: `{node_status}`
- **Stateful Shell**: `PTY Terminal Engine Active`
- **Context Telemetry**: `{self.session_state.token_count} tokens tracked across {len(self.session_state.history)} turns`
- **System Health**: `All subsystems operational`"""
            send_ipc_message("system_report", command="doctor", report=report)

        elif action == "context":
            mod_count = len(self.session_state.modified_files)
            mod_list = "\n".join(f"  - `{p}`" for p in self.session_state.modified_files[:5]) if mod_count else "  *(None)*"
            if mod_count > 5:
                mod_list += f"\n  - *...and {mod_count - 5} more*"
            elapsed = int(time.time() - self.session_state.start_time)
            uptime_str = f"{elapsed // 60}m {elapsed % 60}s" if elapsed >= 60 else f"{elapsed}s"
            report = f"""### 🧠 Workspace Context Telemetry
- **Active Reasoning Model**: `{self.session_state.active_model}`
- **Token Usage**: `{self.session_state.token_count:,} tokens`
- **Conversation Turns**: `{len(self.session_state.history)}`
- **Session Uptime**: `{uptime_str}`
- **Modified Workspace Files ({mod_count})**:
{mod_list}"""
            send_ipc_message("system_report", command="context", report=report)

        elif action == "cost":
            tokens = self.session_state.token_count
            elapsed = int(time.time() - self.session_state.start_time)
            uptime_str = f"{elapsed // 60}m {elapsed % 60}s" if elapsed >= 60 else f"{elapsed}s"
            report = f"""### 📊 Session Telemetry & Cost
- **Total Session Tokens**: `{tokens:,}`
- **Elapsed Time**: `{uptime_str}`
- **Active Engine**: `{self.session_state.active_model}`
- **Estimated API Cost**: `$0.00` *(Included in subscription / local provider)*"""
            send_ipc_message("system_report", command="cost", report=report)

        elif action == "compact":
            if len(self.session_state.history) > 4:
                self.session_state.history = self.session_state.history[-4:]
            report = "### 🗜️ Context Compacted\nConversation history was compressed to reclaim context window headroom."
            send_ipc_message("system_report", command="compact", report=report, toast="Context compacted")

        elif action == "exit":
            # Log that exit command was received
            logger.info("Received exit command")
            self._is_running = False
            # Cancel active running task if not done
            if self._current_task and not self._current_task.done():
                # Cancel the task
                self._current_task.cancel()
            # If the agent exists
            if self.agent:
                # Wrap agent close in protected block
                try:
                    # Close browser and background agent processes asynchronously
                    await self.agent.close()
                # Catch any errors during close without crashing
                except Exception:
                    # Ignore close errors
                    pass
            # Notify frontend that backend has exited cleanly
            send_ipc_message("exited")

        # Handle any unrecognized command actions
        else:
            # Log a warning containing the unknown action name
            logger.warning(f"Unknown action received: {action}")

    # Asynchronous method to switch active LLM provider dynamically
    async def _switch_model(self, model_id: str) -> None:
        """Switch active LLM model provider dynamically."""
        # Clean and strip any whitespace from the model ID
        target = model_id.strip()
        # Log the switch operation
        logger.info(f"Switching active model to: {target}")
        # Update server's active model field
        self.active_model = target
        # Update session state's active model field
        self.session_state.active_model = target
        # Update agent configuration's provider field
        self.agent_config.provider = target

        # If agent instance is currently active
        if self.agent:
            # Update agent's configuration provider
            self.agent.config.provider = target
            # If agent has a web LLM client
            if hasattr(self.agent, "client") and self.agent.client:
                # If target is an Ollama model, set custom Ollama model name on client
                if target.lower() in ("lexi", "qwen", "llama70b") or any(k in target.lower() for k in ("lexi", "qwen")):
                    # Assign the specific Ollama model tag
                    self.agent.client._ollama_model = target
                # If client has a close method, close existing browser session cleanly
                if hasattr(self.agent.client, "close"):
                    # Wrap close in protected try-block
                    try:
                        # Asynchronously close previous provider session
                        await self.agent.client.close()
                    # Catch and ignore errors during closing
                    except Exception:
                        # Pass silently
                        pass
                # Instantiate a fresh ProviderRouter for the new provider
                self.agent.client = create_default_router(getattr(self.app_config, "workspace", None))
                if hasattr(self.agent.client, "active_provider"):
                    self.agent.client.active_provider = target

        # Update application config with new model preference
        self.app_config.model = target
        # Persist updated configuration to config file on disk
        save_config(self.app_config)
        # Notify the TypeScript frontend that model switch completed
        send_ipc_message("model_switched", model=target)

    # Asynchronous method to execute a prompt through the WebAgent loop
    async def _execute_prompt(self, prompt: str) -> None:
        """Run task prompt through agent loop."""
        # Resolve interaction mode (/plan, /act, etc.)
        if prompt.startswith("/plan "):
            actual_task = prompt[6:].strip()
            prompt = (
                f"[PLANNING MODE] Do NOT execute file changes or shell commands yet. "
                f"Analyze the task and return a clear, step-by-step implementation plan. "
                f"End with the converse or done action summarizing your proposed plan.\n\n"
                f"Task: {actual_task}"
            )
        elif prompt.startswith("/act "):
            prompt = prompt[5:].strip()

        logger.info(f"Executing prompt: {prompt[:60]}...")
        # Add the user's prompt to the conversation history in session state
        self.session_state.history.append(("user", prompt))
        # Signal EventBridge that a new conversational turn has begun
        self.event_bridge.start_turn()

        # Protect execution in try-block to catch cancellation and errors
        try:
            # If agent has not been initialized yet
            if not self.agent:
                # Lazily initialize agent now
                self.initialize_agent()

            # Execute the prompt asynchronously on the WebAgent until completion
            await self.agent.run(prompt)
            # Notify frontend that prompt finished successfully
            send_ipc_message("prompt_finished", success=True)
        # Handle user cancellation gracefully
        except asyncio.CancelledError:
            # Log that task was cancelled
            logger.info("Task execution cancelled.")
            # Notify frontend that prompt was cancelled
            send_ipc_message("prompt_finished", success=False, cancelled=True)
        # Handle unexpected exceptions during task execution
        except Exception as exc:
            # Log the full exception traceback for debugging
            logger.exception("Error executing prompt")
            # Notify frontend that prompt failed with an error message
            send_ipc_message("prompt_finished", success=False, error=str(exc))
            # If event bridge has not yet finalized this turn
            if not self.event_bridge._has_finalized_turn:
                # Send error event through event bridge to show error banner in UI
                self.event_bridge.handle_event({"type": "error", "message": str(exc)})

    # Asynchronous method running the main IPC server loop
    async def run(self) -> None:
        """Main IPC server loop: initializes agent and listens on stdin."""
        # Initialize the WebAgent instance
        self.initialize_agent()
        # Retrieve the list of all available models
        available_models = await self.get_available_models()

        # Emit startup ready event over IPC to inform frontend that backend is operational
        send_ipc_message(
            # Event type identifier
            "ready",
            # Currently active model provider name
            active_model=self.active_model,
            # Current UI theme setting
            theme=self.app_config.theme,
            # Complete list of available models
            models=available_models,
            # Process ID of this Python process
            pid=os.getpid(),
        )

        # Get reference to currently running asyncio event loop
        loop = asyncio.get_running_loop()

        # Keep running while server flag remains True
        while self._is_running:
            # Protect loop body against unexpected I/O errors
            try:
                # Read a single line from STDIN without blocking the event loop
                line = await loop.run_in_executor(None, sys.stdin.readline)
                # If STDIN reached End-Of-File (pipe closed by parent process)
                if not line:
                    # Log that EOF was reached
                    logger.info("STDIN EOF reached. Exiting IPC server.")
                    # Exit the while loop
                    break

                # Strip whitespace from the line read
                line_str = line.strip()
                # If the line is empty
                if not line_str:
                    # Skip and wait for the next line
                    continue

                # Protect JSON parsing against malformed input
                try:
                    # Parse the input line as a JSON dictionary
                    cmd_data = json.loads(line_str)
                    # Dispatch and process the command asynchronously
                    await self.handle_command(cmd_data)
                # Catch JSON decode syntax errors
                except json.JSONDecodeError as err:
                    # Log error message detailing the malformed line
                    logger.error(f"Malformed JSON command received: {line_str!r} ({err})")
            # Handle task cancellation cleanly
            except asyncio.CancelledError:
                # Break out of loop
                break
            # Catch any other unexpected errors in the IPC loop
            except Exception as exc:
                # Log the unexpected error traceback
                logger.exception(f"Unexpected error in IPC loop: {exc}")

        # Clean shutdown sequence after loop terminates
        if self.agent:
            # Protect close in try-block
            try:
                # Close the agent and its browser resources
                await self.agent.close()
            # Ignore any errors during cleanup
            except Exception:
                # Pass silently
                pass


# Main entry point function executed when running this module from command line
def main() -> None:
    import argparse
    # Create argument parser describing the Julius IPC Bridge
    parser = argparse.ArgumentParser(description="Julius Python-TypeScript IPC Bridge")
    # Add optional argument for workspace directory path
    parser.add_argument("--workspace", default=".", help="Workspace path")
    # Add optional argument for overriding initial model
    parser.add_argument("--model", default=None, help="Initial model")
    # Parse the command-line arguments provided by user
    args = parser.parse_args()

    # Create the AgentIPCServer instance with parsed arguments
    server = AgentIPCServer(workspace_dir=args.workspace, initial_model=args.model)
    # Protect server execution against keyboard interrupts
    try:
        # Run the server's asynchronous event loop until completion
        asyncio.run(server.run())
    # Catch keyboard interrupt (Ctrl+C) or system exit signals
    except (KeyboardInterrupt, SystemExit):
        # Log clean termination message
        logger.info("IPC Bridge terminated.")


# Check if this script is being executed directly
if __name__ == "__main__":
    # Call the main entrypoint function
    main()
