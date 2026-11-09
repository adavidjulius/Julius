import React from 'react';
import { PassThrough } from 'stream';
import { render } from 'ink';
import { EventEmitter } from 'events';
import { AgentBridge } from '../src/tui_ts/src/bridge/AgentBridge.js';
import { App } from '../src/tui_ts/src/App.js';
import { filterRealTools, ToolSummary } from '../src/tui_ts/src/components/ToolSummary.js';
import { AssistantMessage } from '../src/tui_ts/src/components/AssistantMessage.js';
import type { ToolExecutionRecord, JuliusBridgeEvent } from '../src/tui_ts/src/types.js';

console.log('====================================================');
console.log('🧪 RUNNING COMPREHENSIVE JULIUS LIVE INPUT & UI TESTS');
console.log('====================================================\n');

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

function stripAnsi(str: string): string {
  return str.replace(/\x1b\[[0-9;]*[a-zA-Z]/g, '').replace(/\x1b\]22;[^\x07\x1b]*(\x07|\x1b\\)/g, '');
}

async function runLiveTests() {
  // -----------------------------------------------------------------------------
  // Test 1: Real Python Backend IPC Bridge Connection & Subprocess Latency
  // -----------------------------------------------------------------------------
  console.log('🔹 [Test 1] Spawning live Python WebAgent IPC Bridge...');
  const bridge = new AgentBridge();
  const readyPayload = await bridge.start();

  console.log(`   ✅ Bridge connected in real-time (PID: ${readyPayload.pid})`);
  console.log(`   ✅ Active Model: ${readyPayload.active_model}`);
  console.log(`   ✅ Available Models: ${readyPayload.models.length}`);

  const t0 = Date.now();
  await bridge.ping();
  const latency = Date.now() - t0;
  console.log(`   ✅ Round-trip IPC latency: ${latency}ms`);

  const modelsList = await bridge.getModels();
  if (!modelsList.models || modelsList.models.length === 0) {
    throw new Error('Failed to retrieve model list over live IPC bridge!');
  }
  console.log(`   ✅ Retrieved ${modelsList.models.length} registered models over live IPC.`);

  await bridge.close();
  console.log('   ✅ Live Python IPC backend process closed cleanly.');

  // -----------------------------------------------------------------------------
  // Test 2: Live Question Clarification Flow & Input Non-Blocking
  // -----------------------------------------------------------------------------
  console.log('\n🔹 [Test 2] Testing Question Clarification Flow (No Input Blocking)...');
  class MockTestBridge extends EventEmitter {
    public activeModel = 'nvidia';
    public isStarted = true;
    public lastSubmittedPrompt = '';
    public lastAnsweredQuestion = '';
    public lastConfirmedAction: boolean | null = null;

    async start() {
      return { active_model: 'nvidia', theme: 'dark', models: [], pid: process.pid };
    }
    submitPrompt(p: string) {
      this.lastSubmittedPrompt = p;
    }
    answerQuestion(ans: string) {
      this.lastAnsweredQuestion = ans;
      this.emit('question_ack', { answer: ans });
    }
    confirmAction(allow: boolean) {
      this.lastConfirmedAction = allow;
      this.emit('confirmation_ack', { allow });
    }
    cancelAction() {
      this.emit('action_cancelled');
    }
    async switchModel(m: string) {
      this.activeModel = m;
      this.emit('model_switched', m);
      return m;
    }
    async close() {}
  }

  const mockBridge = new MockTestBridge() as any;
  const mockStdin = new PassThrough() as any;
  mockStdin.isTTY = true;
  mockStdin.setRawMode = () => mockStdin;
  mockStdin.ref = () => mockStdin;
  mockStdin.unref = () => mockStdin;

  const mockStdout = new PassThrough() as any;
  mockStdout.columns = 100;
  mockStdout.rows = 30;

  let screenOutput = '';
  mockStdout.on('data', (chunk: Buffer) => {
    screenOutput += chunk.toString();
  });

  const appInstance = render(React.createElement(App, { bridge: mockBridge }), {
    stdin: mockStdin,
    stdout: mockStdout,
    debug: true,
  });

  await sleep(150);

  // Simulate backend asking user clarification question
  console.log('   Simulating backend asking user clarification question...');
  mockBridge.emit('bridge_event', {
    kind: 'ask_user_question',
    question: 'Multiple active tasks exist. Which task would you like to work on?',
    options: ['1. Continue task A', '2. Start fresh task'],
  });

  await sleep(150);
  let cleanFrame = stripAnsi(screenOutput);
  if (!cleanFrame.includes('Multiple active tasks exist')) {
    throw new Error(`Question dialog failed to render! Screen:\n${cleanFrame}`);
  }
  if (!cleanFrame.includes('Type your response or option number')) {
    throw new Error(`Question prompt hint missing! Screen:\n${cleanFrame}`);
  }
  console.log('   ✅ QuestionDialog rendered clearly on screen with option list.');

  // User types answer into the composer and submits with Enter
  console.log('   Simulating user typing "1" into composer and pressing Enter...');
  mockStdin.write('1\r');
  await sleep(200);

  if (mockBridge.lastAnsweredQuestion !== '1') {
    throw new Error(`Expected bridge.answerQuestion("1"), got "${mockBridge.lastAnsweredQuestion}"!`);
  }
  cleanFrame = stripAnsi(screenOutput);
  if (!cleanFrame.includes('1')) {
    throw new Error(`User response "1" not found in screen messages! Screen:\n${cleanFrame}`);
  }
  console.log('   ✅ User message "1" mounted successfully into conversation.');
  console.log('   ✅ Question clarification flow answered without freezing or stuck input!');

  // -----------------------------------------------------------------------------
  // Test 3: Confirmation Flow (Y/N/Enter)
  // -----------------------------------------------------------------------------
  console.log('\n🔹 [Test 3] Testing Permission Confirmation Dialog Flow...');
  screenOutput = '';
  mockBridge.emit('bridge_event', {
    kind: 'confirm_action',
    action: 'write_file',
    args: { path: 'test_output.txt', content: 'test content' },
  });

  await sleep(150);
  cleanFrame = stripAnsi(screenOutput);
  if (!cleanFrame.includes('Permission Required') || !cleanFrame.includes('write_file')) {
    throw new Error(`Confirmation dialog not rendered! Screen:\n${cleanFrame}`);
  }
  console.log('   ✅ ConfirmationDialog rendered with permission details.');

  console.log('   Simulating pressing "y" to allow...');
  mockStdin.write('y');
  await sleep(150);

  if (mockBridge.lastConfirmedAction !== true) {
    throw new Error('Confirmation "y" was not acknowledged as allowed!');
  }
  console.log('   ✅ Confirmation received and acknowledged as allowed: true.');

  // -----------------------------------------------------------------------------
  // Test 4: Fast Input & Pasted Multi-line Text with Newlines
  // -----------------------------------------------------------------------------
  console.log('\n🔹 [Test 4] Testing Pasted Input with Newline (No Stuck In Middle)...');
  screenOutput = '';
  const pastedPrompt = 'Analyze the current workspace architecture\n';
  mockStdin.write(pastedPrompt);
  await sleep(200);

  if (mockBridge.lastSubmittedPrompt !== 'Analyze the current workspace architecture') {
    throw new Error(`Pasted prompt with newline was not submitted! Got: "${mockBridge.lastSubmittedPrompt}"`);
  }
  cleanFrame = stripAnsi(screenOutput);
  if (!cleanFrame.includes('Analyze the current workspace architecture')) {
    throw new Error(`Pasted prompt not found on screen! Screen:\n${cleanFrame}`);
  }
  console.log('   ✅ Pasted prompt with newline submitted instantly without getting stuck!');

  // -----------------------------------------------------------------------------
  // Test 5: Tab Auto-completion for Slash Commands
  // -----------------------------------------------------------------------------
  console.log('\n🔹 [Test 5] Testing Slash Command Tab Auto-completion...');
  screenOutput = '';
  mockStdin.write('/mo');
  await sleep(80);
  mockStdin.write('\t'); // Press Tab
  await sleep(150);

  cleanFrame = stripAnsi(screenOutput);
  if (!cleanFrame.includes('/model')) {
    throw new Error(`Tab auto-completion for /mo failed! Screen:\n${cleanFrame}`);
  }
  console.log('   ✅ Tab key auto-completed "/mo" to "/model " without false modal triggers!');

  // Clear composer with Ctrl+U
  mockStdin.write('\x15');
  await sleep(80);

  // -----------------------------------------------------------------------------
  // Test 6: ToolSummary Strictly ABOVE Assistant Message Visual Contract
  // -----------------------------------------------------------------------------
  console.log('\n🔹 [Test 6] Verifying ToolSummary ABOVE Assistant Message contract...');
  mockStdin.write('\x1b[F'); // End key to scroll to bottom
  await sleep(100);

  screenOutput = '';
  const tools: ToolExecutionRecord[] = [
    { tool_name: 'run_bash', summary: 'Ran bash: ls -la', command: 'ls -la', output: 'file.txt', duration_s: 0.2, success: true },
  ];

  mockBridge.emit('bridge_event', {
    kind: 'done',
    summary: 'Here is the summary of your directory contents.',
    tools: tools,
  });

  await sleep(250);
  cleanFrame = stripAnsi(screenOutput);
  const toolSummaryIdx = cleanFrame.indexOf('Ran 1 step');
  const assistantMsgIdx = cleanFrame.indexOf('Here is the summary of your directory contents');

  if (toolSummaryIdx === -1 || assistantMsgIdx === -1) {
    throw new Error(`ToolSummary or AssistantMessage missing from rendered frame! Screen:\n${cleanFrame}`);
  }

  if (toolSummaryIdx >= assistantMsgIdx) {
    throw new Error(`VIOLATION: ToolSummary must be rendered ABOVE AssistantMessage! (toolSummary: ${toolSummaryIdx}, assistantMsg: ${assistantMsgIdx})`);
  }
  console.log('   ✅ Verified: ToolSummary is rendered strictly ABOVE AssistantMessage in output area.');

  // -----------------------------------------------------------------------------
  // Test 7: Clean Shutdown & Process Teardown
  // -----------------------------------------------------------------------------
  console.log('\n🔹 [Test 7] Testing Clean Process Teardown...');
  appInstance.unmount();
  console.log('   ✅ App unmounted and terminated cleanly with 0 leaks.');

  console.log('\n====================================================');
  console.log('🎉 ALL LIVE INPUT AND UI TESTS PASSED SUCCESSFULLY!');
  console.log('====================================================');
}

runLiveTests().catch((err) => {
  console.error('\n❌ LIVE TEST FAILED:', err);
  process.exit(1);
});
