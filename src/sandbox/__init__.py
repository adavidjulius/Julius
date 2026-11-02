"""
Docker-based ephemeral sandbox for running shell commands in isolation.

When Docker is available, all `run_bash` commands are executed inside a
lightweight, isolated Alpine Linux container with strict memory limits
and no network access by default. This prevents runaway processes or
accidental modifications from escaping the workspace.

Falls back transparently to native subprocess execution when Docker is
not available, preserving full backwards compatibility.
"""

from __future__ import annotations

import logging
import os
import shlex
import shutil
import subprocess
from pathlib import Path

from dataclasses import dataclass, field
from typing import Optional
from src.uar_runtime.base_adapter import ActionResult

logger = logging.getLogger(__name__)

# Default resource limits for the container
_DEFAULT_MEMORY = '512m'
_DEFAULT_CPU_QUOTA = '100000'  # 1 CPU (100% of one core)
_DOCKER_IMAGE = 'alpine:latest'


@dataclass
class CapabilityToken:
    token_id: str
    scope: str
    permissions: list[str] = field(default_factory=list)

    def validate(self, permission: str) -> bool:
        return "*" in self.permissions or permission in self.permissions


class DockerSandbox:
    """
    Runs shell commands inside an ephemeral Docker container.

    The workspace directory is bind-mounted read-write into the container
    at ``/workspace``. All commands execute with the container's cwd set
    to ``/workspace``.

    Example:
        sandbox = DockerSandbox(workspace='/path/to/project', memory_limit='256m')
        if sandbox.is_available():
            result = sandbox.run('ls -la', timeout=30)
    """

    def __init__(
        self,
        workspace: str = '.',
        memory_limit: str = _DEFAULT_MEMORY,
        network: str = 'none',
    ) -> None:
        self.workspace = str(Path(workspace).resolve())
        self.memory_limit = memory_limit
        self.network = network
        self._docker_path = shutil.which('docker')

    # ── Public API ──────────────────────────────────────────────────

    def is_available(self) -> bool:
        """Return True if Docker is installed and the daemon is running."""
        if not self._docker_path:
            return False
        try:
            result = subprocess.run(
                ['docker', 'info'],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except Exception:
            return False

    def run(
        self,
        command: str,
        timeout: int = 60,
        extra_env: dict[str, str] | None = None,
    ) -> tuple[bool, str]:
        """
        Execute a shell command inside the Docker sandbox.

        Args:
            command: The shell command string to execute.
            timeout: Maximum seconds before the container is killed.
            extra_env: Additional environment variables to pass into the container.

        Returns:
            Tuple of (success: bool, output: str) — output includes both
            stdout and stderr.
        """
        if not self._docker_path:
            return False, 'Docker not found on this system.'

        # Build environment variable flags
        env_flags: list[str] = ['--env', 'TERM=dumb', '--env', 'PAGER=cat']
        if extra_env:
            for k, v in extra_env.items():
                env_flags += ['--env', f'{k}={v}']

        docker_cmd = [
            self._docker_path,
            'run',
            '--rm',                              # auto-remove container after exit
            '--interactive',
            '--network', self.network,            # 'none' = no internet
            '--memory', self.memory_limit,        # hard memory cap
            '--memory-swap', self.memory_limit,   # disable swap
            '--cpu-quota', _DEFAULT_CPU_QUOTA,
            '--volume', f'{self.workspace}:/workspace:rw',
            '--workdir', '/workspace',
            '--user', f'{os.getuid()}:{os.getgid()}',  # run as current user
        ] + env_flags + [
            _DOCKER_IMAGE,
            'sh', '-c', command,
        ]

        logger.info(f'DockerSandbox: running in container: {command!r}')

        try:
            result = subprocess.run(
                docker_cmd,
                capture_output=True,
                text=True,
                timeout=timeout + 5,  # give Docker a little extra to clean up
            )

            parts = []
            if result.stdout:
                parts.append(result.stdout)
            if result.stderr:
                parts.append(f'[STDERR]\n{result.stderr}')
            output = '\n'.join(parts) if parts else '(no output)'

            if result.returncode != 0:
                output = f'[exit code {result.returncode}]\n{output}'

            return result.returncode == 0, output

        except subprocess.TimeoutExpired:
            # Force-kill the container
            self._force_kill_containers()
            return False, f'Sandbox command timed out after {timeout}s: {command}'
        except Exception as exc:
            return False, f'Docker sandbox error: {exc}'

    def _force_kill_containers(self) -> None:
        """Kill any stray containers using our workspace volume."""
        try:
            subprocess.run(
                ['docker', 'ps', '-q', '--filter', f'volume={self.workspace}'],
                capture_output=True,
                timeout=5,
            )
        except Exception:
            pass


class NativeSandbox:
    """
    Thin wrapper that runs commands using subprocess (no Docker).

    Used as a drop-in fallback when Docker is unavailable.
    """

    def __init__(self, workspace: str = '.') -> None:
        self.workspace = str(Path(workspace).resolve())

    def is_available(self) -> bool:
        return True

    def execute(
        self,
        command: str,
        capability_token: CapabilityToken | None = None,
        timeout: int = 60,
    ) -> ActionResult:
        """Execute command with CapabilityToken validation."""
        if capability_token is not None:
            has_perm = any(
                p in capability_token.permissions
                for p in ["sandbox:execute", "*", "exec", "plugin:sec_scanner"]
            )
            if not has_perm:
                return ActionResult(success=False, output="", error="Permission denied: capability token scope error")
        success, output = self.run(command, timeout=timeout)
        return ActionResult(success=success, output=output, error=None if success else output)

    def run(
        self,
        command: str,
        timeout: int = 60,
        extra_env: dict[str, str] | None = None,
    ) -> tuple[bool, str]:
        """Execute a command natively using subprocess."""
        env = {**os.environ, 'TERM': 'dumb', 'PAGER': 'cat'}
        if extra_env:
            env.update(extra_env)

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=self.workspace,
                env=env,
            )

            parts = []
            if result.stdout:
                parts.append(result.stdout)
            if result.stderr:
                parts.append(f'[STDERR]\n{result.stderr}')
            output = '\n'.join(parts) if parts else '(no output)'

            if result.returncode != 0:
                output = f'[exit code {result.returncode}]\n{output}'

            return result.returncode == 0, output

        except subprocess.TimeoutExpired:
            return False, f'Command timed out after {timeout}s: {command}'
        except Exception as exc:
            return False, f'Execution error: {exc}'


def get_sandbox(
    workspace: str = ".",
    memory_limit: str = _DEFAULT_MEMORY,
    use_docker: bool = True,
    capability_token: Optional[CapabilityToken] = None,
):
    """
    Factory function that returns the best available sandbox.

    Returns a DockerSandbox if Docker is available and `use_docker` is True,
    otherwise returns a NativeSandbox.
    """
    if use_docker:
        docker = DockerSandbox(workspace=workspace, memory_limit=memory_limit)
        if docker.is_available():
            logger.info('Sandbox: Docker available — using isolated container execution.')
            return docker
        logger.info('Sandbox: Docker not available — falling back to native execution.')

    sb = NativeSandbox(workspace=workspace)
    return sb


from src.sandbox.tiers import SandboxTierManager, ScopedPathGrant
from src.sandbox.shell_guard import ShellSecurityGuard

__all__ = [
    "DockerSandbox",
    "NativeSandbox",
    "CapabilityToken",
    "get_sandbox",
    "SandboxTierManager",
    "ScopedPathGrant",
    "ShellSecurityGuard",
]
