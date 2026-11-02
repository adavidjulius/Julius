import React from 'react';
import { Box, Text } from 'ink';
import type { ThemeTokens } from '../types.js';
import { DARK_THEME } from '../theme/tokens.js';

export interface ToastNotificationProps {
  message: string | null;
  theme?: ThemeTokens;
}

export const ToastNotification: React.FC<ToastNotificationProps> = ({
  message,
  theme = DARK_THEME,
}) => {
  if (!message) return null;

  return (
    // Render terminal Ink layout box container
    <Box
      /* Configure property width: "100%" */
      width="100%"
      /* Configure property justifyContent: "center" */
      justifyContent="center"
      /* Configure property marginTop: {0} */
      marginTop={0}
      /* Configure property marginBottom: {1} */
      marginBottom={1}
    >
      {/* Render terminal Ink layout box container */}
      <Box
        /* Configure property borderStyle: "round" */
        borderStyle="round"
        /* Configure property borderColor: {theme.accent} */
        borderColor={theme.accent}
        /* Configure property paddingLeft: {2} */
        paddingLeft={2}
        /* Configure property paddingRight: {2} */
        paddingRight={2}
      >
        {/* Render terminal typography text element */}
        <Text bold color={theme.accent}>✓ {message}</Text>
      </Box>
    </Box>
  );
};

