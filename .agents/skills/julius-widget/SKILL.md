---
name: julius-widget
description: Julius widget design system. Read this BEFORE rendering any inline widget in Julius. Defines when to use a widget and the runtime contract; the full visual style lives in references/design-system.md. Your widget runs in a sandboxed iframe with the Julius design system pre-loaded — reference the provided CSS variables, never hardcode colors or fonts.
compatibility: "Julius Workspace, Antigravity IDE"
license: Proprietary
---

# Julius Widget

A widget is a compact visual or interactive surface rendered inline in the conversation:
diagrams, dashboards, calculators, sliders, comparisons, timelines, state machines, small
simulations. Use one when seeing structure helps the user understand, compare, inspect, or act
on the answer better than prose alone.

## When to generate a widget

- The answer has spatial, sequential, systemic, comparative, numeric, or interactive structure.
- The user does not need to say "show", "visualize", "chart", or "widget" — proactive widgets are
  expected when the structure is there.
- If the user gives a compact visual spec without a verb ("REST vs GraphQL table", "checkout state
  machine", "pricing calculator"), render it as a widget instead of only describing it.

Do **not** use a widget for: ordinary prose answers, routine line-by-line code explanations, file
lists / galleries / final deliverables, blocking input workflows, destructive or native actions,
or large long-lived apps.

## Runtime contract

The widget runs in a **sandboxed iframe with the Julius design system CSS already loaded**. All CSS
variables, form-element styles, and SVG classes are available at runtime — reference them, do not
redefine them.

- Allowed: HTML, SVG, CSS, inline JavaScript, native browser APIs.
- **Not allowed**: external scripts, modules, stylesheets, images, fonts, CDN libraries, npm
  packages, `fetch`, or WebSocket. For charts/diagrams use SVG, Canvas, CSS, or plain DOM.
- **Text goes in your response, visuals go in the widget.** All explanatory prose, intros, and
  summaries live OUTSIDE the widget.
- **After the widget renders, don't narrate it.** Once you've called the widget tool and the widget
  is done, do not re-summarize or repeat what you just did — the visual speaks for itself. Say only
  what the widget cannot.
- **Sending intent back.** An interactive widget may call `window.sendPrompt(text)` (when the host
  injects it) to push the user's next intent into the conversation. Write `text` as a real user
  message — what the user would actually type — never a robotic confirmation like "I selected
  option A, please proceed."
- Never hardcode colors, fonts, or border-radius — always use `var(--xxx)`. Hardcoded values break
  dark mode and look inconsistent with the host UI.

## Julius CSS Design Tokens

When styling widgets for Julius, use the pre-loaded CSS variables:

| Variable | Description | Default Value |
| --- | --- | --- |
| `--font-primary` | Primary UI sans-serif font | `'Atkinson Hyperlegible', system-ui, sans-serif` |
| `--font-display` | Display / Heading font | `'Bebas Neue', sans-serif` |
| `--font-thinking` | Serif / Thinking font | `'Playfair Display', Georgia, serif` |
| `--font-mono` | Monospace font | `'JetBrains Mono', 'Fira Code', monospace` |
| `--lt-green` | Julius Primary Accent Green | `#006A25` |
| `--lt-green-dim` | Translucent Accent Background | `rgba(0, 106, 37, 0.15)` |
| `--lt-green-glow` | Translucent Accent Glow | `rgba(0, 106, 37, 0.30)` |
| `--lt-bg-pill` | Subsurface Card / Pill BG | `rgba(255, 255, 255, 0.04)` |
| `--lt-border` | Standard Subdued Border | `rgba(255, 255, 255, 0.09)` |
| `--lt-border-act` | Active / Focused Border | `rgba(0, 106, 37, 0.35)` |
| `--lt-text-dim` | Low Emphasis Text | `rgba(255, 255, 255, 0.40)` |
| `--lt-text-mid` | Medium Emphasis Text | `rgba(255, 255, 255, 0.65)` |
| `--lt-text-hi` | High Emphasis Text | `rgba(255, 255, 255, 0.92)` |
| `--lt-radius` | Standard Corner Radius | `10px` |
| `--bg` | Main Background Surface | `#1F1F1E` |

## Required: read the design system before you design

**Unless the user has given you very explicit, precise styling instructions for this specific
widget, you MUST read [references/design-system.md](references/design-system.md) before writing the
widget code.** It carries the full Julius Perspective Widget style — visual rules, typography,
component patterns, runtime token map, and the application checklist. Do not decide a widget is too
simple, too static, or too small to need it. Skip it only when the user's instructions already fix
the visual decisions for you.

If the widget uses icons, also read [references/icon-system.md](references/icon-system.md): the
skill ships Kimi and Julius UI icons (`assets/icons/`, indexed in `references/icons/manifest.json`) — pick
from the library and inline the SVG instead of drawing your own or using emoji.
