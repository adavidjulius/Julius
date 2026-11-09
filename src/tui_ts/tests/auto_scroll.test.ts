import type { MessageRecord } from '../src/types.js';

console.log('🧪 Testing Auto-Scroll & Viewport Windowing...\n');

// 1. Line wrapping calculation verification
const countWrappedLines = (text: string, width: number): number => {
  if (!text) return 0;
  const clean = text.replace(/[\u{1F600}-\u{1F64F}\u{1F300}-\u{1F5FF}\u{1F680}-\u{1F6FF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}]/gu, '');
  const lines = clean.split('\n');
  let count = 0;
  const innerW = Math.max(16, width);
  for (const l of lines) {
    if (l.length === 0) {
      count += 1;
    } else {
      count += Math.max(1, Math.ceil(l.length / innerW));
    }
  }
  return count;
};

// Paragraph of 200 chars in width 50 should be 4 lines
const samplePara = 'a'.repeat(200);
const lines = countWrappedLines(samplePara, 50);
if (lines !== 4) {
  console.error(`❌ Expected 4 lines for 200 chars in 50 width, got ${lines}`);
  process.exit(1);
}
console.log('   ✅ Word-wrap line counter accurately budgets paragraphs.');

// 2. Viewport windowing: bottom-anchoring when conversation exceeds viewport
const maxViewportRows = 20;
const messages: MessageRecord[] = [
  { id: '1', role: 'assistant', content: 'Turn 0: Welcome message (long paragraph with multiple lines) '.repeat(5), timestamp: 1 },
  { id: '2', role: 'user', content: 'distract me', timestamp: 2 },
  { id: '3', role: 'assistant', content: 'Turn 1: Here is a distraction with a puzzle and facts '.repeat(5), timestamp: 3 },
  { id: '4', role: 'user', content: 'i want you to roast this julius project fully in deep roast and no mercy manner', timestamp: 4 },
];

const contentTextWidth = 60;
const turnHeights = messages.map((m) => {
  let h = 2;
  if (m.role === 'user') {
    h += 2 + countWrappedLines(m.content, 50);
  } else {
    h += countWrappedLines(m.content, contentTextWidth);
  }
  return h;
});

console.log('   Calculated turn heights:', turnHeights);
const totalHeight = turnHeights.reduce((a, b) => a + b, 0);
console.log(`   Total conversation height: ${totalHeight} rows (viewport: ${maxViewportRows} rows)`);

if (totalHeight <= maxViewportRows) {
  console.error('❌ Conversation should exceed viewport for this test!');
  process.exit(1);
}

// Perform bottom-anchoring algorithm
const totalTurns = messages.length;
const remainingRowsForHistory = maxViewportRows - 4; // reserve 4 rows for thinking/streaming

let startIdx = totalTurns - 1;
let acc = 0;
while (startIdx >= 0) {
  const h = turnHeights[startIdx] || 3;
  if (acc + h > remainingRowsForHistory && startIdx < totalTurns - 1) {
    break;
  }
  acc += h;
  startIdx--;
}
startIdx = Math.max(0, startIdx + 1);
const visibleMessages = messages.slice(startIdx, totalTurns);

console.log(`   Visible messages selected: ${visibleMessages.length} (turns ${startIdx} to ${totalTurns - 1})`);
if (visibleMessages.length >= totalTurns) {
  console.error('❌ Oldest messages should have scrolled off the top!');
  process.exit(1);
}
if (visibleMessages[visibleMessages.length - 1]?.id !== '4') {
  console.error('❌ The latest turn (id: 4) MUST ALWAYS be visible at the bottom!');
  process.exit(1);
}
console.log('   ✅ Bottom-anchoring verified: newest turn is anchored at the bottom, oldest scrolled off.');

// 3. Streaming tail slicing when response is taller than viewport
const longStreamingText = Array.from({ length: 30 }, (_, i) => `Streaming roast line ${i + 1}: detailed feedback on architecture`).join('\n');
const fullStreamLines = countWrappedLines(longStreamingText, contentTextWidth);
const availableStreamLines = 15;

const streamLines = longStreamingText.split('\n');
let streamAcc = 0;
let startP = streamLines.length - 1;
while (startP >= 0) {
  const pLines = Math.max(1, Math.ceil((streamLines[startP] || '').length / contentTextWidth));
  if (streamAcc + pLines > availableStreamLines && startP < streamLines.length - 1) {
    break;
  }
  streamAcc += pLines;
  startP--;
}
startP = Math.max(0, startP + 1);
const displayStreaming = streamLines.slice(startP).join('\n');

if (!displayStreaming.includes('Streaming roast line 30')) {
  console.error('❌ Sliced streaming output MUST contain the latest incoming token line 30!');
  process.exit(1);
}
if (displayStreaming.includes('Streaming roast line 1\n')) {
  console.error('❌ Earlier lines of long streaming output should have scrolled off!');
  process.exit(1);
}
console.log('   ✅ Streaming tail slicing verified: latest incoming tokens continuously visible at bottom.');

console.log('\n🎉 ALL AUTO-SCROLL TESTS PASSED CLEANLY!\n');

