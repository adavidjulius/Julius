"""
USB Event Listener for MediaTek Hardware Research.

Phase 3.2 — Background USB event listener on macOS using ``ioreg``
polling for VID ``0x0E8D`` (MediaTek). Detects Preloader/BROM mode
hotplug events and triggers instant handshake callbacks.
"""

from __future__ import annotations

import asyncio
import logging
import re
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# MediaTek Vendor ID
MTK_VENDOR_ID = "0x0e8d"
MTK_VENDOR_ID_INT = 0x0E8D

# Known MediaTek Product IDs
MTK_PRELOADER_PID = "0x0003"  # Preloader/BROM mode
MTK_DA_PID = "0x2000"         # Download Agent mode
MTK_NORMAL_PIDS = {"0x2001", "0x2002", "0x2006"}  # Normal mode


class USBDeviceMode(str, Enum):
    PRELOADER = "preloader"
    DOWNLOAD_AGENT = "download_agent"
    NORMAL = "normal"
    UNKNOWN = "unknown"


@dataclass
class USBDeviceEvent:
    """Structured USB device event."""
    vendor_id: str
    product_id: str
    device_mode: USBDeviceMode
    device_name: str = ""
    serial: str = ""
    timestamp: float = field(default_factory=time.time)
    location_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "usb.device_detected",
            "vendor_id": self.vendor_id,
            "product_id": self.product_id,
            "device_mode": self.device_mode.value,
            "device_name": self.device_name,
            "serial": self.serial,
            "timestamp": self.timestamp,
        }


class USBListener:
    """Background USB event listener for MediaTek devices.

    Polls macOS ``ioreg -p IOUSB -l`` at configurable intervals to detect
    MediaTek device hotplug events. When a Preloader/BROM mode device is
    detected, immediately triggers the registered callback.

    Usage::

        listener = USBListener(on_device=my_callback)
        await listener.start()
        # ... runs in background ...
        await listener.stop()
    """

    def __init__(
        self,
        on_device: Optional[Callable[[USBDeviceEvent], Any]] = None,
        poll_interval: float = 0.25,  # 250ms polling for fast detection
        on_event: Optional[Callable] = None,
    ) -> None:
        self._on_device = on_device
        self._on_event = on_event
        self._poll_interval = poll_interval
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._known_devices: set[str] = set()
        self._detection_count = 0

    async def start(self) -> None:
        """Start the USB listener background task."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("USB listener started (poll_interval=%.2fs)", self._poll_interval)

        if self._on_event:
            self._on_event({
                "type": "usb.listener_started",
                "poll_interval": self._poll_interval,
            })

    async def stop(self) -> None:
        """Stop the USB listener."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("USB listener stopped (detected %d devices)", self._detection_count)

    async def _poll_loop(self) -> None:
        """Main polling loop."""
        while self._running:
            try:
                await self._check_usb_devices()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("USB poll error: %s", exc)

            await asyncio.sleep(self._poll_interval)

    async def _check_usb_devices(self) -> None:
        """Check for new MediaTek USB devices."""
        loop = asyncio.get_running_loop()
        devices = await loop.run_in_executor(None, self._scan_ioreg)

        current_ids = {d.location_id for d in devices}

        for device in devices:
            if device.location_id not in self._known_devices:
                # New device detected!
                self._known_devices.add(device.location_id)
                self._detection_count += 1

                logger.info(
                    "USB: MediaTek device detected! mode=%s pid=%s name=%s",
                    device.device_mode.value,
                    device.product_id,
                    device.device_name,
                )

                if self._on_event:
                    self._on_event(device.to_dict())

                if self._on_device:
                    try:
                        result = self._on_device(device)
                        if asyncio.iscoroutine(result):
                            await result
                    except Exception as exc:
                        logger.error("USB device callback error: %s", exc)

        # Remove stale devices
        self._known_devices = self._known_devices & current_ids

    def _scan_ioreg(self) -> list[USBDeviceEvent]:
        """Scan macOS ioreg for MediaTek USB devices."""
        try:
            result = subprocess.run(
                ["ioreg", "-p", "IOUSB", "-l", "-w", "0"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                return []

            return self._parse_ioreg_output(result.stdout)

        except FileNotFoundError:
            logger.debug("ioreg not found — not on macOS?")
            return []
        except Exception as exc:
            logger.error("ioreg scan failed: %s", exc)
            return []

    @staticmethod
    def classify_mode(pid_hex: str) -> USBDeviceMode:
        """Classify USB device mode from product ID."""
        pid_clean = pid_hex.lower()
        if pid_clean == MTK_PRELOADER_PID.lower():
            return USBDeviceMode.PRELOADER
        elif pid_clean == MTK_DA_PID.lower():
            return USBDeviceMode.DOWNLOAD_AGENT
        elif pid_clean in {p.lower() for p in MTK_NORMAL_PIDS}:
            return USBDeviceMode.NORMAL
        return USBDeviceMode.UNKNOWN

    def _parse_ioreg_output(self, output: str) -> list[USBDeviceEvent]:
        """Parse ioreg output to find MediaTek devices."""
        devices = []

        # Split by device entries
        entries = output.split("+-o ")

        for entry in entries:
            # Check for MediaTek vendor ID
            vid_match = re.search(r'"idVendor"\s*=\s*(\d+)', entry)
            if not vid_match:
                continue

            vid_int = int(vid_match.group(1))
            if vid_int != MTK_VENDOR_ID_INT:
                continue

            # Extract product ID
            pid_match = re.search(r'"idProduct"\s*=\s*(\d+)', entry)
            pid_int = int(pid_match.group(1)) if pid_match else 0
            pid_hex = f"0x{pid_int:04x}"

            # Extract device name
            name_match = re.search(r'"USB Product Name"\s*=\s*"([^"]*)"', entry)
            device_name = name_match.group(1) if name_match else "MediaTek Device"

            # Extract serial
            serial_match = re.search(r'"USB Serial Number"\s*=\s*"([^"]*)"', entry)
            serial = serial_match.group(1) if serial_match else ""

            # Extract location ID for tracking
            loc_match = re.search(r'"locationID"\s*=\s*(\d+)', entry)
            location_id = loc_match.group(1) if loc_match else str(vid_int)

            # Determine device mode
            mode = self.classify_mode(pid_hex)

            devices.append(USBDeviceEvent(
                vendor_id=f"0x{vid_int:04x}",
                product_id=pid_hex,
                device_mode=mode,
                device_name=device_name,
                serial=serial,
                location_id=location_id,
            ))

        return devices

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def detection_count(self) -> int:
        return self._detection_count
