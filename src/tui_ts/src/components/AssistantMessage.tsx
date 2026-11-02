import React from 'react';
import { Box, Text } from 'ink';
import type { ThemeTokens } from '../types.js';
import { DARK_THEME } from '../theme/tokens.js';
import { CommandBox } from './CommandBox.js';

export interface AssistantMessageProps {
  content: string;
  theme?: ThemeTokens;
  horizontalMargin?: number;
  columns?: number;
}

interface ContentBlock {
  type: 'text' | 'code';
  content: string;
  language?: string;
}

function parseBlocks(markdown: string): ContentBlock[] {
  const blocks: ContentBlock[] = [];
  const lines = markdown.split('\n');
  let currentText: string[] = [];
  let inCode = false;
  let codeLang = '';
  let currentCode: string[] = [];

  for (const line of lines) {
    // Check condition: line.trim().startsWith('```')
    if (line.trim().startsWith('```')) {
      if (inCode) {
        // End code block
        blocks.push({
          type: 'code',
          content: currentCode.join('\n'),
          language: codeLang || 'code',
        });
        currentCode = [];
        inCode = false;
        codeLang = '';
      } else {
        // Start code block
        if (currentText.length > 0) {
          blocks.push({ type: 'text', content: currentText.join('\n') });
          currentText = [];
        }
        inCode = true;
        codeLang = line.trim().slice(3).trim();
      }
    } else if (inCode) {
      currentCode.push(line);
    } else {
      currentText.push(line);
    }
  }

  if (inCode && currentCode.length > 0) {
    blocks.push({
      type: 'code',
      content: currentCode.join('\n'),
      language: codeLang || 'code',
    });
  } else if (currentText.length > 0) {
    blocks.push({ type: 'text', content: currentText.join('\n') });
  }

  return blocks;
}

