import React, { useState, useEffect } from 'react';
import { Box, Text } from 'ink';
import type { ThemeTokens, WorkingStep } from '../types.js';
import { DARK_THEME } from '../theme/tokens.js';
import { formatActionDuration } from './modals/ActiveActionModal.js';
import { shouldShowHint } from '../utils/hintManager.js';

export interface ThinkingDotProps {
  label?: string;
  fullThought?: string;
  thoughts?: string[];
  workingSteps?: WorkingStep[];
  activeAction?: string;
  isRunning?: boolean;
  durationS?: number;
  isExpanded?: boolean;
  onToggle?: () => void;
  theme?: ThemeTokens;
  horizontalMargin?: number;
  columns?: number;
}

const SPINNER_FRAMES = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'];

export function sanitizeThought(raw: string): string {
  if (!raw || typeof raw !== 'string') return '';
  let clean = raw.trim();

  // If wrapped in JSON action payload, extract inner thought
  const mJsonTh = clean.match(/"thought"\s*:\s*"((?:[^"\\]|\\.)*)/);
  if (mJsonTh && mJsonTh[1]) {
    clean = mJsonTh[1].replace(/\\"/g, '"').replace(/\\n/g, ' ').trim();
  } else {
    // Extract content from <think>...</think> if present
    const mThink = clean.match(/<think>([\s\S]*?)(?:<\/think>|$)/i);
    if (mThink && mThink[1]?.trim()) {
      clean = mThink[1].trim();
    } else {
      clean = clean.replace(/<\/?(?:think|thought|reasoning)>/gi, '');
    }

    // Strip markdown code fences like ```json, ```, ```text
    clean = clean.replace(/^```[a-zA-Z0-9_-]*\s*/gm, '');
    clean = clean.replace(/\s*```$/gm, '');
    clean = clean.replace(/```[a-zA-Z0-9_-]*/g, '');
    clean = clean.replace(/```/g, '');

    // Strip leading prefixes like "Thought:", "Thinking Process:", "Reasoning:"
    clean = clean.replace(/^(?:Thinking Process|Thought|Reasoning):\s*/i, '');
  }

  // Strip unparsed JSON fragments, trailing JSON blocks, braces
  clean = clean.replace(/json\{[\s\S]*/gi, '');
  clean = clean.trim().replace(/^`+|`+$/g, '').trim();

  // Reject if the thought is just raw JSON syntax, braces, or protocol markers
  if (!clean) return '';
  const lower = clean.toLowerCase();
  if (['json', '```', '```json', '{', '}', '{}', '[]', 'none', 'null'].includes(lower)) {
    return '';
  }
  // Reject execution/action status strings so only authentic API thoughts are displayed
  if (/^(?:executing|running|executed|tool_call)\b/i.test(clean)) {
    return '';
  }
  if (lower.startsWith('executing action') || lower.startsWith('executing direct command') || lower === '(no thought)') {
    return '';
  }
  if (lower.startsWith('{"action"') || lower.startsWith('{"actions"') || lower.startsWith('"action":') || lower.startsWith('action:')) {
    return '';
  }
  if (clean.startsWith('{') && (clean.includes('"action"') || clean.includes('"actions"'))) {
    return '';
  }
  if (/^[{}()[\]"':;,` \n\r\t]+$/.test(clean)) {
    return '';
  }

  return clean.trim();
}

export function formatSummary(text: string, maxLen: number = 65): string {
  if (!text) return 'Thinking';
  const clean = sanitizeThought(text);
  if (!clean) return 'Thinking';

  let phrase = clean.trim().replace(/^[`"':.\s—-]+|[`"':.\s—-]+$/g, '');
  if (!phrase) return 'Thinking';

  // Iteratively strip thinking/thought/reasoning prefixes so only clean context remains
  while (true) {
    const prev = phrase;
    phrase = phrase.replace(/^(?:thinking(?:\s+process)?|thought|reasoning)(?:\s*[:—\-])\s*/i, '').trim();
    phrase = phrase.replace(/^thinking(?:\.{2,3}|…)?\s+/i, '').trim();
    if (['thinking', 'thinking...', 'thinking…', 'thought', 'reasoning', 'json', '```'].includes(phrase.toLowerCase())) {
      phrase = '';
      break;
    }
    if (phrase === prev) break;
  }

  if (!phrase) return 'Thinking';

  // Reject fences, braces, and json keywords
  if (phrase.startsWith('`') || phrase.startsWith('{') || phrase.startsWith('}') || phrase.startsWith('[') || phrase.toLowerCase().startsWith('json')) {
    return 'Thinking';
  }

  // Convert natural language robotic intentions into clean contextual phrases
  phrase = phrase.replace(/^(?:I will|I'll|I am going to|I need to|Let's|Now I will)\s+/i, '');
  phrase = phrase.replace(/^(?:use|run|execute)\s+(?:run_bash|bash)\s+to\s+/i, '');
  phrase = phrase.replace(/^(?:use|call)\s+(?:list_dir|the\s+tool)\s+to\s+/i, '');

  const firstLine = phrase.split('\n')[0]?.trim().replace(/^[`"':\s—-]+|[`"':\s—-]+$/g, '') || '';
  if (!firstLine || ['thinking', 'thinking...', 'thinking…', 'thought', 'reasoning', 'json'].includes(firstLine.toLowerCase())) {
    return 'Thinking';
  }

  // Capitalize first character
  const capitalized = firstLine[0] ? firstLine[0].toUpperCase() + firstLine.slice(1) : firstLine;

  // 1. If an early sentence boundary exists (. ! ?) within maxLen
  const m = capitalized.match(/^(.*?[.!?])(?:\s|$)/);
  if (m && m[1] && m[1].length <= maxLen) {
    const sentence = m[1].replace(/[.!?]+$/, '').trim();
    if (sentence && !['thinking', 'thought', 'json'].includes(sentence.toLowerCase())) {
      return `Thinking — ${sentence}`;
    }
  }

  // 2. If entire first line fits within maxLen
  if (capitalized.length <= maxLen) {
    const trimmed = capitalized.replace(/[.!?]+$/, '').trim();
    if (trimmed && !['thinking', 'thought', 'json'].includes(trimmed.toLowerCase())) {
      return `Thinking — ${trimmed}`;
    }
    return 'Thinking';
  }

  // 3. Otherwise truncate strictly at word boundary without cutting words
  let truncated = capitalized.slice(0, maxLen);
  if (truncated.includes(' ')) {
    truncated = truncated.slice(0, truncated.lastIndexOf(' '));
  }
  const cleanTrunc = truncated.replace(/[.!?,—\s-]+$/, '').replace(/[\s—-]+(?:and|or|because|but)?$/, '').trim();
  if (cleanTrunc && !['thinking', 'thought', 'json'].includes(cleanTrunc.toLowerCase())) {
    return `Thinking — ${cleanTrunc}`;
  }

  return 'Thinking';
}

/**
 * Ergonomic reasoning progression indicator and dynamic thinking panel.
 * Designed with reading psychology and cognitive ergonomics:
 * - Dynamic Saccadic Measure: Adapts card width to content (52 to 76 cols) to avoid eye-tracking fatigue.
 * - Warm Palette: Brand Gold (#c8b896) accents and warm parchment (#ded2b8) text for comfortable night viewing.
 * - Zero Clutter: Strictly restricted to LLM thoughts — all shell/tool executions go to the Active Action inspector.
 */
export const ThinkingDot: React.FC<ThinkingDotProps> = ({
  label = 'Thinking',
  fullThought = '',
  thoughts = [],
  workingSteps = [],
  activeAction = '',
  isRunning = true,
  durationS = 0,
  isExpanded = false,
  onToggle,
  theme = DARK_THEME,
  horizontalMargin,
  columns,
}) => {
  const [spinnerIndex, setSpinnerIndex] = useState(0);

  useEffect(() => {
    if (isRunning) {
      const timer = setInterval(() => {
        setSpinnerIndex((prev) => (prev + 1) % SPINNER_FRAMES.length);
      }, 140);
      return () => clearInterval(timer);
    }
  }, [isRunning]);

  const activeGold = theme.brand_gold || theme.accent || '#c8b896';
  const frame = SPINNER_FRAMES[spinnerIndex];
  const arrow = isExpanded ? '⌄ ' : '› ';

  // Derive dynamic label strictly from LLM thoughts
  let displaySummary = label;
  if (!displaySummary || displaySummary === 'Thinking' || displaySummary.startsWith('Running')) {
    if (thoughts.length > 0) {
      displaySummary = formatSummary(thoughts[thoughts.length - 1] || '');
    } else if (fullThought) {
      displaySummary = formatSummary(fullThought);
    } else {
      displaySummary = 'Thinking';
    }
  }

  if (!isRunning && durationS > 0) {
    const cleanLabel = displaySummary.replace(/^(?:Thinking|Running)\s*(?:—\s*)?/i, '');
    displaySummary = `Thought for ${formatActionDuration(durationS)}${cleanLabel ? ` · ${cleanLabel}` : ''}`;
  }

  // Filter thoughts to clean readable items
  const rawList = thoughts.length > 0 ? thoughts : (fullThought ? [fullThought] : []);
  const displayedThoughts = rawList
    .map(sanitizeThought)
    .filter((th) => th && !th.startsWith('{') && !th.startsWith('```') && th.toLowerCase() !== 'json');

  // Dynamic Saccadic Measure Calculation:
  // Ergonomic ideal: between 32 and 76 columns, adapting dynamically to terminal width
  const termCols = columns || (typeof process !== 'undefined' && process.stdout?.columns ? process.stdout.columns : 80);
  const hMargin = horizontalMargin !== undefined ? horizontalMargin : (termCols < 90 ? 2 : 4);
  const maxAllowedWidth = Math.max(28, termCols - (hMargin * 2) - 4);

  let maxThoughtLen = 0;
  for (const th of displayedThoughts) {
    const lines = th.split('\n');
    for (const l of lines) {
      if (l.length > maxThoughtLen) maxThoughtLen = l.length;
    }
  }
  const dynamicCardWidth = Math.min(Math.min(76, maxAllowedWidth), Math.max(30, maxThoughtLen + 4));

  return (
    <Box
      flexDirection="column"
      marginTop={1}
      marginBottom={1}
      marginLeft={hMargin}
      marginRight={hMargin}
    >
      {/* Single Unified Header: When expanded, shows only Thinking · Reasoning Flow; when collapsed, shows summary */}
      {isExpanded ? (
        <Box flexDirection="row" justifyContent="space-between" alignItems="center" marginBottom={1} width={dynamicCardWidth}>
          <Box flexDirection="row" alignItems="center">
            <Text color={theme.text_faint}>⌄ </Text>
            {isRunning ? (
              <Text bold color={activeGold}>
                {frame}{' '}
              </Text>
            ) : (
              <Text color={theme.text_dim}>
                ●{' '}
              </Text>
            )}
            <Text bold color={activeGold}>
              Thinking · Reasoning Flow
            </Text>
          </Box>
          {shouldShowHint('ctrl_t') && (
            <Text color={theme.text_faint}>
              [Ctrl+T: collapse]
            </Text>
          )}
        </Box>
      ) : (
        <Box flexDirection="row" alignItems="center">
          <Text color={theme.text_faint}>
            ›{' '}
          </Text>
          {isRunning ? (
            <Text bold color={activeGold}>
              {frame}{' '}
            </Text>
          ) : (
            <Text color={theme.text_dim}>
              ●{' '}
            </Text>
          )}
          <Text color={isRunning ? theme.text : theme.text_dim}>
            {displaySummary}
          </Text>
        </Box>
      )}

      {/* Expanded dynamic ergonomic thinking panel with INVISIBLE border following exact formatting */}
      {isExpanded && (
        <Box
          flexDirection="column"
          width={dynamicCardWidth}
          paddingLeft={1}
          paddingRight={1}
          paddingTop={0}
          paddingBottom={0}
          marginTop={0}
          marginBottom={0}
        >
          {/* Clean bulleted thoughts in warm soft parchment (#ded2b8) */}
          {displayedThoughts.length > 0 ? (
            displayedThoughts.map((th, idx) => (
              <Box key={idx} flexDirection="row" marginBottom={idx < displayedThoughts.length - 1 ? 1 : 0}>
                <Text bold color={activeGold}>› </Text>
                <Box flexGrow={1}>
                  <Text color="#ded2b8" wrap="wrap">{th}</Text>
                </Box>
              </Box>
            ))
          ) : (
            <Box>
              <Text italic color={theme.text_faint}>
                (Analyzing task requirements and formulating steps…)
              </Text>
            </Box>
          )}
        </Box>
      )}
    </Box>
  );
};
