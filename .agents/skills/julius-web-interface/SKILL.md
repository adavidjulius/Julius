---
name: julius-web-interface
description: Skill for reading Julius's core architecture, APIs, design systems, and device targets (desktop web, iOS mobile PWA, Android APK / Rockchip P200 Julius OS, connected apps) and implementing interconnected, tactile web interfaces in Julius_Web_Interface without mutating Julius core engine.
compatibility: "Julius Workspace, Antigravity IDE"
license: Proprietary
---

# Julius Web Interface Skill

This skill defines the contract and methodology for translating Julius's ecosystem (agent core, TUI, design tokens, apps, and hardware targets) into the `Julius_Web_Interface` project without altering or disrupting Julius's core code.

## 1. Core Operating Principle: Non-Invasive Interconnection

- **Read From Outside**: Inspect and pull inspiration, API contracts, design tokens, and assets from Julius root directories:
  - `Brand Book/` & `Julius_Fonts/`: Visual brand tokens, typography (Julius handwriting font, JetBrains Mono, Atkinson Hyperlegible, Bebas Neue).
  - `src/julius/tui_ts/src/theme/tokens.ts`: Exact system dark/light color palettes (`#121214` dark bg, `#1c1c1e` surface, `#c8b896` brand gold / antique parchment, `#006A25` forest green, `#731a1a` Roman crimson).
  - `julius_dashboard_api/`: REST & WebSocket contracts (`/api/chat`, `/api/resumption/tasks`, `/api/health`, citation mapping).
  - `julius-apps/`: Embedded application suites (`do-list-where`, `i-want-ui`, `julius-thinking-panel`).
  - `Julius OS/docs/ARCHITECTURE.md`: Rockchip RK3126 / P200 tablet profile, Android APK integration, ADB root specs.
  - `frontend/assets/widget-runtime.js`: Sandboxed iframe communication bridge (`window.JuliusWidgetHost`, `julius:sendPrompt`, `julius:widgetResize`).
- **Implement Inside Only**: All generated web code, UI views, assets, and device shells must be contained strictly inside `Julius_Web_Interface/`.
- **Zero Core Mutation**: Never edit `src/julius/` or break existing core agent behaviors when extending the web interface.

---

## 2. Multi-Device Interconnection Architecture

The web interface unites all Julius form-factors into a single responsive, feelable web application:

```
┌────────────────────────────────────────────────────────────────────────┐
│                      Julius Unified Web Interface                      │
│                                                                        │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────────┐  │
│  │   Desktop View   │  │   iOS Mobile     │  │  Android APK / P200  │  │
│  │  Multi-pane IDE  │  │ Dynamic Island   │  │ Rockchip RK3126 View │  │
│  │ TUI / Live Canvas│  │ Haptics & Notch  │  │ ADB / APK Downloader │  │
│  └────────┬─────────┘  └────────┬─────────┘  └──────────┬───────────┘  │
│           │                     │                       │              │
│           └─────────────────────┼───────────────────────┘              │
│                                 ▼                                      │
│                  Julius Unified State & Event Bus                      │
│                                 │                                      │
│         ┌───────────────────────┼───────────────────────┐              │
│         ▼                       ▼                       ▼              │
│  Connected Apps Hub       AI Agent Engine      Sandboxed Widget Frame  │
│  - do-list-where          - Live FastAPI       - widget-runtime.js     │
│  - i-want-ui              - LLM Stream Bridge  - postMessage bridge    │
│  - Terminal Shell (TUI)   - Resilient Fallback - Dynamic Auto-Resize   │
│  - Firmware / APK Hub                                                  │
└────────────────────────────────────────────────────────────────────────┘
```

### Supported Device Profiles:
1. **Desktop Studio Mode**:
   - Split layout with conversation timeline, thinking panel drawer, live widget canvas, and quick apps switchbar.
   - Comprehensive system telemetry (CPU/eMMC load, memory, active resumption tasks).