// Regex matching inline formatting tokens:
// 1. Inline code: `code`
// 2. Bold: **text**
// 3. Italic: *text* (excluding asterisks that are part of **)
// 4. URLs: http:// or https://
// 5. File paths or commands
const INLINE_TOKEN_REGEX = /(```[\s\S]*?```|`[^`\n]+`|\*\*[^*\n]+\*\*|\*[^*\n]+\*|https?:\/\/[^\s)]+|\/(?:[a-zA-Z0-9_-]+)|(?:(?:\/[\w.-]+)+\/?)|(?:\b[\w.-]+\.(?:py|ts|tsx|js|jsx|json|md|txt|sh|toml|yaml|yml|html|css|pdf|dwg)\b))/g;

export function renderInlineMarkdown(text: string, theme: ThemeTokens): React.ReactNode {
  const activeGold = theme.brand_gold || theme.accent;
  const parts = text.split(INLINE_TOKEN_REGEX);

  return (
    <Text>
      {parts.map((part, idx) => {
        if (!part) return null;

        // Inline code: `code` -> gold, backticks stripped
        if (part.startsWith('`') && part.endsWith('`') && part.length >= 2) {
          const codeText = part.slice(1, -1);
          return (
            <Text key={idx} bold color={activeGold}>
              {codeText}
            </Text>
          );
        }

        // Bold: **text** -> bold in text color, asterisks stripped
        if (part.startsWith('**') && part.endsWith('**') && part.length >= 4) {
          const boldText = part.slice(2, -2);
          return (
            <Text key={idx} bold color={theme.text}>
              {boldText}
            </Text>
          );
        }

        // Italic: *text* -> italic in text color, asterisks stripped
        if (part.startsWith('*') && part.endsWith('*') && part.length >= 2) {
          const italicText = part.slice(1, -1);
          return (
            <Text key={idx} italic color={theme.text}>
              {italicText}
            </Text>
          );
        }

        // URL, file path, or slash command: highlight in active gold
        if (
          part.startsWith('http://') ||
          part.startsWith('https://') ||
          part.startsWith('/') ||
          /\.[a-zA-Z0-9]+$/.test(part)
        ) {
          return (
            <Text key={idx} bold color={activeGold}>
              {part}
            </Text>
          );
        }

        return (
          <Text key={idx} color={theme.text}>
            {part}
          </Text>
        );
      })}
    </Text>
  );
}

// Define function renderFormattedLine(line: string, theme: ThemeTokens)
function renderFormattedLine(line: string, theme: ThemeTokens): React.ReactNode {
  // Define constant activeGold set to theme.brand_gold || theme.accent;
  const activeGold = theme.brand_gold || theme.accent;
  const trimmed = line.trim();

  if (!trimmed) {
    return <Text>{' '}</Text>;
  }

  // Headings: # H1, ## H2, ### H3
  if (line.startsWith('#')) {
    const text = line
      .replace(/^#+\s*/, '')
      .replace(/[\u{1F600}-\u{1F64F}\u{1F300}-\u{1F5FF}\u{1F680}-\u{1F6FF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}]/gu, '')
      .trim();
    return (
      <Box marginTop={1} marginBottom={0}>
        <Text bold color={theme.text}>
          {text}
        </Text>
      </Box>
    );
  }

  // Bullet list items: * item, - item, • item
  if (trimmed.startsWith('* ') || trimmed.startsWith('- ') || trimmed.startsWith('• ')) {
    const bulletContent = trimmed.slice(2);
    return (
      <Box flexDirection="row">
        <Text color={activeGold}>• </Text>
        <Box flexGrow={1}>
          {renderInlineMarkdown(bulletContent, theme)}
        </Box>
      </Box>
    );
  }

  // Numbered list items: 1. item, 2. item
  const numMatch = trimmed.match(/^(\d+\.)\s+(.*)/);
  if (numMatch && numMatch[1] && numMatch[2]) {
    return (
      <Box flexDirection="row">
        <Text bold color={activeGold}>
          {numMatch[1]}{' '}
        </Text>
        <Box flexGrow={1}>
          {renderInlineMarkdown(numMatch[2], theme)}
        </Box>
      </Box>
    );
  }

  // Regular paragraph line with inline markdown formatting
  return renderInlineMarkdown(line, theme);
}

/**
 * Assistant message component:
 * - 2-cell gutter on the left with dim '◦ ' marker on the first line only.
 * - Full markdown rendering: bold, inline code (backticks stripped), bullet lists, code boxes.
 * - Zero raw markdown tokens or unparsed symbols leaked into the UI.
 */
export const AssistantMessage: React.FC<AssistantMessageProps> = ({
  content,
  theme = DARK_THEME,
  horizontalMargin,
  columns,
}) => {
  const clean = content.trim();
  if (!clean) return null;

  const termCols = columns || (typeof process !== 'undefined' && process.stdout?.columns ? process.stdout.columns : 80);
  const hMargin = horizontalMargin !== undefined ? horizontalMargin : (termCols < 90 ? 2 : 4);

  const blocks = parseBlocks(clean);

  return (
    <Box
      flexDirection="row"
      marginTop={1}
      marginBottom={1}
      marginLeft={hMargin}
      marginRight={hMargin}
    >
      {/* 2-cell gutter with '◦ ' marker on the first line */}
      <Box width={2} flexShrink={0}>
        <Text color={theme.text_faint}>◦ </Text>
      </Box>

      {/* Main message content column */}
      <Box flexDirection="column" flexGrow={1}>
        {blocks.map((block, bIdx) => {
          if (block.type === 'code') {
            return (
              <Box key={bIdx} marginTop={1} marginBottom={1}>
                <CommandBox
                  code={block.content}
                  language={block.language}
                  theme={theme}
                />
              </Box>
            );
          }

          const lines = block.content.split('\n');
          return (
            <Box key={bIdx} flexDirection="column" marginBottom={bIdx < blocks.length - 1 ? 1 : 0}>
              {lines.map((line, lIdx) => (
                <Box key={lIdx}>
                  {renderFormattedLine(line, theme)}
                </Box>
              ))}
            </Box>
          );
        })}
      </Box>
    </Box>
  );
};
