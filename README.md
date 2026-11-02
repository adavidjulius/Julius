# Julius

<p align="center">
  <img src="assets/branding/logo.svg" alt="Julius Logo" width="100" height="100" />
</p>

<p align="center">
  <b>Autonomous AI Agent & Multi-Modal System Copilot</b><br>
  <i>Tactile TypeScript TUI · Direct 550B Streaming API · Sandboxed Interactive Canvas · Multi-Tier Memory</i>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg?style=flat-square" alt="License: MIT"></a>
  <a href="CONTRIBUTING.md"><img src="https://img.shields.io/badge/PRs-Welcome-brightgreen.svg?style=flat-square" alt="PRs Welcome"></a>
  <img src="https://img.shields.io/badge/Status-Work%20in%20Progress%20(WIP)-orange.svg?style=flat-square" alt="Status: Work in Progress">
  <img src="https://img.shields.io/badge/Language-TypeScript%20%7C%20Python-3178C6.svg?style=flat-square" alt="TypeScript and Python">
  <img src="https://img.shields.io/badge/Python-3.11%2B-blue.svg?style=flat-square" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/Default%20Model-Nemotron%20550B%20(Free%20NIM)-76B900.svg?style=flat-square" alt="Nemotron 550B Free NIM">
</p>

---

<p align="center">
  <img src="assets/real_tui_screenshot.svg" alt="Julius Terminal Interface (TUI) Showcase" width="880" />
</p>

---

## What is Julius?

**Julius** is an open-source autonomous AI system and coding agent designed to combine deep reasoning models with a tactile, fluid developer experience. 

Unlike conventional CLI chat wrappers, Julius features a high-performance **TypeScript terminal interface (TUI)** built on Ink and React, renders **live sandboxed HTML/JS widgets inline** for data telemetry and visual controls, maintains a **6-tier hierarchical memory engine**, and operates **100% on direct streaming APIs** (featuring free 550B model inference via NVIDIA Build NIM out-of-the-box).

---

## Key Features & Tech Stack

### Key Features
- **Direct Streaming API Architecture**: Pure HTTP streaming inference with sub-millisecond response latency. Runs on NVIDIA Build NIM 550B (`nvidia/nemotron-3-ultra-550b-a55b`) with built-in sliding-window rate limiting (40 RPM, 1.5s pacing, exponential 429 backoff). Fully supports local Ollama endpoints and cloud providers (Anthropic Claude, OpenAI, DeepSeek, Gemini).
- **Tactile TypeScript TUI**: Clean, modern terminal user interface (`src/tui_ts/`) built on React and Ink. Features formatted markdown, syntax highlighting, quiet collapsible thinking indicators, and strict cursor standard compliance (arrow pointer and solid block cursor).
- **Sandboxed Interactive Widget Canvas**: Inline HTML/CSS/JavaScript canvas adhering to the Julius design token system for real-time telemetry dashboards, interactive charts, and live git diff viewers.
- **6-Tier Hierarchical Memory & PKB**: Comprehensive memory management including session working memory, episodic reflections, failure recovery ledgers, vector similarity embeddings, and an AST Tree-sitter Project Knowledge Base (PKB).
- **Autonomous Tooling Suite**: Deep OS tool execution (filesystem operations, bash/powershell command execution, web research, search grounding with SearXNG).
- **Multi-Platform Support**: Engineered from the ground up for seamless operation across Linux, macOS, and Windows.

### Tech Stack
- **Frontend & TUI**: TypeScript, React, Ink, Chalk, Node.js (v18+)
- **Core Engine & Backend**: Python 3.11+, AsyncIO, Pydantic, HTTPX, SQLite3
- **Inference Providers**: Direct HTTP REST APIs (NVIDIA Build NIM, Ollama, Anthropic, OpenAI, DeepSeek)
- **Web & Tooling**: Playwright (reserved exclusively for browser navigation & web transport)
- **Security & Sandboxing**: Cryptographic hash audit ledgers and strict allowlist execution boundaries

---

## Architecture & Folder Structure

