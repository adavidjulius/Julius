import React, { useState, useEffect, useRef } from 'react';
import { Box, Text, useInput, useApp, useStdin } from 'ink';
import type {
  // Import or destructure parameter MessageRecord
  MessageRecord,
  // Import or destructure parameter ToolExecutionRecord
  ToolExecutionRecord,
  // Import or destructure parameter ModelOption
  ModelOption,
  // Import or destructure parameter JuliusBridgeEvent
  JuliusBridgeEvent,
  // Import or destructure parameter WorkingStep
  WorkingStep,
  // Import or destructure parameter ActiveThinkingState
  ActiveThinkingState,
  AppMode,
} from './types.js';
import { DARK_THEME, LIGHT_THEME } from './theme/tokens.js';
import { AgentBridge } from './bridge/AgentBridge.js';
import { UserMessage } from './components/UserMessage.js';
import { AssistantMessage } from './components/AssistantMessage.js';
import { ToolSummary, filterRealTools } from './components/ToolSummary.js';
import { ThinkingDot, formatSummary, sanitizeThought } from './components/ThinkingDot.js';
import { Composer } from './components/Composer.js';
import { CommandSuggestions } from './components/CommandSuggestions.js';
import { StatusLine } from './components/StatusLine.js';
import { WelcomeView } from './components/WelcomeView.js';
import { VirtualConversationView } from './components/VirtualConversationView.js';
import { ConfirmationDialog } from './components/ConfirmationDialog.js';
import { QuestionDialog } from './components/QuestionDialog.js';
import { ToastNotification } from './components/ToastNotification.js';
import { ModelPickerModal } from './components/modals/ModelPickerModal.js';
import { HelpModal } from './components/modals/HelpModal.js';
import { DiffReviewModal } from './components/modals/DiffReviewModal.js';
import { ActiveActionModal, type ActiveActionDetails } from './components/modals/ActiveActionModal.js';
import { copyToClipboard } from './utils/clipboard.js';
import { recordShortcutUse } from './utils/hintManager.js';

export interface AppProps {
  bridge?: AgentBridge;
  initialPrompt?: string;
  initialModel?: string;
}

type ActiveModalType = 'model' | 'help' | 'diff' | 'action' | null;

