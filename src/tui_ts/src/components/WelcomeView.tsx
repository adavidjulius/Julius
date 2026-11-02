import React from 'react';
import { Box, Text } from 'ink';
import type { ThemeTokens } from '../types.js';
import { DARK_THEME } from '../theme/tokens.js';

export const JULIUS_BANNER = `\
╔═════╗ ╔╗   ╔╗ ╔╗      ╔═════╗ ╔╗   ╔╗ ╔═════╗
╚══╗  ║ ║║   ║║ ║║      ╚═╗ ╔═╝ ║║   ║║ ║ ╔═══╝
   ║  ║ ║║   ║║ ║║        ║ ║   ║║   ║║ ║ ╚═══╗
   ║  ║ ║║   ║║ ║║        ║ ║   ║║   ║║ ╚═══╗ ║
╔══╝  ║ ║╚═══╝║ ║╚════╗ ╔═╝ ╚═╗ ║╚═══╝║ ╔═══╝ ║
╚═════╝ ╚═════╝ ╚═════╝ ╚═════╝ ╚═════╝ ╚═════╝`;

export const JULIUS_COMPACT_BANNER = '━━━  J U L I U S  ━━━';

export interface WelcomeViewProps {
  scrolled?: boolean;
  showSubtitle?: boolean;
  theme?: ThemeTokens;
  columns?: number;
  rows?: number;
}

export const WelcomeView: React.FC<WelcomeViewProps> = ({
  scrolled = false,
  showSubtitle = true,
  theme = DARK_THEME,
  columns,
  rows,
}) => {
  const termCols = columns || (typeof process !== 'undefined' && process.stdout?.columns ? process.stdout.columns : 80);
  const termRows = rows || (typeof process !== 'undefined' && process.stdout?.rows ? process.stdout.rows : 24);
  const isNarrow = termCols < 50;
  const isShort = termRows < 22;
  const activeGold = theme.brand_gold || theme.accent || '#c8b896';

  return (
    <Box
      flexDirection="column"
      alignItems="center"
      marginTop={isShort || scrolled ? 0 : 1}
      marginBottom={isShort || scrolled ? 0 : 1}
    >
      {isNarrow ? (
        <Text bold color={activeGold}>
          {JULIUS_COMPACT_BANNER}
        </Text>
      ) : (
        <Text bold color="white">
          {JULIUS_BANNER}
        </Text>
      )}
      {!scrolled && showSubtitle && !isShort && (
        <Box marginTop={1}>
          <Text color={theme.text_faint}>Ask Julius anything or type /help for commands</Text>
        </Box>
      )}
    </Box>
  );
};
