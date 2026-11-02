"""Tests for Phase 3.1: Remote Compute Offloader (Cluster Executor)."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from src.remote.cluster_executor import ClusterConfig, ClusterExecutor, RemoteResult
from src.remote.ssh_pool import SSHConfig, SSHPool


class TestClusterExecutor(unittest.IsolatedAsyncioTestCase):
    """Test suite for cluster executor, connection pooling, and transparent fallback."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def test_cluster_config_defaults(self):
        """ClusterConfig initializes with default host and offload patterns."""
        config = ClusterConfig()
        self.assertIn(config.host, ("127.0.0.1", "192.168.1.45"))
        self.assertEqual(config.username, "ct2026503586")
        self.assertIn("pytest", config.offload_patterns)
        self.assertIn("docker build", config.offload_patterns)
        self.assertTrue(config.fallback_to_local)

    def test_ssh_pool_init(self):
        """SSHPool initializes with configuration."""
        ssh_cfg = SSHConfig(host="192.168.1.45", username="test")
        pool = SSHPool(ssh_cfg)
        self.assertEqual(pool.config.host, "192.168.1.45")

    async def test_fallback_to_local_when_remote_unavailable(self):
        """ClusterExecutor automatically falls back to local execution when remote host unreachable."""
        config = ClusterConfig(host="192.0.2.1", fallback_to_local=True)  # Non-routable TEST-NET IP
        executor = ClusterExecutor(config=config, local_workspace=self.tmp_dir)

        # Mock SSHPool connect to return False
        executor._remote_available = False

        result = await executor.run("echo 'Local Fallback Test'")
        self.assertTrue(result.success)
        self.assertIn("Local Fallback Test", result.output)
        self.assertFalse(result.executed_remotely)

    async def test_remote_execution_mocked(self):
        """When remote host is connected, commands run on remote cluster."""
        config = ClusterConfig(host="192.168.1.45", fallback_to_local=True)
        executor = ClusterExecutor(config=config, local_workspace=self.tmp_dir)
        executor._remote_available = True

        # Mock sync_workspace to prevent real rsync network attempt
        executor.sync_workspace = AsyncMock(return_value=True)

        # Mock SSHPool run_command returning (exit_code, stdout, stderr)
        executor._ssh.run_command = AsyncMock(
            return_value=(0, "Remote Xeon 32-Core Output", "")
        )

        result = await executor.run_remote("pytest tests/")
        self.assertTrue(result.success)
        self.assertIn("Remote Xeon 32-Core Output", result.output)
        self.assertTrue(result.executed_remotely)


if __name__ == "__main__":
    unittest.main()
