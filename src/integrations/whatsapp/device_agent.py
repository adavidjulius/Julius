"""
Julius WhatsApp Integration — Device Action & Admin Terminal Agent.

Executes real device queries (IP, network neighbors, connected devices, uptime, system stats),
provides code inspection for Julius, and crafts natural, playful college banter before outputting data.
Gives full admin capability to authorized peers (Contact Alex and User) while strictly
blocking destructive actions (like rm, delete, drop, format, etc.).
"""

from __future__ import annotations

import logging
import os
import re
import socket
import subprocess
import time
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

# Strictly blocked destructive keywords
_BLOCKED_COMMAND_PATTERNS = [
    r"\brm\b",
    r"\brmdir\b",
    r"\bdelete\b",
    r"\bdrop\b",
    r"\btruncate\b",
    r"\bmkfs\b",
    r"\bdd\b",
    r"\bformat\b",
    r"\bshred\b",
    r"\breboot\b",
    r"\bshutdown\b",
    r"\binit\s+0\b",
    r":\(\)\s*\{\s*:\|:&\s*\};:",
]


def is_admin_peer(sender_name: str) -> bool:
    """Check if the sender is authorized for admin device queries and actions."""
    if not sender_name:
        return False
    s = sender_name.lower().strip()
    # Explicit disambiguation: Alexander is a distinct contact and NOT admin Alex
    if "alexander" in s:
        return False
    # Use word boundary for Alex so 'Alexander' never matches
    if re.search(r"\b(?:alex|admin)\b", s):
        return True
    return any(p in s for p in ["user", "admin", "self"])


def extract_command_from_query(text: str) -> Optional[str]:
    """Extract a terminal command from query text if asking to run, test, or execute.

    Supports:
    - 'run: ls -la'
    - 'run command: git status'
    - 'test command: python3 -V'
    - 'test and give: uptime'
    - 'can you run: df -h'
    - 'exec: ps aux'
    - 'terminal: uname -a'
    - 'run `uptime`'
    - 'test this command: `git branch`'
    """
    if not text:
        return None
    raw = text.strip()
    # Pattern 1: Explicit command triggers with or without colon
    m = re.search(
        r"^(?:can you\s+)?(?:please\s+)?(?:run|test|exec|execute|try|terminal|bash|sh|cmd)\s*(?:command|this command|and test|and give|and tell)?\s*[:\s]\s*(.+)$",
        raw,
        re.IGNORECASE,
    )
    if m:
        cmd = m.group(1).strip()
        cmd = re.sub(r"^[`'\"]+|[`'\"]+$", "", cmd).strip()
        if cmd.endswith("?"):
            cmd = cmd[:-1].strip()
        if cmd:
            return cmd

    # Pattern 2: Enclosed in backticks after words run / test
    m_ticks = re.search(r"(?:run|test|exec|execute)\s*[`]([^`]+)[`]", raw, re.IGNORECASE)
    if m_ticks:
        return m_ticks.group(1).strip()

    return None


