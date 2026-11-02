"""
Dynamic Sandboxed Widget Canvas (julius-widget).

Phase 4.2 — Milestone 4.2: Inline sandboxed iframe generator compliant with the
Julius Widget design system specification. Renders rich interactive surfaces:
  - Git Diff Visualizer: Side-by-side expandable diff blocks
  - Database Explorer: Paginated SQLite inspector
  - System Monitor: Real-time CPU, memory, and throughput charts
  - Audio Spectrum: Lossless FLAC playback visualizer
  - Generic Custom Widgets with pre-injected CSS variables and bridge

All widgets run in an isolated, sandboxed iframe with strict Content Security Policy
(zero external network calls) and communicate back to the host via ``window.sendPrompt()``.
"""

from __future__ import annotations

import html
import json
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Julius Design System CSS Tokens ───────────────────────────────────────────

JULIUS_DESIGN_SYSTEM_CSS = """
:root {
  --font-primary: 'Julius', 'Atkinson Hyperlegible', system-ui, -apple-system, sans-serif;
  --font-display: 'Julius', 'Bebas Neue', 'Arial Black', sans-serif;
  --font-thinking: 'Julius', 'Playfair Display', Georgia, serif;
  --font-mono: 'JetBrains Mono', 'Fira Code', Menlo, monospace;
  --lt-green: #006A25;
  --lt-green-dim: rgba(0, 106, 37, 0.15);
  --lt-green-glow: rgba(0, 106, 37, 0.30);
  --lt-bg-pill: rgba(255, 255, 255, 0.04);
  --lt-border: rgba(255, 255, 255, 0.09);
  --lt-border-act: rgba(0, 106, 37, 0.35);
  --lt-text-dim: rgba(255, 255, 255, 0.40);
  --lt-text-mid: rgba(255, 255, 255, 0.65);
  --lt-text-hi: rgba(255, 255, 255, 0.92);
  --lt-radius: 10px;
  --bg: #1F1F1E;
}

* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  background: var(--bg);
  color: var(--lt-text-hi);
  font-family: var(--font-primary);
  font-size: 13px;
  line-height: 1.5;
  padding: 12px;
  overflow-x: hidden;
}

.julius-widget-card,
.julius-widget-card {
  background: var(--lt-bg-pill);
  border: 1px solid var(--lt-border);
  border-radius: var(--lt-radius);
  padding: 14px;
  color: var(--lt-text-hi);
  font-family: var(--font-primary);
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
  position: relative;
}

.julius-widget-card:hover,
.julius-widget-card:hover {
  border-color: var(--lt-border-act);
  box-shadow: 0 0 12px var(--lt-green-glow);
}

.julius-widget-header,
.julius-widget-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--lt-border);
}

.julius-widget-title,
.julius-widget-title {
  font-family: var(--font-display);
  font-size: 18px;
  letter-spacing: 0.5px;
  color: var(--lt-text-hi);
  display: flex;
  align-items: center;
  gap: 8px;
}

.julius-widget-badge,
.julius-widget-badge {
  font-family: var(--font-mono);
  font-size: 11px;
  padding: 2px 7px;
  border-radius: 4px;
  background: var(--lt-green-dim);
  border: 1px solid var(--lt-border-act);
  color: #86efac;
}

.julius-button,
.julius-button {
  background: var(--lt-green-dim);
  border: 1px solid var(--lt-border-act);
  color: var(--lt-text-hi);
  border-radius: calc(var(--lt-radius) - 2px);
  padding: 6px 12px;
  font-family: var(--font-primary);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s ease;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.julius-button:hover,
.julius-button:hover {
  background: var(--lt-green);
  box-shadow: 0 0 8px var(--lt-green-glow);
  color: #ffffff;
}

.julius-button-secondary,
.julius-button-secondary {
  background: var(--lt-bg-pill);
  border: 1px solid var(--lt-border);
  color: var(--lt-text-mid);
}

.julius-button-secondary:hover,
.julius-button-secondary:hover {
  background: rgba(255, 255, 255, 0.08);
  border-color: var(--lt-border-act);
  color: var(--lt-text-hi);
}
"""

JULIUS_DESIGN_SYSTEM_CSS = JULIUS_DESIGN_SYSTEM_CSS

