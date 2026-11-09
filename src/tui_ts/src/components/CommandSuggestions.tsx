import React from 'react';
import { Box, Text } from 'ink';
import type { ThemeTokens } from '../types.js';
import { DARK_THEME } from '../theme/tokens.js';

export interface CommandSuggestionsProps {
  query: string;
  selectedIndex?: number;
  theme?: ThemeTokens;
}

export const COMMANDS: [cmd: string, desc: string][] = [
  ['/help', 'Show keyboard shortcuts and command guide'],
  ['/mode', 'Switch operation mode: auto, plan, edit, accept, manual (Shift+Tab)'],
  ['/auto', 'Switch to Auto mode (autonomous execution)'],
  ['/plan', 'Switch to Plan mode (propose implementation plan without changes)'],
  ['/edit', 'Switch to Edit mode (interactive code development)'],
  ['/accept', 'Switch to Accept mode (unrestricted access, no blocks)'],
  ['/manual', 'Switch to Manual mode (ask confirmation for actions)'],
  ['/model', 'Switch active reasoning model (F2 picker)'],
  ['/diff', 'Review workspace file modifications and diffs'],
  ['/action', 'Inspect live background command & terminal output'],
  ['/clear', 'Reset conversation and launch fresh browser session'],
  ['/new', 'Reset conversation and launch fresh browser session'],
  ['/plan', 'Analyze task and propose implementation plan without changes'],
  ['/act', 'Execute autonomous task directly'],
  ['/undo', 'Rollback last file modifications from workspace ledger'],
  ['/status', 'Inspect system vitals, CPU, RAM, and disk storage'],
  ['/vitals', 'Inspect live hardware telemetry and battery status'],
  ['/alerts', 'Review proactive background daemon warnings and alerts'],
  ['/teamwork', 'Deploy parallel multi-agent squad (Architect, Dev, QA)'],
  ['/research', 'Launch deep research multi-source verification harness'],
  ['/tools', 'List all available OS and autonomous agent tools'],
  ['/voice', 'Toggle ambient voice listener and speech engine'],
  ['/image', 'Analyze screen or generate visual image assets'],
  ['/doctor', 'Run health check on Python, Git, and environment'],
  ['/context', 'View loaded workspace context and memory telemetry'],
  ['/cost', 'Display session token usage and estimated cost'],
  ['/compact', 'Compress conversation history to reclaim context window'],
  ['/theme', 'Toggle dark / light visual theme'],
  ['/exit', 'Close Julius terminal session safely'],
];

export const CommandSuggestions: React.FC<CommandSuggestionsProps> = ({
  query,
  selectedIndex = 0,
  theme = DARK_THEME,
}) => {
  if (!query || !query.startsWith('/') || query.includes(' ')) {
    return null;
  }

  const prefix = query.toLowerCase().trim();
  const matches = COMMANDS.filter(([cmd]) => cmd.toLowerCase().startsWith(prefix));

  if (matches.length === 0) {
    return null;
  }

  const brandGold = theme.brand_gold || theme.accent || '#c8b896';

  // Render completely borderless per user specification
  return (
    <Box
      flexDirection="column"
      paddingLeft={2}
      paddingRight={2}
      marginBottom={1}
    >
      {matches.slice(0, 8).map(([cmd, desc], idx) => {
        const isSelected = idx === selectedIndex;
        return (
          <Box key={cmd} flexDirection="row">
            <Text color={isSelected ? brandGold : theme.text_dim}>
              {isSelected ? '› ' : '  '}
            </Text>
            <Text bold color={isSelected ? brandGold : '#9ca3af'}>
              {cmd}
            </Text>
            <Text color={theme.text_faint}> — {desc}</Text>
          </Box>
        );
      })}
    </Box>
  );
};
