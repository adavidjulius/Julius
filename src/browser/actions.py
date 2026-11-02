"""
All browser action primitives for the Julius agent.

Each function takes a ``PlaywrightEngine`` plus action-specific args and
returns a ``BrowserObservation``.  The observation's ``.to_text()`` method
produces the text that goes into ``last_result`` in the agent's observation
template — enabling the agent to reason over page state as structured text
rather than relying on screenshots.

Actions exposed (all registered in BROWSER_ACTIONS dispatch table):
  Navigation   : browser_navigate, browser_reload, browser_go_back, browser_go_forward
  Interaction  : browser_click, browser_type, browser_select, browser_hover,
                 browser_scroll, browser_press, browser_clear,
                 browser_double_click, browser_right_click, browser_drag_to
  Touch        : browser_touch_tap, browser_touch_pinch_zoom, browser_touch_swipe
  Waiting      : browser_wait, browser_wait_for_load, browser_wait_for_selector
  Dialogs      : browser_accept_dialog, browser_dismiss_dialog, browser_set_dialog_override
  Snapshot     : browser_get_snapshot, browser_get_network_log, browser_get_console_log,
                 browser_screenshot_element, browser_print_to_pdf
  JS / Extract : browser_eval_js, browser_extract
  Emulation    : browser_set_geolocation, browser_clear_geolocation,
                 browser_set_device_metrics, browser_set_timezone,
                 browser_set_permissions, browser_set_extra_headers
  Network      : browser_enable_fetch, browser_disable_fetch,
                 browser_route_fulfill, browser_route_abort, browser_route_continue
  Contexts     : browser_new_context, browser_close_context
  Sessions     : browser_save_session, browser_load_session
  Tabs         : browser_new_tab, browser_switch_tab, browser_close_tab
  Files        : browser_upload_file, browser_expect_download
  Cookies      : browser_get_cookies, browser_set_cookie, browser_remove_cookie,
                 browser_clear_cookies
  Storage      : browser_clear_storage, browser_get_local_storage, browser_set_local_storage
  Tracing      : browser_start_trace, browser_stop_trace, browser_start_har, browser_stop_har
"""


from __future__ import annotations

import asyncio
import inspect
import logging
from pathlib import Path
from typing import Any

from .anti_bot import AntiBotMode, human_delay, human_type
from .engine import PlaywrightEngine
from .recorder import HARRecorder, TraceRecorder
from .structured_obs import BrowserObservation

logger = logging.getLogger(__name__)


async def _process_cognitive_layer(
    engine: PlaywrightEngine,
    action: str,
    args: dict,
    page: Any,
    record: Any,
    before_obs: BrowserObservation | None,
    obs: BrowserObservation,
) -> BrowserObservation:
    """
    Cognitive layer post-action hook.
    Updates memory, runs verifier checks, checks recovery, extracts facts.
    """
    if obs.error:
        from .memory import record_browser_failure
        record_browser_failure(record.memory, args.get("selector", ""), obs.error)
        return obs

    # 1. Update Browser Memory
    from .memory import record_browser_action
    record_browser_action(record.memory, action, args, obs.url)
    if action == "browser_navigate" and record.memory.page_history:
        record.memory.page_history[-1].title = obs.title

    # 2. Run Verification
    from .verifier import ActionVerifier
    verifier = ActionVerifier()
    if action == "browser_navigate":
        v_res = await verifier.verify_navigation(page, args.get("url", ""), obs)
        if not v_res.passed:
            obs.error = f"NavigationVerificationFailed: Expected {v_res.expected_state}, but got {v_res.actual_state}"
    elif action == "browser_click" and before_obs:
        v_res = await verifier.verify_click(page, args.get("selector", ""), args.get("text", ""), before_obs, obs)
        if not v_res.passed:
            obs.error = f"ClickVerificationFailed: {v_res.actual_state}. {v_res.retry_suggestion or ''}"
    elif action == "browser_type":
        v_res = await verifier.verify_type(page, args.get("selector", ""), args.get("text", ""), obs)
        if not v_res.passed:
            obs.error = f"TypeVerificationFailed: {v_res.actual_state}. {v_res.retry_suggestion or ''}"

    # 3. Fact Extraction
    from .world_model import FactExtractor
    FactExtractor(engine.world_model).extract(obs)

    # 4. Recovery check (if not already handled or errored)
    if not obs.error:
        from .recovery import RecoveryEngine
        rec_res = await RecoveryEngine().check_and_recover(page, obs, record.memory, engine.world_model)
        if rec_res.recovered:
            logger.info(f"Auto-recovery executed: {rec_res.action_taken}")
            obs = await engine.build_observation(page, record, action)
        elif rec_res.agent_message:
            obs.extra["recovery_warning"] = rec_res.agent_message

    return obs



# ── Navigation ────────────────────────────────────────────────────────────────

async def browser_navigate(
    engine: PlaywrightEngine,
    url: str,
    context_id: str = PlaywrightEngine.DEFAULT_CONTEXT,
    wait_until: str = "domcontentloaded",
    anti_bot_mode: str = "off",
    timeout_ms: int = 30000,
) -> BrowserObservation:
    """Navigate to a URL and return a full structured observation."""
    mode = AntiBotMode(anti_bot_mode)

    async def _do() -> BrowserObservation:
        page = await engine.open_page(context_id, anti_bot_mode=mode)
        record = engine.get_context(context_id)

        if mode != AntiBotMode.OFF:
            await human_delay("navigation")

        await page.goto(url, wait_until=wait_until, timeout=timeout_ms)

        if mode != AntiBotMode.OFF:
            await human_delay("navigation")

        obs = await engine.build_observation(page, record, "browser_navigate")
        return await _process_cognitive_layer(
            engine, "browser_navigate",
            {"url": url, "context_id": context_id, "wait_until": wait_until, "anti_bot_mode": anti_bot_mode, "timeout_ms": timeout_ms},
            page, record, None, obs
        )

    return await engine.retry_policy.execute(_do, "browser_navigate")


# ── Interactions ──────────────────────────────────────────────────────────────

async def browser_click(
    engine: PlaywrightEngine,
    selector: str = "",
    text: str = "",
    context_id: str = PlaywrightEngine.DEFAULT_CONTEXT,
    anti_bot_mode: str = "off",
    timeout_ms: int = 10000,
) -> BrowserObservation:
    """Click an element identified by CSS selector or visible text."""
    mode = AntiBotMode(anti_bot_mode)

    async def _do() -> BrowserObservation:
        page = await engine.open_page(context_id)
        record = engine.get_context(context_id)

        before_obs = record.last_obs

        if mode != AntiBotMode.OFF:
            await human_delay("click")

        loc = None
        if text:
            loc = page.get_by_text(text, exact=False).first
        elif selector:
            loc = page.locator(selector).first
        else:
            raise ValueError("browser_click requires either 'selector' or 'text'.")

        try:
            await loc.click(timeout=timeout_ms)
        except Exception as click_err:
            box = None
            if hasattr(loc, "bounding_box"):
                res = loc.bounding_box()
                box = await res if asyncio.iscoroutine(res) else res
            if box and hasattr(page, "mouse") and hasattr(page.mouse, "click"):
                cx = box["x"] + box["width"] / 2.0
                cy = box["y"] + box["height"] / 2.0
                m_res = page.mouse.click(cx, cy)
                if asyncio.iscoroutine(m_res):
                    await m_res
            else:
                raise click_err

        # Wait for any navigation/dom change to settle
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=5000)
        except Exception:
            pass

        obs = await engine.build_observation(page, record, "browser_click")
        return await _process_cognitive_layer(
            engine, "browser_click",
            {"selector": selector, "text": text, "context_id": context_id, "anti_bot_mode": anti_bot_mode, "timeout_ms": timeout_ms},
            page, record, before_obs, obs
        )

    return await engine.retry_policy.execute(_do, "browser_click")