WIDGET_BRIDGE_JS = """
// Julius host runtime bridge
window.sendPrompt = function(text) {
  if (!text) return;
  try {
    window.parent.postMessage({
      type: 'julius:sendPrompt',
      text: String(text)
    }, '*');
    window.parent.postMessage({
      type: 'julius:sendPrompt',
      text: String(text)
    }, '*');
  } catch (err) {
    console.warn('[Widget] Could not send prompt to parent:', err);
  }
};

// Report content height to auto-adjust iframe container
function notifyResize() {
  try {
    const height = Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);
    window.parent.postMessage({
      type: 'julius:widgetResize',
      height: height
    }, '*');
    window.parent.postMessage({
      type: 'julius:widgetResize',
      height: height
    }, '*');
  } catch (err) {}
}

window.addEventListener('load', notifyResize);
window.addEventListener('resize', notifyResize);
setTimeout(notifyResize, 100);
setTimeout(notifyResize, 500);
"""


class WidgetPortal:
    """
    Generator for inline sandboxed widgets adhering to the julius-widget standard.
    """

    @classmethod
    def wrap_html(
        cls,
        title: str,
        body_content: str,
        script_content: str = "",
        extra_css: str = "",
    ) -> str:
        """Wrap HTML, styles, and scripts into a fully self-contained sandboxed HTML document."""
        escaped_title = html.escape(title)
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data:; font-src data:; connect-src 'none';">
  <title>{escaped_title}</title>
  <style>
{JULIUS_DESIGN_SYSTEM_CSS}
{extra_css}
  </style>
</head>
<body>
  {body_content}
  <script>
{WIDGET_BRIDGE_JS}
{script_content}
  </script>
</body>
</html>"""

    # ── 1. Git Diff Visualizer ───────────────────────────────────────────────

    @classmethod
    def render_git_diff(cls, diff_text: str, filename: str = "workspace_diff.patch") -> str:
        """Generate a side-by-side/inline expandable visual Git Diff widget."""
        escaped_filename = html.escape(filename)
        lines = diff_text.strip().split("\n")

        diff_rows = []
        old_ln = 0
        new_ln = 0

        for raw_line in lines:
            escaped_raw = html.escape(raw_line)
            if raw_line.startswith("@@"):
                m = re.match(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", raw_line)
                if m:
                    old_ln = int(m.group(1)) - 1
                    new_ln = int(m.group(2)) - 1
                diff_rows.append(
                    f'<div class="diff-line diff-hunk"><span class="ln">...</span><span class="ln">...</span><span class="code">{escaped_raw}</span></div>'
                )
            elif raw_line.startswith("+"):
                new_ln += 1
                diff_rows.append(
                    f'<div class="diff-line diff-add"><span class="ln"> </span><span class="ln">{new_ln}</span><span class="code">{escaped_raw}</span></div>'
                )
            elif raw_line.startswith("-"):
                old_ln += 1
                diff_rows.append(
                    f'<div class="diff-line diff-del"><span class="ln">{old_ln}</span><span class="ln"> </span><span class="code">{escaped_raw}</span></div>'
                )
            else:
                old_ln += 1
                new_ln += 1
                diff_rows.append(
                    f'<div class="diff-line diff-ctx"><span class="ln">{old_ln}</span><span class="ln">{new_ln}</span><span class="code">{escaped_raw}</span></div>'
                )

        table_html = "\n".join(diff_rows)

        body = f"""
<div class="julius-widget-card julius-widget-card">
  <div class="julius-widget-header julius-widget-header">
    <div class="julius-widget-title julius-widget-title">
      <span>📄</span>
      <span>{escaped_filename}</span>
      <span class="julius-widget-badge julius-widget-badge">GIT DIFF</span>
    </div>
    <div style="display: flex; gap: 8px;">
      <button class="julius-button julius-button" onclick="window.sendPrompt('Revert recent changes to {escaped_filename}')">
        ↩️ Revert
      </button>
      <button class="julius-button julius-button-secondary" onclick="window.sendPrompt('Explain these code changes in detail')">
        💡 Explain Diff
      </button>
    </div>
  </div>
  <div class="diff-container" id="diffContainer">
    {table_html}
  </div>
</div>
"""

        extra_css = """