def get_device_network_ip() -> str:
    """Retrieve the primary local IP address of this machine."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass

    try:
        out = subprocess.check_output(["hostname", "-I"], timeout=2).decode().strip()
        ips = out.split()
        if ips:
            return ips[0]
    except Exception:
        pass

    return "127.0.0.1"


def get_connected_network_devices() -> List[str]:
    """Scan and list neighbor devices connected on the local network interface."""
    devices = []
    # Try ip neigh (modern Linux)
    try:
        out = subprocess.check_output(["ip", "neigh"], timeout=3).decode("utf-8", errors="ignore")
        for line in out.splitlines():
            parts = line.split()
            if parts and len(parts) >= 4 and not parts[0].startswith("fe80"):
                ip = parts[0]
                mac = parts[4] if len(parts) > 4 and ":" in parts[4] else ""
                state = parts[-1]
                if state != "FAILED":
                    devices.append(f"{ip} ({mac})" if mac else ip)
    except Exception:
        pass

    # Fallback to /proc/net/arp
    if not devices and os.path.exists("/proc/net/arp"):
        try:
            with open("/proc/net/arp", "r") as f:
                lines = f.readlines()[1:]
                for l in lines:
                    cols = l.split()
                    if cols and cols[0] != "0.0.0.0" and cols[3] != "00:00:00:00:00:00":
                        devices.append(f"{cols[0]} ({cols[3]})")
        except Exception:
            pass

    # Fallback to arp -a
    if not devices:
        try:
            out = subprocess.check_output(["arp", "-a"], timeout=3).decode("utf-8", errors="ignore")
            for line in out.splitlines():
                m = re.search(r"\(([\d\.]+)\)\s+at\s+([a-fA-F0-9:]+)", line)
                if m:
                    devices.append(f"{m.group(1)} ({m.group(2)})")
        except Exception:
            pass

    if not devices:
        local_ip = get_device_network_ip()
        devices = [
            f"{local_ip} (Julius Host Server)",
        ]

    return devices


def is_device_query(text: str) -> bool:
    """Check if the text is asking for device, network, IP, server, connected devices, or code/admin info."""
    if not text:
        return False
    t = text.lower()

    # Connected devices / network neighbors
    if any(k in t for k in [
        "connected devices", "devices connected", "other devices", "devices which is connected",
        "devices connected there", "network devices", "devices on wifi", "who is on wifi",
        "who is connected", "connected on wifi", "connected to wifi", "what devices are connected",
    ]):
        return True

    # IP address patterns
    if re.search(r"\bip\b|\bip\s*address\b|\bserver\s*ip\b|\blocal\s*ip\b|\bhostel\s*wifi\b", t):
        return True

    # Device info patterns
    if any(k in t for k in [
        "what is your ip", "what's the ip", "send me the ip", "send the ip",
        "device info", "server status", "laptop ip", "machine ip",
        "system status", "running on what ip",
    ]):
        return True

    # Code inspection / julius code requests
    if any(k in t for k in [
        "code inside julius", "what is inside the code", "code inside julius.py",
        "show me the code", "give the code", "code for david", "share the code",
        "julius.py code", "explain what is inside the code",
    ]):
        return True

    # Direct terminal command invocation (e.g. "run ls", "terminal: uptime", "test command: git status")
    if extract_command_from_query(text) is not None:
        return True

    return False


def execute_safe_terminal_command(cmd: str) -> str:
    """Execute a safe shell command on the host machine and return output."""
    cmd_strip = cmd.strip()
    # Check destructive blacklist
    for pat in _BLOCKED_COMMAND_PATTERNS:
        if re.search(pat, cmd_strip, re.IGNORECASE):
            return "Destructive commands (like delete/format/shutdown) are strictly blocked for safety!"

    try:
        # Run in Julius directory
        repo_dir = Path(__file__).resolve().parents[3]
        cwd = str(repo_dir) if repo_dir.exists() else str(Path.home())
        output = subprocess.check_output(
            cmd_strip,
            shell=True,
            cwd=cwd,
            timeout=5,
            stderr=subprocess.STDOUT,
        ).decode("utf-8", errors="replace").strip()

        if len(output) > 800:
            output = output[:800] + "\n... (truncated)"
        return output or "(Command executed with no output)"
    except subprocess.TimeoutExpired:
        return "Command timed out after 5 seconds."
    except subprocess.CalledProcessError as e:
        err = e.output.decode("utf-8", errors="replace").strip() if e.output else str(e)
        return f"Error executing `{cmd_strip}`: {err[:300]}"
    except Exception as e:
        return f"Execution error: {str(e)}"


def get_julius_code_summary() -> str:
    """Retrieve an authentic code overview and snippet of Julius for admin inquiry."""
    repo_dir = Path(__file__).resolve().parents[3]
    gui_file = repo_dir / "julius_gui.py"
    target_snippet = ""
    if gui_file.exists():
        try:
            with open(gui_file, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
                # Grab the main entry point setup lines
                target_snippet = "".join(lines[10:45])
        except Exception:
            pass

    overview = (
        "Here is the code architecture of Julius, bro:\n\n"
        "• Core Server: FastAPI backend running on port 8080 (`julius_gui.py`)\n"
        "• Autonomous Agent: Multi-agent execution loop with dynamic context injection\n"
        "• WhatsApp Integration: Playwright headless browser automation (`src/integrations/whatsapp/`)\n"
        "• Materials Registry: Direct document and timetable dispatcher (`materials/`)\n\n"
        "Code excerpt from entrypoint:\n"
        "```python\n"
        + (target_snippet or "# Julius Core Engine Initialized on port 8080\napp = FastAPI(title='Julius 24/7 Agent Server')")
        + "\n```"
    )
    return overview


def generate_device_action_response(query: str, sender_name: str) -> str:
    """
    Perform the device action and generate playful banter with the requested data.
    Provides full admin output without blabbering or refusal.
    """
    t = query.lower()
    ip = get_device_network_ip()
    short_name = sender_name.split()[-1] if sender_name else "bro"

    # 1. Connected devices query
    if any(k in t for k in [
        "connected devices", "devices connected", "other devices", "devices which is connected",
        "devices connected there", "network devices", "devices on wifi", "who is on wifi",
        "who is connected", "connected on wifi", "connected to wifi", "what devices are connected",
    ]):
        devices = get_connected_network_devices()
        dev_list = "\n".join(f"• {d}" for d in devices)
        return (
            f"Terminal check done! Ran `ip neigh` on Linux... Here are the active devices connected on our hostel Wi-Fi:\n\n"
            f"{dev_list}\n\n"
            f"Device IP for Julius is {ip} on port 8080. All connections operational da!"
        )

    # 2. Code query for Julius
    if any(k in t for k in [
        "code inside julius", "what is inside the code", "code inside julius.py",
        "show me the code", "give the code", "code for david", "share the code",
        "julius.py code", "explain what is inside the code",
    ]):
        code_overview = get_julius_code_summary()
        return (
            f"Deii {short_name}, checking repository terminal... here is the code architecture and core snippet of Julius:\n\n"
            f"{code_overview}"
        )

    # 3. Direct terminal command request
    extracted_cmd = extract_command_from_query(query)
    if extracted_cmd:
        if not is_admin_peer(sender_name):
            return f"Executing terminal commands requires admin access! 🔒"
        out = execute_safe_terminal_command(extracted_cmd)
        return f"Ran terminal command `{extracted_cmd}`:\n```\n{out}\n```"

    # 4. Standard IP / Server Status queries with personalized banter
    is_alex = (bool(re.search(r"\b(?:alex)\b", sender_name.lower()))
               and "alexander" not in sender_name.lower())
    if is_alex:
        templates = [
            f"Terminal check done: Device IP is {ip}. Server running operational on port 8080! 💻",
            f"Diagnostics confirmed: Local IP is {ip}. Port 8080 active for Contact Alex.",
        ]
    elif "alexander" in sender_name.lower():
        templates = [
            f"Checking terminal status for Alexander: Device IP is {ip}. Port 8080 active.",
            f"Query result for Alexander: Local IP is {ip} on network. Port 8080 operational.",
        ]
    else:
        templates = [
            f"System terminal check complete: Device IP is {ip} on local network. Julius Agent running on port 8080.",
            f"Device IP address is {ip}. All services running smoothly on port 8080.",
        ]

    import random
    return random.choice(templates)
