import React from 'react';
import { Box, Text, useInput, useStdin } from 'ink';
import type { ThemeTokens } from '../../types.js';
import { DARK_THEME } from '../../theme/tokens.js';

export interface HelpModalProps {
  onClose: () => void;
  theme?: ThemeTokens;
  columns?: number;
  rows?: number;
}

const SHORTCUTS = [
  ['Enter', 'Send prompt'],
  ['Shift+Enter', 'Insert new line'],
  ['Esc', 'Cancel action / Dismiss modal'],
  ['↑ / ↓', 'Navigate prompt history'],
  ['Ctrl+I', 'Inspect running action & live terminal output'],
  ['Ctrl+T', 'Expand / collapse thinking reasoning'],
  ['Ctrl+Y', 'Copy last assistant answer (with toast)'],
  ['Ctrl+O', 'Expand / collapse tool execution steps'],
  ['F2', 'Switch reasoning model'],
  ['?', 'Toggle this shortcut guide'],
];

export const HelpModal: React.FC<HelpModalProps> = ({
  onClose,
  theme = DARK_THEME,
  columns,
  rows,
}) => {
  const { isRawModeSupported } = useStdin();

  useInput((input, key) => {
    if (key.escape || key.return || input === '?' || input === 'q' || input === ' ') {
      onClose();
    }
  }, { isActive: Boolean(isRawModeSupported) });

  const activeGold = theme.brand_gold || theme.accent;
  const termCols = columns || (typeof process !== 'undefined' && process.stdout?.columns ? process.stdout.columns : 80);
  const termRows = rows || (typeof process !== 'undefined' && process.stdout?.rows ? process.stdout.rows : 24);
  const cardWidth = Math.min(78, Math.max(36, termCols - 4));
  const isShortScreen = termRows < 24;

  return (
    <Box
      flexDirection="column"
      width={cardWidth}
      borderStyle="round"
      borderColor={activeGold}
      paddingLeft={termCols < 60 ? 1 : 2}
      paddingRight={termCols < 60 ? 1 : 2}
      paddingTop={0}
      paddingBottom={0}
      marginTop={0}
      marginBottom={1}
      alignSelf="center"
    >
      <Box justifyContent="center">
        <Text bold color={theme.text}>
          Keyboard Shortcuts
        </Text>
      </Box>
      {!isShortScreen && (
        <Box justifyContent="center" marginBottom={1}>
          <Text color={activeGold}>Quick keys and navigation controls</Text>
        </Box>
      )}

      {/* Inner table box */}
      <Box
        flexDirection="column"
        borderStyle="round"
        borderColor={theme.border_idle}
        paddingLeft={1}
        paddingRight={1}
        marginBottom={1}
      >
        {SHORTCUTS.map(([key, desc]) => (
          <Box key={key} justifyContent="space-between">
            <Box width={20}>
              <Text bold color={theme.accent}>
                {key}
              </Text>
            </Box>
            <Box flexGrow={1}>
              <Text color={theme.text_dim}>{desc}</Text>
            </Box>
          </Box>
        ))}
      </Box>

      <Box justifyContent="center">
        <Text color={theme.text_faint}>[Esc] or [?] Dismiss</Text>
      </Box>
    </Box>
  );
};

