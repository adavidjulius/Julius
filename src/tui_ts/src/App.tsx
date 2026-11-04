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
import { ConfirmationDialog } from './components/ConfirmationDialog.js';
import { QuestionDialog } from './components/QuestionDialog.js';
import { ToastNotification } from './components/ToastNotification.js';
import { ModelPickerModal } from './components/modals/ModelPickerModal.js';
import { HelpModal } from './components/modals/HelpModal.js';
import { DiffReviewModal } from './components/modals/DiffReviewModal.js';
import { ActiveActionModal, type ActiveActionDetails } from './components/modals/ActiveActionModal.js';
import { copyToClipboard } from './utils/clipboard.js';

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
  const [activeModel, setActiveModel] = useState<string>(initialModel || 'nvidia');
  const [availableModels, setAvailableModels] = useState<ModelOption[]>([]);
  const [isDimmed, setIsDimmed] = useState(false);
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
  } | null>(null);

  const lastAssistantAnswerRef = useRef<string>('');
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
            setActiveThinking((prev) => {
              const newStep: WorkingStep = {
                type: 'thought',
                text: cleanThought,
                timestamp: Date.now(),
              };
              return {
                label: dynamicLabel,
                fullThought: (prev?.fullThought ? prev.fullThought + '\n\n' : '') + cleanThought,
                thoughts: [...(prev?.thoughts || []), cleanThought],
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
      } else if (kind === 'stream_chunk') {
        const chunk = event.chunk || '';
        const trimmedChunk = chunk.trim();
        const isJsonToolCall = Boolean(
          trimmedChunk.startsWith('{') &&
          (trimmedChunk.includes('"tool"') || trimmedChunk.includes('"action"') || trimmedChunk.includes('"function"'))
        );
        if (chunk && !isJsonToolCall) {
          setStreamingAnswer((prev) => prev + chunk);
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
        });
      } else if (kind === 'done' || kind === 'converse') {
        const rawFinal = (kind === 'done' ? event.summary : event.message) || streamingAnswer;
        const finalText = (rawFinal || '').trim();
        const isJsonToolCall = Boolean(
          finalText.startsWith('{') &&
          (finalText.includes('"tool"') || finalText.includes('"action"') || finalText.includes('"function"'))
        );
        const tools = (event.tools as unknown as ToolExecutionRecord[]) || currentTurnTools;

        if (finalText && !isJsonToolCall) {
          lastAssistantAnswerRef.current = finalText;
          setMessages((prev) => [
            ...prev,
            {
              id: `ast_${Date.now()}`,
              role: 'assistant',
              content: finalText,
              timestamp: Date.now(),
              tools: tools.length > 0 ? [...tools] : undefined,
              thoughts: activeThinking?.thoughts,
              workingSteps: activeThinking?.workingSteps,
              thoughtDurationS: activeThinking?.durationS,
            },
          ]);
        }

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

      // Capture mouse click sequences (\x1b[<0;col;rowM) without letting escape bytes leak into input
      const mouseMatch = str.match(/(?:\x1b)?\[<(\d+);(\d+);(\d+)([Mm])/);
      if (mouseMatch) {
        const btn = parseInt(mouseMatch[1] || '0', 10);
        const row = parseInt(mouseMatch[3] || '0', 10);
        const type = mouseMatch[4]; // 'M' is button press

        // Mouse Wheel Scroll support: 64 = wheel up, 65 = wheel down
        // Damped progressive single-step scroll (at most 1 step every 40ms) for smooth, non-bunchy navigation
        if (btn === 64) {
          const now = Date.now();
          if (now - lastWheelTimeRef.current >= 40) {
            lastWheelTimeRef.current = now;
            setScrollOffset((prev) => prev + 1);
          }
          return;
        }
        if (btn === 65) {
          const now = Date.now();
          if (now - lastWheelTimeRef.current >= 40) {
            lastWheelTimeRef.current = now;
            setScrollOffset((prev) => Math.max(0, prev - 1));
          }
          return;
        }

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
    };
    stdin.on('data', handleRawStdin);
    return () => {
      stdin.removeListener('data', handleRawStdin);
    };
  }, [stdin, activeModal, dimensions.rows]);

  // Global Keybindings, Shortcuts & Input Management
  useInput((input, key) => {
    // Immediately drop any mouse reporting codes or escape noise
    if (input && /(\x1b)?\[<\d+;\d+;\d+[Mm]/.test(input)) {
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

    // 1. Single-key Confirmation: Y/N without needing Enter
    if (pendingConfirmation) {
      const lower = input.toLowerCase();
      if (lower === 'y') {
        bridge?.confirmAction(true);
        setPendingConfirmation(null);
        return;
      }
      if (lower === 'n') {
        bridge?.confirmAction(false);
        setPendingConfirmation(null);
        return;
      }
    }

    // 2. F2: Model Picker Modal (supports terminal F2 escape sequences)
    if (input === '\x1bOQ' || input === '\x1b[12~' || (key as unknown as Record<string, boolean>).f2) {
      setActiveModal('model');
      return;
    }

    // 3. Ctrl+D: Diff Review Modal
    if (input === '\x04' || (key.ctrl && (input.toLowerCase() === 'd' || input === '\x04'))) {
      setActiveModal('diff');
      return;
    }

    // 4. Ctrl+I / Tab / F3: Action Inspector Modal
    const isCtrlI = Boolean(
      input === '\x09' ||
      input === '\t' ||
      (key as any).tab ||
      (key.ctrl && (input.toLowerCase() === 'i' || input === '\x09')) ||
      (key.ctrl && (key as any).tab) ||
      input === '\x1bOR' ||
      input === '\x1b[13~' ||
      (key as any).f3
    );
    if (isCtrlI) {
      setActiveModal((prev) => (prev === 'action' ? null : 'action'));
      return;
    }

    // 5. Ctrl+Y: Copy last assistant answer to clipboard
    if (input === '\x19' || (key.ctrl && (input.toLowerCase() === 'y' || input === '\x19'))) {
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
      setIsThinkingExpanded((prev) => !prev);
      return;
    }

    // 7. Ctrl+O: Toggle tool summary expansion
    if (input === '\x0f' || (key.ctrl && (input.toLowerCase() === 'o' || input === '\x0f'))) {
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

    // 9. Viewport Conversation Scrolling: PageUp, PageDown, Home, End, Ctrl+U, Up/Down arrows
    // Progressive single-step scrolling for smooth viewport movement without jerky leaps
    if (key.pageUp || input === '\x1b[5~' || input === '\x1b[5;2~') {
      setScrollOffset((prev) => prev + 1);
      return;
    }
    if (key.pageDown || input === '\x1b[6~' || input === '\x1b[6;2~') {
      setScrollOffset((prev) => Math.max(0, prev - 1));
      return;
    }
    if (input === '\x1b[H' || input === '\x1b[1~' || (key as unknown as Record<string, boolean>).home) {
      setScrollOffset(999);
      return;
    }
    if (input === '\x1b[F' || input === '\x1b[4~' || (key as unknown as Record<string, boolean>).end) {
      setScrollOffset(0);
      return;
    }
    if (input === '\x15' || (key.ctrl && input.toLowerCase() === 'u')) {
      setScrollOffset((prev) => prev + 2);
      return;
    }
    if (!query && key.upArrow) {
      setScrollOffset((prev) => prev + 1);
      return;
    }
    if (!query && key.downArrow && scrollOffset > 0) {
      setScrollOffset((prev) => Math.max(0, prev - 1));
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

      if (matchesCmd('/plan', ['/p', '/pl'])) {
        if (!arg) {
          showToast('Usage: /plan <task description>');
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
        {/* Welcome wordmark banner ALWAYS at the top */}
        <WelcomeView
          scrolled={hasStarted}
          showSubtitle={!hasStarted && !activeModal}
          theme={theme}
          columns={dimensions.columns}
          rows={dimensions.rows}
        />

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
            {/* Message history: viewport-windowed with true scrolling and overflow protection */}
            {(() => {
              const activeGold = theme.brand_gold || theme.accent;
              const isNarrow = dimensions.columns < 50;
              const isShort = dimensions.rows < 24;
              // Authentic Julius ASCII banner is preserved at top (~8 rows with margins)
              const bannerHeight = isNarrow ? 2 : 8;
              const footerHeight = 5;
              const maxViewportRows = Math.max(4, dimensions.rows - bannerHeight - footerHeight);

              // Indent all output (agent response, thinking panel, tool summary) by 1 tab space (4 columns)
              // to clearly define Question (Input) vs Answer (Output)
              const outputMargin = hMargin + 4;

              // Estimate rendered height of each message with strict pixel-perfect row budgeting
              const estimateTurnLines = (m: MessageRecord): number => {
                let lines = 2; // base marginTop(1) + marginBottom(1)
                if (m.role === 'user') {
                  const contentLen = m.content.length;
                  const innerWidth = Math.max(20, dimensions.columns - 16);
                  const textLines = Math.ceil(contentLen / innerWidth) || 1;
                  // Card contains top border (1) + bottom border (1) + wrapped content text lines
                  return lines + 2 + textLines;
                }
                if (m.tools && filterRealTools(m.tools).length > 0) {
                  lines += 2; // ToolSummary
                }
                const contentLines = m.content.split('\n').length;
                lines += Math.min(contentLines, maxViewportRows - 2);
                return lines;
              };

              const turns = [...messages];
              const turnHeights = turns.map(estimateTurnLines);

              // Clamped scroll offset
              const maxScroll = Math.max(0, turns.length - 1);
              const currentOffset = Math.min(scrollOffset, maxScroll);

              let targetEnd = turns.length - 1 - currentOffset;
              if (targetEnd < 0) targetEnd = 0;

              let targetStart = targetEnd;
              let usedRows = 0;

              // Reserve space for live streaming or active thinking with accurate row tracking
              if (streamingAnswer) {
                usedRows += Math.min(streamingAnswer.split('\n').length + 2, 8);
              }
              if (activeThinking) {
                const thCount = activeThinking.thoughts.length;
                usedRows += isThinkingExpanded ? Math.min(2 + thCount * 2, 10) : 2;
              }

              while (targetStart >= 0) {
                const h = turnHeights[targetStart] || 3;
                if (usedRows + h > maxViewportRows && targetStart < targetEnd) {
                  break;
                }
                usedRows += h;
                targetStart--;
              }
              targetStart = Math.max(0, targetStart + 1);

              const visibleMessages = turns.length > 0 ? turns.slice(targetStart, targetEnd + 1) : [];
              const hiddenAbove = targetStart;
              const hiddenBelow = turns.length - 1 - targetEnd;

              return (
                <>
                  {hiddenAbove > 0 && (
                    <Box paddingLeft={hMargin + 2} marginTop={0} marginBottom={1}>
                      <Text color={theme.text_faint}>
                        ↑ ({hiddenAbove} earlier {hiddenAbove === 1 ? 'turn' : 'turns'} hidden · PageUp / ↑ to scroll)
                      </Text>
                    </Box>
                  )}
                  {visibleMessages.map((m) => {
                    if (m.role === 'user') {
                      return <UserMessage key={m.id} content={m.content} theme={theme} horizontalMargin={hMargin} columns={dimensions.columns} />;
                    }

                    return (
                      <Box key={m.id} flexDirection="column">
                        {/* ToolSummary strictly ABOVE assistant response, indented by tab space under output */}
                        {m.tools && filterRealTools(m.tools).length > 0 && (
                          <ToolSummary
                            tools={m.tools}
                            isExpanded={isToolsExpanded}
                            onToggle={() => setIsToolsExpanded((p) => !p)}
                            theme={theme}
                            horizontalMargin={outputMargin}
                            columns={dimensions.columns}
                          />
                        )}
                        <AssistantMessage content={m.content} theme={theme} horizontalMargin={outputMargin} columns={dimensions.columns} />
                      </Box>
                    );
                  })}
                  {hiddenBelow > 0 && (
                    <Box paddingLeft={hMargin + 2} marginTop={1} marginBottom={0}>
                      <Text bold color={activeGold}>
                        ↓ Scrolled up ({hiddenBelow} newer {hiddenBelow === 1 ? 'turn' : 'turns'} below · Press End to return) ↓
                      </Text>
                    </Box>
                  )}
                </>
              );
            })()}

            {/* Live streaming assistant answer indented by tab space */}
            {streamingAnswer.length > 0 && (
              <Box flexDirection="column">
                {currentTurnTools.length > 0 && filterRealTools(currentTurnTools).length > 0 && (
                  <ToolSummary
                    tools={currentTurnTools}
                    isExpanded={isToolsExpanded}
                    onToggle={() => setIsToolsExpanded((p) => !p)}
                    theme={theme}
                    horizontalMargin={outputMargin}
                    columns={dimensions.columns}
                  />
                )}
                <AssistantMessage content={streamingAnswer} theme={theme} horizontalMargin={outputMargin} columns={dimensions.columns} />
              </Box>
            )}

            {/* Active thinking indicator indented by tab space */}
            {activeThinking && (
              <ThinkingDot
                label={activeThinking.label}
                fullThought={activeThinking.fullThought}
                thoughts={activeThinking.thoughts}
                workingSteps={activeThinking.workingSteps}
                activeAction={runningAction}
                isRunning={activeThinking.isRunning}
                durationS={activeThinking.durationS}
                isExpanded={isThinkingExpanded}
                onToggle={() => setIsThinkingExpanded((p) => !p)}
                theme={theme}
                horizontalMargin={outputMargin}
                columns={dimensions.columns}
              />
            )}

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
                theme={theme}
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
            if (val.startsWith('/')) {
              setQuery(val);
            } else if (query) {
              setQuery('');
            }
          }}
          isFocused={isComposerFocused && !activeModal && !pendingConfirmation && !pendingQuestion}
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

        {/* Single-line Status Telemetry (Bottom row, clean without model tag) */}
        <StatusLine
          hintText="? for help · / for commands"
          runningText={runningAction}
          isDimmed={isDimmed}
          theme={theme}
        />
      </Box>
    </Box>
  );
};
