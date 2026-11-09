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

export interface ContentBlock {
  type: 'text' | 'code' | 'table' | 'diagram';
  content: string;
  language?: string;
  tableRows?: string[][];
}

const BOX_DRAWING_CHARS = /[┌─┐│└┘╔═╗║╚╝├┤┬┴┼▲▼►◄──]/;

export function stripOrReplaceEmojis(text: string): string {
  if (!text) return '';
  const withoutThinking = text
    .replace(/<think>[\s\S]*?<\/think>/gi, '')
    .replace(/<thought>[\s\S]*?<\/thought>/gi, '')
    .replace(/<reasoning>[\s\S]*?<\/reasoning>/gi, '')
    .replace(/<\/?(?:think|thought|reasoning)>/gi, '');
  return withoutThinking
    .replace(/[✅✔☑]/g, '[DONE]')
    .replace(/[❌✖✗]/g, '[FAIL]')
    .replace(/[⚠️⚡]/g, '[!]')
    .replace(/[💡]/g, '[INFO]')
    .replace(/[🚀]/g, '[RUN]')
    .replace(/[🔒]/g, '[LOCK]')
    .replace(/[🔍🔎]/g, '[FIND]')
    .replace(/[\u{1F600}-\u{1F64F}\u{1F300}-\u{1F5FF}\u{1F680}-\u{1F6FF}\u{1F700}-\u{1F77F}\u{1F780}-\u{1F7FF}\u{1F800}-\u{1F8FF}\u{1F900}-\u{1F9FF}\u{1FA00}-\u{1FA6F}\u{1FA70}-\u{1FAFF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}]/gu, '');
}

export function parseTableRow(line: string): string[] {
  let trimmed = line.trim();
  if (trimmed.startsWith('|')) trimmed = trimmed.slice(1);
  if (trimmed.endsWith('|')) trimmed = trimmed.slice(0, -1);
  return trimmed.split('|').map((c) => c.trim());
}

export function isTableDelimiter(line: string): boolean {
  const trimmed = line.trim();
  if (!trimmed.includes('|') && !trimmed.includes('-')) return false;
  const cells = parseTableRow(trimmed);
  return cells.length >= 2 && cells.every((c) => /^:?-{2,}:?$/.test(c.trim()));
}

export function isTableLine(line: string): boolean {
  const trimmed = line.trim();
  if (!trimmed.includes('|')) return false;
  const cells = parseTableRow(trimmed);
  return cells.length >= 2;
}

function isCodeBlockText(text: string): boolean {
  const lines = text.trim().split('\n').filter((l) => l.trim().length > 0);
  if (lines.length === 0) return false;
  if (lines[0]?.startsWith('#!/')) return true;

  let codeMatches = 0;
  for (const l of lines) {
    const t = l.trim();
    if (
      t.startsWith('#!/') ||
      t.startsWith('def ') ||
      t.startsWith('class ') ||
      t.startsWith('import ') ||
      t.startsWith('from ') ||
      t.startsWith('return ') ||
      t.startsWith('print(') ||
      t.startsWith('if __name__') ||
      t.startsWith('const ') ||
      t.startsWith('function ')
    ) {
      codeMatches++;
    }
  }
  return codeMatches >= 2 || (lines.length > 2 && codeMatches / lines.length > 0.4);
}