async def browser_type(
    engine: PlaywrightEngine,
    selector: str,
    text: str,
    context_id: str = PlaywrightEngine.DEFAULT_CONTEXT,
    clear: bool = True,
    anti_bot_mode: str = "off",
    timeout_ms: int = 10000,
) -> BrowserObservation:
    """Fill an input field with text (optionally clearing first)."""
    mode = AntiBotMode(anti_bot_mode)

    async def _do() -> BrowserObservation:
        page = await engine.open_page(context_id)
        record = engine.get_context(context_id)

        before_obs = record.last_obs

        if mode != AntiBotMode.OFF:
            await human_delay("click")

        await page.wait_for_selector(selector, timeout=timeout_ms)
        if clear:
            await page.fill(selector, "")

        if mode == AntiBotMode.HUMAN:
            await human_type(page, selector, text)
        else:
            await page.fill(selector, text)

        obs = await engine.build_observation(page, record, "browser_type")
        return await _process_cognitive_layer(
            engine, "browser_type",
            {"selector": selector, "text": text, "context_id": context_id, "clear": clear, "anti_bot_mode": anti_bot_mode, "timeout_ms": timeout_ms},
            page, record, before_obs, obs
        )

    return await engine.retry_policy.execute(_do, "browser_type")


async def browser_select(
    engine: PlaywrightEngine,
    selector: str,
    value: str,
    context_id: str = PlaywrightEngine.DEFAULT_CONTEXT,
    timeout_ms: int = 10000,
) -> BrowserObservation:
    """Select an option in a <select> element by value, label, or index."""
    async def _do() -> BrowserObservation:
        page = await engine.open_page(context_id)
        record = engine.get_context(context_id)
        before_obs = record.last_obs
        await page.wait_for_selector(selector, timeout=timeout_ms)
        await page.select_option(selector, value=value)
        obs = await engine.build_observation(page, record, "browser_select")
        return await _process_cognitive_layer(
            engine, "browser_select",
            {"selector": selector, "value": value, "context_id": context_id, "timeout_ms": timeout_ms},
            page, record, before_obs, obs
        )

    return await engine.retry_policy.execute(_do, "browser_select")


async def browser_hover(
    engine: PlaywrightEngine,
    selector: str,
    context_id: str = PlaywrightEngine.DEFAULT_CONTEXT,
    timeout_ms: int = 10000,
) -> BrowserObservation:
    """Hover the mouse over an element."""
    async def _do() -> BrowserObservation:
        page = await engine.open_page(context_id)
        record = engine.get_context(context_id)
        await page.hover(selector, timeout=timeout_ms)
        await asyncio.sleep(0.3)  # let tooltip/menu appear
        return await engine.build_observation(page, record, "browser_hover")

    return await engine.retry_policy.execute(_do, "browser_hover")


async def browser_scroll(
    engine: PlaywrightEngine,
    direction: str = "down",
    px: int = 500,
    context_id: str = PlaywrightEngine.DEFAULT_CONTEXT,
) -> BrowserObservation:
    """Scroll the page. direction: 'up' | 'down' | 'left' | 'right'."""
    async def _do() -> BrowserObservation:
        page = await engine.open_page(context_id)
        record = engine.get_context(context_id)
        delta_x = px if direction == "right" else (-px if direction == "left" else 0)
        delta_y = px if direction == "down" else (-px if direction == "up" else 0)
        await page.mouse.wheel(delta_x, delta_y)
        await asyncio.sleep(0.3)
        return await engine.build_observation(page, record, "browser_scroll")

    return await engine.retry_policy.execute(_do, "browser_scroll")


async def browser_press(
    engine: PlaywrightEngine,
    key: str,
    context_id: str = PlaywrightEngine.DEFAULT_CONTEXT,
) -> BrowserObservation:
    """Press a keyboard key (e.g. Enter, Tab, Escape, ArrowDown)."""
    async def _do() -> BrowserObservation:
        page = await engine.open_page(context_id)
        record = engine.get_context(context_id)
        await page.keyboard.press(key)
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=3000)
        except Exception:
            pass
        return await engine.build_observation(page, record, "browser_press")

    return await engine.retry_policy.execute(_do, "browser_press")


async def browser_clear(
    engine: PlaywrightEngine,
    selector: str,
    context_id: str = PlaywrightEngine.DEFAULT_CONTEXT,
    timeout_ms: int = 10000,
) -> BrowserObservation:
    """Clear an input field."""
    async def _do() -> BrowserObservation:
        page = await engine.open_page(context_id)
        record = engine.get_context(context_id)
        await page.fill(selector, "", timeout=timeout_ms)
        return await engine.build_observation(page, record, "browser_clear")

    return await engine.retry_policy.execute(_do, "browser_clear")


# ── Waiting ───────────────────────────────────────────────────────────────────

async def browser_wait(
    engine: PlaywrightEngine,
    selector: str = "",
    timeout_ms: int = 10000,
    state: str = "visible",
    context_id: str = PlaywrightEngine.DEFAULT_CONTEXT,
) -> BrowserObservation:
    """
    Wait for a condition, then return observation.

    If selector is empty, waits for network idle instead.
    state: 'visible' | 'hidden' | 'attached' | 'detached'
    """
    async def _do() -> BrowserObservation:
        page = await engine.open_page(context_id)
        record = engine.get_context(context_id)

        if selector:
            await page.wait_for_selector(selector, state=state, timeout=timeout_ms)
        else:
            await page.wait_for_load_state("networkidle", timeout=timeout_ms)

        return await engine.build_observation(page, record, "browser_wait")

    return await engine.retry_policy.execute(_do, "browser_wait")


# ── Snapshot ──────────────────────────────────────────────────────────────────

async def browser_get_snapshot(
    engine: PlaywrightEngine,
    context_id: str = PlaywrightEngine.DEFAULT_CONTEXT,
) -> BrowserObservation:
    """Return a full observation of the current page state without performing any action."""
    try:
        page = await engine.open_page(context_id)
        record = engine.get_context(context_id)
        return await engine.build_observation(page, record, "browser_get_snapshot")
    except Exception as exc:
        return BrowserObservation(action="browser_get_snapshot", error=str(exc))


async def browser_get_network_log(
    engine: PlaywrightEngine,
    context_id: str = PlaywrightEngine.DEFAULT_CONTEXT,
    method_filter: str = "",
    url_filter: str = "",
) -> BrowserObservation:
    """Return accumulated network log for the context (optionally filtered)."""
    try:
        record = engine.get_context(context_id)
        if not record:
            return BrowserObservation(action="browser_get_network_log", error=f"Context '{context_id}' not found.")
        log = list(record._network_log)
        if method_filter:
            log = [r for r in log if r.method.upper() == method_filter.upper()]
        if url_filter:
            log = [r for r in log if url_filter in r.url]
        obs = BrowserObservation(action="browser_get_network_log")
        obs.network_requests.extend(log)
        return obs
    except Exception as exc:
        return BrowserObservation(action="browser_get_network_log", error=str(exc))


