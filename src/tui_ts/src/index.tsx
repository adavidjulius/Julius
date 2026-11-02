import chalk from 'chalk';

// Use ANSI 256 color mode so Apple Terminal.app and all terminals render Julius Brand Gold (#C8B896 -> \x1b[38;5;187m)
process.env.FORCE_COLOR = '2';
delete process.env.COLORTERM;
chalk.level = 2;

import React from 'react';
import { render } from 'ink';
import { App } from './App.js';

export function runTUI(): void {
  const args = process.argv.slice(2);
  let initialModel: string | undefined;

  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    if (arg === '--model' && args[i + 1]) {
      initialModel = args[i + 1];
    } else if (arg?.startsWith('--model=')) {
      initialModel = arg.slice(8);
    }
  }

  // 1. Enter terminal Alternate Screen Buffer (\x1b[?1049h)
  // 2. Clear screen and move cursor to (0,0) (\x1b[H\x1b[2J)
  // 3. Enable SGR mouse tracking for status line clicks and wheel scrolling (\x1b[?1000h\x1b[?1006h)
  // 4. Ensure mouse pointer is normal arrow (\x1b]22;default\x1b\\)
  // 5. Enforce solid block text cursor and hide hardware cursor while rendering (\x1b[2 q\x1b[?25l)
  if (process.stdout.isTTY) {
    process.stdout.write('\x1b[?1049h\x1b[H\x1b[2J\x1b[?1000h\x1b[?1006h\x1b]22;default\x1b\\\x1b[2 q\x1b[?25l');
  }

  const cleanup = () => {
    if (process.stdout.isTTY) {
      // Ensure mouse tracking is disabled, reset pointer and cursor, show cursor, and exit Alternate Screen Buffer
      process.stdout.write('\x1b[?1000l\x1b[?1002l\x1b[?1003l\x1b[?1006l\x1b]22;default\x1b\\\x1b[2 q\x1b[?25h\x1b[?1049l');
    }
  };

  process.on('exit', cleanup);
  process.on('SIGINT', () => {
    cleanup();
    process.exit(0);
  });
  process.on('SIGTERM', () => {
    cleanup();
    process.exit(0);
  });

  const { waitUntilExit } = render(<App initialModel={initialModel} />);
  waitUntilExit().then(cleanup).catch(cleanup);
}

if (process.argv[1]?.endsWith('index.ts') || process.argv[1]?.endsWith('index.tsx') || process.argv[1]?.endsWith('index.js')) {
  runTUI();
}
