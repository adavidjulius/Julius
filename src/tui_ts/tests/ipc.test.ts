import { AgentBridge } from '../src/bridge/AgentBridge.js';

async function testIPC() {
  console.log('🧪 Starting Julius Python <-> TypeScript IPC Bridge Test...');
  const bridge = new AgentBridge();

  const startMs = Date.now();
  const readyPayload = await bridge.start();
  console.log(`✅ Bridge ready in ${Date.now() - startMs}ms!`);
  console.log(`   - Active Model: ${readyPayload.active_model}`);
  console.log(`   - Theme: ${readyPayload.theme}`);
  console.log(`   - Available Models count: ${readyPayload.models.length}`);
  console.log(`   - Backend PID: ${readyPayload.pid}`);

  // Test 1: Ping / Pong Latency
  console.log('\n⏱️ Testing IPC Latency (Ping/Pong)...');
  const pingStart = Date.now();
  const pongTime = await bridge.ping();
  const latency = Date.now() - pingStart;
  console.log(`✅ Pong received! Round-trip latency: ${latency}ms (timestamp: ${pongTime})`);

  // Test 2: Get Models List
  console.log('\n📋 Testing Model Listing...');
  const modelsData = await bridge.getModels();
  console.log(`✅ Models list retrieved (${modelsData.models.length} models, active: ${modelsData.active_model})`);
  for (const m of modelsData.models) {
    console.log(`   • ${m.name.padEnd(20)} (${m.id})`);
  }

  // Test 3: Model Switching
  console.log('\n🔄 Testing Dynamic Model Switch (to "kimi")...');
  const switched1 = await bridge.switchModel('kimi');
  console.log(`✅ Model successfully switched to: ${switched1}`);

  console.log('\n🔄 Testing Dynamic Model Switch (back to "chatgpt")...');
  const switched2 = await bridge.switchModel('chatgpt');
  console.log(`✅ Model successfully switched to: ${switched2}`);

  // Test 4: Clean Termination
  console.log('\n🛑 Closing IPC Bridge...');
  await bridge.close();
  console.log('✅ IPC Bridge closed cleanly with zero errors.');
  console.log('\n🎉 ALL PHASE 1 IPC BRIDGE TESTS PASSED!');
  process.exit(0);
}

testIPC().catch((err) => {
  console.error('❌ IPC Test failed:', err);
  process.exit(1);
});

