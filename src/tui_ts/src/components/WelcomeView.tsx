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

export interface WelcomeViewProps {
  scrolled?: boolean;
  showSubtitle?: boolean;
  theme?: ThemeTokens;
  columns?: number;
  rows?: number;
  activeModel?: string;
  appMode?: string;
}

export const WelcomeView: React.FC<WelcomeViewProps> = ({
  theme = DARK_THEME,
  rows,
}) => {
  const termRows = rows || (typeof process !== 'undefined' && process.stdout?.rows ? process.stdout.rows : 24);
  const isShort = termRows < 24;
  const activeGold = theme.brand_gold || theme.accent || '#c8b896';

  return (
    <Box
      flexDirection="column"
      alignItems="center"
      marginTop={isShort ? 0 : 1}
      marginBottom={0}
      flexShrink={0}
    >
      {/* ASCII banner rendered in signature brand gold */}
      <Text bold color={activeGold}>
        {JULIUS_BANNER}
      </Text>
    </Box>
  );
};
