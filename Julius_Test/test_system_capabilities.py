"""
Comprehensive Verification Suite for Julius Extended System Capabilities.

Tests all 6 core pillars of the extended capabilities:
1. Native Desktop Screen & Window Perception (DesktopCaptureEngine)
2. High-Level OS System Controller (SystemController vitals, clipboard, notifications, apps)
3. Multi-Agent Swarm Teamwork (TeamworkDispatcher DAG execution)
4. Autonomous Proactive Daemon (ProactiveDaemon heartbeat & alerts)
5. Ambient Voice Listener & Auditory Earcons (AmbientVoiceListener & play_earcon)
6. ActionExecutor & Canonical Tools Integration (Tools registry, ToolSearch, ActionExecutor)
"""

from __future__ import annotations

import asyncio
import os
import sys
import unittest
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.perception.desktop_capture import (
    DesktopCaptureEngine,
    WindowInfo,
    ScreenCaptureResult,
    get_desktop_engine,
)
from src.services.system_controller import (
    SystemController,
    SystemVitals,
    get_system_controller,
)
from src.coordinator.agent_teamwork import (
    TeamworkDispatcher,
    TeamworkReport,
    get_teamwork_dispatcher,
)
from src.services.proactive_daemon import (
    ProactiveDaemon,
    ProactiveAlert,
    AlertSeverity,
    get_proactive_daemon,
)
from src.voice.ambient_listener import (
    AmbientVoiceListener,
    EarconCue,
    WakeWordState,
    play_earcon,
    get_ambient_listener,
)
from src.tools import (
    CORE_TOOL_SCHEMAS,
    DEFERRED_TOOL_SCHEMAS,
    resolve_tool_search,
    execute_tool,
    PORTED_TOOLS,
)
from src.action_executor import ActionExecutor, ActionResult


class TestDesktopPerception(unittest.TestCase):
    """Test Pillar 1: Native Desktop Screen & Window Perception."""

    def setUp(self):
        self.engine = get_desktop_engine()

    def test_active_window_detection(self):
        """Active window inspection returns structured WindowInfo."""
        win = self.engine.get_active_window()
        self.assertIsInstance(win, WindowInfo)
        self.assertIsNotNone(win.app_name)
        self.assertIsNotNone(win.window_title)
        self.assertTrue(len(win.app_name) > 0)
        print(f"\n[Test] Detected Active Window: '{win.app_name}' — '{win.window_title}'")

    def test_screen_capture_structure(self):
        """Screen capture returns ScreenCaptureResult with dimensions and active window."""
        res = self.engine.capture_screen(save_to_disk=False)
        self.assertIsInstance(res, ScreenCaptureResult)
        self.assertIsNotNone(res.active_window)
        # On headless CI or systems without display access, check error or valid bytes
        if res.success:
            self.assertTrue(len(res.image_bytes) > 0 or res.file_path is not None)
            print(f"[Test] Screen capture succeeded: {res.width}x{res.height}")
        else:
            self.assertIsNotNone(res.error)
            print(f"[Test] Screen capture skipped/error (expected on headless env): {res.error}")


class TestSystemController(unittest.TestCase):
    """Test Pillar 2: High-Level OS System Controller."""

    def setUp(self):
        self.controller = get_system_controller()

    def test_system_vitals_collection(self):
        """System vitals collects CPU, RAM, disk, and OS info."""
        v = self.controller.get_system_vitals()
        self.assertIsInstance(v, SystemVitals)
        self.assertGreaterEqual(v.cpu_count, 1)
        self.assertGreaterEqual(v.disk_total_gb, 0.0)
        self.assertTrue(len(v.hostname) > 0)
        self.assertTrue(len(v.os_name) > 0)

        # Dictionary export
        v_dict = v.to_dict()
        self.assertIn("cpu_count", v_dict)
        self.assertIn("memory", v_dict)
        self.assertIn("disk", v_dict)
        self.assertIn("os", v_dict)

        summary = v.format_summary()
        self.assertIn("CPU:", summary)
        self.assertIn("Disk:", summary)
        print(f"\n[Test] System Vitals Summary: {summary}")

    def test_clipboard_operations(self):
        """Clipboard write and read roundtrip."""
        test_text = f"Julius_System_Test_{os.getpid()}"
        write_ok = self.controller.write_clipboard(test_text)
        if write_ok:
            read_back = self.controller.read_clipboard()
            self.assertIn(test_text, read_back)
            print(f"[Test] Clipboard read/write verified: '{test_text}'")
        else:
            print("[Test] Clipboard write skipped (headless/unsupported display)")

    def test_list_running_apps(self):
        """List running applications returns a list of dictionaries with app names."""
        apps = self.controller.list_running_apps()
        self.assertIsInstance(apps, list)
        if apps:
            self.assertIn("name", apps[0])
            print(f"[Test] Discovered {len(apps)} running applications (e.g. {apps[0]['name']})")


class TestTeamworkDispatcher(unittest.TestCase):
    """Test Pillar 3: Multi-Agent Swarm Teamwork."""

    def test_mission_execution(self):
        """TeamworkDispatcher coordinates Architect -> Developer -> Verifier squad."""
        dispatcher = TeamworkDispatcher()
        goal = "Implement high-speed telemetry caching module"

        report = dispatcher.execute_mission(
            goal=goal,
            personas=["architect", "developer", "security_auditor", "verifier"],
        )

        self.assertIsInstance(report, TeamworkReport)
        self.assertTrue(report.success)
        self.assertEqual(len(report.members), 4)

        personas_executed = [m.persona for m in report.members]
        self.assertIn("architect", personas_executed)
        self.assertIn("developer", personas_executed)
        self.assertIn("security_auditor", personas_executed)
        self.assertIn("verifier", personas_executed)

        md = report.format_markdown()
        self.assertIn("Teamwork Swarm Mission", md)
        self.assertIn("ARCHITECT", md)
        self.assertIn("DEVELOPER", md)
        print(f"\n[Test] Teamwork Mission Output Preview:\n{md[:250]}...\n")


