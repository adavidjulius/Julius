import React, { useState } from 'react';
import { Box, Text, useInput, useStdin } from 'ink';
import type { ThemeTokens, ModelOption, ReasoningEffort } from '../../types.js';
import { DARK_THEME } from '../../theme/tokens.js';

export interface ModelPickerModalProps {
  models: ModelOption[];
  activeModel: string;
  activeEffort?: ReasoningEffort;
  onSelect: (modelId: string, effort?: ReasoningEffort) => void;
  onClose: () => void;
  theme?: ThemeTokens;
  columns?: number;
  rows?: number;
}

const EFFORT_LEVELS: ReasoningEffort[] = ['low', 'medium', 'high', 'xhigh', 'max'];

export const ModelPickerModal: React.FC<ModelPickerModalProps> = ({
  models,
  activeModel,
  activeEffort = 'high',
  onSelect,
  onClose,
  theme = DARK_THEME,
  columns,
  rows,
}) => {
  const { isRawModeSupported } = useStdin();
  const activeIdx = models.findIndex(
    (m) => m.id === activeModel ||
      (activeModel === 'nvidia' && m.id === 'nvidia/nemotron-3-ultra-550b-a55b') ||
      (m.id === 'nvidia' && activeModel === 'nvidia/nemotron-3-ultra-550b-a55b')
  );
  const [selectedIndex, setSelectedIndex] = useState(activeIdx >= 0 ? activeIdx : 0);
  const [selectedEffort, setSelectedEffort] = useState<ReasoningEffort>(activeEffort);
  const [activeTab, setActiveTab] = useState<'model' | 'effort'>('model');

  useInput((input, key) => {
    if (key.escape) {
      onClose();
      return;
    }

    if (key.tab) {
      setActiveTab((prev) => (prev === 'model' ? 'effort' : 'model'));
      return;
    }

    if (key.return) {
      const selected = models[selectedIndex];
      if (selected) {
        onSelect(selected.id, selectedEffort);
      }
      return;
    }

    if (activeTab === 'model') {
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

      const num = parseInt(input, 10);
      if (!isNaN(num) && num >= 1 && num <= models.length) {
        const selected = models[num - 1];
        if (selected) {
          onSelect(selected.id, selectedEffort);
        }
        return;
      }
    } else {
      // Effort tab navigation
      if (key.downArrow || key.rightArrow) {
        const idx = EFFORT_LEVELS.indexOf(selectedEffort);
        setSelectedEffort(EFFORT_LEVELS[(idx + 1) % EFFORT_LEVELS.length] || 'high');
        return;
      }
      if (key.upArrow || key.leftArrow) {
        const idx = EFFORT_LEVELS.indexOf(selectedEffort);
        const next = (idx - 1 + EFFORT_LEVELS.length) % EFFORT_LEVELS.length;
        setSelectedEffort(EFFORT_LEVELS[next] || 'high');
        return;
      }
    }
  }, { isActive: Boolean(isRawModeSupported) });

  const activeGold = theme.brand_gold || theme.accent || '#c8b896';
  const termCols = columns || (typeof process !== 'undefined' && process.stdout?.columns ? process.stdout.columns : 80);
  const cardWidth = Math.min(74, Math.max(36, termCols - 4));
  // Unselected text in grey, selected in brand gold
  const greyText = '#9ca3af';

  return (
    <Box
      flexDirection="column"
      width={cardWidth}
      borderStyle="round"
      borderColor={theme.border_idle || '#3e3e42'}
      paddingLeft={termCols < 60 ? 1 : 2}
      paddingRight={termCols < 60 ? 1 : 2}
      marginTop={0}
      marginBottom={1}
      alignSelf="center"
    >
      <Box marginBottom={1} justifyContent="space-between">
        <Text bold color={activeGold}>
          Select Reasoning Model
        </Text>
        <Text color={greyText}>
          Tab: <Text bold color={activeTab === 'model' ? activeGold : greyText}>[1] Model</Text> · <Text bold color={activeTab === 'effort' ? activeGold : greyText}>[2] Effort</Text>
        </Text>
      </Box>

      {activeTab === 'model' ? (
        <Box flexDirection="column" marginBottom={1}>
          {models.map((m, idx) => {
            const isHighlighted = idx === selectedIndex;
            const isActive = m.id === activeModel;

            return (
              <Box key={m.id}>
                <Text color={isHighlighted ? activeGold : greyText} bold={isHighlighted}>
                  {isHighlighted ? '› ' : '  '}{idx + 1}. {m.name}
                </Text>
                {isActive && (
                  <Text color={activeGold} bold>
                    {' '}(active)
                  </Text>
                )}
              </Box>
            );
          })}
        </Box>
      ) : (
        <Box flexDirection="column" marginBottom={1}>
          <Box marginBottom={0}>
            <Text color={theme.text_faint}>Reasoning effort for subagents and complex tasks:</Text>
          </Box>
          {EFFORT_LEVELS.map((eff) => {
            const isSelected = eff === selectedEffort;
            return (
              <Box key={eff}>
                <Text color={isSelected ? activeGold : greyText} bold={isSelected}>
                  {isSelected ? '› ' : '  '}{eff.toUpperCase()}
                </Text>
                {eff === activeEffort && (
                  <Text color={theme.text_faint}> (current default)</Text>
                )}
              </Box>
            );
          })}
        </Box>
      )}

      <Box>
        <Text color={theme.text_faint}>
          [Tab] Switch Tab · [Up/Down] Navigate · [Enter] Confirm · [Esc] Cancel
        </Text>
      </Box>
    </Box>
  );
};
