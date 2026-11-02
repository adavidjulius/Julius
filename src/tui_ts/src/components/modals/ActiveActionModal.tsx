import React, { useState, useEffect } from 'react';
import { Box, Text, useInput, useStdin } from 'ink';
import type { ThemeTokens } from '../../types.js';
import { DARK_THEME } from '../../theme/tokens.js';

export interface ActiveActionDetails {
  action: string;
  command: string;
  startTime: number;
  endTime?: number;
  duration?: number;
  output?: string;
  is_running: boolean;
}

export interface ActiveActionModalProps {
  activeAction?: ActiveActionDetails | null;
  runningAction?: string;
  onCancelAction: () => void;
  onClose: () => void;
  theme?: ThemeTokens;
  columns?: number;
  rows?: number;
}

/**
 * Format duration in seconds to human-readable string:
 * - Under 60s: "4.1s", "29.2s"
 * - 60s and above: "1m 54s", "2m 10s"
 */
export function formatActionDuration(seconds: number): string {
  if (!seconds || seconds <= 0) return '0.0s';
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const mins = Math.floor(seconds / 60);
  const remainingSecs = Math.round(seconds % 60);
  return remainingSecs > 0 ? `${mins}m ${remainingSecs}s` : `${mins}m`;
}

/**
 * Format raw terminal output, resolving carriage returns (\r) and stripping ANSI escapes cleanly.
 */
