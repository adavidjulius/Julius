# Julius Workspace Guidelines

## Language Hierarchy & Development Priority (STRICT)
- **Primary Language Priority (Highest - TypeScript)**:
  - Whenever an agent writes or develops code in this repository, **TypeScript (`.ts` / `.tsx`) is the HIGHEST PRIORITY language**.
  - All new user interface components, TUI widgets, frontend applications, tooling scripts, and interactive systems MUST be written in TypeScript first.
  - Continue the incremental migration of the terminal interface (`src/tui_ts/`) and UI systems into TypeScript while strictly preserving the visual contract and design system tokens.
- **Secondary Language Priority (Python)**:
  - **Python** is the secondary language, reserved exclusively for backend agent core loops, direct OS/subprocess system executors, and ML/LLM provider integrations where the Python runtime (`.venv/`) is already established.
  - When modifying existing Python code, maintain compatibility, but whenever introducing new sub-systems, UI layers, or standalone modules, default to TypeScript.

## Cursor & Visual Standards
- **Normal Cursor Enforcement**:
  - The cursor must ALWAYS remain a **normal arrow pointer** (`pointer: default`, escape sequence `\e]22;default\a`) and a **standard solid block text cursor** (`\e[2 q`).
  - Never allow the cursor to get stuck in an `I`-beam / text-selection shape (`pointer: text` is strictly forbidden across general window surfaces).
- **TUI & Display Standards**:
  - `ToolSummary` (`› Ran X steps · Y.Ys`) must always be rendered ABOVE the assistant's response message in conversation areas.
  - Thinking panel processes must stay strictly inside their designated collapsible indicators and never leak raw JSON, thinking tags, or markdown backticks into assistant messages.

## Core Development & Testing Rules
- **Testing Isolation**:
  - All test programs, experimental verification scripts, and test runners must reside in `Julius_Test/`.
  - The core application (`src/`, CLI, TUI, entrypoints) must never import from or depend on `Julius_Test/`.
  - Deleting `Julius_Test/` must never break the main program under any circumstances.
  - Production code logic, bug fixes, and features must be integrated directly into `src/` (main code).

## Model Architecture & Direct API Standard
- All LLM model inference runs via direct HTTP streaming APIs (NVIDIA Build NIM Free 550B default, Ollama HTTP, official Cloud APIs).
- Zero browser scraping or browser subprocesses are permitted for model fetching.
- Browser engines (Playwright) are reserved exclusively for agent web exploration tools (`src/browser/`) and WhatsApp messaging transport.
