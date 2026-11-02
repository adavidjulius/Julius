import { stateStore, type AppState } from './services/stateStore.js';
import { soundHaptics } from './services/soundHaptics.js';
import { juliusApi } from './services/juliusApi.js';
import type { DeviceMode, ActiveApp } from './types/index.js';

// Global interface for window binding
declare global {
  interface Window {
    juliusApp: {
      setDeviceMode: (mode: DeviceMode) => void;
      switchApp: (app: ActiveApp) => void;
      toggleSound: () => boolean;
      sendPrompt: (prompt: string) => Promise<void>;
    };
  }
}

class JuliusWebPrerequisites {
  private rootEl: HTMLElement;

  constructor() {
    const el = document.getElementById('app-root');
    if (!el) {
      throw new Error('Root element #app-root not found');
    }
    this.rootEl = el;

    this.registerGlobalHooks();
    this.setupWidgetIframeBridge();

    // Subscribe to state updates
    stateStore.subscribe((state) => this.render(state));

    // Initial render
    this.render(stateStore.getState());
  }

  private registerGlobalHooks(): void {
    window.juliusApp = {
      setDeviceMode: (mode: DeviceMode) => {
        stateStore.setDeviceMode(mode);
      },
      switchApp: (app: ActiveApp) => {
        stateStore.setActiveApp(app);
      },
      toggleSound: () => {
        return stateStore.toggleSound();
      },
      sendPrompt: async (prompt: string) => {
        await stateStore.sendMessage(prompt);
      }
    };
  }

  private setupWidgetIframeBridge(): void {
    window.addEventListener('message', (event) => {
      const data = event.data;
      if (!data || typeof data !== 'object') return;

      if (data.type === 'julius:sendPrompt' && typeof data.text === 'string') {
        const text = data.text.trim();
        if (text) {
          stateStore.sendMessage(text);
        }
      }
    });
  }

  private render(state: AppState): void {
    const isOnline = state.telemetry.backendOnline;

    this.rootEl.innerHTML = `
      <div class="prerequisite-ready-stage">
        <div class="prerequisite-card">
          <div class="prerequisite-badge">
            <span>✦</span>
            <span>PREREQUISITE SCAFFOLD READY</span>
          </div>
          
          <h1 class="prerequisite-title">Julius Web Interface</h1>
          
          <p class="prerequisite-desc">
            The foundational architecture, skill contracts, and hardware bridges are established.
            Ready for your custom design prompt!
          </p>

          <div class="prerequisite-grid">
            <div class="prerequisite-item">
              <div class="prerequisite-item-title">Design System & Tokens</div>
              <div class="prerequisite-item-status">✓ #121214, #c8b896, #006A25</div>
            </div>

            <div class="prerequisite-item">
              <div class="prerequisite-item-title">Dual-Mode API Bridge</div>
              <div class="prerequisite-item-status">✓ ${isOnline ? 'LIVE (Port 8000)' : 'RESILIENT CORE READY'}</div>
            </div>

            <div class="prerequisite-item">
              <div class="prerequisite-item-title">Cross-Device Foundations</div>
              <div class="prerequisite-item-status">✓ Web · iOS PWA · Android P200 APK</div>
            </div>

            <div class="prerequisite-item">
              <div class="prerequisite-item-title">Skill Contract</div>
              <div class="prerequisite-item-status">✓ .agents/skills/julius-web-interface</div>
            </div>
          </div>
        </div>
      </div>
    `;
  }
}

// Bootstrap once DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => new JuliusWebPrerequisites());
} else {
  new JuliusWebPrerequisites();
}