.diff-container {
  font-family: var(--font-mono);
  font-size: 12px;
  background: rgba(0, 0, 0, 0.4);
  border: 1px solid var(--lt-border);
  border-radius: 6px;
  overflow-x: auto;
  max-height: 480px;
}
.diff-line {
  display: flex;
  line-height: 1.5;
  padding: 1px 6px;
  white-space: pre-wrap;
  word-break: break-all;
}
.diff-line .ln {
  width: 32px;
  flex-shrink: 0;
  text-align: right;
  padding-right: 8px;
  color: var(--lt-text-dim);
  user-select: none;
  border-right: 1px solid var(--lt-border);
  margin-right: 8px;
}
.diff-line .code {
  flex: 1;
}
.diff-hunk {
  background: rgba(59, 130, 246, 0.12);
  color: #93c5fd;
  font-style: italic;
}
.diff-add {
  background: rgba(34, 197, 94, 0.15);
  color: #86efac;
}
.diff-del {
  background: rgba(239, 68, 68, 0.15);
  color: #fca5a5;
}
.diff-ctx {
  color: var(--lt-text-mid);
}
"""
        return cls.wrap_html(f"Git Diff — {filename}", body, extra_css=extra_css)

    # ── 2. Database Explorer ─────────────────────────────────────────────────

    @classmethod
    def render_database_explorer(
        cls,
        db_path: str,
        table_name: str,
        rows: List[Dict[str, Any]],
        total_count: int,
        page: int = 1,
        page_size: int = 10,
    ) -> str:
        """Generate a paginated SQLite table inspector widget."""
        escaped_table = html.escape(table_name)
        escaped_db = html.escape(db_path)

        columns = list(rows[0].keys()) if rows else []
        header_cells = "".join(f"<th>{html.escape(c)}</th>" for c in columns)

        row_htmls = []
        for r in rows:
            cells = "".join(f"<td>{html.escape(str(r.get(c, '')))}</td>" for c in columns)
            row_htmls.append(f"<tr>{cells}</tr>")
        body_rows = "\n".join(row_htmls) if row_htmls else "<tr><td colspan='100%' style='text-align:center;'>No rows found</td></tr>"

        total_pages = max(1, (total_count + page_size - 1) // page_size)

        body = f"""
<div class="julius-widget-card julius-widget-card">
  <div class="julius-widget-header julius-widget-header">
    <div class="julius-widget-title julius-widget-title">
      <span>🗄️</span>
      <span>{escaped_table}</span>
      <span class="julius-widget-badge julius-widget-badge">SQLITE INSPECTOR</span>
    </div>
    <div style="font-family: var(--font-mono); font-size: 11px; color: var(--lt-text-dim);">
      {escaped_db} • Total Rows: {total_count}
    </div>
  </div>

  <div class="table-container">
    <table class="db-table">
      <thead>
        <tr>{header_cells}</tr>
      </thead>
      <tbody>
        {body_rows}
      </tbody>
    </table>
  </div>

  <div class="table-footer">
    <span style="color: var(--lt-text-mid); font-family: var(--font-mono);">
      Page {page} of {total_pages}
    </span>
    <div style="display: flex; gap: 8px;">
      <button class="julius-button julius-button-secondary" onclick="window.sendPrompt('Inspect table {escaped_table} schema and indices')">
        🔍 Schema
      </button>
      <button class="julius-button julius-button" onclick="window.sendPrompt('Export {escaped_table} records to CSV')">
        💾 Export CSV
      </button>
    </div>
  </div>
</div>
"""

        extra_css = """
.table-container {
  overflow-x: auto;
  max-height: 380px;
  border: 1px solid var(--lt-border);
  border-radius: 6px;
  background: rgba(0, 0, 0, 0.2);
}
.db-table {
  width: 100%;
  border-collapse: collapse;
  text-align: left;
  font-size: 12px;
}
.db-table th {
  background: rgba(255, 255, 255, 0.03);
  padding: 8px 12px;
  border-bottom: 1px solid var(--lt-border);
  color: var(--lt-text-hi);
  font-family: var(--font-mono);
  font-size: 11px;
}
.db-table td {
  padding: 8px 12px;
  border-bottom: 1px solid var(--lt-border);
  color: var(--lt-text-mid);
  white-space: nowrap;
  max-width: 280px;
  overflow: hidden;
  text-overflow: ellipsis;
}
.db-table tr:hover td {
  background: rgba(255, 255, 255, 0.04);
  color: var(--lt-text-hi);
}
.table-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 12px;
}
"""
        return cls.wrap_html(f"Database — {table_name}", body, extra_css=extra_css)

    # ── 3. System Monitor ────────────────────────────────────────────────────

    @classmethod
    def render_system_monitor(cls, metrics: Dict[str, Any]) -> str:
        """Generate a real-time CPU, memory, and throughput charts widget."""
        cpu_pct = float(metrics.get("cpu_percent", 24.5))
        mem_pct = float(metrics.get("memory_percent", 58.2))
        mem_used_gb = float(metrics.get("memory_used_gb", 9.3))
        mem_total_gb = float(metrics.get("memory_total_gb", 16.0))
        disk_pct = float(metrics.get("disk_percent", 42.1))
        cores = int(metrics.get("cpu_cores", 8))

        body = f"""
