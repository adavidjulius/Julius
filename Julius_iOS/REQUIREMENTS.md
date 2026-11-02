# Julius iOS — Product & Technical Requirements Specification

## 1. Product Vision & Scope

**Julius iOS** is the native iOS & iPadOS client for Julius — the autonomous reasoning, academic study companion, coding agent, and workflow execution platform. Julius iOS translates Julius's terminal UI, dual-engine reasoning (Playwright WebLLM + Study Brain fallback), and multimodal capabilities into a high-performance Apple platform experience.

The app is architected with modern **SwiftUI**, **Tuist modular architecture**, and **Swift 6 strict concurrency**, supporting iPhones and iPads running **iOS / iPadOS 17.0+**.

---

## 2. Functional Requirements

### FR-1: Dual-Protocol Backend Communication
- **FR-1.1**: The client must establish a persistent **WebSocket connection** (`ws://<host>:9111/ws`) for bidirectional real-time message streaming, thinking progress updates, and execution steps.
- **FR-1.2**: In the event of network disruption or WebSocket disconnection, the client must automatically fall back to **HTTP REST API** (`POST http://<host>:9111/api/chat`).
- **FR-1.3**: Zero-config auto-reconnect with exponential backoff (`1s`, `2s`, `4s`, max `10s`).
- **FR-1.4**: Connection status indicator (Connected: System Green `#30D158`, Reconnecting: Yellow `#FFD60A`, Offline: Dim `#86868B`).

### FR-2: Real-Time Streaming & Animated Tokens
- **FR-2.1**: Incoming message chunks must be appended smoothly to the active view without causing full-list redraws.
- **FR-2.2**: Active streaming must render an animated typing/cursor indicator.
- **FR-2.3**: Full Markdown support: syntax-highlighted code blocks, tables, bold/italic, LaTeX equations (via KaTeX / MathJax or native Swift parser), and file/link previews.

### FR-3: Thinking Panel (Reasoning & Trace Visualization)
- **FR-3.1**: Model reasoning thoughts (`<think> ... </think>`) must be extracted and encapsulated in a dedicated collapsible **Thinking Panel**.
- **FR-3.2 (STRICT RULE)**: Raw thinking tags, unfinished JSON objects, or internal agent backticks MUST NEVER leak into the user-facing message body.
- **FR-3.3**: The thinking panel must feature:
  - Collapsible accordion with smooth disclosure chevron.
  - Active execution state (pulsing timer or step spinner).
  - Elapsed reasoning duration badge (e.g., `Thought for 3.4s`).
  - Monospaced / faint styling for intermediate reasoning steps.

### FR-4: Tool Execution Summary (Visual Contract)
- **FR-4.1 (STRICT RULE)**: The `ToolSummary` component (`› Ran X steps · Y.Ys`) MUST ALWAYS be positioned and rendered **ABOVE** the assistant's response message in conversation threads.
- **FR-4.2**: Tapping the ToolSummary expands a detail sheet or inline drawer displaying executed steps (e.g., live search, code compilation, file reads).

### FR-5: Multi-Session Management & Persistence
- **FR-5.1**: Users can create, switch between, rename, and delete conversation sessions.
- **FR-5.2**: Local session persistence using **SwiftData** (or Core Data) with offline access to previous conversations.
- **FR-5.3**: Session metadata: title, last message preview, timestamp, token count, and active model.

### FR-6: Multimodal Perception & Input
- **FR-6.1**: Camera capture & Photos Picker integration for uploading study diagrams, homework problems, math formulas, and code screenshots.
- **FR-6.2**: On-device thumbnail generation and base64 / multipart encoding for transmission to Julius's Vision Perception Layer (`analyze_study_image`).
- **FR-6.3**: Document Picker support for PDF and text file attachments.

### FR-7: Voice & Audio Interaction
- **FR-7.1**: Speech-to-text dictation using Apple `Speech` framework (`SFSpeechRecognizer`).
- **FR-7.2**: Text-to-speech voice response using Apple `AVSpeechSynthesizer` or custom Julius voice models.
- **FR-7.3**: Dedicated hands-free "Study Voice Mode" full-screen overlay with animated audio waveform visualizer.

### FR-8: Settings & Server Configuration
- **FR-8.1**: Host address & port configuration (`http://localhost:9111`, custom IP, or Bonjour name).
- **FR-8.2**: Model / Provider selection: DeepSeek, ChatGPT, Gemini, Claude, or local model.
- **FR-8.3**: Theme override (Dark, Light, System).
- **FR-8.4**: Cache clearing and diagnostic network health tester.

---

## 3. UI/UX & Brand Design System Requirements

