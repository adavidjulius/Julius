# Julius Security & Privacy Architecture (WS10)

## "What Runs Where, What Leaves Your Machine"

Julius is engineered as a **local-first autonomous engineering agent**. This document specifies the exact security invariants, network boundaries, and execution isolation tiers.

---

### 1. Data Flow & Network Boundaries

```
[ Your Machine (Local) ]
┌─────────────────────────────────────────────────────────────┐
│ Workspace Files & Code       ──> Never leave machine        │
│ PKB SQLite Database          ──> Stored locally (.julius/)   │
│ HMAC Audit Ledger            ──> Cryptographically chained  │
│ OS Keychain Credentials      ──> Never exported to disk      │
│                                                             │
│ Outbound Prompt (BYOK)       ──> Official Provider API only │
│                                  (OpenAI, Anthropic, etc.)  │
└─────────────────────────────────────────────────────────────┘
```

1. **Zero Phone-Home / Zero Telemetry Default**:
   Julius operates strictly without mandatory analytics, tracking pixels, or phone-home licensing checks. OpenTelemetry tracing is strictly opt-in (`telemetry.enabled = false` by default).

2. **Official Model APIs (BYOK)**:
   All model interactions use direct HTTPS streaming APIs with user-provided API keys. Web-automation and DOM scraping of consumer chat interfaces are strictly forbidden.

3. **Consent-Gated Explicit Fallbacks**:
   Julius never silently redirects your prompts to a third-party model. If a provider fails, fallback follows an explicit list in your configuration (`providers.fallback = [...]`), displays a visible warning, and records the event in the cryptographic audit ledger. Setting `data_residency = "local_only"` completely forbids any cloud fallback.

---

### 2. Four Choke Points of Credential Redaction

Credentials, API keys, and sensitive tokens are scrubbed at four architectural choke points:
1. **PKB Indexing**: Prevents credentials in local files from entering symbol or vector index databases.
2. **Outbound Context (DLP)**: Scans every message before dispatching to an LLM provider.
3. **Application Logs**: Cleans all log lines before writing to disk or terminal.
4. **Audit Payloads**: Sanitizes all security audit ledger records.

---

### 3. Execution Sandbox Tiers

| Tier | Isolation Level | File Access | Network | Default For |
|---|---|---|---|---|
| **Tier 0** | Read-Only | Read workspace files only | Disabled | Untrusted repos, code reviewers |
| **Tier 1** | Workspace Sandbox | Writes strictly confined to workspace | Disabled | **Default for all local tasks** |
| **Tier 2** | Container Sandbox | Docker/Podman container (`--cap-drop ALL`, read-only root) | Configurable | Server / Team multi-tenant mode |
| **Tier 3** | Host Access | Time-boxed scoped grants (TTL) | Enabled | Interactive single-action approval |

---

### 4. Hard-Deny Paths

No user role, approval token, or host access grant can override the hard-deny path policy:
- `~/.ssh/**`
- `~/.aws/**`
- `~/.gnupg/**`
- `~/.config/gcloud/**`
- `**/id_rsa*`
- `/etc/shadow`
- `/etc/passwd`

