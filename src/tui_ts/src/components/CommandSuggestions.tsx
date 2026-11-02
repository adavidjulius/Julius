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
  ['/model', 'Switch active reasoning model (F2 picker)'],
  ['/diff', 'Review workspace file modifications and diffs'],
  ['/action', 'Inspect live background command & terminal output'],
  ['/clear', 'Reset conversation and launch fresh browser session'],
  ['/new', 'Reset conversation and launch fresh browser session'],
  ['/plan', 'Analyze task and propose implementation plan without changes'],
  ['/act', 'Execute autonomous task directly'],
  ['/undo', 'Rollback last file modifications from workspace ledger'],
  ['/doctor', 'Run health check on Python, Git, and environment'],
  ['/context', 'View loaded workspace context and memory telemetry'],
  ['/cost', 'Display session token usage and estimated cost'],
  ['/compact', 'Compress conversation history to reclaim context window'],
  ['/theme', 'Toggle dark / light visual theme'],
  ['/exit', 'Close Julius terminal session safely'],
];

export const CommandSuggestions: React.FC<CommandSuggestionsProps> = ({
  // Import or destructure parameter query
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

  return (
    <Box
      flexDirection="column"
      borderStyle="round"
      borderColor={brandGold}
      paddingLeft={1}
      paddingRight={1}
      marginBottom={1}
    >
      {matches.slice(0, 6).map(([cmd, desc], idx) => {
        const isSelected = idx === selectedIndex;
        return (
          <Box key={cmd}>
            <Text color={isSelected ? brandGold : theme.text_dim}>
              {isSelected ? '› ' : '  '}
              <Text bold color={brandGold}>
                {cmd}
              </Text>{' '}
              <Text color={theme.text_faint}>— {desc}</Text>
            </Text>
          </Box>
        );
      })}
    </Box>
  );
};
