import React from 'react';
import { PassThrough } from 'stream';
import { render } from 'ink';
import { EventEmitter } from 'events';
import { App } from '../src/App.js';
import { ToolSummary, filterRealTools } from '../src/components/ToolSummary.js';
import type { JuliusBridgeEvent, ToolExecutionRecord } from '../src/types.js';

console.log('====================================================');
console.log('🧪 TESTING STEP SUPPRESSION & ERGONOMIC COMMAND CARD');
console.log('====================================================\n');

function sleep(ms: number) {
  return new Promise((r) => setTimeout(r, ms));
}

async function runTests() {
  // -----------------------------------------------------------------------------
  // Unit Test: filterRealTools & ToolSummary suppression on conversational actions
  // -----------------------------------------------------------------------------
  console.log('🔹 [Unit Test 1] Testing filterRealTools on protocol actions...');
  const conversationalTools: ToolExecutionRecord[] = [
    { tool_name: 'converse', summary: 'Executed converse', duration_s: 0.1, success: true },
    { tool_name: 'done', summary: 'Task completed: All tasks finished', duration_s: 0.1, success: true },
    { tool_name: 'ask_human', summary: 'Conversation recorded: prompt', duration_s: 0.1, success: true },
  ];

  const filtered = filterRealTools(conversationalTools);
  if (filtered.length !== 0) {
    throw new Error(`Expected 0 real tools from conversational actions, got ${filtered.length}!`);
  }
  console.log('   ✅ Conversational protocol actions ("converse", "done", "ask_human") are completely filtered out.');

  const mixedTools: ToolExecutionRecord[] = [
    { tool_name: 'converse', summary: 'Executed converse', duration_s: 0.1, success: true },
    {
      tool_name: 'run_bash',
      summary: 'Ran bash: pip install fpdf2',
      command: 'python -m pip install fpdf2',
      output: 'Collecting fpdf2\nDownloading...',
      duration_s: 4.2,
      success: true,
    },
  ];
  const realMixed = filterRealTools(mixedTools);
  if (realMixed.length !== 1 || realMixed[0]?.command !== 'python -m pip install fpdf2') {
    throw new Error(`Expected only run_bash to remain, got ${JSON.stringify(realMixed)}!`);
  }
  console.log('   ✅ Real tools are preserved while protocol tools are filtered.\n');

  // -----------------------------------------------------------------------------
  // Component Test: ToolSummary expanded view shows ONLY command, ZERO output dumps
  // -----------------------------------------------------------------------------
  console.log('🔹 [Unit Test 2] Testing ToolSummary expanded psychological view (command only, no output dumps)...');
  const stdout = new PassThrough();
  let renderedOutput = '';
  stdout.on('data', (c) => {
    renderedOutput += c.toString();
  });

  const toolsToTest: ToolExecutionRecord[] = [
    {
      tool_name: 'run_bash',
      summary: 'Ran bash: python -m pip install fpdf2',
      command: 'python -m pip install fpdf2',
      output: 'Traceback (most recent call last):\nFile "/Library/Python/..." Error: large raw stdout dump',
      duration_s: 3.5,
      success: true,
    },
  ];

  const instance = render(
    <ToolSummary
      tools={toolsToTest}
      isExpanded={true}
    />,
    { stdout: stdout as any, stdin: new PassThrough() as any }
  );

  await sleep(120);
  instance.unmount();
  const clean = renderedOutput.replace(/\x1b\[[0-9;]*[a-zA-Z]/g, '');

  if (!clean.includes('Executed Command')) {
    throw new Error(`ToolSummary missing Executed Command title! Got:\n${clean}`);
  }
  if (!clean.includes('$ python -m pip install fpdf2')) {
    throw new Error(`ToolSummary missing executed command line! Got:\n${clean}`);
  }
  if (clean.includes('Traceback') || clean.includes('large raw stdout dump')) {
    throw new Error(`VIOLATION: Raw output was dumped into the psychological command view! Got:\n${clean}`);
  }

  console.log('   ✅ ToolSummary renders dynamic card with "$ python -m pip install fpdf2".');
  console.log('   ✅ Psychological ergonomics verified: ZERO stdout/stderr trace dumped into the summary!\n');

  // -----------------------------------------------------------------------------
  // E2E Test: Full App Simulation of conversational turns without command steps
  // -----------------------------------------------------------------------------
  console.log('🔹 [E2E Test 3] Simulating user turn "hello julius" with NO commands executed...');

  class MockBridge extends EventEmitter {
    public activeModel = 'deepseek';
    public isStarted = true;
    async start() {
      this.emit('ready', {
        active_model: 'deepseek',
        theme: 'dark',
        models: [{ id: 'deepseek', name: 'DeepSeek-R1', desc: 'Reasoning' }],
        pid: 1234,
      });
    }
    submitPrompt(prompt: string) {
      this.emit('prompt_submitted', prompt);
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
  mockStdout.on('data', (chunk: Buffer) => {
    screenBuffer += chunk.toString();
  });

  const getCleanScreen = () =>
    screenBuffer
      .replace(/\x1b\[[0-9;]*[a-zA-Z]/g, '')
      .replace(/(\x1b)?\[<\d+;\d+;\d+[Mm]/g, '');

  const mockBridge = new MockBridge();
  const appInstance = render(<App bridge={mockBridge as any} />, {
    stdin: mockStdin,
    stdout: mockStdout,
    patchConsole: false,
  });

  await sleep(150);

  // 1. User asks "hello julius"
  mockStdin.write('hello julius');
  await sleep(50);
  mockStdin.write('\r');
  await sleep(150);

  // Assistant streams answer
  mockBridge.emit('bridge_event', {
    kind: 'stream_chunk',
    chunk: "Hello! I'm Julius, your unrestricted autonomous system agent. How can I help you today?",
  } as JuliusBridgeEvent);
  await sleep(100);

  // Assistant completes turn with converse tool recorded by old agent
  mockBridge.emit('bridge_event', {
    kind: 'done',
    summary: "Hello! I'm Julius, your unrestricted autonomous system agent. How can I help you today?",
    tools: [
      { tool_name: 'converse', summary: 'Executed converse', duration_s: 0.1, success: true },
    ],
  } as any);
  await sleep(200);

  const frame = getCleanScreen();
  if (frame.includes('Ran 1 step') || frame.includes('Ran steps')) {
    console.log('FAILING FRAME:\n', frame);
    throw new Error('VIOLATION: "Ran 1 step" was displayed on conversational turn with no tool commands executed!');
  }
  if (!frame.includes("Hello! I'm Julius")) {
    console.log('FAILING FRAME:\n', frame);
    throw new Error('Assistant message was not rendered!');
  }

  console.log('   ✅ Conversational turn completed cleanly: NO "Ran steps" rendered!');
  console.log('   ✅ Simple answer displayed purely and directly without cognitive clutter.\n');

  appInstance.unmount();
  console.log('====================================================');
  console.log('🎉 ALL STEP SUPPRESSION & ERGONOMIC TESTS PASSED!');
  console.log('====================================================');
  process.exit(0);
}

runTests().catch((err) => {
  console.error('\n❌ TEST FAILED:', err.message);
  process.exit(1);
});
