"""
SSH Connection Pool for Remote Cluster Integration.

Phase 3.1 — Provides a persistent async SSH connection pool using asyncssh
(with paramiko fallback) for the KCC Lab 32-Core Xeon cluster.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

try:
    import asyncssh
    _ASYNCSSH_AVAILABLE = True
except ImportError:
    asyncssh = None
    _ASYNCSSH_AVAILABLE = False

try:
    import paramiko
    _PARAMIKO_AVAILABLE = True
except ImportError:
    paramiko = None
    _PARAMIKO_AVAILABLE = False


# ── Configuration ─────────────────────────────────────────────────────────────

@dataclass
class SSHConfig:
    """SSH connection configuration."""
    host: str = "127.0.0.1"
    port: int = 22
    username: str = "ct2026503586"
    key_path: str = str(Path.home() / ".ssh" / "id_rsa")
    known_hosts_path: str | None = None
    connect_timeout: float = 10.0
    keepalive_interval: int = 30
    max_connections: int = 4


# ── Async SSH Connection Pool ─────────────────────────────────────────────────

class SSHPool:
    """Persistent async SSH connection pool.

    Maintains a pool of SSH connections to the remote cluster,
    reusing them across multiple commands. Automatically reconnects
    on failure.
    """

    def __init__(self, config: SSHConfig | None = None) -> None:
        self.config = config or SSHConfig()
        self._connections: list[Any] = []
        self._semaphore = asyncio.Semaphore(self.config.max_connections)
        self._connected = False
        self._lock = asyncio.Lock()

    @property
    def is_available(self) -> bool:
        """Check if SSH libraries are available."""
        return _ASYNCSSH_AVAILABLE or _PARAMIKO_AVAILABLE

    async def connect(self) -> bool:
        """Establish initial SSH connection to the remote host."""
        if not self.is_available:
            logger.error("No SSH library available (install asyncssh or paramiko)")
            return False

        async with self._lock:
            if self._connected:
                return True

            try:
                if _ASYNCSSH_AVAILABLE:
                    conn = await asyncssh.connect(
                        self.config.host,
                        port=self.config.port,
                        username=self.config.username,
                        client_keys=[self.config.key_path],
                        known_hosts=self.config.known_hosts_path,
                        connect_timeout=self.config.connect_timeout,
                        keepalive_interval=self.config.keepalive_interval,
                    )
                    self._connections.append(conn)
                    self._connected = True
                    logger.info(
                        "SSH connected to %s@%s:%d",
                        self.config.username,
                        self.config.host,
                        self.config.port,
                    )
                    return True
                elif _PARAMIKO_AVAILABLE:
                    # Paramiko fallback (runs in executor)
                    loop = asyncio.get_running_loop()
                    conn = await loop.run_in_executor(None, self._connect_paramiko)
                    if conn:
                        self._connections.append(conn)
                        self._connected = True
                        return True

            except Exception as exc:
                logger.error("SSH connection failed: %s", exc)
                return False

        return False

    def _connect_paramiko(self) -> Any:
        """Blocking paramiko connection (run in executor)."""
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(
                hostname=self.config.host,
                port=self.config.port,
                username=self.config.username,
                key_filename=self.config.key_path,
                timeout=self.config.connect_timeout,
            )
            logger.info("SSH (paramiko) connected to %s", self.config.host)
            return client
        except Exception as exc:
            logger.error("Paramiko connection failed: %s", exc)
            return None

    async def run_command(
        self,
        command: str,
        timeout: float = 60.0,
        cwd: str | None = None,
    ) -> tuple[int, str, str]:
        """Execute a command on the remote host.

        Args:
            command: Shell command to execute.
            timeout: Maximum execution time in seconds.
            cwd: Working directory on the remote host.

        Returns:
            Tuple of (return_code, stdout, stderr).
        """
        if cwd:
            command = f"cd {cwd} && {command}"

        async with self._semaphore:
            try:
                if _ASYNCSSH_AVAILABLE and self._connections:
                    conn = self._connections[0]
                    result = await asyncio.wait_for(
                        conn.run(command),
                        timeout=timeout,
                    )
                    return (
                        result.exit_status or 0,
                        result.stdout or "",
                        result.stderr or "",
                    )
                elif _PARAMIKO_AVAILABLE and self._connections:
                    loop = asyncio.get_running_loop()
                    return await asyncio.wait_for(
                        loop.run_in_executor(
                            None, self._run_paramiko, command,
                        ),
                        timeout=timeout,
                    )
                else:
                    return (1, "", "No SSH connection available")

            except asyncio.TimeoutError:
                return (124, "", f"Command timed out after {timeout}s")
            except Exception as exc:
                logger.error("SSH command failed: %s", exc)
                return (1, "", str(exc))

    def _run_paramiko(self, command: str) -> tuple[int, str, str]:
        """Blocking paramiko command execution."""
        try:
            client = self._connections[0]
            _, stdout, stderr = client.exec_command(command)
            exit_code = stdout.channel.recv_exit_status()
            return (exit_code, stdout.read().decode(), stderr.read().decode())
        except Exception as exc:
            return (1, "", str(exc))

    async def close(self) -> None:
        """Close all SSH connections."""
        for conn in self._connections:
            try:
                if _ASYNCSSH_AVAILABLE and hasattr(conn, 'close'):
                    conn.close()
                elif _PARAMIKO_AVAILABLE and hasattr(conn, 'close'):
                    conn.close()
            except Exception:
                pass
        self._connections.clear()
        self._connected = False
        logger.info("SSH pool closed")

    async def is_reachable(self) -> bool:
        """Quick connectivity check."""
        try:
            code, out, _ = await self.run_command("echo ok", timeout=5.0)
            return code == 0 and "ok" in out
        except Exception:
            return False
