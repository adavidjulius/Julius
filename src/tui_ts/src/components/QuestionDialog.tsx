import React, { useState } from 'react';
import { Box, Text, useInput, useStdin } from 'ink';
import type { ThemeTokens, QuestionPreviewOption } from '../types.js';
import { DARK_THEME } from '../theme/tokens.js';

export interface QuestionDialogProps {
  question: string;
  options?: (string | QuestionPreviewOption)[];
  previewOptions?: QuestionPreviewOption[];
  onSelectOption?: (option: string | QuestionPreviewOption, index: number) => void;
  theme?: ThemeTokens;
  columns?: number;
}

export const QuestionDialog: React.FC<QuestionDialogProps> = ({
  question,
  options = [],
  previewOptions,
  onSelectOption,
  theme = DARK_THEME,
  columns,
}) => {
  const { isRawModeSupported } = useStdin();
  const [focusedIndex, setFocusedIndex] = useState(0);

  // Normalize options to structured preview items if possible
  const rawList: (string | QuestionPreviewOption)[] = previewOptions && previewOptions.length > 0 ? previewOptions : options;
  const normalizedOptions: QuestionPreviewOption[] = rawList.map((opt) => {
    if (typeof opt === 'string') {
      return { label: opt, description: '' };
    }
    return opt;
  });

  const hasAnyPreview = normalizedOptions.some((opt) => Boolean(opt.preview && opt.preview.trim()));
  const termCols = columns || (typeof process !== 'undefined' && process.stdout?.columns ? process.stdout.columns : 80);
  const activeGold = theme.brand_gold || theme.accent || '#c8b896';

  useInput((input, key) => {
    if (normalizedOptions.length === 0) return;

    if (key.upArrow) {
      setFocusedIndex((prev) => (prev > 0 ? prev - 1 : normalizedOptions.length - 1));
      return;
    }
    if (key.downArrow) {
      setFocusedIndex((prev) => (prev < normalizedOptions.length - 1 ? prev + 1 : 0));
      return;
    }
    if (key.return) {
      const chosen = normalizedOptions[focusedIndex];
      if (chosen && onSelectOption) {
        onSelectOption(chosen, focusedIndex);
      }
      return;
    }

    const num = parseInt(input, 10);
    if (!isNaN(num) && num >= 1 && num <= normalizedOptions.length) {
      setFocusedIndex(num - 1);
      const chosen = normalizedOptions[num - 1];
      if (chosen && onSelectOption) {
        onSelectOption(chosen, num - 1);
      }
    }
  }, { isActive: Boolean(isRawModeSupported) });

  const currentPreview = normalizedOptions[focusedIndex]?.preview || '';

  return (
    <Box
      flexDirection="column"
      marginTop={1}
      marginBottom={1}
      paddingLeft={termCols < 90 ? 1 : 2}
      paddingRight={termCols < 90 ? 1 : 2}
    >
      <Box
        flexDirection="column"
        borderStyle="round"
        borderColor={theme.border_focused}
        paddingLeft={1}
        paddingRight={1}
        paddingTop={0}
        paddingBottom={0}
      >
        <Box marginBottom={1}>
          <Text bold color={activeGold}>Clarification / Selection: </Text>
          <Text color={theme.text} bold>{question}</Text>
        </Box>

        {hasAnyPreview && termCols >= 70 ? (
          /* Side-by-side Preview Mode */
          <Box flexDirection="row" width="100%">
            {/* Left: Options list */}
            <Box flexDirection="column" width="45%" paddingRight={1}>
              {normalizedOptions.map((opt, idx) => {
                const isSelected = idx === focusedIndex;
                return (
                  <Box key={idx} marginBottom={0}>
                    <Text color={isSelected ? activeGold : theme.text_dim} bold={isSelected}>
                      {isSelected ? '› ' : '  '}{idx + 1}. {opt.label}
                    </Text>
                    {opt.description ? (
                      <Text color={theme.text_faint}> — {opt.description}</Text>
                    ) : null}
                  </Box>
                );
              })}
            </Box>

            {/* Right: Bordered Preview Box */}
            <Box
              flexDirection="column"
              width="55%"
              borderStyle="single"
              borderColor={theme.border_subtle || theme.border_idle}
              paddingLeft={1}
              paddingRight={1}
            >
              <Box marginBottom={0}>
                <Text color={theme.text_dim} bold underline>Preview</Text>
              </Box>
              <Text color={theme.text}>
                {currentPreview || '(No preview content for this option)'}
              </Text>
            </Box>
          </Box>
        ) : (
          /* Standard Vertical List Mode */
          <Box flexDirection="column" marginTop={0}>
            {normalizedOptions.map((opt, idx) => {
              const isSelected = idx === focusedIndex;
              return (
                <Box key={idx} marginBottom={0}>
                  <Text color={isSelected ? activeGold : theme.accent} bold={isSelected}>
                    {isSelected ? '› ' : '  '}{idx + 1}. {opt.label}
                  </Text>
                  {opt.description ? (
                    <Text color={theme.text_dim}> — {opt.description}</Text>
                  ) : null}
                </Box>
              );
            })}
          </Box>
        )}

        <Box marginTop={1}>
          <Text color={theme.text_faint}>
            [Up/Down] Select  ·  [1-{normalizedOptions.length}] Direct  ·  [Enter] Confirm or type reply in composer
          </Text>
        </Box>
      </Box>
    </Box>
  );
};
