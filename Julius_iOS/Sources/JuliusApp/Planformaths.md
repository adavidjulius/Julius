# Mathematical & LaTeX Rendering Implementation Plan

## 1. Overview & Architecture
Modern AI chat interfaces render mathematical formulas using a **three-stage pipeline**:
1. **Prompt-Level Delimiter Standardization:** Instructing the LLM to wrap all inline math in `$...$` and block equations in `$$...$$`, prohibiting raw unwrapped LaTeX macros or hybrid Unicode-LaTeX strings.
2. **Pre-Processing & Streaming Normalization:** Sanitizing alternative delimiters (`\[...\]`, `\(...\)`), wrapping bare macros (like `\boxed{...}`), and auto-closing unclosed `$$` delimiters while tokens are actively streaming.
3. **AST Tokenization & Client-Side Typesetting:** Using a math-aware Markdown AST plugin (`remark-math`) to shield math expressions from standard Markdown emphasis parsing (e.g., preventing `_1` from turning into italics), paired with **KaTeX** (`rehype-katex`) or native iOS math rendering (`LaTeXSwiftUI`).

---

## 2. Root Cause Diagnosis
When formulas render as broken plain text (such as `\boxed{P_1 + 1/2ρ v_1^2...}` or `√{2gh}`), two pipeline issues are occurring:
1. **Unwrapped & Hybrid LaTeX Output:** Either the model is emitting raw LaTeX commands (`\boxed`, `\uparrow`, `_1`, `^2`) mixed with Unicode characters (`ρ`, `√`) without `$...$` delimiters, or a backend/frontend regex sanitizer is stripping `$` signs and converting select macros (`\rho` -> `ρ`, `\sqrt` -> `√`) while leaving braces `{}` and subscripts untouched.
2. **Missing Math Typesetter in the Markdown Parser:** Standard Markdown parsers handle tables, bold text, and lists, but treat LaTeX syntax as literal text unless paired with a dedicated math parser and CSS stylesheet.

---

## 3. Target Output Examples

| Context | Raw Broken String | Proper LaTeX Input |
| :--- | :--- | :--- |
| **Display Equation** | `\boxed{P_1 + 1/2ρ v_1^2 + ρ g h_1 = P_2 + 1/2ρ v_2^2 + ρ g h_2}` | `$$\boxed{P_1 + \frac{1}{2}\rho v_1^2 + \rho g h_1 = P_2 + \frac{1}{2}\rho v_2^2 + \rho g h_2}$$` |
| **Table / Inline Math** | `1 / 2ρ v^2` | `$\frac{1}{2}\rho v^2$` |
| **Symbolic Arrows** | `Constriction → v \uparrow → P \downarrow` | `Constriction $\rightarrow v \uparrow \rightarrow P \downarrow$` |
| **Square Roots** | `v = √{2gh}` | `$v = \sqrt{2gh}$` |

---

## 4. Step-by-Step Implementation Plan

### Phase 1: Standardize LLM Output via System Prompt
Remove any custom regex scripts that convert LaTeX commands into Unicode symbols (`ρ`, `√`), and append the following rules to your system prompt:

```markdown
### Mathematical & Scientific Formatting
- Always use standard LaTeX for mathematical expressions, variables, subscripts, superscripts, and formulas.
- Wrap inline math in single dollar signs: `$...$` (e.g., `$P_1$`, `$\frac{1}{2}\rho v^2$`, `$v = \sqrt{2gh}$`).
- Wrap standalone block equations in double dollar signs on their own lines:
  $$
  \boxed{P_1 + \frac{1}{2}\rho v_1^2 + \rho g h_1 = P_2 + \frac{1}{2}\rho v_2^2 + \rho g h_2}
  $$
- Never output raw LaTeX macros (such as `\boxed`, `\frac`, `\uparrow`, `_1`, or `^2`) outside of `$...$` or `$$...$$` delimiters.
- Never mix Unicode math symbols (like `√` or `ρ`) with raw LaTeX braces or subscripts (like `√{2gh}`). Always use pure LaTeX (`\sqrt{2gh}`, `\rho`) inside `$` delimiters.
```

---

### Phase 2: Build the Pre-Processor & Streaming Guard
LLMs occasionally emit `\[ ... \]` or `\( ... \)` instead of `$$ ... $$` and `$ ... $`, or output a bare `\boxed{...}` without delimiters. In addition, an unclosed `$$` during token streaming can cause raw syntax to flash on screen.

Create `normalizeMathMarkdown.ts` and run it on every message string before passing it to your Markdown component:

```typescript
// normalizeMathMarkdown.ts

export function normalizeMathMarkdown(text: string): string {
  if (!text) return "";

  let processed = text;

  // 1. Convert \[ ... \] to $$ ... $$
  processed = processed.replace(/\\\[([\s\S]*?)\\\]/g, (_, math) => `$$${math}$$`);

  // 2. Convert \( ... \) to $ ... $
  processed = processed.replace(/\\\(([\s\S]*?)\\\)/g, (_, math) => `$${math}$`);

  // 3. Catch bare \boxed{...} that are not already wrapped in $ or $$
  processed = processed.replace(
    /(?<!\$)\\boxed\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}(?!\$)/g,
    "$$\\boxed{$1}$$"
  );

  // 4. Streaming Guard: Auto-close unclosed block math ($$) during token streaming
  const blockCount = (processed.match(/\$\$/g) || []).length;
  if (blockCount % 2 !== 0) {
    processed += "\n$$";
  }

  return processed;
}
```

