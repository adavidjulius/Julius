/**
 * Julius Design Tokens & Brand System
 * Exactly synchronized with src/julius/tui_ts/src/theme/tokens.ts
 * and .agents/skills/julius-widget/references/design-system.md
 */

export const JULIUS_THEME = {
  // Dark Backgrounds
  bg: '#121214',              // Julius System Dark Base
  bgElevated: '#1c1c1e',      // Surface +4% shift
  bgRaised: '#2c2c2e',        // Raised card surface +8% shift
  bgCanvas: '#1F1F1E',        // Widget / Visual canvas container
  bgPill: 'rgba(255, 255, 255, 0.04)',

  // Brand Palette
  brandGold: '#c8b896',       // Dusty 100-year-old antique parchment (#C8B896)
  brandCrimson: '#731a1a',    // Roman Crimson (#731A1A)
  brandObsidian: '#1a1a1a',   // Obsidian Base (#1A1A1A)

  // Julius Primary Green System
  green: '#006A25',           // Julius Forest Green
  greenDim: 'rgba(0, 106, 37, 0.15)',
  greenGlow: 'rgba(0, 106, 37, 0.35)',
  greenLight: '#30d158',      // System Status Green

  // UI Accents
  warning: '#ffd60a',         // System Yellow
  error: '#ff453a',           // System Red
  blue: '#0a84ff',            // System Blue

  // Borders
  borderIdle: 'rgba(255, 255, 255, 0.09)',
  borderFocused: '#c8b896',   // Focused antique gold
  borderActive: 'rgba(0, 106, 37, 0.40)',

  // Text Hierarchy
  textHigh: '#f5f5f7',        // High emphasis (15.6:1 contrast)
  textMid: 'rgba(255, 255, 255, 0.65)',
  textDim: '#86868b',         // Secondary dim
  textFaint: '#48484a',       // Tertiary subtle

  // Typography
  fontBrand: "'Julius', system-ui, sans-serif",
  fontPrimary: "'Atkinson Hyperlegible', system-ui, -apple-system, sans-serif",
  fontDisplay: "'Bebas Neue', sans-serif",
  fontThinking: "'Playfair Display', Georgia, serif",
  fontMono: "'JetBrains Mono', 'Fira Code', monospace",

  // Radii
  radius: '10px',
  radiusLarge: '16px',
  radiusPill: '9999px',
};