function formatTerminalOutput(raw: string, maxLines: number = 7): string[] {
  if (!raw) return [];
  const lines = raw.replace(/\r\n/g, '\n').split('\n');
  const processed: string[] = [];

  for (const line of lines) {
    let cleanLine = line;
    if (cleanLine.includes('\r')) {
      const parts = cleanLine.split('\r');
      const nonEmpties = parts.filter((p) => p.trim());
      cleanLine = nonEmpties.length > 0 ? nonEmpties[nonEmpties.length - 1]! : parts[parts.length - 1]!;
    }
    // Strip ANSI escape codes
    cleanLine = cleanLine.replace(/\x1b\[[0-9;]*[a-zA-Z]/g, '').trimEnd();
    if (cleanLine) {
      processed.push(cleanLine);
    }
  }

  return processed.slice(-maxLines);
}

/**
 * Authentic Active Action Modal.
 * Exact visual and behavioral parity with Python Textual's ActiveActionModal:
 * - Card width: 78, rounded Brand Gold #C8B896 border, centered.
 * - Title: "Active Action" in bold #f5f5f7.
 * - Subtitle: "Live status and control of background operations" in gold.
 * - Status Line: "STATUS: ● RUNNING (Xs)" or "STATUS: ✓ Completed" or "STATUS: ○ IDLE".
 * - Command Box: rounded #3e3e42 border, showing "$ <command>" in cyan.
 * - Process Output Box: height 8, rounded #3e3e42 border, ALWAYS rendered with live or completed stream.
 * - Actions: "[⏹ Cancel Action]" (red #b91c1c when running) and "[Close]" (#2c2c2e).
 */
export const ActiveActionModal: React.FC<ActiveActionModalProps> = ({
  activeAction = null,
  runningAction = '',
  onCancelAction,
  onClose,
  theme = DARK_THEME,
  columns,
  rows,
}) => {
  const [elapsed, setElapsed] = useState(0);
  const { isRawModeSupported } = useStdin();

  const isRunning = Boolean(
    (activeAction && activeAction.is_running) ||
    (runningAction && runningAction.trim().length > 0)
  );

  useEffect(() => {
    if (!isRunning) {
      if (activeAction?.duration !== undefined) {
        setElapsed(activeAction.duration);
      } else if (activeAction?.endTime && activeAction?.startTime) {
        setElapsed((activeAction.endTime - activeAction.startTime) / 1000);
      }
      return;
    }
    const start = activeAction?.startTime || Date.now();
    const interval = setInterval(() => {
      setElapsed((Date.now() - start) / 1000);
    }, 100);
    return () => clearInterval(interval);
  }, [isRunning, activeAction?.startTime, activeAction?.endTime, activeAction?.duration, runningAction]);

  useInput((input, key) => {
    // Dismiss modal on Escape, Q, or Enter
    if (key.escape || input.toLowerCase() === 'q' || key.return) {
      onClose();
      return;
    }

    // Cancel active action on C / c (only when running)
    if (isRunning && input.toLowerCase() === 'c') {
      onCancelAction();
      onClose();
      return;
    }
  }, { isActive: true });

  const activeGold = theme.brand_gold || theme.accent || '#c8b896';
  const actionName = activeAction?.action || (runningAction ? 'run_bash' : 'action');
  const currentCommand = activeAction?.command || runningAction || '';
  const isDoneAction = currentCommand.toLowerCase() === 'done' || currentCommand.toLowerCase() === 'executing done...';
  const displayCommand = isDoneAction ? '(Task complete)' : currentCommand;
  const currentOutput = activeAction?.output || '';

  const termCols = columns || (typeof process !== 'undefined' && process.stdout?.columns ? process.stdout.columns : 80);
  const termRows = rows || (typeof process !== 'undefined' && process.stdout?.rows ? process.stdout.rows : 24);
  const cardWidth = Math.min(78, Math.max(36, termCols - 4));
  const isShortScreen = termRows < 18;
  const outputBoxHeight = termRows <= 24 ? 4 : (termRows <= 32 ? 6 : 8);

  const outputLines = formatTerminalOutput(currentOutput, Math.max(2, outputBoxHeight - 2));

  return (
    <Box
      flexDirection="column"
      width={cardWidth}
      flexShrink={0}
      borderStyle="round"
      borderColor={activeGold}
      paddingLeft={termCols < 60 ? 1 : 2}
      paddingRight={termCols < 60 ? 1 : 2}
      paddingTop={0}
      paddingBottom={0}
      marginTop={0}
      marginBottom={1}
      alignSelf="center"
    >
      {/* 1. Modal Header Title */}
      <Box justifyContent="center" flexShrink={0}>
        <Text bold color={theme.text || '#f5f5f7'}>
          Active Action
        </Text>
      </Box>

      {/* 2. Subtitle */}
      {!isShortScreen && (
        <Box justifyContent="center" marginBottom={1}>
          <Text color={activeGold}>
            Live status and control of background operations
          </Text>
        </Box>
      )}

      {/* 3. Status Line */}
      <Box justifyContent="center" marginBottom={1}>
        <Text bold color={theme.text || '#f5f5f7'}>STATUS: </Text>
        {isRunning ? (
          <Text>
            <Text bold color={theme.success || '#22c55e'}>● Running ({actionName})</Text>
            <Text color={theme.text_faint || '#86868b'}>  •  </Text>
            <Text bold color={activeGold}>{formatActionDuration(elapsed)} elapsed</Text>
            <Text color={theme.text_faint || '#86868b'}>  (Click 'Cancel Action' below if stuck)</Text>
          </Text>
        ) : currentCommand ? (
          <Text>
            <Text bold color={theme.success || '#22c55e'}>✓ Completed</Text>
            {elapsed > 0 && <Text color={theme.text_faint || '#86868b'}>  •  {formatActionDuration(elapsed)}</Text>}
          </Text>
        ) : (
          <Text color={theme.text_faint || '#86868b'}>
            ○ IDLE
          </Text>
        )}
      </Box>

      {/* 4. Command Box */}
      <Box
        flexDirection="column"
        borderStyle="round"
        borderColor={theme.border_idle || '#3e3e42'}
        paddingLeft={1}
        paddingRight={1}
        marginBottom={1}
      >
        <Box marginBottom={0}>
          <Text bold color={theme.text_dim || '#86868b'}>Command / Target:</Text>
        </Box>
        <Box>
          <Text bold color={activeGold}>$ </Text>
          {displayCommand ? (
            <Text bold color="#38bdf8" wrap="wrap">
              {displayCommand}
            </Text>
          ) : (
            <Text color={theme.text_faint || '#86868b'}>
              No tool action actively executing.
            </Text>
          )}
        </Box>
      </Box>

      {/* 5. Terminal / Process Output Box - ALWAYS VISIBLE */}
      <Box
        flexDirection="column"
        borderStyle="round"
        borderColor={theme.border_idle || '#3e3e42'}
        paddingLeft={1}
        paddingRight={1}
        height={outputBoxHeight}
        overflowY="hidden"
        marginBottom={1}
      >
        <Box marginBottom={0}>
          <Text bold color={theme.text_dim || '#86868b'}>Process Output:</Text>
        </Box>
        <Box flexDirection="column" flexGrow={1}>
          {outputLines.length > 0 ? (
            outputLines.map((line, idx) => (
              <Text key={idx} color="#ded2b8" wrap="wrap">
                {line}
              </Text>
            ))
          ) : isRunning ? (
            <Text>
              <Text color={activeGold}>$ </Text>
              <Text color={theme.text_faint || '#86868b'}>
                Process executing... output will stream here
              </Text>
            </Text>
          ) : (
            <Text color={theme.text_faint || '#86868b'}>
              (No recent output to display)
            </Text>
          )}
        </Box>
      </Box>

      {/* 6. Controls / Action Buttons */}
      <Box flexDirection="row" justifyContent="center" marginBottom={1}>
        {isRunning ? (
          <Box marginRight={2}>
            <Text backgroundColor="#b91c1c" color="#ffffff" bold>
              {'  ⏹ Cancel Action [C]  '}
            </Text>
          </Box>
        ) : (
          <Box marginRight={2}>
            <Text backgroundColor="#2a2020" color="#555555">
              {'  ⏹ Cancel Action [C]  '}
            </Text>
          </Box>
        )}
        <Box>
          <Text backgroundColor="#2c2c2e" color="#f5f5f7" bold>
            {'  Close [Esc]  '}
          </Text>
        </Box>
      </Box>
    </Box>
  );
};
