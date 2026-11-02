import React, { useState, useEffect } from 'react';
import { Box, Text } from 'ink';
import type { ThemeTokens } from '../types.js';
import { DARK_THEME } from '../theme/tokens.js';
import { formatActionDuration } from './modals/ActiveActionModal.js';

export interface StatusLineProps {
  modelName?: string;
  hintText?: string;
  runningText?: string;
  isDimmed?: boolean;
  theme?: ThemeTokens;
}

const SPINNER_FRAMES = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'];

export const StatusLine: React.FC<StatusLineProps> = ({
  modelName = '',
  hintText = '? for help',
  runningText = '',
  isDimmed = false,
  theme = DARK_THEME,
}) => {
  const [spinnerIndex, setSpinnerIndex] = useState(0);
  const [startTime, setStartTime] = useState<number | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  const isLoading = Boolean(runningText && runningText.trim());

  useEffect(() => {
    if (isLoading) {
      const now = Date.now();
      setStartTime(now);
      const timer = setInterval(() => {
        setSpinnerIndex((prev) => (prev + 1) % SPINNER_FRAMES.length);
        setElapsedSeconds(Math.max(0, (Date.now() - now) / 1000));
      }, 100);
      return () => clearInterval(timer);
    } else {
      setStartTime(null);
      setElapsedSeconds(0);
    }
  }, [isLoading, runningText]);

  if (isDimmed && !isLoading) {
    return <Box height={1} />;
  }

  const frame = SPINNER_FRAMES[spinnerIndex];
  const elapsedStr = elapsedSeconds >= 0.5 ? ` (${formatActionDuration(elapsedSeconds)})` : '';

  return (
    <Box height={1} width="100%" justifyContent="space-between" paddingLeft={1} paddingRight={1}>
      {/* Bottom-left: Hint text or prompt instructions */}
      <Box>
        <Text color={theme.text_faint}>{hintText}</Text>
      </Box>

      {/* Bottom-right: Loading action spinner when active */}
      <Box>
        {isLoading && (
          <Text>
            <Text color={theme.accent}>{frame}</Text> <Text color={theme.text}>{runningText}</Text>
            <Text color={theme.text_dim}>{elapsedStr}</Text>
            <Text color={theme.brand_gold || theme.accent}> [Ctrl+I: Inspect Action]</Text>
          </Text>
        )}
      </Box>
    </Box>
  );
};