async def browser_get_console_log(
    engine: PlaywrightEngine,
    context_id: str = PlaywrightEngine.DEFAULT_CONTEXT,
) -> BrowserObservation:
    """Return accumulated console log for the context."""
    try:
        record = engine.get_context(context_id)
        if not record:
            return BrowserObservation(action="browser_get_console_log", error=f"Context '{context_id}' not found.")
        obs = BrowserObservation(action="browser_get_console_log")
        obs.console_logs.extend(list(record._console_logs))
        return obs
    except Exception as exc:
        return BrowserObservation(action="browser_get_console_log", error=str(exc))


# ── JavaScript evaluation & extraction ────────────────────────────────────────

async def browser_eval_js(
    engine: PlaywrightEngine,
    script: str = "",
    context_id: str = PlaywrightEngine.DEFAULT_CONTEXT,
    **kwargs,
) -> BrowserObservation:
    """Evaluate a JavaScript expression on the page and return the result."""
    js_expr = script or kwargs.get("js", "")
    if not js_expr:
        raise ValueError("browser_eval_js requires either 'script' or 'js'.")

    async def _do() -> BrowserObservation:
        page = await engine.open_page(context_id)
        record = engine.get_context(context_id)
        result = await page.evaluate(js_expr)
        return await engine.build_observation(
            page, record, "browser_eval_js",
            extra={"js_result": result},
            take_screenshot=False,
        )

    return await engine.retry_policy.execute(_do, "browser_eval_js")


async def browser_extract(
    engine: PlaywrightEngine,
    selectors: dict[str, str],
    context_id: str = PlaywrightEngine.DEFAULT_CONTEXT,
) -> BrowserObservation:
    """
    Extract multiple fields from the page by CSS selector map.

    Args
    ----
    selectors: {"field_name": "css_selector", ...}

    Example
    -------
    {"title": "h1", "price": ".price", "description": "#desc p"}
    → extra = {"title": "...", "price": "$29.99", "description": "..."}
    """
    async def _do() -> BrowserObservation:
        page = await engine.open_page(context_id)
        record = engine.get_context(context_id)

        extracted: dict[str, Any] = {}
        for field, sel in selectors.items():
            try:
                el = await page.query_selector(sel)
                if el:
                    extracted[field] = (await el.inner_text()).strip()
                else:
                    extracted[field] = None
            except Exception as exc:
                extracted[field] = f"ERROR: {exc}"

        return await engine.build_observation(
            page, record, "browser_extract",
            extra={"extraction": extracted},
            take_screenshot=False,
        )

    return await engine.retry_policy.execute(_do, "browser_extract")


# ── Context management ────────────────────────────────────────────────────────

async def browser_new_context(
    engine: PlaywrightEngine,
    context_id: str,
    storage_state: str | None = None,
    anti_bot_mode: str = "off",
    record_video: bool = False,
) -> BrowserObservation:
    """Create a new named browser context (isolated cookies/storage)."""
    try:
        mode = AntiBotMode(anti_bot_mode)
        await engine.new_context(
            context_id=context_id,
            storage_state=storage_state,
            anti_bot_mode=mode,
            record_video=record_video,
        )
        return BrowserObservation(
            action="browser_new_context",
            extra={"context_id": context_id, "created": True},
        )
    except Exception as exc:
        return BrowserObservation(action="browser_new_context", error=str(exc))


async def browser_close_context(
    engine: PlaywrightEngine,
    context_id: str,
) -> BrowserObservation:
    """Close and destroy a named browser context."""
    try:
        await engine.close_context(context_id)
        return BrowserObservation(
            action="browser_close_context",
            extra={"context_id": context_id, "closed": True},
        )
    except Exception as exc:
        return BrowserObservation(action="browser_close_context", error=str(exc))


# ── Session management ────────────────────────────────────────────────────────

async def browser_save_session(
    engine: PlaywrightEngine,
    path: str,
    context_id: str = PlaywrightEngine.DEFAULT_CONTEXT,
) -> BrowserObservation:
    """Save cookies + localStorage to a JSON session file in the workspace."""
    try:
        saved_path = await engine.save_session(context_id, path)
        return BrowserObservation(
            action="browser_save_session",
            extra={"saved_to": saved_path},
        )
    except Exception as exc:
        return BrowserObservation(action="browser_save_session", error=str(exc))


async def browser_load_session(
    engine: PlaywrightEngine,
    path: str,
    context_id: str = PlaywrightEngine.DEFAULT_CONTEXT,
) -> BrowserObservation:
    """Restore a previously saved browser session from a JSON file."""
    try:
        await engine.load_session(context_id, path)
        return BrowserObservation(
            action="browser_load_session",
            extra={"loaded_from": path, "context_id": context_id},
        )
    except Exception as exc:
        return BrowserObservation(action="browser_load_session", error=str(exc))


# ── Multi-tab ─────────────────────────────────────────────────────────────────

async def browser_new_tab(
    engine: PlaywrightEngine,
    url: str = "",
    context_id: str = PlaywrightEngine.DEFAULT_CONTEXT,
) -> BrowserObservation:
    """Open a new tab in the context (optionally navigate to a URL immediately)."""
    try:
        page, tab_index = await engine.new_tab(context_id)
        if url:
            await page.goto(url, wait_until="domcontentloaded")
        record = engine.get_context(context_id)
        obs = await engine.build_observation(page, record, "browser_new_tab")
        obs.extra["tab_index"] = tab_index
        return obs
    except Exception as exc:
        return BrowserObservation(action="browser_new_tab", error=str(exc))


async def browser_switch_tab(
    engine: PlaywrightEngine,
    tab_index: int | None = None,
    index: int | None = None,
    title: str | None = None,
    url: str | None = None,
    context_id: str = PlaywrightEngine.DEFAULT_CONTEXT,
) -> BrowserObservation:
    """Switch the active tab in a context by index, title keyword, or url keyword."""
    try:
        record = engine.get_context(context_id)
        target_idx = tab_index if tab_index is not None else index

        if record and record.pages:
            if title:
                for i, p in enumerate(record.pages):
                    t_val = p.title() if callable(getattr(p, "title", None)) else getattr(p, "title", "")
                    page_title = await t_val if asyncio.iscoroutine(t_val) else (t_val or "")
                    if title.lower() in page_title.lower():
                        target_idx = i
                        break
            elif url:
                for i, p in enumerate(record.pages):
                    page_url = getattr(p, "url", "")
                    if url.lower() in page_url.lower():
                        target_idx = i
                        break

        if target_idx is None:
            target_idx = 0

        engine.switch_tab(context_id, target_idx)
        page = record.active_page if record else None
        if not page and record and record.pages and 0 <= target_idx < len(record.pages):
            page = record.pages[target_idx]
        if not page:
            return BrowserObservation(action="browser_switch_tab", error="No page at that index.")
        return await engine.build_observation(page, record, "browser_switch_tab")
    except Exception as exc:
        return BrowserObservation(action="browser_switch_tab", error=str(exc))


async def browser_close_tab(
    engine: PlaywrightEngine,
    tab_index: int | None = None,
    context_id: str = PlaywrightEngine.DEFAULT_CONTEXT,
) -> BrowserObservation:
    """Close a tab (defaults to the active tab)."""
    try:
        await engine.close_tab(context_id, tab_index)
        return BrowserObservation(action="browser_close_tab", extra={"closed_tab": tab_index})
    except Exception as exc:
        return BrowserObservation(action="browser_close_tab", error=str(exc))


