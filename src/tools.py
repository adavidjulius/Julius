"""
Canonical Tool Registry and Dynamic Deferred Tool Loading Engine (WS1.1 / WS1.2).
Implements the 2-tier tool architecture:
- Core Tools (injected into default prompt)
- Deferred Tools (loaded on-demand via ToolSearch)
- Full backward compatibility for PortingModule / execute_tool
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .models import PortingBacklog, PortingModule
from .permissions import ToolPermissionContext

logger = logging.getLogger(__name__)

# ── Canonical JSONSchemas for Core Tools ─────────────────────────────────────

CORE_TOOL_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "Bash": {
        "name": "Bash",
        "description": "Executes a bash command and returns its output. Use for shell operations, running tests, or CLI commands.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The command to execute"},
                "timeout": {"type": "number", "description": "Optional timeout in milliseconds (max 600000)"},
                "run_in_background": {"type": "boolean", "description": "Set to true to run command detached in background"},
                "description": {"type": "string", "description": "Clear, concise description of what this command does in active voice"},
            },
            "required": ["command"],
        },
    },
    "Read": {
        "name": "Read",
        "description": "Reads a file from the local filesystem with line numbers starting at 1 (cat -n format). Reads PDFs via pages parameter.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "The absolute or relative path to the file to read"},
                "offset": {"type": "integer", "description": "The line number to start reading from"},
                "limit": {"type": "integer", "description": "The number of lines to read (max 2000 lines)"},
                "pages": {"type": "string", "description": "Page range for PDF files (e.g. '1-5', '10-20')"},
                "allow_large": {"type": "boolean", "description": "Set to true to read larger files up to context limit"},
            },
            "required": ["file_path"],
        },
    },
    "Edit": {
        "name": "Edit",
        "description": "Performs exact string replacement in a file. Must have read the file in this conversation first. old_string must match uniquely.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "The path to the file to modify"},
                "old_string": {"type": "string", "description": "The exact text to replace"},
                "new_string": {"type": "string", "description": "The replacement text"},
                "replace_all": {"type": "boolean", "description": "Replace all occurrences instead of requiring unique match (default false)"},
            },
            "required": ["file_path", "old_string", "new_string"],
        },
    },
    "Write": {
        "name": "Write",
        "description": "Writes a file to the local filesystem, overwriting if one exists. If file exists, must read it first.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "The path to the file to write"},
                "content": {"type": "string", "description": "The full text content to write"},
            },
            "required": ["file_path", "content"],
        },
    },
    "Glob": {
        "name": "Glob",
        "description": "Finds files matching a glob pattern (e.g. '**/*.ts', 'src/**/*.py').",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "The glob pattern to match"},
                "path": {"type": "string", "description": "Base directory to search in (default: current directory)"},
            },
            "required": ["pattern"],
        },
    },
    "Grep": {
        "name": "Grep",
        "description": "Fast regex search across files in the workspace (ripgrep-backed).",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Regular expression pattern to search for"},
                "path": {"type": "string", "description": "Directory or file path to search within"},
                "include": {"type": "string", "description": "File glob pattern to include (e.g. '*.ts', '*.py')"},
            },
            "required": ["pattern"],
        },
    },
    "AskUserQuestion": {
        "name": "AskUserQuestion",
        "description": "Ask the user an interactive question with selectable options and optional side-by-side preview panels.",
        "parameters": {
            "type": "object",
            "properties": {
                "questions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "question": {"type": "string", "description": "The question to ask"},
                            "header": {"type": "string", "description": "Short chip label (max 12 chars)"},
                            "multiSelect": {"type": "boolean", "description": "Allow multiple options to be selected"},
                            "options": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "label": {"type": "string", "description": "Display text for option"},
                                        "description": {"type": "string", "description": "Explanation of choice"},
                                        "preview": {"type": "string", "description": "Optional markdown preview content (code snippet, mockup)"},
                                    },
                                    "required": ["label", "description"],
                                },
                            },
                        },
                        "required": ["question", "header", "options", "multiSelect"],
                    },
                },
            },
            "required": ["questions"],
        },
    },
    "ToolSearch": {
        "name": "ToolSearch",
        "description": "Fetches full schema definitions for deferred tools so they can be called. Query format: 'select:<name>' or keywords.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Query to find deferred tools (e.g. 'select:Workflow', 'workflow script')"},
                "max_results": {"type": "number", "description": "Maximum number of schemas to return (default: 5)"},
            },
            "required": ["query"],
        },
    },
    "Agent": {
        "name": "Agent",
        "description": "Launch a subagent to handle complex, multi-step tasks. 'fork' inherits context; specialized agents run isolated.",
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "The task for the agent to perform"},
                "description": {"type": "string", "description": "A short 3-5 word description of the task"},
                "subagent_type": {"type": "string", "description": "'fork' to inherit conversation context, or fresh agent name", "enum": ["fork", "general-purpose", "Explore", "Plan"]},
                "model": {"type": "string", "description": "Optional model override for the subagent"},
                "effort": {"type": "string", "description": "Reasoning effort level", "enum": ["low", "medium", "high", "xhigh", "max"]},
                "isolation": {"type": "string", "description": "Isolation mode ('worktree' creates a temporary git worktree)", "enum": ["worktree", "remote"]},
            },
            "required": ["description", "prompt"],
        },
    },
    "Skill": {
        "name": "Skill",
        "description": "Invoke a packaged skill or slash command by name.",
        "parameters": {
            "type": "object",
            "properties": {
                "skill": {"type": "string", "description": "Name of the skill from available skills"},
                "args": {"type": "string", "description": "Optional arguments for the skill"},
            },
            "required": ["skill"],
        },
    },
}

# ── Canonical JSONSchemas for Deferred Tools ─────────────────────────────────

DEFERRED_TOOL_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "Workflow": {
        "name": "Workflow",
        "description": "Execute a workflow script that orchestrates multiple subagents deterministically using agent(), parallel(), pipeline(), and phase().",
        "parameters": {
            "type": "object",
            "properties": {
                "script": {"type": "string", "description": "Self-contained workflow script beginning with export const meta = { name, description, phases }"},
                "name": {"type": "string", "description": "Name of a predefined workflow"},
                "args": {"type": "object", "description": "Input arguments exposed to script as global args"},
                "resumeFromRunId": {"type": "string", "description": "Run ID of a prior workflow to resume from"},
            },
        },
    },
    "TaskCreate": {
        "name": "TaskCreate",
        "description": "Create a new task on the session planning task board.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Short title of the task"},
                "description": {"type": "string", "description": "Detailed task description"},
            },
            "required": ["title"],
        },
    },
    "TaskGet": {
        "name": "TaskGet",
        "description": "Get status and details of a task by ID.",
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "ID of the task to retrieve"},
            },
            "required": ["task_id"],
        },
    },
    "TaskUpdate": {
        "name": "TaskUpdate",
        "description": "Update status of an active task on the board.",
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "ID of the task to update"},
                "status": {"type": "string", "enum": ["pending", "in_progress", "completed", "failed"]},
                "result": {"type": "string", "description": "Outcome or note"},
            },
            "required": ["task_id", "status"],
        },
    },
    "TaskList": {
        "name": "TaskList",
        "description": "List all tasks on the session planning task board.",
        "parameters": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "description": "Optional status filter"},
            },
        },
    },
    "TaskStop": {
        "name": "TaskStop",
        "description": "Cancel or stop an active task or background subagent by ID.",
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "ID of task to stop"},
            },
            "required": ["task_id"],
        },
    },
    "NotebookEdit": {
        "name": "NotebookEdit",
        "description": "Edit or insert cells in a Jupyter Notebook (.ipynb).",
        "parameters": {
            "type": "object",
            "properties": {
                "notebook_path": {"type": "string", "description": "Path to the notebook file"},
                "cell_number": {"type": "integer", "description": "0-indexed cell index"},
                "new_source": {"type": "string", "description": "New source text for cell"},
                "cell_type": {"type": "string", "enum": ["code", "markdown"]},
                "edit_mode": {"type": "string", "enum": ["replace", "insert_before", "insert_after", "delete"]},
            },
            "required": ["notebook_path", "cell_number", "new_source"],
        },
    },
    "ReportFindings": {
        "name": "ReportFindings",
        "description": "Report verified code-review findings as a typed list so the host UI can render them.",
        "parameters": {
            "type": "object",
            "properties": {
                "findings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "file": {"type": "string", "description": "Path of file"},
                            "line": {"type": "integer", "description": "1-indexed line number"},
                            "summary": {"type": "string", "description": "One-sentence defect statement"},
                            "failure_scenario": {"type": "string", "description": "Concrete failure trigger"},
                            "category": {"type": "string", "description": "Kebab-case category slug"},
                        },
                        "required": ["file", "summary", "failure_scenario"],
                    },
                },
                "level": {"type": "string", "enum": ["low", "medium", "high", "xhigh", "max"]},
            },
            "required": ["findings"],
        },
    },
    "ScheduleWakeup": {
        "name": "ScheduleWakeup",
        "description": "Schedule when to resume work in dynamic loop mode. Aligns delays with prompt-cache TTL (<=270s or >=1200s).",
        "parameters": {
            "type": "object",
            "properties": {
                "delaySeconds": {"type": "number", "description": "Seconds from now to wake up (clamped to [60, 3600])"},
                "prompt": {"type": "string", "description": "The prompt to fire on wake-up"},
                "reason": {"type": "string", "description": "Short explanation for chosen delay"},
                "noop": {"type": "boolean", "description": "True if nothing changed worth reporting"},
                "stop": {"type": "boolean", "description": "Set to true to end loop immediately"},
            },
        },
    },
    "EnterWorktree": {
        "name": "EnterWorktree",
        "description": "Create and switch to an isolated git worktree branch for safe experimentation.",
        "parameters": {
            "type": "object",
            "properties": {
                "branch_name": {"type": "string", "description": "Optional branch name for worktree"},
            },
        },
    },
    "ExitWorktree": {
        "name": "ExitWorktree",
        "description": "Exit the isolated git worktree and return to the main working repository.",
        "parameters": {
            "type": "object",
            "properties": {
                "discard_changes": {"type": "boolean", "description": "Discard worktree uncommitted changes"},
            },
        },
    },
    "CaptureScreen": {
        "name": "CaptureScreen",
        "description": "Capture a screenshot of the user's desktop display and detect the active frontmost window.",
        "parameters": {
            "type": "object",
            "properties": {
                "save_to_disk": {"type": "boolean", "description": "Whether to save screenshot image to disk cache"},
            },
        },
    },
    "GetActiveWindow": {
        "name": "GetActiveWindow",
        "description": "Inspect the active frontmost application name, window title, and process ID.",
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
    "GetSystemVitals": {
        "name": "GetSystemVitals",
        "description": "Collect live OS and hardware telemetry: CPU load, RAM usage, free disk space, and battery status.",
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
    "SendSystemNotification": {
        "name": "SendSystemNotification",
        "description": "Deliver a native desktop operating system notification banner with sound.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Notification title"},
                "message": {"type": "string", "description": "Notification body message"},
                "sound": {"type": "boolean", "description": "Whether to play notification sound (default true)"},
            },
            "required": ["title", "message"],
        },
    },
    "ManageClipboard": {
        "name": "ManageClipboard",
        "description": "Read or write text from/to the native system clipboard.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["read", "write"], "description": "Action: 'read' or 'write'"},
                "text": {"type": "string", "description": "Text to write when action is 'write'"},
            },
            "required": ["action"],
        },
    },
    "AppControl": {
        "name": "AppControl",
        "description": "Launch, focus, list, or quit desktop applications.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["launch", "focus", "list", "quit"], "description": "Action to perform"},
                "app_name": {"type": "string", "description": "Name of application (required for launch, focus, quit)"},
            },
            "required": ["action"],
        },
    },
    "RunTeamwork": {
        "name": "RunTeamwork",
        "description": "Deploy a specialized multi-agent squad (Architect, Developer, Security Auditor, Verifier) to solve a complex goal in parallel.",
        "parameters": {
            "type": "object",
            "properties": {
                "goal": {"type": "string", "description": "High-level goal for the team to achieve"},
                "personas": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of personas: architect, developer, security_auditor, verifier",
                },
            },
            "required": ["goal"],
        },
    },
    "GenerateImage": {
        "name": "GenerateImage",
        "description": "Generate an image using the NVIDIA NIM image generation helper model.",
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Description of the image to generate"},
                "output_path": {"type": "string", "description": "Optional file path to save image (e.g. 'generated_image.png')"},
            },
            "required": ["prompt"],
        },
    },
    "AnalyzeImage": {
        "name": "AnalyzeImage",
        "description": "Analyze an image using the NVIDIA NIM multimodal vision helper model.",
        "parameters": {
            "type": "object",
            "properties": {
                "image_path": {"type": "string", "description": "Path to image file"},
                "prompt": {"type": "string", "description": "Question or analysis prompt"},
            },
            "required": ["image_path"],
        },
    },
}


# ── Dynamic ToolSearch Resolver ──────────────────────────────────────────────


def resolve_tool_search(query: str, max_results: int = 5) -> str:
    """
    Search deferred tools and return loaded schemas wrapped in <functions> XML.
    Supports 'select:<name>' (or comma-separated 'select:Workflow,TaskCreate') and keyword matching.
    """
    selected_tools: List[Dict[str, Any]] = []
    q = query.strip()

    if q.lower().startswith("select:"):
        names_str = q[7:].strip()
        names = [n.strip() for n in names_str.split(",") if n.strip()]
        for name in names:
            # Check deferred tools first
            for dt_name, dt_schema in DEFERRED_TOOL_SCHEMAS.items():
                if dt_name.lower() == name.lower():
                    selected_tools.append(dt_schema)
                    break
            else:
                # Check core tools
                for ct_name, ct_schema in CORE_TOOL_SCHEMAS.items():
                    if ct_name.lower() == name.lower():
                        selected_tools.append(ct_schema)
                        break
    else:
        # Keyword search over deferred tools
        words = [w.lower() for w in q.split() if w]
        scored: List[Tuple[int, Dict[str, Any]]] = []
        for name, schema in DEFERRED_TOOL_SCHEMAS.items():
            desc = schema.get("description", "").lower()
            name_lower = name.lower()
            score = sum(3 for w in words if w in name_lower) + sum(1 for w in words if w in desc)
            if score > 0:
                scored.append((score, schema))
        scored.sort(key=lambda x: x[0], reverse=True)
        selected_tools = [s for _, s in scored[:max_results]]

    if not selected_tools:
        return f"<functions>\n<!-- No deferred tools matched query '{query}'. Available deferred tools: {', '.join(DEFERRED_TOOL_SCHEMAS.keys())} -->\n</functions>"

    function_lines = []
    for schema in selected_tools:
        json_line = json.dumps(schema, separators=(",", ":"))
        function_lines.append(f"<function>{json_line}</function>")

    return f"<functions>\n" + "\n".join(function_lines) + "\n</functions>"


# ── Backward Compatibility: Mirrored Porting Modules ─────────────────────────


SNAPSHOT_PATH = Path(__file__).resolve().parent / 'reference_data' / 'tools_snapshot.json'


@dataclass(frozen=True)
class ToolExecution:
    name: str
    source_hint: str
    payload: str
    handled: bool
    message: str


def _generate_modules_from_schemas() -> tuple[PortingModule, ...]:
    modules = []
    for name, s in CORE_TOOL_SCHEMAS.items():
        modules.append(PortingModule(name=name, responsibility=s["description"][:100], source_hint="core_schema", status="active"))
    for name, s in DEFERRED_TOOL_SCHEMAS.items():
        modules.append(PortingModule(name=name, responsibility=s["description"][:100], source_hint="deferred_schema", status="deferred"))
    return tuple(modules)


PORTED_TOOLS: tuple[PortingModule, ...] = _generate_modules_from_schemas()


def build_tool_backlog() -> PortingBacklog:
    return PortingBacklog(title='Tool surface', modules=list(PORTED_TOOLS))


def tool_names() -> list[str]:
    return [module.name for module in PORTED_TOOLS]


def get_tool(name: str) -> PortingModule | None:
    needle = name.lower()
    for module in PORTED_TOOLS:
        if module.name.lower() == needle:
            return module
    return None


def get_tools(
    simple_mode: bool = False,
    include_mcp: bool = True,
    permission_context: ToolPermissionContext | None = None,
) -> tuple[PortingModule, ...]:
    tools = list(PORTED_TOOLS)
    if simple_mode:
        tools = [module for module in tools if module.name in {'Bash', 'Read', 'Edit', 'Write'}]
    return tuple(tools)


def find_tools(query: str, limit: int = 20) -> list[PortingModule]:
    needle = query.lower()
    matches = [module for module in PORTED_TOOLS if needle in module.name.lower() or needle in module.responsibility.lower()]
    return matches[:limit]


def execute_tool(name: str, payload: str = '', permission_context: ToolPermissionContext | None = None) -> ToolExecution:
    """Dispatches execution to ToolSearch if requested, or returns handled execution."""
    if name.lower() == "toolsearch":
        result = resolve_tool_search(payload)
        return ToolExecution(name="ToolSearch", source_hint="core", payload=payload, handled=True, message=result)
    return ToolExecution(name=name, source_hint="core", payload=payload, handled=True, message=f"Executed tool '{name}'.")


def render_tool_index(limit: int = 20, query: str | None = None) -> str:
    modules = find_tools(query, limit) if query else list(PORTED_TOOLS[:limit])
    lines = [f'Total Registered Tools: {len(PORTED_TOOLS)} (Core: {len(CORE_TOOL_SCHEMAS)}, Deferred: {len(DEFERRED_TOOL_SCHEMAS)})', '']
    if query:
        lines.append(f'Filtered by: {query}')
        lines.append('')
    lines.extend(f'- {module.name} [{module.status}] — {module.responsibility}' for module in modules)
    return '\n'.join(lines)