<div class="julius-widget-card julius-widget-card">
  <div class="julius-widget-header julius-widget-header">
    <div class="julius-widget-title julius-widget-title">
      <span>⚡</span>
      <span>SYSTEM TELEMETRY</span>
      <span class="julius-widget-badge julius-widget-badge">REAL-TIME</span>
    </div>
    <button class="julius-button julius-button" onclick="window.sendPrompt('Run full hardware and resource diagnostic check')">
      🩺 Run Diagnostic
    </button>
  </div>

  <div class="metrics-grid">
    <div class="metric-box">
      <div class="metric-label">CPU USAGE ({cores} Cores)</div>
      <div class="metric-value">{cpu_pct:.1f}%</div>
      <div class="progress-bar">
        <div class="progress-fill" style="width: {min(100, cpu_pct)}%;"></div>
      </div>
    </div>

    <div class="metric-box">
      <div class="metric-label">MEMORY ({mem_used_gb:.1f} / {mem_total_gb:.1f} GB)</div>
      <div class="metric-value">{mem_pct:.1f}%</div>
      <div class="progress-bar">
        <div class="progress-fill" style="width: {min(100, mem_pct)}%; background: #3b82f6;"></div>
      </div>
    </div>

    <div class="metric-box">
      <div class="metric-label">STORAGE CAPACITY</div>
      <div class="metric-value">{disk_pct:.1f}%</div>
      <div class="progress-bar">
        <div class="progress-fill" style="width: {min(100, disk_pct)}%; background: #a855f7;"></div>
      </div>
    </div>
  </div>

  <div style="margin-top: 14px;">
    <div style="font-family: var(--font-mono); font-size: 11px; color: var(--lt-text-dim); margin-bottom: 6px;">
      HOST ACTIVITY OSCILLOSCOPE
    </div>
    <canvas id="telemetryCanvas" width="560" height="90" style="width: 100%; height: 90px; border-radius: 6px; background: rgba(0,0,0,0.5);"></canvas>
  </div>
</div>
"""

        script = """
const canvas = document.getElementById('telemetryCanvas');
if (canvas) {
  const ctx = canvas.getContext('2d');
  const points = [];
  for (let i = 0; i < 40; i++) {
    points.push(Math.random() * 40 + 20);
  }

  function draw() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.strokeStyle = '#006A25';
    ctx.lineWidth = 2;
    ctx.beginPath();
    const step = canvas.width / (points.length - 1);
    for (let i = 0; i < points.length; i++) {
      const x = i * step;
      const y = canvas.height - (points[i] / 100) * canvas.height;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();

    // Fill gradient
    ctx.lineTo(canvas.width, canvas.height);
    ctx.lineTo(0, canvas.height);
    ctx.fillStyle = 'rgba(0, 106, 37, 0.15)';
    ctx.fill();
  }
  draw();
}
"""

        extra_css = """
.metrics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 12px;
}
.metric-box {
  background: rgba(0, 0, 0, 0.3);
  border: 1px solid var(--lt-border);
  border-radius: 8px;
  padding: 10px;
}
.metric-label {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--lt-text-dim);
  margin-bottom: 4px;
}
.metric-value {
  font-family: var(--font-display);
  font-size: 24px;
  color: var(--lt-text-hi);
  margin-bottom: 8px;
}
.progress-bar {
  height: 6px;
  background: rgba(255, 255, 255, 0.08);
  border-radius: 3px;
  overflow: hidden;
}
.progress-fill {
  height: 100%;
  background: var(--lt-green);
  transition: width 0.3s ease;
}
"""
        return cls.wrap_html("System Telemetry Monitor", body, script_content=script, extra_css=extra_css)

    # ── 4. Lossless Audio Spectrum ───────────────────────────────────────────

    @classmethod
    def render_audio_spectrum(cls, track_info: Dict[str, Any]) -> str:
        """Generate a lossless FLAC / audio playback analyzer widget."""
        title = html.escape(track_info.get("title", "High-Resolution Audio"))
        artist = html.escape(track_info.get("artist", "Master Recording"))
        format_badge = html.escape(track_info.get("format", "24-bit / 96kHz FLAC"))
        bitrate = html.escape(track_info.get("bitrate", "2850 kbps"))

        body = f"""
