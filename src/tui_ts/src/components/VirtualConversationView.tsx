import React from 'react';
import { Box, Text } from 'ink';
import type { ThemeTokens, MessageRecord, ActiveThinkingState, ToolExecutionRecord } from '../types.js';
import { DARK_THEME } from '../theme/tokens.js';
import { JULIUS_BANNER } from './WelcomeView.js';
import { filterRealTools } from './ToolSummary.js';
import {
  parseBlocks,
  renderInlineMarkdown,
  stripOrReplaceEmojis,
  parseTableRow,
  isTableDelimiter,
} from './AssistantMessage.js';

export interface VirtualConversationViewProps {
  messages: MessageRecord[];
  activeThinking: ActiveThinkingState | null;
  runningAction: string;
  streamingAnswer: string;
  currentTurnTools: ToolExecutionRecord[];
  isThinkingExpanded: boolean;
  isToolsExpanded: boolean;
  onToggleThinking: () => void;
  onToggleTools: () => void;
  scrollOffset: number;
  viewportHeight: number;
  columns: number;
  theme?: ThemeTokens;
  horizontalMargin?: number;
  activeModel?: string;
  appMode?: string;
}

export interface VirtualLine {
  id: string;
  node: React.ReactNode;
}

/**
 * Word-wrap a string into array of lines each guaranteed <= maxWidth characters.
 */
export function wrapTextToLines(text: string, maxWidth: number): string[] {
  if (!text) return [''];
  const maxW = Math.max(16, maxWidth);
  const words = text.split(' ');
  const lines: string[] = [];
  let current = '';

  for (const word of words) {
    if (!current) {
      if (word.length > maxW) {
        for (let i = 0; i < word.length; i += maxW) {
          lines.push(word.slice(i, i + maxW));
        }
      } else {
        current = word;
      }
    } else if (current.length + 1 + word.length <= maxW) {
      current += ' ' + word;
    } else {
      lines.push(current);
      if (word.length > maxW) {
        for (let i = 0; i < word.length; i += maxW) {
          const chunk = word.slice(i, i + maxW);
          if (i + maxW < word.length) {
            lines.push(chunk);
          } else {
            current = chunk;
          }
        }
      } else {
        current = word;
      }
    }
  }
  if (current) {
    lines.push(current);
  }
  return lines.length > 0 ? lines : [''];
}

