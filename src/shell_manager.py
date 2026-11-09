"""
Persistent stateful terminal shell manager using pseudo-terminals (PTYs).
Keeps a single shell session alive across agent steps to preserve directory,
environment variable, and virtual environment state.
"""

from __future__ import annotations

import logging
import os
import re
import select
import subprocess
import threading
import time

logger = logging.getLogger(__name__)

# Check if pseudo-terminals (PTY) are supported (Unix only)
try:
    import pty
    _PTY_AVAILABLE = True
except ImportError:
    _PTY_AVAILABLE = False


class StatefulShell:
    """
    Manages a persistent, stateful terminal process via openpty().
    Allows executing a sequence of commands while preserving state (cd, env, etc.).
    """

    def __init__(self, workspace_root: str, env: dict[str, str] | None = None) -> None:
        self.workspace_root = str(os.path.abspath(workspace_root))
        self.env = env
        self.master_fd = None
        self.process = None
        self._pty_active = False
        self._lock = threading.Lock()  # Finding #14: serialize concurrent command execution
        self.current_command: Optional[str] = None
        self.command_start_time: float = 0.0
        self.partial_output: str = ""
        self.cancel_requested: bool = False
        self.last_command: Optional[str] = None
        self.last_output: str = ""
        self.last_duration: float = 0.0
        self.last_exit_code: Optional[int] = None
        
        self._start_shell()

    def _start_shell(self) -> None:
        """Spawn the background shell process."""
        shell_env = dict(self.env if self.env is not None else os.environ)
        shell_env['TERM'] = 'dumb'
        shell_env['PAGER'] = 'cat'
        shell_env['GIT_PAGER'] = 'cat'
        shell_env['CI'] = '1'
        shell_env['DEBIAN_FRONTEND'] = 'noninteractive'
        shell_env['PYTHONUNBUFFERED'] = '1'
        shell_env['npm_config_yes'] = 'true'
        # Ensure project virtual environment and standard system paths are present in PATH
        current_path = shell_env.get('PATH', '')
        venv_bin = os.path.join(self.workspace_root, ".venv", "bin")
        if os.path.isdir(venv_bin) and venv_bin not in current_path:
            current_path = f"{venv_bin}:{current_path}"
        for extra_bin in ('/opt/homebrew/bin', '/opt/homebrew/sbin', '/usr/local/bin'):
            if extra_bin not in current_path and os.path.exists(extra_bin):
                current_path = f"{extra_bin}:{current_path}"
        shell_env['PATH'] = current_path
        if _PTY_AVAILABLE:
            try:
                self.master_fd, slave_fd = pty.openpty()
                # Disable ECHO on slave so input is never reflected back to master
                try:
                    import termios
                    attrs = termios.tcgetattr(slave_fd)
                    attrs[3] = attrs[3] & ~termios.ECHO
                    termios.tcsetattr(slave_fd, termios.TCSANOW, attrs)
                except Exception as te:
                    logger.debug(f"StatefulShell: Could not disable slave ECHO: {te}")

                # Run bash in non-profile, non-rc mode to be clean and fast
                self.process = subprocess.Popen(
                    ['/bin/bash', '--noprofile', '--norc'],
                    stdin=slave_fd,
                    stdout=slave_fd,
                    stderr=slave_fd,
                    cwd=self.workspace_root,
                    close_fds=True,
                    env=shell_env
                )
                os.close(slave_fd)

                try:
                    os.set_blocking(self.master_fd, False)
                except Exception as be:
                    logger.debug(f"StatefulShell: Could not set non-blocking on master_fd: {be}")

                self._pty_active = True

                # Initialize shell environment: set +H to disable history expansion, PS1='' to avoid prompt clutter
                self._write_init_sequence()
                # Consume initial bash startup text (welcome banners, default shell warnings)
                self._read_raw_output(timeout=0.3)
                logger.info("StatefulShell: Persistent PTY bash shell successfully started.")
                return
            except Exception as e:
                logger.warning(f"StatefulShell: Failed to initialize PTY shell: {e}. Falling back to stateless execution.")

        # If PTY is not available or failed to start, we flag it so we can fall back
        self._pty_active = False
        logger.info("StatefulShell: Running in stateless mode (PTY not available or failed).")

    def _write_init_sequence(self) -> None:
        """Initialize bash with clean environment settings (disable history expansion, clear PS1 & PS2 prompts)."""
        if self.master_fd is not None:
            try:
                os.write(self.master_fd, b"set +H; PS1=''; PS2=''\n")
            except Exception:
                pass

    def execute_command(self, command: str, timeout: int = 60) -> tuple[bool, str]:
        """
        Execute a shell command in the stateful shell and return (success, output).
        
        If PTY is inactive, falls back to stateless subprocess execution.
        Thread-safe: concurrent callers are serialized.
        """
        with self._lock:  # Finding #14: prevent interleaved PTY I/O
            # For multiline scripts, heredocs, or large payloads, dispatch via sourced temporary
            # script to avoid BSD TTYHOG/MAX_CANON buffer drops and ensure 100% input fidelity.
            trimmed = command.strip()
            if self._pty_active and ('\n' in trimmed or '<<' in trimmed or len(command) > 512):
                return self._execute_script_wrapped_locked(command, timeout)
            return self._execute_command_locked(command, timeout)

    def _execute_script_wrapped_locked(self, script_content: str, timeout: int) -> tuple[bool, str]:
        """Execute multiline or heredoc script by writing to a temporary file and sourcing it."""
        tmp_dir = os.path.join(self.workspace_root, ".julius")
        os.makedirs(tmp_dir, exist_ok=True)
        tmp_file = os.path.join(tmp_dir, f"_cmd_{os.getpid()}_{int(time.time() * 1000)}.sh")
        try:
            with open(tmp_file, "w", encoding="utf-8") as f:
                f.write(script_content + "\n")

            # Source script so directory changes and environment variables persist
            wrapper_cmd = f'. "{tmp_file}"'
            success, output = self._execute_command_locked(wrapper_cmd, timeout)
            # Remove wrapper reference from output if present
            if wrapper_cmd in output:
                output = output.replace(wrapper_cmd, "").strip()
            return success, output
        finally:
            try:
                if os.path.exists(tmp_file):
                    os.remove(tmp_file)
            except Exception:
                pass

    def _sanitize_and_close_command(self, command: str) -> str:
        """
        Ensure the command does not leave unclosed here-documents, unclosed quotes,
        or unbalanced syntax that would cause bash to hang waiting on stdin/secondary prompt.
        """
        clean_cmd = command.rstrip()

        # 1. Detect unclosed here-documents: << 'EOF', << "EOF", << EOF, << 'PYEOF'
        here_matches = list(re.finditer(r'<<-?\s*[\'"]?([A-Za-z0-9_]+)[\'"]?', clean_cmd))
        for m in here_matches:
            delimiter = m.group(1)
            # Check if delimiter appears as a standalone line after the << declaration
            post_match = clean_cmd[m.end():]
            lines_after = [l.strip() for l in post_match.splitlines()]
            if delimiter not in lines_after:
                logger.warning(f"StatefulShell: Auto-closing unclosed here-doc delimiter '{delimiter}' to prevent PTY hang")
                clean_cmd += f"\n{delimiter}\n"

        # 2. Check for unbalanced single quotes
        single_quotes = len(re.findall(r"(?<!\\)'", clean_cmd))
        if single_quotes % 2 != 0:
            logger.warning("StatefulShell: Auto-closing unclosed single quote to prevent PTY hang")
            clean_cmd += "'\n"

        # 3. Check for unbalanced double quotes
        double_quotes = len(re.findall(r'(?<!\\)"', clean_cmd))
        if double_quotes % 2 != 0:
            logger.warning("StatefulShell: Auto-closing unclosed double quote to prevent PTY hang")
            clean_cmd += '"\n'

        return clean_cmd

    def _execute_command_locked(self, command: str, timeout: int) -> tuple[bool, str]:
        """Internal: execute a command while holding the lock."""
        if not self._pty_active:
            return self._execute_stateless(command, timeout)

        sentinel = "JULIUS_DONE"
        clean_cmd = self._sanitize_and_close_command(command.rstrip())
        full_cmd = f"{clean_cmd}\necho {sentinel}_$?_\n"
        payload = full_cmd.encode('utf-8')

        output = ""
        start_time = time.time()
        exit_code = None
        self.current_command = command
        self.command_start_time = start_time
        self.partial_output = ""
        self.cancel_requested = False

        offset = 0
        total_bytes = len(payload)

        # ── Phase 1: Non-blocking interleaved write and read ──────────────────
        # Write payload in chunks while simultaneously draining readable bytes
        # from master_fd so kernel PTY buffers NEVER saturate or deadlock.
        while offset < total_bytes and (time.time() - start_time < timeout):
            if self.cancel_requested:
                break

            r, w, _ = select.select([self.master_fd], [self.master_fd], [], 0.05)

            # Drain any pending output first
            if self.master_fd in r:
                try:
                    chunk = os.read(self.master_fd, 4096).decode('utf-8', errors='ignore')
                    if chunk:
                        output += chunk
                        self.partial_output = output
                        match = re.search(r'JULIUS_DONE_(\d+)_', output)
                        if match:
                            exit_code = int(match.group(1))
                            break
                except (OSError, BlockingIOError):
                    pass

            # Write next chunk if space available
            if self.master_fd in w and offset < total_bytes:
                try:
                    chunk_to_write = payload[offset:offset + 1024]
                    written = os.write(self.master_fd, chunk_to_write)
                    offset += written
                except (BlockingIOError, OSError) as e:
                    # Write failed (e.g. process died)
                    if isinstance(e, OSError) and e.errno not in (11, 35):  # EAGAIN / EWOULDBLOCK
                        logger.error(f"StatefulShell: PTY write error: {e}")
                        break

        # Handle cancellation or timeout during write phase
        if self.cancel_requested:
            self.cancel_requested = False
            try:
                os.write(self.master_fd, b"\x03\x03")
            except OSError:
                pass
            self.current_command = None
            return False, f"[Command cancelled by user after {time.time() - start_time:.1f}s]\n{self._clean_output(output, command)}"

        if offset < total_bytes and (time.time() - start_time >= timeout):
            logger.warning(f"StatefulShell: Timed out during write after {timeout}s: {command[:60]}")
            try:
                os.write(self.master_fd, b"\x03\x03")
            except OSError:
                pass
            self.current_command = None
            return False, f"Command timed out after {timeout}s during dispatch: {command[:60]}"

        # ── Phase 2: Read output until sentinel or timeout ────────────────────
        while exit_code is None and (time.time() - start_time < timeout):
            if self.cancel_requested:
                self.cancel_requested = False
                try:
                    os.write(self.master_fd, b"\x03\x03")
                except OSError:
                    pass
                self.current_command = None
                return False, f"[Command cancelled by user after {time.time() - start_time:.1f}s]\n{self._clean_output(output, command)}"

            r, _, _ = select.select([self.master_fd], [], [], 0.05)
            if self.master_fd in r:
                try:
                    chunk = os.read(self.master_fd, 4096).decode('utf-8', errors='ignore')
                    if chunk:
                        output += chunk
                        self.partial_output = output

                        match = re.search(r'JULIUS_DONE_(\d+)_', output)
                        if match:
                            exit_code = int(match.group(1))
                            break

                        # Break secondary prompt stalls (e.g. bash waiting on unclosed syntax)
                        if output.rstrip().endswith(('>', '> ', '>>', '>> ')):
                            try:
                                os.write(self.master_fd, b"\n\x03")
                            except OSError:
                                pass
                    else:
                        break
                except (OSError, BlockingIOError):
                    break

        self.current_command = None

        if exit_code is None:
            # Command timed out
            logger.warning(f"StatefulShell: Command timed out after {timeout}s: {command}")
            # Send Ctrl+C twice to break loops or hanging commands
            try:
                os.write(self.master_fd, b"\x03")
                time.sleep(0.1)
                os.write(self.master_fd, b"\x03")
            except OSError:
                pass
            # Read any trailing output produced before timeout
            trailing = ""
            try:
                r, _, _ = select.select([self.master_fd], [], [], 0.2)
                if self.master_fd in r:
                    trailing = os.read(self.master_fd, 4096).decode('utf-8', errors='ignore')
            except OSError:
                pass
            total_out = self._clean_output(output + trailing, command)
            preview = f"\nOutput before timeout:\n{total_out}" if total_out else ""
            # Recycle and restart the background shell so future commands are not blocked
            self.restart()
            return False, f"Command timed out after {timeout}s and was terminated: {command}{preview}"

        cleaned_output = self._clean_output(output, command)
        success = (exit_code == 0)

        if not success:
            cleaned_output = f"[exit code {exit_code}]\n{cleaned_output}"

        self.last_command = command
        self.last_output = cleaned_output
        self.last_duration = max(0.1, time.time() - start_time)
        self.last_exit_code = exit_code

        return success, cleaned_output

    def cancel_current_command(self) -> bool:
        """Cancel currently executing command in shell."""
        if not self.current_command and not self.cancel_requested:
            return False
        self.cancel_requested = True
        if self._pty_active and self.master_fd:
            try:
                os.write(self.master_fd, b"\x03\x03")
                return True
            except OSError:
                pass
        return bool(self.current_command or self.cancel_requested)

    def _read_raw_output(self, timeout: float) -> str:
        """Helper to read any pending bytes from master fd."""
        buffer = b""
        start = time.time()
        while time.time() - start < timeout:
            r, _, _ = select.select([self.master_fd], [], [], 0.02)
            if self.master_fd in r:
                try:
                    chunk = os.read(self.master_fd, 4096)
                    if not chunk:
                        break
                    buffer += chunk
                except OSError:
                    break
        return buffer.decode('utf-8', errors='ignore')

    def _clean_output(self, full_output: str, cmd_str: str) -> str:
        """Cleans terminal echo, sentinel outputs, and shell prompts from output."""
        # Standardise line endings
        full_output = full_output.replace('\r\n', '\n').replace('\r', '\n')
        lines = full_output.split('\n')

        cleaned_lines = []
        for line in lines:
            if "JULIUS_DONE_" in line:
                continue
            # Strip secondary multiline bash prompts like "> > > " if present
            cleaned_line = re.sub(r'^(?:>\s*)+', '', line)
            cleaned_lines.append(cleaned_line)

        # Strip command echo line if it exists at the top
        if len(cleaned_lines) > 0:
            first_line = cleaned_lines[0]
            # Match if line contains the command or is prompt + command
            if cmd_str in first_line or first_line.endswith(cmd_str) or cmd_str.split(';')[0] in first_line:
                cleaned_lines = cleaned_lines[1:]

        result = "\n".join(cleaned_lines)

        # Clean trailing prompts like "bash-3.2$ " or "bash-3.2# "
        result = re.sub(r'bash-\d+\.\d+[\$\#]\s*$', '', result)
        return result.strip()

    def _execute_stateless(self, command: str, timeout: int) -> tuple[bool, str]:
        """Stateless command execution fallback using subprocess."""
        shell_env = dict(self.env if self.env is not None else os.environ)
        shell_env['TERM'] = 'dumb'
        shell_env['PAGER'] = 'cat'
        try:
            result = subprocess.run(
                command, shell=True, capture_output=True, text=True,
                timeout=timeout, cwd=self.workspace_root,
                env=shell_env,
            )
            parts = []
            if result.stdout:
                parts.append(result.stdout)
            if result.stderr:
                parts.append(f'[STDERR]\n{result.stderr}')
            output = '\n'.join(parts) if parts else '(no output)'
            if result.returncode != 0:
                output = f'[exit code {result.returncode}]\n{output}'
            self.last_command = command
            self.last_output = output
            self.last_duration = 0.5
            self.last_exit_code = result.returncode
            return (result.returncode == 0), output
        except Exception as e:
            return False, f"Stateless execution error: {e}"

    def close(self) -> None:
        """Terminate the shell process and close descriptors."""
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=1.0)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
        if self.master_fd is not None:
            try:
                os.close(self.master_fd)
            except OSError:
                pass
            self.master_fd = None
        self._pty_active = False

    def restart(self) -> None:
        """Safely close and restart the background shell process after timeouts or corruption."""
        try:
            self.close()
        except Exception:
            pass
        try:
            self._start_shell()
            logger.info("StatefulShell: Background shell successfully recycled and restarted.")
        except Exception as e:
            logger.error(f"StatefulShell: Failed to restart shell: {e}")
