import React, { useState } from 'react';
import { Box, Text, useInput, useStdin } from 'ink';
import type { ThemeTokens } from '../types.js';
import { DARK_THEME } from '../theme/tokens.js';
import { COMMANDS } from './CommandSuggestions.js';
import { readFromClipboard } from '../utils/clipboard.js';

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
 * High-performance, clean React Ink Composer with full clipboard paste support.
 * Subtle non-glowing grey border per design specification.
 */
function sanitizeTerminalInput(raw: string): string {
  if (!raw) return '';
  // 1. Strip bracketed paste mode markers \x1b[200~ and \x1b[201~
  let cleaned = raw.replace(/\x1b\[200~/g, '').replace(/\x1b\[201~/g, '');
  // 2. Strip all SGR mouse sequences: [<B;X;Y;M or [<B;X;Y;m
  cleaned = cleaned.replace(/(\x1b)?\[<\d+;\d+;\d+[Mm]/g, '');
  // 3. Strip legacy X10 mouse reporting
  cleaned = cleaned.replace(/(\x1b)?\[M.{3}/g, '');
  // 4. Strip ANSI escape sequences EXCEPT standard printable characters
  cleaned = cleaned.replace(/(\x1b|\u001b)\[[0-9;?]*[a-zA-Z~]/g, '');
  cleaned = cleaned.replace(/\x1b/g, '');
  // 5. Strip backspace/del bytes
  cleaned = cleaned.replace(/[\x7f\b\x08]/g, '');
  // 6. Strip block cursor character so it never enters buffer
  cleaned = cleaned.replace(/[██]/g, '');
  // 7. Convert tabs to spaces
  cleaned = cleaned.replace(/\t/g, '  ');
  // 8. Allow standard printable characters, spaces, and preserve newlines
  return Array.from(cleaned).filter((ch) => {
    const code = ch.charCodeAt(0);
    return code === 10 || code === 13 || (code >= 32 && code < 127) || code > 159;
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

    // 1. Clipboard Paste (Ctrl+V, Cmd+V, or ASCII \x16)
    const isPaste = Boolean(
      (key.ctrl && (input.toLowerCase() === 'v' || input === '\x16')) ||
      (key.meta && input.toLowerCase() === 'v') ||
      input === '\x16'
    );
    if (isPaste) {
      const clipText = readFromClipboard();
      if (clipText) {
        const cleanClip = sanitizeTerminalInput(clipText);
        if (cleanClip.length > 0) {
          const next = text.slice(0, cursorOffset) + cleanClip + text.slice(cursorOffset);
          updateText(next, cursorOffset + cleanClip.length);
          return;
        }
      }
    }

    // 2. Tab completion for slash commands (Shift+Tab is reserved for Mode Switching)
    const isShiftTab = Boolean(
      (key.shift && (key.tab || input === '\t' || input === '\x09')) ||
      input === '\x1b[Z' ||
      input === '\x1b[27;2;9~' ||
      input === '\x1b[9;2u'
    );
    if (isShiftTab) {
      return;
    }

    const isTab = Boolean(key.tab || input === '\t' || input === '\x09');
    if (isTab) {
      if (text.startsWith('/')) {
        const spaceIdx = text.indexOf(' ');
        if (spaceIdx === -1) {
          const query = text.toLowerCase().trim();
          const matching = COMMANDS.find(([cmd]) => cmd.toLowerCase().startsWith(query));
          if (matching) {
            const completed = matching[0] + ' ';
            updateText(completed, completed.length);
            return;
          }
        }
      }
      return;
    }

    // Ignore global shortcuts so they are handled cleanly by App
    const isGlobalShortcut = Boolean(
      (key.ctrl && ['t', 'o', 'd', 'y', 'l'].includes(input.toLowerCase())) ||
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

    // 3. Submit on Enter: Auto-expands slash command prefixes like /he -> /help
    const hasNewline = Boolean(input && (input.includes('\n') || input.includes('\r')));
    if (key.return || input === '\r' || input === '\n' || hasNewline) {
      const incomingText = hasNewline ? sanitizeTerminalInput(input.replace(/[\r\n]+$/, '')) : '';
      let combined = (text.slice(0, cursorOffset) + incomingText + text.slice(cursorOffset)).trim();

      // If user typed a slash command prefix (e.g. /he, /mod, /cl), resolve to matching command
      if (combined.startsWith('/') && !combined.includes(' ')) {
        const lower = combined.toLowerCase();
        const match = COMMANDS.find(([cmd]) => cmd.toLowerCase().startsWith(lower));
        if (match) {
          combined = match[0];
        }
      }

      if (combined) {
        if (!history.length || history[history.length - 1] !== combined) {
          setHistory((prev) => [...prev, combined]);
        }
        setHistoryIndex(-1);
        setSavedDraft('');
        setText('');
        setCursorOffset(0);
        onChange?.('');
        setHasSubmitted(true);
        onSubmit(combined);
      }
      return;
    }

    // Left Arrow
    if (key.leftArrow || input === '\x1b[D' || input === '\x1bOD') {
      setCursorOffset((prev) => Math.max(0, prev - 1));
      return;
    }

    // Right Arrow
    if (key.rightArrow || input === '\x1b[C' || input === '\x1bOC') {
      setCursorOffset((prev) => Math.min(text.length, prev + 1));
      return;
    }

    // Home / Ctrl+A
    if (input === '\x01' || (key.ctrl && (input.toLowerCase() === 'a' || input === '\x01')) || (key as any).home || input === '\x1b[H' || input === '\x1b[1~') {
      setCursorOffset(0);
      return;
    }

    // End / Ctrl+E
    if (input === '\x05' || (key.ctrl && (input.toLowerCase() === 'e' || input === '\x05')) || (key as any).end || input === '\x1b[F' || input === '\x1b[4~') {
      setCursorOffset(text.length);
      return;
    }

    // Ctrl+U: Clear line
    if (input === '\x15' || (key.ctrl && (input.toLowerCase() === 'u' || input === '\x15'))) {
      updateText('', 0);
      return;
    }

    // Backspace
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

    // Delete
    if ((key.delete || input === '\x1b[3~') && cursorOffset < text.length) {
      const next = text.slice(0, cursorOffset) + text.slice(cursorOffset + 1);
      updateText(next, cursorOffset);
      return;
    }

    // Up Arrow: History
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

    // Down Arrow: History
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

    // Ignore unhandled control combinations
    if (key.ctrl || key.meta) {
      return;
    }

    // Standard printable character input and multi-character paste bursts
    const sanitized = sanitizeTerminalInput(input);
    if (sanitized.length > 0) {
      const next = text.slice(0, cursorOffset) + sanitized + text.slice(cursorOffset);
      updateText(next, cursorOffset + sanitized.length);
    }
  }, { isActive: isFocused });

  const activeGold = theme.brand_gold || theme.accent || '#c8b896';
  // Subtle dark grey border — NO GOLD GLOW on input box per user request
  const borderColor = theme.border_idle || '#3e3e42';
  // Text in grey (#a1a1aa), selected / cursor in brand gold
  const textColor = '#a1a1aa';

  const renderContent = () => {
    if (text.length === 0) {
      if (isFocused) {
        return (
          <Text wrap="truncate">
            <Text color={activeGold}>█</Text>
            <Text color={theme.text_faint}> {placeholder}</Text>
          </Text>
        );
      }
      return <Text color={theme.text_faint}>{placeholder}</Text>;
    }

    const before = text.slice(0, cursorOffset);
    const after = text.slice(cursorOffset);

    // Slash command highlight
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
            <Text color={textColor}>{args}</Text>
          </Text>
        );
      } else {
        const cmd = text.slice(0, cmdEnd);
        const argsBefore = text.slice(cmdEnd, cursorOffset);
        const argsAfter = text.slice(cursorOffset);
        return (
          <Text wrap="wrap">
            <Text bold color={activeGold}>{cmd}</Text>
            <Text color={textColor}>{argsBefore}</Text>
            {isFocused && <Text color={activeGold}>█</Text>}
            <Text color={textColor}>{argsAfter}</Text>
          </Text>
        );
      }
    }

    return (
      <Text wrap="wrap">
        <Text color={textColor}>{before}</Text>
        {isFocused && <Text color={activeGold}>█</Text>}
        <Text color={textColor}>{after}</Text>
      </Text>
    );
  };

  const terminalRows = rows !== undefined ? rows : (typeof process !== 'undefined' && process.stdout?.rows ? process.stdout.rows : 24);
  const isSmallTerminal = terminalRows < 20;

  return (
    <Box
      width="100%"
      minHeight={3}
      height={isSmallTerminal ? 3 : undefined}
      flexDirection="column"
      borderStyle="round"
      borderColor={borderColor}
      paddingLeft={1}
      paddingRight={1}
    >
      {renderContent()}
    </Box>
  );
};