---

### Phase 3: Integrate the Frontend Math Engine

Choose **Option A** for Web / React / Hybrid WebView frontends, or **Option B** for native iOS SwiftUI views.

#### Option A: React / Next.js / WebView Frontend (Recommended)
KaTeX is fast, synchronous, and prevents layout shift during token streaming.

**1. Install Dependencies:**
```bash
npm install react-markdown remark-gfm remark-math rehype-katex katex
```

**2. Create the Message Renderer (`ChatMessage.tsx`):**
```tsx
import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css'; // Required: prevents duplicate/unstyled MathML output
import { normalizeMathMarkdown } from './normalizeMathMarkdown';

interface ChatMessageProps {
  content: string;
}

export function ChatMessage({ content }: ChatMessageProps) {
  const safeContent = normalizeMathMarkdown(content);

  return (
    <div className="prose prose-invert max-w-none">
      <ReactMarkdown false false, rehypePlugins="{[[rehypeKatex," remarkMath]} remarkPlugins="{[remarkGfm," strict: throwOnError: { }]]}>
        {safeContent}
      </ReactMarkdown>
    </div>
  );
}
```

#### Option B: Native iOS (SwiftUI) Frontend
Apple's native `AttributedString(markdown:)` ignores LaTeX. Use `LaTeXSwiftUI` (built on `SwiftMath` and `MarkdownUI`) or a lightweight local `WKWebView` running `marked` + `KaTeX`.

**1. Swift Normalization Helper (`MathNormalizer.swift`):**
```swift
import Foundation

func normalizeMathMarkdown(_ text: String) -> String {
    guard !text.isEmpty else { return "" }
    var processed = text

    // Convert \[ ... \] to $$ ... $$
    processed = processed.replacingOccurrences(
        of: #"\\\[([\s\S]*?)\\\]"#,
        with: "$$$$$1$$$$",
        options: .regularExpression
    )

    // Convert \( ... \) to $ ... $
    processed = processed.replacingOccurrences(
        of: #"\\\(([\s\S]*?)\\\)"#,
        with: "$$$1$$",
        options: .regularExpression
    )

    // Auto-close unclosed $$ during streaming
    let blockMatches = processed.components(separatedBy: "$$").count - 1
    if blockMatches % 2 != 0 {
        processed += "\n$$"
    }

    return processed
}
```

**2. SwiftUI View (`MessageRowView.swift`):**
```swift
import SwiftUI
import LaTeXSwiftUI

struct MessageRowView: View {
    let rawMessage: String

    var body: some View {
        LaTeX(normalizeMathMarkdown(rawMessage))
            .parsingMode(.onlyEquations) // Parses $...$ and $$...$$ while preserving prose
            .errorMode(.original)        // Prevents flicker on incomplete mid-stream tokens
            .blockMode(.blockViews)
    }
}
```
> **Note for iOS Tables + `\boxed{}`:** If your responses frequently combine Markdown tables with inline LaTeX and `\boxed{...}` macros, rendering messages inside a local `WKWebView` bundle with `KaTeX` provides 100% macro and GFM table parity.

---

### Phase 4: Mobile CSS & Horizontal Overflow Polish
Long equations (such as Bernoulli's equation) exceed narrow mobile viewports. Add these styles to your global CSS (`globals.css` or `math-styles.css`) so block equations scroll horizontally without breaking your page layout:

```css
/* Horizontal scroll for wide block equations on mobile viewports */
.katex-display {
  overflow-x: auto;
  overflow-y: hidden;
  padding: 0.75rem 0;
  margin: 0.5rem 0;
  -webkit-overflow-scrolling: touch;
}

/* Keep inline equations from wrapping mid-expression */
.katex {
  font-size: 1.05em;
  white-space: nowrap;
}

/* Allow inline math inside tables to wrap cleanly if needed */
td .katex,
th .katex {
  white-space: normal;
}

/* Style \boxed{} borders for dark mode UI */
.katex .boxpad {
  border-color: rgba(255, 255, 255, 0.35);
  padding: 0.4em;
}
```

---

## 5. Verification & QA Checklist
- [ ] **Inspect Raw Backend Payload:** Check the raw API stream in your network inspector before it hits the frontend. If `\rho` is already converted to `ρ` or `\sqrt` is converted to `√`, disable the backend text-sanitization regex causing the partial conversion.
- [ ] **Verify Stylesheet Import:** Confirm `katex/dist/katex.min.css` is loaded. Missing CSS causes equations to render twice (once as unstyled MathML and once as raw HTML spans).
- [ ] **Subscript Collision Test:** Render `$P_1 + \frac{1}{2}\rho v_1^2 = P_2 + \frac{1}{2}\rho v_2^2$` and verify that `_1` and `_2` render as subscripts rather than italicizing the text between them.
- [ ] **Table Math Test:** Render a Markdown table containing `$\frac{1}{2}\rho v^2$` and `$\rho g h$` in cells and confirm both the table grid and formulas render intact.
- [ ] **Mobile Viewport Overflow Test:** Test a wide `\boxed{...}` equation on a 375px mobile screen to confirm smooth horizontal scrolling within the message container.