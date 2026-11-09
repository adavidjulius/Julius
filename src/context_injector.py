"""Dynamic workspace context injection for the Julius agent.

Scans the workspace directory and builds a contextual awareness block
that gets injected into the agent's observation prompts. This gives
the agent visibility into the project's ecosystem, structure, and
tracking metadata without the user having to explain it manually.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Ecosystem detection markers ───────────────────────────────────────────────

_ECOSYSTEM_MARKERS: list[tuple[str, str]] = [
    ('requirements.txt', 'Python (pip)'),
    ('pyproject.toml', 'Python (modern/PEP 621)'),
    ('setup.py', 'Python (setuptools)'),
    ('Pipfile', 'Python (Pipenv)'),
    ('package.json', 'Node.js (npm/yarn)'),
    ('pnpm-lock.yaml', 'Node.js (pnpm)'),
    ('Cargo.toml', 'Rust (cargo)'),
    ('go.mod', 'Go'),
    ('Gemfile', 'Ruby (Bundler)'),
    ('pom.xml', 'Java (Maven)'),
    ('build.gradle', 'Java/Kotlin (Gradle)'),
    ('CMakeLists.txt', 'C/C++ (CMake)'),
    ('Makefile', 'Make-based build'),
]

# ── Entry point detection ─────────────────────────────────────────────────────

_ENTRY_MARKERS: list[tuple[str, str]] = [
    ('main.py', 'Python entry: `main.py`'),
    ('app.py', 'Python entry: `app.py`'),
    ('run_agent.py', 'Agent entry: `run_agent.py`'),
    ('julius_gui.py', 'GUI entry: `julius_gui.py`'),
    ('manage.py', 'Django entry: `manage.py`'),
    ('index.js', 'Node.js entry: `index.js`'),
    ('index.ts', 'TypeScript entry: `index.ts`'),
    ('server.js', 'Server entry: `server.js`'),
]


def build_workspace_context(workspace_root: str) -> str:
    """
    Scan the workspace and build a contextual awareness block.

    This is injected into the agent's observation prompt so it understands
    the project structure, ecosystem, and available metadata without
    needing to run discovery commands.

    Args:
        workspace_root: Absolute path to the workspace root directory.

    Returns:
        A formatted string block for prompt injection, or empty string
        if no meaningful context was detected.
    """
    root = Path(workspace_root)
    if not root.is_dir():
        return ''

    parts: list[str] = ['### Workspace Context']

    # ── Project metadata from prd.json ────────────────────────────
    prd_path = root / 'prd.json'
    if prd_path.exists():
        try:
            prd = json.loads(prd_path.read_text(errors='replace'))
            name = prd.get('name') or 'Julius'
            version = prd.get('version', '?')
            description = prd.get('description', '')
            parts.append(f'**Project**: {name} v{version}')
            if description:
                parts.append(f'**Description**: {description[:120]}')
        except (json.JSONDecodeError, OSError):
            logger.debug('prd.json exists but could not be parsed.')

    # ── Task tracking ─────────────────────────────────────────────
    progress_path = root / 'progress.txt'
    if progress_path.exists():
        try:
            content = progress_path.read_text(errors='replace')
            line_count = len(content.splitlines())
            parts.append(f'**Task Tracking**: `progress.txt` present ({line_count} lines) — reference when roadmap or feature tracking is requested.')
        except OSError:
            parts.append('**Task Tracking**: `progress.txt` present — reference when roadmap or feature tracking is requested.')

    # ── Ecosystem detection ───────────────────────────────────────
    detected_ecosystems: list[str] = []
    for marker, ecosystem in _ECOSYSTEM_MARKERS:
        if (root / marker).exists():
            detected_ecosystems.append(f'{ecosystem} (`{marker}`)')

    if detected_ecosystems:
        parts.append(f'**Ecosystem(s)**: {", ".join(detected_ecosystems)}')

    # ── Entry points ──────────────────────────────────────────────
    detected_entries: list[str] = []
    for marker, description in _ENTRY_MARKERS:
        if (root / marker).exists():
            detected_entries.append(description)

    if detected_entries:
        parts.append(f'**Entry Points**: {"; ".join(detected_entries)}')

    # ── Version control ───────────────────────────────────────────
    if (root / '.git').is_dir():
        parts.append('**Git**: Repository initialized.')

    # ── Project memory rules ──────────────────────────────────────
    for rules_file in ('JULIUS.md', 'AGENTS.md', '.cursorrules', 'MEMORY.md'):
        r_path = root / rules_file
        if r_path.exists():
            try:
                parts.append(f'**Project Memory Rules**: `{rules_file}` present')
                break
            except OSError:
                pass

    # ── Container/Deployment ──────────────────────────────────────
    container_files = [f for f in ('Dockerfile', 'Containerfile', 'docker-compose.yml', 'docker-compose.yaml')
                       if (root / f).exists()]
    if container_files:
        parts.append(f'**Containerized**: {", ".join(f"`{f}`" for f in container_files)} detected.')

    # ── Framework environment identifier ──────────────────────────
    if len(parts) > 1:  # Only add if we found something
        parts.append('')
        parts.append(
            '> CURRENT FRAMEWORK ENVIRONMENT: You are working inside the '
            "'Julius' workspace. Note: Only inspect project tracking files "
            '(`prd.json`, `progress.txt`) when the user explicitly requests project-level '
            'planning, roadmap status, or feature tracking. For conversational queries, '
            'follow-up questions, or specific system commands, respond directly without '
            'consulting workspace tracking files.'
        )

    return '\n'.join(parts) if len(parts) > 1 else ''
