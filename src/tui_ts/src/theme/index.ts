import { DARK_THEME, LIGHT_THEME } from './tokens.js';
import type { ThemeTokens } from '../types.js';

export * from './tokens.js';

export function getTheme(name?: string): ThemeTokens {
  const norm = (name || '').trim().toLowerCase();
  if (norm === 'light') {
    return LIGHT_THEME;
  }
  return DARK_THEME;
}

