# Julius Widget Icon System Specification

Julius inline widgets use inline vector SVG icons matching the Julius dark green aesthetic.

## Standard SVG Icon Pattern

Always inline SVGs directly inside widget HTML. Ensure `stroke` or `fill` inherits or references `--lt-green` or `--lt-text-mid`.

### Green Glowing Indicator Icon
```html
<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--lt-green)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="filter: drop-shadow(0 0 4px var(--lt-green-glow));">
  <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
</svg>
```

### Chevron Toggle Icon
```html
<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--lt-text-dim)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <polyline points="6 9 12 15 18 9"></polyline>
</svg>
```
