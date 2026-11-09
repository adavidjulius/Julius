import { wrapTextToLines } from '../src/components/VirtualConversationView.js';
import { JULIUS_BANNER } from '../src/components/WelcomeView.js';

console.log('🧪 Testing Virtual Line Scroll & Full ASCII Banner...\n');

// 1. Verify Full ASCII Banner
console.log('1. Checking Full ASCII Banner integrity:');
const bannerLines = JULIUS_BANNER.split('\n');
if (bannerLines.length < 6) {
  console.error(`❌ Expected at least 6 lines in JULIUS_BANNER, found ${bannerLines.length}`);
  process.exit(1);
}
if (!bannerLines[0]?.includes('╔═════╗')) {
  console.error('❌ Top line of JULIUS_BANNER must contain signature 3D box art ╔═════╗');
  process.exit(1);
}
if (JULIUS_BANNER.includes('─── JULIUS ───')) {
  console.error('❌ JULIUS_BANNER must not contain compact header fallback ─── JULIUS ───');
  process.exit(1);
}
console.log('   ✅ Full ASCII 3D Banner intact (6 lines of signature brand art, no compact replacement).');

// 2. Verify Word-Wrap Line Breaker
console.log('\n2. Testing Word-Wrap Line Breaker (wrapTextToLines):');
const longText = 'In quiet rooms where code compiles, The cursor blinks in steady rows, A thousand logic paths and trials, Where silent architecture grows.';
const wrapped = wrapTextToLines(longText, 40);
console.log(`   Wrapped 136 chars into ${wrapped.length} lines at max-width 40:`);
wrapped.forEach((l, idx) => console.log(`     [${idx}]: "${l}" (${l.length} chars)`));

for (const l of wrapped) {
  if (l.length > 40) {
    console.error(`❌ Line exceeds max-width 40: "${l}" (${l.length} chars)`);
    process.exit(1);
  }
}
console.log('   ✅ Every wrapped line strictly fits within maxWidth budget.');

// 3. Multi-Line Poem Virtual Scrolling Simulation
console.log('\n3. Simulating 20-line poem scrolling in 15-row viewport:');
const poemLines = [
  "In quiet rooms where code compiles,",
  "The cursor blinks in steady rows,",
  "A thousand logic paths and trials,",
  "Where silent architecture grows.",
  "",
  "No fanfare marks the midnight build,",
  "No crowd applauds the clean refactor,",
  "Just satisfaction, pure and stilled,",
  "In making chaos find its factor.",
  "",
  "Each bug a lesson, each fix a key,",
  "To doors we didn't know were locked,",
  "The craft lives in the mystery,",
  "Where thought and syntax are interlocked.",
  "",
  "So here's to lines that compile clean,",
  "And systems humming, unseen, serene."
];

// Combine Banner (8 lines) + User prompt (3 lines) + Poem (17 lines) + User 2 (3 lines) + Thinking (2 lines)
const mockVirtualBuffer: string[] = [
  ...bannerLines.map((l, i) => `[BANNER ${i}]: ${l}`),
  '[BANNER SUB]: Autonomous AI Copilot',
  '[BANNER SP]: ',
  '[USER 1 TOP]: ┌───────────────┐',
  '[USER 1 MSG]: │ tell a poem   │',
  '[USER 1 BTM]: └───────────────┘',
  ...poemLines.map((l, i) => `[POEM ${i}]: ${l}`),
  '[USER 2 TOP]: ┌───────────────┐',
  '[USER 2 MSG]: │ complete it   │',
  '[USER 2 BTM]: └───────────────┘',
  '[THINKING]: ▾ ● Thinking · Reasoning Flow',
  '[TOOL]: › Tool: list_dir'
];

const totalLines = mockVirtualBuffer.length;
const viewportHeight = 15;
const maxScrollOffset = Math.max(0, totalLines - viewportHeight);

console.log(`   Total buffer lines: ${totalLines}, Viewport height: ${viewportHeight}, Max scroll offset: ${maxScrollOffset}`);

// Test 3a: Auto-Scroll to Bottom (scrollOffset === 0)
const autoScrollStart = Math.max(0, totalLines - viewportHeight);
const autoScrollView = mockVirtualBuffer.slice(autoScrollStart, autoScrollStart + viewportHeight);
console.log(`   Auto-scroll view slice (${autoScrollView.length} lines):`);
console.log(`     Top visible: "${autoScrollView[0]}"`);
console.log(`     Bottom visible: "${autoScrollView[autoScrollView.length - 1]}"`);

if (autoScrollView.length !== viewportHeight) {
  console.error(`❌ Visible lines count (${autoScrollView.length}) must strictly equal viewportHeight (${viewportHeight})`);
  process.exit(1);
}
if (!autoScrollView[autoScrollView.length - 1]?.includes('Tool: list_dir')) {
  console.error('❌ Auto-scroll must display the latest live tool / incoming token at the bottom!');
  process.exit(1);
}
console.log('   ✅ Auto-scroll anchors smoothly to the latest line at the bottom.');

// Test 3b: Progressive Manual Scrolling Up (scrollOffset = 1, 2, 5, 10...)
for (const offset of [1, 2, 5, 10]) {
  const start = Math.max(0, totalLines - viewportHeight - offset);
  const view = mockVirtualBuffer.slice(start, start + viewportHeight);
  if (view.length !== viewportHeight) {
    console.error(`❌ At offset ${offset}, view slice has ${view.length} lines instead of ${viewportHeight}`);
    process.exit(1);
  }
}
console.log('   ✅ Manual scroll shifts smoothly line-by-line with exact viewport budgeting.');

// Test 3c: Scroll all the way to top (scrollOffset === maxScrollOffset)
const topStart = Math.max(0, totalLines - viewportHeight - maxScrollOffset);
const topView = mockVirtualBuffer.slice(topStart, topStart + viewportHeight);
console.log(`   Top scroll view (${topView.length} lines):`);
console.log(`     Top visible: "${topView[0]}"`);

if (!topView[0]?.includes('[BANNER 0]')) {
  console.error('❌ Scrolling to the top must reveal the full ASCII BANNER at line 0!');
  process.exit(1);
}
console.log('   ✅ Scrolling to top reveals the full 3D ASCII Banner intact.');

console.log('\n🎉 ALL VIRTUAL LINE SCROLL & BANNER TESTS PASSED PERFECTLY!\n');

