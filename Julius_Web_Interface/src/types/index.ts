export type DeviceMode = 'desktop' | 'ios' | 'android' | 'matrix';

export type DeviceOrientation = 'portrait' | 'landscape';

export type MessageRole = 'user' | 'assistant' | 'system';

export interface ToolSummaryData {
  stepsCount: number;
  executionTimeSec: number;
  toolName: string;
  status: 'success' | 'running' | 'failed';
  actions?: string[];
}

export interface ThinkingStep {
  title: string;
  durationMs: number;
  detail: string;
}

export interface ThinkingTrace {
  isExpanded: boolean;
  steps: ThinkingStep[];
  summary: string;
  rawThought?: string;
  totalTimeSec?: number;
}

export interface WidgetData {
  id: string;
  type: string;
  title: string;
  htmlContent: string;
  height?: number;
}

export interface CitationSource {
  id: number;
  title: string;
  url: string;
  snippet?: string;
}

export interface ChatMessage {
  id: string;
  role: MessageRole;
  text: string;
  timestamp: string;
  toolSummary?: ToolSummaryData;
  thinking?: ThinkingTrace;
  widget?: WidgetData;
  citations?: CitationSource[];
}

export type ActiveApp = 
  | 'chat'
  | 'terminal'
  | 'do-list-where'
  | 'i-want-ui'
  | 'thinking-panel'
  | 'apk-manager'
  | 'firmware-p200'
  | 'font-studio';

export interface SystemTelemetry {
  cpuUsage: number;
  ramUsage: string;
  emmcStorage: string;
  wifiConnected: boolean;
  backendOnline: boolean;
  activeTasksCount: number;
  adbRootActive: boolean;
  hardwareRotation: number;
}

export interface AppDescriptor {
  id: ActiveApp;
  name: string;
  category: string;
  icon: string;
  badge?: string;
  description: string;
}

