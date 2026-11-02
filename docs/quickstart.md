# Julius Quickstart Guide (WS10)

Get up and running with Julius in **under 5 minutes**.

---

### Step 1: Automated Installation

```bash
# macOS / Linux
./install.sh

# Or start directly with the wrapper
./julius --setup
```

### Step 2: Configure Your Provider (BYOK or Local)

Julius supports bringing your own API keys or running completely local:

- **Local Ollama (Zero Cloud Costs)**:
  Start Ollama: `ollama run llama3.1`
  Julius detects Ollama automatically on `http://127.0.0.1:11434`.

- **Cloud Official APIs**:
  Set your API key in environment or OS Keychain:
  ```bash
  export NVIDIA_API_KEY="your-key"
  # or OPENAI_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY, DEEPSEEK_API_KEY
  ```

### Step 3: Run Julius Doctor

Verify that all dependencies, keychains, and permissions are optimal:
```bash
./julius doctor
```

### Step 4: Launch Your First Task

```bash
# Interactive Terminal TUI
./julius

# Or execute a direct command
./julius "Audit this repository for security risks and document findings"
```

---

### Useful CLI Commands

- `julius doctor`: System health and readiness check.
- `julius config validate`: Validate configuration schema.
- `julius audit verify`: Check cryptographic integrity of HMAC audit ledger.
- `julius stats`: Display local token usage and cost metrics.
- `julius jobs list`: View active and completed background tasks.
- `julius backup`: Take an online SQLite backup.
- `julius diagnostics`: Generate a sanitized support bundle.

