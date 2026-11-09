# Module docstring describing this file as the configuration and safety parameters for Julius
"""Agent configuration, safety settings, and runtime constants."""

# Enable modern type hint annotations support across all Python 3.10+ runtimes
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


ProviderName = Literal['nvidia', 'chatgpt', 'grok', 'deepseek', 'perplexity', 'gemini', 'kimi', 'ollama', 'llama', 'aifreeforever', 'aifree', 'deepseek-v4-flash', 'nvidia-nim', 'nemotron', 'nemotron-550b', 'nvidia-550b', '550b']

SUPPORTED_PROVIDERS: tuple[ProviderName, ...] = (
    'nvidia', 'nvidia-nim', 'nemotron', 'nemotron-550b', 'nvidia-550b', '550b',
    'aifreeforever', 'aifree', 'deepseek-v4-flash',
    'chatgpt', 'grok', 'deepseek', 'perplexity', 'gemini', 'kimi', 'ollama', 'llama'
)

# Immutable set of action names that modify files or execute shell code and may require confirmation
DESTRUCTIVE_ACTIONS: frozenset[str] = frozenset({
    # Action executing arbitrary shell commands in the terminal
    'run_bash',
    # Action creating or completely overwriting a file
    'write_file',
    # Action modifying an existing file with targeted search-and-replace
    'edit_file',
    # Action executing git repository operations
    'git',
})

# Immutable set of action names that only read data and are always safe to execute
SAFE_ACTIONS: frozenset[str] = frozenset({
    # Safe action reading contents of a file
    'read_file',
    # Safe action listing directory contents
    'list_dir',
    # Safe action searching files matching patterns or keywords
    'search_files',
    # Safe action prompting human user with a question
    'ask_human',
    # Safe action speaking to the user directly
    'converse',
    # Safe action declaring the task is completed
    'done',
    # Safe action translating text using Sarvam AI
    'sarvam_translate',
    # Safe action generating text-to-speech using Sarvam AI
    'sarvam_tts',
    # Safe action transcribing speech-to-text using Sarvam AI
    'sarvam_stt',
    # Safe action performing OCR using Sarvam AI
    'sarvam_ocr',
})


# Safely attempt to load environment variables from .env files
try:
    from dotenv import load_dotenv
    # Loop over candidate .env file locations
    for _env_cand in [
        # Check project root .env file
        Path(__file__).resolve().parent.parent / ".env",
        # Check ~/.Julius/.env user configuration file
        Path.home() / ".Julius" / ".env",
        # Check current working directory .env file
        Path.cwd() / ".env"
    ]:
        # If candidate file exists
        if _env_cand.exists():
            # Load environment variables without overriding existing environment values
            load_dotenv(dotenv_path=_env_cand, override=False)
# Ignore ImportError if python-dotenv is not installed
except ImportError:
    # Pass silently
    pass


# Helper function to resolve default directories in user home folder respecting lowercase or uppercase .julius
def _resolve_default_dir(sub: str) -> str:
    # Expand path to lowercase ~/.julius/<subfolder>
    julius_lower = os.path.expanduser(f'~/.julius/{sub}')
    # Expand path to uppercase ~/.Julius/<subfolder>
    julius_upper = os.path.expanduser(f'~/.Julius/{sub}')
    # If lowercase directory already exists
    if os.path.exists(julius_lower):
        # Return lowercase path
        return julius_lower
    # If uppercase directory already exists
    if os.path.exists(julius_upper):
        # Return uppercase path
        return julius_upper
    # Otherwise default to lowercase path
    return julius_lower


