"""Tests for Phase 4.2: Dynamic Sandboxed Widget Canvas (julius-widget)."""

from __future__ import annotations

import unittest
from src.components.widget_portal import WidgetPortal, JULIUS_DESIGN_SYSTEM_CSS


class TestWidgetCanvas(unittest.TestCase):
    """Test suite verifying WidgetPortal adherence to julius-widget specs and sandboxing."""

    def test_css_tokens_and_variables(self):
        """Julius design system tokens are present in base CSS."""
        self.assertIn("--lt-green: #006A25", JULIUS_DESIGN_SYSTEM_CSS)
        self.assertIn("--lt-bg-pill:", JULIUS_DESIGN_SYSTEM_CSS)
        self.assertIn("--lt-border-act:", JULIUS_DESIGN_SYSTEM_CSS)
        self.assertIn("--lt-radius: 10px", JULIUS_DESIGN_SYSTEM_CSS)
        self.assertIn("--font-primary:", JULIUS_DESIGN_SYSTEM_CSS)

    def test_wrap_html_sandbox_csp(self):
        """wrap_html creates document with strict sandboxed CSP and postMessage bridge."""
        html_doc = WidgetPortal.wrap_html(title="Test Widget", body_content="<p>Hello Widget</p>")
        self.assertIn("<meta http-equiv=\"Content-Security-Policy\"", html_doc)
        self.assertIn("default-src 'none'", html_doc)
        self.assertIn("window.sendPrompt", html_doc)
        self.assertIn("window.parent.postMessage", html_doc)
        self.assertIn("<p>Hello Widget</p>", html_doc)

    def test_render_iframe_tag(self):
        """render_iframe_tag produces sandboxed iframe without network access."""
        iframe = WidgetPortal.render_iframe_tag("<h1>Sample</h1>", height=280)
        self.assertIn("<iframe", iframe)
        self.assertIn("sandbox=\"allow-scripts\"", iframe)
        self.assertIn("height: 280px", iframe)
        self.assertIn("srcdoc=\"", iframe)

    def test_render_git_diff(self):
        """render_git_diff produces structured diff widget with additions and deletions."""
        diff_sample = """--- a/src/main.py
+++ b/src/main.py
@@ -1,3 +1,3 @@
-def old(): pass
+def new(): pass
"""
        html_out = WidgetPortal.render_git_diff(diff_sample, filename="src/main.py")
        self.assertIn("src/main.py", html_out)
        self.assertIn("diff-del", html_out)
        self.assertIn("diff-add", html_out)
        self.assertIn("Revert recent changes", html_out)

    def test_render_system_monitor(self):
        """render_system_monitor generates CPU, RAM, and disk utilization gauges."""
        metrics = {
            "cpu_percent": 34.5,
            "memory_percent": 68.2,
            "memory_used_gb": 10.9,
            "memory_total_gb": 16.0,
            "disk_percent": 45.0,
            "cpu_cores": 8,
        }
        html_out = WidgetPortal.render_system_monitor(metrics)
        self.assertIn("SYSTEM TELEMETRY", html_out)
        self.assertIn("34.5%", html_out)
        self.assertIn("68.2%", html_out)
        self.assertIn("45.0%", html_out)

    def test_render_audio_spectrum(self):
        """render_audio_spectrum produces FLAC player visualizer with frequency bars."""
        track_info = {
            "title": "Midnight Drive",
            "artist": "Julius Synth",
            "format": "24-bit / 96kHz FLAC",
            "bitrate": "2850 kbps",
        }
        html_out = WidgetPortal.render_audio_spectrum(track_info)
        self.assertIn("Midnight Drive", html_out)
        self.assertIn("Julius Synth", html_out)
        self.assertIn("24-bit / 96kHz FLAC", html_out)
        self.assertIn("spectrumCanvas", html_out)

    def test_render_custom_widget(self):
        """render_custom_widget wraps arbitrary HTML with full Julius tokens and scripts."""
        html_out = WidgetPortal.render_custom_widget(
            title="Custom Action",
            html_body="<button class='julius-button' onclick=\"sendPrompt('Deploy now')\">Deploy</button>",
            script="console.log('ready');",
        )
        self.assertIn("Custom Action", html_out)
        self.assertIn("Deploy now", html_out)
        self.assertIn("console.log('ready');", html_out)


if __name__ == "__main__":
    unittest.main()
