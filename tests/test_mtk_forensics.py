"""Tests for Phase 3.2: MediaTek Forensics Copilot for Oppo A16."""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from src.research.mtk_daemon import HandshakeResult, MTKConfig, MTKDaemon
from src.research.usb_listener import (
    MTK_DA_PID,
    MTK_PRELOADER_PID,
    MTK_VENDOR_ID,
    USBDeviceEvent,
    USBDeviceMode,
    USBListener,
)


class TestMTKForensics(unittest.IsolatedAsyncioTestCase):
    """Test suite for MTK daemon, USB hotplug detection, and BROM handshake."""

    def test_usb_device_mode_classification(self):
        """USB listener properly classifies device modes based on PID."""
        listener = USBListener()
        self.assertEqual(
            listener.classify_mode(MTK_PRELOADER_PID), USBDeviceMode.PRELOADER
        )
        self.assertEqual(
            listener.classify_mode(MTK_DA_PID), USBDeviceMode.DOWNLOAD_AGENT
        )
        self.assertEqual(
            listener.classify_mode("0x2001"), USBDeviceMode.NORMAL
        )
        self.assertEqual(
            listener.classify_mode("0x9999"), USBDeviceMode.UNKNOWN
        )

    def test_mtk_config_defaults(self):
        """MTKConfig initializes with Oppo A16 model and auto-handshake enabled."""
        config = MTKConfig()
        self.assertEqual(config.device_model, "CPH2269")
        self.assertTrue(config.auto_handshake)
        self.assertEqual(config.scrcpy_port, 8100)

    async def test_daemon_lifecycle(self):
        """MTKDaemon starts and stops USB listener cleanly."""
        daemon = MTKDaemon()
        self.assertFalse(daemon.get_status()["running"])

        # Patch USBListener start and stop to avoid real ioreg polling
        with patch.object(daemon._usb_listener, "start", new_callable=AsyncMock) as mock_start, \
             patch.object(daemon._usb_listener, "stop", new_callable=AsyncMock) as mock_stop:
            await daemon.start()
            self.assertTrue(daemon.get_status()["running"])
            mock_start.assert_called_once()

            await daemon.stop()
            self.assertFalse(daemon.get_status()["running"])
            mock_stop.assert_called_once()

    async def test_auto_handshake_trigger_on_preloader(self):
        """Preloader mode event triggers automated BROM handshake."""
        events = []
        daemon = MTKDaemon(on_event=lambda ev: events.append(ev))

        # Mock handshake attempt
        mock_result = HandshakeResult(
            success=True,
            duration_ms=45.0,
            device_mode="preloader",
            output="BROM handshake sequence complete",
        )
        daemon._attempt_handshake = AsyncMock(return_value=mock_result)

        event = USBDeviceEvent(
            vendor_id=MTK_VENDOR_ID,
            product_id=MTK_PRELOADER_PID,
            device_mode=USBDeviceMode.PRELOADER,
            device_name="MediaTek Preloader",
        )

        await daemon._on_device_detected(event)

        daemon._attempt_handshake.assert_called_once_with(event)
        self.assertEqual(len(daemon._handshake_history), 1)
        self.assertTrue(daemon._handshake_history[0].success)

        status = daemon.get_status()
        self.assertEqual(status["handshake_attempts"], 1)
        self.assertEqual(status["successful_handshakes"], 1)

    async def test_adb_command_execution_mocked(self):
        """ADB commands can be dispatched and parsed asynchronously."""
        daemon = MTKDaemon()

        with patch("subprocess.run") as mock_sub:
            mock_sub.return_value = MagicMock(
                returncode=0, stdout="List of devices attached\nCPH2269\tdevice\n", stderr=""
            )
            code, stdout, stderr = await daemon.adb_command("devices")
            self.assertEqual(code, 0)
            self.assertIn("CPH2269", stdout)


if __name__ == "__main__":
    unittest.main()
