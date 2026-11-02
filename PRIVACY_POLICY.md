# Julius Privacy Policy (WS11)

*Effective Date: October 31, 2026*

Julius is designed from the ground up as a **local-first** autonomous software engineering system. We prioritize privacy, data autonomy, and transparency.

---

### 1. Information We Do NOT Collect
- **Your Source Code**: Julius never uploads, analyzes, or stores your local code files or project assets on remote company servers. All codebase indexing (PKB) is performed locally on your device.
- **Your Keystrokes or Terminal History**: Your interactions, prompts, and tool outputs stay on your local device.
- **Mandatory Analytics**: Julius contains no silent tracking telemetry.

---

### 2. Information Handled Under Bring-Your-Own-Key (BYOK)
When you instruct Julius to execute tasks using external LLM providers (e.g. OpenAI, Anthropic, Google Gemini, DeepSeek, xAI):
- Prompts, tool declarations, and context snippets relevant to your instruction are transmitted directly from your computer to the official provider endpoint using your configured API key.
- Provider data retention and usage policies apply to those transmissions. Julius does not proxy or resell API access.

---

### 3. Local Credentials
API keys and secrets are stored in your operating system's native secure credential store (macOS Keychain, Windows Credential Manager, or Linux Secret Service). They are never transmitted to Julius servers.

---

### 4. Opt-In Telemetry & Crash Diagnostics
If you explicitly enable telemetry in `~/.julius/config.toml` (`telemetry.enabled = true`), anonymized operational metrics (error codes and latencies) may be exported to your designated endpoint. If you generate a diagnostics bundle via `julius diagnostics`, sensitive paths and secrets are automatically redacted before export.

