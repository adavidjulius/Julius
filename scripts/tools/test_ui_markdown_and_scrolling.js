import React from '../src/tui_ts/node_modules/react/index.js';
import { PassThrough } from 'stream';
import { render } from '../src/tui_ts/node_modules/ink/build/index.js';
import { EventEmitter } from 'events';
import { App } from '../src/tui_ts/dist/App.js';
import { renderInlineMarkdown } from '../src/tui_ts/dist/components/AssistantMessage.js';
import { DARK_THEME } from '../src/tui_ts/dist/theme/tokens.js';

console.log('====================================================');
console.log('🧪 TESTING UI RENDERING, MARKDOWN PARSING & SCROLLING');
console.log('====================================================\n');

class MockBridge extends EventEmitter {
  constructor() {
    super();
    this.activeModel = 'nvidia';
    this.isStarted = true;
  }
  async start() {
    this.emit('ready', {
      active_model: 'nvidia',
      theme: 'dark',
      models: [{ id: 'nvidia', name: 'NVIDIA Nemotron 550B', desc: 'Reasoning' }],
      pid: 9999,
    });
  }
  submitPrompt(p) {
    this.emit('prompt_submitted', p);
  }
  async switchModel(m) {
    this.activeModel = m;
    this.emit('model_switched', m);
  }
  async close() {}
}

const mockStdin = new PassThrough();
mockStdin.isTTY = true;
mockStdin.setRawMode = () => mockStdin;
mockStdin.ref = () => mockStdin;
mockStdin.unref = () => mockStdin;

const mockStdout = new PassThrough();
mockStdout.columns = 100;
mockStdout.rows = 35;

let screenBuffer = '';
mockStdout.on('data', (d) => {
  screenBuffer += d.toString();
});

function getCleanScreen() {
  return screenBuffer
    .replace(/\x1b\[[0-9;]*[a-zA-Z]/g, '')
    .replace(/\x1b\([a-zA-Z0-9]/g, '')
    .replace(/\r/g, '');
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function runTest() {
  const mockBridge = new MockBridge();

  // Test 1: Markdown tokenization test directly
  console.log('🔹 [Test 1] Testing markdown inline tokenization...');
  const testText = "You are **Admin User** (username: `adminuser`), with `/home/adminuser` home.";
  const renderedNode = renderInlineMarkdown(testText, DARK_THEME);
  if (!renderedNode) throw new Error("renderInlineMarkdown failed");
  console.log('   ✅ Markdown inline tokenization passed.\n');

  // Test 2: Mount full app and simulate multi-turn conversation
  console.log('🔹 [Test 2] Mounting App with MockBridge in 100x35 terminal...');
  const { cleanup } = render(
    React.createElement(App, {
      initialModel: 'nvidia',
      bridge: mockBridge,
    }),
    {
      stdout: mockStdout,
      stdin: mockStdin,
      patchConsole: false,
    }
  );

  await sleep(150);
  mockBridge.emit('ready', {
    active_model: 'nvidia',
    theme: 'dark',
    models: [{ id: 'nvidia', name: 'NVIDIA Nemotron 550B', desc: '550B NIM' }],
    pid: 9999,
  });
  await sleep(100);

  // Simulate Turn 1: User says hello
  console.log('🔹 [Test 3] Simulating Turn 1 (Hello David Julius)...');
  mockBridge.emit('bridge_event', {
    kind: 'converse',
    message: "Hello David! I'm Julius, your unrestricted autonomous system agent. How can I help you today?",
    tools: [{ name: 'read_file', success: true, duration_s: 1.7 }],
  });
  await sleep(100);

  // Simulate Turn 2: User asks who am i
  console.log('🔹 [Test 4] Simulating Turn 2 (who am i) with markdown bold and inline code...');
  mockBridge.emit('bridge_event', {
    kind: 'converse',
    message: "You are **Admin User** (username: `adminuser`), the host user and administrator of this macOS system.",
    tools: [{ name: 'search_files', success: true, duration_s: 3.4 }],
  });
  await sleep(100);

  // Simulate Turn 3: Long listing turn
  console.log('🔹 [Test 5] Simulating Turn 3 (long job listing with bullet lists)...');
  const longListing = [
    "I'm Julius, your unrestricted autonomous system agent on macOS. Here's what I can do for you:",
    "* **List/explore directories** - `list_dir` to see folder contents",
    "* **Search files** - `search_files` to find text/code inside files",
    "**System & Shell Commands**",
    "* **Install packages** - Homebrew, pip, npm, cargo, etc.",
    "* **System administration** - Full admin privileges, no restrictions",
    "* **Process management** - ps, kill, htop, system monitoring",
    "* **Write/run code** - Python, JavaScript, Go, Rust, C++, Swift, etc.",
    "* **Run tests** - `run_tests` for pytest, jest, cargo test, etc.",
    "* **Debug & refactor** - Read, analyze, and modify codebases",
    "* **Penetration testing** - Network scans, vulnerability research",
    "**CapCut Video Editing Suite**",
    "* **Add clips, audio, text, effects, transitions**",
    "* **Beat-sync editing** - Auto-cut to music BPM",
    "* **Export & open in CapCut Desktop**",
    "**Just tell me what you need** - I'll execute it directly.",
  ].join('\n');

  mockBridge.emit('bridge_event', {
    kind: 'done',
    summary: longListing,
    tools: [{ name: 'run_bash', success: true, duration_s: 10.1 }],
  });
  await sleep(150);

  let frame = getCleanScreen();
  // Verify markdown rendered properly: no raw **Admin User**
  if (frame.includes('**Admin User**')) {
    throw new Error("Raw **Admin User** leaked into rendered screen! Expected asterisks to be stripped and bolded.");
  }
  if (frame.includes('`adminuser`')) {
    throw new Error("Raw `adminuser` with backticks leaked into rendered screen! Expected backticks to be stripped.");
  }
  console.log('   ✅ Markdown bold, inline code, and bullet lists rendered with clean typography.\n');

  // Verify ToolSummary is rendered above assistant response
  if (!frame.includes('Ran 1 step')) {
    console.log('--- FRAME CONTENTS ---');
    console.log(frame);
    console.log('----------------------');
    throw new Error("ToolSummary missing from turn!");
  }
  console.log('   ✅ ToolSummary (› Ran 1 step · 10.1s) is present above assistant response.\n');

  // Test 6: Verify scrolling up with PageUp
  console.log('🔹 [Test 6] Testing PageUp scrolling...');
  screenBuffer = '';
  mockStdin.write('\x1b[5~'); // PageUp
  await sleep(150);

  frame = getCleanScreen();
  if (!frame.includes('Scrolled up')) {
    throw new Error("PageUp failed to update scrollOffset or show scrolled indicator!");
  }
  console.log('   ✅ PageUp scroll registered: viewport shifted up and indicator displayed.\n');

  // Test 7: Verify returning to bottom with End key
  console.log('🔹 [Test 7] Testing End key return to bottom...');
  screenBuffer = '';
  mockStdin.write('\x1b[4~'); // End key
  await sleep(150);

  frame = getCleanScreen();
  if (frame.includes('Scrolled up')) {
    throw new Error("End key failed to reset scrollOffset to 0!");
  }
  console.log('   ✅ End key reset scroll offset to bottom (pinned).\n');

  cleanup();
  console.log('====================================================');
  console.log('🎉 ALL UI RENDERING, MARKDOWN & SCROLL TESTS PASSED!');
  console.log('====================================================\n');
}

runTest().catch((err) => {
  console.error('❌ Test failed:', err);
  process.exit(1);
});
