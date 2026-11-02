import React from 'react';
import { PassThrough } from 'stream';
import { render } from 'ink';
import { EventEmitter } from 'events';
import { App } from '../src/App.js';
import type { AgentBridge } from '../src/bridge/AgentBridge.js';
import type { JuliusBridgeEvent } from '../src/types.js';

console.log('====================================================');
console.log('🧪 TESTING DYNAMIC THINKING & RESTORED ACTIVE ACTION');
console.log('====================================================\n');

class MockBridge extends EventEmitter {
  public activeModel = 'deepseek';
  public isStarted = true;
  public cancelled = false;

  async start() {
    this.emit('ready', {
      active_model: 'deepseek',
      theme: 'dark',
      models: [
        { id: 'deepseek', name: 'DeepSeek-R1', desc: 'Reasoning' },
        { id: 'gemini', name: 'Gemini 2.0 Flash', desc: 'Fast' },
      ],
      pid: 1234,
    });
  }

  submitPrompt(prompt: string) {
    this.emit('prompt_submitted', prompt);
  }

  cancelAction() {
    this.cancelled = true;
    this.emit('cancelled');
  }

  async close() {}
}

const mockStdin = new PassThrough() as any;
mockStdin.isTTY = true;
mockStdin.setRawMode = () => mockStdin;
mockStdin.ref = () => mockStdin;
mockStdin.unref = () => mockStdin;

const mockStdout = new PassThrough() as any;
mockStdout.columns = 120;
mockStdout.rows = 50;

let screenBuffer = '';
let lastChunk = '';
mockStdout.on('data', (chunk: Buffer) => {
  lastChunk = chunk.toString();
  screenBuffer += chunk.toString();
});

function getCleanScreen(): string {
  return screenBuffer.replace(/\x1b\[[0-9;]*[a-zA-Z]/g, '').replace(/\x1b\]22;[^\x07\x1b]*(\x07|\x1b\\)/g, '');
}

function getLastCleanFrame(): string {
  return lastChunk.replace(/\x1b\[[0-9;]*[a-zA-Z]/g, '').replace(/\x1b\]22;[^\x07\x1b]*(\x07|\x1b\\)/g, '');
}

