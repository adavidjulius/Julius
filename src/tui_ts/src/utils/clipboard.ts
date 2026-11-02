import { spawn } from 'node:child_process';

/**
 * Cross-platform clipboard helper.
 * On macOS, directly pipes to pbcopy.
 * On Linux, uses xclip or wl-copy.
 * On Windows, uses clip.exe.
 */
export function copyToClipboard(text: string): boolean {
  if (!text) return false;

  try {
    const isMac = process.platform === 'darwin';
    const isWindows = process.platform === 'win32';

    let cmd = 'xclip';
    let args = ['-selection', 'clipboard'];

    if (isMac) {
      cmd = 'pbcopy';
      args = [];
    } else if (isWindows) {
      cmd = 'clip';
      args = [];
    }

    const child = spawn(cmd, args, { stdio: ['pipe', 'ignore', 'ignore'] });
    child.stdin.write(text);
    child.stdin.end();
    return true;
  } catch {
    return false;
  }
}

