"""
Model Context Protocol (MCP) server for the Julius agent.

Exposes Julius's core tools as MCP-compatible tool endpoints, allowing
external applications (databases, issue trackers, IDEs, other AI agents)
to connect and invoke Julius's capabilities through the standard protocol.

Protocol: https://modelcontextprotocol.io

Usage:
    python -m src.mcp.server --workspace /path/to/project --port 3000
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp import types as mcp_types
    _MCP_AVAILABLE = True
except ImportError:
    _MCP_AVAILABLE = False

# ── Tool definitions (matches ActionExecutor capabilities) ────────────────────

_TOOL_DEFINITIONS = [
    {
        'name': 'run_bash',
        'description': 'Execute a shell command in the agent workspace and return its output.',
        'inputSchema': {
            'type': 'object',
            'properties': {
                'command': {'type': 'string', 'description': 'The shell command to run.'},
            },
            'required': ['command'],
        },
    },
    {
        'name': 'read_file',
        'description': 'Read a file from the workspace, optionally restricted to a line range.',
        'inputSchema': {
            'type': 'object',
            'properties': {
                'path': {'type': 'string', 'description': 'Path to the file.'},
                'start_line': {'type': 'integer', 'description': 'First line to read (1-indexed).'},
                'end_line': {'type': 'integer', 'description': 'Last line to read (1-indexed, inclusive).'},
            },
            'required': ['path'],
        },
    },
    {
        'name': 'write_file',
        'description': 'Create or overwrite a file in the workspace.',
        'inputSchema': {
            'type': 'object',
            'properties': {
                'path': {'type': 'string', 'description': 'Destination path.'},
                'content': {'type': 'string', 'description': 'Full file content to write.'},
            },
            'required': ['path', 'content'],
        },
    },
    {
        'name': 'edit_file',
        'description': 'Replace a specific string in a file.',
        'inputSchema': {
            'type': 'object',
            'properties': {
                'path': {'type': 'string', 'description': 'Path to the file.'},
                'old_text': {'type': 'string', 'description': 'The exact text to replace.'},
                'new_text': {'type': 'string', 'description': 'The replacement text.'},
            },
            'required': ['path', 'old_text', 'new_text'],
        },
    },
    {
        'name': 'list_dir',
        'description': 'List the contents of a directory.',
        'inputSchema': {
            'type': 'object',
            'properties': {
                'path': {'type': 'string', 'description': 'Directory path (default: workspace root).'},
            },
        },
    },
    {
        'name': 'search_files',
        'description': 'Search for a pattern across files (like grep).',
        'inputSchema': {
            'type': 'object',
            'properties': {
                'pattern': {'type': 'string', 'description': 'Search pattern.'},
                'path': {'type': 'string', 'description': 'Directory to search in.'},
            },
            'required': ['pattern'],
        },
    },
    {
        'name': 'list_symbols',
        'description': 'List all functions and classes in a source file using AST parsing.',
        'inputSchema': {
            'type': 'object',
            'properties': {
                'path': {'type': 'string', 'description': 'Path to the source file.'},
            },
            'required': ['path'],
        },
    },
    {
        'name': 'read_symbol',
        'description': 'Extract the full source code of a named function or class.',
        'inputSchema': {
            'type': 'object',
            'properties': {
                'path': {'type': 'string', 'description': 'Path to the source file.'},
                'symbol': {'type': 'string', 'description': 'Name of the function or class.'},
            },
            'required': ['path', 'symbol'],
        },
    },
    {
        'name': 'capcut_list_projects',
        'description': 'List all CapCut Desktop projects, drafts, durations, and metadata.',
        'inputSchema': {'type': 'object', 'properties': {}},
    },
    {
        'name': 'capcut_get_project',
        'description': 'Inspect timeline tracks, video/audio clips, text overlays, and duration of a CapCut project.',
        'inputSchema': {
            'type': 'object',
            'properties': {
                'project_name': {'type': 'string', 'description': 'Name of the CapCut project draft.'},
            },
            'required': ['project_name'],
        },
    },
    {
        'name': 'capcut_create_project',
        'description': 'Create a new CapCut Desktop project with specified dimensions, aspect ratio, and framerate.',
        'inputSchema': {
            'type': 'object',
            'properties': {
                'project_name': {'type': 'string', 'description': 'Name of the project to create.'},
                'width': {'type': 'integer', 'description': 'Width in pixels (e.g. 1920 or 3840).'},
                'height': {'type': 'integer', 'description': 'Height in pixels (e.g. 1080 or 2160).'},
                'fps': {'type': 'integer', 'description': 'Framerate in FPS (default 30).'},
                'aspect_ratio': {'type': 'string', 'description': 'Ratio: 16:9, 9:16, 1:1, etc.'},
            },
            'required': ['project_name'],
        },
    },
    {
        'name': 'capcut_add_video_clip',
        'description': 'Add a video clip to project timeline with millisecond precision positioning, transitions, and audio envelope.',
        'inputSchema': {
            'type': 'object',
            'properties': {
                'project_name': {'type': 'string', 'description': 'Target project name.'},
                'file_path': {'type': 'string', 'description': 'Path to local video file.'},
                'start_time': {'type': 'number', 'description': 'In-point in seconds (default 0.0).'},
                'start_time_ms': {'type': 'number', 'description': 'In-point in milliseconds.'},
                'duration': {'type': 'number', 'description': 'Duration in seconds.'},
                'duration_ms': {'type': 'number', 'description': 'Duration in milliseconds.'},
                'target_start': {'type': 'number', 'description': 'Timeline start in seconds.'},
                'target_start_ms': {'type': 'number', 'description': 'Timeline start in milliseconds.'},
                'speed': {'type': 'number', 'description': 'Playback speed multiplier.'},
                'volume': {'type': 'number', 'description': 'Volume 0.0 to 2.0.'},
                'transition': {'type': 'string', 'description': 'Transition type name.'},
            },
            'required': ['project_name', 'file_path'],
        },
    },
    {
        'name': 'capcut_add_audio_clip',
        'description': 'Add an audio or BGM soundtrack to project timeline with volume envelope and millisecond precision.',
        'inputSchema': {
            'type': 'object',
            'properties': {
                'project_name': {'type': 'string', 'description': 'Target project name.'},
                'file_path': {'type': 'string', 'description': 'Path to local audio file.'},
                'start_time': {'type': 'number', 'description': 'In-point in seconds.'},
                'duration': {'type': 'number', 'description': 'Duration in seconds.'},
                'target_start': {'type': 'number', 'description': 'Timeline start in seconds.'},
                'volume': {'type': 'number', 'description': 'Volume 0.0 to 2.0.'},
            },
            'required': ['project_name', 'file_path'],
        },
    },
    {
        'name': 'capcut_split_clip',
        'description': 'Split a clip on the CapCut timeline at an exact millisecond timestamp into two separate clips.',
        'inputSchema': {
            'type': 'object',
            'properties': {
                'project_name': {'type': 'string', 'description': 'Target project name.'},
                'track_index': {'type': 'integer', 'description': 'Track index (default 0).'},
                'segment_index': {'type': 'integer', 'description': 'Segment index (default 0).'},
                'split_time': {'type': 'number', 'description': 'Split point in seconds.'},
                'split_time_ms': {'type': 'number', 'description': 'Split point in milliseconds.'},
            },
            'required': ['project_name'],
        },
    },
    {
        'name': 'capcut_trim_clip',
        'description': 'Trim clip in/out points and timeline start/duration down to milliseconds.',
        'inputSchema': {
            'type': 'object',
            'properties': {
                'project_name': {'type': 'string', 'description': 'Target project name.'},
                'track_index': {'type': 'integer', 'description': 'Track index.'},
                'segment_index': {'type': 'integer', 'description': 'Segment index.'},
                'target_start_ms': {'type': 'number', 'description': 'New timeline start in ms.'},
                'duration_ms': {'type': 'number', 'description': 'New duration in ms.'},
                'source_start_ms': {'type': 'number', 'description': 'New source in-point in ms.'},
            },
            'required': ['project_name'],
        },
    },
    {
        'name': 'capcut_beat_sync_edit',
        'description': 'Assemble a multi-clip video montage beat-synced to music down to milliseconds.',
        'inputSchema': {
            'type': 'object',
            'properties': {
                'project_name': {'type': 'string', 'description': 'Project name to create.'},
                'video_clips': {'type': 'array', 'items': {'type': 'string'}, 'description': 'List of clip paths.'},
                'music_path': {'type': 'string', 'description': 'Path to BGM audio file.'},
                'bpm': {'type': 'number', 'description': 'Beats per minute (default 120.0).'},
                'beats_per_cut': {'type': 'integer', 'description': 'Beats per cut (default 4).'},
                'target_duration': {'type': 'number', 'description': 'Duration in seconds.'},
                'transition': {'type': 'string', 'description': 'Optional transition name.'},
                'effects': {'type': 'array', 'items': {'type': 'string'}, 'description': 'Optional scene effects.'},
            },
            'required': ['project_name', 'video_clips', 'music_path'],
        },
    },
    {
        'name': 'capcut_save_draft',
        'description': 'Validate, scaffold, and synchronize a draft for 100% openability in CapCut Desktop.',
        'inputSchema': {
            'type': 'object',
            'properties': {
                'project_name': {'type': 'string', 'description': 'Project name.'},
            },
            'required': ['project_name'],
        },
    },
    {
        'name': 'capcut_open_in_app',
        'description': 'Launch or switch to CapCut Desktop macOS application and open the project.',
        'inputSchema': {
            'type': 'object',
            'properties': {
                'project_name': {'type': 'string', 'description': 'Optional project name.'},
            },
        },
    },
    {
        'name': 'capcut_fix_network_and_effects',
        'description': 'Unblock CapCut network dropping & geo-restrictions so effects and materials work permanently without VPN.',
        'inputSchema': {'type': 'object', 'properties': {}},
    },
    {
        'name': 'capcut_inspect_timeline_ui',
        'description': 'Generate interactive HTML timeline inspector view (MCP App UI) for a project.',
        'inputSchema': {
            'type': 'object',
            'properties': {
                'project_name': {'type': 'string', 'description': 'Project name.'},
            },
            'required': ['project_name'],
        },
    },
]


def build_mcp_server(workspace: str, permission_gate: Any | None = None) -> 'Server':
    """
    Create and configure the MCP server instance.

    Args:
        workspace: Absolute path to the agent's workspace directory.
        permission_gate: Optional PermissionGate instance for tool authorization.

    Returns:
        A configured MCP Server ready to run.
    """
    if not _MCP_AVAILABLE:
        raise ImportError('mcp package not installed. Run: pip install mcp')

    from src.action_executor import ActionExecutor

    executor = ActionExecutor(workspace_root=workspace, permission_gate=permission_gate)
    server = Server('julius-agent')

    @server.list_tools()
    async def list_tools() -> list[mcp_types.Tool]:
        return [
            mcp_types.Tool(
                name=t['name'],
                description=t['description'],
                inputSchema=t['inputSchema'],
            )
            for t in _TOOL_DEFINITIONS
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[mcp_types.TextContent]:
        """Dispatch an MCP tool call to the ActionExecutor with permission checks."""
        if permission_gate:
            try:
                from src.permission_gate import ActionType, PermissionResponse
                resp = await permission_gate.request_permission(
                    action_type=ActionType.MCP_CALL,
                    payload=f"{name}({json.dumps(arguments)})",
                    description=f"MCP client requested tool '{name}'",
                    server_name="julius-agent",
                    tool_name=name,
                )
                if resp not in (PermissionResponse.APPROVE_ONCE, PermissionResponse.APPROVE_SESSION):
                    return [mcp_types.TextContent(
                        type='text',
                        text=f"Execution of tool '{name}' was blocked by the Julius permission gate.",
                    )]
            except Exception as exc:
                logger.error(f"Permission gate error for tool {name}: {exc}")

        result = executor.execute(name, arguments)
        return [mcp_types.TextContent(
            type='text',
            text=result.output,
        )]

    return server


async def run_server(workspace: str) -> None:
    """Run the MCP server on stdio (standard MCP transport)."""
    server = build_mcp_server(workspace)
    logger.info(f'Julius MCP server starting (workspace: {workspace})')
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Julius MCP Server')
    parser.add_argument('--workspace', default='.', help='Workspace root directory')
    parser.add_argument('--log-level', default='INFO', help='Logging level')
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO))

    if not _MCP_AVAILABLE:
        print('Error: mcp package not installed. Run: pip install mcp', file=sys.stderr)
        sys.exit(1)

    import asyncio
    asyncio.run(run_server(args.workspace))