# ── File upload & download ────────────────────────────────────────────────────

async def browser_upload_file(
    engine: PlaywrightEngine,
    selector: str,
    file_path: str,
    context_id: str = PlaywrightEngine.DEFAULT_CONTEXT,
    timeout_ms: int = 10000,
) -> BrowserObservation:
    """Attach a local file to an <input type=file> element."""
    async def _do() -> BrowserObservation:
        page = await engine.open_page(context_id)
        record = engine.get_context(context_id)
        abs_path = str(Path(engine.workspace_root) / file_path)
        if not Path(abs_path).exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        await page.set_input_files(selector, abs_path, timeout=timeout_ms)
        return await engine.build_observation(
            page, record, "browser_upload_file",
            extra={"uploaded": file_path},
        )

    return await engine.retry_policy.execute(_do, "browser_upload_file")


async def browser_expect_download(
    engine: PlaywrightEngine,
    trigger_selector: str,
    save_path: str,
    context_id: str = PlaywrightEngine.DEFAULT_CONTEXT,
    timeout_ms: int = 60000,
) -> BrowserObservation:
    """Click a download trigger and save the resulting download to the workspace."""
    async def _do() -> BrowserObservation:
        page = await engine.open_page(context_id)
        record = engine.get_context(context_id)

        abs_save = str(Path(engine.workspace_root) / save_path)
        Path(abs_save).parent.mkdir(parents=True, exist_ok=True)

        async with page.expect_download(timeout=timeout_ms) as dl_info:
            await page.click(trigger_selector)
        download = await dl_info.value
        await download.save_as(abs_save)

        return await engine.build_observation(
            page, record, "browser_expect_download",
            extra={"downloaded_to": save_path, "suggested_filename": download.suggested_filename},
        )

    return await engine.retry_policy.execute(_do, "browser_expect_download")


# ── Tracing ───────────────────────────────────────────────────────────────────

async def browser_start_trace(
    engine: PlaywrightEngine,
    context_id: str = PlaywrightEngine.DEFAULT_CONTEXT,
    screenshots: bool = True,
    snapshots: bool = True,
) -> BrowserObservation:
    """Start a Playwright trace session on the context."""
    try:
        record = await engine.ensure_context(context_id)
        recorder = TraceRecorder(record.context, engine.workspace_root)
        await recorder.start(screenshots=screenshots, snapshots=snapshots)
        record.trace_recorder = recorder
        return BrowserObservation(
            action="browser_start_trace",
            extra={"context_id": context_id, "recording": True},
        )
    except Exception as exc:
        return BrowserObservation(action="browser_start_trace", error=str(exc))


async def browser_stop_trace(
    engine: PlaywrightEngine,
    path: str = "debug/trace.zip",
    context_id: str = PlaywrightEngine.DEFAULT_CONTEXT,
) -> BrowserObservation:
    """Stop trace recording and save the .zip file to the workspace."""
    try:
        record = engine.get_context(context_id)
        if not record or not record.trace_recorder:
            return BrowserObservation(action="browser_stop_trace", error="No active trace recorder.")
        saved = await record.trace_recorder.stop(path)
        record.trace_recorder = None
        return BrowserObservation(
            action="browser_stop_trace",
            extra={"saved_to": saved, "open_with": "npx playwright show-trace " + saved},
        )
    except Exception as exc:
        return BrowserObservation(action="browser_stop_trace", error=str(exc))


async def browser_start_har(
    engine: PlaywrightEngine,
    path: str = "debug/session.har",
    context_id: str = PlaywrightEngine.DEFAULT_CONTEXT,
) -> BrowserObservation:
    """Start recording all network activity to a HAR file."""
    try:
        page = await engine.open_page(context_id)
        record = engine.get_context(context_id)
        recorder = HARRecorder(page, engine.workspace_root)
        await recorder.start(path)
        record.har_recorder = recorder
        return BrowserObservation(
            action="browser_start_har",
            extra={"context_id": context_id, "path": path},
        )
    except Exception as exc:
        return BrowserObservation(action="browser_start_har", error=str(exc))


async def browser_stop_har(
    engine: PlaywrightEngine,
    context_id: str = PlaywrightEngine.DEFAULT_CONTEXT,
) -> BrowserObservation:
    """Finalise and flush the HAR recording."""
    try:
        record = engine.get_context(context_id)
        if not record or not record.har_recorder:
            return BrowserObservation(action="browser_stop_har", error="No active HAR recorder.")
        saved = await record.har_recorder.stop()
        record.har_recorder = None
        return BrowserObservation(
            action="browser_stop_har",
            extra={"saved_to": saved},
        )
    except Exception as exc:
        return BrowserObservation(action="browser_stop_har", error=str(exc))


# ── Phase 1: Navigation extras ────────────────────────────────────────────────

async def browser_reload(
    engine: PlaywrightEngine,
    ignore_cache: bool = False,
    context_id: str = PlaywrightEngine.DEFAULT_CONTEXT,
) -> BrowserObservation:
    """Reload the current page."""
    try:
        if engine._use_external_browser:
            await engine._rpc_direct("browser.reload", {"ignoreCache": ignore_cache})
        else:
            page = await engine.open_page(context_id)
            if ignore_cache:
                await page.reload(wait_until="domcontentloaded")
            else:
                await page.reload()
        record = engine.get_context(context_id)
        page = await engine.open_page(context_id)
        return await engine.build_observation(page, record, "browser_reload")
    except Exception as exc:
        return BrowserObservation(action="browser_reload", error=str(exc))


async def browser_go_back(
    engine: PlaywrightEngine,
    context_id: str = PlaywrightEngine.DEFAULT_CONTEXT,
) -> BrowserObservation:
    """Navigate back in browser history."""
    try:
        if engine._use_external_browser:
            await engine._rpc_direct("browser.goBack", {})
        else:
            page = await engine.open_page(context_id)
            await page.go_back()
        record = engine.get_context(context_id)
        page = await engine.open_page(context_id)
        return await engine.build_observation(page, record, "browser_go_back")
    except Exception as exc:
        return BrowserObservation(action="browser_go_back", error=str(exc))


async def browser_go_forward(
    engine: PlaywrightEngine,
    context_id: str = PlaywrightEngine.DEFAULT_CONTEXT,
) -> BrowserObservation:
    """Navigate forward in browser history."""
    try:
        if engine._use_external_browser:
            await engine._rpc_direct("browser.goForward", {})
        else:
            page = await engine.open_page(context_id)
            await page.go_forward()
        record = engine.get_context(context_id)
        page = await engine.open_page(context_id)
        return await engine.build_observation(page, record, "browser_go_forward")
    except Exception as exc:
        return BrowserObservation(action="browser_go_forward", error=str(exc))


# ── Phase 1: Wait states ──────────────────────────────────────────────────────

