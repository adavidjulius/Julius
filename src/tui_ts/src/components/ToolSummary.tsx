import React, { useState } from 'react';
import { Box, Text } from 'ink';
import type { ThemeTokens, ToolExecutionRecord } from '../types.js';
import { DARK_THEME } from '../theme/tokens.js';
import { shouldShowHint } from '../utils/hintManager.js';

export interface ToolSummaryProps {
  tools: ToolExecutionRecord[];
  totalDurationS?: number;
  isExpanded?: boolean;
  onToggle?: () => void;
  theme?: ThemeTokens;
  horizontalMargin?: number;
  columns?: number;
}

export function formatStepDuration(seconds: number): string {
  if (seconds <= 0) return '0.1s';
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const mins = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  if (secs > 0) return `${mins}m ${secs}s`;
  return `${mins}m`;
}

/**
 * Filter out internal protocol actions and conversational responses.
 * Returns only genuine tool/command executions.
 */
export function filterRealTools(tools?: ToolExecutionRecord[]): ToolExecutionRecord[] {
  if (!tools || tools.length === 0) return [];
  return tools.filter((t) => {
    const name = (t.tool_name || (t as any).name || '').toLowerCase();
    const summary = (t.summary || '').toLowerCase();
    if (!name && !summary) return false;
    if (['converse', 'done', 'finish', 'ask_human', 'none', 'chat', 'message'].includes(name)) {
      return false;
    }
    if (
      summary.startsWith('executed converse') ||
      summary.startsWith('conversation recorded') ||
      summary.startsWith('task completed')
    ) {
      return false;
    }
    return true;
  });
}

/**
 * Ergonomic, quiet collapsible tool activity summary.
 * Designed with reading psychology and cognitive ergonomics:
 * - Dynamic Saccadic Measure: Adapts card width to command content (52 to 76 cols).
 * - Zero Cognitive Clutter: Displays strictly the executed command ($ <cmd>), NEVER stdout/stderr dumps.
 * - Suppressed on Simple Answers: Only renders when genuine system commands/tools were executed.
 */
export const ToolSummary: React.FC<ToolSummaryProps> = ({
  tools,
  totalDurationS = 0,
  isExpanded: controlledExpanded,
  onToggle,
  theme = DARK_THEME,
  horizontalMargin,
  columns,
}) => {
  const [internalExpanded, setInternalExpanded] = useState(false);

  const realTools = filterRealTools(tools);
  if (realTools.length === 0) {
    return null;
  }

  const expanded = controlledExpanded !== undefined ? controlledExpanded : internalExpanded;
  const count = realTools.length;
  const durS =
    totalDurationS > 0
      ? totalDurationS
      : realTools.reduce((acc, t) => acc + (t.duration_s || 0.1), 0);
  const timeStr = formatStepDuration(durS);
  const activeGold = theme.brand_gold || theme.accent || '#c8b896';

  const termCols = columns || (typeof process !== 'undefined' && process.stdout?.columns ? process.stdout.columns : 80);
  const hMargin = horizontalMargin !== undefined ? horizontalMargin : (termCols < 90 ? 2 : 4);
  const maxAllowedWidth = Math.max(28, termCols - (hMargin * 2) - 4);

  // Dynamic Saccadic Measure: adapts to terminal width
  let maxCmdLen = 0;
  for (const t of realTools) {
    const cmdStr = (t.command || (t.args ? JSON.stringify(t.args) : t.summary) || '').trim();
    for (const line of cmdStr.split('\n')) {
      if (line.length > maxCmdLen) maxCmdLen = line.length;
    }
  }
  const minCardWidth = Math.min(48, maxAllowedWidth);
  const dynamicCardWidth = Math.min(Math.min(76, maxAllowedWidth), Math.max(minCardWidth, maxCmdLen + 8));

  return (
    <Box
      flexDirection="column"
      marginTop={0}
      marginBottom={1}
      marginLeft={hMargin}
      marginRight={hMargin}
    >
      {/* Collapsed single-line view: clean arrow, step count, and duration */}
      <Box flexDirection="row" alignItems="center">
        <Text color={theme.text_faint}>
          {expanded ? '⌄ ' : '› '}
        </Text>
        <Text color={theme.text_dim}>
          Ran {count} step{count !== 1 ? 's' : ''} · {timeStr}
        </Text>
      </Box>

      {/* Expanded dynamic ergonomic card: SHOWS ONLY COMMANDS, ZERO OUTPUT DUMPS */}
      {expanded && (
        <Box
          flexDirection="column"
          width={dynamicCardWidth}
          borderStyle="round"
          borderColor={theme.border_idle || '#3e3e42'}
          paddingLeft={2}
          paddingRight={2}
          paddingTop={0}
          paddingBottom={0}
          marginTop={1}
          marginBottom={0}
        >
          {/* Header line with title and collapse hint */}
          <Box flexDirection="row" justifyContent="space-between" marginBottom={1}>
            <Text bold color={activeGold}>
              ● Executed Command{count > 1 ? 's' : ''}
            </Text>
            {shouldShowHint('ctrl_o') && (
              <Text color={theme.text_faint}>
                [Ctrl+O: collapse]
              </Text>
            )}
          </Box>

          {/* Clean command list in Sky Blue (#38bdf8) with Brand Gold prompt ($ ) */}
          {realTools.map((t, idx) => {
            const rawCmd = (t.command || (t.args ? JSON.stringify(t.args) : t.summary)).trim();
            const cleanCmd = rawCmd.startsWith('$') ? rawCmd.slice(1).trim() : rawCmd;
            const durTag = t.duration_s > 0 ? ` · ${formatStepDuration(t.duration_s)}` : '';

            return (
              <Box
                key={idx}
                flexDirection="row"
                marginBottom={idx < realTools.length - 1 ? 1 : 0}
              >
                <Text bold color={activeGold}>$ </Text>
                <Box flexGrow={1} flexDirection="row" justifyContent="space-between">
                  <Text color="#38bdf8" wrap="wrap">
                    {cleanCmd}
                  </Text>
                  {durTag ? (
                    <Text color={theme.text_faint}>{durTag}</Text>
                  ) : null}
                </Box>
              </Box>
            );
          })}
        </Box>
      )}
    </Box>
  );
};