# Function to check whether Ollama API is reachable on local network or localhost
def check_ollama_online_sync(timeout: float = 0.5) -> bool:
    """Pre-flight check whether Ollama is reachable on LAN or localhost."""
    import socket
    import urllib.parse
    # Retrieve configured Ollama host URL from environment or default to localhost
    host_str = os.getenv("OLLAMA_HOST", os.getenv("OLLAMA_API_URL", "http://127.0.0.1:11434")).strip()
    # Fallback to default localhost if string is empty
    if not host_str:
        host_str = "http://127.0.0.1:11434"
    # Ensure URL protocol prefix is present
    if not host_str.startswith("http://") and not host_str.startswith("https://"):
        host_str = f"http://{host_str}"
    # Protect socket connection attempt in try block
    try:
        # Parse URL string
        parsed = urllib.parse.urlparse(host_str)
        # Extract hostname or default to 127.0.0.1
        host = parsed.hostname or "127.0.0.1"
        # Extract port or default to Ollama standard port 11434
        port = parsed.port or 11434
        # Test TCP connection to host and port with specified timeout
        with socket.create_connection((host, port), timeout=timeout):
            # If socket connected successfully, return True
            return True
    # If connection fails or times out
    except Exception:
        # Pass silently to candidate scan
        pass

    # Scan localhost or configured host where Ollama server commonly runs
    for candidate in ("127.0.0.1", "localhost"):
        # Protect connection attempt
        try:
            # Attempt rapid 150ms connection test
            with socket.create_connection((candidate, 11434), timeout=0.15):
                # Return True if responsive
                return True
        # Ignore failed connections
        except Exception:
            # Pass silently
            pass
    # Return False if no Ollama instance was reachable
    return False


# Function to dynamically determine the default model provider
def get_default_provider() -> ProviderName:
    """Dynamically determine default provider: NVIDIA Nemotron 550B Build Free API is the primary default."""
    env_default = os.getenv("JULIUS_DEFAULT_MODEL", "").strip().lower()
    if env_default in ("nvidia", "nemotron", "nvidia-nim", "nim"):
        return "nvidia"
    if env_default in SUPPORTED_PROVIDERS and env_default not in ("ollama", "llama", "local"):
        return env_default  # type: ignore

    # NVIDIA Nemotron 550B (Build Free API) is the primary default provider.
    return "nvidia"