async def browser_wait_for_load(
    engine: PlaywrightEngine,
    state: str = "load",
    timeout_ms: int = 30000,
    context_id: str = PlaywrightEngine.DEFAULT_CONTEXT,
) -> BrowserObservation:
    """Wait for a page load state: 'load', 'domcontentloaded', or 'networkidle'."""
    try:
        if engine._use_external_browser:
            result = await engine._rpc_direct("browser.waitForLoad", {"state": state, "timeout": timeout_ms})
        else:
            page = await engine.open_page(context_id)
            await page.wait_for_load_state(state=state, timeout=timeout_ms)
            result = {"waited": True, "state": state}
        return BrowserObservation(action="browser_wait_for_load", extra=result or {})
    except Exception as exc:
        return BrowserObservation(action="browser_wait_for_load", error=str(exc))


async def browser_wait_for_selector(
    engine: PlaywrightEngine,
    selector: str,
    timeout_ms: int = 15000,
    visible: bool = True,
    context_id: str = PlaywrightEngine.DEFAULT_CONTEXT,
) -> BrowserObservation:
    """Wait until a CSS selector appears in the DOM (optionally visible)."""
    try:
        if engine._use_external_browser:
            result = await engine._rpc_direct("browser.waitForSelector", {
                "selector": selector, "timeout": timeout_ms, "visible": visible
            })
        else:
            page = await engine.open_page(context_id)
            state_arg = "visible" if visible else "attached"
            await page.wait_for_selector(selector, state=state_arg, timeout=timeout_ms)
            result = {"found": True, "selector": selector}
        return BrowserObservation(action="browser_wait_for_selector", extra=result or {})
    except Exception as exc:
        return BrowserObservation(action="browser_wait_for_selector", error=str(exc))


# ── Phase 2: Precise Input ────────────────────────────────────────────────────

async def browser_drag_to(
    engine: PlaywrightEngine,
    from_x: float | None = None,
    from_y: float | None = None,
    to_x: float | None = None,
    to_y: float | None = None,
    from_selector: str | None = None,
    to_selector: str | None = None,
    steps: int = 20,
    context_id: str = PlaywrightEngine.DEFAULT_CONTEXT,
) -> BrowserObservation:
    """Drag from one point/element to another with smooth intermediate steps."""
    try:
        if engine._use_external_browser:
            params: dict[str, Any] = {"steps": steps}
            if from_x is not None: params["fromX"] = from_x
            if from_y is not None: params["fromY"] = from_y
            if to_x is not None: params["toX"] = to_x
            if to_y is not None: params["toY"] = to_y
            result = await engine._rpc_direct("browser.dragTo", params)
        else:
            page = await engine.open_page(context_id)
            src_x = from_x or 0.0
            src_y = from_y or 0.0
            dst_x = to_x or 0.0
            dst_y = to_y or 0.0
            if from_selector:
                el = await page.query_selector(from_selector)
                bbox = await el.bounding_box()
                if bbox:
                    src_x = bbox["x"] + bbox["width"] / 2
                    src_y = bbox["y"] + bbox["height"] / 2
            if to_selector:
                el = await page.query_selector(to_selector)
                bbox = await el.bounding_box()
                if bbox:
                    dst_x = bbox["x"] + bbox["width"] / 2
                    dst_y = bbox["y"] + bbox["height"] / 2
            await page.mouse.move(src_x, src_y)
            await page.mouse.down()
            step_count = max(steps, 1)
            for i in range(1, step_count + 1):
                t = i / step_count
                await page.mouse.move(src_x + (dst_x - src_x) * t, src_y + (dst_y - src_y) * t)
            await page.mouse.up()
            result = {"dragged": True}
        return BrowserObservation(action="browser_drag_to", extra=result or {})
    except Exception as exc:
        return BrowserObservation(action="browser_drag_to", error=str(exc))


async def browser_double_click(
    engine: PlaywrightEngine,
    x: float | None = None,
    y: float | None = None,
    selector: str | None = None,
    context_id: str = PlaywrightEngine.DEFAULT_CONTEXT,
) -> BrowserObservation:
    """Double-click at a coordinate or element."""
    try:
        if engine._use_external_browser:
            params: dict[str, Any] = {}
            if x is not None: params["x"] = x
            if y is not None: params["y"] = y
            result = await engine._rpc_direct("browser.doubleClick", params)
        else:
            page = await engine.open_page(context_id)
            if selector:
                await page.dblclick(selector)
            elif x is not None and y is not None:
                await page.mouse.dblclick(x, y)
            result = {"clicked": True}
        return BrowserObservation(action="browser_double_click", extra=result or {})
    except Exception as exc:
        return BrowserObservation(action="browser_double_click", error=str(exc))


async def browser_right_click(
    engine: PlaywrightEngine,
    x: float | None = None,
    y: float | None = None,
    selector: str | None = None,
    context_id: str = PlaywrightEngine.DEFAULT_CONTEXT,
) -> BrowserObservation:
    """Right-click at a coordinate or element."""
    try:
        if engine._use_external_browser:
            params: dict[str, Any] = {}
            if x is not None: params["x"] = x
            if y is not None: params["y"] = y
            result = await engine._rpc_direct("browser.rightClick", params)
        else:
            page = await engine.open_page(context_id)
            if selector:
                await page.click(selector, button="right")
            elif x is not None and y is not None:
                await page.mouse.click(x, y, button="right")
            result = {"clicked": True}
        return BrowserObservation(action="browser_right_click", extra=result or {})
    except Exception as exc:
        return BrowserObservation(action="browser_right_click", error=str(exc))


# ── Phase 2: Touch ────────────────────────────────────────────────────────────

async def browser_touch_tap(
    engine: PlaywrightEngine,
    x: float,
    y: float,
    context_id: str = PlaywrightEngine.DEFAULT_CONTEXT,
) -> BrowserObservation:
    """Simulate a touch tap at the given coordinates (CDP touch events)."""
    try:
        if engine._use_external_browser:
            result = await engine._rpc_direct("browser.touchTap", {"x": x, "y": y})
        else:
            page = await engine.open_page(context_id)
            await page.tap_point(x, y)  # type: ignore[attr-defined]
            result = {"tapped": True}
        return BrowserObservation(action="browser_touch_tap", extra=result or {})
    except Exception as exc:
        return BrowserObservation(action="browser_touch_tap", error=str(exc))


async def browser_touch_pinch_zoom(
    engine: PlaywrightEngine,
    center_x: float = 400,
    center_y: float = 400,
    from_scale: float = 1.0,
    to_scale: float = 2.0,
    steps: int = 20,
    context_id: str = PlaywrightEngine.DEFAULT_CONTEXT,
) -> BrowserObservation:
    """Simulate a pinch-to-zoom gesture via multi-touch CDP events."""
    try:
        if engine._use_external_browser:
            result = await engine._rpc_direct("browser.touchPinchZoom", {
                "centerX": center_x, "centerY": center_y,
                "fromScale": from_scale, "toScale": to_scale, "steps": steps,
            })
        else:
            result = {"zoomed": False, "reason": "Native Playwright does not support touch pinch — use Julius Browser."}
        return BrowserObservation(action="browser_touch_pinch_zoom", extra=result or {})
    except Exception as exc:
        return BrowserObservation(action="browser_touch_pinch_zoom", error=str(exc))


