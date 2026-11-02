import React from 'react';
import { Box, Text } from 'ink';
import type { ThemeTokens } from '../types.js';
import { DARK_THEME } from '../theme/tokens.js';

export interface ConfirmationDialogProps {
  actionName: string;
  args?: Record<string, unknown>;
  theme?: ThemeTokens;
}

export const ConfirmationDialog: React.FC<ConfirmationDialogProps> = ({
  // Import or destructure parameter actionName
  actionName,
  args = {},
  theme = DARK_THEME,
}) => {
  const brandGold = theme.brand_gold || theme.accent || '#c8b896';
  const argsStr = Object.keys(args).length > 0 ? JSON.stringify(args, null, 2) : '';

  return (
    <Box
      flexDirection="column"
      marginTop={1}
      marginBottom={1}
      paddingLeft={2}
      paddingRight={2}
    >
      <Box
        flexDirection="column"
        borderStyle="round"
        borderColor={brandGold}
        paddingLeft={1}
        paddingRight={1}
        paddingTop={0}
        paddingBottom={0}
      >
        <Box>
          <Text bold color={brandGold}>
            Permission Required:{' '}
          </Text>
          <Text color={theme.text}>Agent requests to execute </Text>
          <Text bold color={brandGold}>
            {actionName}
          </Text>
        </Box>

        {argsStr && (
          <Box marginTop={1} paddingLeft={1}>
            <Text color={theme.text_dim}>{argsStr}</Text>
          </Box>
        )}

        <Box marginTop={1}>
          <Text color={theme.text_faint}>Press </Text>
          <Text bold color={theme.success}>[Y] Allow</Text>
          <Text color={theme.text_faint}> or </Text>
          <Text bold color={theme.error}>[N] Deny</Text>
        </Box>
      </Box>
    </Box>
  );
};

