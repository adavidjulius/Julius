# Contributing to Julius

Thank you for your interest in contributing to **Julius**! 🚀

Julius is an open-source, multi-modal autonomous agent platform combining an intelligent Terminal User Interface (TUI), web dashboard, direct streaming API integrations (NVIDIA Build 550B, Ollama, Claude, OpenAI), and specialized integrations.

Whether you are fixing a bug, adding new agent tools, enhancing the TypeScript TUI, or writing documentation, we welcome and celebrate your contributions!

---

## 🗺️ How to Get Involved

The project is currently a **Work in Progress (WIP)** with plenty of exciting areas where your help will make a huge impact:
- **Unfinished Roadmap Items**: Pick up items from the roadmap checklist in [README.md](README.md#project-status-work-in-progress--roadmap).
- **TypeScript TUI Expansion**: Implement new interactive widgets, status indicators, and screen layouts in `src/tui_ts/`.
- **LLM Provider Connectors**: Add or benchmark streaming providers in `src/providers/`.
- **Cross-Platform Target Testing**: Expand support across Linux, macOS, and Windows.
- **Documentation & Examples**: Write quick tutorials, cookbooks, and tool extension examples.

---

## 🛠️ Development Setup

### Prerequisites
- **Python**: 3.10, 3.11, or 3.12+ (tested with Python 3.10–3.14)
- **Node.js**: v18.0.0+ and `npm`
- **Git**

### Step-by-Step Setup
1. **Fork the repository** on GitHub: [github.com/adavidjulius/Julius](https://github.com/adavidjulius/Julius)
2. **Clone your fork**:
   ```bash
   git clone https://github.com/<your-username>/Julius.git
   cd Julius
   ```
3. **Set up a Python virtual environment**:
   ```bash
   # On macOS/Linux:
   python3 -m venv .venv
   source .venv/bin/activate

   # On Windows:
   python -m venv .venv
   .venv\Scripts\activate
   ```
4. **Install Python dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
5. **Install Node/TypeScript dependencies**:
   ```bash
   npm install
   ```
6. **Configure environment variables**:
   ```bash
   cp .env.example .env
   ```
   Add your free NVIDIA API key from [build.nvidia.com](https://build.nvidia.com/explore/discover) or configure your local Ollama instance.

---

## 📐 Language Hierarchy & Architecture Rules

When developing for Julius, please adhere to our strict repository standards:

### 1. Language Priority (Highest: TypeScript)
- **TypeScript (`.ts` / `.tsx`) is the HIGHEST PRIORITY language** for:
  - All new user interface components and visual screens
  - Terminal User Interface (`src/tui_ts/`) widgets and terminal layout engines
  - Web dashboards and interactive frontends
  - User-facing developer tooling scripts
- **Python** is reserved exclusively for:
  - Backend agent core loops and memory ledgers
  - Direct OS / subprocess system executors
  - Direct HTTP streaming LLM provider integrations (`src/providers/`)

### 2. Cursor & Visual Standards
- The cursor must **ALWAYS** remain a normal arrow pointer (`pointer: default`) and a standard solid block text cursor (`\e[2 q`).
- Never allow the cursor to get stuck in an `I`-beam / text-selection shape.
- `ToolSummary` (`› Ran X steps · Y.Ys`) must always render **above** the assistant's response message in conversation displays.
- Internal thinking processes must remain encapsulated inside collapsible indicators and never leak raw tags or JSON into user messages.

### 3. Model Architecture Standard
- All LLM model inference runs via direct HTTP streaming APIs (NVIDIA Build 550B, Ollama HTTP, official Cloud APIs).
- Browser automation is strictly prohibited for model inference (browser automation is reserved exclusively for agent web exploration tools and messaging transport).

---

## 🧪 Testing & Quality Gates

Before opening a Pull Request, verify that your changes pass all tests and linting gates:

```bash
# Run unit and integration tests
pytest tests/

# Test specific subsystems
pytest tests/whatsapp/
```

> [!NOTE]
> All automated tests and test fixtures reside in `tests/`. Production code must never import from test folders.

---

## 🌿 Git & Pull Request Workflow

1. **Create a topic branch**:
   ```bash
   git checkout -b feature/your-feature-name
   # or
   git checkout -b fix/issue-description
   ```
2. **Make your changes** following the language hierarchy and design tokens.
3. **Commit with clean, descriptive commit messages**:
   ```bash
   git commit -m "feat(tui): add streaming token indicator"
   # or
   git commit -m "fix(providers): handle connection timeout gracefully"
   ```
4. **Push to your fork**:
   ```bash
   git push origin feature/your-feature-name
   ```
5. **Open a Pull Request**:
   - Navigate to the original Julius repository on GitHub.
   - Click **New Pull Request** and select your branch.
   - Fill out the PR description with:
     - Clear explanation of the changes made
     - Screenshots or screen recordings for any visual/UI/TUI changes
     - Confirmation that `pytest tests/` passed locally.

---

## 💬 Community & Code of Conduct

We are committed to providing a friendly, safe, and welcoming environment for all contributors regardless of experience level, gender identity, race, or background. Please treat fellow maintainers and contributors with kindness and respect.

Thank you for helping build Julius! 🎉