async def browser_touch_swipe(
    engine: PlaywrightEngine,
    from_x: float,
    from_y: float,
    to_x: float,
    to_y: float,
    steps: int = 20,
    duration_ms: int = 300,
    context_id: str = PlaywrightEngine.DEFAULT_CONTEXT,
) -> BrowserObservation:
    """Simulate a touch swipe gesture via CDP touch events."""
    try:
        if engine._use_external_browser:
            result = await engine._rpc_direct("browser.touchSwipe", {
                "fromX": from_x, "fromY": from_y, "toX": to_x, "toY": to_y,
                "steps": steps, "durationMs": duration_ms,
            })
        else:
            result = {"swiped": False, "reason": "Native Playwright does not support CDP touch swipe — use Julius Browser."}
        return BrowserObservation(action="browser_touch_swipe", extra=result or {})
    except Exception as exc:
        return BrowserObservation(action="browser_touch_swipe", error=str(exc))


# ── Phase 1: Dialogs ──────────────────────────────────────────────────────────

async def browser_accept_dialog(
    engine: PlaywrightEngine,
    prompt_text: str = "",
    context_id: str = PlaywrightEngine.DEFAULT_CONTEXT,
) -> BrowserObservation:
    """Configure the next dialog (alert/confirm/prompt) to be accepted."""
    try:
        if engine._use_external_browser:
            result = await engine._rpc_direct("browser.acceptDialog", {"promptText": prompt_text})
        else:
            page = await engine.open_page(context_id)
            page.once("dialog", lambda d: asyncio.create_task(d.accept(prompt_text)))
            result = {"set": True}
        return BrowserObservation(action="browser_accept_dialog", extra=result or {})
    except Exception as exc:
        return BrowserObservation(action="browser_accept_dialog", error=str(exc))


async def browser_dismiss_dialog(
    engine: PlaywrightEngine,
    context_id: str = PlaywrightEngine.DEFAULT_CONTEXT,
) -> BrowserObservation:
    """Configure the next dialog to be dismissed."""
    try:
        if engine._use_external_browser:
            result = await engine._rpc_direct("browser.dismissDialog", {})
        else:
            page = await engine.open_page(context_id)
            page.once("dialog", lambda d: asyncio.create_task(d.dismiss()))
            result = {"set": True}
        return BrowserObservation(action="browser_dismiss_dialog", extra=result or {})
    except Exception as exc:
        return BrowserObservation(action="browser_dismiss_dialog", error=str(exc))


async def browser_set_dialog_override(
    engine: PlaywrightEngine,
    override: dict | None = None,
    context_id: str = PlaywrightEngine.DEFAULT_CONTEXT,
) -> BrowserObservation:
    """Set a persistent dialog override. Pass None to clear."""
    try:
        result = await engine._rpc_direct("browser.setDialogOverride", {"override": override})
        return BrowserObservation(action="browser_set_dialog_override", extra=result or {})
    except Exception as exc:
        return BrowserObservation(action="browser_set_dialog_override", error=str(exc))


# ── Phase 1: Emulation ────────────────────────────────────────────────────────

async def browser_set_geolocation(
    engine: PlaywrightEngine,
    latitude: float,
    longitude: float,
    accuracy: float = 1.0,
    context_id: str = PlaywrightEngine.DEFAULT_CONTEXT,
) -> BrowserObservation:
    """Override the browser's geolocation position."""
    try:
        if engine._use_external_browser:
            result = await engine._rpc_direct("browser.setGeolocation", {
                "latitude": latitude, "longitude": longitude, "accuracy": accuracy,
            })
        else:
            record = await engine.ensure_context(context_id)
            await record.context.set_geolocation({"latitude": latitude, "longitude": longitude, "accuracy": accuracy})
            result = {"success": True}
        return BrowserObservation(action="browser_set_geolocation", extra=result or {})
    except Exception as exc:
        return BrowserObservation(action="browser_set_geolocation", error=str(exc))


async def browser_clear_geolocation(
    engine: PlaywrightEngine,
    context_id: str = PlaywrightEngine.DEFAULT_CONTEXT,
) -> BrowserObservation:
    """Clear geolocation override."""
    try:
        if engine._use_external_browser:
            result = await engine._rpc_direct("browser.clearGeolocation", {})
        else:
            record = await engine.ensure_context(context_id)
            await record.context.set_geolocation(None)  # type: ignore[arg-type]
            result = {"success": True}
        return BrowserObservation(action="browser_clear_geolocation", extra=result or {})
    except Exception as exc:
        return BrowserObservation(action="browser_clear_geolocation", error=str(exc))


async def browser_set_device_metrics(
    engine: PlaywrightEngine,
    width: int = 1280,
    height: int = 800,
    device_scale_factor: float = 1.0,
    mobile: bool = False,
    has_touch: bool = False,
    context_id: str = PlaywrightEngine.DEFAULT_CONTEXT,
) -> BrowserObservation:
    """Override viewport size and device scaling via CDP Emulation domain."""
    try:
        if engine._use_external_browser:
            result = await engine._rpc_direct("browser.setDeviceMetrics", {
                "width": width, "height": height, "deviceScaleFactor": device_scale_factor,
                "mobile": mobile, "hasTouch": has_touch,
            })
        else:
            page = await engine.open_page(context_id)
            await page.set_viewport_size({"width": width, "height": height})
            result = {"success": True}
        return BrowserObservation(action="browser_set_device_metrics", extra=result or {})
    except Exception as exc:
        return BrowserObservation(action="browser_set_device_metrics", error=str(exc))


async def browser_set_timezone(
    engine: PlaywrightEngine,
    timezone_id: str,
    context_id: str = PlaywrightEngine.DEFAULT_CONTEXT,
) -> BrowserObservation:
    """Override the browser's timezone (e.g. 'America/New_York')."""
    try:
        if engine._use_external_browser:
            result = await engine._rpc_direct("browser.setTimezone", {"timezoneId": timezone_id})
        else:
            record = await engine.ensure_context(context_id)
            await record.context.set_extra_http_headers({})  # no-op; timezone not directly supported
            result = {"success": True, "note": "Timezone override requires CDP. Use Julius Browser for full support."}
        return BrowserObservation(action="browser_set_timezone", extra=result or {})
    except Exception as exc:
        return BrowserObservation(action="browser_set_timezone", error=str(exc))


async def browser_set_permissions(
    engine: PlaywrightEngine,
    allow: list[str] | None = None,
    deny: list[str] | None = None,
    context_id: str = PlaywrightEngine.DEFAULT_CONTEXT,
) -> BrowserObservation:
    """Grant or revoke browser permissions (e.g. 'geolocation', 'camera')."""
    try:
        if engine._use_external_browser:
            result = await engine._rpc_direct("browser.setPermissions", {
                "allow": allow or [], "deny": deny or [],
            })
        else:
            record = await engine.ensure_context(context_id)
            if allow:
                await record.context.grant_permissions(allow)
            result = {"success": True}
        return BrowserObservation(action="browser_set_permissions", extra=result or {})
    except Exception as exc:
        return BrowserObservation(action="browser_set_permissions", error=str(exc))


async def browser_set_extra_headers(
    engine: PlaywrightEngine,
    headers: dict[str, str],
    context_id: str = PlaywrightEngine.DEFAULT_CONTEXT,
) -> BrowserObservation:
    """Set extra HTTP headers sent with every request."""
    try:
        if engine._use_external_browser:
            result = await engine._rpc_direct("browser.setExtraHTTPHeaders", {"headers": headers})
        else:
            record = await engine.ensure_context(context_id)
            await record.context.set_extra_http_headers(headers)
            result = {"set": True}
        return BrowserObservation(action="browser_set_extra_headers", extra=result or {})
    except Exception as exc:
        return BrowserObservation(action="browser_set_extra_headers", error=str(exc))