function extractActionContent(text: string): { type: 'text' | 'code'; content: string; language?: string } | null {
  const trimmed = text.trim();
  if (!trimmed.startsWith('{') && !trimmed.startsWith('json{') && !trimmed.includes('"actions":') && !trimmed.includes('"action":')) {
    return null;
  }
  try {
    const cleanJson = trimmed.replace(/^json\s*/, '');
    const parsed = JSON.parse(cleanJson);
    if (typeof parsed === 'object' && parsed !== null) {
      if (parsed.message && typeof parsed.message === 'string') {
        return { type: 'text', content: parsed.message };
      }
      if (parsed.summary && typeof parsed.summary === 'string') {
        return { type: 'text', content: parsed.summary };
      }
      if (Array.isArray(parsed.actions) && parsed.actions.length > 0) {
        const commands: string[] = [];
        for (const a of parsed.actions) {
          const cmd = a.args?.command || a.args?.cmd || a.arguments?.cmd || a.arguments?.command;
          if (cmd) {
            commands.push(cmd);
          } else if (a.args?.summary || a.arguments?.summary) {
            return { type: 'text', content: a.args?.summary || a.arguments?.summary };
          }
        }
        if (commands.length > 0) {
          return { type: 'code', content: commands.join('\n'), language: 'bash' };
        }
      }
      const singleCmd = parsed.args?.command || parsed.args?.cmd || parsed.arguments?.cmd || parsed.arguments?.command;
      if (singleCmd) {
        return { type: 'code', content: singleCmd, language: 'bash' };
      }
    }
  } catch {
    const matchCmd = trimmed.match(/["'](?:cmd|command)["']\s*:\s*["']([^"']+)["']/);
    if (matchCmd && matchCmd[1]) {
      return { type: 'code', content: matchCmd[1].replace(/\\n/g, '\n'), language: 'bash' };
    }
    const matchMsg = trimmed.match(/["'](?:message|summary)["']\s*:\s*["']([^"']+)["']/);
    if (matchMsg && matchMsg[1]) {
      return { type: 'text', content: matchMsg[1].replace(/\\n/g, '\n') };
    }
  }
  return null;
}

export function parseBlocks(markdown: string): ContentBlock[] {
  const cleanMarkdown = stripOrReplaceEmojis(markdown);
  const blocks: ContentBlock[] = [];
  const lines = cleanMarkdown.split('\n');
  let currentText: string[] = [];
  let inCode = false;
  let codeLang = '';
  let currentCode: string[] = [];

  let inTable = false;
  let currentTable: string[] = [];

  const flushText = () => {
    if (currentText.length > 0) {
      const joined = currentText.join('\n');
      const actionContent = extractActionContent(joined);
      if (actionContent) {
        blocks.push(actionContent);
      } else if (isCodeBlockText(joined)) {
        blocks.push({
          type: 'code',
          content: joined.trim(),
          language: joined.includes('def ') || joined.includes('import ') ? 'python' : 'code',
        });
      } else {
        blocks.push({ type: 'text', content: joined });
      }
      currentText = [];
    }
  };

  const flushTable = () => {
    if (currentTable.length > 0) {
      const parsedRows = currentTable.map(parseTableRow);
      // Filter out markdown separator rows (e.g. |---|---| or |:---:|)
      const dataRows = parsedRows.filter(
        (cols) => !cols.every((c) => /^:?[- ]{2,}:?$/.test(c.trim()))
      );
      if (dataRows.length > 0) {
        blocks.push({
          type: 'table',
          content: currentTable.join('\n'),
          tableRows: dataRows,
        });
      }
      currentTable = [];
      inTable = false;
    }
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i] || '';
    const trimmed = line.trim();

    if (trimmed.startsWith('```')) {
      if (inTable) {
        flushTable();
      }
      if (inCode) {
        const codeContent = currentCode.join('\n');
        const isDiagram =
          ['diagram', 'ascii', 'mermaid', 'box'].includes(codeLang.toLowerCase()) ||
          BOX_DRAWING_CHARS.test(codeContent);

        blocks.push({
          type: isDiagram ? 'diagram' : 'code',
          content: codeContent,
          language: codeLang || (isDiagram ? 'diagram' : 'code'),
        });
        currentCode = [];
        inCode = false;
        codeLang = '';
      } else {
        flushText();
        inCode = true;
        codeLang = trimmed.slice(3).trim();
      }
      continue;
    }

    if (inCode) {
      currentCode.push(line);
      continue;
    }

    // Markdown Table Detection (supports with or without outer pipes)
    const isThisTable = isTableLine(line) || isTableDelimiter(line);
    if (isThisTable) {
      if (!inTable) {
        const nextLine = lines[i + 1] || '';
        if (isTableDelimiter(nextLine) || isTableLine(nextLine) || isTableDelimiter(line)) {
          flushText();
          inTable = true;
        }
      }
      if (inTable) {
        currentTable.push(line);
        continue;
      }
    } else if (inTable) {
      flushTable();
    }

    currentText.push(line);
  }

  if (inCode && currentCode.length > 0) {
    blocks.push({
      type: 'code',
      content: currentCode.join('\n'),
      language: codeLang || 'code',
    });
  }
  if (inTable) {
    flushTable();
  }
  flushText();

  return blocks;
}

const INLINE_TOKEN_REGEX = /(```[\s\S]*?```|`[^`\n]+`|\*\*[^*\n]+\*\*|\*[^*\n]+\*|https?:\/\/[^\s)]+|(?:^|\s)\/[a-zA-Z0-9_-]{2,}\b|(?:(?:\/[\w.-]+)+\/?)|(?:\b[\w.-]+\.(?:py|ts|tsx|js|jsx|json|md|txt|sh|toml|yaml|yml|html|css|pdf|dwg)\b))/g;

export function renderInlineMarkdown(text: string, theme: ThemeTokens): React.ReactNode {
  const activeGold = theme.brand_gold || theme.accent;
  const parts = text.split(INLINE_TOKEN_REGEX);

  return (
    <Text>
      {parts.map((part, idx) => {
        if (!part) return null;

        if (part.startsWith('`') && part.endsWith('`') && part.length >= 2) {
          const codeText = part.slice(1, -1);
          return (
            <Text key={idx} bold color={activeGold}>
              {codeText}
            </Text>
          );
        }

        if (part.startsWith('**') && part.endsWith('**') && part.length >= 4) {
          const boldText = part.slice(2, -2);
          return (
            <Text key={idx} bold color={theme.text}>
              {boldText}
            </Text>
          );
        }

        if (part.startsWith('*') && part.endsWith('*') && part.length >= 2) {
          const italicText = part.slice(1, -1);
          return (
            <Text key={idx} italic color={theme.text}>
              {italicText}
            </Text>
          );
        }

        const trimmed = part.trim();
        if (
          trimmed.startsWith('http://') ||
          trimmed.startsWith('https://') ||
          (trimmed.startsWith('/') && trimmed.length >= 3 && !trimmed.includes(' ') && (trimmed.includes('/') && trimmed.indexOf('/', 1) !== -1 || ['/help', '/model', '/diff', '/action', '/clear', '/plan', '/act', '/undo', '/status', '/vitals', '/alerts', '/doctor', '/context', '/cost', '/compact', '/theme', '/exit'].includes(trimmed.toLowerCase()))) ||
          /\.[a-zA-Z0-9]{1,5}$/.test(trimmed)
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

export function renderFormattedLine(line: string, theme: ThemeTokens): React.ReactNode {
  const activeGold = theme.brand_gold || theme.accent;
  const trimmed = line.trim();

  if (!trimmed) {
    return <Text>{' '}</Text>;
  }

  // Headings: strictly 1 to 6 '#' followed by whitespace (not shebangs #! or code comments)
  if (/^#{1,6}[\s\t]+/.test(trimmed)) {
    const text = trimmed
      .replace(/^#{1,6}[\s\t]+/, '')
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

  // Bullet list items
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

  // Numbered list items
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

  return renderInlineMarkdown(line, theme);
}

function getVisibleLength(text: string): number {
  return text
    .replace(/\*\*(.*?)\*\*/g, '$1')
    .replace(/\*(.*?)\*/g, '$1')
    .replace(/`(.*?)`/g, '$1')
    .trim().length;
}

function wrapWord(text: string, maxWidth: number): string[] {
  const clean = text.trim();
  if (!clean) return [''];
  if (getVisibleLength(clean) <= maxWidth) return [clean];

  const words = clean.split(/\s+/);
  const lines: string[] = [];
  let current = '';

  for (const w of words) {
    if (!current) {
      current = w;
    } else if (getVisibleLength(current + ' ' + w) <= maxWidth) {
      current += ' ' + w;
    } else {
      lines.push(current);
      current = w;
    }
  }
  if (current) lines.push(current);
  return lines.length > 0 ? lines : [clean];
}

/**
 * Render Markdown Tables cleanly with aligned columns, cell wrapping, headers in active gold, and subtle dividers.
 */
export function renderTableBlock(rows: string[][], theme: ThemeTokens, termCols: number = 80, hMargin: number = 4): React.ReactNode {
  if (!rows || rows.length === 0) return null;

  const numCols = Math.max(...rows.map((r) => r.length));
  if (numCols === 0) return null;

  // Total available width for table content
  const maxTableWidth = Math.max(36, termCols - (hMargin * 2) - 6);
  // Dividers take (numCols - 1) * 3 chars (' │ ')
  const dividerSpace = (numCols - 1) * 3;
  const availableContentWidth = Math.max(numCols * 8, maxTableWidth - dividerSpace);

  // Measure natural desired width for each column
  const naturalWidths: number[] = new Array(numCols).fill(0);
  for (const row of rows) {
    for (let c = 0; c < numCols; c++) {
      const cellLen = getVisibleLength(row[c] || '');
      naturalWidths[c] = Math.max(naturalWidths[c] || 0, cellLen);
    }
  }

  // Calculate allocated column widths
  const colWidths: number[] = new Array(numCols).fill(0);
  const totalNatural = naturalWidths.reduce((a, b) => a + b, 0);

  if (totalNatural <= availableContentWidth) {
    for (let c = 0; c < numCols; c++) {
      colWidths[c] = Math.max(6, naturalWidths[c] || 6);
    }
  } else {
    // Distribute space proportionally or cap wide columns
    let remainingWidth = availableContentWidth;
    let unallocatedCols = numCols;

    // First allocate fixed columns (<= 16 chars natural)
    for (let c = 0; c < numCols; c++) {
      const nat = naturalWidths[c] || 8;
      if (nat <= 16) {
        colWidths[c] = Math.max(6, nat);
        remainingWidth -= colWidths[c];
        unallocatedCols--;
      }
    }

    // Allocate remaining width to wider columns
    if (unallocatedCols > 0) {
      const widthPerWideCol = Math.max(12, Math.floor(remainingWidth / unallocatedCols));
      for (let c = 0; c < numCols; c++) {
        if (colWidths[c] === 0) {
          colWidths[c] = widthPerWideCol;
        }
      }
    }
  }

  const activeGold = theme.brand_gold || theme.accent;
  const dividerColor = theme.border_idle || '#3e3e42';

  const renderRowLines = (cells: string[], isHeader: boolean, keyPrefix: string) => {
    // Wrap each cell's text to its assigned column width
    const cellLines = cells.map((cell, cIdx) =>
      wrapWord(cell || '', colWidths[cIdx] || 10)
    );
    const maxLineCount = Math.max(1, ...cellLines.map((lines) => lines.length));

    const renderedLines: React.ReactNode[] = [];
    for (let lineIdx = 0; lineIdx < maxLineCount; lineIdx++) {
      const rowContent = cellLines
        .map((lines, cIdx) => {
          const w = colWidths[cIdx] || 10;
          const text = lines[lineIdx] || '';
          return text.padEnd(w);
        })
        .join(' │ ');

      renderedLines.push(
        <Box key={`${keyPrefix}_l${lineIdx}`}>
          <Text bold={isHeader} color={isHeader ? activeGold : theme.text}>
            {rowContent}
          </Text>
        </Box>
      );
    }
    return renderedLines;
  };

  const headerRow = rows[0] || [];
  const bodyRows = rows.slice(1);
  const dividerLine = colWidths.map((w) => '─'.repeat(w)).join('─┼─');

  return (
    <Box
      flexDirection="column"
      marginTop={1}
      marginBottom={1}
      paddingLeft={1}
      paddingRight={1}
    >
      {/* Header Row */}
      {renderRowLines(headerRow, true, 'hdr')}

      {/* Divider */}
      <Box>
        <Text color={dividerColor}>
          {dividerLine}
        </Text>
      </Box>

      {/* Data Rows */}
      {bodyRows.map((r, rIdx) => (
        <Box key={`row_${rIdx}`} flexDirection="column">
          {renderRowLines(r, false, `row_${rIdx}`)}
        </Box>
      ))}
    </Box>
  );
}

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
      <Box width={2} flexShrink={0}>
        <Text color={theme.text_faint}>◦ </Text>
      </Box>

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

          if (block.type === 'diagram') {
            return (
              <Box
                key={bIdx}
                flexDirection="column"
                marginTop={1}
                marginBottom={1}
                borderStyle="round"
                borderColor={theme.border_idle || '#3e3e42'}
                paddingLeft={1}
                paddingRight={1}
              >
                <Text color={theme.brand_gold || theme.accent}>
                  {block.content}
                </Text>
              </Box>
            );
          }

          if (block.type === 'table' && block.tableRows) {
            return (
              <Box key={bIdx}>
                {renderTableBlock(block.tableRows, theme, termCols, hMargin)}
              </Box>
            );
          }

          const lines = block.content.split('\n');
          return (
            <Box key={bIdx} flexDirection="column">
              {lines.map((line, lIdx) => (
                <Box key={lIdx}>{renderFormattedLine(line, theme)}</Box>
              ))}
            </Box>
          );
        })}
      </Box>
    </Box>
  );
};
