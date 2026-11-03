import React from 'react';
import { Box, Text } from 'ink';
import type { ThemeTokens } from '../types.js';
import { DARK_THEME } from '../theme/tokens.js';

export interface UserMessageProps {
  content: string;
  theme?: ThemeTokens;
  horizontalMargin?: number;
  columns?: number;
}

/**
 * User message rendered on a subtle hairline thread card, left-aligned, not bold.
 * Ultra-thin single hairline border with dimmed subtle shading ("like a thread: it is there but not there"),
 * adapting dynamically to terminal dimensions without overflow.
 */
export const UserMessage: React.FC<UserMessageProps> = ({
  content,
  theme = DARK_THEME,
  horizontalMargin,
  columns,
}) => {
  const termCols = columns || (typeof process !== 'undefined' && process.stdout?.columns ? process.stdout.columns : 80);
  const hMargin = horizontalMargin !== undefined ? horizontalMargin : (termCols < 90 ? 2 : 4);
  const maxCardWidth = Math.max(24, termCols - (hMargin * 2) - 4);

  // Dynamic card width: exactly fits content + 4 (padding & border), clamped cleanly between 8 and maxCardWidth
  const lines = content.trim().split('\n');
  const maxLineLen = Math.max(...lines.map((l) => l.length), 0);
  const cardWidth = Math.min(maxCardWidth, Math.max(8, maxLineLen + 4));

  return (
    <Box
      flexDirection="row"
      marginTop={1}
      marginBottom={1}
      paddingLeft={hMargin}
    >
      <Box
        borderStyle="single"
        borderColor={(theme as any).border_subtle || '#28282e'}
        borderDimColor={true}
        paddingLeft={1}
        paddingRight={1}
        width={cardWidth}
      >
        <Text color={theme.text} wrap="wrap">{content.trim()}</Text>
      </Box>
    </Box>
  );
};

