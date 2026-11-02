import type { DeviceMode, DeviceOrientation, ActiveApp, ChatMessage, SystemTelemetry } from '../types/index.js';
import { soundHaptics } from './soundHaptics.js';
import { juliusApi } from './juliusApi.js';

export interface AppState {
  deviceMode: DeviceMode;
  deviceOrientation: DeviceOrientation;
  activeApp: ActiveApp;
  messages: ChatMessage[];
  telemetry: SystemTelemetry;
  isGenerating: boolean;
  currentStepMessage: string;
  isThinkingDrawerOpen: boolean;
  isTerminalOpen: boolean;
  soundEnabled: boolean;
  hardwareRotation: number;
}

type Listener = (state: AppState) => void;

class JuliusStore {
  private state: AppState;
  private listeners: Set<Listener> = new Set();

  constructor() {
    this.state = {
      deviceMode: 'desktop',
      deviceOrientation: 'portrait',
      activeApp: 'chat',
      isGenerating: false,
      currentStepMessage: '',
      isThinkingDrawerOpen: false,
      isTerminalOpen: false,
      soundEnabled: soundHaptics.isEnabled(),
      hardwareRotation: 0,
      telemetry: {
        cpuUsage: 14,
        ramUsage: '482 MB / 1024 MB',
        emmcStorage: '3.2 GB / 8.0 GB',
        wifiConnected: true,
        backendOnline: false,
        activeTasksCount: 2,
        adbRootActive: true,
        hardwareRotation: 0,
      },
      messages: [
        {
          id: 'msg-welcome',
          role: 'assistant',
          text: `Welcome to the **Julius Universal Web Experience**.\n\n` +
            `Everything is interconnected across your devices:\n` +
            `- **Desktop Studio**: Full-screen reasoning canvas & terminal.\n` +
            `- **Mobile iOS**: Apple haptic tactile feedback, Dynamic Island, and PWA.\n` +
            `- **Android / Julius OS**: Rockchip P200 tablet shell, root ADB gateway, and direct APK bridge.\n` +
            `- **Connected Apps**: *Do List Where*, *I Want UI*, and *Font Studio*.\n\n` +
            `Type a request below or switch device modes in the top toolbar to explore!`,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          toolSummary: {
            toolName: 'Julius_System_Bootstrap',
            stepsCount: 4,
            executionTimeSec: 0.84,
            status: 'success',
            actions: ['Load Design Tokens', 'Initialize Audio Synthesizer', 'Connect Device Mesh', 'Bind IFrame Sandbox']
          },
          thinking: {
            isExpanded: false,
            summary: 'Initialized Julius core runtime across web, iOS, and APK channels.',
            steps: [
              { title: 'Theme Tokens Initialized', durationMs: 140, detail: 'Applied #121214 dark palette and #006A25 green accent' },
              { title: 'Audio Context Prepared', durationMs: 90, detail: 'Synthesizer tuned for keyboard and button taps' },
              { title: 'Device Mesh Bound', durationMs: 180, detail: 'Synchronized Desktop, iOS, and Android P200 frames' }
            ]
          }
        }
      ]
    };

    // Periodic telemetry ping
    setInterval(() => {
      this.refreshTelemetry();
    }, 4000);
  }

  public getState(): AppState {
    return this.state;
  }

  public subscribe(listener: Listener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private emit(): void {
    this.listeners.forEach(fn => fn(this.state));
  }

  public setDeviceMode(mode: DeviceMode): void {
    soundHaptics.playTap();
    this.state.deviceMode = mode;
    this.emit();
  }

  public setDeviceOrientation(orientation: DeviceOrientation): void {
    soundHaptics.playTap();
    this.state.deviceOrientation = orientation;
    this.state.hardwareRotation = orientation === 'landscape' ? 90 : 0;
    this.state.telemetry.hardwareRotation = this.state.hardwareRotation;
    this.emit();
  }

  public setActiveApp(app: ActiveApp): void {
    soundHaptics.playTap();
    this.state.activeApp = app;
    this.emit();
  }

  public toggleSound(): boolean {
    const enabled = soundHaptics.toggleSound();
    this.state.soundEnabled = enabled;
    this.emit();
    return enabled;
  }

  public toggleThinkingDrawer(): void {
    soundHaptics.playTap();
    this.state.isThinkingDrawerOpen = !this.state.isThinkingDrawerOpen;
    this.emit();
  }

  public toggleTerminal(): void {
    soundHaptics.playTap();
    this.state.isTerminalOpen = !this.state.isTerminalOpen;
    this.emit();
  }

  public toggleThinkingExpansion(messageId: string): void {
    soundHaptics.playTap();
    const msg = this.state.messages.find(m => m.id === messageId);
    if (msg && msg.thinking) {
      msg.thinking.isExpanded = !msg.thinking.isExpanded;
      this.emit();
    }
  }

  public async sendMessage(query: string): Promise<void> {
    const trimmed = query.trim();
    if (!trimmed || this.state.isGenerating) return;

    soundHaptics.playKey();

    // 1. Add User Message
    const userMsg: ChatMessage = {
      id: `usr-${Date.now()}`,
      role: 'user',
      text: trimmed,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    };

    this.state.messages.push(userMsg);
    this.state.isGenerating = true;
    this.state.currentStepMessage = 'Julius is thinking...';
    this.emit();

    // 2. Call API / Resilient Agent Service
    try {
      const result = await juliusApi.sendQuery(trimmed, (step) => {
        this.state.currentStepMessage = step;
        this.emit();
      });

      // 3. Add Assistant Message
      const assistantMsg: ChatMessage = {
        id: `ast-${Date.now()}`,
        role: 'assistant',
        text: result.answerText,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        toolSummary: result.toolSummary,
        thinking: result.thinking,
        widget: result.widget,
      };

      this.state.messages.push(assistantMsg);
      soundHaptics.playComplete();
    } catch (err) {
      this.state.messages.push({
        id: `err-${Date.now()}`,
        role: 'assistant',
        text: `Encountered an issue processing query. Please check local connectivity.`,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      });
    } finally {
      this.state.isGenerating = false;
      this.state.currentStepMessage = '';
      this.emit();
    }
  }

  private async refreshTelemetry(): Promise<void> {
    const isOnline = await juliusApi.checkHealth();
    const activeTasks = await juliusApi.getActiveTasks();

    // Slight realistic jitter for CPU load
    const cpu = Math.floor(12 + Math.random() * 8);

    this.state.telemetry = {
      ...this.state.telemetry,
      backendOnline: isOnline,
      activeTasksCount: activeTasks,
      cpuUsage: cpu,
    };
    this.emit();
  }
}

export const stateStore = new JuliusStore();

