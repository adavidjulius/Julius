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

export function formatActionDuration(seconds: number): string {
  if (!seconds || seconds <= 0) return '0.0s';
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const mins = Math.floor(seconds / 60);
  const remainingSecs = Math.round(seconds % 60);
  return remainingSecs > 0 ? `${mins}m ${remainingSecs}s` : `${mins}m`;
}

function formatTerminalOutput(raw: string, maxLines: number = 6): string[] {
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
    cleanLine = cleanLine.replace(/\x1b\[[0-9;]*[a-zA-Z]/g, '').trimEnd();
    if (cleanLine) {
      processed.push(cleanLine);
    }
  }

  return processed.slice(-maxLines);
}

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
    if (key.escape || input.toLowerCase() === 'q' || key.return) {
      onClose();
      return;
    }
    if (input.toLowerCase() === 'c') {
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
  const cardWidth = Math.min(74, Math.max(36, termCols - 4));
  const outputBoxHeight = termRows <= 24 ? 3 : 5;
  const outputLines = formatTerminalOutput(currentOutput, outputBoxHeight);

  // Subtle clean border per design requirements
  return (
    <Box
      flexDirection="column"
      width={cardWidth}
      borderStyle="round"
      borderColor={theme.border_idle || '#3e3e42'}
      paddingLeft={2}
      paddingRight={2}
      paddingTop={0}
      paddingBottom={0}
      marginBottom={1}
      alignSelf="center"
    >
      {/* 1. Header & Status */}
      <Box justifyContent="space-between" marginBottom={0}>
        <Text bold color="#f5f5f7">
          Active Action
        </Text>
        <Text>
          {isRunning ? (
            <Text bold color={theme.success || '#22c55e'}>● Running ({actionName}) · {formatActionDuration(elapsed)}</Text>
          ) : currentCommand ? (
            <Text bold color={theme.success || '#22c55e'}>✓ Completed · {formatActionDuration(elapsed)}</Text>
          ) : (
            <Text color={theme.text_faint}>○ Idle</Text>
          )}
        </Text>
      </Box>

      {/* 2. Command Display */}
      <Box flexDirection="row" marginTop={0} marginBottom={0}>
        <Text bold color={activeGold}>$ </Text>
        <Text color="#38bdf8" wrap="wrap">
          {displayCommand || 'No active background command'}
        </Text>
      </Box>

      {/* 3. Output Section */}
      <Box flexDirection="column" marginTop={0} marginBottom={1}>
        <Box marginBottom={0}>
          <Text color={theme.text_dim}>Output:</Text>
        </Box>
        {outputLines.length > 0 ? (
          outputLines.map((line, idx) => (
            <Text key={idx} color="#ded2b8" wrap="wrap">
              {line}
            </Text>
          ))
        ) : (
          <Text color={theme.text_faint}>
            {isRunning ? 'Process executing... live output will stream here' : '(No process output)'}
          </Text>
        )}
      </Box>

      {/* 4. Controls */}
      <Box flexDirection="row" justifyContent="flex-end" marginBottom={0}>
        {isRunning && (
          <Box marginRight={2}>
            <Text backgroundColor="#b91c1c" color="#ffffff" bold>
              {' [C] Cancel Action '}
            </Text>
          </Box>
        )}
        <Text color={theme.text_faint}>[Esc / Enter] Close</Text>
      </Box>
    </Box>
  );
};
