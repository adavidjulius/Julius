import React, { useState } from 'react';
import { Box, Text, useInput, useStdin } from 'ink';
import type { ThemeTokens } from '../types.js';
import { DARK_THEME } from '../theme/tokens.js';

export interface ComposerProps {
  onSubmit: (prompt: string) => void;
  onChange?: (text: string) => void;
  onTyping?: () => void;
  placeholder?: string;
  isFocused?: boolean;
  isWorking?: boolean;
  theme?: ThemeTokens;
  columns?: number;
  rows?: number;
}

/**
 * High-performance, zero-lag React Ink Composer.
 * Strictly preserves the round #3e3e42 idle and #c8b896 focused border from src/tui/components/composer.py.
 */
/**
 * Sanitizes terminal input by stripping all SGR mouse reporting codes,
 * terminal escape sequences, and non-printable control characters.
 */
function sanitizeTerminalInput(raw: string): string {
  if (!raw) return '';
  // 1. Strip all SGR mouse sequences (with or without leading ESC \x1b): [<B;X;Y;M or [<B;X;Y;m
  let cleaned = raw.replace(/(\x1b)?\[<\d+;\d+;\d+[Mm]/g, '');
  // 2. Strip legacy X10/Xterm mouse reporting: \x1b[M or [M + 3 bytes
  cleaned = cleaned.replace(/(\x1b)?\[M.{3}/g, '');
  // 3. Strip any ANSI/VT escape / CSI sequences
  cleaned = cleaned.replace(/(\x1b|\u001b)\[[0-9;?]*[a-zA-Z~]/g, '');
  // 4. Strip any dangling ESC bytes
  cleaned = cleaned.replace(/\x1b/g, '');
  // 5. Strip backspace/del bytes so they are never appended as characters
  cleaned = cleaned.replace(/[\x7f\b\x08]/g, '');
  // 6. Strip block cursor character so it never enters input buffer
  cleaned = cleaned.replace(/[█\u2588]/g, '');
  // 7. Keep only printable characters (ASCII 32..126 or Unicode > 159)
  return Array.from(cleaned).filter((ch) => {
    const code = ch.charCodeAt(0);
    return (code >= 32 && code < 127) || code > 159;
  }).join('');
}

export const Composer: React.FC<ComposerProps> = ({
  onSubmit,
  onChange,
  onTyping,
  placeholder = 'Ask Julius anything',
  isFocused = true,
  isWorking = false,
  theme = DARK_THEME,
  columns,
  rows,
}) => {
  const { isRawModeSupported } = useStdin();
  const [text, setText] = useState('');
  const [cursorOffset, setCursorOffset] = useState(0);
  const [history, setHistory] = useState<string[]>([]);
  const [historyIndex, setHistoryIndex] = useState(-1);
  const [savedDraft, setSavedDraft] = useState('');
  const [hasSubmitted, setHasSubmitted] = useState(false);

  React.useEffect(() => {
    if (!isWorking && hasSubmitted) {
      setHasSubmitted(false);
    }
  }, [isWorking]);

  const updateText = (newText: string, newOffset?: number) => {
    if (newText.length > 0 && hasSubmitted) {
      setHasSubmitted(false);
    }
    setText(newText);
    setCursorOffset(typeof newOffset === 'number' ? newOffset : newText.length);
    queueMicrotask(() => {
      onChange?.(newText);
    });
  };

  useInput((input, key) => {
    if (!isFocused) return;

    // Ignore global shortcuts so they are handled cleanly by App without typing into composer text
    const isGlobalShortcut = Boolean(
      input === '\x09' ||
      input === '\t' ||
      key.tab ||
      (key.ctrl && ['i', 't', 'o', 'd', 'y', 'l'].includes(input.toLowerCase())) ||
      (key as any).f2 ||
      (key as any).f3 ||
      input === '\x1bOR' ||
      input === '\x1b[13~'
    );
    if (isGlobalShortcut) {
      return;
    }

    if (onTyping) {
      queueMicrotask(() => onTyping());
    }

    // Submit on Enter or newline
    if (key.return || input === '\r' || input === '\n') {
      const trimmed = text.trim();
      if (trimmed) {
        if (!history.length || history[history.length - 1] !== trimmed) {
          setHistory((prev) => [...prev, trimmed]);
        }
        setHistoryIndex(-1);
        setSavedDraft('');
        updateText('', 0);
        setHasSubmitted(true);
        onSubmit(trimmed);
      }
      return;
    }

    // Left Arrow: Move cursor left (with terminal escape fallbacks)
    if (key.leftArrow || input === '\x1b[D' || input === '\x1bOD') {
      setCursorOffset((prev) => Math.max(0, prev - 1));
      return;
    }

    // Right Arrow: Move cursor right (with terminal escape fallbacks)
    if (key.rightArrow || input === '\x1b[C' || input === '\x1bOC') {
      setCursorOffset((prev) => Math.min(text.length, prev + 1));
      return;
    }

    // Home / Ctrl+A: Move cursor to start
    if ((key.ctrl && input.toLowerCase() === 'a') || (key as any).home || input === '\x1b[H' || input === '\x1b[1~') {
      setCursorOffset(0);
      return;
    }

    // End / Ctrl+E: Move cursor to end
    if ((key.ctrl && input.toLowerCase() === 'e') || (key as any).end || input === '\x1b[F' || input === '\x1b[4~') {
      setCursorOffset(text.length);
      return;
    }

    // Ctrl+U: Clear line
    if (key.ctrl && input.toLowerCase() === 'u') {
      updateText('', 0);
      return;
    }

    // Backspace: Delete character before cursor (handles macOS Delete key: ASCII 127 '\x7f', '\b', '\x08', or key.backspace)
    const isBackspace = Boolean(
      key.backspace ||
      input === '\x7f' ||
      input === '\b' ||
      input === '\x08' ||
      input === '\u007f' ||
      input === '\u0008' ||
      (key.delete && cursorOffset === text.length)
    );
    if (isBackspace) {
      if (cursorOffset > 0) {
        const next = text.slice(0, cursorOffset - 1) + text.slice(cursorOffset);
        updateText(next, cursorOffset - 1);
      } else if (text.length > 0) {
        const next = text.slice(0, -1);
        updateText(next, next.length);
      }
      return;
    }

    // Delete: Delete character at cursor
    if ((key.delete || input === '\x1b[3~') && cursorOffset < text.length) {
      const next = text.slice(0, cursorOffset) + text.slice(cursorOffset + 1);
      updateText(next, cursorOffset);
      return;
    }

    // Up Arrow: History navigation
    if (key.upArrow || input === '\x1b[A' || input === '\x1bOA') {
      if (history.length > 0) {
        if (historyIndex === -1) {
          setSavedDraft(text);
          const nextIdx = history.length - 1;
          setHistoryIndex(nextIdx);
          const histText = history[nextIdx] || '';
          updateText(histText, histText.length);
        } else if (historyIndex > 0) {
          const nextIdx = historyIndex - 1;
          setHistoryIndex(nextIdx);
          const histText = history[nextIdx] || '';
          updateText(histText, histText.length);
        }
      }
      return;
    }

    // Down Arrow: History navigation
    if (key.downArrow || input === '\x1b[B' || input === '\x1bOB') {
      if (historyIndex !== -1) {
        if (historyIndex < history.length - 1) {
          const nextIdx = historyIndex + 1;
          setHistoryIndex(nextIdx);
          const histText = history[nextIdx] || '';
          updateText(histText, histText.length);
        } else {
          setHistoryIndex(-1);
          updateText(savedDraft, savedDraft.length);
        }
      }
      return;
    }

    // Ignore all unhandled ctrl and meta key combinations so they are never typed as characters
    if (key.ctrl || key.meta) {
      return;
    }

    // Standard printable character input with full mouse & control noise rejection
    const sanitized = sanitizeTerminalInput(input);
    if (sanitized.length > 0) {
      const next = text.slice(0, cursorOffset) + sanitized + text.slice(cursorOffset);
      updateText(next, cursorOffset + sanitized.length);
    }
  }, { isActive: isFocused });

  // Julius Brand Palette: Warm Brand Gold #C8B896 for input box border
  const activeGold = theme.brand_gold || theme.accent || '#c8b896';
  const borderColor = activeGold;
  const borderStyle = 'round';
  const borderDimColor = false;

  // Render input content with slash command highlighting and cursor position
  const renderContent = () => {
    if (text.length === 0) {
      if (isFocused) {
        // When focused and empty for new prompt, placeholder vanishes, cursor blinks at start
        return <Text color={activeGold}>█</Text>;
      }
      return <Text color={theme.text_faint}>{placeholder}</Text>;
    }

    const before = text.slice(0, cursorOffset);
    const after = text.slice(cursorOffset);

    // Highlight slash commands (/model, /help, /action, etc.) in Brand Gold
    if (text.startsWith('/')) {
      const spaceIdx = text.indexOf(' ');
      const cmdEnd = spaceIdx === -1 ? text.length : spaceIdx;

      if (cursorOffset <= cmdEnd) {
        const cmdBefore = text.slice(0, cursorOffset);
        const cmdAfter = text.slice(cursorOffset, cmdEnd);
        const args = text.slice(cmdEnd);
        return (
          <Text wrap="wrap">
            <Text bold color={activeGold}>{cmdBefore}</Text>
            {isFocused && <Text color={activeGold}>█</Text>}
            <Text bold color={activeGold}>{cmdAfter}</Text>
            <Text color={theme.text}>{args}</Text>
          </Text>
        );
      } else {
        const cmd = text.slice(0, cmdEnd);
        const argsBefore = text.slice(cmdEnd, cursorOffset);
        const argsAfter = text.slice(cursorOffset);
        return (
          <Text wrap="wrap">
            <Text bold color={activeGold}>{cmd}</Text>
            <Text color={theme.text}>{argsBefore}</Text>
            {isFocused && <Text color={activeGold}>█</Text>}
            <Text color={theme.text}>{argsAfter}</Text>
          </Text>
        );
      }
    }

    // Standard user text
    return (
      <Text wrap="wrap">
        <Text color={theme.text}>{before}</Text>
        {isFocused && <Text color={activeGold}>█</Text>}
        <Text color={theme.text}>{after}</Text>
      </Text>
    );
  };

  // Auto-clamping rule: adapt input box height responsively to available rows
  const terminalRows = rows !== undefined ? rows : (typeof process !== 'undefined' && process.stdout?.rows ? process.stdout.rows : 24);
  const isSmallTerminal = terminalRows < 20;

  return (
    <Box
      width="100%"
      minHeight={3}
      height={isSmallTerminal ? 3 : undefined}
      flexDirection="column"
      borderStyle={borderStyle}
      borderColor={borderColor}
      borderDimColor={borderDimColor}
      paddingLeft={1}
      paddingRight={1}
    >
      {renderContent()}
    </Box>
  );
};

