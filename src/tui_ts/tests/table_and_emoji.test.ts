import { stripOrReplaceEmojis, parseTableRow, isTableLine, isTableDelimiter } from '../src/components/AssistantMessage.js';

console.log('🧪 Testing Table & Emoji Improvements...\n');

// 1. Emoji sanitization
const rawText = 'Layer | Status | What\'s Done\nPhase 2 | ✅ Complete | Done 🚀\nPhase 1 | ❌ Failed | Warning ⚠️';
const cleanText = stripOrReplaceEmojis(rawText);

if (cleanText.includes('✅') || cleanText.includes('❌') || cleanText.includes('🚀') || cleanText.includes('⚠️')) {
  console.error('❌ Failed: Emojis should be completely sanitized!');
  process.exit(1);
}
if (!cleanText.includes('[DONE]') || !cleanText.includes('[FAIL]') || !cleanText.includes('[!]')) {
  console.error('❌ Failed: Clean ASCII tokens [DONE], [FAIL], [!] must be present!');
  process.exit(1);
}
console.log('   ✅ Emoji sanitization verified.');

// 2. Table row parsing with and without leading/trailing pipes
const rowWithOuterPipes = '| Layer | Status | What\'s Done |';
const rowWithoutOuterPipes = 'Layer | Status | What\'s Done';
const parsed1 = parseTableRow(rowWithOuterPipes);
const parsed2 = parseTableRow(rowWithoutOuterPipes);

if (parsed1.length !== 3 || parsed1[0] !== 'Layer' || parsed1[1] !== 'Status' || parsed1[2] !== "What's Done") {
  console.error('❌ Failed to parse row with outer pipes:', parsed1);
  process.exit(1);
}
if (parsed2.length !== 3 || parsed2[0] !== 'Layer' || parsed2[1] !== 'Status' || parsed2[2] !== "What's Done") {
  console.error('❌ Failed to parse row without outer pipes:', parsed2);
  process.exit(1);
}
console.log('   ✅ Table row parsing parity confirmed.');

// 3. Table line detection
if (!isTableLine(rowWithOuterPipes) || !isTableLine(rowWithoutOuterPipes)) {
  console.error('❌ isTableLine should identify both formats!');
  process.exit(1);
}

const delimiter1 = '|---|:---:|---|';
const delimiter2 = '---|---|---';
if (!isTableDelimiter(delimiter1) || !isTableDelimiter(delimiter2)) {
  console.error('❌ isTableDelimiter should identify both delimiter formats!');
  process.exit(1);
}
console.log('   ✅ Table delimiter detection confirmed.');

console.log('\n🎉 ALL TABLE AND EMOJI SANITIZATION TESTS PASSED CLEANLY!\n');

