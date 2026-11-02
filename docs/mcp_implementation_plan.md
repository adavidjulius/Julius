# MCP Implementation Plan for Julius

**Date:** 2026-06-20  
**Status:** Planning Phase  
**Estimated Timeline:** ~1 week

---

## 1. Current State Assessment

- MCP referenced in PRD stories:
  - **US-007**: Plugin/MCP lifecycle maturity
  - **US-004**: Recovery recipes include MCP_handshake_failure
- No MCP implementation exists in the Python codebase yet
- Plugin architecture already exists (referenced in US-007)

---

## 2. Recommended MCP Servers (Priority Order)

### 2.1 filesystem (MCP Server)
| Property | Value |
|----------|-------|
| **Priority** | 1 (Highest) |
| **Rationale** | Most foundational — gives agents ability to read/write files, essential for any coding task |
| **Implementation** | `@modelcontextprotocol/server-filesystem` npm package |
| **Use Cases** | File operations, code reading/writing, project exploration |

### 2.2 github (MCP Server)
| Property | Value |
|----------|-------|
| **Priority** | 2 |
| **Rationale** | PRD is focused on git workflows (US-003 stale branch detection, US-006 policy engine) |
| **Implementation** | `@modelcontextprotocol/server-github` or custom GitHub API wrapper |
| **Use Cases** | PR creation, issue management, repo operations |

### 2.3 brave-search (MCP Server)
| Property | Value |
|----------|-------|
| **Priority** | 3 |
| **Rationale** | Adds web search capability for debugging and research |
| **Implementation** | `@modelcontextprotocol/server-brave-search` |
| **Use Cases** | Researching error messages, finding documentation |

### 2.4 memory (MCP Server)
| Property | Value |
|----------|-------|
| **Priority** | 4 |
| **Rationale** | Knowledge persistence across sessions |
| **Implementation** | `@modelcontextprotocol/server-memory` |
| **Use Cases** | Remembering decisions, patterns, and project context |

---

## 3. Implementation Approach

### Phase 1: Infrastructure (2-3 days)

#### 3.1 Add MCP Client Library
**Options:**
- **Option A (Recommended):** Official `mcp` Python package
  - Faster implementation
  - Adds external dependency
  - Community-supported
- **Option B:** Custom SSE/stdio client from scratch
  - More control
  - No additional dependencies
  - More development time

#### 3.2 MCP Client Class
**File:** `src/mcp_client.py`

**Required Functionality:**
- Connect to MCP servers via stdio/SSE
- Handle tool discovery and invocation
- Manage connection lifecycle:
  - Startup
  - Healthcheck
  - Shutdown

**Class Structure:**
```python
class MCPClient:
    def __init__(self, config: MCPConfig):
        """Initialize MCP client with server configuration."""
        
    def connect(self, server_name: str) -> bool:
        """Establish connection to an MCP server."""
        
    def discover_tools(self, server_name: str) -> list[Tool]:
        """Discover available tools from a server."""
        
    def invoke_tool(self, server_name: str, tool_name: str, params: dict) -> dict:
        """Invoke a tool on a server."""
        
    def healthcheck(self, server_name: str) -> HealthStatus:
        """Check server health status."""
        
    def shutdown(self, server_name: str) -> bool:
        """Gracefully shutdown a server connection."""
```

#### 3.3 MCP Configuration
**Location (Decision Pending):**
- Option A: `.julius.json` (centralized)
- Option B: `mcp_config.json` (cleanly separated)

**Configuration Schema:**
```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": [
        "-y",
        "@modelcontextprotocol/server-filesystem",
        "/path/to/workspace"
      ],
      "env": {},
      "autoStart": true
    },
    "github": {
      "command": "npx",
      "args": [
        "-y",
        "@modelcontextprotocol/server-github"
      ],
      "env": {
        "GITHUB_TOKEN": "${GITHUB_TOKEN}"
      },
      "autoStart": false
    }
  }
}
```

---

### Phase 2: Integration with Agent (2-3 days)

#### 4.1 Tool Wrapper
**File:** `src/mcp_tools.py`

**Purpose:** Translate MCP tools to agent actions

