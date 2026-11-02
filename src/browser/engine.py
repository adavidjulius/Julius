"""
PlaywrightEngine — persistent async browser lifecycle manager.

Manages:
  - A single long-lived Playwright instance across the agent session
  - Named browser contexts (each with isolated cookies/storage)
  - Per-context page registry
  - Console log and network request listeners
  - Retry policy wrapper for resilient action execution
  - Tracing / video recorder attachment per context

Design decision: this class is async and lives in WebAgent (alongside
MCPManager), NOT inside ActionExecutor (which runs in a thread). Browser
actions bypass ActionExecutor and are dispatched directly in web_agent.py.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)

try:
    from playwright.async_api import (
        async_playwright,
        Browser,
        BrowserContext,
        Page,
        PlaywrightContextManager,
        TimeoutError as PlaywrightTimeoutError,
    )
    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    _PLAYWRIGHT_AVAILABLE = False
    logger.warning("playwright not installed — browser actions unavailable. Run: pip install playwright && playwright install chromium")

from .structured_obs import BrowserObservation, InteractiveElement, NetworkEntry, BotDetection
from .anti_bot import AntiBotMode, pick_stealth_context_options, detect_bot_block
import aiohttp
import base64
import json

class KeyboardMock:
    def __init__(self, page: ExternalPage) -> None:
        self.page = page

    async def press(self, key: str, **kwargs: Any) -> None:
        await self.page._rpc("browser.pressKey", {"key": key, "modifiers": []})


class MouseMock:
    def __init__(self, page: ExternalPage) -> None:
        self.page = page

    async def wheel(self, delta_x: float, delta_y: float, **kwargs: Any) -> None:
        await self.page._rpc("browser.scroll", {"deltaX": delta_x, "deltaY": delta_y})


class ElementHandleMock:
    def __init__(self, page: ExternalPage, selector: str) -> None:
        self.page = page
        self.selector = selector

    async def inner_text(self) -> str:
        expr = f"""(() => {{
            const el = document.querySelector('{self.selector}');
            return el ? el.innerText : '';
        }})()"""
        return await self.page.evaluate(expr)


class DownloadMock:
    async def save_as(self, path: str) -> None:
        pass


class DownloadInfoMock:
    async def __aenter__(self) -> DownloadInfoMock:
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        pass

    @property
    async def value(self) -> DownloadMock:
        return DownloadMock()


class LocatorMock:
    def __init__(self, page: ExternalPage, text: str | None = None, selector: str | None = None) -> None:
        self.page = page
        self.text = text
        self.selector = selector

    @property
    def first(self) -> LocatorMock:
        return self

    async def click(self, timeout: float | None = None, **kwargs: Any) -> None:
        if self.text:
            await self.page.click_by_text(self.text)
        elif self.selector:
            await self.page.click(self.selector)


class ExternalPage:
    def __init__(self, engine: PlaywrightEngine, native_page: Page | None = None, tab_id: str = "tab-1") -> None:
        self.engine = engine
        self._tab_id = tab_id
        self._last_native_page = native_page

    async def get_native_page(self) -> Page:
        pages = self.engine._browser.contexts[0].pages
        guest_pages = [p for p in pages if not p.url.startswith("file://")]
        if not guest_pages:
            await asyncio.sleep(0.2)
            pages = self.engine._browser.contexts[0].pages
            guest_pages = [p for p in pages if not p.url.startswith("file://")]
        
        resolved = None
        if guest_pages:
            if len(guest_pages) == 1:
                resolved = guest_pages[0]
            else:
                try:
                    tabs = await self.engine._rpc_direct("browser.listTabs")
                    this_tab = next((t for t in tabs if t.get("tabId") == self._tab_id), None) if tabs else None
                    if this_tab:
                        url = this_tab.get("url")
                        for p in guest_pages:
                            if p.url == url:
                                resolved = p
                                break
                except Exception:
                    pass
                if not resolved:
                    resolved = guest_pages[-1]
        else:
            resolved = pages[0]
            
        self._last_native_page = resolved
        return resolved

    @property
    def url(self) -> str:
        if self._last_native_page:
            try:
                return self._last_native_page.url
            except Exception:
                pass
        return "about:blank"

    async def title(self) -> str:
        page = await self.get_native_page()
        return await page.title()

    @property
    def keyboard(self) -> Any:
        if not self._last_native_page:
            pages = self.engine._browser.contexts[0].pages
            guest_pages = [p for p in pages if not p.url.startswith("file://")]
            self._last_native_page = guest_pages[-1] if guest_pages else pages[0]
        return self._last_native_page.keyboard

    @property
    def mouse(self) -> Any:
        if not self._last_native_page:
            pages = self.engine._browser.contexts[0].pages
            guest_pages = [p for p in pages if not p.url.startswith("file://")]
            self._last_native_page = guest_pages[-1] if guest_pages else pages[0]
        return self._last_native_page.mouse

    async def _rpc(self, method: str, params: dict | None = None) -> Any:
        if params is None:
            params = {}
        if "tabId" not in params and self._tab_id:
            params["tabId"] = self._tab_id
        return await self.engine._rpc_direct(method, params)

    async def goto(self, url: str, wait_until: str | None = None, timeout: float | None = None, **kwargs: Any) -> None:
        page = await self.get_native_page()
        await page.goto(url, wait_until=wait_until, timeout=timeout, **kwargs)

    async def click(self, selector: str, timeout: float | None = None, **kwargs: Any) -> None:
        page = await self.get_native_page()
        await page.click(selector, timeout=timeout, **kwargs)

    async def fill(self, selector: str, text: str, timeout: float | None = None, **kwargs: Any) -> None:
        page = await self.get_native_page()
        await page.fill(selector, text, timeout=timeout, **kwargs)

    async def select_option(self, selector: str, value: str, timeout: float | None = None, **kwargs: Any) -> Any:
        page = await self.get_native_page()
        return await page.select_option(selector, value=value, timeout=timeout, **kwargs)

    async def hover(self, selector: str, timeout: float | None = None, **kwargs: Any) -> None:
        page = await self.get_native_page()
        await page.hover(selector, timeout=timeout, **kwargs)

    async def query_selector(self, selector: str) -> Any:
        page = await self.get_native_page()
        return await page.query_selector(selector)

    async def set_input_files(self, selector: str, abs_path: str, timeout: float | None = None) -> None:
        page = await self.get_native_page()
        await page.set_input_files(selector, abs_path, timeout=timeout)

    def expect_download(self, timeout: float | None = None) -> Any:
        if not self._last_native_page:
            pages = self.engine._browser.contexts[0].pages
            guest_pages = [p for p in pages if not p.url.startswith("file://")]
            self._last_native_page = guest_pages[-1] if guest_pages else pages[0]
        return self._last_native_page.expect_download(timeout=timeout)

    async def screenshot(self, path: str | None = None, **kwargs: Any) -> bytes:
        page = await self.get_native_page()
        return await page.screenshot(path=path, **kwargs)

    async def evaluate(self, expression: str, **kwargs: Any) -> Any:
        page = await self.get_native_page()
        return await page.evaluate(expression, **kwargs)

    async def wait_for_load_state(self, state: str | None = None, timeout: float | None = None) -> None:
        page = await self.get_native_page()
        await page.wait_for_load_state(state=state, timeout=timeout)

    async def wait_for_selector(self, selector: str, state: str | None = None, timeout: float | None = None) -> None:
        page = await self.get_native_page()
        await page.wait_for_selector(selector, state=state, timeout=timeout)

    async def click_by_text(self, text: str) -> None:
        page = await self.get_native_page()
        await page.get_by_text(text).first.click()

    def get_by_text(self, text: str, **kwargs: Any) -> Any:
        if not self._last_native_page:
            pages = self.engine._browser.contexts[0].pages
            guest_pages = [p for p in pages if not p.url.startswith("file://")]
            self._last_native_page = guest_pages[-1] if guest_pages else pages[0]
        return self._last_native_page.get_by_text(text, **kwargs)

    def __getattr__(self, name: str) -> Any:
        if not self._last_native_page:
            pages = self.engine._browser.contexts[0].pages
            guest_pages = [p for p in pages if not p.url.startswith("file://")]
            self._last_native_page = guest_pages[-1] if guest_pages else pages[0]
        return getattr(self._last_native_page, name)



# ── Retry policy ──────────────────────────────────────────────────────────────

class ActionRetryPolicy:
    """
    Wraps a browser coroutine with exponential-backoff retry.

    Retries on:
      - PlaywrightTimeoutError
      - ConnectionError / network hiccups

    Fails fast on:
      - ValueError (bad selector syntax)
      - Any error where the DOM snapshot shows the element truly absent
    """

    def __init__(self, max_attempts: int = 3, base_delay_ms: int = 500) -> None:
        self.max_attempts = max_attempts
        self.base_delay_ms = base_delay_ms

    async def execute(
        self,
        coro_factory: Callable[[], Awaitable[BrowserObservation]],
        action_name: str,
    ) -> BrowserObservation:
        last_obs: BrowserObservation | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                obs = await coro_factory()
                return obs
            except PlaywrightTimeoutError as exc:
                delay = (self.base_delay_ms * (2 ** (attempt - 1))) / 1000.0
                logger.warning(
                    f"[{action_name}] Timeout on attempt {attempt}/{self.max_attempts}; "
                    f"retrying in {delay:.1f}s: {exc}"
                )
                last_obs = BrowserObservation(
                    action=action_name,
                    error=f"Timeout (attempt {attempt}/{self.max_attempts}): {exc}",
                )
                if attempt < self.max_attempts:
                    await asyncio.sleep(delay)
            except ValueError as exc:
                # Bad selector etc. — don't retry
                return BrowserObservation(action=action_name, error=str(exc))
            except Exception as exc:
                delay = (self.base_delay_ms * (2 ** (attempt - 1))) / 1000.0
                logger.warning(
                    f"[{action_name}] Error on attempt {attempt}/{self.max_attempts}: {exc}"
                )
                last_obs = BrowserObservation(action=action_name, error=str(exc))
                if attempt < self.max_attempts:
                    await asyncio.sleep(delay)

        return last_obs or BrowserObservation(action=action_name, error="All retry attempts exhausted.")


# ── Context record ────────────────────────────────────────────────────────────

class BrowserContextRecord:
    """Holds a named context and its associated state."""

    def __init__(
        self,
        context_id: str,
        context: "BrowserContext",
        workspace_root: str,
        anti_bot_mode: AntiBotMode = AntiBotMode.OFF,
    ) -> None:
        self.context_id = context_id
        self.context = context
        self.workspace_root = Path(workspace_root)
        self.anti_bot_mode = anti_bot_mode
        self.pages: list["Page"] = []
        self.active_page_index: int = 0

        # Per-context log buffers (cleared on each navigation)
        self._console_logs: list[str] = []
        self._network_log: list[NetworkEntry] = []
        self._request_times: dict[str, float] = {}   # url → start_time

        # Passive callbacks for request/response interception/observation
        self._request_callbacks: list[Callable[[Any], Any]] = []
        self._response_callbacks: list[Callable[[Any], Any]] = []

        # Trace / HAR recorders (lazy-initialised)
        self.trace_recorder: Any = None
        self.har_recorder: Any = None

        # Cognitive Layer additions
        from .memory import BrowserMemory
        self.memory = BrowserMemory()
        self.last_obs: "BrowserObservation | None" = None

    @property
    def active_page(self) -> "Page | None":
        if not self.pages:
            return None
        idx = min(self.active_page_index, len(self.pages) - 1)
        return self.pages[idx]

    def on_request(self, cb: Callable[[Any], Any]) -> None:
        """Register a passive request listener."""
        self._request_callbacks.append(cb)
        for page in self.pages:
            try:
                page.on("request", cb)
            except Exception:
                pass

    def on_response(self, cb: Callable[[Any], Any]) -> None:
        """Register a passive response listener."""
        self._response_callbacks.append(cb)
        for page in self.pages:
            try:
                page.on("response", cb)
            except Exception:
                pass

    async def _attach_listeners(self, page: "Page") -> None:
        """Wire console + network listeners on a newly opened page."""

        def on_console(msg: Any) -> None:
            entry = f"[{msg.type}] {msg.text}"
            self._console_logs.append(entry)
            if len(self._console_logs) > 200:
                self._console_logs.pop(0)

        def on_request(req: Any) -> None:
            self._request_times[req.url] = time.monotonic()
            for cb in self._request_callbacks:
                try:
                    cb(req)
                except Exception:
                    pass

        def on_response(resp: Any) -> None:
            start = self._request_times.pop(resp.request.url, None)
            dur = int((time.monotonic() - start) * 1000) if start else 0
            self._network_log.append(NetworkEntry(
                url=resp.url,
                method=resp.request.method,
                status=resp.status,
                duration_ms=dur,
                resource_type=resp.request.resource_type,
            ))
            if len(self._network_log) > 500:
                self._network_log.pop(0)
            for cb in self._response_callbacks:
                try:
                    cb(resp)
                except Exception:
                    pass

        page.on("console", on_console)
        page.on("request", on_request)
        page.on("response", on_response)

        # Wire active request/response callbacks registered prior to page load
        for cb in self._request_callbacks:
            try:
                page.on("request", cb)
            except Exception:
                pass
        for cb in self._response_callbacks:
            try:
                page.on("response", cb)
            except Exception:
                pass

        # Trigger tracker blocklist routing if STEALTH mode is enabled
        if self.anti_bot_mode == AntiBotMode.STEALTH:
            try:
                from .anti_bot import route_block_trackers
                await route_block_trackers(page)
            except Exception as e:
                logger.warning(f"Failed to enable tracker route blocking on page: {e}")

        # Inject glitchy overlay bundle
        try:
            bundle_path = Path(__file__).parent.parent.parent / "playwright-glitchy-framework" / "dist" / "glitchyOverlay.bundle.js"
            if bundle_path.is_file():
                bundle_source = bundle_path.read_text(encoding="utf-8")
                bootstrap = f"""
                  (function () {{
                    if (document.getElementById('julius-glitchy-root')) return;

                    {bundle_source}

                    var JuliusOverlayGlobal =
                      (typeof JuliusOverlay !== 'undefined' && JuliusOverlay) ||
                      (typeof window !== 'undefined' && window.JuliusOverlay);

                    var injectFn =
                      (JuliusOverlayGlobal && JuliusOverlayGlobal.injectGlitchyOverlay) ||
                      (typeof injectGlitchyOverlay !== 'undefined' && injectGlitchyOverlay);

                    if (typeof injectFn === 'function') {{
                      var start = function() {{
                        if (!document.getElementById('julius-glitchy-root')) {{
                          try {{
                            injectFn({{}});
                          }} catch (e) {{
                            console.error('Failed to inject glitchy overlay:', e);
                          }}
                        }}
                      }};
                      if (document.readyState === 'loading') {{
                        document.addEventListener('DOMContentLoaded', start);
                      }} else {{
                        start();
                      }}
                    }}
                  }})();
                """
                await page.add_init_script(script=bootstrap)
        except Exception as exc:
            logger.warning(f"Failed to inject glitchy overlay: {exc}")

    def drain_logs(self) -> tuple[list[str], list[NetworkEntry]]:
        """Return and clear current console/network buffers."""
        logs = list(self._console_logs)
        net = list(self._network_log)
        self._console_logs.clear()
        self._network_log.clear()
        return logs, net


# ── Main engine ───────────────────────────────────────────────────────────────

class PlaywrightEngine:
    """
    Async singleton that owns the Playwright instance for the agent session.

    Lifecycle
    ---------
    1. ``await engine.start()``  — called once at agent startup
    2. Actions use ``engine.get_context(ctx_id)`` / ``engine.open_page(ctx_id)``
    3. ``await engine.stop()``   — called at agent shutdown (closes browser)

    The "default" context is created automatically on first use.
    """

    DEFAULT_CONTEXT = "default"

    # ── Global shared singleton state ─────────────────────────────────────────
    # All WebAgent instances share ONE browser process so multiple windows/contexts
    # can co-exist without one task closing another's window.
    _shared_pw: "PlaywrightContextManager | None" = None
    _shared_browser: "Browser | None" = None
    _shared_contexts: dict[str, BrowserContextRecord] = {}

    # Resolved once from env at first start so every instance agrees on the mode.
    _headed_mode_resolved: bool = False
    _headed_mode: bool = True  # default = headed (keeps windows alive)

    def __init__(self, workspace_root: str) -> None:
        # Force external browser off for now as requested by user
        self._use_external_browser = False
        self._use_lightpanda = os.getenv("JULIUS_USE_LIGHTPANDA", "false").lower() in ("true", "1", "yes")
        self._use_obscura = os.getenv("JULIUS_USE_OBSCURA", "false").lower() in ("true", "1", "yes")
        self._external_url = os.getenv("JULIUS_BROWSER_URL", "http://127.0.0.1:17321/rpc")
        self._lightpanda_url = os.getenv("JULIUS_LIGHTPANDA_URL", "ws://127.0.0.1:9222/")
        self._obscura_url = os.getenv("JULIUS_OBSCURA_URL", "ws://127.0.0.1:9223/")
        self._session: aiohttp.ClientSession | None = None
        self._lightpanda_proc = None
        self._obscura_proc = None
        
        if not _PLAYWRIGHT_AVAILABLE and not self._use_external_browser:
            raise ImportError(
                "playwright is not installed. Run: pip install playwright && playwright install chromium"
            )
        self.workspace_root = workspace_root
        self._pw: "PlaywrightContextManager | None" = None
        self._browser: "Browser | None" = None
        self._contexts: dict[str, BrowserContextRecord] = {}
        self.retry_policy = ActionRetryPolicy()

        # Resolve headless flag once globally so all instances agree.
        if not PlaywrightEngine._headed_mode_resolved:
            headless_env = os.getenv("JULIUS_HEADLESS", "false").lower() in ("true", "1", "yes")
            PlaywrightEngine._headed_mode = not headless_env  # headed = NOT headless
            PlaywrightEngine._headed_mode_resolved = True

        self._headless = not PlaywrightEngine._headed_mode

        # Global persistent browser world model
        from .world_model import WorldModel
        self.world_model = WorldModel(workspace_root, persist=True)

    async def _rpc_direct(self, method: str, params: dict | None = None) -> Any:
        if params is None:
            params = {}
        payload = {
            "jsonrpc": "2.0",
            "id": int(time.time() * 1000),
            "method": method,
            "params": params
        }
        if not self._session:
            self._session = aiohttp.ClientSession()
        async with self._session.post(self._external_url, json=payload) as resp:
            if resp.status != 200 and resp.status != 400:
                raise RuntimeError(f"JSON-RPC server returned HTTP {resp.status}")
            data = await resp.json()
            if isinstance(data, list):
                data = data[0]
            if "error" in data:
                raise RuntimeError(data["error"].get("message", "Unknown RPC error"))
            return data.get("result")

    async def ensure_started(self) -> None:
        """Lazily start the browser engine if not already started."""
        if self._pw is None and getattr(self, "_session", None) is None:
            await self.start()

    async def start(self) -> None:
        """Launch the Playwright browser. Call once at agent startup.
        
        If the shared browser already exists (headed mode, previous task),
        this simply re-attaches to it — no new window is opened.
        """
        if self._use_external_browser:
            self._session = aiohttp.ClientSession()
            connected = False
            try:
                async with self._session.get(self._external_url.replace("/rpc", "/health")) as resp:
                    if resp.status == 200:
                        logger.info("PlaywrightEngine: Connected to healthy external browser JSON-RPC server.")
                        connected = True
            except Exception:
                pass

            if not connected:
                if self._session:
                    await self._session.close()
                    self._session = None

                import subprocess
                browser_dir = Path(self.workspace_root) / "Julius_Browser"
                if not (browser_dir.exists() and (browser_dir / "package.json").exists()):
                    browser_dir = Path(self.workspace_root).parent / "Julius_Browser"
                
                if browser_dir.exists() and (browser_dir / "package.json").exists():
                    logger.info("PlaywrightEngine: Attempting to launch Julius Browser automatically via 'npm start'...")
                    self._external_browser_proc = subprocess.Popen(
                        ["npm", "start"],
                        cwd=str(browser_dir),
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
                    self._session = aiohttp.ClientSession()
                    started = False
                    for _ in range(50):
                        await asyncio.sleep(0.2)
                        try:
                            async with self._session.get(self._external_url.replace("/rpc", "/health")) as resp:
                                if resp.status == 200:
                                    started = True
                                    break
                        except Exception:
                            pass
                    if not started:
                        if hasattr(self, "_external_browser_proc") and self._external_browser_proc is not None:
                            self._external_browser_proc.terminate()
                            self._external_browser_proc = None
                        await self._session.close()
                        self._session = None
                        raise RuntimeError(f"Timed out waiting for Julius Browser to start on {self._external_url}.")
                    logger.info("PlaywrightEngine: Julius Browser launched successfully.")
                else:
                    raise RuntimeError(
                        f"External browser is not running on {self._external_url} "
                        "and Julius_Browser directory was not found in workspace root."
                    )
            
            # Connect over CDP natively
            self._pw = await async_playwright().start()
            connected_cdp = False
            for _ in range(30):
                try:
                    self._browser = await self._pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
                    connected_cdp = True
                    break
                except Exception:
                    await asyncio.sleep(0.2)
            if not connected_cdp:
                raise RuntimeError("Timed out waiting to connect to Electron CDP on port 9222.")
                
            logger.info("PlaywrightEngine: Connected to external browser over CDP natively.")
            PlaywrightEngine._shared_pw = self._pw
            PlaywrightEngine._shared_browser = self._browser
            PlaywrightEngine._shared_contexts = self._contexts
            return


        if self._use_lightpanda:
            import socket
            port = 9222
            if "127.0.0.1:" in self._lightpanda_url or "localhost:" in self._lightpanda_url:
                try:
                    port = int(self._lightpanda_url.split(":")[-1].replace("/", ""))
                except Exception:
                    pass
            
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.5)
            already_running = False
            try:
                s.connect(("127.0.0.1", port))
                already_running = True
                s.close()
                logger.info(f"PlaywrightEngine: Found already running CDP server on port {port}. Connecting...")
            except Exception:
                pass
            
            if not already_running:
                import shutil
                import subprocess
                # Search order: workspace root, workspace/scratch, system PATH
                candidates = [
                    Path(self.workspace_root) / "lightpanda",
                    Path(self.workspace_root) / "scratch" / "lightpanda",
                ]
                lp_path: str | None = None
                for candidate in candidates:
                    if candidate.exists() and os.access(str(candidate), os.X_OK):
                        lp_path = str(candidate)
                        break
                
                if lp_path is None:
                    system_lp = shutil.which("lightpanda")
                    if system_lp:
                        lp_path = system_lp
                    else:
                        raise FileNotFoundError(
                            "Lightpanda binary not found. Please place the nightly binary at "
                            f"{self.workspace_root}/scratch/lightpanda or install it globally via Homebrew."
                        )
                
                logger.info(f"PlaywrightEngine: Launching Lightpanda serve process from {lp_path}...")
                self._lightpanda_proc = subprocess.Popen(
                    [lp_path, "serve", "--host", "127.0.0.1", "--port", str(port), "--obey-robots"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                
                import urllib.request
                started = False
                for _ in range(50):
                    await asyncio.sleep(0.1)
                    if self._lightpanda_proc.poll() is not None:
                        out, err = self._lightpanda_proc.communicate()
                        raise RuntimeError(f"Lightpanda failed to start: {err.decode('utf-8')}")
                    try:
                        req = urllib.request.Request(f"http://127.0.0.1:{port}/json/version")
                        with urllib.request.urlopen(req, timeout=0.1) as resp:
                            if resp.status == 200:
                                started = True
                                break
                    except Exception:
                        pass
                
                if not started:
                    if self._lightpanda_proc:
                        self._lightpanda_proc.terminate()
                        self._lightpanda_proc = None
                    raise RuntimeError("Timed out waiting for Lightpanda to start on port 9222.")
                logger.info("PlaywrightEngine: Lightpanda serve started successfully.")
            
            self._pw = await async_playwright().start()
            self._browser = await self._pw.chromium.connect_over_cdp(self._lightpanda_url)
            logger.info("PlaywrightEngine: Connected to Lightpanda browser globally.")
            return

        if self._use_obscura:
            import socket
            port = 9223
            if "127.0.0.1:" in self._obscura_url or "localhost:" in self._obscura_url:
                try:
                    port = int(self._obscura_url.split(":")[-1].replace("/", ""))
                except Exception:
                    pass
            
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.5)
            already_running = False
            try:
                s.connect(("127.0.0.1", port))
                already_running = True
                s.close()
                logger.info(f"PlaywrightEngine: Found already running Obscura CDP server on port {port}. Connecting...")
            except Exception:
                pass
            
            if not already_running:
                import shutil
                import subprocess
                # Search order: workspace root, workspace/scratch, system PATH
                candidates = [
                    Path(self.workspace_root) / "obscura",
                    Path(self.workspace_root) / "scratch" / "obscura",
                ]
                obs_path: str | None = None
                for candidate in candidates:
                    if candidate.exists() and os.access(str(candidate), os.X_OK):
                        obs_path = str(candidate)
                        break
                
                if obs_path is None:
                    system_obs = shutil.which("obscura")
                    if system_obs:
                        obs_path = system_obs
                    else:
                        raise FileNotFoundError(
                            "Obscura binary not found. Please place the nightly binary at "
                            f"{self.workspace_root}/scratch/obscura or install it globally."
                        )
                
                logger.info(f"PlaywrightEngine: Launching Obscura serve process from {obs_path}...")
                self._obscura_proc = subprocess.Popen(
                    [obs_path, "serve", "--port", str(port), "--stealth"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                
                import urllib.request
                started = False
                for _ in range(50):
                    await asyncio.sleep(0.1)
                    if self._obscura_proc.poll() is not None:
                        out, err = self._obscura_proc.communicate()
                        raise RuntimeError(f"Obscura failed to start: {err.decode('utf-8')}")
                    try:
                        req = urllib.request.Request(f"http://127.0.0.1:{port}/json/version")
                        with urllib.request.urlopen(req, timeout=0.1) as resp:
                            if resp.status == 200:
                                started = True
                                break
                    except Exception:
                        pass
                
                if not started:
                    if self._obscura_proc:
                        self._obscura_proc.terminate()
                        self._obscura_proc = None
                    raise RuntimeError(f"Timed out waiting for Obscura to start on port {port}.")
                logger.info("PlaywrightEngine: Obscura serve started successfully.")
            
            self._pw = await async_playwright().start()
            self._browser = await self._pw.chromium.connect_over_cdp(self._obscura_url)
            logger.info("PlaywrightEngine: Connected to Obscura browser globally.")
            return

        if PlaywrightEngine._shared_browser is not None:
            self._pw = PlaywrightEngine._shared_pw
            self._browser = PlaywrightEngine._shared_browser
            self._contexts = PlaywrightEngine._shared_contexts
            logger.info(
                f"PlaywrightEngine: attached to shared browser "
                f"({len(self._contexts)} existing context(s))"
            )
            return

        self._pw = await async_playwright().start()
        
        user_profile_dir = os.path.expanduser("~/.gemini/julius_browser_profile")
        os.makedirs(user_profile_dir, exist_ok=True)
        
        # Remove leftover SingletonLock to prevent startup blocks
        lock_file = os.path.join(user_profile_dir, "SingletonLock")
        if os.path.exists(lock_file) or os.path.islink(lock_file):
            try:
                os.remove(lock_file)
                logger.info("PlaywrightEngine: Removed leftover SingletonLock file.")
            except Exception as e:
                logger.warning(f"PlaywrightEngine: Failed to remove SingletonLock: {e}")

        try:
            persistent_ctx = await self._pw.chromium.launch_persistent_context(
                user_data_dir=user_profile_dir,
                headless=self._headless,
                args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
            )
        except Exception as e:
            err_lower = str(e).lower()
            if "playwright install" in err_lower or "executable doesn't exist" in err_lower or "chromium" in err_lower:
                logger.info("PlaywrightEngine: Chromium browser missing. Installing automatically...")
                import subprocess, sys
                subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
                persistent_ctx = await self._pw.chromium.launch_persistent_context(
                    user_data_dir=user_profile_dir,
                    headless=self._headless,
                    args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
                )
            else:
                persistent_ctx = await self._pw.chromium.launch_persistent_context(
                    user_data_dir=user_profile_dir,
                    headless=self._headless,
                    args=["--no-sandbox"]
                )


        class PersistentBrowserShim:
            def __init__(self, context, pw):
                self._context = context
                self._pw = pw
                self.contexts = [context]

            async def new_context(self, **opts):
                # Always reuse the same persistent context to block incognito/guest mode
                return self._context

            async def close(self):
                await self._context.close()

        self._browser = PersistentBrowserShim(persistent_ctx, self._pw)

        # Persist to class-level singletons
        PlaywrightEngine._shared_pw = self._pw
        PlaywrightEngine._shared_browser = self._browser
        PlaywrightEngine._shared_contexts = self._contexts
        logger.info(f"PlaywrightEngine started globally using persistent profile (headless={self._headless})")


    async def stop(self) -> None:
        """Agent-task teardown hook.
        
        In **headed** mode this is intentionally a no-op — we keep every
        browser window alive between tasks so the user can see and interact
        with all windows without anything disappearing unexpectedly.
        
        In **headless** mode we clean up normally.
        Call :meth:`force_stop` for an unconditional full shutdown.
        """
        if self._use_external_browser:
            if self._session:
                await self._session.close()
                self._session = None
            return
        if self._use_lightpanda or self._use_obscura:
            await self._do_stop()
            return
        if PlaywrightEngine._headed_mode:
            logger.info(
                "PlaywrightEngine.stop() called in headed mode — "
                "skipping teardown to keep all windows alive."
            )
            return

        await self._do_stop()

    async def force_stop(self) -> None:
        """Unconditionally close the browser and all contexts.
        
        Use only when the whole application is shutting down.
        """
        logger.info("PlaywrightEngine.force_stop() — closing all browser resources.")
        await self._do_stop()

    async def _do_stop(self) -> None:
        """Internal: actually close everything."""
        if self._use_external_browser:
            if self._session:
                await self._session.close()
                self._session = None
            if hasattr(self, "_external_browser_proc") and self._external_browser_proc is not None:
                try:
                    self._external_browser_proc.terminate()
                    try:
                        self._external_browser_proc.wait(timeout=3)
                    except Exception:
                        self._external_browser_proc.kill()
                    logger.info("PlaywrightEngine: External Browser subprocess terminated.")
                except Exception as exc:
                    logger.warning(f"PlaywrightEngine: Error terminating External Browser process: {exc}")
                self._external_browser_proc = None
            self._contexts.clear()
            return
        for record in list(self._contexts.values()):
            try:
                await record.context.close()
            except Exception:
                pass
        self._contexts.clear()
        if PlaywrightEngine._shared_contexts is not self._contexts:
            PlaywrightEngine._shared_contexts.clear()
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None
            PlaywrightEngine._shared_browser = None
        if self._pw:
            try:
                await self._pw.stop()
            except Exception:
                pass
            self._pw = None
            PlaywrightEngine._shared_pw = None
        # Terminate Lightpanda subprocess only if we launched it
        if self._lightpanda_proc is not None:
            try:
                self._lightpanda_proc.terminate()
                try:
                    self._lightpanda_proc.wait(timeout=3)
                except Exception:
                    self._lightpanda_proc.kill()
                logger.info("PlaywrightEngine: Lightpanda subprocess terminated.")
            except Exception as exc:
                logger.warning(f"PlaywrightEngine: Error terminating Lightpanda process: {exc}")
            self._lightpanda_proc = None
        # Terminate Obscura subprocess only if we launched it
        if self._obscura_proc is not None:
            try:
                self._obscura_proc.terminate()
                try:
                    self._obscura_proc.wait(timeout=3)
                except Exception:
                    self._obscura_proc.kill()
                logger.info("PlaywrightEngine: Obscura subprocess terminated.")
            except Exception as exc:
                logger.warning(f"PlaywrightEngine: Error terminating Obscura process: {exc}")
            self._obscura_proc = None
        PlaywrightEngine._headed_mode_resolved = False  # allow re-init on next start
        logger.info("PlaywrightEngine fully stopped.")


    # ── Context management ───────────────────────────────────────────────────
    async def _get_active_native_page(self) -> Page:
        pages = self._browser.contexts[0].pages
        guest_pages = [p for p in pages if not p.url.startswith("file://")]
        if not guest_pages:
            await asyncio.sleep(0.5)
            pages = self._browser.contexts[0].pages
            guest_pages = [p for p in pages if not p.url.startswith("file://")]
        if not guest_pages:
            return pages[0]
        try:
            tabs = await self._rpc_direct("browser.listTabs")
            active_tab = next((t for t in tabs if t.get("active")), None) if tabs else None
            if active_tab:
                active_url = active_tab.get("url")
                for p in guest_pages:
                    if p.url == active_url:
                        return p
        except Exception:
            pass
        return guest_pages[-1]

    async def new_context(
        self,
        context_id: str = DEFAULT_CONTEXT,
        storage_state: str | None = None,
        anti_bot_mode: AntiBotMode = AntiBotMode.OFF,
        record_video: bool = False,
    ) -> BrowserContextRecord:
        """
        Create (or replace) a named browser context.

        Parameters
        ----------
        context_id:      Logical name — used in all subsequent browser actions.
        storage_state:   Path to a JSON session file (cookies + localStorage).
        anti_bot_mode:   Stealth level for this context.
        record_video:    If True, records video to workspace debug/videos/.
        """
        if self._use_external_browser and not self._use_lightpanda and not self._use_obscura:
            if context_id in self._contexts:
                return self._contexts[context_id]
            ctx = self._browser.contexts[0]
            record = BrowserContextRecord(context_id, ctx, self.workspace_root, anti_bot_mode=anti_bot_mode)
            native_page = await self._get_active_native_page()
            page = ExternalPage(self, native_page, tab_id="tab-1")
            await record._attach_listeners(page)
            record.pages = [page]
            self._contexts[context_id] = record
            logger.info(f"Browser context '{context_id}' created in external browser mode with native page")
            return record

        if context_id in self._contexts:
            if not self._headless:
                logger.info(f"Browser context '{context_id}' already exists. Reusing it to keep window awake.")
                return self._contexts[context_id]
            else:
                await self._contexts[context_id].context.close()
                del self._contexts[context_id]

        opts = pick_stealth_context_options(anti_bot_mode)

        if storage_state:
            state_path = Path(self.workspace_root) / storage_state
            if state_path.exists():
                opts["storage_state"] = str(state_path)
        elif self.DEFAULT_CONTEXT in self._contexts:
            try:
                default_ctx = self._contexts[self.DEFAULT_CONTEXT].context
                # Retrieve live cookies and localStorage from the default context
                state = await default_ctx.storage_state()
                opts["storage_state"] = state
                logger.info(
                    f"PlaywrightEngine: Inherited storage state from '{self.DEFAULT_CONTEXT}' context "
                    f"to prevent incognito/guest mode in new context '{context_id}'."
                )
            except Exception as e:
                logger.warning(f"PlaywrightEngine: Failed to inherit default context storage state: {e}")

        if record_video:
            from .recorder import build_video_context_options
            opts.update(build_video_context_options(self.workspace_root))

        ctx = await self._browser.new_context(**opts)
        script_deadline = int(os.getenv("JULIUS_SCRIPT_DEADLINE_MS", "30000"))
        ctx.set_default_timeout(script_deadline)
        record = BrowserContextRecord(context_id, ctx, self.workspace_root, anti_bot_mode=anti_bot_mode)
        self._contexts[context_id] = record
        logger.info(f"Browser context '{context_id}' created (anti_bot={anti_bot_mode})")
        return record


    def get_context(self, context_id: str = DEFAULT_CONTEXT) -> BrowserContextRecord | None:
        return self._contexts.get(context_id)

    async def ensure_context(
        self,
        context_id: str = DEFAULT_CONTEXT,
        anti_bot_mode: AntiBotMode = AntiBotMode.OFF,
    ) -> BrowserContextRecord:
        """Return existing context or create a new default one."""
        if context_id not in self._contexts:
            await self.new_context(context_id, anti_bot_mode=anti_bot_mode)
        return self._contexts[context_id]

    async def close_context(self, context_id: str) -> None:
        """Close a named browser context.
        
        In headed mode this is a no-op to prevent windows from disappearing
        when one agent task finishes or the next one starts.
        """
        if self._use_external_browser and not self._use_lightpanda and not self._use_obscura:
            if context_id in self._contexts:
                del self._contexts[context_id]
            return
        if PlaywrightEngine._headed_mode:
            logger.info(
                f"close_context('{context_id}') skipped — headed mode keeps all contexts alive."
            )
            return
        if context_id in self._contexts:
            try:
                await self._contexts[context_id].context.close()
            except Exception:
                pass
            del self._contexts[context_id]

    # ── Page management ──────────────────────────────────────────────────────

    async def open_page(
        self,
        context_id: str = DEFAULT_CONTEXT,
        anti_bot_mode: AntiBotMode = AntiBotMode.OFF,
    ) -> "Page":
        """Get the active page for a context (creating context+page if needed)."""
        record = await self.ensure_context(context_id, anti_bot_mode)
        if not record.pages:
            if self._use_external_browser and not self._use_lightpanda and not self._use_obscura:
                native_page = await self._get_active_native_page()
                page = ExternalPage(self, native_page, tab_id="tab-1")
                await record._attach_listeners(page)
            else:
                page = await record.context.new_page()
                await record._attach_listeners(page)
            record.pages.append(page)
        return record.active_page

    async def new_tab(
        self,
        context_id: str = DEFAULT_CONTEXT,
    ) -> tuple["Page", int]:
        """Open a new tab in the context. Returns (page, tab_index)."""
        record = await self.ensure_context(context_id)
        if self._use_external_browser and not self._use_lightpanda and not self._use_obscura:
            res = await self._rpc_direct("browser.newTab")
            tab_id = res.get("tabId") if res else f"tab-{len(record.pages)+1}"
            
            # Wait a moment for new guest page to register over CDP
            await asyncio.sleep(1.0)
            
            pages = self._browser.contexts[0].pages
            guest_pages = [p for p in pages if not p.url.startswith("file://")]
            existing_native_pages = {p._native_page for p in record.pages if hasattr(p, "_native_page")}
            new_native_page = next((p for p in guest_pages if p not in existing_native_pages), guest_pages[-1])
            
            page = ExternalPage(self, new_native_page, tab_id=tab_id)
            await record._attach_listeners(page)
        else:
            page = await record.context.new_page()
            await record._attach_listeners(page)
        record.pages.append(page)
        tab_index = len(record.pages) - 1
        record.active_page_index = tab_index
        return page, tab_index


    def switch_tab(self, context_id: str, tab_index: int) -> None:
        record = self._contexts.get(context_id)
        if record and 0 <= tab_index < len(record.pages):
            record.active_page_index = tab_index
            if self._use_external_browser and not self._use_lightpanda and not self._use_obscura:
                # Ask external browser to bring this tab's webview to front
                page = record.pages[tab_index]
                asyncio.create_task(self._rpc_direct("browser.switchTab", {"tabId": page._tab_id}))

    async def close_tab(self, context_id: str, tab_index: int | None = None) -> None:
        """Close a tab in the context.
        
        In headed mode this is a no-op — tabs are kept alive so multi-window
        testing workflows never lose a page mid-task.
        """
        if self._use_external_browser and not self._use_lightpanda and not self._use_obscura:
            record = self._contexts.get(context_id)
            if not record or not record.pages:
                return
            idx = tab_index if tab_index is not None else record.active_page_index
            if 0 <= idx < len(record.pages):
                page = record.pages[idx]
                try:
                    await self._rpc_direct("browser.closeTab", {"tabId": page._tab_id})
                except Exception:
                    pass
                record.pages.pop(idx)
                record.active_page_index = max(0, record.active_page_index - 1)
            return

        if PlaywrightEngine._headed_mode:
            logger.info(
                f"close_tab('{context_id}', {tab_index}) skipped — headed mode keeps all tabs alive."
            )
            return
        record = self._contexts.get(context_id)
        if not record or not record.pages:
            return
        idx = tab_index if tab_index is not None else record.active_page_index
        if 0 <= idx < len(record.pages):
            try:
                await record.pages[idx].close()
            except Exception:
                pass
            record.pages.pop(idx)
            record.active_page_index = max(0, record.active_page_index - 1)

    # ── Session persistence ──────────────────────────────────────────────────

    async def save_session(self, context_id: str, relative_path: str) -> str:
        """Save cookies + localStorage to a JSON file in the workspace."""
        if self._use_external_browser and not self._use_lightpanda and not self._use_obscura:
            logger.info("save_session: session persistence is managed by external browser - skipping.")
            return relative_path
        record = self._contexts.get(context_id)
        if not record:
            raise ValueError(f"Context '{context_id}' not found.")
        out_path = Path(self.workspace_root) / relative_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        await record.context.storage_state(path=str(out_path))
        logger.info(f"Session '{context_id}' saved to {relative_path}")
        return relative_path

    async def load_session(self, context_id: str, relative_path: str) -> None:
        """Re-create the context from a previously saved session file.
        
        In headed mode the existing context is reused with injected cookies
        rather than being destroyed and recreated, so the window stays open.
        """
        if self._use_external_browser and not self._use_lightpanda and not self._use_obscura:
            logger.info("load_session: session persistence is managed by external browser - skipping.")
            return
        state_path = Path(self.workspace_root) / relative_path
        if not state_path.exists():
            raise FileNotFoundError(f"Session file not found: {relative_path}")

        if PlaywrightEngine._headed_mode and context_id in self._contexts:
            # Inject cookies into the live context without closing/reopening it
            import json
            try:
                with open(state_path) as fh:
                    state = json.load(fh)
                record = self._contexts[context_id]
                if state.get("cookies"):
                    await record.context.add_cookies(state["cookies"])
                logger.info(
                    f"Session '{context_id}' cookies injected from {relative_path} (window kept alive)."
                )
                return
            except Exception as exc:
                logger.warning(f"Cookie injection failed ({exc}), falling back to context recreate.")

        await self.new_context(context_id, storage_state=relative_path)
        logger.info(f"Session '{context_id}' loaded from {relative_path}")

    # ── Snapshot helpers ─────────────────────────────────────────────────────

    async def take_screenshot(
        self,
        page: "Page",
        prefix: str = "verify",
    ) -> str:
        """Save a screenshot to a session-scoped temp directory and return the absolute path.
        
        Screenshots go to /tmp/julius_sessions/<session_id>/ so they are:
        - Not polluting the workspace root
        - Automatically cleaned up by the OS on reboot / session cleanup
        """
        import tempfile
        session_tmp = Path(tempfile.gettempdir()) / "julius_sessions" / getattr(self, '_session_id', 'default')
        session_tmp.mkdir(parents=True, exist_ok=True)
        filename = f"{prefix}_{int(time.time())}.png"
        path = session_tmp / filename

        # 1. Hide the glitchy overlay so it doesn't appear in / flicker during the screenshot
        try:
            await page.evaluate("""
                (() => {
                    const el = document.getElementById('julius-glitchy-root');
                    if (el) { el.__prev_display = el.style.display; el.style.display = 'none'; }
                })()
            """)
        except Exception:
            pass

        try:
            await page.screenshot(path=str(path))
        finally:
            # 2. Restore the overlay after the screenshot is taken
            try:
                await page.evaluate("""
                    (() => {
                        const el = document.getElementById('julius-glitchy-root');
                        if (el) { el.style.display = el.__prev_display || ''; delete el.__prev_display; }
                    })()
                """)
            except Exception:
                pass

        # Return absolute path so consumers can serve it without path-joining workspace_root
        return str(path)

    @staticmethod
    async def get_dom_snapshot(page: "Page", max_chars: int = 4000) -> str:
        """
        Return a condensed DOM skeleton via JS evaluation.

        Strips script/style tags, collapses whitespace, truncates to max_chars.
        """
        try:
            raw = await page.evaluate("""
                () => {
                    const clone = document.documentElement.cloneNode(true);
                    // Remove noise
                    for (const tag of ['script', 'style', 'svg', 'noscript', 'head']) {
                        for (const el of clone.querySelectorAll(tag)) el.remove();
                    }
                    // Collapse whitespace
                    let html = clone.outerHTML;
                    html = html.replace(/\\s{2,}/g, ' ').replace(/> </g, '>\\n<');
                    return html;
                }
            """)
            if len(raw) > max_chars:
                raw = raw[:max_chars] + "\n… (truncated)"
            return raw
        except Exception:
            return "(DOM snapshot unavailable)"

    @staticmethod
    async def get_interactive_elements(page: "Page") -> list[InteractiveElement]:
        """Extract all buttons, links, inputs, selects from the page."""
        try:
            elements = await page.evaluate("""
                () => {
                    const results = [];
                    const selectors = [
                        { sel: 'button', role: 'button' },
                        { sel: 'a[href]', role: 'link' },
                        { sel: 'input:not([type=hidden])', role: 'input' },
                        { sel: 'select', role: 'select' },
                        { sel: 'textarea', role: 'textarea' },
                        { sel: '[role=button]', role: 'button' },
                        { sel: '[role=link]', role: 'link' },
                        { sel: '[role=checkbox]', role: 'checkbox' },
                        { sel: '[role=tab]', role: 'tab' },
                        { sel: '[role=menuitem]', role: 'menuitem' },
                    ];
                    const seen = new Set();
                    for (const { sel, role } of selectors) {
                        for (const el of document.querySelectorAll(sel)) {
                            if (seen.has(el)) continue;
                            seen.add(el);
                            const label = (
                                el.getAttribute('aria-label') ||
                                el.getAttribute('placeholder') ||
                                el.innerText ||
                                el.value ||
                                el.name ||
                                el.id ||
                                el.className ||
                                ''
                            ).trim().slice(0, 80);
                            const r = role === 'input' ? (el.type || 'input') : role;
                            // Build best selector
                            let selector = '';
                            if (el.id) selector = '#' + el.id;
                            else if (el.name) selector = sel.split(':')[0] + '[name="' + el.name + '"]';
                            else selector = sel;
                            results.push({
                                role: r,
                                label,
                                selector,
                                disabled: el.disabled || false,
                                value: (el.value || '').slice(0, 100),
                            });
                        }
                    }
                    return results.slice(0, 50);  // cap at 50
                }
            """)
            return [
                InteractiveElement(
                    role=e.get("role", ""),
                    label=e.get("label", ""),
                    selector=e.get("selector", ""),
                    disabled=e.get("disabled", False),
                    value=e.get("value", ""),
                )
                for e in (elements or [])
            ]
        except Exception:
            return []

    async def build_observation(
        self,
        page: "Page",
        record: BrowserContextRecord,
        action: str,
        extra: dict | None = None,
        take_screenshot: bool = True,
        error: str | None = None,
        diff_mode: bool = True,
    ) -> BrowserObservation:
        """Build a full BrowserObservation for the current page state."""
        url = page.url
        title = await page.title()
        console_logs, network_requests = record.drain_logs()

        if error:
            return BrowserObservation(
                action=action,
                url=url,
                title=title,
                error=error,
                console_logs=console_logs,
                network_requests=network_requests,
            )

        bot = detect_bot_block(title, url)
        dom = await self.get_dom_snapshot(page)
        elements = await self.get_interactive_elements(page)

        screenshot_path = ""
        if take_screenshot:
            try:
                screenshot_path = await self.take_screenshot(page, prefix=action.replace("/", "_"))
            except Exception:
                pass

        obs = BrowserObservation(
            action=action,
            url=url,
            title=title,
            dom_snapshot=dom,
            interactive_elements=elements,
            console_logs=console_logs,
            network_requests=network_requests,
            screenshot_path=screenshot_path,
            bot_detection=bot,
            error=None,
            extra=extra or {},
        )

        # Calculate DOM diff if a previous observation exists
        if diff_mode and record.last_obs is not None:
            from .dom_diff import DOMDiff
            obs.diff = DOMDiff.diff(record.last_obs, obs)

        # Persist this observation as the last known state
        record.last_obs = obs
        return obs

    @property
    def is_running(self) -> bool:
        return self._browser is not None
