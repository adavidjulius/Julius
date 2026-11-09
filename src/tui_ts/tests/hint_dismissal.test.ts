import { recordShortcutUse, shouldShowHint, getShortcutCount, DEFAULT_MAX_HINT_COUNT } from '../src/utils/hintManager.js';

console.log('====================================================');
console.log('🧪 TESTING 7-TIMES SHORTCUT HINT DISMISSAL MECHANISM');
console.log('====================================================\n');

const testKey = `test_shortcut_${Date.now()}`;

// 1. Initially count should be 0 and shouldShowHint must be true
const initialCount = getShortcutCount(testKey);
const showInitially = shouldShowHint(testKey);
console.log(`[1] Initial count: ${initialCount}, shouldShowHint: ${showInitially}`);
if (initialCount !== 0 || !showInitially) {
  console.error('❌ Failed: initial state must be 0 and showHint true');
  process.exit(1);
}

// 2. Increment through 6 uses — hint MUST still be visible
for (let i = 1; i <= 6; i++) {
  const count = recordShortcutUse(testKey);
  const show = shouldShowHint(testKey);
  console.log(`  Use #${i}: count = ${count}, shouldShowHint = ${show}`);
  if (count !== i || !show) {
    console.error(`❌ Failed at step ${i}: hint should still show before 7th use`);
    process.exit(1);
  }
}

// 3. 7th use — reaching the threshold!
const count7 = recordShortcutUse(testKey);
const show7 = shouldShowHint(testKey);
console.log(`[3] 7th Use: count = ${count7}, shouldShowHint = ${show7}`);
if (count7 !== 7 || show7 !== false) {
  console.error('❌ Failed: On 7th use, suggestion text MUST disappear (shouldShowHint = false)!');
  process.exit(1);
}

// 4. 8th and beyond — remains permanently dismissed
const count8 = recordShortcutUse(testKey);
const show8 = shouldShowHint(testKey);
console.log(`[4] 8th Use: count = ${count8}, shouldShowHint = ${show8}`);
if (show8 !== false) {
  console.error('❌ Failed: Hint must remain dismissed for experienced users');
  process.exit(1);
}

console.log('\n✅ ALL 7-TIMES SHORTCUT DISMISSAL TESTS PASSED SUCCESSFULLY!\n');
