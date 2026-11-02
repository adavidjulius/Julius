from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .models import PortingBacklog, PortingModule

SNAPSHOT_PATH = Path(__file__).resolve().parent / 'reference_data' / 'commands_snapshot.json'

JULIUS_SLASH_COMMANDS: dict[str, str] = {
    "context optimize": "Optimize and prune context window",
    "pkb rebuild": "Rebuild Project Knowledge Base graph index",
    "symbol graph": "Visualize symbol call graph",
    "arch discovery": "Run neural architecture search & discovery",
    "mem clear": "Clear working memory cache",
    "skill install": "Install an Agent Skill package",
    "skill list": "List all registered skills",
    "skill remove": "Uninstall an Agent Skill package",
    "sec scan": "Run security auditor & secret scanner",
    "lint run": "Run code linter and auto-formatter",
    "test run": "Run workspace test suite",
    "refactor plan": "Generate refactoring plan",
    "doc gen": "Generate inline & API documentation",
    "db optimize": "Analyze and optimize SQL queries",
    "devops check": "Validate Dockerfile and CI configuration",
    "api bench": "Benchmark API endpoints",
    "frontend audit": "Audit UI components and accessibility",
    "backend audit": "Audit backend endpoints and middleware",
    "git sync": "Synchronize repository git status",
    "task resume": "Resume active background tasks",
    "capcut list": "List all CapCut Desktop projects and drafts",
    "capcut open": "Open CapCut Desktop video editor",
    "capcut fix-network": "Fix CapCut network dropping & unlock all effects and materials",
    "capcut list-pro-effects": "List and search Pro video scene effects and filters",
    "capcut unlock-pro": "Unlock all VIP/Pro restriction tokens across projects",
}

# Backward compatibility alias
JULIUS_SLASH_COMMANDS = JULIUS_SLASH_COMMANDS


@dataclass(frozen=True)
class CommandExecution:
    name: str
    source_hint: str
    prompt: str
    handled: bool
    message: str


@lru_cache(maxsize=1)
def load_command_snapshot() -> tuple[PortingModule, ...]:
    if SNAPSHOT_PATH.exists():
        raw_entries = json.loads(SNAPSHOT_PATH.read_text())
        return tuple(
            PortingModule(
                name=entry['name'],
                responsibility=entry['responsibility'],
                source_hint=entry['source_hint'],
                status='mirrored',
            )
            for entry in raw_entries
        )
    return ()


PORTED_COMMANDS = load_command_snapshot()

COMMAND_ALIASES = {
    'plugins': 'plugin',
    'marketplace': 'plugin',
}


@lru_cache(maxsize=1)
def built_in_command_names() -> frozenset[str]:
    names = set(module.name for module in PORTED_COMMANDS)
    names.update(JULIUS_SLASH_COMMANDS.keys())
    return frozenset(names)


def build_command_backlog() -> PortingBacklog:
    return PortingBacklog(title='Command surface', modules=list(PORTED_COMMANDS))


def command_names() -> list[str]:
    return sorted(list(built_in_command_names()))


def get_command(name: str) -> PortingModule | None:
    needle = COMMAND_ALIASES.get(name.lower(), name.lower())
    if needle in JULIUS_SLASH_COMMANDS:
        return PortingModule(
            name=needle,
            responsibility=JULIUS_SLASH_COMMANDS[needle],
            source_hint="slash_command",
            status="active",
        )
    for module in PORTED_COMMANDS:
        if module.name.lower() == needle:
            return module
    return None


def get_commands(cwd: str | None = None, include_plugin_commands: bool = True, include_skill_commands: bool = True) -> tuple[PortingModule, ...]:
    commands = list(PORTED_COMMANDS)
    for k, v in JULIUS_SLASH_COMMANDS.items():
        commands.append(PortingModule(name=k, responsibility=v, source_hint="slash_command", status="active"))
    if not include_plugin_commands:
        commands = [module for module in commands if 'plugin' not in module.source_hint.lower()]
    if not include_skill_commands:
        commands = [module for module in commands if 'skills' not in module.source_hint.lower()]
    return tuple(commands)


def find_commands(query: str, limit: int = 20) -> list[PortingModule]:
    needle = query.lower()
    matches = []
    for k, v in JULIUS_SLASH_COMMANDS.items():
        if needle in k.lower() or needle in v.lower():
            matches.append(PortingModule(name=k, responsibility=v, source_hint="slash_command", status="active"))
    for module in PORTED_COMMANDS:
        if needle in module.name.lower() or needle in module.source_hint.lower():
            matches.append(module)
    return matches[:limit]


def execute_command(name: str, prompt: str = '') -> CommandExecution:
    needle = name.lower()
    if needle in JULIUS_SLASH_COMMANDS:
        parts = needle.split()
        category = parts[0].title()
        message = f"[Julius Slash Command] {category} processed for {name}: {prompt}"
        return CommandExecution(name=name, source_hint="slash_command", prompt=prompt, handled=True, message=message)

    module = get_command(name)
    if module is None:
        return CommandExecution(name=name, source_hint='', prompt=prompt, handled=False, message=f'Unknown command: {name}')
    action = f"Mirrored command '{module.name}' from {module.source_hint} would handle prompt {prompt!r}."
    return CommandExecution(name=module.name, source_hint=module.source_hint, prompt=prompt, handled=True, message=action)


def render_command_index(limit: int = 20, query: str | None = None) -> str:
    modules = find_commands(query, limit) if query else list(PORTED_COMMANDS[:limit])
    lines = [f'Command entries: {len(PORTED_COMMANDS) + len(JULIUS_SLASH_COMMANDS)}', '']
    if query:
        lines.append(f'Filtered by: {query}')
        lines.append('')
    lines.extend(f'- {module.name} — {module.source_hint}' for module in modules)
    return '\n'.join(lines)
