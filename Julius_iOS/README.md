# Julius iOS & iPadOS

> **Phase**: Prerequisites & Architecture Planning  
> **Status**: Ready for App Generation (Waiting for User Command)  
> **Strict Policy**: App code generation is paused until explicitly commanded.

This directory is dedicated to the native **Julius iOS & iPadOS** application. All prerequisites, system specifications, architectural blueprints, dependency manifests, diagnostic validators, and AI agent skills have been researched, gathered, and configured.

---

## 📁 Workspace Contents

| File / Directory | Description |
|---|---|
| [`PREREQUISITES.md`](PREREQUISITES.md) | Comprehensive checklist for macOS, Xcode, toolchains, accounts, and network reachability. |
| [`REQUIREMENTS.md`](REQUIREMENTS.md) | Functional, UI/UX, brand book tokens, and technical requirements specification. |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Tuist modular architecture blueprint (`App` → `Features` → `UI` → `Core`), data flow, and state design. |
| [`Brewfile`](Brewfile) | Declarative Homebrew dependencies (`tuist`, `fastlane`, `swiftformat`, `xcbeautify`, `node`). |
| [`check_prerequisites.sh`](check_prerequisites.sh) | Executable diagnostic script that verifies machine and environment readiness. |
| [`skills/`](skills) | Curated AI agent skills for iOS development (detailed below). |

---

## 🛠️ Integrated Skills

The following skills are placed in `skills/` (and `.agents/skills/`) to guide AI agents and developers during application development:

1. **`app-creator`** (`skills/app-creator/`):
   - Installed via `npx skillfish add antranapp/skills app-creator`.
   - Contains `create_app.py` scaffolding engine, Tuist project generators, CI scripts, and fastlane automation.
2. **`julius-design-system`** (`skills/julius-design-system/`):
   - Encodes Julius brand tokens (Obsidian `#121214`, Surface `#1C1C1E`, Antique Gold `#C8B896`, Roman Crimson `#731A1A`).
   - Custom typography rules (`Julius-Regular.ttf` & `Julius-Bold.ttf`).
   - Component contracts: `ToolSummary` (`› Ran X steps · Y.Ys`) strictly rendered **above** assistant responses.
   - Strict cursor pointer enforcement (default arrow pointer, block cursor, no stuck I-beams).
3. **`swiftui-architecture`** (`skills/swiftui-architecture/`):
   - Extracted from the authoritative **Axiom** toolkit (`CharlesWiltgen/Axiom`).
   - 65KB deep reference guide for SwiftUI architecture, navigation stacks, observation patterns, and state-as-bridge separation.
4. **`swift-concurrency`** (`skills/swift-concurrency/`):
   - Swift 6 strict concurrency, `@MainActor` UI isolation, actor boundary crossing, and data-race prevention.
5. **`swift-testing`** (`skills/swift-testing/`):
   - Protocol-driven unit testing, Swift Testing framework patterns, and visual regression snapshot testing.

---

## 🚀 Quick Verification

Run the automated environment check:
```bash
./check_prerequisites.sh
```

To install any missing developer tools:
```bash
brew bundle --file=Brewfile
```

---

## ⏳ Next Step: App Creation Phase

When ready to scaffold the app codebase, the user can trigger the creation phase with the desired App Name, Bundle Identifier, and Team ID.

