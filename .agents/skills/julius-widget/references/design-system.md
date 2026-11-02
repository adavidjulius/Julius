# Julius Widget Design System Specification

This document details the visual style, component rules, typography, and runtime CSS tokens for creating inline widgets in Julius.

## Visual Rules & Aesthetic

1. **Dark Theme Native**: All widgets render inside Julius's dark container (`--bg: #1F1F1E`).
2. **Seamless Integration**: Use rounded corners (`--lt-radius: 10px`), subtle border overlays (`--lt-border`), and translucent pill backdrops (`--lt-bg-pill`).
3. **Accent Highlights**: Accent elements, active states, and focus rings use Julius Green (`--lt-green: #006A25`) with glowing effects (`--lt-green-glow: rgba(0, 106, 37, 0.3)`).
4. **Typography Hierarchy**:
   - Headers: `--font-display` ('Bebas Neue', sans-serif)
   - Body & Controls: `--font-primary` ('Atkinson Hyperlegible', system-ui, sans-serif)
   - Code & Metrics: `--font-mono` ('JetBrains Mono', monospace)
   - Thinking & Narrative context: `--font-thinking` ('Playfair Display', serif)

## Component Specifications

### Cards & Panels
```css
.julius-widget-card {
  background: var(--lt-bg-pill);
  border: 1px solid var(--lt-border);
  border-radius: var(--lt-radius);
  padding: 16px;
  color: var(--lt-text-hi);
  font-family: var(--font-primary);
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}
.julius-widget-card:hover {
  border-color: var(--lt-border-act);
  box-shadow: 0 0 12px var(--lt-green-glow);
}
```

### Buttons & Interactive Inputs
```css
.julius-button {
  background: var(--lt-green-dim);
  border: 1px solid var(--lt-border-act);
  color: var(--lt-text-hi);
  border-radius: calc(var(--lt-radius) - 2px);
  padding: 8px 14px;
  font-family: var(--font-primary);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s ease;
}
.julius-button:hover {
  background: var(--lt-green);
  box-shadow: 0 0 8px var(--lt-green-glow);
}
```

### Communication Protocol
To send user intent back to the Julius host chat session:
```javascript
function selectOption(optionName) {
  if (typeof window.sendPrompt === 'function') {
    window.sendPrompt(`I'd like to explore the ${optionName} option.`);
  }
}
```
