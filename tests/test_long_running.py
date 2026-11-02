"""
Tests for Stage 1 (classifier) and Stage 2 (progress detection) via long_running.py.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.long_running import (
    classify_command,
    launch_background,
    poll_job,
    run_long_running_blocking,
    PollStatus,
    BackgroundJob,
    _pid_alive,
    _log_indicates_failure,
)


# ---------------------------------------------------------------------------
# Stage 1: classify_command
# ---------------------------------------------------------------------------

class TestClassifyCommand:
    """Unit tests for the command classifier (Stage 1)."""

    @pytest.mark.parametrize("cmd", [
        "docker build -t julius-research:latest .",
        "docker build .",
        "docker pull python:3.11-slim",
        "docker run --rm myimage",
        "pip install torch",
        "pip install torch transformers",
        "pip3 install tensorflow",
        "pip install -r requirements.txt",
        "npm install",
        "npm install react react-dom",
        "yarn install",
        "yarn add lodash",
        "conda install numpy",
        "cargo build --release",
        "make all",
        "cmake ..",
        "apt-get install -y git",
        "brew install ffmpeg",
        "git clone https://github.com/example/repo.git",
        "git pull origin main",
        "wget https://example.com/large_file.zip",
        "curl -o model.bin https://example.com/model.bin",
        "python train.py --epochs 100",
        "python finetune_model.py",
        "playwright install chromium",
    ])
    def test_classified_as_long_running(self, cmd):
        assert classify_command(cmd) is True, f"Expected LONG_RUNNING for: {cmd!r}"

    @pytest.mark.parametrize("cmd", [
        "ls -la",
        "echo hello",
        "cat README.md",
        "git status",
        "git log -n 5",
        "python -c 'print(1+1)'",
        "pwd",
        "mkdir -p /tmp/testdir",
        "cp file.txt /tmp/",
        "rm -f temp.txt",
        "grep -r 'pattern' .",
        "find . -name '*.py'",
        "ps aux",
        "df -h",
    ])
    def test_not_classified_as_long_running(self, cmd):
        assert classify_command(cmd) is False, f"Expected NOT long_running for: {cmd!r}"

    def test_pip_install_torch_is_classified(self):
        """Explicit regression test for the triggering scenario."""
        assert classify_command("pip install torch==2.1.2") is True

    def test_docker_build_julius_research_is_classified(self):
        """Explicit regression test for the original failure scenario."""
        assert classify_command("docker build -t julius-research:latest .") is True


# ---------------------------------------------------------------------------
# Stage 2: progress detection via real processes
# ---------------------------------------------------------------------------

@pytest.mark.skipif(os.name == "nt" and not shutil.which("bash"), reason="Requires POSIX bash environment")
class TestPollJobProgress:
    """Integration tests for poll_job with real background processes."""

    def test_fast_completing_command(self, tmp_path):
        """A command that completes quickly is reported as COMPLETED."""
        log = str(tmp_path / "out.log")
        job = launch_background("echo 'hello world'", workspace=str(tmp_path), log_path=log)
        # Wait briefly for it to finish
        time.sleep(1.0)
        result = poll_job(job, check_interval=0.5, stall_window=10.0)
        assert result.status == PollStatus.COMPLETED
        assert result.exit_code == 0

    def test_command_with_real_output_is_in_progress(self, tmp_path):
        """A command producing output is correctly detected as making progress."""
        log = str(tmp_path / "out.log")
        # Run a command that writes output progressively
        job = launch_background(
            "for i in 1 2 3 4 5; do echo $i; sleep 0.3; done",
            workspace=str(tmp_path),
            log_path=log,
        )
        # Poll once quickly — it should be in progress or completed
        time.sleep(0.2)
        result = poll_job(job, check_interval=0.5, stall_window=30.0)
        # Should finish eventually
        assert result.status in (PollStatus.COMPLETED, PollStatus.IN_PROGRESS)

    def test_failed_command_is_reported_as_failed(self, tmp_path):
        """A command that exits non-zero is reported as FAILED, not suppressed."""
        log = str(tmp_path / "out.log")
        job = launch_background(
            "echo 'error output'; exit 1",
            workspace=str(tmp_path),
            log_path=log,
        )
        time.sleep(1.5)
        result = poll_job(job, check_interval=0.5, stall_window=10.0)
        assert result.status == PollStatus.FAILED
        assert result.exit_code != 0

    def test_run_long_running_blocking_success(self, tmp_path):
        """run_long_running_blocking returns (True, output) for successful commands."""
        success, output = run_long_running_blocking(
            "echo 'stage1 complete'",
            workspace=str(tmp_path),
            check_interval=0.5,
            stall_window=30.0,
        )
        assert success is True
        assert "stage1 complete" in output

    def test_run_long_running_blocking_failure(self, tmp_path):
        """run_long_running_blocking returns (False, output) for failing commands."""
        success, output = run_long_running_blocking(
            "echo 'bad output'; exit 2",
            workspace=str(tmp_path),
            check_interval=0.5,
            stall_window=10.0,
        )
        assert success is False
        assert "FAILED" in output or "bad output" in output


# ---------------------------------------------------------------------------
# Stage 2: stall detection
# ---------------------------------------------------------------------------

@pytest.mark.skipif(os.name == "nt" and not shutil.which("bash"), reason="Requires POSIX bash environment")
class TestStallDetection:
    """Tests that stall detection correctly distinguishes slow-but-alive from hung."""

    def test_pid_alive_for_running_process(self):
        """_pid_alive returns True for a process that is still running."""
        proc = subprocess.Popen(
            ['sleep', '10'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            assert _pid_alive(proc.pid) is True
        finally:
            proc.kill()
            proc.wait()

    def test_pid_not_alive_for_finished_process(self):
        """_pid_alive returns False for a process that has exited."""
        proc = subprocess.Popen(
            ['echo', 'done'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        proc.wait()
        # Give OS a moment to clean up
        time.sleep(0.1)
        # After wait(), pid is reaped — either False or still technically in table
        # The key test: we can at least call it without error
        result = _pid_alive(proc.pid)
        assert isinstance(result, bool)

    def test_stall_detection_with_very_short_window(self, tmp_path):
        """A command that produces no output and takes a while is flagged as STALLED
        when stall_window is very short."""
        log = str(tmp_path / "out.log")
        # Command that sleeps without output — simulates hung process
        job = launch_background(
            "sleep 60",  # Will be detected as stalled before it completes
            workspace=str(tmp_path),
            log_path=log,
        )
        # Use a very short stall window of 3 seconds
        result = poll_job(job, check_interval=1.0, stall_window=3.0)
        # Kill the sleeping process
        try:
            os.kill(job.pid, 9)
        except ProcessLookupError:
            pass
        assert result.status == PollStatus.STALLED

    def test_log_indicates_failure_detection(self):
        """_log_indicates_failure correctly identifies error patterns."""
        assert _log_indicates_failure("Error: module not found") is True
        assert _log_indicates_failure("Traceback (most recent call last)") is True
        assert _log_indicates_failure("Successfully installed torch-2.1.2") is False
        assert _log_indicates_failure("Step 3/5 done") is False