# Dataclass holding all configuration settings for the autonomous WebAgent
@dataclass
class AgentConfig:
    """Full configuration for the autonomous AI copilot."""

    # ── LLM Provider ──────────────────────────────────────────────
    # Active neural reasoning model provider
    provider: ProviderName = field(default_factory=get_default_provider)
    # Legacy browser options (Model generation uses Direct API; retained for non-model tool compatibility)
    profile_dir: str = field(default_factory=lambda: _resolve_default_dir('browser_profile'))
    headless: bool = False

    # ── Agent Loop ────────────────────────────────────────────────
    # Maximum steps per task (0 denotes unlimited until completed)
    max_steps: int = 0  # 0 denotes unlimited iterations until the job completes
    # Maximum seconds to wait for LLM response
    response_timeout: int = int(os.getenv("LOCAL_LLM_TIMEOUT", "300"))  # generous timeout for local LAN 9B model
    # Number of times to retry failed LLM queries
    retry_limit: int = 2  # retries per LLM request on failure
    # Base multiplier for exponential retry backoff delays
    retry_backoff_base: float = 2.0  # exponential backoff multiplier

    # ── Safety ────────────────────────────────────────────────────
    # Require human confirmation before executing any tool actions
    confirm_actions: bool = False  # Fully Autonomous mode — no human confirmation gates
    # Only require human confirmation for destructive actions like file edits and bash
    confirm_destructive_only: bool = False  # No destructive-only gating either
    # Prompt user before writing or modifying files
    confirm_writes: bool = False  # Prompt user before writing or modifying files
    # Buffer file edits in memory until task completion
    deferred_writes: bool = False  # Buffer file writes until task completion
    # Emergency abort hotkey sequence (disabled by default to prevent OS accessibility traps)
    abort_hotkey: str = ''  # emergency stop keyboard shortcut (empty = disabled)
    # Allow moving mouse to screen corner to abort actions
    enable_pyautogui_failsafe: bool = False  # move mouse to top-left corner to abort

    # ── Workspace ─────────────────────────────────────────────────
    # Workspace root directory where actions are permitted
    allowed_directory: str = '.'  # workspace root; actions are sandboxed here
    # Maximum lines of a file to return in observation prompt
    max_file_read_lines: int = 500  # limit file reads to prevent huge context
    # Maximum characters of terminal output to return in observation prompt
    max_bash_output_chars: int = 8000  # truncate bash output
    # Maximum seconds before a bash command execution times out
    bash_timeout: int = 60  # seconds per bash command (prevents premature timeouts on builds/tests)

    # ── Sandbox (Phase 2) ─────────────────────────────────────────
    # Whether to isolate execution inside a Docker container
    use_docker_sandbox: bool = False       # Docker sandbox disabled — run commands directly
    # Memory cap for Docker container
    docker_memory_limit: str = '512m'      # container memory cap (e.g. '256m', '1g')
    # List of subdirectories allowed for strict write access
    strict_write_paths: list = field(default_factory=list)  # allowlisted write sub-dirs

    # ── Self-Healing (Phase 3) ─────────────────────────────────────
    # Whether agent automatically triggers self-healing subroutines on error
    enable_self_healing: bool = False      # self-healing DISABLED — no auto-fix loops
    # Maximum consecutive self-healing retry cycles
    self_heal_attempts: int = 0            # zero attempts — never enter heal cycle

    # ── Observation ───────────────────────────────────────────────
    # Capture desktop screenshots for vision reasoning
    screenshot_mode: bool = False  # capture desktop screenshots for vision
    # Enable visual perception and DOM tree analysis
    use_perception: bool = True   # Enable visual perception and DOM fusion
    # Directory where vision screenshots are stored
    screenshot_dir: str = field(default_factory=lambda: _resolve_default_dir('screenshots'))

    # ── Logging ───────────────────────────────────────────────────
    # Directory where execution logs are written
    log_dir: str = field(default_factory=lambda: _resolve_default_dir('logs'))
    # Enable verbose diagnostic logging
    verbose: bool = False

    # Lifecycle hook executed automatically after dataclass fields are initialized
    def __post_init__(self) -> None:
        # Resolve allowed directory to its canonical absolute filesystem path
        self.allowed_directory = str(Path(self.allowed_directory).resolve())
        # Ensure browser profile directory exists
        Path(self.profile_dir).mkdir(parents=True, exist_ok=True)
        # Ensure screenshot directory exists
        Path(self.screenshot_dir).mkdir(parents=True, exist_ok=True)
        # Ensure log directory exists
        Path(self.log_dir).mkdir(parents=True, exist_ok=True)

    # Property returning the human-readable name of the current execution mode
    @property
    def execution_mode(self) -> str:
        """Return human-readable execution mode name: Autonomous, Supervised, or Manual."""
        # If confirmations are completely disabled
        if not self.confirm_actions:
            # Return Autonomous mode label
            return "Autonomous"
        # If only destructive actions require confirmation
        elif self.confirm_destructive_only:
            # Return Supervised mode label
            return "Supervised"
        # Otherwise all actions require confirmation
        else:
            # Return Manual mode label
            return "Manual"

    # Method to set the operational safety mode
    def set_execution_mode(self, mode: str) -> None:
        """Set execution mode explicitly (Autonomous, Supervised, or Manual)."""
        # Convert mode string to lowercase and strip whitespace
        mode_clean = str(mode).strip().lower()
        # Handle Autonomous mode configuration
        if mode_clean in ("autonomous", "auto"):
            # Disable action confirmations
            self.confirm_actions = False
            # Disable destructive gating
            self.confirm_destructive_only = False
            # Disable write confirmations
            self.confirm_writes = False
        # Handle Supervised mode configuration
        elif mode_clean in ("supervised", "sup"):
            # Enable action confirmations
            self.confirm_actions = True
            # Enable destructive gating only
            self.confirm_destructive_only = True
        # Handle Manual mode configuration
        elif mode_clean in ("manual", "man"):
            # Enable action confirmations
            self.confirm_actions = True
            # Disable destructive gating to gate every action
            self.confirm_destructive_only = False
        # Handle unknown mode argument
        else:
            # Raise error for invalid mode string
            raise ValueError(f"Unknown execution mode '{mode}'. Supported modes: Autonomous, Supervised, Manual")

    # Method to check if an action requires user confirmation under current settings
    def needs_confirmation(self, action_name: str) -> bool:
        """Check whether a given action needs human confirmation."""
        # Check if write confirmations are explicitly enforced for file modifications
        if self.confirm_writes and action_name in ('write_file', 'edit_file'):
            # Return True
            return True
        # If confirmations are turned off globally, return False
        if not self.confirm_actions:
            # Return False
            return False
        # If supervised mode is active, check against DESTRUCTIVE_ACTIONS set
        if self.confirm_destructive_only:
            # Return True if action is destructive
            return action_name in DESTRUCTIVE_ACTIONS
        # In manual mode, check if action is not in SAFE_ACTIONS
        return action_name not in SAFE_ACTIONS

    # Method to verify if a filesystem path is permitted for agent operations
    def is_path_allowed(self, path: str) -> bool:
        """All paths allowed — no workspace sandboxing."""
        # Return True allowing access across local workspace
        return True
