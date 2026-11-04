# Velvet Aurora Enhancements

This document details the architectural refinements and tactile user interface improvements implemented across the Julius Autonomous Agent engine.

---

## 1. Overview

The Velvet Aurora release establishes tactile interface responsiveness, normalizes agent tool execution payloads, and provides a streamlined terminal installer.

Key objectives achieved:
- Elimination of agent stalls during tool output parsing.
- Dynamic message container width scaling according to prompt content length.
- Standardized brand palette integration (#C8B896) for all borders and interactive states.
- Borderless, clean model selector triggered directly via `/model`.
- Multi-provider API verification wizard with live endpoint health checks.
- Clean terminal UX free of raw JSON leakages and unnecessary visual decorators.

---

## 2. Core Agent Engine: Tool Action Normalization

### 2.1 Problem Statement
When open-weight large language models (such as Nemotron, Llama, or DeepSeek) generate autonomous actions, their output format often varies. Certain models emit flat JSON tool payloads:
```json
{"tool": "read_file", "path": "README.md"}
```
or standard OpenAI function-call schemas:
```json
{"name": "read_file", "parameters": {"path": "README.md"}}
```
The internal action dispatcher previously expected a strict `{ "action": "...", "args": { ... } }` payload format. Unrecognized shapes led to unhandled parsing fallbacks, causing agent loops to halt and raw JSON text to leak into conversation bubbles.

### 2.2 Normalization Pipeline
The parser was updated in `src/web_agent.py` and `src/agent_prompts.py`:
1. **Key Hoisting**: Fields designated as `tool`, `function`, or `name` are automatically hoisted to `action`.
2. **Argument Normalization**: Fields under `parameters` or flat dictionary keys are consolidated into `args`.
3. **Protocol Filtering**: `is_json_or_protocol` detects raw serialized JSON blocks and prevents them from rendering as conversational assistant messages.

---

## 3. Tactile Terminal User Interface (TypeScript React Ink)

### 3.1 Dynamic User Message Width
Earlier iterations utilized a static width constraint of 24 columns for user message containers. This produced disproportionate cards for short inputs like "hello".

The updated `UserMessage.tsx` dynamically sizes the container:
```typescript
const lines = content.trim().split('\n');
const maxLineLen = Math.max(...lines.map((l) => l.length), 0);
const cardWidth = Math.min(maxCardWidth, Math.max(8, maxLineLen + 4));
```
Short messages dynamically adapt to their minimum bounding size while longer inputs wrap neatly within viewport bounds.

### 3.2 Borderless Direct Model Selector
The `/model` command displays an inline, borderless model navigation list:
- Arrow keys (`Up` / `Down` or `j` / `k`) and numeric keys (`1`-`9`) allow immediate selection.
- Active items are highlighted using Julius Brand Gold (`#C8B896`) with a clean `> ` indicator.
- Extraneous nested frames, subtitles, and descriptions are omitted to preserve visual clarity.

### 3.3 Slash Command Ergonomics
The input handler now recognizes two-character prefix matches and multi-word inputs:
- `/pl` and `/plan` resolve to the planning flow.
- `/mo` and `/model` activate the model switcher.
- `/cl` and `/clear` reset the viewport session.
- Arguments can be supplied directly (e.g., `/model gemini` or `/plan investigate build`).

---

## 4. Interactive Installer & Verification Wizard (`install.sh`)

### 4.1 Navigation and Prompt Styling
The installer features a clean ASCII header and interactive keyboard navigation:
- Brand styling using terminal 24-bit color sequences (`\033[38;2;200;184;150m`).
- Clear input prompts: `> Asking for <Provider> API key:`.
- Zero emoji characters; all status indicators use standard Unicode symbols (`[1/7]`, `->`, checkmarks).

### 4.2 Endpoint Health Probes
When an API key is supplied, `install.sh` executes an instantaneous endpoint probe via `curl`:
- **NVIDIA NIM**: `https://integrate.api.nvidia.com/v1/models`
- **Anthropic Claude**: `https://api.anthropic.com/v1/messages`
- **OpenAI ChatGPT**: `https://api.openai.com/v1/models`
- **DeepSeek**: `https://api.deepseek.com/models`
- **Google Gemini**: `https://generativelanguage.googleapis.com/v1beta/models`
- **xAI Grok**: `https://api.x.ai/v1/models`

Keys are only saved to `.env` once the endpoint validates the credentials, preventing downstream authentication failures.

---

## 5. Verification Checklist

1. **TypeScript Build**: Compiled with `tsc` without errors or warnings.
2. **Python Syntax**: All modified backend files validated via Python AST compiler.
3. **Installer Syntax**: Bash syntax check passed with `bash -n install.sh`.
4. **Git Tree Cleanliness**: All modifications consolidated under designated feature branch and merged into main.
