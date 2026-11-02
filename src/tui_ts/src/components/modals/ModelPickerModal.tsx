import React, { useState } from 'react';
import { Box, Text, useInput, useStdin } from 'ink';
import type { ThemeTokens, ModelOption } from '../../types.js';
import { DARK_THEME } from '../../theme/tokens.js';

export interface ModelPickerModalProps {
  models: ModelOption[];
  activeModel: string;
  onSelect: (modelId: string) => void;
  onClose: () => void;
  theme?: ThemeTokens;
  columns?: number;
  rows?: number;
}

export const ModelPickerModal: React.FC<ModelPickerModalProps> = ({
  models,
  activeModel,
  onSelect,
  onClose,
  theme = DARK_THEME,
  columns,
  rows,
}) => {
  const { isRawModeSupported } = useStdin();
  const activeIdx = models.findIndex((m) => m.id === activeModel);
  const [selectedIndex, setSelectedIndex] = useState(activeIdx >= 0 ? activeIdx : 0);

  useInput((input, key) => {
    if (key.escape) {
      onClose();
      return;
    }

    if (key.return) {
      const selected = models[selectedIndex];
      if (selected) {
        onSelect(selected.id);
      }
      return;
    }

    // Support both single key events and multiple rapid bundled arrow sequences
    const downMatches = input ? input.match(/\x1b\[B|j/g) : null;
    const upMatches = input ? input.match(/\x1b\[A|k/g) : null;
    const downCount = (downMatches ? downMatches.length : 0) || (key.downArrow ? 1 : 0);
    const upCount = (upMatches ? upMatches.length : 0) || (key.upArrow ? 1 : 0);

    if (downCount > 0 && models.length > 0) {
      setSelectedIndex((prev) => (prev + downCount) % models.length);
      return;
    }

    if (upCount > 0 && models.length > 0) {
      setSelectedIndex((prev) => {
        const next = (prev - upCount) % models.length;
        return next < 0 ? next + models.length : next;
      });
      return;
    }

    // Number keys 1-9 for direct model selection
    const num = parseInt(input, 10);
    if (!isNaN(num) && num >= 1 && num <= models.length) {
      const selected = models[num - 1];
      if (selected) {
        onSelect(selected.id);
      }
      return;
    }
  }, { isActive: Boolean(isRawModeSupported) });

  const activeGold = theme.brand_gold || theme.accent || '#c8b896';
  const termCols = columns || (typeof process !== 'undefined' && process.stdout?.columns ? process.stdout.columns : 80);
  const termRows = rows || (typeof process !== 'undefined' && process.stdout?.rows ? process.stdout.rows : 24);
  const cardWidth = Math.min(78, Math.max(36, termCols - 4));
  const isShortScreen = termRows <= 32;

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
      marginBottom={isShortScreen ? 0 : 1}
      alignSelf="center"
    >
      <Box justifyContent="center">
        <Text bold color={theme.text}>
          Select Reasoning Model
        </Text>
      </Box>
      {!isShortScreen && (
        <Box justifyContent="center" marginBottom={1}>
          <Text color={activeGold}>
            Choose active neural provider for reasoning & tool execution
          </Text>
        </Box>
      )}

      {/* Inner options container */}
      <Box
        flexDirection="column"
        borderStyle="round"
        borderColor={theme.border_idle}
        paddingLeft={1}
        paddingRight={1}
        paddingTop={0}
        paddingBottom={0}
        marginBottom={1}
      >
        {models.map((m, idx) => {
          const isHighlighted = idx === selectedIndex;
          const isActive = m.id === activeModel;

          return (
            <Box
              key={m.id}
              justifyContent="space-between"
              paddingLeft={1}
              paddingRight={1}
            >
              <Box>
                <Text color={isHighlighted ? activeGold : theme.text} bold={isHighlighted}>
                  {isHighlighted ? '❯ ' : '  '}{idx + 1}. {m.name}
                </Text>
                {isActive && (
                  <Text color={theme.success} bold>
                    {' '}(active)
                  </Text>
                )}
              </Box>
              <Text color={isHighlighted ? activeGold : theme.text_dim} bold={isHighlighted}>
                {m.desc}
              </Text>
            </Box>
          );
        })}
      </Box>

      <Box justifyContent="center">
        <Text color={theme.text_faint}>
          [↑/↓] Navigate  ·  [1-9] Direct select  ·  [Enter] Confirm  ·  [Esc] Cancel
        </Text>
      </Box>
    </Box>
  );
};
