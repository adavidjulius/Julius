"""
MediaTek BROM/Preloader Daemon for Hardware Research.

Phase 3.2 — Milestone 3.2: Automated MediaTek hardware research copilot
for the Oppo A16 (CPH2269). Monitors USB events, catches Preloader/BROM
mode windows, and automatically initiates mtkclient handshake payloads.

Also provides ADB/scrcpy tunnel management for live device screen streaming.
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

from .usb_listener import USBDeviceEvent, USBDeviceMode, USBListener

logger = logging.getLogger(__name__)


# ── Configuration ─────────────────────────────────────────────────────────────

@dataclass
class MTKConfig:
    """MediaTek research daemon configuration."""
    mtkclient_path: str = ""  # Path to mtkclient binary/script
    device_model: str = "CPH2269"  # Oppo A16
    auto_handshake: bool = True
    handshake_timeout: float = 10.0
    scrcpy_port: int = 8100
    adb_path: str = "adb"
    log_dir: str = str(Path.home() / ".julius" / "mtk_logs")


@dataclass
class HandshakeResult:
    """Result of a BROM handshake attempt."""
    success: bool
    duration_ms: float
    device_mode: str
    output: str = ""
    error: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "mtk.handshake_result",
            "success": self.success,
            "duration_ms": self.duration_ms,
            "device_mode": self.device_mode,
            "output": self.output[:500],
            "error": self.error[:200],
            "timestamp": self.timestamp,
        }


# ── MTK Daemon ────────────────────────────────────────────────────────────────

class MTKDaemon:
    """MediaTek hardware research daemon.

    Orchestrates USB monitoring, BROM handshake triggering, and
    ADB/scrcpy tunneling for the Oppo A16 research target.

    Usage::

        daemon = MTKDaemon(on_event=ws_send)
        await daemon.start()
        # ... auto-monitors USB, catches BROM mode, initiates handshake
        await daemon.stop()
    """

    def __init__(
        self,
        config: MTKConfig | None = None,
        on_event: Optional[Callable] = None,
    ) -> None:
        self.config = config or MTKConfig()
        self._on_event = on_event
        self._usb_listener = USBListener(
            on_device=self._on_device_detected,
            poll_interval=0.1,  # 100ms for sub-120ms detection target
            on_event=on_event,
        )
        self._handshake_history: list[HandshakeResult] = []
        self._scrcpy_process: Optional[subprocess.Popen] = None
        self._running = False

        # Ensure log directory exists
        Path(self.config.log_dir).mkdir(parents=True, exist_ok=True)

    async def start(self) -> None:
        """Start the MTK daemon and USB listener."""
        self._running = True
        await self._usb_listener.start()
        logger.info("MTK daemon started for %s", self.config.device_model)

        if self._on_event:
            self._on_event({
                "type": "mtk.daemon_started",
                "device_model": self.config.device_model,
                "auto_handshake": self.config.auto_handshake,
            })

    async def stop(self) -> None:
        """Stop the daemon and cleanup resources."""
        self._running = False
        await self._usb_listener.stop()
        self._stop_scrcpy()
        logger.info("MTK daemon stopped")

    async def _on_device_detected(self, event: USBDeviceEvent) -> None:
        """Handle a newly detected MediaTek device."""
        logger.info(
            "MTK device detected: mode=%s pid=%s",
            event.device_mode.value,
            event.product_id,
        )

        if self._on_event:
            self._on_event({
                "type": "mtk.device_detected",
                "device_mode": event.device_mode.value,
                "product_id": event.product_id,
                "device_name": event.device_name,
            })

        # Trigger handshake only in Preloader mode
        if event.device_mode == USBDeviceMode.PRELOADER and self.config.auto_handshake:
            logger.info("BROM/Preloader mode detected — initiating handshake!")
            result = await self._attempt_handshake(event)
            self._handshake_history.append(result)

            if self._on_event:
                self._on_event(result.to_dict())

    async def _attempt_handshake(self, event: USBDeviceEvent) -> HandshakeResult:
        """Attempt BROM handshake using mtkclient.

        This must be triggered as fast as possible after Preloader mode
        detection, before the verified-boot lock checks kick in.
        """
        start = time.time()

        # Determine mtkclient command
        mtkclient_cmd = self.config.mtkclient_path or self._find_mtkclient()
        if not mtkclient_cmd:
            return HandshakeResult(
                success=False,
                duration_ms=(time.time() - start) * 1000,
                device_mode=event.device_mode.value,
                error="mtkclient not found in PATH",
            )

        try:
            # Run mtkclient handshake
            result = await asyncio.wait_for(
                asyncio.get_running_loop().run_in_executor(
                    None,
                    lambda: subprocess.run(
                        [mtkclient_cmd, "stage"],
                        capture_output=True,
                        text=True,
                        timeout=self.config.handshake_timeout,
                    ),
                ),
                timeout=self.config.handshake_timeout + 2,
            )

            elapsed_ms = (time.time() - start) * 1000

            # Log the attempt
            log_path = Path(self.config.log_dir) / f"handshake_{int(time.time())}.log"
            log_path.write_text(
                f"Timestamp: {time.ctime()}\n"
                f"Device: {event.device_name} (PID: {event.product_id})\n"
                f"Duration: {elapsed_ms:.1f}ms\n"
                f"Exit Code: {result.returncode}\n"
                f"STDOUT:\n{result.stdout}\n"
                f"STDERR:\n{result.stderr}\n",
            )

            return HandshakeResult(
                success=result.returncode == 0,
                duration_ms=elapsed_ms,
                device_mode=event.device_mode.value,
                output=result.stdout,
                error=result.stderr,
            )

        except asyncio.TimeoutError:
            elapsed_ms = (time.time() - start) * 1000
            return HandshakeResult(
                success=False,
                duration_ms=elapsed_ms,
                device_mode=event.device_mode.value,
                error=f"Handshake timed out after {self.config.handshake_timeout}s",
            )
        except Exception as exc:
            elapsed_ms = (time.time() - start) * 1000
            return HandshakeResult(
                success=False,
                duration_ms=elapsed_ms,
                device_mode=event.device_mode.value,
                error=str(exc),
            )

    def _find_mtkclient(self) -> str | None:
        """Find mtkclient in PATH or common locations."""
        import shutil
        path = shutil.which("mtkclient") or shutil.which("mtk")
        if path:
            return path

        # Check common install locations
        candidates = [
            Path.home() / "mtkclient" / "mtk",
            Path("/usr/local/bin/mtkclient"),
            Path("/usr/local/bin/mtk"),
        ]
        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                return str(candidate)

        return None

    # ── ADB / Scrcpy Integration ──────────────────────────────────────────────

    async def start_scrcpy(self) -> bool:
        """Start scrcpy for live device screen streaming.

        Launches scrcpy as a subprocess with appropriate flags for
        low-latency streaming.
        """
        import shutil

        scrcpy_path = shutil.which("scrcpy")
        if not scrcpy_path:
            logger.error("scrcpy not found in PATH")
            return False

        # Check ADB connectivity
        adb_check = subprocess.run(
            [self.config.adb_path, "devices"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if "device" not in adb_check.stdout:
            logger.error("No ADB device connected")
            return False

        try:
            self._scrcpy_process = subprocess.Popen(
                [
                    scrcpy_path,
                    "--port", str(self.config.scrcpy_port),
                    "--max-fps", "30",
                    "--bit-rate", "4M",
                    "--window-title", f"Julius Research — {self.config.device_model}",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            logger.info("scrcpy started on port %d", self.config.scrcpy_port)

            if self._on_event:
                self._on_event({
                    "type": "mtk.scrcpy_started",
                    "port": self.config.scrcpy_port,
                })

            return True
        except Exception as exc:
            logger.error("scrcpy launch failed: %s", exc)
            return False

    def _stop_scrcpy(self) -> None:
        """Stop the scrcpy process."""
        if self._scrcpy_process:
            self._scrcpy_process.terminate()
            self._scrcpy_process = None
            logger.info("scrcpy stopped")

    async def adb_command(self, command: str) -> tuple[int, str, str]:
        """Execute an ADB command."""
        try:
            result = await asyncio.get_running_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    [self.config.adb_path, *command.split()],
                    capture_output=True,
                    text=True,
                    timeout=30,
                ),
            )
            return result.returncode, result.stdout, result.stderr
        except Exception as exc:
            return 1, "", str(exc)

    # ── Status ────────────────────────────────────────────────────────────────

    def get_status(self) -> dict[str, Any]:
        """Return daemon status."""
        return {
            "running": self._running,
            "usb_listener_active": self._usb_listener.is_running,
            "detections": self._usb_listener.detection_count,
            "handshake_attempts": len(self._handshake_history),
            "successful_handshakes": sum(
                1 for h in self._handshake_history if h.success
            ),
            "scrcpy_active": self._scrcpy_process is not None,
            "device_model": self.config.device_model,
        }
