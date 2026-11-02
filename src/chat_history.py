"""Persistent chat history — survives program restarts.

History is stored in ~/.julius/chat_history.jsonl (one JSON object per line).
Each entry represents one completed agent run (task + all step records).

Public API
----------
append_run(task, steps, summary, success)  — save a completed run
load_all()                                  — return list of all saved runs
delete_all()                                — wipe the entire history file
delete_run(run_id)                          — remove a single run by its id
print_history()                             — pretty-print history to stdout
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from rich.console import Console
    from rich.table import Table
    from rich.text import Text
    _console = Console()
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

HISTORY_DIR = Path.home() / '.julius'
HISTORY_FILE = HISTORY_DIR / 'chat_history.jsonl'


def _ensure_dir() -> None:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)


def append_run(
    task: str,
    steps: list[dict[str, Any]],
    summary: str,
    success: bool,
    provider: str = 'unknown',
) -> str:
    """Append one completed agent run to history. Returns the run_id."""
    _ensure_dir()
    run_id = str(uuid.uuid4())[:8]
    entry = {
        'run_id': run_id,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'task': task,
        'provider': provider,
        'success': success,
        'summary': summary,
        'total_steps': len(steps),
        'steps': steps,
    }
    with HISTORY_FILE.open('a', encoding='utf-8') as f:
        f.write(json.dumps(entry) + '\n')
    return run_id


def load_all() -> list[dict[str, Any]]:
    """Return all saved runs, oldest first."""
    if not HISTORY_FILE.exists():
        return []
    runs: list[dict[str, Any]] = []
    with HISTORY_FILE.open('r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    runs.append(json.loads(line))
                except json.JSONDecodeError:
                    pass  # skip corrupted lines
    return runs


def delete_all() -> int:
    """Delete all history. Returns number of runs deleted."""
    if not HISTORY_FILE.exists():
        return 0
    runs = load_all()
    count = len(runs)
    HISTORY_FILE.unlink()
    return count


def delete_run(run_id: str) -> bool:
    """Delete a single run by run_id. Returns True if found and removed."""
    runs = load_all()
    original_count = len(runs)
    runs = [r for r in runs if r.get('run_id') != run_id]
    if len(runs) == original_count:
        return False  # not found
    _ensure_dir()
    with HISTORY_FILE.open('w', encoding='utf-8') as f:
        for run in runs:
            f.write(json.dumps(run) + '\n')
    return True


def print_history(limit: int | None = None) -> None:
    """Pretty-print saved history to stdout."""
    runs = load_all()
    if not runs:
        if HAS_RICH:
            _console.print('[dim]No chat history found. Run a task first![/dim]')
        else:
            print('No chat history found. Run a task first!')
        return

    display = runs[-limit:] if limit else runs

    if HAS_RICH:
        table = Table(title=f'Julius — Chat History ({len(runs)} total run(s))', show_lines=True)
        table.add_column('Run ID', style='dim', width=10)
        table.add_column('Date/Time', width=22)
        table.add_column('Provider', width=12)
        table.add_column('Status', width=8)
        table.add_column('Steps', width=6, justify='right')
        table.add_column('Task', no_wrap=False)
        table.add_column('Summary', no_wrap=False)

        for run in display:
            ts = run.get('timestamp', '')
            try:
                dt = datetime.fromisoformat(ts)
                ts_fmt = dt.strftime('%Y-%m-%d %H:%M UTC')
            except Exception:
                ts_fmt = ts

            status_icon = '[green]✅[/green]' if run.get('success') else '[red]❌[/red]'
            table.add_row(
                run.get('run_id', '?'),
                ts_fmt,
                run.get('provider', '?'),
                Text.from_markup(status_icon),
                str(run.get('total_steps', '?')),
                run.get('task', '')[:120],
                run.get('summary', '')[:200],
            )
        _console.print(table)
    else:
        print(f'\n=== Julius Chat History ({len(runs)} total run(s)) ===')
        for i, run in enumerate(display, 1):
            ts = run.get('timestamp', 'unknown time')
            status = '✅ Success' if run.get('success') else '❌ Failed'
            print(f'\n[{i}] Run ID : {run.get("run_id", "?")}')
            print(f'    Time    : {ts}')
            print(f'    Provider: {run.get("provider", "?")}')
            print(f'    Status  : {status}')
            print(f'    Steps   : {run.get("total_steps", "?")}')
            print(f'    Task    : {run.get("task", "")[:120]}')
            print(f'    Summary : {run.get("summary", "")[:200]}')
        print()
