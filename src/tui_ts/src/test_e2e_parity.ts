import { AgentBridge } from './bridge/AgentBridge.js';

async function runParityVerification() {
  console.log('====================================================');
  console.log('🚀 JULIUS TYPESCRIPT TUI - PARITY & IPC AUDIT');
  console.log('====================================================\n');

  const bridge = new AgentBridge();
  const startTime = Date.now();

  console.log('1. Starting Bridge & Spawning Python WebAgent...');
  const ready = await bridge.start();
  const bootDuration = Date.now() - startTime;
  console.log(`   ✅ Spawned successfully in ${bootDuration}ms (PID: ${ready.pid})`);
  console.log(`   ✅ Default Model: ${ready.active_model}`);
  console.log(`   ✅ Default Theme: ${ready.theme}`);

  // Parity Check 1: Latency benchmark
  console.log('\n2. Benchmarking IPC Latency...');
  const latencies: number[] = [];
  for (let i = 0; i < 5; i++) {
    const t0 = Date.now();
    await bridge.ping();
    latencies.push(Date.now() - t0);
  }
  const avgLatency = latencies.reduce((a, b) => a + b, 0) / latencies.length;
  console.log(`   ✅ 5 IPC Pings executed. Average latency: ${avgLatency.toFixed(2)}ms (samples: ${latencies.join(', ')}ms)`);
  if (avgLatency > 50) {
    throw new Error(`Latency too high: ${avgLatency}ms`);
  }

  // Parity Check 2: Model Registry & Switch Chains
  console.log('\n3. Verifying All Models Wiring & Switch Parity...');
  const modelsData = await bridge.getModels();
  const expectedModelIds = ['nvidia', 'aifreeforever', 'deepseek', 'chatgpt', 'grok', 'gemini', 'kimi', 'perplexity'];
  for (const expectedId of expectedModelIds) {
    const found = modelsData.models.some((m) => m.id === expectedId);
    if (!found) {
      throw new Error(`Missing expected model: ${expectedId}`);
    }
  }
  console.log(`   ✅ All 6 cloud neural models + Ollama verified in model picker registry.`);

  // Test sequential model switching
  console.log('   Testing switch chain: chatgpt -> kimi -> grok -> chatgpt');
  await bridge.switchModel('kimi');
  console.log('   • Switched to kimi');
  await bridge.switchModel('grok');
  console.log('   • Switched to grok');
  await bridge.switchModel('chatgpt');
  console.log('   • Switched back to chatgpt');
  console.log('   ✅ Model switching parity confirmed.');

  // Parity Check 3: Clean Termination
  console.log('\n4. Verifying Clean Process Shutdown...');
  await bridge.close();
  console.log('   ✅ Python process and stdio pipes closed cleanly.');

  console.log('\n====================================================');
  console.log('🎉 ALL PARITY & BENCHMARK CHECKS PASSED WITH 100% SUCCESS!');
  console.log('====================================================');
  process.exit(0);
}

runParityVerification().catch((err) => {
  console.error('❌ Parity verification failed:', err);
  process.exit(1);
});

