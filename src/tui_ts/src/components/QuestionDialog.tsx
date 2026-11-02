import React from 'react';
import { Box, Text } from 'ink';
import type { ThemeTokens } from '../types.js';
import { DARK_THEME } from '../theme/tokens.js';

export interface QuestionDialogProps {
  question: string;
  options?: string[];
  theme?: ThemeTokens;
}

export const QuestionDialog: React.FC<QuestionDialogProps> = ({
  // Import or destructure parameter question
  question,
  options = [],
  theme = DARK_THEME,
}) => {
  return (
    <Box
      flexDirection="column"
      marginTop={1}
      marginBottom={1}
      marginLeft={8}
      marginRight={8}
    >
      <Box
        flexDirection="column"
        borderStyle="round"
        borderColor={theme.border_focused}
        paddingLeft={1}
        paddingRight={1}
      >
        <Box>
          <Text bold color={theme.accent}>Clarification Needed: </Text>
          <Text color={theme.text}>{question}</Text>
        </Box>

        {options.length > 0 && (
          <Box flexDirection="column" marginTop={1} paddingLeft={1}>
            {options.map((opt, idx) => (
              <Box key={idx}>
                <Text color={theme.accent}>{idx + 1}. </Text>
                <Text color={theme.text_dim}>{opt}</Text>
              </Box>
            ))}
          </Box>
        )}

        <Box marginTop={1}>
          <Text color={theme.text_faint}>Type your response or option number in the composer below</Text>
        </Box>
      </Box>
    </Box>
  );
};