### BR-1: Julius Brand Color Palette & Master Mark (Authoritative Brand Book)
| Token | Dark Mode Hex | Light Mode Hex | Purpose |
|---|---|---|---|
| **Primary Brand Energy** | `#7ED321` | `#5BA615` | **Julius Electric Green** (Oscilloscope phosphor, action focus) |
| **Deep Green Accent** | `#006A25` | `#006A25` | High-voltage deep accent |
| **Dark Slate Badge** | `#0F172A` | `#0F172A` | Master OS & App Icon squircle canvas |
| **Canvas Background** | `#121214` | `#F5F5F7` | Base obsidian canvas |
| **Card Surface** | `#1C1C1E` | `#E5E5EA` | Assistant cards, list cells (+4% lightness) |
| **Raised Surface** | `#2C2C2E` | `#D1D1D6` | Popovers, modal sheets (+8% lightness) |
| **Primary Text** | `#F5F5F7` | `#1D1D1F` | High-contrast readable body (15.6:1) |
| **Secondary Text** | `#86868B` | `#6E6E73` | Timestamps, metadata (4.9:1) |
| **Tertiary Text** | `#48484A` | `#AEAEB2` | Placeholders, subtle hints |
| **Brand Gold / Parchment**| `#C8B896` | `#C8B896` | Antique Roman parchment, accents, focus |
| **Roman Crimson** | `#731A1A` | `#731A1A` | Imperial watermark crimson |
| **User Message Bubble** | `#2C2C2E` | `#E5E5EA` | User message bubble |
| **Success** | `#7ED321` | `#34C759` | Status online, verified step |
| **Warning** | `#FFD60A` | `#C8B896` | Alert states |
| **Error** | `#FF453A` | `#FF3B30` | Execution failures |
| **Border Idle** | `#3E3E42` | `#C7C7CC` | Card and bubble outlines |
| **Border Focused** | `#7ED321` | `#7ED321` | Active focus indicator |

### BR-2: Master Mark Geometry & Continuous Curvature (G2)
- **Vector Blueprint**: 512 × 512 pt (viewBox `0 0 512 512`), dorsal apex `(400.67, 96.49)`, ground anchor `(234.12, 458.30)`.
- **Badge Squircle**: `rx=115pt` on 512pt box (22.5% continuous curvature).
- **G2 Squircles**: Continuous mathematical curvature acceleration without tangent breaks (`--radius-sm: 6px`, `--radius-md: 8px`, `--radius-lg: 10px`, `--radius-xl: 16px`, `--radius-pill: 9999px`).
- **Harmonic Sine Breathing Physics**: 1400ms cycle (sine opacity `0.35` -> `1.0`).
- **Canonical Rhetorical Phrasing**:
  - Greeting: *"Ready. What are we building?"*
  - Organization Signature: *LUMENAGENT*
  - Completion: *"Done. X files compiled, Y tests passed."*

### BR-2: Typography
- Custom font family `Julius` (`Julius-Regular.ttf` & `Julius-Bold.ttf`) bundled in `Resources/Fonts/`.
- Dynamic Type support enabled across all text views (`@ScaledMetric`).
- Code blocks rendered with `Font.system(.subheadline, design: .monospaced)`.

### BR-3: Cursor & Pointer Contract (STRICT)
- **Normal Pointer Rule**: On iPadOS (with trackpad/mouse) and macOS Catalyst:
  - The pointer must ALWAYS remain a **standard arrow pointer** (`pointer: default`).
  - Text selection cursor must only appear over selectable text, and never remain stuck in an `I`-beam across general window surfaces or list backgrounds.
  - Text input areas use a standard solid block or vertical bar cursor.

---

## 4. Technical & Architectural Requirements

### TR-1: Modular Architecture (Tuist)
Following the `app-creator` modular template:
1. **`App` (Thin Shell)**: Dependency injection setup, App entry point (`@main`), navigation router.
2. **`Features`**: Self-contained UI feature modules (`ChatFeature`, `ThinkingFeature`, `VoiceFeature`, `SettingsFeature`).
3. **`UI`**: Reusable components (`Theme`, `DesignTokens`, `MessageBubbleView`, `ThinkingPanelView`, `ToolSummaryView`, `MarkdownView`).
4. **`Core`**: Business logic (`NetworkClient`, `WebSocketManager`, `StreamParser`, `SessionStore`, `Models`, `AudioEngine`).

### TR-2: Swift 6 Concurrency
- Whole-module complete concurrency checking enabled (`SWIFT_STRICT_CONCURRENCY = complete`).
- All UI state models isolated to `@MainActor`.
- Data transfer objects declared with `Sendable` conformance.
- Zero data-race warnings or crashes.

### TR-3: Testing Coverage
- **Unit Tests (`CoreTests`)**: Protocol mock testing for network requests, parser logic, and model validation.
- **UI Tests (`FeaturesTests`)**: State-driven SwiftUI ViewModels verified with state transitions.
- **Snapshot Tests (`SnapshotTests`)**: Visual regression testing using `swift-snapshot-testing` for both Dark and Light themes across iPhone and iPad screen sizes.

---

## 5. Non-Functional Requirements

| Metric | Target | Verification Method |
|---|---|---|
| **Frame Rate** | 60 fps (120 fps ProMotion) | Instruments Core Animation Trace |
| **Memory Usage** | < 80 MB baseline, < 150 MB peak | Xcode Memory Gauge |
| **Cold Launch Time** | < 1.2s to interactive chat | MetricKit / Instruments |
| **App Bundle Size** | < 25 MB compressed download | Tuist build artifact inspection |
| **Crash Rate** | 0.00% across test suites | XCTest suite execution |
| **Network Resilience** | Graceful recovery from airplane mode | Network link conditioner testing |

