#!/usr/bin/env python3
"""
Oppo A16 (CPH2269) Device Monitor
Monitors ADB-connected device state and logs system properties for research.
"""

import subprocess
import json
import os
import sys
from datetime import datetime

DEVICE_SERIAL = "65GQ7SZHGU89NVEA"
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logs")

def run_adb(command):
    """Execute an ADB shell command and return the output."""
    result = subprocess.run(
        f"adb -s {DEVICE_SERIAL} shell {command}",
        shell=True, capture_output=True, text=True
    )
    return result.stdout.strip()

def get_props():
    """Collect key system properties."""
    props = {}
    keys = [
        "ro.product.model",
        "ro.build.version.release",
        "ro.board.platform",
        "ro.product.manufacturer",
        "ro.build.fingerprint",
        "sys.oem_unlock_allowed",
        "ro.boot.flash.locked",
        "ro.boot.verifiedbootstate",
        "ro.build.version.sdk",
        "ro.product.cpu.abi",
        "ro.hardware",
    ]
    for key in keys:
        value = run_adb(f"getprop {key}")
        props[key] = value
    return props

def check_connection():
    """Check if the device is connected via ADB."""
    result = subprocess.run("adb devices", shell=True, capture_output=True, text=True)
    return DEVICE_SERIAL in result.stdout and "device" in result.stdout

def save_snapshot():
    """Take a device snapshot and save to log file."""
    timestamp = datetime.now().isoformat()
    connected = check_connection()

    snapshot = {
        "timestamp": timestamp,
        "device_serial": DEVICE_SERIAL,
        "connected": connected,
    }

    if connected:
        snapshot["properties"] = get_props()
    else:
        snapshot["error"] = "Device not connected"

    log_file = os.path.join(LOG_DIR, f"snapshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(log_file, "w") as f:
        json.dump(snapshot, f, indent=2)

    print(f"Snapshot saved: {log_file}")
    return snapshot

def monitor_loop(interval=60):
    """Continuously monitor device at given interval in seconds."""
    print(f"Starting Oppo A16 monitor (interval: {interval}s)...")
    print(f"Device: {DEVICE_SERIAL}")
    print(f"Logs: {LOG_DIR}")
    print("Press Ctrl+C to stop.\n")

    try:
        while True:
            snapshot = save_snapshot()
            if snapshot.get("connected"):
                props = snapshot.get("properties", {})
                model = props.get("ro.product.model", "unknown")
                android = props.get("ro.build.version.release", "?")
                oem_unlock = props.get("sys.oem_unlock_allowed", "?")
                print(f"  Model: {model} | Android: {android} | OEM Unlock: {oem_unlock}")
            else:
                print("  Device disconnected!")
            import time
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nMonitoring stopped.")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        snapshot = save_snapshot()
        print(json.dumps(snapshot, indent=2))
    elif len(sys.argv) > 1 and sys.argv[1] == "--monitor":
        interval = int(sys.argv[2]) if len(sys.argv) > 2 else 60
        monitor_loop(interval)
    else:
        print("Usage:")
        print("  python device_monitor.py --once       # Take a single snapshot")
        print("  python device_monitor.py --monitor [N] # Monitor every N seconds (default 60)")