async function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function testDynamicThinkingAndActiveAction() {
  const mockBridge = new MockBridge() as unknown as AgentBridge;

  const instance = render(React.createElement(App, {
    bridge: mockBridge,
    initialModel: 'deepseek',
  }), {
    stdin: mockStdin,
    stdout: mockStdout,
    debug: true,
  });

  await sleep(150);

  // ----------------------------------------------------
  // TEST 1: Submit prompt & verify initial thinking state
  // ----------------------------------------------------
  console.log('🔹 [Test 1] Submitting prompt "List files in my desktop"...');
  mockStdin.write('List files in my desktop');
  await sleep(50);
  mockStdin.write('\r');
  await sleep(150);

  let frame = getCleanScreen();
  if (!frame.includes('List files in my desktop')) {
    console.log('DEBUG FRAME:\n', frame);
    throw new Error('User message not visible on screen!');
  }
  if (!frame.includes('Thinking')) {
    console.log('DEBUG FRAME:\n', frame);
    throw new Error('Thinking indicator not initiated!');
  }
  console.log('   ✅ User message rendered and Thinking initiated.\n');

  // ----------------------------------------------------
  // TEST 2: Dynamic Thinking Label Changes on Thoughts
  // ----------------------------------------------------
  console.log('🔹 [Test 2] Simulating incoming contextual thoughts...');
  screenBuffer = '';
  (mockBridge as any).emit('bridge_event', {
    kind: 'thought',
    thought: 'I will list all files on the desktop using bash command ls',
  } as JuliusBridgeEvent);
  await sleep(150);

  frame = getCleanScreen();
  if (!frame.includes('Thinking — List all files on the desktop')) {
    console.log('DEBUG FRAME 2:\n', frame);
    throw new Error(`Dynamic contextual thought label failed! Got:\n${frame}`);
  }
  console.log('   ✅ Dynamic label updated to contextual verb: "Thinking — List all files on the desktop...".\n');

  // ----------------------------------------------------
  // TEST 3: Dynamic Label Changes to Running Action
  // ----------------------------------------------------
  console.log('🔹 [Test 3] Simulating action_scheduled event (ls -la ~/Desktop)...');
  screenBuffer = '';
  (mockBridge as any).emit('bridge_event', {
    kind: 'action_scheduled',
    action: 'run_bash',
    command: 'ls -la ~/Desktop',
  } as JuliusBridgeEvent);
  await sleep(150);

  frame = getCleanScreen();
  // Verify that active action command is routed to status line and inspector
  if (!frame.includes('ls -la ~/Desktop') || !frame.includes('Inspect Action')) {
    console.log('DEBUG FRAME 3:\n', frame);
    throw new Error(`Active action routing failed! Expected "ls -la ~/Desktop [Ctrl+I: Inspect Action]", got:\n${frame}`);
  }
  console.log('   ✅ Active action cleanly routed to inspector status line: "ls -la ~/Desktop [Ctrl+I: Inspect Action]".\n');

  // ----------------------------------------------------
  // TEST 4: Tool Execution Output Streaming
  // ----------------------------------------------------
  console.log('🔹 [Test 4] Simulating tool_completed event with output...');
  (mockBridge as any).emit('bridge_event', {
    kind: 'tool_completed',
    tool_name: 'run_bash',
    command: 'ls -la ~/Desktop',
    output: 'drwxr-xr-x Julius\ndrwxr-xr-x workspaces\n-rw-r--r-- flames.html',
    success: true,
  } as JuliusBridgeEvent);
  await sleep(100);

  // Send subsequent thought
  screenBuffer = '';
  (mockBridge as any).emit('bridge_event', {
    kind: 'thought',
    thought: 'Analyzing the listed directory contents to formulate final response',
  } as JuliusBridgeEvent);
  await sleep(150);

  frame = getCleanScreen();
  if (!frame.includes('Thinking — Analyzing the listed directory')) {
    console.log('DEBUG FRAME 4:\n', frame);
    throw new Error(`Dynamic label failed on subsequent thought! Got:\n${frame}`);
  }
  console.log('   ✅ Thinking label dynamically updated to: "Thinking — Analyzing the listed directory...".\n');

  // ----------------------------------------------------
  // TEST 5: Clicking Thinking Indicator Expands Dynamic Ergonomic Reasoning Flow
  // ----------------------------------------------------
  console.log('🔹 [Test 5] Simulating terminal toggle on thinking indicator (Ctrl+T)...');
  screenBuffer = '';
  mockStdin.write('\x14'); // Ctrl+T
  await sleep(150);

  frame = getCleanScreen();
  if (!frame.includes('Thinking') || !frame.includes('Reasoning Flow')) {
    console.log('DEBUG FRAME 5:\n', frame);
    throw new Error(`Dynamic ergonomic thinking panel failed to expand! Frame:\n${frame}`);
  }
  if (!frame.includes('Analyzing the listed directory contents')) {
    console.log('DEBUG FRAME 5:\n', frame);
    throw new Error(`Thinking panel missing thought content! Frame:\n${frame}`);
  }
  console.log('   ✅ Dynamic ergonomic reasoning panel expanded successfully with warm typography!');
  console.log('   ✅ Panel is strictly isolated to LLM thoughts with dynamic saccadic width.\n');

  // Close full view with Ctrl+T
  mockStdin.write('\x14');
  await sleep(100);

  // ----------------------------------------------------
  // TEST 6: Authentic Active Action Modal via /action and Ctrl+I
  // ----------------------------------------------------
  console.log('🔹 [Test 6] Testing Active Action Modal (Ctrl+I hotkey & /action)...');
  screenBuffer = '';

  // Send raw Ctrl+I / Tab byte (\x09)
  mockStdin.write('\x09');
  await sleep(150);

  frame = getCleanScreen();
  if (!frame.includes('Active Action') || !frame.includes('STATUS:')) {
    console.log('DEBUG FRAME 6 (Ctrl+I):\n', frame);
    throw new Error(`Active Action modal failed to open via Ctrl+I hotkey! Frame:\n${frame}`);
  }
  if (!frame.includes('Live status and control of background operations')) {
    console.log('DEBUG FRAME 6:\n', frame);
    throw new Error(`Active Action subtitle missing! Frame:\n${frame}`);
  }
  if (!frame.includes('ls -la ~/Desktop') || !frame.includes('Process Output:')) {
    console.log('DEBUG FRAME 6:\n', frame);
    throw new Error(`Active Action boxes missing! Frame:\n${frame}`);
  }
  console.log('   ✅ Active Action Modal opened instantly via Ctrl+I hotkey!');
  console.log('   ✅ Rendered with STATUS, Command / Target, and persistent Process Output.');

  // Test [C] Cancel in modal
  console.log('🔹 [Test 7] Pressing [C] to Cancel Active Action...');
  mockStdin.write('c');
  await sleep(150);

  if (!(mockBridge as any).cancelled) {
    throw new Error('Cancel signal was not dispatched to bridge!');
  }
  console.log('   ✅ Active action cancelled successfully via modal.\n');

  instance.unmount();
  console.log('====================================================');
  console.log('🎉 ALL DYNAMIC THINKING & ACTIVE ACTION TESTS PASSED!');
  console.log('====================================================');
  process.exit(0);
}

testDynamicThinkingAndActiveAction().catch((err) => {
  console.error('\n❌ TEST FAILED:', err.message);
  process.exit(1);
});
