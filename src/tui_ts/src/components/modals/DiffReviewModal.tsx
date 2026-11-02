import React, { useState, useEffect } from 'react';
import { Box, Text, useInput, useStdin } from 'ink';
import { exec } from 'node:child_process';
import type { ThemeTokens } from '../../types.js';
import { DARK_THEME } from '../../theme/tokens.js';

export interface DiffReviewModalProps {
  onClose: () => void;
  theme?: ThemeTokens;
  columns?: number;
  rows?: number;
}

export const DiffReviewModal: React.FC<DiffReviewModalProps> = ({
  onClose,
  theme = DARK_THEME,
  columns,
  rows,
}) => {
  const [diffText, setDiffText] = useState<string>('Loading workspace changes...');

  useEffect(() => {
    exec('git diff --no-color -U3 2>/dev/null', (err, stdout) => {
      if (err || !stdout.trim()) {
        exec('git status -s 2>/dev/null', (sErr, sOut) => {
          if (!sErr && sOut.trim()) {
            setDiffText('Untracked / Modified files:\n' + sOut);
          } else {
            setDiffText('No modified files detected in workspace.');
          }
        });
      } else {
        setDiffText(stdout);
      }
    });
  }, []);

  const { isRawModeSupported } = useStdin();

  useInput((_input, key) => {
    if (key.escape) {
      onClose();
    }
  }, { isActive: Boolean(isRawModeSupported) });

  const termCols = columns || (typeof process !== 'undefined' && process.stdout?.columns ? process.stdout.columns : 80);
  const termRows = rows || (typeof process !== 'undefined' && process.stdout?.rows ? process.stdout.rows : 24);
  const cardWidth = Math.min(85, Math.max(36, termCols - 4));
  const maxLines = Math.max(4, termRows - 12);
  const lines = diffText.split('\n').slice(0, maxLines);
  const activeGold = theme.brand_gold || theme.accent;

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
          Workspace Diff Review
        </Text>
      </Box>
      <Box justifyContent="center" marginBottom={1}>
        <Text color={theme.accent}>Review file changes and modifications</Text>
      </Box>

      {/* Diff Content Box */}
      <Box
        flexDirection="column"
        borderStyle="round"
        borderColor={theme.border_idle}
        paddingLeft={1}
        paddingRight={1}
        minHeight={6}
        marginBottom={1}
      >
        {lines.map((l, idx) => {
          let lineCol = theme.text_dim;
          if (l.startsWith('+')) lineCol = theme.success;
          else if (l.startsWith('-')) lineCol = theme.error;
          else if (l.startsWith('@@')) lineCol = theme.accent;

          return (
            <Text key={idx} color={lineCol}>
              {l || ' '}
            </Text>
          );
        })}
      </Box>

      <Box justifyContent="center">
        <Text color={theme.text_faint}>[Esc] Dismiss</Text>
      </Box>
    </Box>
  );
};

