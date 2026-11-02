---
name: julius-design-system
description: Design tokens, typography, visual contracts, and cursor standards for Julius on Apple platforms (iOS, iPadOS, macOS). Use whenever implementing UI views, components, message bubbles, tool indicators, or color schemes for Julius.
---

# Julius iOS Design System & Visual Contract

This skill defines the visual hierarchy, color palette, typography, component contracts, and interaction standards for Julius iOS and iPadOS applications.

## 1. Color Palette & Design Tokens

### Dark Theme (Default)
Matches the authoritative system dark tokens from `src/tui_ts/src/theme/tokens.ts` and `src/tui/theme.py`:

| Token | Hex / Value | Description |
|---|---|---|
| `bg` | `#121214` | Julius System Dark Canvas |
| `surface` | `#1C1C1E` | Card surface (+4% lightness shift) |
| `raised` | `#2C2C2E` | Elevated elements, modals (+8% lightness) |
| `text` | `#F5F5F7` | Primary text (15.6:1 contrast ratio) |
| `text_dim` | `#86868B` | Secondary text (4.9:1 contrast ratio) |
| `text_faint` | `#48484A` | Tertiary text, subtle hints, placeholders |
| `accent` | `#C8B896` | Dusty antique Roman parchment / Roman Gold |
| `brand_crimson` | `#731A1A` | Julius Brand Book Roman Crimson |
| `brand_obsidian` | `#1A1A1A` | Julius Brand Book Body Obsidian |
| `brand_gold` | `#C8B896` | Accent borders, badges, highlighted controls |
| `success` | `#30D158` | System Green (online status, successful steps) |
| `warning` | `#FFD60A` | System Yellow (alerts, pending states) |
| `error` | `#FF453A` | System Red (failed executions, tool errors) |
| `border_idle` | `#3E3E42` | Crisp subtle border for containers |
| `border_focused` | `#C8B896` | Focused antique paper border |
| `scrim` | `rgba(0,0,0,0.65)` | Modal / overlay backdrop scrim |

### Light Theme
| Token | Hex / Value | Description |
|---|---|---|
| `bg` | `#F5F5F7` | Julius System Light Canvas |
| `surface` | `#E5E5EA` | Inset surface |
| `raised` | `#D1D1D6` | Raised card surface |
| `text` | `#1D1D1F` | Primary dark text (14.8:1 contrast) |
| `text_dim` | `#6E6E73` | Secondary text (4.8:1 contrast) |
| `text_faint` | `#AEAEB2` | Tertiary text |
| `accent` | `#007AFF` | Julius System Blue (light) |
| `border_idle` | `#C7C7CC` | Defined idle light border |
| `border_focused` | `#007AFF` | Focused light border |

---

## 2. Typography

1. **Brand Font**: `Julius` (`Julius-Regular.ttf`, `Julius-Bold.ttf`) located at `/Julius_Fonts/`.
2. **System Font Fallbacks**:
   - Headers: `Font.custom("Julius-Bold", size: ...)` or `.system(.headline, design: .serif)`
   - Body & Code: `Font.custom("Julius-Regular", size: ...)` with `.monospaced()` for code blocks.
3. **Dynamic Type Support**: Always use relative text sizing (`@ScaledMetric`) so fonts respect user accessibility sizes.

---

## 3. UI Component Contracts

### Tool Summary Component
- **Rule**: `ToolSummary` (`› Ran X steps · Y.Ys`) MUST ALWAYS BE RENDERED ABOVE the assistant's response message in chat areas.
- **Layout**:
  ```
  ┌────────────────────────────────────────────────────────┐
  │ › Ran 3 steps · 1.2s                        [Details] │  <- ToolSummary
  ├────────────────────────────────────────────────────────┤
  │ Assistant message text begins here...                  │
  │                                                        │
  └────────────────────────────────────────────────────────┘
  ```

### Thinking Panel Process
- Must stay strictly inside designated collapsible disclosure views (`DisclosureGroup` in SwiftUI).
- Never leak raw `<think>`, `</think>`, JSON blobs, or markdown backticks into the user-facing message.
- Provide a smooth animated chevron indicator and subtle elapsed timer.

### Message Bubbles
- **User Bubble**: Right-aligned, pastel tint / accent wash, rounded corners with trailing anchor.
- **Assistant Bubble**: Left-aligned, Obsidian surface card (`#1C1C1E`), crisp border (`#3E3E42`), leading anchor.

---

## 4. Cursor & Pointer Contract (STRICT)

- **Normal Cursor Enforcement**:
  - The pointer MUST ALWAYS remain a standard arrow pointer (`pointer: default` / `.hoverEffect(.highlight)`) and standard solid block or bar text cursor inside text editors.
  - Never allow pointer or cursor to get stuck in an `I`-beam / text-selection shape across general window or scrollable list surfaces.

