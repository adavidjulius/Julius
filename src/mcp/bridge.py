"""
MCP client bridge for the Julius agent.

Allows the Julius agent itself to call external MCP servers (databases,
issue boards, external APIs) and maps their tool responses back into the
agent's standard ActionResult format.

Example:
    bridge = MCPBridge('postgres-mcp', ['npx', '-y', '@modelcontextprotocol/server-postgres', DB_URL])
    await bridge.connect()
    result = await bridge.call_tool('query', {'sql': 'SELECT * FROM users LIMIT 5'})
    # result is an ActionResult compatible with the agent loop
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from mcp import types as mcp_types
    _MCP_AVAILABLE = True
except ImportError:
    _MCP_AVAILABLE = False


class MCPBridgeResult:
    """ActionResult-compatible wrapper for MCP tool responses."""
    def __init__(self, success: bool, output: str, action: str, error: str | None = None):
        self.success = success
        self.output = output
        self.action = action
        self.error = error


class MCPBridge:
    """
    Client bridge that connects to an external MCP server and exposes
    its tools to the Julius agent in ActionResult format.

    Args:
        server_name: Human-readable name for the external server.
        command: Command list to launch the MCP server process
                 (e.g. ['npx', '-y', '@modelcontextprotocol/server-postgres', url]).
    """

    def __init__(self, server_name: str, command: list[str]) -> None:
        if not _MCP_AVAILABLE:
            raise ImportError('mcp package not installed. Run: pip install mcp')
        self.server_name = server_name
        self.command = command
        self._session: 'ClientSession | None' = None
        self._tools: dict[str, 'mcp_types.Tool'] = {}
        self._context = None

    async def connect(self) -> list[str]:
        """
        Connect to the external MCP server.

        Returns:
            List of tool names available on the server.
        """
        params = StdioServerParameters(command=self.command[0], args=self.command[1:])
        self._context = stdio_client(params)
        read_stream, write_stream = await self._context.__aenter__()
        self._session = ClientSession(read_stream, write_stream)
        await self._session.__aenter__()
        await self._session.initialize()

        # Discover available tools
        tools_response = await self._session.list_tools()
        self._tools = {t.name: t for t in tools_response.tools}
        logger.info(f'MCPBridge [{self.server_name}]: connected. Tools: {list(self._tools.keys())}')
        return list(self._tools.keys())

    async def disconnect(self) -> None:
        """Disconnect from the external MCP server and clean up."""
        if self._session:
            try:
                await self._session.__aexit__(None, None, None)
            except Exception:
                pass
        if self._context:
            try:
                await self._context.__aexit__(None, None, None)
            except Exception:
                pass
        self._session = None
        self._tools = {}
        logger.info(f'MCPBridge [{self.server_name}]: disconnected')

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> MCPBridgeResult:
        """
        Call a tool on the external MCP server.

        Args:
            tool_name: Name of the tool to call.
            arguments: Tool input arguments.

        Returns:
            MCPBridgeResult with the tool output.
        """
        if not self._session:
            return MCPBridgeResult(
                success=False,
                output='MCPBridge not connected. Call connect() first.',
                action=tool_name,
                error='not_connected',
            )

        if tool_name not in self._tools:
            available = ', '.join(sorted(self._tools.keys()))
            return MCPBridgeResult(
                success=False,
                output=f'Tool "{tool_name}" not found on {self.server_name}. Available: {available}',
                action=tool_name,
                error='tool_not_found',
            )

        try:
            response = await self._session.call_tool(tool_name, arguments)
            # Collect all text content from the response
            output_parts = []
            for content in response.content:
                if hasattr(content, 'text'):
                    output_parts.append(content.text)
                else:
                    output_parts.append(json.dumps(content.__dict__, default=str))

            output = '\n'.join(output_parts) if output_parts else '(no output)'
            return MCPBridgeResult(success=True, output=output, action=tool_name)

        except Exception as exc:
            logger.error(f'MCPBridge [{self.server_name}] tool "{tool_name}" failed: {exc}')
            return MCPBridgeResult(
                success=False,
                output=f'MCP tool error: {exc}',
                action=tool_name,
                error=str(exc),
            )

    def list_tools(self) -> list[dict]:
        """Return a list of available tool descriptions for the agent's SYSTEM_PROMPT."""
        return [
            {
                'name': t.name,
                'description': t.description or '',
                'server': self.server_name,
            }
            for t in self._tools.values()
        ]

    @property
    def is_connected(self) -> bool:
        return self._session is not None
