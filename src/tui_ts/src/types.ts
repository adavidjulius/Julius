/**
 * Core type definitions for Julius TypeScript TUI.
 * Exactly matches Python models to guarantee 100% interoperability.
 */

export interface SquircleRadii {
  readonly xs: string;
  readonly sm: string;
  readonly md: string;
  readonly lg: string;
  readonly xl: string;
  readonly pill: string;
}

export interface ThemeTokens {
  readonly name: string;
  readonly bg: string;
  readonly surface: string;
  readonly raised: string;
  readonly text: string;
  readonly text_dim: string;
  readonly text_faint: string;
  readonly accent: string;
  readonly success: string;
  readonly warning: string;
  readonly error: string;
  readonly border_idle: string;
  readonly border_focused: string;
  readonly border_subtle?: string;
  readonly scrim: string;
  readonly is_dark: boolean;
  readonly is_no_color: boolean;
  readonly brand_gold: string;
  readonly brand_crimson: string;
  readonly brand_obsidian: string;
  readonly brand_electric_green: string;
  readonly brand_green_deep: string;
  readonly brand_green_glow: string;
  readonly brand_slate_badge: string;
  readonly radius: SquircleRadii;
}

export interface ToolExecutionRecord {
  tool_name: string;
  summary: string;
  duration_s: number;
  success: boolean;
  command: string;
  args: Record<string, unknown>;
  output: string;
}

export interface FileUndoRecord {
  path: string;
  pre_edit_content: string | null;
  existed_before: boolean;
}

export interface WorkingStep {
  type: 'thought' | 'action' | 'result';
  text: string;
  command?: string;
  output?: string;
  timestamp: number;
}

export interface ActiveThinkingState {
  label: string;
  fullThought: string;
  thoughts: string[];
  workingSteps: WorkingStep[];
  isRunning: boolean;
  durationS?: number;
}

export interface MessageRecord {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: number;
  tools?: ToolExecutionRecord[];
  thoughts?: string[];
  fullThought?: string;
  workingSteps?: WorkingStep[];
  thoughtDurationS?: number;
}

export type ReasoningEffort = 'low' | 'medium' | 'high' | 'xhigh' | 'max';
export type PermissionModeType = 'bypass' | 'normal' | 'plan' | 'strict';
export type AppMode = 'auto' | 'plan' | 'edit' | 'accept' | 'manual';

export interface ContextGaugeData {
  current_tokens: number;
  max_tokens: number;
  percentage: number;
  is_warm: boolean;
  cache_read?: number;
  cache_created?: number;
}

export interface QuestionPreviewOption {
  label: string;
  description: string;
  preview?: string;
}

export interface JuliusSessionState {
  active_model: string;
  effort_level?: ReasoningEffort;
  permission_mode?: PermissionModeType;
  theme_name: string;
  token_count: number;
  context_gauge?: ContextGaugeData;
  start_time: number;
  current_step: number;
  max_steps: number;
  is_working: boolean;
  status_message: string;
  modified_files: string[];
  undo_stack: FileUndoRecord[];
  current_turn_tools: ToolExecutionRecord[];
  history: [role: string, content: string][];
  last_assistant_answer: string;
}

export interface ModelOption {
  id: string;
  name: string;
  desc: string;
}

export type JuliusEventType =
  | 'thought'
  | 'action_scheduled'
  | 'tool_completed'
  | 'stream_chunk'
  | 'stream_clear'
  | 'stream_end'
  | 'done'
  | 'converse'
  | 'error'
  | 'ask_user_question'
  | 'confirm_action'
  | 'status'
  | 'step_start'
  | 'finished_failure'
  | 'plan_approval'
  | 'whatsapp_status'
  | 'whatsapp_message'
  | 'whatsapp_approval';

export interface JuliusBridgeEvent {
  kind: JuliusEventType;
  thought?: string;
  action?: string;
  args?: Record<string, unknown>;
  command?: string;
  tool_name?: string;
  output?: string;
  success?: boolean;
  chunk?: string;
  summary?: string;
  message?: string;
  tools?: Record<string, unknown>[];
  duration_s?: number;
  question?: string;
  options?: string[];
  previewOptions?: QuestionPreviewOption[];
  multiSelect?: boolean;
  status?: string;
  plan?: string;
  data?: unknown;
}

export interface IPCReadyPayload {
  active_model: string;
  theme: string;
  models: ModelOption[];
  pid: number;
}

export interface IPCPromptFinishedPayload {
  success: boolean;
  cancelled?: boolean;
  error?: string;
}

export interface IPCSystemReportPayload {
  command: string;
  report: string;
  toast?: string;
}

