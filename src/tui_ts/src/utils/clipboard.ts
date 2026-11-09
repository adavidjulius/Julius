import { spawn, spawnSync } from 'node:child_process';

/**
 * Cross-platform clipboard helper.
 * On macOS, directly pipes to pbcopy / pbpaste.
 * On Linux, uses xclip or wl-copy / wl-paste.
 * On Windows, uses clip.exe / PowerShell Get-Clipboard.
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

export function readFromClipboard(): string {
  try {
    const isMac = process.platform === 'darwin';
    const isWindows = process.platform === 'win32';

    if (isMac) {
      const res = spawnSync('pbpaste', [], { encoding: 'utf-8', timeout: 1000 });
      return res.stdout || '';
    } else if (isWindows) {
      const res = spawnSync('powershell', ['-NoProfile', '-Command', 'Get-Clipboard'], { encoding: 'utf-8', timeout: 1000 });
      return res.stdout ? res.stdout.replace(/\r\n/g, '\n').trim() : '';
    } else {
      // Linux: Try wl-paste then xclip
      try {
        const res = spawnSync('wl-paste', [], { encoding: 'utf-8', timeout: 1000 });
        if (res.stdout) return res.stdout;
      } catch {
        // Fall back to xclip
      }
      const res = spawnSync('xclip', ['-selection', 'clipboard', '-o'], { encoding: 'utf-8', timeout: 1000 });
      return res.stdout || '';
    }
  } catch {
    return '';
  }
}