class TestProactiveDaemon(unittest.TestCase):
    """Test Pillar 4: Autonomous Proactive Daemon."""

    def test_proactive_vitals_check(self):
        """Daemon evaluates system vitals and generates alerts when thresholds exceeded."""
        daemon = ProactiveDaemon(workspace_root=str(PROJECT_ROOT), heartbeat_interval=1.0)
        alerts = daemon.check_system_vitals()
        self.assertIsInstance(alerts, list)
        for a in alerts:
            self.assertIsInstance(a, ProactiveAlert)
            self.assertIn(a.severity, (AlertSeverity.INFO, AlertSeverity.WARNING, AlertSeverity.CRITICAL))
            self.assertTrue(len(a.title) > 0)
            print(f"[Test] Generated Proactive Alert: {a.format_line()}")

    def test_git_status_check(self):
        """Daemon evaluates git status without throwing errors."""
        daemon = ProactiveDaemon(workspace_root=str(PROJECT_ROOT), heartbeat_interval=1.0)
        alerts = daemon.check_git_status()
        self.assertIsInstance(alerts, list)


class TestAmbientVoiceListener(unittest.TestCase):
    """Test Pillar 5: Ambient Voice Listener & Auditory Earcons."""

    def setUp(self):
        self.listener = get_ambient_listener()

    def test_wake_word_detection(self):
        """Detects wake words in user speech transcripts."""
        self.assertTrue(self.listener.is_wake_word_detected("Hey Julius, what is the server load?"))
        self.assertTrue(self.listener.is_wake_word_detected("Julius run tests please"))
        self.assertFalse(self.listener.is_wake_word_detected("Can you check the weather?"))

    def test_command_extraction(self):
        """Strips wake word prefix cleanly."""
        cmd1 = self.listener.extract_command("Hey Julius, what is the CPU load?")
        self.assertEqual(cmd1, "what is the CPU load?")

        cmd2 = self.listener.extract_command("Julius: build project")
        self.assertEqual(cmd2, "build project")

    def test_earcon_cues(self):
        """play_earcon executes cleanly for each cue."""
        for cue in [EarconCue.WAKE, EarconCue.THINKING, EarconCue.SUCCESS, EarconCue.ALERT]:
            # Should not crash on any platform
            res = play_earcon(cue)
            self.assertIsInstance(res, bool)


class TestActionExecutorAndToolsIntegration(unittest.TestCase):
    """Test Pillar 6: ActionExecutor & Canonical Tools Integration."""

    def setUp(self):
        self.executor = ActionExecutor(workspace_root=str(PROJECT_ROOT))

    def test_tool_schemas_registered(self):
        """Verify all new system tools are registered in DEFERRED_TOOL_SCHEMAS."""
        system_tools = [
            "CaptureScreen",
            "GetActiveWindow",
            "GetSystemVitals",
            "SendSystemNotification",
            "ManageClipboard",
            "AppControl",
            "RunTeamwork",
        ]
        for t in system_tools:
            self.assertIn(t, DEFERRED_TOOL_SCHEMAS, f"Missing tool schema: {t}")
            schema = DEFERRED_TOOL_SCHEMAS[t]
            self.assertEqual(schema["name"], t)
            self.assertIn("description", schema)
            self.assertIn("parameters", schema)

    def test_tool_search_resolution(self):
        """ToolSearch resolves deferred system tools via select: syntax."""
        result = resolve_tool_search("select:CaptureScreen,GetSystemVitals,RunTeamwork")
        self.assertIn("<functions>", result)
        self.assertIn("CaptureScreen", result)
        self.assertIn("GetSystemVitals", result)
        self.assertIn("RunTeamwork", result)
        self.assertIn("</functions>", result)

    def test_executor_get_system_vitals(self):
        """ActionExecutor executes 'get_system_vitals'."""
        res = self.executor.execute("get_system_vitals", {})
        self.assertIsInstance(res, ActionResult)
        self.assertTrue(res.success)
        self.assertIn("System Vitals", res.output)
        self.assertIsNotNone(res.data)

    def test_executor_get_active_window(self):
        """ActionExecutor executes 'get_active_window'."""
        res = self.executor.execute("get_active_window", {})
        self.assertIsInstance(res, ActionResult)
        self.assertTrue(res.success)
        self.assertIn("Frontmost Application", res.output)

    def test_executor_run_teamwork(self):
        """ActionExecutor executes 'run_teamwork'."""
        res = self.executor.execute("run_teamwork", {
            "goal": "Verify database connection pooling security",
            "personas": ["architect", "security_auditor"],
        })
        self.assertIsInstance(res, ActionResult)
        self.assertTrue(res.success)
        self.assertIn("Teamwork Swarm Mission", res.output)
        self.assertIn("ARCHITECT", res.output)

    def test_executor_manage_clipboard_read(self):
        """ActionExecutor executes 'manage_clipboard' read action."""
        res = self.executor.execute("manage_clipboard", {"action": "read"})
        self.assertIsInstance(res, ActionResult)
        self.assertTrue(res.success)


if __name__ == "__main__":
    unittest.main(verbosity=2)