export const VirtualConversationView: React.FC<VirtualConversationViewProps> = ({
  messages,
  activeThinking,
  runningAction,
  streamingAnswer,
  currentTurnTools,
  isThinkingExpanded,
  isToolsExpanded,
  scrollOffset,
  viewportHeight,
  columns,
  theme = DARK_THEME,
  horizontalMargin,
  activeModel,
  appMode = 'auto',
}) => {
  const activeGold = theme.brand_gold || theme.accent || '#c8b896';
  const hMargin = horizontalMargin !== undefined ? horizontalMargin : (columns < 90 ? 2 : 4);
  const outputMargin = hMargin + 4;
  const contentTextWidth = Math.max(20, columns - outputMargin - 4);
  const maxCardWidth = Math.max(24, columns - (hMargin * 2) - 4);

  const virtualLines: VirtualLine[] = [];
  let lineKeySeq = 0;
  const nextId = (prefix: string) => `${prefix}_${lineKeySeq++}`;

  // 1. FULL ASCII BANNER (Item 0 at the very top of history)
  // The full 3D ASCII banner is ALWAYS rendered in signature brand gold, cleanly with zero clutter
  const bannerRawLines = JULIUS_BANNER.split('\n');
  bannerRawLines.forEach((bannerLine, bIdx) => {
    virtualLines.push({
      id: nextId(`banner_${bIdx}`),
      node: (
        <Box flexDirection="row" justifyContent="center" width="100%">
          <Text bold color={activeGold}>
            {bannerLine}
          </Text>
        </Box>
      ),
    });
  });

  virtualLines.push({
    id: nextId('banner_spacer'),
    node: (
      <Box height={1}>
        <Text>{' '}</Text>
      </Box>
    ),
  });

  // Helper to build virtual lines for assistant response content
  const appendAssistantContentLines = (content: string, prefixId: string) => {
    const clean = stripOrReplaceEmojis(content.trim());
    if (!clean) return;

    const blocks = parseBlocks(clean);
    let isFirstLineOfTurn = true;

    for (const block of blocks) {
      if (block.type === 'code') {
        const codeLines = block.content.split('\n');
        const lang = block.language || 'code';
        const boxWidth = Math.min(contentTextWidth, Math.max(20, ...codeLines.map((l) => l.length + 4), lang.length + 8));
        const topHdr = `┌─ [${lang}] ` + '─'.repeat(Math.max(0, boxWidth - lang.length - 7)) + '┐';
        virtualLines.push({
          id: nextId(`${prefixId}_code_top`),
          node: (
            <Box flexDirection="row" marginLeft={outputMargin}>
              <Text color={theme.border_idle || '#3e3e42'}>{topHdr}</Text>
            </Box>
          ),
        });
        for (let cIdx = 0; cIdx < codeLines.length; cIdx++) {
          const cLine = (codeLines[cIdx] || '').slice(0, boxWidth - 4);
          const padded = '│ ' + cLine.padEnd(boxWidth - 4) + ' │';
          virtualLines.push({
            id: nextId(`${prefixId}_code_${cIdx}`),
            node: (
              <Box flexDirection="row" marginLeft={outputMargin}>
                <Text color={activeGold}>{padded}</Text>
              </Box>
            ),
          });
        }
        const btm = '└' + '─'.repeat(Math.max(0, boxWidth - 2)) + '┘';
        virtualLines.push({
          id: nextId(`${prefixId}_code_btm`),
          node: (
            <Box flexDirection="row" marginLeft={outputMargin}>
              <Text color={theme.border_idle || '#3e3e42'}>{btm}</Text>
            </Box>
          ),
        });
        isFirstLineOfTurn = false;
        continue;
      }

      if (block.type === 'table' && block.tableRows && block.tableRows.length > 0) {
        const rows = block.tableRows;
        const numCols = Math.max(...rows.map((r) => r.length));
        const dividerSpace = (numCols - 1) * 3;
        const maxTWidth = Math.max(36, columns - (outputMargin * 2) - 4);
        const availWidth = Math.max(numCols * 8, maxTWidth - dividerSpace);
        const colW = Math.max(6, Math.floor(availWidth / Math.max(1, numCols)));

        const formatRow = (cells: string[]) => {
          return cells.map((c) => (c || '').padEnd(colW).slice(0, colW)).join(' │ ');
        };

        const headerCells = rows[0] || [];
        virtualLines.push({
          id: nextId(`${prefixId}_tbl_hdr`),
          node: (
            <Box flexDirection="row" marginLeft={outputMargin}>
              <Text bold color={activeGold}>
                {formatRow(headerCells)}
              </Text>
            </Box>
          ),
        });
        const dividerLine = new Array(numCols).fill('─'.repeat(colW)).join('─┼─');
        virtualLines.push({
          id: nextId(`${prefixId}_tbl_div`),
          node: (
            <Box flexDirection="row" marginLeft={outputMargin}>
              <Text color={theme.border_idle || '#3e3e42'}>
                {dividerLine}
              </Text>
            </Box>
          ),
        });
        for (let rIdx = 1; rIdx < rows.length; rIdx++) {
          const rowCells = rows[rIdx] || [];
          virtualLines.push({
            id: nextId(`${prefixId}_tbl_row_${rIdx}`),
            node: (
              <Box flexDirection="row" marginLeft={outputMargin}>
                <Text color={theme.text}>
                  {formatRow(rowCells)}
                </Text>
              </Box>
            ),
          });
        }
        isFirstLineOfTurn = false;
        continue;
      }

      // Text block: split paragraphs and wrap
      const rawParaLines = block.content.split('\n');
      for (const pLine of rawParaLines) {
        const trimmed = pLine.trim();
        if (!trimmed) {
          virtualLines.push({
            id: nextId(`${prefixId}_empty`),
            node: (
              <Box height={1} marginLeft={outputMargin}>
                <Text>{' '}</Text>
              </Box>
            ),
          });
          continue;
        }

        const wrapped = wrapTextToLines(trimmed, contentTextWidth - 4);
        for (let wIdx = 0; wIdx < wrapped.length; wIdx++) {
          const wLine = wrapped[wIdx] || '';
          const isLead = isFirstLineOfTurn;
          isFirstLineOfTurn = false;

          virtualLines.push({
            id: nextId(`${prefixId}_txt`),
            node: (
              <Box flexDirection="row" marginLeft={outputMargin}>
                <Box width={2} flexShrink={0}>
                  <Text color={theme.text_faint}>{isLead ? '◦ ' : '  '}</Text>
                </Box>
                <Box flexGrow={1}>
                  {renderInlineMarkdown(wLine, theme)}
                </Box>
              </Box>
            ),
          });
        }
      }
    }

    // Spacer after assistant turn
    virtualLines.push({
      id: nextId(`${prefixId}_spacer`),
      node: (
        <Box height={1}>
          <Text>{' '}</Text>
        </Box>
      ),
    });
  };

  // 2. CONVERSATION TURNS
  for (const m of messages) {
    if (m.role === 'user') {
      const userContent = m.content.trim();
      const rawLines = userContent.split('\n');
      const innerW = maxCardWidth - 4;
      const wrapped = rawLines.flatMap((l) => wrapTextToLines(l, innerW));
      const longest = Math.max(...wrapped.map((l) => l.length), 0);
      const actualW = Math.min(maxCardWidth, Math.max(8, longest + 4));

      // Top hairline border
      const topBorder = '┌' + '─'.repeat(Math.max(0, actualW - 2)) + '┐';
      virtualLines.push({
        id: nextId(`usr_${m.id}_top`),
        node: (
          <Box flexDirection="row" paddingLeft={hMargin}>
            <Text color={theme.border_subtle || '#3e3e42'} dimColor>
              {topBorder}
            </Text>
          </Box>
        ),
      });

      // User card content lines
      wrapped.forEach((lineText, lIdx) => {
        const padded = '│ ' + lineText.padEnd(actualW - 4) + ' │';
        virtualLines.push({
          id: nextId(`usr_${m.id}_line_${lIdx}`),
          node: (
            <Box flexDirection="row" paddingLeft={hMargin}>
              <Text color={theme.text}>{padded}</Text>
            </Box>
          ),
        });
      });

      // Bottom hairline border
      const btmBorder = '└' + '─'.repeat(Math.max(0, actualW - 2)) + '┘';
      virtualLines.push({
        id: nextId(`usr_${m.id}_btm`),
        node: (
          <Box flexDirection="row" paddingLeft={hMargin}>
            <Text color={theme.border_subtle || '#3e3e42'} dimColor>
              {btmBorder}
            </Text>
          </Box>
        ),
      });

      // Spacer after user message
      virtualLines.push({
        id: nextId(`usr_${m.id}_sp`),
        node: (
          <Box height={1}>
            <Text>{' '}</Text>
          </Box>
        ),
      });
      continue;
    }

    // Assistant Turn in history
    // 2a. Thinking indicator strictly ABOVE answer
    if (m.thoughts && m.thoughts.length > 0) {
      const durStr = m.thoughtDurationS ? ` (${m.thoughtDurationS.toFixed(1)}s)` : '';
      virtualLines.push({
        id: nextId(`ast_${m.id}_th_hdr`),
        node: (
          <Box flexDirection="row" marginLeft={outputMargin}>
            <Text color={activeGold}>▾ </Text>
            <Text color={theme.text_faint}>Thinking · Reasoning Flow{durStr}</Text>
          </Box>
        ),
      });
      if (isThinkingExpanded) {
        const fullTh = (m.fullThought || m.thoughts.join('\n')).trim();
        const paragraphs = fullTh.split(/\n+/).map((p) => p.trim()).filter(Boolean);
        paragraphs.forEach((p, pIdx) => {
          const wrappedP = wrapTextToLines(p, contentTextWidth - 4);
          wrappedP.forEach((pLine, pwIdx) => {
            virtualLines.push({
              id: nextId(`ast_${m.id}_th_${pIdx}_${pwIdx}`),
              node: (
                <Box flexDirection="row" marginLeft={outputMargin + 2}>
                  <Text color={theme.text_faint}>{pwIdx === 0 ? '› ' : '  '}{pLine}</Text>
                </Box>
              ),
            });
          });
        });
      }
    }

    // 2b. Tool summary strictly ABOVE assistant response
    if (m.tools && filterRealTools(m.tools).length > 0) {
      const real = filterRealTools(m.tools);
      const dur = real.reduce((acc, t) => acc + (t.duration_s || 0), 0);
      virtualLines.push({
        id: nextId(`ast_${m.id}_tl_hdr`),
        node: (
          <Box flexDirection="row" marginLeft={outputMargin}>
            <Text color={activeGold}>› </Text>
            <Text color={theme.text_faint}>
              Ran {real.length} step{real.length > 1 ? 's' : ''} · {dur.toFixed(1)}s
            </Text>
          </Box>
        ),
      });
      if (isToolsExpanded) {
        real.forEach((t, tIdx) => {
          virtualLines.push({
            id: nextId(`ast_${m.id}_tl_${tIdx}`),
            node: (
              <Box flexDirection="row" marginLeft={outputMargin + 2}>
                <Text color={theme.text_faint}>
                  - {t.tool_name}: {t.command || t.tool_name} ({t.duration_s ? `${t.duration_s.toFixed(1)}s` : 'done'})
                </Text>
              </Box>
            ),
          });
        });
      }
    }

    // 2c. Assistant message content
    appendAssistantContentLines(m.content, `ast_${m.id}`);
  }

  // 3. LIVE TURN (Streaming / Thinking / Tools)
  if (activeThinking) {
    const isThinkingActive = Boolean(activeThinking.isRunning);
    const durStr = activeThinking.durationS ? ` (${activeThinking.durationS.toFixed(1)}s)` : '';
    const label = isThinkingExpanded ? 'Reasoning Flow' : (activeThinking.label || 'Reasoning Flow');
    virtualLines.push({
      id: nextId('live_th_hdr'),
      node: (
        <Box flexDirection="row" marginLeft={outputMargin}>
          <Text color={activeGold}>▾ </Text>
          {isThinkingActive ? <Text color={activeGold}>● </Text> : null}
          <Text color={theme.text_faint}>Thinking · {label}{durStr}</Text>
        </Box>
      ),
    });
    // Static & persistent: Once thinking text arrives, keep it visible and stable on screen
    if (isThinkingExpanded && (activeThinking.fullThought || activeThinking.thoughts.length > 0)) {
      const liveFullTh = (activeThinking.fullThought || activeThinking.thoughts.join(' ')).trim();
      const paragraphs = liveFullTh.split(/\n+/).map((p) => p.trim()).filter(Boolean);
      paragraphs.forEach((p, pIdx) => {
        const wrappedP = wrapTextToLines(p, contentTextWidth - 4);
        wrappedP.forEach((pLine, pwIdx) => {
          virtualLines.push({
            id: nextId(`live_th_${pIdx}_${pwIdx}`),
            node: (
              <Box flexDirection="row" marginLeft={outputMargin + 2}>
                <Text color={theme.text_faint}>{pwIdx === 0 ? '› ' : '  '}{pLine}</Text>
              </Box>
            ),
          });
        });
      });
    }
  }

  if (currentTurnTools.length > 0 && filterRealTools(currentTurnTools).length > 0) {
    const real = filterRealTools(currentTurnTools);
    const dur = real.reduce((acc, t) => acc + (t.duration_s || 0), 0);
    virtualLines.push({
      id: nextId('live_tl_hdr'),
      node: (
        <Box flexDirection="row" marginLeft={outputMargin}>
          <Text color={activeGold}>› </Text>
          <Text color={theme.text_faint}>
            Ran {real.length} step{real.length > 1 ? 's' : ''} · {dur.toFixed(1)}s
          </Text>
        </Box>
      ),
    });
    if (isToolsExpanded) {
      real.forEach((t, tIdx) => {
        virtualLines.push({
          id: nextId(`live_tl_${tIdx}`),
          node: (
            <Box flexDirection="row" marginLeft={outputMargin + 2}>
              <Text color={theme.text_faint}>
                - {t.tool_name}: {t.command || t.tool_name} ({t.duration_s ? `${t.duration_s.toFixed(1)}s` : 'running'})
              </Text>
            </Box>
          ),
        });
      });
    }
  }

  if (streamingAnswer.trim().length > 0) {
    appendAssistantContentLines(streamingAnswer, 'live_stream');
  }

  // 4. VIEWPORT WINDOWING & TRUE SMOOTH SCROLLING
  const totalLines = virtualLines.length;
  const maxLines = Math.max(4, viewportHeight);
  const maxScrollOffset = Math.max(0, totalLines - maxLines);
  const clampedOffset = Math.min(scrollOffset, maxScrollOffset);

  let startIndex: number;
  if (clampedOffset === 0) {
    // AUTO-SCROLL TO BOTTOM: Always anchors to the very latest line!
    startIndex = Math.max(0, totalLines - maxLines);
  } else {
    // MANUAL SCROLL UP: Line-level offset moving upwards smoothly
    startIndex = Math.max(0, totalLines - maxLines - clampedOffset);
  }
  const endIndex = Math.min(totalLines, startIndex + maxLines);
  const visibleLines = virtualLines.slice(startIndex, endIndex);

  return (
    <Box flexDirection="column" height={maxLines} width="100%" flexShrink={0}>
      {visibleLines.map((item, idx) => (
        <Box key={item.id || `line_${startIndex + idx}`} height={1} flexShrink={0}>
          {item.node}
        </Box>
      ))}
    </Box>
  );
};
