import React from 'react';
import { Box, Text } from 'ink';
import type { ThemeTokens } from '../types.js';
import { DARK_THEME } from '../theme/tokens.js';
import { shouldShowHint } from '../utils/hintManager.js';

export interface CommandBoxProps {
  code: string;
  language?: string;
  theme?: ThemeTokens;
}

export const CommandBox: React.FC<CommandBoxProps> = ({
  code,
  language = 'bash',
  theme = DARK_THEME,
}) => {
  const lines = code.trim().split('\n');

  return (
    <Box
      flexDirection="column"
      borderStyle="round"
      borderColor={theme.border_idle}
      paddingLeft={1}
      paddingRight={1}
      marginTop={1}
      marginBottom={1}
    >
      {/* Top Header */}
      <Box justifyContent="space-between" marginBottom={0}>
        <Text color={theme.text_faint}>{language}</Text>
        {shouldShowHint('ctrl_y') && (
          <Text color={theme.accent}>[Ctrl+Y to copy]</Text>
        )}
      </Box>

      {/* Code Content */}
      <Box flexDirection="column" marginTop={0}>
        {lines.map((line, idx) => (
          <Text key={idx} color={theme.text}>
            {line}
          </Text>
        ))}
      </Box>
    </Box>
  );
};