# ── Phase 5: Network Interception ─────────────────────────────────────────────

async def browser_enable_fetch(
    engine: PlaywrightEngine,
    url_patterns: list[str] | None = None,
    context_id: str = PlaywrightEngine.DEFAULT_CONTEXT,
) -> BrowserObservation:
    """Enable CDP Fetch domain to intercept network requests."""
    try:
        result = await engine._rpc_direct("browser.enableFetch", {"urlPatterns": url_patterns or []})
        return BrowserObservation(action="browser_enable_fetch", extra=result or {})
    except Exception as exc:
        return BrowserObservation(action="browser_enable_fetch", error=str(exc))


async def browser_disable_fetch(
    engine: PlaywrightEngine,
    context_id: str = PlaywrightEngine.DEFAULT_CONTEXT,
) -> BrowserObservation:
    """Disable CDP Fetch domain interception."""
    try:
        result = await engine._rpc_direct("browser.disableFetch", {})
        return BrowserObservation(action="browser_disable_fetch", extra=result or {})
    except Exception as exc:
        return BrowserObservation(action="browser_disable_fetch", error=str(exc))


async def browser_route_fulfill(
    engine: PlaywrightEngine,
    request_id: str,
    status: int = 200,
    headers: dict[str, str] | None = None,
    body: str = "",
    context_id: str = PlaywrightEngine.DEFAULT_CONTEXT,
) -> BrowserObservation:
    """Fulfill a pending intercepted request with a mock response."""
    try:
        result = await engine._rpc_direct("browser.routeFulfill", {
            "requestId": request_id, "status": status,
            "headers": headers or {}, "body": body,
        })
        return BrowserObservation(action="browser_route_fulfill", extra=result or {})
    except Exception as exc:
        return BrowserObservation(action="browser_route_fulfill", error=str(exc))


async def browser_route_abort(
    engine: PlaywrightEngine,
    request_id: str,
    error_reason: str = "BlockedByClient",
    context_id: str = PlaywrightEngine.DEFAULT_CONTEXT,
) -> BrowserObservation:
    """Abort (block) a pending intercepted request."""
    try:
        result = await engine._rpc_direct("browser.routeAbort", {
            "requestId": request_id, "errorReason": error_reason,
        })
        return BrowserObservation(action="browser_route_abort", extra=result or {})
    except Exception as exc:
        return BrowserObservation(action="browser_route_abort", error=str(exc))


async def browser_route_continue(
    engine: PlaywrightEngine,
    request_id: str,
    url: str | None = None,
    method: str | None = None,
    headers: dict[str, str] | None = None,
    post_data: str | None = None,
    context_id: str = PlaywrightEngine.DEFAULT_CONTEXT,
) -> BrowserObservation:
    """Continue a pending intercepted request, optionally modifying it."""
    try:
        params: dict[str, Any] = {"requestId": request_id}
        if url: params["url"] = url
        if method: params["method"] = method
        if headers: params["headers"] = headers
        if post_data: params["postData"] = post_data
        result = await engine._rpc_direct("browser.routeContinue", params)
        return BrowserObservation(action="browser_route_continue", extra=result or {})
    except Exception as exc:
        return BrowserObservation(action="browser_route_continue", error=str(exc))


# ── Phase 7: Screenshots & PDF ────────────────────────────────────────────────

async def browser_screenshot_element(
    engine: PlaywrightEngine,
    selector: str | None = None,
    node_id: int | None = None,
    save_path: str | None = None,
    context_id: str = PlaywrightEngine.DEFAULT_CONTEXT,
) -> BrowserObservation:
    """Screenshot a specific element by selector or node ID."""
    try:
        if engine._use_external_browser:
            params: dict[str, Any] = {}
            if node_id: params["nodeId"] = node_id
            result = await engine._rpc_direct("browser.screenshotElement", params)
        else:
            page = await engine.open_page(context_id)
            el = await page.query_selector(selector or "body")
            data = await el.screenshot(path=save_path)
            import base64
            result = {"success": True, "mimeType": "image/png", "dataBase64": base64.b64encode(data).decode()}
        return BrowserObservation(action="browser_screenshot_element", extra=result or {})
    except Exception as exc:
        return BrowserObservation(action="browser_screenshot_element", error=str(exc))


async def browser_print_to_pdf(
    engine: PlaywrightEngine,
    save_path: str | None = None,
    options: dict | None = None,
    context_id: str = PlaywrightEngine.DEFAULT_CONTEXT,
) -> BrowserObservation:
    """Print the current page to a PDF file."""
    try:
        if engine._use_external_browser:
            result = await engine._rpc_direct("browser.printToPdf", {"options": options or {}})
        else:
            page = await engine.open_page(context_id)
            abs_path = str(Path(engine.workspace_root) / save_path) if save_path else None
            data = await page.pdf(path=abs_path, **(options or {}))
            import base64
            result = {"success": True, "mimeType": "application/pdf", "dataBase64": base64.b64encode(data).decode()}
        return BrowserObservation(action="browser_print_to_pdf", extra=result or {})
    except Exception as exc:
        return BrowserObservation(action="browser_print_to_pdf", error=str(exc))


# ── Phase 6: Cookies & Storage ────────────────────────────────────────────────

async def browser_get_cookies(
    engine: PlaywrightEngine,
    url: str | None = None,
    context_id: str = PlaywrightEngine.DEFAULT_CONTEXT,
) -> BrowserObservation:
    """Get all cookies, optionally filtered by URL."""
    try:
        if engine._use_external_browser:
            result = await engine._rpc_direct("browser.getCookies", {"url": url} if url else {})
        else:
            record = await engine.ensure_context(context_id)
            cookies = await record.context.cookies(urls=[url] if url else None)
            result = {"success": True, "cookies": cookies}
        return BrowserObservation(action="browser_get_cookies", extra=result or {})
    except Exception as exc:
        return BrowserObservation(action="browser_get_cookies", error=str(exc))


async def browser_set_cookie(
    engine: PlaywrightEngine,
    name: str,
    value: str,
    url: str | None = None,
    domain: str | None = None,
    path: str = "/",
    context_id: str = PlaywrightEngine.DEFAULT_CONTEXT,
) -> BrowserObservation:
    """Set a browser cookie."""
    try:
        cookie: dict[str, Any] = {"name": name, "value": value, "path": path}
        if url: cookie["url"] = url
        if domain: cookie["domain"] = domain
        if engine._use_external_browser:
            result = await engine._rpc_direct("browser.setCookie", cookie)
        else:
            record = await engine.ensure_context(context_id)
            await record.context.add_cookies([cookie])
            result = {"success": True}
        return BrowserObservation(action="browser_set_cookie", extra=result or {})
    except Exception as exc:
        return BrowserObservation(action="browser_set_cookie", error=str(exc))


async def browser_remove_cookie(
    engine: PlaywrightEngine,
    name: str,
    url: str,
    context_id: str = PlaywrightEngine.DEFAULT_CONTEXT,
) -> BrowserObservation:
    """Remove a specific cookie by name and URL."""
    try:
        if engine._use_external_browser:
            result = await engine._rpc_direct("browser.removeCookie", {"name": name, "url": url})
        else:
            record = await engine.ensure_context(context_id)
            await record.context.clear_cookies()
            result = {"success": True, "note": "Native Playwright clears all cookies; filter by name not supported."}
        return BrowserObservation(action="browser_remove_cookie", extra=result or {})
    except Exception as exc:
        return BrowserObservation(action="browser_remove_cookie", error=str(exc))


