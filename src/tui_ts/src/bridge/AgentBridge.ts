import { EventEmitter } from 'node:events';
import { spawn, type ChildProcess } from 'node:child_process';
import { createInterface, type Interface as ReadlineInterface } from 'node:readline';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { existsSync } from 'node:fs';
import type {
  // Import or destructure parameter JuliusBridgeEvent
  JuliusBridgeEvent,
  // Import or destructure parameter ModelOption
  ModelOption,
  // Import or destructure parameter IPCReadyPayload
  IPCReadyPayload,
  // Import or destructure parameter IPCPromptFinishedPayload
  IPCPromptFinishedPayload,
  IPCSystemReportPayload,
} from '../types.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

export interface AgentBridgeOptions {
  pythonPath?: string;
  scriptPath?: string;
  workspaceDir?: string;
  initialModel?: string;
}

export declare interface AgentBridge {
  on(event: 'ready', listener: (payload: IPCReadyPayload) => void): this;
  on(event: 'bridge_event', listener: (event: JuliusBridgeEvent) => void): this;
  on(event: 'status_update', listener: (status: string) => void): this;
  on(event: 'model_switched', listener: (model: string) => void): this;
  on(event: 'models_list', listener: (data: { models: ModelOption[]; active_model: string }) => void): this;
  on(event: 'prompt_finished', listener: (payload: IPCPromptFinishedPayload) => void): this;
  on(event: 'confirmation_ack', listener: (data: { allow: boolean }) => void): this;
  on(event: 'question_ack', listener: (data: { answer: string }) => void): this;
  on(event: 'action_cancelled', listener: () => void): this;
  on(event: 'pong', listener: (timestamp: number) => void): this;
  on(event: 'system_report', listener: (payload: IPCSystemReportPayload) => void): this;
  on(event: 'session_cleared', listener: () => void): this;
  on(event: 'error', listener: (err: Error) => void): this;
  on(event: 'close', listener: (code: number | null) => void): this;
}

export class AgentBridge extends EventEmitter {
  private proc: ChildProcess | null = null;
  private rl: ReadlineInterface | null = null;
  private isReady = false;
  private readyPromise: Promise<IPCReadyPayload>;
  private readyResolver!: (payload: IPCReadyPayload) => void;
  private options: AgentBridgeOptions;

  constructor(options: AgentBridgeOptions = {}) {
    super();
    this.options = options;
    this.readyPromise = new Promise((res) => {
      this.readyResolver = res;
    });
  }

  private resolvePythonExecutable(): string {
    if (this.options.pythonPath && existsSync(this.options.pythonPath)) {
      return this.options.pythonPath;
    }

    // Try explicit venv paths
    const candidates = [
      resolve(process.cwd(), '.venv/bin/python'),
      resolve(__dirname, '../../../../.venv/bin/python'),
      resolve(process.cwd(), 'Julius/.venv/bin/python'),
      process.env.VIRTUAL_ENV ? resolve(process.env.VIRTUAL_ENV, 'bin/python') : '',
      '/opt/homebrew/bin/python3',
      'python3',
    ].filter(Boolean);

    for (const cand of candidates) {
      if (existsSync(cand)) {
        return cand;
      }
    }

    return 'python3';
  }

  private resolveScriptPath(): string {
    if (this.options.scriptPath && existsSync(this.options.scriptPath)) {
      return this.options.scriptPath;
    }

    const defaultScript = resolve(__dirname, '../../../bridge/agent_ipc.py');
    return defaultScript;
  }

  public async start(): Promise<IPCReadyPayload> {
    const pythonExe = this.resolvePythonExecutable();
    const script = this.resolveScriptPath();
    const workspace = this.options.workspaceDir || '.';

    const args = [script, '--workspace', workspace];
    if (this.options.initialModel) {
      args.push('--model', this.options.initialModel);
    }

    this.proc = spawn(pythonExe, args, {
      stdio: ['pipe', 'pipe', 'pipe'],
      env: {
        ...process.env,
        PYTHONUNBUFFERED: '1',
      },
    });

    if (!this.proc.stdout || !this.proc.stdin) {
      throw new Error('Failed to spawn Python process with stdio pipes');
    }

    this.rl = createInterface({
      input: this.proc.stdout,
      terminal: false,
    });

    this.rl.on('line', (line: string) => {
      const trimmed = line.trim();
      if (!trimmed) return;

      try {
        const msg = JSON.parse(trimmed);
        this.handleIncomingMessage(msg);
      } catch (err) {
        // Silently skip non-JSON or malformed lines
      }
    });

    this.proc.stderr?.on('data', (chunk: Buffer) => {
      // Optional debug logging can be wired here
    });

    this.proc.on('error', (err: Error) => {
      this.emit('error', err);
    });

    this.proc.on('close', (code: number | null) => {
      this.isReady = false;
      this.proc = null;
      this.emit('close', code);
    });

    return this.readyPromise;
  }

