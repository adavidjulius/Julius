"""
Unit tests for platform compatibility layer (src/platform_compat.py).
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from src.platform_compat import (
    IS_LINUX,
    IS_MACOS,
    IS_WINDOWS,
    IS_WSL,
    copy_to_clipboard,
    get_clipboard_text,
    get_cache_dir,
    get_config_dir,
    get_data_dir,
    get_platform_name,
    get_temp_dir,
    open_in_default_app,
    python_executable,
    safe_chmod,
    shell_exec,
    which,
)


def test_platform_flags_consistency():
    """Verify that OS flags are mutually coherent."""
    # At most one primary OS flag is true
    os_count = sum([IS_WINDOWS, IS_MACOS, IS_LINUX])
    assert os_count == 1, f"Expected exactly 1 OS flag to be True, got {os_count}"

    name = get_platform_name()
    if IS_WSL:
        assert name == "wsl"
    elif IS_WINDOWS:
        assert name == "windows"
    elif IS_MACOS:
        assert name == "macos"
    elif IS_LINUX:
        assert name == "linux"


def test_standard_directory_paths():
    """Verify standard directories return valid Path objects and exist."""
    cfg = get_config_dir("JuliusTest")
    cache = get_cache_dir("JuliusTest")
    data = get_data_dir("JuliusTest")
    tmp = get_temp_dir()

    assert isinstance(cfg, Path)
    assert isinstance(cache, Path)
    assert isinstance(data, Path)
    assert isinstance(tmp, Path)

    assert cfg.exists()
    assert cache.exists()
    assert data.exists()
    assert tmp.exists()

    # Clean up test dirs
    for d in (cfg, cache, data):
        try:
            d.rmdir()
        except OSError:
            pass


def test_python_executable_resolution():
    """Verify python_executable finds a usable python binary."""
    py_path = python_executable()
    assert py_path, "python_executable() returned empty string"
    assert Path(py_path).is_file() or Path(py_path).exists()


def test_safe_chmod(tmp_path: Path):
    """Verify safe_chmod works without raising errors."""
    test_file = tmp_path / "test_file.txt"
    test_file.write_text("hello", encoding="utf-8")
    safe_chmod(test_file, 0o755)
    assert test_file.exists()


def test_which():
    """Verify which finds standard executables."""
    # python or python3 should exist in any test environment
    cand = which("python") or which("python3")
    assert cand is not None
    assert Path(cand).exists()


def test_clipboard_windows_mock():
    """Verify Windows clip path when on Windows."""
    with patch("src.platform_compat.IS_WINDOWS", True):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            success = copy_to_clipboard("test clipboard text")
            assert success is True
            mock_run.assert_called_once()
            assert mock_run.call_args[0][0] == ["clip"]


def test_clipboard_macos_mock():
    """Verify macOS pbcopy path when on macOS."""
    with patch("src.platform_compat.IS_WINDOWS", False):
        with patch("src.platform_compat.IS_MACOS", True):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)
                success = copy_to_clipboard("test clipboard text")
                assert success is True
                mock_run.assert_called_once()
                assert mock_run.call_args[0][0] == ["pbcopy"]


def test_clipboard_linux_mock():
    """Verify Linux wl-copy / xclip path when on Linux."""
    with patch("src.platform_compat.IS_WINDOWS", False):
        with patch("src.platform_compat.IS_MACOS", False):
            with patch("src.platform_compat.IS_LINUX", True):
                with patch("subprocess.run") as mock_run:
                    mock_run.return_value = MagicMock(returncode=0)
                    success = copy_to_clipboard("test clipboard text")
                    assert success is True
                    mock_run.assert_called_once()
                    assert mock_run.call_args[0][0] == ["wl-copy"]


def test_open_in_default_app_mock():
    """Verify open_in_default_app delegates to appropriate OS command."""
    with patch("src.platform_compat.IS_WINDOWS", False):
        with patch("src.platform_compat.IS_MACOS", True):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)
                res = open_in_default_app("some_doc.pdf")
                assert res is True
                assert mock_run.call_args[0][0] == ["open", "some_doc.pdf"]


def test_get_clipboard_text_mock():
    """Verify get_clipboard_text delegates to pbpaste on macOS."""
    with patch("src.platform_compat.IS_WINDOWS", False):
        with patch("src.platform_compat.IS_MACOS", True):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout="retrieved clipboard text")
                text = get_clipboard_text()
                assert text == "retrieved clipboard text"
                assert mock_run.call_args[0][0] == ["pbpaste"]


def test_shell_exec_basic():
    """Verify shell_exec runs simple echo."""
    proc = shell_exec("echo julius_test")
    assert proc.returncode == 0
    assert "julius_test" in proc.stdout