2. **Mobile iOS Mode**:
   - iPhone 16 Pro bezel with realistic Dynamic Island, iOS system status bar (Wi-Fi, 5G, 100% battery, live digital clock).
   - iOS home indicator gesture bar, frosted translucent tab bar (`backdrop-filter: blur(20px)`).
   - Audio-tactile feedback (simulated iOS tap haptics using Web Audio API synthesis).
3. **Android APK & Julius OS Tablet Mode**:
   - Rockchip RK3126 / P200 smart display hardware frame (1024x600 landscape default, 90° hardware rotation toggle).
   - Android navigation buttons (Back, Home, Recents), Root ADB status pill (`ro.secure=0`, `ro.debuggable=1`).
   - Built-in APK package installer simulator & direct Julius APK download bridge.
4. **Interconnected Split Matrix**:
   - Simultaneous side-by-side view synchronizing actions across Desktop, iOS, and Android APK in real-time.

---

## 3. Visual & Aesthetic Standards (Strict Julius Rules)

When developing or modifying `Julius_Web_Interface`:

1. **TypeScript First**:
   - All modules, state managers, and view controllers are written in **TypeScript (`.ts` / `.tsx`)**.
   - Strong type safety for messages, device modes, app descriptors, and widget payloads.
2. **Cursor Standard**:
   - The cursor must ALWAYS remain a **normal arrow pointer** (`pointer: default`) across general surfaces and buttons.
   - Never allow the cursor to get stuck in an `I`-beam / text-selection shape.
3. **ToolSummary Placement**:
   - `ToolSummary` (`› Ran X steps · Y.Ys`) MUST be rendered **ABOVE** the assistant's response message in chat bubbles.
4. **Thinking Panel Isolation**:
   - Thinking logs, reasoning chains, and introspection traces must remain strictly inside collapsible indicators.
   - Zero raw JSON, thinking tags (`<think>`), or unformatted markdown leakage into user-facing responses.
5. **Authentic Design Tokens**:
   - Background: `#121214` (System Dark) / `#1F1F1E` (Widget Canvas)
   - Surfaces: `#1c1c1e` (Card surface), `#2c2c2e` (Raised elements)
   - Brand Accent: `#c8b896` (Dusty antique parchment / Brand Gold)
   - Primary Accent: `#006A25` (Julius Forest Green) & `#006A25` glow
   - Roman Crimson: `#731a1a` (Brand Book Crimson)
   - Text: `#f5f5f7` (Primary high-contrast), `#86868b` (Secondary dim)
   - Typography: 'Julius' brand handwriting font, 'Atkinson Hyperlegible', 'JetBrains Mono', 'Bebas Neue', 'Playfair Display'.

---

## 4. API & Integration Contracts

The web interface implements a resilient Dual-Mode Connector:

1. **Live Backend Bridge**:
   - Searches for local FastAPI backend at `http://localhost:8000`.
   - Hits `/api/health` to verify SearXNG & LLM connectivity.
   - Posts user queries to `/api/chat` with `{ query: string }`.
   - Polls active resumption tasks from `/api/resumption/tasks`.
2. **Resilient Simulated Core**:
   - If the backend API is offline, the interface seamlessly falls back to a high-fidelity client-side Julius Agent Engine.
   - Emulates tool executions (`network_probe`, `rag_grounding`, `widget_generator`, `apk_packager`).
   - Streams responses token-by-token with realistic thinking pauses, tool summaries, and interactive sandboxed widgets.
   - Guarantees the website is **always 100% testable and feelable** immediately upon loading.

---

## 5. Verification & Testing Protocol

- All automated test scripts must be placed in `Julius_Test/` (e.g., `Julius_Test/test_julius_web_interface.py`).
- Never introduce dependencies in `src/` on `Julius_Test/` or `Julius_Web_Interface/`.
- Deleting `Julius_Test/` must not affect `Julius_Web_Interface/` or core Julius functionality.