```text
Julius/
├── .github/
│   └── workflows/              # GitHub Actions CI matrices (Linux, macOS, Windows)
├── assets/
│   ├── branding/               # Brand logos, vector badges, and icon sets
│   ├── fonts/                  # Custom Julius typography and variable web fonts
│   └── media/                  # Official TUI screenshots and showcase visuals
├── apps/
│   ├── ios/                    # Julius iOS companion client
│   └── web/                    # Tactile Web Interface (Julius_Web_Interface)
├── config/                     # Default agent configurations and security policies
├── docs/                       # Architectural specifications and design system tokens
├── frontend/                   # Local dashboard and UI components
├── scripts/                    # Supply chain license audits, verification gates, and tooling
├── src/                        # Core agent source code
│   ├── arch_discovery/         # AST code analysis & model discovery pipeline
│   ├── browser/                # Sandboxed browser navigation tooling
│   ├── cli/                    # CLI presenter, spinners, and command dispatch
│   ├── integrations/           # WhatsApp, Spotify, and system integrations
│   ├── memory/                 # 6-tier hierarchical memory & session stores
│   ├── pkb/                    # Project Knowledge Base AST symbol graph
│   ├── providers/              # Direct API LLM connectors (NVIDIA, Ollama, Cloud)
│   ├── security/               # Cryptographic audit ledger & safety guardrails
│   ├── tools/                  # Autonomous tool implementations (fs, bash, web)
│   ├── tui_ts/                 # High-performance TypeScript/Ink terminal interface
│   └── widgets/                # Dynamic sandboxed interactive HTML/JS canvas
├── tests/                      # Unified automated test suite
│   ├── adversarial/            # Security hardening and policy bypass verification
│   ├── music/                  # Audio streaming and FLAC import tests
│   ├── platform/               # OS-specific adapters and terminal compatibility
│   └── whatsapp/               # Messaging protocol and router tests
├── .env.example                # Example environment configuration with placeholders
├── CONTRIBUTING.md             # Contributor guidelines and workflow
├── LICENSE                     # MIT License
├── install.sh                  # Native installer for Linux, macOS, and WSL
├── install.ps1                 # Native Windows PowerShell installer
├── pyproject.toml              # Standardized package metadata and pytest configuration
├── requirements.txt            # Python dependencies
└── julius.py                   # Primary agent launcher
```

---

## Step-by-Step Quick Start Guide (For Beginners)

### 1. Clone the Repository
```bash
git clone https://github.com/adavidjulius/Julius.git
cd Julius
```

### 2. Run the Native One-Line Installer

<details open>
<summary><b>macOS & Linux</b></summary>

```bash
bash install.sh
```
</details>

<details>
<summary><b>Windows (PowerShell)</b></summary>

```powershell
.\install.ps1
```
</details>

*Alternatively, install via the universal Python script:*
```bash
python install.py
```

---

## How to Get, Save, and Test the API Key

Julius uses **NVIDIA Build NIM** by default for 550B parameter model reasoning.

### Step 1: Obtain your Free NVIDIA NIM API Key
1. Go to [NVIDIA Build NIM Portal](https://build.nvidia.com).
2. Sign in with your NVIDIA developer account (or create one for free).
3. Search for `nemotron-3-ultra-550b` or click **Get API Key**.
4. Generate and copy your personal API key (starts with `nvapi-`).

### Step 2: Configure Environment Variables
Copy the template configuration file:
```bash
# Linux / macOS
cp .env.example .env

# Windows (PowerShell)
Copy-Item .env.example .env
```

Open `.env` in any text editor and paste your API key:
```env
# Primary LLM API Key (NVIDIA NIM Free 550B)
NVIDIA_API_KEY=nvapi-YOUR_ACTUAL_KEY_HERE
```

### Step 3: Test and Launch
Verify your setup and test connectivity:
```bash
# Verify CLI help and provider registration:
python julius.py --help

# Launch interactive autonomous agent:
python julius.py
```

---

## Project Status & Long-Term Roadmap

> [!IMPORTANT]
> **Project Status: On Hold / Work in Progress (WIP)**  
> Julius is an active pre-release open-source project. While the core engine, provider routing, security boundaries, and test suites are robust and verified, several advanced systems are awaiting active implementation.

### Long-Term Architectural Milestones

- [ ] **Autonomous Multi-Agent Swarm Orchestration**: Distributed hierarchical task decomposition, consensus voting among specialized agents, and dynamic fault-tolerant replanning.
- [ ] **Sandboxed WebAssembly / MicroVM Runtime**: Zero-trust ephemeral sandbox execution for untrusted shell commands and dynamic scripts across Linux, macOS, and Windows.
- [ ] **Local SLM Multimodal Perception**: Low-latency on-device vision and duplex audio streaming using quantized small language models (Llama 3.2 Vision, Whisper, Kokoro TTS) without third-party cloud latency.
- [ ] **Decentralized Knowledge Mesh & AST Semantic Memory**: Peer-to-peer encrypted knowledge base synchronization, vector memory sharding, and real-time syntax-tree indexing.
- [ ] **Cross-Platform Tactile Interface Ecosystem**: Unified tactile design system across macOS, Linux, Windows, iOS companion PWA, and Rockchip P200 embedded Julius OS.
- [ ] **Extensible Open Plugin & MCP Marketplace**: Dynamic capability discovery, sandboxed tool plugins, and community agent skills via Model Context Protocol.

---

## Join the Community & Contribute!

Open source thrives when developers build together! Whether you are:
- A **TypeScript / React** engineer passionate about terminal UX and design systems
- A **Python Systems** developer interested in autonomous loops and sandboxing
- An **AI / ML** researcher building multi-agent swarms and local SLM inference
- A **Technical Writer** who wants to improve documentation, examples, and guides

We would love your contributions!

1. Read our [Contributing Guide](CONTRIBUTING.md) for code standards and testing protocols.
2. Check open discussions and pick up items from our roadmap.
3. Submit a Pull Request and let's build the future of autonomous engineering copilots together!

---

## License

This project is licensed under the [MIT License](LICENSE) — see the `LICENSE` file for details.