**Implementation:**
```python
class MCPToolWrapper:
    def __init__(self, client: MCPClient):
        """Initialize wrapper with MCP client."""
        
    def get_action_for_tool(self, tool: Tool) -> Action:
        """Map MCP tool to agent action."""
        
    def execute_tool_action(self, action: Action) -> Result:
        """Execute mapped action via MCP."""
```

#### 4.2 MCP Health Check Integration
**Integration Points:**
- Worker startup lifecycle (US-007)
- Periodic health checks
- Degraded-mode behavior

**Health Check Flow:**
1. On worker startup, attempt to connect to all configured MCP servers
2. Report connection status (connected, degraded, failed)
3. If critical servers are down, trigger recovery (US-004)
4. Expose health status via structured events

#### 4.3 Recovery Handling
**Recovery Recipe:** `MCP_handshake_failure`

**Recovery Steps:**
1. Attempt reconnect with exponential backoff
2. If first retry fails, escalate to user
3. Log failure in recovery ledger
4. Emit `MCP_handshake_failure` event with structured data

---

### Phase 3: Testing & Documentation (1-2 days)

#### 5.1 Unit Tests
**File:** `tests/test_mcp_client.py`

**Test Coverage:**
- MCP client connection lifecycle
- Tool discovery and invocation
- Health check functionality
- Error handling and recovery
- Configuration parsing

**Test Structure:**
```python
class TestMCPClient:
    def test_connect_to_server(self):
        """Test successful connection to MCP server."""
        
    def test_discover_tools(self):
        """Test tool discovery from server."""
        
    def test_invoke_tool(self):
        """Test tool invocation."""
        
    def test_healthcheck(self):
        """Test health status reporting."""
        
    def test_connection_failure_recovery(self):
        """Test recovery from connection failure."""
```

#### 5.2 Integration Tests
**File:** `tests/test_mcp_integration.py`

**Test Scope:**
- Actual MCP server communication (mock or real)
- End-to-end tool execution
- Configuration validation
- Multi-server scenarios

#### 5.3 Documentation
**File:** `docs/MCP.md`

**Documentation Sections:**
1. **Overview** — What is MCP and why we use it
2. **Installation** — Installing dependencies (Node.js, Python packages)
3. **Configuration** — How to configure MCP servers
4. **Usage** — How to use MCP tools in Julius
5. **Troubleshooting** — Common issues and solutions
6. **Adding New Servers** — How to add additional MCP servers

---

## 4. Timeline Summary

| Phase | Description | Duration |
|-------|-------------|----------|
| **Phase 1** | Infrastructure (client, config) | 2-3 days |
| **Phase 2** | Integration with Agent | 2-3 days |
| **Phase 3** | Testing & Documentation | 1-2 days |
| **Total** | Full Implementation | **~1 week** |

---

## 5. Open Decisions (Pending)

| # | Decision | Options | Recommendation |
|---|----------|---------|----------------|
| **D1** | MCP Python SDK | A: Official `mcp` package<br>B: Custom client from scratch | **A** — Faster to implement |
| **D2** | Server Execution | A: Node.js (`npx`)<br>B: Python-native servers | **A** — Official servers use Node.js |
| **D3** | Config Location | A: `.julius.json`<br>B: `mcp_config.json` | **B** — Clean separation |
| **D4** | Auto-Start Strategy | A: Auto-start all at boot<br>B: On-demand startup | **B** — Lighter resource usage |

---

## 6. Success Criteria

- [ ] MCP client can connect to at least one MCP server
- [ ] MCP tools are discoverable and invocable by the agent
- [ ] Health check integration reports server status
- [ ] Recovery handling works for handshake failures
- [ ] Unit tests pass with >80% coverage
- [ ] Documentation is complete and actionable
- [ ] No regressions in existing functionality

---

## 7. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Node.js not installed | High | Add Node.js dependency check; provide install instructions |
| MCP server compatibility | Medium | Test with multiple server versions; pin versions in config |
| Performance overhead | Low | On-demand startup strategy minimizes overhead |
| API changes in MCP spec | Medium | Abstract MCP client layer; version-pin dependencies |

---

**Prepared by:** Julius  
**Date:** 2026-06-20  
**Version:** 1.0