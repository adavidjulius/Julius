"""
High-Level OS System Controller for Julius.

Provides native cross-platform operating system automation:
- System Vitals (CPU load, memory pressure, disk space, battery status)
- Native OS Notifications (macOS Notification Center, Linux notify-send, Windows Toast)
- Clipboard Management (read / write with safety redacting)
- Application Lifecycle Control (launch, focus, list, quit)
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class SystemVitals:
    """Hardware and OS telemetry snapshot."""
    cpu_percent: float = 0.0
    cpu_count: int = 1
    load_averages: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    memory_total_gb: float = 0.0
    memory_used_gb: float = 0.0
    memory_free_gb: float = 0.0
    memory_percent: float = 0.0
    disk_total_gb: float = 0.0
    disk_used_gb: float = 0.0
    disk_free_gb: float = 0.0
    disk_percent_used: float = 0.0
    battery_percent: Optional[float] = None
    battery_charging: Optional[bool] = None
    hostname: str = ""
    os_name: str = ""
    os_release: str = ""
    uptime_seconds: float = 0.0
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cpu_percent": self.cpu_percent,
            "cpu_count": self.cpu_count,
            "load_averages": list(self.load_averages),
            "memory": {
                "total_gb": round(self.memory_total_gb, 2),
                "used_gb": round(self.memory_used_gb, 2),
                "free_gb": round(self.memory_free_gb, 2),
                "percent_used": round(self.memory_percent, 1),
            },
            "disk": {
                "total_gb": round(self.disk_total_gb, 2),
                "used_gb": round(self.disk_used_gb, 2),
                "free_gb": round(self.disk_free_gb, 2),
                "percent_used": round(self.disk_percent_used, 1),
            },
            "battery": {
                "percent": self.battery_percent,
                "charging": self.battery_charging,
            } if self.battery_percent is not None else None,
            "os": f"{self.os_name} {self.os_release} ({self.hostname})",
            "uptime_seconds": int(self.uptime_seconds),
        }

    def format_summary(self) -> str:
        bat_str = f", Battery: {self.battery_percent}% {'(Charging)' if self.battery_charging else ''}" if self.battery_percent is not None else ""
        return (
            f"CPU: {self.cpu_percent}% ({self.cpu_count} cores) · "
            f"RAM: {round(self.memory_used_gb, 1)}/{round(self.memory_total_gb, 1)} GB ({round(self.memory_percent)}%) · "
            f"Disk: {round(self.disk_free_gb, 1)} GB free ({round(100 - self.disk_percent_used)}% free)"
            f"{bat_str}"
        )


class SystemController:
    """
    Central controller for native operating system automation and telemetry.
    """

    def __init__(self) -> None:
        self.os_type = platform.system().lower()
        self.hostname = platform.node()
        self.os_release = platform.release()
        logger.info("SystemController initialized for %s (%s)", self.os_type, self.hostname)

    # ── System Vitals ─────────────────────────────────────────────────────────

    def get_system_vitals(self) -> SystemVitals:
        """Collect current system CPU, memory, disk, and battery vitals."""
        vitals = SystemVitals(
            hostname=self.hostname,
            os_name=platform.system(),
            os_release=self.os_release,
        )

        # 1. CPU & Load Averages
        try:
            vitals.cpu_count = os.cpu_count() or 1
            if hasattr(os, "getloadavg"):
                vitals.load_averages = os.getloadavg()
                # Rough estimate of CPU utilization based on 1-min load average
                vitals.cpu_percent = min(100.0, round((vitals.load_averages[0] / vitals.cpu_count) * 100.0, 1))
            else:
                vitals.cpu_percent = 0.0
        except Exception as exc:
            logger.debug("CPU vitals error: %s", exc)

        # 2. Disk Usage (Root volume)
        try:
            root_path = "/" if self.os_type != "windows" else "C:\\"
            usage = shutil.disk_usage(root_path)
            vitals.disk_total_gb = usage.total / (1024 ** 3)
            vitals.disk_used_gb = usage.used / (1024 ** 3)
            vitals.disk_free_gb = usage.free / (1024 ** 3)
            vitals.disk_percent_used = (usage.used / usage.total) * 100.0 if usage.total > 0 else 0.0
        except Exception as exc:
            logger.debug("Disk usage error: %s", exc)

        # 3. Memory Telemetry
        if self.os_type == "darwin":
            self._fill_macos_memory(vitals)
        elif self.os_type == "linux":
            self._fill_linux_memory(vitals)
        elif self.os_type == "windows":
            self._fill_windows_memory(vitals)

        # 4. Battery Status
        self._fill_battery(vitals)

        # 5. Uptime
        self._fill_uptime(vitals)

        return vitals

    def _fill_macos_memory(self, vitals: SystemVitals) -> None:
        """Parse macOS vm_stat and sysctl for memory."""
        try:
            # Physical memory size
            res = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=1.0)
            if res.returncode == 0:
                total_bytes = int(res.stdout.strip())
                vitals.memory_total_gb = total_bytes / (1024 ** 3)

            # vm_stat for active/free/speculative
            vm_res = subprocess.run(["vm_stat"], capture_output=True, text=True, timeout=1.0)
            if vm_res.returncode == 0 and vitals.memory_total_gb > 0:
                page_size = 4096
                lines = vm_res.stdout.splitlines()
                pages_free = 0
                for line in lines:
                    if "Pages free:" in line:
                        pages_free = int(line.split(":")[1].strip().rstrip("."))
                    elif "Pages speculative:" in line:
                        pages_free += int(line.split(":")[1].strip().rstrip("."))

                free_gb = (pages_free * page_size) / (1024 ** 3)
                vitals.memory_free_gb = free_gb
                vitals.memory_used_gb = max(0.0, vitals.memory_total_gb - free_gb)
                vitals.memory_percent = (vitals.memory_used_gb / vitals.memory_total_gb) * 100.0
        except Exception as exc:
            logger.debug("macOS memory error: %s", exc)

    def _fill_linux_memory(self, vitals: SystemVitals) -> None:
        """Parse Linux /proc/meminfo."""
        try:
            meminfo_path = Path("/proc/meminfo")
            if meminfo_path.exists():
                data = meminfo_path.read_text()
                total_kb = 0
                avail_kb = 0
                for line in data.splitlines():
                    if line.startswith("MemTotal:"):
                        total_kb = int(line.split()[1])
                    elif line.startswith("MemAvailable:"):
                        avail_kb = int(line.split()[1])

                if total_kb > 0:
                    vitals.memory_total_gb = total_kb / (1024 ** 2)
                    vitals.memory_free_gb = avail_kb / (1024 ** 2)
                    vitals.memory_used_gb = max(0.0, vitals.memory_total_gb - vitals.memory_free_gb)
                    vitals.memory_percent = (vitals.memory_used_gb / vitals.memory_total_gb) * 100.0
        except Exception as exc:
            logger.debug("Linux memory error: %s", exc)

    def _fill_windows_memory(self, vitals: SystemVitals) -> None:
        """Query Windows memory via PowerShell."""
        try:
            ps = "Get-CimInstance Win32_OperatingSystem | Select-Object TotalVisibleMemorySize,FreePhysicalMemory | ConvertTo-Json"
            res = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=2.0)
            if res.returncode == 0:
                import json
                data = json.loads(res.stdout)
                total_kb = data.get("TotalVisibleMemorySize", 0)
                free_kb = data.get("FreePhysicalMemory", 0)
                if total_kb > 0:
                    vitals.memory_total_gb = total_kb / (1024 ** 2)
                    vitals.memory_free_gb = free_kb / (1024 ** 2)
                    vitals.memory_used_gb = max(0.0, vitals.memory_total_gb - vitals.memory_free_gb)
                    vitals.memory_percent = (vitals.memory_used_gb / vitals.memory_total_gb) * 100.0
        except Exception as exc:
            logger.debug("Windows memory error: %s", exc)

    def _fill_battery(self, vitals: SystemVitals) -> None:
        """Query battery status."""
        if self.os_type == "darwin":
            try:
                res = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True, timeout=1.0)
                if res.returncode == 0 and "%" in res.stdout:
                    import re
                    match = re.search(r"(\d+)%", res.stdout)
                    if match:
                        vitals.battery_percent = float(match.group(1))
                    vitals.battery_charging = "charging" in res.stdout.lower() or "ac power" in res.stdout.lower()
            except Exception:
                pass
        elif self.os_type == "linux":
            try:
                bat_dirs = list(Path("/sys/class/power_supply").glob("BAT*"))
                if bat_dirs:
                    cap_file = bat_dirs[0] / "capacity"
                    stat_file = bat_dirs[0] / "status"
                    if cap_file.exists():
                        vitals.battery_percent = float(cap_file.read_text().strip())
                    if stat_file.exists():
                        vitals.battery_charging = stat_file.read_text().strip().lower() in ("charging", "full")
            except Exception:
                pass

    def _fill_uptime(self, vitals: SystemVitals) -> None:
        """Get system uptime."""
        try:
            if self.os_type == "darwin":
                res = subprocess.run(["sysctl", "-n", "kern.boottime"], capture_output=True, text=True, timeout=1.0)
                if res.returncode == 0 and "sec =" in res.stdout:
                    import re
                    sec_match = re.search(r"sec\s*=\s*(\d+)", res.stdout)
                    if sec_match:
                        boot_sec = int(sec_match.group(1))
                        vitals.uptime_seconds = max(0.0, time.time() - boot_sec)
            elif self.os_type == "linux":
                up_file = Path("/proc/uptime")
                if up_file.exists():
                    vitals.uptime_seconds = float(up_file.read_text().split()[0])
        except Exception:
            pass

    # ── Native Notifications ──────────────────────────────────────────────────

    def send_notification(self, title: str, message: str, sound: bool = True) -> bool:
        """Send a native operating system notification."""
        safe_title = title.replace('"', '\\"')
        safe_msg = message.replace('"', '\\"')

        try:
            if self.os_type == "darwin":
                sound_clause = ' sound name "default"' if sound else ""
                script = f'display notification "{safe_msg}" with title "{safe_title}"{sound_clause}'
                res = subprocess.run(["osascript", "-e", script], capture_output=True, timeout=2.0)
                return res.returncode == 0

            elif self.os_type == "linux" and shutil.which("notify-send"):
                res = subprocess.run(["notify-send", safe_title, safe_msg], capture_output=True, timeout=2.0)
                return res.returncode == 0

            elif self.os_type == "windows":
                ps_script = f"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
$template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$textNodes = $template.GetElementsByTagName("text")
$textNodes.Item(0).AppendChild($template.CreateTextNode("{safe_title}")) | Out-Null
$textNodes.Item(1).AppendChild($template.CreateTextNode("{safe_msg}")) | Out-Null
$toast = [Windows.UI.Notifications.ToastNotification]::new($template)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("Julius").Show($toast)
"""
                res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_script], capture_output=True, timeout=3.0)
                return res.returncode == 0

        except Exception as exc:
            logger.warning("Failed to send system notification: %s", exc)

        return False

    # ── Clipboard Management ──────────────────────────────────────────────────

    def read_clipboard(self) -> str:
        """Read the current text content of the system clipboard."""
        try:
            if self.os_type == "darwin" and shutil.which("pbpaste"):
                res = subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=1.5)
                return res.stdout

            elif self.os_type == "linux":
                if shutil.which("xclip"):
                    res = subprocess.run(["xclip", "-selection", "clipboard", "-o"], capture_output=True, text=True, timeout=1.5)
                    return res.stdout
                elif shutil.which("wl-paste"):
                    res = subprocess.run(["wl-paste"], capture_output=True, text=True, timeout=1.5)
                    return res.stdout

            elif self.os_type == "windows":
                res = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Clipboard"], capture_output=True, text=True, timeout=1.5)
                return res.stdout.strip()

        except Exception as exc:
            logger.debug("Failed to read clipboard: %s", exc)

        return ""

    def write_clipboard(self, text: str) -> bool:
        """Write text content to the system clipboard."""
        try:
            if self.os_type == "darwin" and shutil.which("pbcopy"):
                proc = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
                proc.communicate(input=text.encode("utf-8"), timeout=1.5)
                return proc.returncode == 0

            elif self.os_type == "linux":
                if shutil.which("xclip"):
                    proc = subprocess.Popen(["xclip", "-selection", "clipboard"], stdin=subprocess.PIPE)
                    proc.communicate(input=text.encode("utf-8"), timeout=1.5)
                    return proc.returncode == 0
                elif shutil.which("wl-copy"):
                    proc = subprocess.Popen(["wl-copy"], stdin=subprocess.PIPE)
                    proc.communicate(input=text.encode("utf-8"), timeout=1.5)
                    return proc.returncode == 0

            elif self.os_type == "windows":
                proc = subprocess.Popen(["powershell", "-NoProfile", "-Command", "Set-Clipboard -Value $input"], stdin=subprocess.PIPE)
                proc.communicate(input=text.encode("utf-8"), timeout=1.5)
                return proc.returncode == 0

        except Exception as exc:
            logger.debug("Failed to write clipboard: %s", exc)

        return False

    # ── Application Lifecycle Control ─────────────────────────────────────────

    def list_running_apps(self) -> List[Dict[str, Any]]:
        """List user-visible running applications."""
        apps: List[Dict[str, Any]] = []
        try:
            if self.os_type == "darwin":
                script = '''
                tell application "System Events"
                    set appList to every application process whose visible is true
                    set res to ""
                    repeat with p in appList
                        set res to res & (name of p) & "|||" & (unix id of p as text) & "\\n"
                    end repeat
                    return res
                end tell
                '''
                res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=2.5)
                if res.returncode == 0:
                    for line in res.stdout.splitlines():
                        if "|||" in line:
                            parts = line.split("|||")
                            apps.append({"name": parts[0].strip(), "pid": int(parts[1].strip())})
            elif self.os_type == "linux":
                res = subprocess.run(["ps", "-u", str(os.getuid()), "-o", "comm,pid"], capture_output=True, text=True, timeout=2.0)
                if res.returncode == 0:
                    for line in res.stdout.splitlines()[1:]:
                        parts = line.split()
                        if len(parts) >= 2:
                            apps.append({"name": parts[0], "pid": int(parts[1])})
        except Exception as exc:
            logger.debug("Failed to list running apps: %s", exc)

        return apps

    def control_app(self, action: str, app_name: str) -> Tuple[bool, str]:
        """
        Execute application action: 'launch', 'focus', 'quit'.
        """
        action = action.lower().strip()
        app_name = app_name.strip()

        try:
            if action in ("launch", "open"):
                if self.os_type == "darwin":
                    res = subprocess.run(["open", "-a", app_name], capture_output=True, text=True, timeout=3.0)
                    if res.returncode == 0:
                        return True, f"Launched {app_name}"
                    return False, res.stderr.strip() or f"Could not launch {app_name}"
                elif self.os_type == "linux":
                    subprocess.Popen([app_name], start_new_session=True)
                    return True, f"Launched {app_name}"
                elif self.os_type == "windows":
                    subprocess.Popen(["start", app_name], shell=True)
                    return True, f"Launched {app_name}"

            elif action in ("focus", "activate"):
                if self.os_type == "darwin":
                    script = f'tell application "{app_name}" to activate'
                    res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=2.0)
                    return res.returncode == 0, f"Focused {app_name}" if res.returncode == 0 else f"Failed to focus {app_name}"

            elif action in ("quit", "close"):
                if self.os_type == "darwin":
                    script = f'tell application "{app_name}" to quit'
                    res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=2.0)
                    return res.returncode == 0, f"Quit {app_name}" if res.returncode == 0 else f"Failed to quit {app_name}"

        except Exception as exc:
            return False, f"App control error ({action} {app_name}): {exc}"

        return False, f"Unsupported app control action: {action}"


# Singleton instance
_system_controller: Optional[SystemController] = None


def get_system_controller() -> SystemController:
    """Get or instantiate global SystemController."""
    global _system_controller
    if _system_controller is None:
        _system_controller = SystemController()
    return _system_controller
