"""
Remote Compute Offloader — Cluster Executor.

Phase 3.1 — Milestone 3.1: Transparently offloads CPU-heavy actions to the
KCC Lab 32-core Xeon cluster via SSH. Provides workspace mirroring via rsync,
real-time stdout/stderr streaming, and automatic fallback to local execution
when the remote server is unreachable.

Interface mirrors ActionExecutor.run_bash() for transparent substitution.
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from .ssh_pool import SSHPool, SSHConfig

logger = logging.getLogger(__name__)


# ── Configuration ─────────────────────────────────────────────────────────────

@dataclass
class ClusterConfig:
    """Remote cluster configuration."""
    host: str = "127.0.0.1"
    port: int = 22
    username: str = "ct2026503586"
    key_path: str = str(Path.home() / ".ssh" / "id_rsa")
    remote_workspace: str = "/home/ct2026503586/julius_workspace"
    rsync_excludes: list[str] = field(default_factory=lambda: [
        ".git", ".venv", "__pycache__", "node_modules", ".julius",
        "*.pyc", ".pytest_cache", ".DS_Store",
    ])
    offload_patterns: list[str] = field(default_factory=lambda: [
        "pytest", "python -m pytest", "docker build", "docker-compose",
        "npm run build", "cargo build", "make", "gcc", "g++",
        "ast_reindex", "rag_index",
    ])
    fallback_to_local: bool = True
    command_timeout: float = 300.0  # 5 minutes default


# ── Execution Result ──────────────────────────────────────────────────────────

@dataclass
class RemoteResult:
    """Result of a remote command execution."""
    success: bool
    output: str
    error: str = ""
    exit_code: int = 0
    executed_remotely: bool = False
    duration_ms: float = 0.0
    host: str = ""


# ── Cluster Executor ──────────────────────────────────────────────────────────

class ClusterExecutor:
    """Transparent remote command execution with local fallback.

    Offloads CPU-heavy commands to the remote cluster while providing
    the same interface as local execution. Includes workspace syncing
    via rsync.

    Usage::

        executor = ClusterExecutor()
        await executor.connect()

        # Automatically decides local vs remote
        result = await executor.run("pytest tests/")

        # Force remote execution
        result = await executor.run_remote("docker build .")
    """

    def __init__(
        self,
        config: ClusterConfig | None = None,
        local_workspace: str = ".",
        on_event: Optional[Callable] = None,
    ) -> None:
        self.config = config or ClusterConfig()
        self.local_workspace = str(Path(local_workspace).resolve())
        self._on_event = on_event

        ssh_config = SSHConfig(
            host=self.config.host,
            port=self.config.port,
            username=self.config.username,
            key_path=self.config.key_path,
        )
        self._ssh = SSHPool(ssh_config)
        self._remote_available = False
        self._last_sync_time: float = 0.0

    @property
    def is_remote_available(self) -> bool:
        return self._remote_available

    async def connect(self) -> bool:
        """Establish SSH connection to the remote cluster."""
        if not self._ssh.is_available:
            logger.warning("SSH libraries not available — remote execution disabled")
            return False

        connected = await self._ssh.connect()
        if connected:
            reachable = await self._ssh.is_reachable()
            self._remote_available = reachable
            if reachable:
                # Ensure remote workspace directory exists
                await self._ssh.run_command(f"mkdir -p {self.config.remote_workspace}")
                logger.info("Cluster executor connected to %s", self.config.host)
            return reachable

        self._remote_available = False
        return False

    def should_offload(self, command: str) -> bool:
        """Determine if a command should be offloaded to the cluster."""
        cmd_lower = command.lower().strip()
        return any(pattern in cmd_lower for pattern in self.config.offload_patterns)

    async def sync_workspace(self) -> bool:
        """Synchronize local workspace to remote via rsync.

        Only syncs diffs (rsync --archive --compress --delete).
        """
        if not self._remote_available:
            return False

        start = time.time()

        exclude_args = []
        for pattern in self.config.rsync_excludes:
            exclude_args.extend(["--exclude", pattern])

        rsync_cmd = [
            "rsync",
            "--archive", "--compress", "--delete",
            "--timeout=30",
            *exclude_args,
            f"{self.local_workspace}/",
            f"{self.config.username}@{self.config.host}:{self.config.remote_workspace}/",
        ]

        # Add SSH key if specified
        if self.config.key_path:
            rsync_cmd.extend(["-e", f"ssh -i {self.config.key_path} -p {self.config.port}"])

        try:
            result = await asyncio.get_running_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    rsync_cmd,
                    capture_output=True,
                    text=True,
                    timeout=120,
                ),
            )

            elapsed = time.time() - start
            if result.returncode == 0:
                self._last_sync_time = time.time()
                logger.info("Workspace synced to %s in %.1fs", self.config.host, elapsed)
                return True
            else:
                logger.error("rsync failed: %s", result.stderr[:200])
                return False

        except FileNotFoundError:
            logger.error("rsync not found — install rsync for workspace sync")
            return False
        except Exception as exc:
            logger.error("Workspace sync failed: %s", exc)
            return False

    async def run(
        self,
        command: str,
        timeout: float | None = None,
        force_remote: bool = False,
    ) -> RemoteResult:
        """Execute a command, automatically choosing local or remote.

        Args:
            command: Shell command to execute.
            timeout: Override default timeout.
            force_remote: Force remote execution.

        Returns:
            RemoteResult with execution details.
        """
        use_remote = force_remote or (
            self._remote_available and self.should_offload(command)
        )

        if use_remote:
            result = await self.run_remote(command, timeout=timeout)
            # Fallback to local if remote failed and fallback is enabled
            if not result.success and self.config.fallback_to_local:
                logger.info("Remote execution failed — falling back to local")
                return await self.run_local(command, timeout=timeout)
            return result

        return await self.run_local(command, timeout=timeout)

    async def run_remote(
        self,
        command: str,
        timeout: float | None = None,
    ) -> RemoteResult:
        """Execute a command on the remote cluster.

        Automatically syncs workspace before execution.
        """
        start = time.time()
        timeout = timeout or self.config.command_timeout

        if not self._remote_available:
            return RemoteResult(
                success=False,
                output="",
                error="Remote cluster not available",
                exit_code=1,
                executed_remotely=False,
            )

        # Emit event
        if self._on_event:
            self._on_event({
                "type": "cluster.executing",
                "command": command[:120],
                "host": self.config.host,
            })

        # Sync workspace if stale (>60s since last sync)
        if time.time() - self._last_sync_time > 60:
            await self.sync_workspace()

        # Execute on remote
        exit_code, stdout, stderr = await self._ssh.run_command(
            command,
            timeout=timeout,
            cwd=self.config.remote_workspace,
        )

        elapsed = (time.time() - start) * 1000

        result = RemoteResult(
            success=exit_code == 0,
            output=stdout,
            error=stderr,
            exit_code=exit_code,
            executed_remotely=True,
            duration_ms=elapsed,
            host=self.config.host,
        )

        if self._on_event:
            self._on_event({
                "type": "cluster.completed",
                "command": command[:120],
                "success": result.success,
                "duration_ms": elapsed,
                "host": self.config.host,
            })

        return result

    async def run_local(
        self,
        command: str,
        timeout: float | None = None,
    ) -> RemoteResult:
        """Execute a command locally (fallback)."""
        start = time.time()
        timeout = timeout or self.config.command_timeout

        try:
            result = await asyncio.get_running_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    cwd=self.local_workspace,
                    timeout=timeout,
                ),
            )

            elapsed = (time.time() - start) * 1000

            return RemoteResult(
                success=result.returncode == 0,
                output=result.stdout,
                error=result.stderr,
                exit_code=result.returncode,
                executed_remotely=False,
                duration_ms=elapsed,
                host="localhost",
            )

        except subprocess.TimeoutExpired:
            return RemoteResult(
                success=False,
                output="",
                error=f"Command timed out after {timeout}s",
                exit_code=124,
                executed_remotely=False,
                host="localhost",
            )
        except Exception as exc:
            return RemoteResult(
                success=False,
                output="",
                error=str(exc),
                exit_code=1,
                executed_remotely=False,
                host="localhost",
            )

    async def close(self) -> None:
        """Close SSH connections."""
        await self._ssh.close()
        self._remote_available = False