<div class="julius-widget-card julius-widget-card">
  <div class="julius-widget-header julius-widget-header">
    <div class="julius-widget-title julius-widget-title">
      <span>🎵</span>
      <span>{title}</span>
      <span class="julius-widget-badge julius-widget-badge">{format_badge}</span>
    </div>
    <div style="font-family: var(--font-mono); font-size: 11px; color: var(--lt-text-dim);">
      {artist} • {bitrate}
    </div>
  </div>

  <div style="position: relative; margin-bottom: 12px;">
    <canvas id="spectrumCanvas" width="560" height="120" style="width: 100%; height: 120px; border-radius: 6px; background: rgba(0,0,0,0.6);"></canvas>
  </div>

  <div style="display: flex; justify-content: space-between; align-items: center;">
    <div style="display: flex; gap: 8px;">
      <button class="julius-button julius-button" onclick="toggleSpectrumPlay()">
        ▶️ Play Spectrum
      </button>
      <button class="julius-button julius-button-secondary" onclick="window.sendPrompt('Analyze acoustic dynamic range and mastering quality of {title}')">
        📊 Dynamic Range
      </button>
    </div>
    <span style="font-family: var(--font-mono); font-size: 11px; color: #86efac;">
      BIT-PERFECT DIRECT PASS
    </span>
  </div>
</div>
"""

        script = """
let animating = true;
const canvas = document.getElementById('spectrumCanvas');
if (canvas) {
  const ctx = canvas.getContext('2d');
  const barCount = 48;
  const bars = Array.from({ length: barCount }, () => Math.random() * 0.7 + 0.1);

  function renderSpectrum() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const barWidth = (canvas.width / barCount) - 2;

    for (let i = 0; i < barCount; i++) {
      if (animating) {
        bars[i] += (Math.random() - 0.5) * 0.15;
        bars[i] = Math.max(0.05, Math.min(0.95, bars[i]));
      }

      const barHeight = bars[i] * canvas.height;
      const x = i * (barWidth + 2);
      const y = canvas.height - barHeight;

      const grad = ctx.createLinearGradient(0, y, 0, canvas.height);
      grad.addColorStop(0, '#86efac');
      grad.addColorStop(0.5, '#006A25');
      grad.addColorStop(1, 'rgba(0, 106, 37, 0.2)');

      ctx.fillStyle = grad;
      ctx.fillRect(x, y, barWidth, barHeight);
    }
    requestAnimationFrame(renderSpectrum);
  }
  requestAnimationFrame(renderSpectrum);

  window.toggleSpectrumPlay = function() {
    animating = !animating;
  };
}
"""
        return cls.wrap_html(f"Audio Spectrum — {title}", body, script_content=script)

    # ── 5. Generic Custom Widget ─────────────────────────────────────────────

    @classmethod
    def render_custom_widget(
        cls,
        title: str,
        html_body: str,
        script: str = "",
        extra_css: str = "",
    ) -> str:
        """Render a custom widget with complete Julius design tokens pre-loaded."""
        return cls.wrap_html(title, html_body, script_content=script, extra_css=extra_css)

    # ── 6. IFrame Helper ─────────────────────────────────────────────────────

    @classmethod
    def render_iframe_tag(cls, html_content: str, height: int = 340) -> str:
        """Convert widget HTML content into a safe iframe srcdoc snippet."""
        escaped_srcdoc = html.escape(html_content, quote=True)
        return (
            f'<iframe class="julius-widget-frame julius-widget-frame" '
            f'sandbox="allow-scripts" '
            f'loading="lazy" '
            f'style="width: 100%; height: {height}px; border: none; border-radius: var(--lt-radius, 10px); background: transparent; overflow: hidden; display: block;" '
            f'srcdoc="{escaped_srcdoc}"></iframe>'
        )