async def browser_clear_cookies(
    engine: PlaywrightEngine,
    context_id: str = PlaywrightEngine.DEFAULT_CONTEXT,
) -> BrowserObservation:
    """Clear all cookies for the session."""
    try:
        if engine._use_external_browser:
            result = await engine._rpc_direct("browser.clearCookies", {})
        else:
            record = await engine.ensure_context(context_id)
            await record.context.clear_cookies()
            result = {"success": True}
        return BrowserObservation(action="browser_clear_cookies", extra=result or {})
    except Exception as exc:
        return BrowserObservation(action="browser_clear_cookies", error=str(exc))


async def browser_clear_storage(
    engine: PlaywrightEngine,
    storages: list[str] | None = None,
    context_id: str = PlaywrightEngine.DEFAULT_CONTEXT,
) -> BrowserObservation:
    """Clear browser storage (localStorage, sessionStorage, indexedDB, etc.)."""
    try:
        if engine._use_external_browser:
            result = await engine._rpc_direct("browser.clearStorage", {"storages": storages})
        else:
            page = await engine.open_page(context_id)
            await page.evaluate("() => { localStorage.clear(); sessionStorage.clear(); }")
            result = {"success": True}
        return BrowserObservation(action="browser_clear_storage", extra=result or {})
    except Exception as exc:
        return BrowserObservation(action="browser_clear_storage", error=str(exc))


async def browser_get_local_storage(
    engine: PlaywrightEngine,
    context_id: str = PlaywrightEngine.DEFAULT_CONTEXT,
) -> BrowserObservation:
    """Read all localStorage key-value pairs from the current page."""
    try:
        if engine._use_external_browser:
            result = await engine._rpc_direct("browser.getLocalStorage", {})
        else:
            page = await engine.open_page(context_id)
            data = await page.evaluate(
                "(function(){const o={};for(let i=0;i<localStorage.length;i++){const k=localStorage.key(i);o[k]=localStorage.getItem(k);}return o;})()"
            )
            result = {"storage": data}
        return BrowserObservation(action="browser_get_local_storage", extra=result or {})
    except Exception as exc:
        return BrowserObservation(action="browser_get_local_storage", error=str(exc))


async def browser_set_local_storage(
    engine: PlaywrightEngine,
    items: dict[str, str],
    context_id: str = PlaywrightEngine.DEFAULT_CONTEXT,
) -> BrowserObservation:
    """Set multiple localStorage key-value pairs on the current page."""
    try:
        if engine._use_external_browser:
            result = await engine._rpc_direct("browser.setLocalStorage", {"items": items})
        else:
            page = await engine.open_page(context_id)
            await page.evaluate(
                f"(function(items){{for(const [k,v] of Object.entries(items)){{localStorage.setItem(k,v);}}}}({{}}))",
                items
            )
            result = {"set": True}
        return BrowserObservation(action="browser_set_local_storage", extra=result or {})
    except Exception as exc:
        return BrowserObservation(action="browser_set_local_storage", error=str(exc))




# ── Dispatch table ────────────────────────────────────────────────────────────

#: Maps action name → async callable (engine, **args) → BrowserObservation
BROWSER_ACTIONS: dict[str, Any] = {
    "browser_navigate": browser_navigate,
    "browser_click": browser_click,
    "browser_type": browser_type,
    "browser_select": browser_select,
    "browser_hover": browser_hover,
    "browser_scroll": browser_scroll,
    "browser_press": browser_press,
    "browser_clear": browser_clear,
    "browser_wait": browser_wait,
    "browser_get_snapshot": browser_get_snapshot,
    "browser_get_network_log": browser_get_network_log,
    "browser_get_console_log": browser_get_console_log,
    "browser_eval_js": browser_eval_js,
    "browser_extract": browser_extract,
    "browser_new_context": browser_new_context,
    "browser_close_context": browser_close_context,
    "browser_save_session": browser_save_session,
    "browser_load_session": browser_load_session,
    "browser_new_tab": browser_new_tab,
    "browser_switch_tab": browser_switch_tab,
    "browser_close_tab": browser_close_tab,
    "browser_upload_file": browser_upload_file,
    "browser_expect_download": browser_expect_download,
    "browser_start_trace": browser_start_trace,
    "browser_stop_trace": browser_stop_trace,
    "browser_start_har": browser_start_har,
    "browser_stop_har": browser_stop_har,
    # ── Phase 1-6 new actions ─────────────────────────────────────────────────
    "browser_drag_to": browser_drag_to,
    "browser_double_click": browser_double_click,
    "browser_right_click": browser_right_click,
    "browser_touch_tap": browser_touch_tap,
    "browser_touch_pinch_zoom": browser_touch_pinch_zoom,
    "browser_touch_swipe": browser_touch_swipe,
    "browser_wait_for_load": browser_wait_for_load,
    "browser_wait_for_selector": browser_wait_for_selector,
    "browser_accept_dialog": browser_accept_dialog,
    "browser_dismiss_dialog": browser_dismiss_dialog,
    "browser_set_dialog_override": browser_set_dialog_override,
    "browser_set_geolocation": browser_set_geolocation,
    "browser_clear_geolocation": browser_clear_geolocation,
    "browser_set_device_metrics": browser_set_device_metrics,
    "browser_set_timezone": browser_set_timezone,
    "browser_set_permissions": browser_set_permissions,
    "browser_set_extra_headers": browser_set_extra_headers,
    "browser_enable_fetch": browser_enable_fetch,
    "browser_disable_fetch": browser_disable_fetch,
    "browser_route_fulfill": browser_route_fulfill,
    "browser_route_abort": browser_route_abort,
    "browser_route_continue": browser_route_continue,
    "browser_screenshot_element": browser_screenshot_element,
    "browser_print_to_pdf": browser_print_to_pdf,
    "browser_get_cookies": browser_get_cookies,
    "browser_set_cookie": browser_set_cookie,
    "browser_remove_cookie": browser_remove_cookie,
    "browser_clear_cookies": browser_clear_cookies,
    "browser_clear_storage": browser_clear_storage,
    "browser_get_local_storage": browser_get_local_storage,
    "browser_set_local_storage": browser_set_local_storage,
    "browser_reload": browser_reload,
    "browser_go_back": browser_go_back,
    "browser_go_forward": browser_go_forward,
}


async def dispatch(engine: PlaywrightEngine, action: str, args: dict) -> BrowserObservation:
    """Route a browser action name + args to the correct async function."""
    fn = BROWSER_ACTIONS.get(action)
    if fn is None:
        return BrowserObservation(
            action=action,
            error=f"Unknown browser action '{action}'. Available: {', '.join(sorted(BROWSER_ACTIONS))}",
        )
    try:
        await engine.ensure_started()
        sig = inspect.signature(fn)
        filtered_args = {}
        has_kwargs = any(p.kind == p.VAR_KEYWORD for p in sig.parameters.values())

        for k, v in args.items():
            if has_kwargs or k in sig.parameters:
                filtered_args[k] = v

        return await fn(engine, **filtered_args)
    except TypeError as exc:
        return BrowserObservation(
            action=action,
            error=f"Invalid arguments for '{action}': {exc}",
        )
    except Exception as exc:
        return BrowserObservation(action=action, error=str(exc))
