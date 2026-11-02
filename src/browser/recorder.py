"""
Playwright tracing, video, and HAR recording for debugging.

Provides:
  - Trace recording (openable with `playwright show-trace`)
  - HAR (HTTP Archive) recording for full network replay
  - Video recording per browser context

All recordings are saved inside the workspace so they can be served
and downloaded through julius_gui.py's static file handler.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from playwright.async_api import BrowserContext, Page

logger = logging.getLogger(__name__)


class TraceRecorder:
    """
    Manages Playwright trace recording for a single browser context.

    Usage
    -----
    recorder = TraceRecorder(context, workspace_root)
    await recorder.start(screenshots=True, snapshots=True)
    # … browser actions …
    path = await recorder.stop("debug/trace.zip")
    """

    def __init__(self, context: "BrowserContext", workspace_root: str) -> None:
        self.context = context
        self.workspace_root = Path(workspace_root)
        self._recording = False

    async def start(
        self,
        screenshots: bool = True,
        snapshots: bool = True,
        sources: bool = False,
    ) -> None:
        """Start a Playwright trace session on the context."""
        if self._recording:
            logger.warning("TraceRecorder: already recording, ignoring start()")
            return
        await self.context.tracing.start(
            screenshots=screenshots,
            snapshots=snapshots,
            sources=sources,
        )
        self._recording = True
        logger.info("TraceRecorder: trace started")

    async def stop(self, relative_path: str = "debug/trace.zip") -> str:
        """
        Stop recording and save the trace zip.

        Returns the workspace-relative path to the saved file.
        """
        if not self._recording:
            raise RuntimeError("TraceRecorder: not currently recording")
        out_path = self.workspace_root / relative_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        await self.context.tracing.stop(path=str(out_path))
        self._recording = False
        logger.info(f"TraceRecorder: trace saved to {relative_path}")
        return relative_path

    @property
    def is_recording(self) -> bool:
        return self._recording


class HARRecorder:
    """
    Manages HAR (HTTP Archive) recording for a single browser page.

    Usage
    -----
    recorder = HARRecorder(page, workspace_root)
    await recorder.start("debug/session.har")
    # … browser actions …
    path = await recorder.stop()
    """

    def __init__(self, page: "Page", workspace_root: str) -> None:
        self.page = page
        self.workspace_root = Path(workspace_root)
        self._har_path: str | None = None
        self._recording = False

    async def start(self, relative_path: str = "debug/session.har") -> None:
        """Begin recording all network to HAR at the given workspace-relative path."""
        if self._recording:
            logger.warning("HARRecorder: already recording")
            return
        out_path = self.workspace_root / relative_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        await self.page.route_from_har(str(out_path), not_found="continue")
        self._har_path = relative_path
        self._recording = True
        logger.info(f"HARRecorder: HAR recording started → {relative_path}")

    async def stop(self) -> str | None:
        """Finalise and flush the HAR file. Returns the workspace-relative path."""
        if not self._recording:
            return None
        # Playwright HAR is flushed when the page closes or explicitly via unroute
        await self.page.unroute_all()
        self._recording = False
        logger.info(f"HARRecorder: HAR recording stopped → {self._har_path}")
        return self._har_path

    @property
    def is_recording(self) -> bool:
        return self._recording


def build_video_context_options(
    workspace_root: str,
    video_dir: str = "debug/videos",
    video_size: dict[str, int] | None = None,
) -> dict[str, Any]:
    """
    Return ``browser.new_context(**opts)`` additions to enable video recording.

    Video files are saved automatically when the context is closed.
    Each page within the context gets its own .webm file.

    Example
    -------
    opts = build_video_context_options(workspace_root)
    context = await browser.new_context(**opts)
    """
    out_dir = Path(workspace_root) / video_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    size = video_size or {"width": 1280, "height": 900}
    return {
        "record_video_dir": str(out_dir),
        "record_video_size": size,
    }
