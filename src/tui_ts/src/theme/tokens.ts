import chalk from 'chalk';
import type { ThemeTokens, SquircleRadii } from '../types.js';

// Ensure ANSI 256 color mode for universal terminal compatibility (Apple Terminal.app & iTerm2)
if (typeof process !== 'undefined' && process.env) {
  process.env.FORCE_COLOR = '2';
  delete process.env.COLORTERM;
}
chalk.level = 2;

export const SQUIRCLE_RADII: SquircleRadii = {
  xs: '4px',
  sm: '6px',
  md: '8px',
  lg: '10px',
  xl: '16px',
  pill: '9999px',
};

/**
 * Julius Dark Theme (default)
 * Exact hex values matching Python DARK_THEME in src/tui/theme.py
 */
export const DARK_THEME: ThemeTokens = {
  name: 'dark',
  bg: '#121214',           // Julius System Dark
  surface: '#1c1c1e',      // +4% lightness shift
  raised: '#2c2c2e',       // +8% lightness shift
  text: '#f5f5f7',         // Julius primary text (15.6:1 contrast against bg)
  text_dim: '#86868b',     // Julius secondary text (4.9:1 contrast against bg)
  text_faint: '#48484a',   // Tertiary/subtle text
  accent: '#c8b896',       // Dusty 100-year-old antique paper / parchment
  success: '#30d158',      // Julius System Green
  warning: '#ffd60a',      // Julius System Yellow
  error: '#ff453a',        // Julius System Red
  border_idle: '#3e3e42',  // Crisp defined idle border
  border_focused: '#c8b896', // Focused dusty antique paper border
  scrim: 'rgba(0, 0, 0, 0.65)',
  is_dark: true,
  is_no_color: false,
  brand_gold: '#c8b896',      // Julius Brand Book Border/Accent (#C8B896 RGB 200,184,150)
  brand_crimson: '#731a1a',   // Julius Brand Book Roman Crimson (#731A1A RGB 115,26,26)
  brand_obsidian: '#1a1a1a',  // Julius Brand Book Body Obsidian (#1A1A1A RGB 26,26,26)
  brand_electric_green: '#7ed321', // Julius Master Electric Green (#7ED321)
  brand_green_deep: '#006a25',     // Julius Deep Forest Green (#006A25)
  brand_green_glow: 'rgba(126, 211, 33, 0.35)', // Electric Green Glow
  brand_slate_badge: '#0f172a',    // Dark Slate OS App Icon Badge (#0F172A)
  radius: SQUIRCLE_RADII,
};

/**
 * Julius Light Theme
 * Exact hex values matching Python LIGHT_THEME in src/tui/theme.py
 */
export const LIGHT_THEME: ThemeTokens = {
  name: 'light',
  bg: '#f5f5f7',           // Julius System Light
  surface: '#e5e5ea',      // Subtle inset surface
  raised: '#d1d1d6',       // Raised card surface
  text: '#1d1d1f',         // Primary dark text (14.8:1 contrast against bg)
  text_dim: '#6e6e73',     // Secondary text (4.8:1 contrast against bg)
  text_faint: '#aeaeb2',   // Tertiary/subtle text
  accent: '#007aff',       // Julius System Blue (light)
  success: '#34c759',      // Julius System Green (light)
  warning: '#c8b896',      // Dusty aged parchment tone
  error: '#ff3b30',        // Julius System Red (light)
  border_idle: '#c7c7cc',  // Crisp defined idle light border
  border_focused: '#007aff', // Focused light accent
  scrim: 'rgba(0, 0, 0, 0.35)',
  is_dark: false,
  is_no_color: false,
  brand_gold: '#c8b896',
  brand_crimson: '#731a1a',
  brand_obsidian: '#1a1a1a',
  brand_electric_green: '#7ed321',
  brand_green_deep: '#006a25',
  brand_green_glow: 'rgba(126, 211, 33, 0.35)',
  brand_slate_badge: '#0f172a',
  radius: SQUIRCLE_RADII,
};

