"""
Canonical slash commands registry for Julius.

Single source of truth for all slash commands across:
- Composer autocomplete suggestions
- Application slash command router
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Optional


@dataclass(frozen=True)
class CommandDef:
    name: str
    description: str
    handler_id: str
    aliases: Tuple[str, ...] = field(default_factory=tuple)


# Canonical registry of all supported slash commands
CANONICAL_COMMANDS: List[CommandDef] = [
    CommandDef("/help", "Display keyboard shortcuts and command reference", "help", aliases=("/?",)),
    CommandDef("/plan", "Analyze task and outline a step-by-step roadmap", "plan"),
    CommandDef("/act", "Execute task directly in autonomous mode", "act"),
    CommandDef("/review", "Review code changes, diffs, and edge cases", "review"),
    CommandDef("/doctor", "Check environment, tools, and model connectivity", "doctor"),
    CommandDef("/context", "Display loaded workspace context and tokens", "context"),
    CommandDef("/compact", "Compress chat history to free context window", "compact"),
    CommandDef("/diff", "Review modified file deltas and hunks", "diff", aliases=("/changes",)),
    CommandDef("/action", "Inspect active command execution and live output", "action", aliases=("/inspect", "/ps")),
    CommandDef("/heal", "Diagnose and repair code errors or failing tests", "heal"),
    CommandDef("/undo", "Rollback last file mutation via workspace ledger", "undo"),
    CommandDef("/model", "Switch reasoning engine (DeepSeek, ChatGPT, Gemini, Grok)", "model"),
    CommandDef("/theme", "Toggle light, dark, or auto theme", "theme"),
    CommandDef("/copy", "Copy latest assistant response to clipboard", "copy"),
    CommandDef("/clear", "Reset conversation to a fresh session", "clear", aliases=("/new",)),
    CommandDef("/init", "Analyze codebase and initialize project guide", "init"),
    CommandDef("/cost", "Show token usage and session telemetry", "cost"),
    CommandDef("/quit", "Cleanly exit Julius CLI", "quit", aliases=("/exit",)),
]

# Derived: Composer autocomplete suggestions: (name, description)
COMMAND_SUGGESTIONS: List[Tuple[str, str]] = [
    (cmd.name, cmd.description) for cmd in CANONICAL_COMMANDS
]

# Derived: Fast trigger lookup (primary name + aliases) -> CommandDef
COMMAND_LOOKUP: Dict[str, CommandDef] = {}
for cmd in CANONICAL_COMMANDS:
    COMMAND_LOOKUP[cmd.name.lower()] = cmd
    for alias in cmd.aliases:
        COMMAND_LOOKUP[alias.lower()] = cmd


def get_command_def(cmd_text: str) -> Optional[CommandDef]:
    """Look up a command definition by name or alias (case-insensitive)."""
    return COMMAND_LOOKUP.get(cmd_text.strip().lower())
