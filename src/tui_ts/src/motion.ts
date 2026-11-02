/**
 * Physics and timing presets for Julius terminal animations.
 * Exactly matches src/tui/motion.py
 */

export const MotionPresets = {
  ENTER_DURATION_MS: 220,    // 220 ms
  SETTLE_DURATION_MS: 160,   // 160 ms
  FADE_DURATION_MS: 120,     // 120 ms
  BREATHE_CYCLE_MS: 1400,    // 1400 ms loop
  BREATHE_MIN_OPACITY: 0.35,
  BREATHE_MAX_OPACITY: 1.0,
} as const;

export function isReducedMotion(): boolean {
  const envVal = (process.env.JULIUS_REDUCE_MOTION || '').toLowerCase().trim();
  return ['1', 'true', 'yes', 'on'].includes(envVal);
}