  private handleIncomingMessage(msg: Record<string, unknown>): void {
    const type = msg.type as string;

    switch (type) {
      case 'ready': {
        this.isReady = true;
        const payload: IPCReadyPayload = {
          active_model: (msg.active_model as string) || '',
          theme: (msg.theme as string) || 'dark',
          models: (msg.models as ModelOption[]) || [],
          pid: (msg.pid as number) || 0,
        };
        this.readyResolver(payload);
        this.emit('ready', payload);
        break;
      }

      case 'bridge_event': {
        const event = msg.event as JuliusBridgeEvent;
        this.emit('bridge_event', event);
        break;
      }

      case 'status_update': {
        const status = (msg.status as string) || '';
        this.emit('status_update', status);
        break;
      }

      case 'model_switched': {
        const model = (msg.model as string) || '';
        this.emit('model_switched', model);
        break;
      }

      case 'models_list': {
        this.emit('models_list', {
          models: (msg.models as ModelOption[]) || [],
          active_model: (msg.active_model as string) || '',
        });
        break;
      }

      case 'prompt_finished': {
        const payload: IPCPromptFinishedPayload = {
          success: Boolean(msg.success),
          cancelled: Boolean(msg.cancelled),
          error: (msg.error as string) || undefined,
        };
        this.emit('prompt_finished', payload);
        break;
      }

      case 'confirmation_ack': {
        this.emit('confirmation_ack', { allow: Boolean(msg.allow) });
        break;
      }

      case 'question_ack': {
        this.emit('question_ack', { answer: String(msg.answer || '') });
        break;
      }

      case 'action_cancelled': {
        this.emit('action_cancelled');
        break;
      }

      case 'pong': {
        this.emit('pong', Number(msg.timestamp || Date.now()));
        break;
      }

      case 'system_report': {
        this.emit('system_report', {
          command: String(msg.command || ''),
          report: String(msg.report || ''),
          toast: msg.toast ? String(msg.toast) : undefined,
        });
        break;
      }

      case 'session_cleared': {
        this.emit('session_cleared');
        break;
      }

      default:
        // Ignore unhandled event types gracefully
        break;
    }
  }

  public sendCommand(cmd: Record<string, unknown>): void {
    if (!this.proc || !this.proc.stdin || !this.proc.stdin.writable) {
      throw new Error('IPC Bridge is not connected to Python backend');
    }

    const payload = JSON.stringify(cmd) + '\n';
    this.proc.stdin.write(payload);
  }

  public submitPrompt(prompt: string): void {
    this.sendCommand({ action: 'submit_prompt', prompt });
  }

  public confirmAction(allow: boolean): void {
    this.sendCommand({ action: 'confirm_action', allow });
  }

  public answerQuestion(answer: string): void {
    this.sendCommand({ action: 'answer_question', answer });
  }

  public clearSession(): void {
    this.sendCommand({ action: 'clear' });
  }

  public undo(): void {
    this.sendCommand({ action: 'undo' });
  }

  public doctor(): void {
    this.sendCommand({ action: 'doctor' });
  }

  public context(): void {
    this.sendCommand({ action: 'context' });
  }

  public cost(): void {
    this.sendCommand({ action: 'cost' });
  }

  public compact(): void {
    this.sendCommand({ action: 'compact' });
  }

  public switchModel(model: string): Promise<string> {
    return new Promise((resolve) => {
      const handler = (newModel: string) => {
        this.off('model_switched', handler);
        resolve(newModel);
      };
      this.on('model_switched', handler);
      this.sendCommand({ action: 'switch_model', model });
    });
  }

  public getModels(): Promise<{ models: ModelOption[]; active_model: string }> {
    return new Promise((resolve) => {
      const handler = (data: { models: ModelOption[]; active_model: string }) => {
        this.off('models_list', handler);
        resolve(data);
      };
      this.on('models_list', handler);
      this.sendCommand({ action: 'get_models' });
    });
  }

  public ping(): Promise<number> {
    return new Promise((resolve) => {
      const handler = (timestamp: number) => {
        this.off('pong', handler);
        resolve(timestamp);
      };
      this.on('pong', handler);
      this.sendCommand({ action: 'ping' });
    });
  }

  public cancelAction(): void {
    this.sendCommand({ action: 'cancel_action' });
  }

  public async close(): Promise<void> {
    if (this.proc && this.proc.stdin && this.proc.stdin.writable) {
      try {
        this.sendCommand({ action: 'exit' });
      } catch {
        // Ignore write failures during exit
      }
    }

    if (this.rl) {
      this.rl.close();
      this.rl = null;
    }

    if (this.proc) {
      this.proc.kill('SIGTERM');
      this.proc = null;
    }

    this.isReady = false;
  }
}

