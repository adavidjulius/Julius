import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';

const HINTS_FILE = path.join(os.homedir(), '.julius', 'hints_state.json');
export const DEFAULT_MAX_HINT_COUNT = 7;

interface HintsState {
  counts: Record<string, number>;
}

let inMemoryState: HintsState | null = null;

function loadHintsState(): HintsState {
  if (inMemoryState) return inMemoryState;
  try {
    if (fs.existsSync(HINTS_FILE)) {
      const raw = fs.readFileSync(HINTS_FILE, 'utf-8');
      inMemoryState = JSON.parse(raw);
      if (inMemoryState && typeof inMemoryState.counts === 'object') {
        return inMemoryState;
      }
    }
  } catch {
    // Non-blocking fallback
  }
  inMemoryState = { counts: {} };
  return inMemoryState;
}

function saveHintsState(state: HintsState): void {
  inMemoryState = state;
  try {
    const dir = path.dirname(HINTS_FILE);
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }
    fs.writeFileSync(HINTS_FILE, JSON.stringify(state, null, 2), 'utf-8');
  } catch {
    // Non-blocking fallback
  }
}

/**
 * Record a shortcut use or step action (e.g. 'ctrl_o', 'ctrl_t', 'ctrl_y', 'ctrl_i', 'status_help', 'f2_model').
 * Persistently increments user familiarity count.
 */
export function recordShortcutUse(key: string): number {
  const state = loadHintsState();
  const current = (state.counts[key] || 0) + 1;
  state.counts[key] = current;
  saveHintsState(state);
  return current;
}

/**
 * Check whether a shortcut suggestion text should still be displayed.
 * 7-Times Rule: Once the user has performed the step or used the shortcut 7 times,
 * the hint suggestion text automatically disappears to keep the UI clean!
 */
export function shouldShowHint(key: string, maxCount: number = DEFAULT_MAX_HINT_COUNT): boolean {
  const state = loadHintsState();
  const count = state.counts[key] || 0;
  return count < maxCount;
}

export function getShortcutCount(key: string): number {
  const state = loadHintsState();
  return state.counts[key] || 0;
}