export const App: React.FC<AppProps> = ({
  bridge: injectedBridge,
  // Import or destructure parameter initialPrompt
  initialPrompt,
  // Import or destructure parameter initialModel
  initialModel,
}) => {
  const { exit } = useApp();
  const { stdin, isRawModeSupported } = useStdin();
  const [isDarkTheme, setIsDarkTheme] = useState(true);
  const theme = isDarkTheme ? DARK_THEME : LIGHT_THEME;

  // Dynamic Terminal Window Dimensions
  const [dimensions, setDimensions] = useState({
    columns: process.stdout.columns || 80,
    rows: process.stdout.rows || 24,
  });

  useEffect(() => {
    const handleResize = () => {
      setDimensions({
        columns: process.stdout.columns || 80,
        rows: process.stdout.rows || 24,
      });
    };
    process.stdout.on('resize', handleResize);
    return () => {
      process.stdout.off('resize', handleResize);
    };
  }, []);

  const [bridge, setBridge] = useState<AgentBridge | null>(injectedBridge || null);
  const [messages, setMessages] = useState<MessageRecord[]>([]);
  const [activeThinking, setActiveThinking] = useState<ActiveThinkingState | null>(null);
  const [activeActionDetails, setActiveActionDetails] = useState<ActiveActionDetails | null>(null);
  const [streamingAnswer, setStreamingAnswer] = useState<string>('');
  const [currentTurnTools, setCurrentTurnTools] = useState<ToolExecutionRecord[]>([]);
  const [query, setQuery] = useState('');
  const [runningAction, setRunningAction] = useState('');
  const [activeModel, setActiveModel] = useState<string>(initialModel || 'nvidia/nemotron-3-ultra-550b-a55b');
  const [availableModels, setAvailableModels] = useState<ModelOption[]>([
    {
      id: 'nvidia/nemotron-3-ultra-550b-a55b',
      name: 'Nemotron 3 Ultra 550B',
      desc: 'NVIDIA NIM Free · 550B Flagship Reasoning & Tools (1,000 Credits)',
    },
    {
      id: 'nvidia/nemotron-3.5-lightning-30b-a3b',
      name: 'Nemotron 3.5 Lightning 30B',
      desc: 'NVIDIA NIM Free · Fast 30B Tool Calling Specialist',
    },
    {
      id: 'claude-3-5-sonnet-20241022',
      name: 'Claude 3.5 Sonnet',
      desc: 'Anthropic · State-of-the-Art Coding & Architecture',
    },
    {
      id: 'claude-3-5-haiku-20241022',
      name: 'Claude 3.5 Haiku',
      desc: 'Anthropic · Ultra-Fast Lightweight Intelligence',
    },
    {
      id: 'gpt-4o',
      name: 'GPT-4o',
      desc: 'OpenAI · Flagship Omnimodal Reasoning',
    },
    {
      id: 'o3-mini',
      name: 'o3-mini',
      desc: 'OpenAI · Deep Reasoning STEM & Code Specialist',
    },
    {
      id: 'deepseek-chat',
      name: 'DeepSeek V3',
      desc: 'DeepSeek · High-Performance Low-Cost Coding',
    },
    {
      id: 'deepseek-reasoner',
      name: 'DeepSeek R1',
      desc: 'DeepSeek · Open Reasoning & Math Model',
    },
    {
      id: 'gemini-2.0-flash',
      name: 'Gemini 2.0 Flash',
      desc: 'Google AI · Ultra-Fast Multimodal Intelligence',
    },
    {
      id: 'ollama',
      name: 'Local Ollama',
      desc: 'Local LAN · 100% Private Offline Inference',
    },
  ]);
  const [isDimmed, setIsDimmed] = useState(false);
  const [appMode, setAppMode] = useState<AppMode>('auto');
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const [isThinkingExpanded, setIsThinkingExpanded] = useState(false);
  const [isToolsExpanded, setIsToolsExpanded] = useState(false);
  const [activeModal, setActiveModal] = useState<ActiveModalType>(null);
  const [isComposerFocused, setIsComposerFocused] = useState(true);
  const [scrollOffset, setScrollOffset] = useState(0);

  // Modal / Prompt Overlays
  const [pendingConfirmation, setPendingConfirmation] = useState<{
    action: string;
    args: Record<string, unknown>;
  } | null>(null);
  const [pendingQuestion, setPendingQuestion] = useState<{
    question: string;
    options: string[];
    previewOptions?: import('./types.js').QuestionPreviewOption[];
  } | null>(null);

  const lastAssistantAnswerRef = useRef<string>('');
  const streamingAnswerRef = useRef<string>('');
  const toastTimerRef = useRef<NodeJS.Timeout | null>(null);
  const lastWheelTimeRef = useRef<number>(0);

  const showToast = (msg: string) => {
    if (toastTimerRef.current) {
      clearTimeout(toastTimerRef.current);
    }
    setToastMessage(msg);
    toastTimerRef.current = setTimeout(() => {
      setToastMessage(null);
    }, 1500);
  };

  // Initialize bridge if not provided
  useEffect(() => {
    const activeBridge = injectedBridge || new AgentBridge({ initialModel });
    setBridge(activeBridge);

    activeBridge.on('ready', (payload) => {
      setActiveModel(payload.active_model);
      setAvailableModels(payload.models);
    });

    activeBridge.on('status_update', (status) => {
      setRunningAction(status);
      if (status && status.trim()) {
        const isThinkStatus = status.toLowerCase().startsWith('thinking');
        if (isThinkStatus) {
          setActiveThinking((prev) => ({
            label: status,
            fullThought: prev?.fullThought || '',
            thoughts: prev?.thoughts || [],
            workingSteps: prev?.workingSteps || [],
            isRunning: true,
            durationS: prev?.durationS,
          }));
        }
        // Action status strictly updates Active Action details
        setActiveActionDetails((prev) => (prev ? { ...prev, command: status } : {
          action: 'action',
          command: status,
          startTime: Date.now(),
          is_running: true,
        }));
      }
    });

    activeBridge.on('model_switched', (newModel) => {
      setActiveModel(newModel);
      showToast(`Model switched to ${newModel}`);
    });

    activeBridge.on('mode_switched', (newMode) => {
      setAppMode(newMode as AppMode);
      showToast(`Mode switched to: ${newMode.toUpperCase()}`);
    });

    activeBridge.on('bridge_event', (event: JuliusBridgeEvent) => {
      const { kind } = event;

      if (kind === 'thought') {
        const thoughtText = event.thought || '';
        const lower = thoughtText.toLowerCase().trim();
        // Only accept authentic API reasoning thoughts — completely reject tool/action execution noise
        const isActionNoise = (
          lower.startsWith('executing') ||
          lower.startsWith('running') ||
          lower.startsWith('executed') ||
          lower.startsWith('(no thought') ||
          lower.startsWith('tool_call') ||
          lower === 'none'
        );
        if (thoughtText && !isActionNoise) {
          const dynamicLabel = formatSummary(thoughtText);
          const cleanThought = sanitizeThought(thoughtText);
          if (cleanThought) {
            setRunningAction('');
            setActiveThinking((prev) => {
              const prevThoughts = prev?.thoughts || [];
              const lastThought = prevThoughts.length > 0 ? prevThoughts[prevThoughts.length - 1] : '';

              // If the new thought chunk is an extension of the last thought in this turn, update in-place
              let updatedThoughts: string[];
              if (!lastThought) {
                updatedThoughts = [cleanThought];
              } else if (cleanThought.startsWith(lastThought) || lastThought.startsWith(cleanThought)) {
                updatedThoughts = [...prevThoughts.slice(0, -1), cleanThought];
              } else {
                updatedThoughts = [...prevThoughts.slice(0, -1), `${lastThought} ${cleanThought}`];
              }

              const newStep: WorkingStep = {
                type: 'thought',
                text: cleanThought,
                timestamp: Date.now(),
              };
              return {
                label: dynamicLabel,
                fullThought: cleanThought,
                thoughts: updatedThoughts,
                workingSteps: [...(prev?.workingSteps || []), newStep],
                isRunning: true,
                durationS: prev?.durationS,
              };
            });
          }
        }
      } else if (kind === 'action_scheduled') {
        const actionName = (event.action || '').toLowerCase();
        // Ignore internal protocol completion / conversational actions so they never schedule as active tasks
        if (['done', 'converse', 'finish', 'ask_human', 'none', 'chat', 'message'].includes(actionName)) {
          return;
        }
        const cmd = event.command || event.action || 'Executing action';
        setRunningAction(cmd);
        // Update active action details for Active Action column / modal (Ctrl+I)
        setActiveActionDetails({
          action: event.action || 'action',
          command: cmd,
          startTime: Date.now(),
          is_running: true,
        });
        streamingAnswerRef.current = '';
        setStreamingAnswer('');
      } else if (kind === 'tool_completed') {
        const toolName = event.tool_name || event.action || 'tool';
        const toolOutput = event.output || '';
        const isSuccess = event.success !== false;
        // Update active action details for Active Action column / modal (Ctrl+I)
        setActiveActionDetails((prev) =>
          prev
            ? {
              ...prev,
              output: (prev.output ? prev.output + '\n' : '') + toolOutput,
              is_running: false,
              endTime: Date.now(),
              duration: prev.startTime ? (Date.now() - prev.startTime) / 1000 : undefined,
            }
            : {
              action: toolName,
              command: event.command || toolName,
              startTime: Date.now(),
              output: toolOutput,
              is_running: false,
              endTime: Date.now(),
            }
        );
      } else if (kind === 'stream_clear') {
        streamingAnswerRef.current = '';
        setStreamingAnswer('');
      } else if (kind === 'step_start') {
        if (streamingAnswerRef.current) {
          streamingAnswerRef.current = '';
          setStreamingAnswer('');
        }
      } else if (kind === 'stream_chunk') {
        const chunk = event.chunk || '';
        const cleanChunk = chunk
          .replace(/<think>[\s\S]*?<\/think>/gi, '')
          .replace(/<\/?(?:think|thought|reasoning)>/gi, '');
        const trimmedChunk = cleanChunk.trim();
        const isJsonToolCall = Boolean(
          trimmedChunk.startsWith('{') &&
          (trimmedChunk.includes('"tool"') || trimmedChunk.includes('"action"') || trimmedChunk.includes('"function"'))
        );
        if (cleanChunk && !isJsonToolCall) {
          streamingAnswerRef.current += cleanChunk;
          setStreamingAnswer(streamingAnswerRef.current);
          setActiveThinking((prev) => (prev ? { ...prev, isRunning: false } : null));
          // Preserve active action details for post-action inspection
          setActiveActionDetails((prev) => (prev ? {
            ...prev,
            is_running: false,
            endTime: prev.endTime || Date.now(),
            duration: prev.duration !== undefined ? prev.duration : (prev.startTime ? (Date.now() - prev.startTime) / 1000 : undefined),
          } : null));
          setRunningAction('');
        }
      } else if (kind === 'confirm_action') {
        setPendingConfirmation({
          action: event.action || 'action',
          args: event.args || {},
        });
      } else if (kind === 'ask_user_question') {
        setPendingQuestion({
          question: event.question || '',
          options: event.options || [],
          previewOptions: event.previewOptions,
        });
      } else if (kind === 'done' || kind === 'converse') {
        const rawFinal = (kind === 'done' ? event.summary : event.message) || streamingAnswerRef.current;
        const cleanFinal = (rawFinal || '')
          .replace(/<think>[\s\S]*?<\/think>/gi, '')
          .replace(/<thought>[\s\S]*?<\/thought>/gi, '')
          .replace(/<reasoning>[\s\S]*?<\/reasoning>/gi, '')
          .replace(/<\/?(?:think|thought|reasoning)>/gi, '')
          .trim();
        const finalText = cleanFinal;
        const isJsonToolCall = Boolean(
          (finalText.startsWith('{') || finalText.startsWith('json{')) &&
          (finalText.includes('"tool"') || finalText.includes('"action"') || finalText.includes('"function"') || finalText.includes('"actions"'))
        );
        const tools = (event.tools as unknown as ToolExecutionRecord[]) || currentTurnTools;

        const displayContent = !isJsonToolCall && finalText
          ? finalText
          : (tools.length > 0
              ? `I've completed ${tools.length} step(s) and verified the results.`
              : (finalText && !finalText.startsWith('{') ? finalText : 'Task completed successfully.'));

        if (displayContent) {
          lastAssistantAnswerRef.current = displayContent;
          setMessages((prev) => [
            ...prev,
            {
              id: `ast_${Date.now()}`,
              role: 'assistant',
              content: displayContent,
              timestamp: Date.now(),
              tools: tools.length > 0 ? [...tools] : undefined,
              thoughts: activeThinking?.thoughts,
              fullThought: activeThinking?.fullThought,
              workingSteps: activeThinking?.workingSteps,
              thoughtDurationS: activeThinking?.durationS,
            },
          ]);
          setScrollOffset(0);
        }

        streamingAnswerRef.current = '';
        setStreamingAnswer('');
        setActiveThinking(null);
        // Preserve last action details as completed for inspection with final frozen duration
        setActiveActionDetails((prev) => (prev ? {
          ...prev,
          is_running: false,
          endTime: prev.endTime || Date.now(),
          duration: prev.duration !== undefined ? prev.duration : (prev.startTime ? (Date.now() - prev.startTime) / 1000 : undefined),
        } : null));
        setCurrentTurnTools([]);
        setRunningAction('');
        setPendingConfirmation(null);
        setPendingQuestion(null);
      } else if (kind === 'plan_approval') {
        const planText = event.plan || 'Implementation plan generated.';
        setPendingQuestion({
          question: `Plan Approval Requested:\n\n${planText}`,
          options: [
            'Approve & Execute Plan',
            'Request Plan Revisions',
            'Cancel Plan',
          ],
        });
      } else if (kind === 'status') {
        const statusMsg = event.status || event.message || '';
        if (statusMsg) {
          showToast(statusMsg);
        }
      } else if (kind === 'finished_failure') {
        const failureSummary = event.summary || 'Task completed with issues.';
        showToast(failureSummary);
      } else if (kind === 'error') {
        const errMsg = event.message || 'An error occurred';
        setMessages((prev) => [
          ...prev,
          {
            id: `err_${Date.now()}`,
            role: 'assistant',
            content: `Error: ${errMsg}`,
            timestamp: Date.now(),
          },
        ]);
        setActiveThinking(null);
        // Preserve last action details as completed for inspection
        setActiveActionDetails((prev) => (prev ? { ...prev, is_running: false } : null));
        setStreamingAnswer('');
        setRunningAction('');
      }
    });

    activeBridge.on('prompt_finished', (payload?: { success?: boolean; cancelled?: boolean; error?: string }) => {
      setRunningAction('');
      setActiveThinking(null);
      setStreamingAnswer('');
      // Preserve active action details for post-action inspection
      setActiveActionDetails((prev) => (prev ? { ...prev, is_running: false } : null));
      if (payload?.cancelled) {
        showToast('Task cancelled');
      }
    });

    activeBridge.on('system_report', (data: { command: string; report: string; toast?: string }) => {
      setMessages((prev) => [
        ...prev,
        {
          id: `sys_${Date.now()}`,
          role: 'assistant',
          content: data.report,
          timestamp: Date.now(),
        },
      ]);
      if (data.toast) {
        showToast(data.toast);
      }
    });

    activeBridge.on('session_cleared', () => {
      showToast('Started fresh chat session');
    });

    if (!injectedBridge) {
      activeBridge.start().catch(() => { });
    }

    return () => {
      if (!injectedBridge) {
        activeBridge.close().catch(() => { });
      }
    };
  }, [injectedBridge, initialModel]);

  // Listen for raw function keys and mouse clicks on stdin
  useEffect(() => {
    if (!stdin) return;
    const handleRawStdin = (chunk: Buffer | string) => {
      const str = chunk.toString();
      // F2 terminal sequences across xterm / linux / macOS Terminal: \x1bOQ, \x1b[12~, \x1b[Q
      if (str === '\x1bOQ' || str === '\x1b[12~' || str === '\x1b[Q') {
        if (!activeModal) setActiveModal('model');
        return;
      }

      // F3 terminal sequences for Active Action inspector: \x1bOR, \x1b[13~, \x1b[1;2R, \x1b[13;2~
      if (str === '\x1bOR' || str === '\x1b[13~' || str === '\x1b[1;2R' || str === '\x1b[13;2~') {
        setActiveModal((prev) => (prev === 'action' ? null : 'action'));
        return;
      }

      // Capture mouse click and wheel sequences (\x1b[<btn;col;rowM or m)
      const mouseMatch = str.match(/(?:\x1b)?\[<(\d+);(\d+);(\d+)([Mm])/);
      if (mouseMatch) {
        const btn = parseInt(mouseMatch[1] || '0', 10);
        const row = parseInt(mouseMatch[3] || '0', 10);
        const type = mouseMatch[4]; // 'M' is button press

        // Mouse Wheel UP: button 64 or modifier variants (64 + 4, 8, etc.)
        if (btn === 64 || ((btn & 64) === 64 && (btn & 1) === 0)) {
          setScrollOffset((prev) => prev + 2);
          return;
        }

        // Mouse Wheel DOWN: button 65 or modifier variants
        if (btn === 65 || ((btn & 64) === 64 && (btn & 1) === 1)) {
          setScrollOffset((prev) => Math.max(0, prev - 2));
          return;
        }

        // Only handle explicit button click (btn === 0)
        if (type === 'M' && btn === 0) {
          if (!activeModal) {
            if (row >= dimensions.rows - 2 && (runningAction || activeActionDetails)) {
              // Clicked on bottom status row while action is running or completed: open Active Action Modal
              setActiveModal('action');
            } else if (row >= dimensions.rows - 5) {
              setIsComposerFocused(true);
            } else {
              setIsComposerFocused(true);
            }
          }
        }
        return;
      }

      // Traditional XTerm mouse sequences (\x1b[M followed by 3 bytes)
      if (str.startsWith('\x1b[M') && str.length >= 6) {
        const cb = str.charCodeAt(3) - 32;
        if (cb === 64 || cb === 96) {
          setScrollOffset((prev) => prev + 2);
          return;
        }
        if (cb === 65 || cb === 97) {
          setScrollOffset((prev) => Math.max(0, prev - 2));
          return;
        }
      }
    };
    stdin.on('data', handleRawStdin);
    return () => {
      stdin.removeListener('data', handleRawStdin);
    };
  }, [stdin, activeModal, dimensions.rows]);

  // Global Keybindings, Shortcuts & Input Management
  useInput((input, key) => {
    // Immediately drop any mouse reporting codes or escape noise
    if (input && (/(\x1b)?\[<\d+;\d+;\d+[Mm]/.test(input) || /^\x1b\[M/.test(input))) {
      return;
    }

    // If a modal is active, Esc dismisses it and returns focus to composer
    if (activeModal) {
      if (key.escape) {
        setActiveModal(null);
        setIsComposerFocused(true);
      }
      return;
    }

    // Emergency action & task cancellation: Escape or Ctrl+C breaks out of stuck actions instantly
    const isCtrlC = Boolean(key.ctrl && (input?.toLowerCase() === 'c' || input === '\x03'));
    if ((key.escape || isCtrlC) && (runningAction || activeThinking)) {
      bridge?.cancelAction();
      setRunningAction('');
      setActiveThinking(null);
      setActiveActionDetails((prev) => (prev ? { ...prev, is_running: false } : null));
      showToast('Action cancelled');
      return;
    }

    // 1. Single-key / Quick Confirmation: Y/A/Enter to allow, N/D/Esc to deny
    if (pendingConfirmation) {
      const lower = (input || '').toLowerCase();
      if (lower === 'y' || lower === 'a' || key.return) {
        bridge?.confirmAction(true);
        setPendingConfirmation(null);
        return;
      }
      if (lower === 'n' || lower === 'd' || key.escape) {
        bridge?.confirmAction(false);
        setPendingConfirmation(null);
        return;
      }
    }

    // 2. F2: Model Picker Modal (supports terminal F2 escape sequences)
    if (input === '\x1bOQ' || input === '\x1b[12~' || (key as unknown as Record<string, boolean>).f2) {
      recordShortcutUse('f2_model');
      setActiveModal('model');
      return;
    }

    // 3. Ctrl+D: Diff Review Modal
    if (input === '\x04' || (key.ctrl && (input.toLowerCase() === 'd' || input === '\x04'))) {
      setActiveModal('diff');
      return;
    }

    // Shift+Tab: Cycle operating modes (Auto -> Plan -> Edit -> Accept -> Manual)
    const isShiftTab = Boolean(
      (key.shift && ((key as any).tab || input === '\t' || input === '\x09')) ||
      input === '\x1b[Z' ||
      input === '\x1b[27;2;9~' ||
      input === '\x1b[9;2u'
    );
    if (isShiftTab) {
      const MODES: AppMode[] = ['auto', 'plan', 'edit', 'accept', 'manual'];
      const MODE_DESCS: Record<AppMode, string> = {
        auto: 'Auto (Autonomous)',
        plan: 'Plan (Read-only Planning)',
        edit: 'Edit (Code Development)',
        accept: 'Accept (Full Access · No Restrictions)',
        manual: 'Manual (Ask Confirmation)',
      };
      setAppMode((prev: AppMode) => {
        const nextIdx = (MODES.indexOf(prev) + 1) % MODES.length;
        const nextMode = MODES[nextIdx];
        bridge?.setMode(nextMode);
        showToast(`Mode: ${MODE_DESCS[nextMode]}`);
        return nextMode;
      });
      return;
    }

    // 4. Ctrl+I / Tab / F3: Action Inspector Modal
    const isCtrlI = !isShiftTab && Boolean(
      input === '\x09' ||
      input === '\t' ||
      (key as any).tab ||
      (key.ctrl && (input?.toLowerCase() === 'i' || input === '\x09')) ||
      (key.ctrl && (key as any).tab) ||
      input === '\x1bOR' ||
      input === '\x1b[13~' ||
      (key as any).f3
    );
    if (isCtrlI) {
      // If currently typing a slash command, let Tab complete the command instead of opening Action modal
      if (query.startsWith('/') && !query.includes(' ')) {
        return;
      }
      recordShortcutUse('ctrl_i');
      setActiveModal((prev) => (prev === 'action' ? null : 'action'));
      return;
    }

    // 5. Ctrl+Y: Copy last assistant answer to clipboard
    if (input === '\x19' || (key.ctrl && (input.toLowerCase() === 'y' || input === '\x19'))) {
      recordShortcutUse('ctrl_y');
      const textToCopy = lastAssistantAnswerRef.current;
      if (textToCopy) {
        if (copyToClipboard(textToCopy)) {
          showToast(`Copied ${textToCopy.length} characters`);
        } else {
          showToast('Failed to copy to clipboard');
        }
      } else {
        showToast('Nothing to copy yet');
      }
      return;
    }

    // 6. Ctrl+T: Toggle thinking expansion
    if (input === '\x14' || (key.ctrl && (input.toLowerCase() === 't' || input === '\x14'))) {
      recordShortcutUse('ctrl_t');
      setIsThinkingExpanded((prev) => !prev);
      return;
    }

    // 7. Ctrl+O: Toggle tool summary expansion
    if (input === '\x0f' || (key.ctrl && (input.toLowerCase() === 'o' || input === '\x0f'))) {
      recordShortcutUse('ctrl_o');
      setIsToolsExpanded((prev) => !prev);
      return;
    }

    // 8. Ctrl+L: Clear screen & redraw terminal buffer cleanly
    if (input === '\x0c' || (key.ctrl && (input.toLowerCase() === 'l' || input === '\x0c'))) {
      if (process.stdout.isTTY) {
        process.stdout.write('\x1b[H\x1b[2J');
      }
      setDimensions({
        columns: process.stdout.columns || 80,
        rows: process.stdout.rows || 24,
      });
      return;
    }

    // 9. Viewport Conversation Scrolling: PageUp, PageDown, Home, End, Ctrl+U, Shift+Up/Down
    if (key.pageUp || input === '\x1b[5~' || input === '\x1b[5;2~') {
      setScrollOffset((prev) => prev + 4);
      return;
    }
    if (key.pageDown || input === '\x1b[6~' || input === '\x1b[6;2~') {
      setScrollOffset((prev) => Math.max(0, prev - 4));
      return;
    }
    if (input === '\x1b[H' || input === '\x1b[1~' || (key as unknown as Record<string, boolean>).home) {
      setScrollOffset(9999);
      return;
    }
    if (input === '\x1b[F' || input === '\x1b[4~' || (key as unknown as Record<string, boolean>).end) {
      setScrollOffset(0);
      return;
    }
    if (input === '\x15' || (key.ctrl && input.toLowerCase() === 'u')) {
      setScrollOffset((prev) => prev + 4);
      return;
    }
    if (key.shift && key.upArrow) {
      setScrollOffset((prev) => prev + 2);
      return;
    }
    if (key.shift && key.downArrow) {
      setScrollOffset((prev) => Math.max(0, prev - 2));
      return;
    }

    // 10. Esc: Cancel running task or dismiss overlays
    if (key.escape) {
      if (pendingConfirmation) {
        bridge?.confirmAction(false);
        setPendingConfirmation(null);
      } else if (pendingQuestion) {
        bridge?.answerQuestion('User cancelled.');
        setPendingQuestion(null);
      } else if (runningAction || activeThinking) {
        bridge?.cancelAction();
        showToast('Action cancelled');
      }
      return;
    }
  }, { isActive: !activeModal });

  const handlePromptSubmit = async (prompt: string) => {
    const trimmed = prompt.trim();
    if (!trimmed) return;
    setScrollOffset(0);

    // Check for client-side slash commands (with smart prefix and two-word matching)
    if (trimmed.startsWith('/')) {
      const spaceIdx = trimmed.indexOf(' ');
      const rawCmd = (spaceIdx === -1 ? trimmed : trimmed.slice(0, spaceIdx)).toLowerCase();
      const arg = spaceIdx === -1 ? '' : trimmed.slice(spaceIdx + 1).trim();

      // Helper to match exact command or prefix of at least 2 characters (e.g. /he -> /help, /pl -> /plan)
      const matchesCmd = (target: string, aliases: string[] = []): boolean => {
        if (rawCmd === target || aliases.includes(rawCmd)) return true;
        if (rawCmd.length >= 2 && target.startsWith(rawCmd)) return true;
        return aliases.some((a) => a.length >= 2 && a.startsWith(rawCmd));
      };

      if (matchesCmd('/help', ['/h', '/?'])) {
        setActiveModal('help');
        return;
      }

      if (matchesCmd('/model', ['/m', '/mo', '/mod'])) {
        if (arg && bridge) {
          await bridge.switchModel(arg);
        } else {
          setActiveModal('model');
        }
        return;
      }

      if (matchesCmd('/diff', ['/d', '/dif', '/changes'])) {
        setActiveModal('diff');
        return;
      }

      if (matchesCmd('/think', ['/t', '/th'])) {
        setIsThinkingExpanded((prev) => !prev);
        return;
      }

      if (matchesCmd('/action', ['/a', '/inspect', '/ps'])) {
        if (!arg) {
          setActiveModal('action');
          return;
        }
      }

      if (matchesCmd('/clear', ['/c', '/new', '/ne', '/reset'])) {
        setMessages([]);
        setStreamingAnswer('');
        setActiveThinking(null);
        setActiveActionDetails(null);
        setRunningAction('');
        bridge?.clearSession();
        showToast('Started fresh chat session');
        return;
      }

      if (matchesCmd('/mode')) {
        const MODES: AppMode[] = ['auto', 'plan', 'edit', 'accept', 'manual'];
        const target = (arg || '').toLowerCase().trim() as AppMode;
        if (MODES.includes(target)) {
          setAppMode(target);
          bridge?.setMode(target);
          showToast(`Mode: ${target.toUpperCase()}`);
        } else {
          setAppMode((prev: AppMode) => {
            const nextIdx = (MODES.indexOf(prev) + 1) % MODES.length;
            const nextMode = MODES[nextIdx];
            bridge?.setMode(nextMode);
            showToast(`Mode: ${nextMode.toUpperCase()}`);
            return nextMode;
          });
        }
        return;
      }

      if (matchesCmd('/auto')) {
        setAppMode('auto');
        bridge?.setMode('auto');
        showToast('Mode: AUTO (Autonomous execution)');
        return;
      }

      if (matchesCmd('/accept')) {
        setAppMode('accept');
        bridge?.setMode('accept');
        showToast('Mode: ACCEPT (Full unrestricted access)');
        return;
      }

      if (matchesCmd('/manual')) {
        setAppMode('manual');
        bridge?.setMode('manual');
        showToast('Mode: MANUAL (Ask confirmation)');
        return;
      }

      if (matchesCmd('/edit')) {
        setAppMode('edit');
        bridge?.setMode('edit');
        showToast('Mode: EDIT (Code development)');
        return;
      }

      if (matchesCmd('/plan', ['/p', '/pl'])) {
        if (!arg) {
          setAppMode('plan');
          bridge?.setMode('plan');
          showToast('Mode: PLAN (Read-only planning)');
          return;
        }
        // Execute prompt in plan mode
        const userMsg: MessageRecord = {
          id: `usr_${Date.now()}`,
          role: 'user',
          content: `/plan ${arg}`,
          timestamp: Date.now(),
        };
        setMessages((prev) => [...prev, userMsg]);
        setActiveThinking({
          label: 'Planning',
          fullThought: '',
          thoughts: [],
          workingSteps: [],
          isRunning: true,
        });
        setActiveActionDetails(null);
        setStreamingAnswer('');
        bridge?.submitPrompt(`/plan ${arg}`);
        return;
      }

      if (matchesCmd('/act')) {
        if (!arg) {
          showToast('Usage: /act <task description>');
          return;
        }
        const userMsg: MessageRecord = {
          id: `usr_${Date.now()}`,
          role: 'user',
          content: arg,
          timestamp: Date.now(),
        };
        setMessages((prev) => [...prev, userMsg]);
        setActiveThinking({
          label: 'Thinking',
          fullThought: '',
          thoughts: [],
          workingSteps: [],
          isRunning: true,
        });
        setActiveActionDetails(null);
        setStreamingAnswer('');
        bridge?.submitPrompt(arg);
        return;
      }

      if (matchesCmd('/undo', ['/u'])) {
        bridge?.undo();
        return;
      }

      if (matchesCmd('/doctor', ['/doc'])) {
        bridge?.doctor();
        return;
      }

      if (matchesCmd('/context', ['/ctx', '/con'])) {
        bridge?.context();
        return;
      }

      if (matchesCmd('/cost')) {
        bridge?.cost();
        return;
      }

      if (matchesCmd('/compact', ['/comp'])) {
        bridge?.compact();
        return;
      }

      if (matchesCmd('/status', ['/vitals', '/vital', '/stat'])) {
        bridge?.sendCommand({ action: 'vitals' });
        return;
      }

      if (matchesCmd('/alerts', ['/alert', '/proactive'])) {
        bridge?.sendCommand({ action: 'alerts' });
        return;
      }

      if (matchesCmd('/theme')) {
        setIsDarkTheme((prev) => !prev);
        showToast('Theme toggled');
        return;
      }

      if (matchesCmd('/exit', ['/quit', '/q', '/ex'])) {
        await bridge?.close();
        exit();
        return;
      }
    }

    // If awaiting question clarification, send as answer
    if (pendingQuestion) {
      setMessages((prev) => [
        ...prev,
        {
          id: `usr_${Date.now()}`,
          role: 'user',
          content: trimmed,
          timestamp: Date.now(),
        },
      ]);
      bridge?.answerQuestion(trimmed);
      setPendingQuestion(null);
      return;
    }

    // Mount user message
    const userMsg: MessageRecord = {
      id: `usr_${Date.now()}`,
      role: 'user',
      content: trimmed,
      timestamp: Date.now(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setActiveThinking({
      label: 'Thinking',
      fullThought: '',
      thoughts: [],
      workingSteps: [],
      isRunning: true,
    });
    setActiveActionDetails(null);
    setStreamingAnswer('');

    // Dispatch to Python backend via IPC bridge
    bridge?.submitPrompt(trimmed);
  };

  // Guard: Window too small overlay (< 60 columns or < 16 rows)
  if (dimensions.columns < 60 || dimensions.rows < 16) {
    return (
      <Box
        flexDirection="column"
        width="100%"
        height={dimensions.rows}
        alignItems="center"
        justifyContent="center"
      >
        <Text bold color={theme.accent}>
          Please enlarge your terminal window to continue with Julius.
        </Text>
        <Box marginTop={1}>
          <Text color={theme.text_faint}>
            Current: {dimensions.columns}×{dimensions.rows} (Minimum required: 60×16)
          </Text>
        </Box>
      </Box>
    );
  }

  const hasStarted = messages.length > 0 || Boolean(activeThinking) || Boolean(streamingAnswer);
  const pad = dimensions.columns < 80 ? 1 : (dimensions.columns < 120 ? 1 : (dimensions.columns >= 160 ? 4 : 2));
  const hMargin = dimensions.columns < 80 ? 1 : (dimensions.columns < 110 ? 2 : 4);
  // Indent all output (agent response, thinking panel, tool summary) by 1 tab space (4 columns)
  // to clearly define Question (Input) vs Answer (Output)
  const outputMargin = hMargin + 4;

  return (
    <Box
      flexDirection="column"
      width={dimensions.columns}
      height={dimensions.rows}
      paddingLeft={pad}
      paddingRight={pad}
      justifyContent="space-between"
    >
      {/* 1. Main Viewport Area: Takes all available height above bottom composer */}
      <Box
        flexDirection="column"
        flexGrow={1}
        justifyContent="flex-start"
      >
        {/* Welcome wordmark banner shown above modals */}
        {activeModal && (
          <WelcomeView
            showSubtitle={false}
            theme={theme}
            columns={dimensions.columns}
            rows={dimensions.rows}
          />
        )}

        {/* Floating Toast Notification */}
        <ToastNotification message={toastMessage} theme={theme} />

        {/* Modals & Overlays: Rendered STRICTLY AFTER (BELOW) THE JULIUS BANNER */}
        {activeModal === 'model' && (
          <Box flexDirection="column" alignItems="center" marginTop={0} marginBottom={1}>
            <ModelPickerModal
              models={availableModels}
              activeModel={activeModel}
              columns={dimensions.columns}
              rows={dimensions.rows}
              onSelect={async (modelId) => {
                setActiveModal(null);
                setIsComposerFocused(true);
                if (bridge) {
                  await bridge.switchModel(modelId);
                }
              }}
              onClose={() => {
                setActiveModal(null);
                setIsComposerFocused(true);
              }}
              theme={theme}
            />
          </Box>
        )}

        {activeModal === 'action' && (
          <Box flexDirection="column" alignItems="center" marginTop={0} marginBottom={1} flexShrink={0}>
            <ActiveActionModal
              activeAction={activeActionDetails}
              runningAction={runningAction}
              columns={dimensions.columns}
              rows={dimensions.rows}
              onCancelAction={() => {
                bridge?.cancelAction();
                setActiveActionDetails((prev) => (prev ? { ...prev, is_running: false } : null));
                setRunningAction('');
                showToast('Action cancelled');
              }}
              onClose={() => {
                setActiveModal(null);
                setIsComposerFocused(true);
              }}
              theme={theme}
            />
          </Box>
        )}

        {activeModal === 'help' && (
          <Box flexDirection="column" alignItems="center" marginTop={0} marginBottom={1}>
            <HelpModal
              columns={dimensions.columns}
              rows={dimensions.rows}
              onClose={() => {
                setActiveModal(null);
                setIsComposerFocused(true);
              }}
              theme={theme}
            />
          </Box>
        )}

        {activeModal === 'diff' && (
          <Box flexDirection="column" alignItems="center" marginTop={0} marginBottom={1}>
            <DiffReviewModal
              columns={dimensions.columns}
              rows={dimensions.rows}
              onClose={() => {
                setActiveModal(null);
                setIsComposerFocused(true);
              }}
              theme={theme}
            />
          </Box>
        )}

        {/* Conversation Stream: Displayed when no modal is open */}
        {!activeModal && (
          <Box flexDirection="column" flexGrow={1}>
            {(() => {
              const footerRows = 4 + (query.startsWith('/') && !query.includes(' ') ? 4 : 0);
              const maxViewportRows = Math.max(4, dimensions.rows - footerRows);

              return (
                <>
                  <VirtualConversationView
                    messages={messages}
                    activeThinking={activeThinking}
                    runningAction={runningAction}
                    streamingAnswer={streamingAnswer}
                    currentTurnTools={currentTurnTools}
                    isThinkingExpanded={isThinkingExpanded}
                    isToolsExpanded={isToolsExpanded}
                    onToggleThinking={() => setIsThinkingExpanded((p) => !p)}
                    onToggleTools={() => setIsToolsExpanded((p) => !p)}
                    scrollOffset={scrollOffset}
                    viewportHeight={maxViewportRows}
                    columns={dimensions.columns}
                    theme={theme}
                    horizontalMargin={hMargin}
                    activeModel={activeModel}
                    appMode={appMode}
                  />

                  {/* Floating scroll indicator when user is scrolled up */}
                  {scrollOffset > 0 && (
                    <Box flexDirection="row" justifyContent="center" width="100%" marginTop={0} marginBottom={0}>
                      <Text color={theme.text_faint}>
                        ↓ Scrolled up ({scrollOffset} line{scrollOffset > 1 ? 's' : ''} above bottom · Press End to return) ↓
                      </Text>
                    </Box>
                  )}
                </>
              );
            })()}

            {/* Active Confirmation Dialog */}
            {pendingConfirmation && (
              <ConfirmationDialog
                actionName={pendingConfirmation.action}
                args={pendingConfirmation.args}
                theme={theme}
              />
            )}

            {/* Active Clarification Question Dialog */}
            {pendingQuestion && (
              <QuestionDialog
                question={pendingQuestion.question}
                options={pendingQuestion.options}
                previewOptions={pendingQuestion.previewOptions}
                onSelectOption={(chosen) => {
                  const answer = typeof chosen === 'string' ? chosen : chosen.label;
                  if (bridge) {
                    bridge.sendInput(answer);
                  }
                  setPendingQuestion(null);
                }}
                theme={theme}
                columns={dimensions.columns}
              />
            )}
          </Box>
        )}
      </Box>

      {/* 2. Bottom Anchored Controls (Always resting at the very bottom of the terminal window) */}
      <Box flexDirection="column" flexShrink={0}>
        {/* Suggestions popup directly above Composer */}
        {!activeModal && !pendingConfirmation && !pendingQuestion && <CommandSuggestions query={query} theme={theme} />}

        {/* Composer Input with Julius Brand Book #C8B896 Border when clicked/focused */}
        <Composer
          onSubmit={handlePromptSubmit}
          onChange={(val) => {
            if (scrollOffset > 0) {
              setScrollOffset(0);
            }
            if (val.startsWith('/')) {
              setQuery(val);
            } else if (query) {
              setQuery('');
            }
          }}
          isFocused={isComposerFocused && !activeModal && !pendingConfirmation}
          isWorking={Boolean(activeThinking) || Boolean(streamingAnswer) || Boolean(runningAction)}
          columns={dimensions.columns}
          rows={dimensions.rows}
          placeholder={
            pendingConfirmation
              ? 'Press Y to allow or N to deny...'
              : pendingQuestion
                ? 'Type your answer or option number...'
                : 'Ask Julius anything'
          }
          theme={theme}
        />

        {/* Single-line Status Telemetry (Bottom row with Mode Badge & Shift+Tab hint) */}
        <StatusLine
          appMode={appMode}
          hintText="/ for commands"
          runningText={runningAction}
          isDimmed={isDimmed}
          theme={theme}
        />
      </Box>
    </Box>
  );
};
