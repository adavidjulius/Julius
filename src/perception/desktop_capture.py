"""
Desktop Screen & Window Perception Engine for Julius.

Provides native cross-platform OS desktop screen capture, active window
inspection, and UI element perception across macOS, Linux, and Windows.
"""

from __future__ import annotations

import io
import logging
import os
import platform
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    from PIL import Image
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False


@dataclass
class WindowInfo:
    """Information about an active application window."""
    app_name: str
    window_title: str
    pid: Optional[int] = None
    is_frontmost: bool = True
    bounds: Optional[Dict[str, int]] = None  # {x, y, width, height}


@dataclass
class ScreenCaptureResult:
    """Result of capturing the desktop screen."""
    success: bool
    image_bytes: bytes = b""
    width: int = 0
    height: int = 0
    active_window: Optional[WindowInfo] = None
    timestamp: float = field(default_factory=time.time)
    file_path: Optional[str] = None
    error: Optional[str] = None


class DesktopCaptureEngine:
    """
    Cross-platform desktop perception engine.
    Enables Julius to see the user's desktop, IDE, terminal, and browser.
    """

    def __init__(self, cache_dir: Optional[str] = None) -> None:
        self.os_type = platform.system().lower()
        self.cache_dir = Path(cache_dir or (Path.home() / ".julius" / "perception_cache"))
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        logger.info("DesktopCaptureEngine initialized for OS: %s (cache: %s)", self.os_type, self.cache_dir)

    # ── Active Window Detection ───────────────────────────────────────────────

    def get_active_window(self) -> WindowInfo:
        """
        Inspect the currently frontmost active window and application.
        Supports macOS, Linux (X11/Wayland), and Windows.
        """
        if self.os_type == "darwin":
            return self._get_active_window_macos()
        elif self.os_type == "linux":
            return self._get_active_window_linux()
        elif self.os_type == "windows":
            return self._get_active_window_windows()
        return WindowInfo(app_name="Unknown", window_title="Unknown")

    def _get_active_window_macos(self) -> WindowInfo:
        """Query macOS frontmost application and window title via AppleScript."""
        script = '''
        tell application "System Events"
            set frontApp to first application process whose frontmost is true
            set appName to name of frontApp
            set appPid to unix id of frontApp
            set windowTitle to "Unknown"
            try
                tell frontApp
                    set windowTitle to name of front window
                end tell
            end try
            return appName & "|||" & windowTitle & "|||" & (appPid as text)
        end tell
        '''
        try:
            res = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=2.0,
            )
            if res.returncode == 0 and "|||" in res.stdout:
                parts = res.stdout.strip().split("|||")
                app_name = parts[0].strip() if len(parts) > 0 else "Unknown"
                window_title = parts[1].strip() if len(parts) > 1 else "Unknown"
                pid = int(parts[2].strip()) if len(parts) > 2 and parts[2].strip().isdigit() else None
                return WindowInfo(app_name=app_name, window_title=window_title, pid=pid, is_frontmost=True)
        except Exception as exc:
            logger.debug("AppleScript active window inspection failed: %s", exc)

        return WindowInfo(app_name="Desktop/Finder", window_title="Workspace", is_frontmost=True)

    def _get_active_window_linux(self) -> WindowInfo:
        """Query Linux active window via xdotool or hyprctl."""
        if shutil.which("xdotool"):
            try:
                res = subprocess.run(
                    ["xdotool", "getactivewindow", "getwindowname"],
                    capture_output=True,
                    text=True,
                    timeout=1.5,
                )
                title = res.stdout.strip() or "Unknown"
                pid_res = subprocess.run(
                    ["xdotool", "getactivewindow", "getwindowpid"],
                    capture_output=True,
                    text=True,
                    timeout=1.0,
                )
                pid = int(pid_res.stdout.strip()) if pid_res.stdout.strip().isdigit() else None
                return WindowInfo(app_name="X11 Window", window_title=title, pid=pid)
            except Exception as exc:
                logger.debug("xdotool window detection error: %s", exc)

        return WindowInfo(app_name="Linux Desktop", window_title="Active Workspace")

    def _get_active_window_windows(self) -> WindowInfo:
        """Query Windows active window via PowerShell."""
        ps_cmd = (
            'Add-Type @"\n'
            'using System;\n'
            'using System.Runtime.InteropServices;\n'
            'using System.Text;\n'
            'public class User32 {\n'
            '  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();\n'
            '  [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int count);\n'
            '}\n'
            '"@;\n'
            '$hwnd = [User32]::GetForegroundWindow();\n'
            '$title = New-Object System.Text.StringBuilder 256;\n'
            '[User32]::GetWindowText($hwnd, $title, 256) | Out-Null;\n'
            '$title.ToString()'
        )
        try:
            res = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_cmd],
                capture_output=True,
                text=True,
                timeout=2.0,
            )
            title = res.stdout.strip() or "Windows Active Window"
            return WindowInfo(app_name="Windows App", window_title=title)
        except Exception as exc:
            logger.debug("Windows PowerShell window detection error: %s", exc)

        return WindowInfo(app_name="Windows Desktop", window_title="Workspace")

    # ── Desktop Screen Capture ────────────────────────────────────────────────

    def capture_screen(
        self,
        display_index: int = 0,
        save_to_disk: bool = True,
    ) -> ScreenCaptureResult:
        """
        Capture the current desktop display.
        Uses native OS screen capture commands for zero external dependency overhead.
        """
        timestamp = time.time()
        temp_file = self.cache_dir / f"screen_{int(timestamp)}.png"
        active_window = self.get_active_window()

        success = False
        error_msg = None

        if self.os_type == "darwin":
            success, error_msg = self._capture_macos(temp_file)
        elif self.os_type == "linux":
            success, error_msg = self._capture_linux(temp_file)
        elif self.os_type == "windows":
            success, error_msg = self._capture_windows(temp_file)
        else:
            success, error_msg = self._capture_pil_fallback(temp_file)

        if not success or not temp_file.exists():
            return ScreenCaptureResult(
                success=False,
                active_window=active_window,
                error=error_msg or "Failed to capture desktop screenshot",
            )

        try:
            with open(temp_file, "rb") as f:
                img_bytes = f.read()

            width, height = 0, 0
            if _PIL_AVAILABLE:
                with Image.open(io.BytesIO(img_bytes)) as img:
                    width, height = img.size

            return ScreenCaptureResult(
                success=True,
                image_bytes=img_bytes,
                width=width,
                height=height,
                active_window=active_window,
                file_path=str(temp_file) if save_to_disk else None,
            )
        except Exception as read_exc:
            return ScreenCaptureResult(
                success=False,
                active_window=active_window,
                error=f"Error processing screenshot: {read_exc}",
            )

    def _capture_macos(self, dest_path: Path) -> Tuple[bool, Optional[str]]:
        """Capture macOS screen via native screencapture binary."""
        try:
            # -x: mute audio chime, -C: capture cursor
            cmd = ["screencapture", "-x", "-C", str(dest_path)]
            res = subprocess.run(cmd, capture_output=True, timeout=5.0)
            if res.returncode == 0 and dest_path.exists():
                return True, None
            return False, res.stderr.decode("utf-8", errors="ignore")
        except Exception as exc:
            return False, str(exc)

    def _capture_linux(self, dest_path: Path) -> Tuple[bool, Optional[str]]:
        """Capture Linux screen via scrot, import, or gnome-screenshot."""
        for tool, args in [
            ("scrot", ["scrot", str(dest_path)]),
            ("import", ["import", "-window", "root", str(dest_path)]),
            ("gnome-screenshot", ["gnome-screenshot", "-f", str(dest_path)]),
        ]:
            if shutil.which(tool):
                try:
                    res = subprocess.run(args, capture_output=True, timeout=5.0)
                    if res.returncode == 0 and dest_path.exists():
                        return True, None
                except Exception:
                    continue
        return self._capture_pil_fallback(dest_path)

    def _capture_windows(self, dest_path: Path) -> Tuple[bool, Optional[str]]:
        """Capture Windows screen via PowerShell and .NET Graphics."""
        ps_code = f"""
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$bmp = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
$graphics = [System.Drawing.Graphics]::FromImage($bmp)
$graphics.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
$bmp.Save("{dest_path}", [System.Drawing.Imaging.ImageFormat]::Png)
$graphics.Dispose()
$bmp.Dispose()
"""
        try:
            res = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_code],
                capture_output=True,
                timeout=5.0,
            )
            if res.returncode == 0 and dest_path.exists():
                return True, None
            return False, res.stderr.decode("utf-8", errors="ignore")
        except Exception:
            return self._capture_pil_fallback(dest_path)

    def _capture_pil_fallback(self, dest_path: Path) -> Tuple[bool, Optional[str]]:
        """Universal fallback using PIL.ImageGrab."""
        if not _PIL_AVAILABLE:
            return False, "PIL/Pillow is not installed for fallback screen capture."
        try:
            from PIL import ImageGrab
            screenshot = ImageGrab.grab()
            screenshot.save(str(dest_path), format="PNG")
            return True, None
        except Exception as exc:
            return False, f"PIL ImageGrab error: {exc}"


# Singleton instance
_desktop_engine: Optional[DesktopCaptureEngine] = None


def get_desktop_engine() -> DesktopCaptureEngine:
    """Get or instantiate the global DesktopCaptureEngine."""
    global _desktop_engine
    if _desktop_engine is None:
        _desktop_engine = DesktopCaptureEngine()
    return _desktop_engine
