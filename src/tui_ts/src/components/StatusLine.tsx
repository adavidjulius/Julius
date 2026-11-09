import React, { useState, useEffect } from 'react';
import { Box, Text } from 'ink';
import type { ThemeTokens, ContextGaugeData, ReasoningEffort, PermissionModeType, AppMode } from '../types.js';
import { DARK_THEME } from '../theme/tokens.js';
import { formatActionDuration } from './modals/ActiveActionModal.js';
import { shouldShowHint } from '../utils/hintManager.js';

export interface StatusLineProps {
  modelName?: string;
  hintText?: string;
  runningText?: string;
  isDimmed?: boolean;
  theme?: ThemeTokens;
  contextGauge?: ContextGaugeData;
  effortLevel?: ReasoningEffort;
  permissionMode?: PermissionModeType;
  appMode?: AppMode;
}

const MODE_DISPLAY: Record<AppMode, { label: string; color: string; badge: string }> = {
  auto: { label: 'Auto', color: '#569cd6', badge: '[Auto]' },
  plan: { label: 'Plan', color: '#c586c0', badge: '[Plan]' },
  edit: { label: 'Edit', color: '#4ec9b0', badge: '[Edit]' },
  accept: { label: 'Accept', color: '#dcdcaa', badge: '[Accept: Full Access]' },
  manual: { label: 'Manual', color: '#ce9178', badge: '[Manual: Confirm]' },
};

const SPINNER_FRAMES = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'];

function formatTokenCount(num: number): string {
  if (num < 1000) return `${num}`;
  return `${(num / 1000).toFixed(num >= 10000 ? 0 : 1)}k`;
}

export const StatusLine: React.FC<StatusLineProps> = ({
  modelName = '',
  hintText = '? for help',
  runningText = '',
  isDimmed = false,
  theme = DARK_THEME,
  contextGauge,
  effortLevel,
  permissionMode,
  appMode,
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
  const activeGold = theme.brand_gold || theme.accent || '#c8b896';

  // Render context gauge bar: [====----]
  let gaugeText = '';
  if (contextGauge && contextGauge.max_tokens > 0) {
    const totalBars = 8;
    const filledBars = Math.min(totalBars, Math.round((contextGauge.current_tokens / contextGauge.max_tokens) * totalBars));
    const emptyBars = Math.max(0, totalBars - filledBars);
    const barStr = '='.repeat(filledBars) + '-'.repeat(emptyBars);
    const currStr = formatTokenCount(contextGauge.current_tokens);
    const maxStr = formatTokenCount(contextGauge.max_tokens);
    const warmSymbol = contextGauge.is_warm ? ' ⚡' : '';
    gaugeText = `[${barStr}] ${currStr}/${maxStr}${warmSymbol}`;
  }

  return (
    <Box height={1} width="100%" justifyContent="space-between" paddingLeft={1} paddingRight={1}>
      {/* Bottom-left: Model, mode, effort, and token context gauge */}
      <Box>
        <Text color={theme.text_faint}>
          {modelName ? <Text color={activeGold} bold>{modelName} </Text> : null}
          {appMode ? (
            <Text>
              <Text color={MODE_DISPLAY[appMode].color} bold>{MODE_DISPLAY[appMode].badge} </Text>
              <Text color={theme.text_dim}>Shift+Tab to switch modes · </Text>
            </Text>
          ) : null}
          {effortLevel ? <Text color={theme.text_dim}>· {effortLevel} </Text> : null}
          {permissionMode && !appMode ? <Text color={theme.text_dim}>· {permissionMode} </Text> : null}
          {gaugeText ? <Text color={theme.text_faint}>· {gaugeText} </Text> : null}
          {hintText && !appMode ? <Text color={theme.text_faint}>{hintText}</Text> : null}
          {appMode && hintText ? <Text color={theme.text_faint}>{hintText}</Text> : null}
        </Text>
      </Box>

      {/* Bottom-right: Loading action spinner when active */}
      <Box>
        {isLoading && (
          <Text>
            <Text color={theme.accent}>{frame}</Text> <Text color={theme.text}>{runningText}</Text>
            <Text color={theme.text_dim}>{elapsedStr}</Text>
            {shouldShowHint('ctrl_i') && (
              <Text color={activeGold}> [Ctrl+I: Inspect Action]</Text>
            )}
          </Text>
        )}
      </Box>
    </Box>
  );
};
