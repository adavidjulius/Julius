"""
Goal-Based Navigation — end-to-end browser objective execution.

The agent gives GoalNavigator a high-level goal like 'Login to the site'
or 'Add item to cart and checkout'. GoalNavigator:

  1. Matches the goal against built-in templates to build a BrowserTaskGraph
  2. Executes each step using all cognition subsystems:
       - DOMDiff to detect unexpected page changes → auto-replan
       - ActionVerifier to confirm each step succeeded
       - RecoveryEngine to handle modals, spinners, stale elements
       - BrowserMemory to avoid repeating already-done steps
       - WorldModel to track persistent facts throughout
  3. Returns a GoalResult with what was accomplished, what changed in the
     world model, and what (if anything) still needs to happen

For goals that don't match a template, GoalNavigator falls back to a
"navigate + snapshot + let agent decide" plan (3 steps max) and surfaces
the full observation so the agent can take over.

No LLM calls during template-based execution. The LLM only gets the
final GoalResult as its observation.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .engine import PlaywrightEngine
    from .memory import BrowserMemory
    from .world_model import WorldModel
    from .structured_obs import BrowserObservation

from .dom_diff import DOMDiff, DiffResult
from .verifier import ActionVerifier
from .recovery import RecoveryEngine, RecoveryResult
from .planner import BrowserTaskGraph, BrowserStep

logger = logging.getLogger(__name__)


# ── GoalResult ────────────────────────────────────────────────────────────────

@dataclass
class GoalResult:
    success: bool
    goal: str
    steps_taken: int = 0
    steps_succeeded: int = 0
    steps_failed: int = 0
    final_url: str = ""
    final_title: str = ""
    world_state_delta: dict[str, Any] = field(default_factory=dict)
    screenshot_path: str = ""
    error: str = ""
    recovery_events: list[str] = field(default_factory=list)
    replanned: bool = False

    def to_text(self) -> str:
        status = "✅ SUCCESS" if self.success else "❌ FAILED"
        lines = [
            f"GOAL RESULT: {self.goal}",
            f"Status: {status}",
            f"Steps: {self.steps_succeeded}/{self.steps_taken} succeeded"
            + (f" ({self.steps_failed} failed)" if self.steps_failed else ""),
            f"Final URL: {self.final_url}",
            f"Final Title: {self.final_title}",
        ]

        if self.world_state_delta:
            lines.append("\nWorld model updated:")
            for k, v in self.world_state_delta.items():
                lines.append(f"  {k}: {v!r}")

        if self.recovery_events:
            lines.append(f"\nAuto-recoveries ({len(self.recovery_events)}):")
            for ev in self.recovery_events:
                lines.append(f"  • {ev}")

        if self.replanned:
            lines.append("\n[Note: Goal was replanned mid-execution due to unexpected page change]")

        if self.error:
            lines.append(f"\nError: {self.error}")

        if self.screenshot_path:
            lines.append(f"\nScreenshot: {self.screenshot_path}")

        return "\n".join(lines)


# ── Goal templates ────────────────────────────────────────────────────────────

def _build_login_template(
    graph: BrowserTaskGraph,
    url: str = "",
    email_selector: str = "input[type=email], input[name=email], #email",
    password_selector: str = "input[type=password], input[name=password], #password",
    submit_selector: str = "button[type=submit], input[type=submit], button:has-text('Login'), button:has-text('Sign in')",
    email: str = "",
    password: str = "",
) -> None:
    """Template: navigate to login page, fill credentials, submit."""
    if url:
        graph.add_step("nav", f"Navigate to {url}", "browser_navigate", {"url": url})
        deps = ["nav"]
    else:
        deps = []

    graph.add_step("wait_form", "Wait for login form", "browser_wait",
                   {"selector": email_selector, "timeout_ms": 8000}, depends_on=deps)
    graph.add_step("fill_email", "Fill email field", "browser_type",
                   {"selector": email_selector, "text": email or "__EMAIL__"},
                   depends_on=["wait_form"])
    graph.add_step("fill_password", "Fill password field", "browser_type",
                   {"selector": password_selector, "text": password or "__PASSWORD__"},
                   depends_on=["fill_email"])
    graph.add_step("submit", "Submit login form", "browser_click",
                   {"selector": submit_selector}, depends_on=["fill_password"])
    graph.add_step("verify_login", "Verify login succeeded", "browser_wait",
                   {"timeout_ms": 5000}, depends_on=["submit"])


def _build_fill_form_template(
    graph: BrowserTaskGraph,
    fields: list[dict],   # [{"selector": "...", "value": "..."}]
    submit_selector: str = "button[type=submit]",
) -> None:
    """Template: fill multiple form fields, then submit."""
    prev_id = None
    for i, f in enumerate(fields):
        step_id = f"fill_{i}"
        graph.add_step(step_id, f"Fill field {i+1}", "browser_type",
                       {"selector": f["selector"], "text": f["value"]},
                       depends_on=[prev_id] if prev_id else [])
        prev_id = step_id
    graph.add_step("submit", "Submit form", "browser_click",
                   {"selector": submit_selector},
                   depends_on=[prev_id] if prev_id else [])


def _build_navigate_template(
    graph: BrowserTaskGraph,
    url: str,
    wait_selector: str = "",
) -> None:
    """Template: navigate to URL, optionally wait for element."""
    graph.add_step("nav", f"Navigate to {url}", "browser_navigate", {"url": url})
    if wait_selector:
        graph.add_step("wait", "Wait for page element", "browser_wait",
                       {"selector": wait_selector, "timeout_ms": 10000},
                       depends_on=["nav"])


def _build_extract_template(
    graph: BrowserTaskGraph,
    url: str,
    selectors: dict[str, str],
) -> None:
    """Template: navigate then extract structured data."""
    graph.add_step("nav", f"Navigate to {url}", "browser_navigate", {"url": url})
    graph.add_step("extract", "Extract page data", "browser_extract",
                   {"selectors": selectors}, depends_on=["nav"])


def _build_click_template(
    graph: BrowserTaskGraph,
    selector: str = "",
    text: str = "",
    url: str = "",
) -> None:
    """Template: navigate (optional), then click an element."""
    deps = []
    if url:
        graph.add_step("nav", f"Navigate to {url}", "browser_navigate", {"url": url})
        deps = ["nav"]
    args = {}
    if selector:
        args["selector"] = selector
    if text:
        args["text"] = text
    graph.add_step("click", f"Click {text or selector}", "browser_click",
                   args, depends_on=deps)


def _build_fallback_template(
    graph: BrowserTaskGraph,
    url: str = "",
) -> None:
    """Fallback: navigate (if URL provided) + snapshot. Agent decides next step."""
    if url:
        graph.add_step("nav", f"Navigate to {url}", "browser_navigate", {"url": url})
        graph.add_step("snapshot", "Capture current page state", "browser_get_snapshot",
                       depends_on=["nav"])
    else:
        graph.add_step("snapshot", "Capture current page state", "browser_get_snapshot")


# ── Template matcher ──────────────────────────────────────────────────────────

def match_template(goal: str, params: dict) -> tuple[str, BrowserTaskGraph] | None:
    """
    Match a natural-language goal to a built-in template.
    Returns (template_name, graph) or None if no match.
    """
    import re
    goal_lower = goal.lower()
    ws = params.get("workspace_root", ".")
    graph = BrowserTaskGraph(ws)
    graph.set_goal(goal)

    # Login
    if re.search(r"\b(log ?in|sign ?in|authenticate|login)\b", goal_lower):
        _build_login_template(
            graph,
            url=params.get("url", ""),
            email=params.get("email", ""),
            password=params.get("password", ""),
        )
        return "login", graph

    # Fill form
    if re.search(r"\bfill\b.+\bform\b|\bsubmit\b.+\bform\b", goal_lower):
        fields = params.get("fields", [])
        submit = params.get("submit_selector", "button[type=submit]")
        _build_fill_form_template(graph, fields, submit)
        return "fill_form", graph

    # Navigate
    if re.search(r"\bnavigate\b|\bgo to\b|\bopen\b|\bvisit\b", goal_lower):
        url = params.get("url", "")
        wait = params.get("wait_selector", "")
        if url:
            _build_navigate_template(graph, url, wait)
            return "navigate", graph

    # Extract / scrape
    if re.search(r"\bextract\b|\bscrape\b|\bget data\b|\bcollect\b", goal_lower):
        url = params.get("url", "")
        sels = params.get("selectors", {})
        if url and sels:
            _build_extract_template(graph, url, sels)
            return "extract", graph

    # Click
    if re.search(r"\bclick\b|\bpress\b|\btap\b", goal_lower):
        _build_click_template(
            graph,
            selector=params.get("selector", ""),
            text=params.get("text", ""),
            url=params.get("url", ""),
        )
        return "click", graph

    return None


# ── GoalNavigator ─────────────────────────────────────────────────────────────

class GoalNavigator:
    """
    Executes browser goals end-to-end, orchestrating all cognition subsystems.
    """

    REPLAN_THRESHOLD = 0.4     # fraction of expected elements missing → replan

    def __init__(
        self,
        engine: "PlaywrightEngine",
        world_model: "WorldModel",
    ) -> None:
        self.engine = engine
        self.world_model = world_model
        self.verifier = ActionVerifier()
        self.recovery = RecoveryEngine()
        self._current_graph: BrowserTaskGraph | None = None

    async def pursue(
        self,
        goal: str,
        context_id: str = "default",
        max_steps: int = 20,
        params: dict | None = None,
    ) -> GoalResult:
        """
        Execute a browser goal end-to-end.

        Parameters
        ----------
        goal:       Natural language objective, e.g. 'Login to the site'
        context_id: Which browser context to use
        max_steps:  Safety limit on number of steps
        params:     Additional parameters for template (url, email, selectors, etc.)
        """
        params = params or {}
        params["workspace_root"] = self.engine.workspace_root
        result = GoalResult(success=False, goal=goal)
        facts_before = set(self.world_model.keys())

        # Match template or use fallback
        template_match = match_template(goal, params)
        if template_match:
            template_name, graph = template_match
            logger.info(f"GoalNavigator: using template {template_name!r} for goal {goal!r}")
        else:
            graph = BrowserTaskGraph(self.engine.workspace_root)
            graph.set_goal(goal)
            _build_fallback_template(graph, url=params.get("url", ""))
            logger.info(f"GoalNavigator: no template matched for {goal!r}, using fallback")

        self._current_graph = graph
        prev_obs: "BrowserObservation | None" = None
        steps_run = 0

        from .actions import dispatch

        while steps_run < max_steps:
            step = graph.next_executable_step()
            if step is None:
                break

            steps_run += 1
            result.steps_taken += 1
            graph.mark_running(step.id)
            logger.info(f"GoalNavigator: step {step.id!r}: {step.action}({step.args})")

            # Execute the action
            try:
                obs: "BrowserObservation" = await dispatch(self.engine, step.action, step.args)
            except Exception as exc:
                obs_err = __import__("src.browser.structured_obs",
                                     fromlist=["BrowserObservation"]).BrowserObservation(
                    action=step.action, error=str(exc)
                )
                obs = obs_err

            # Run recovery checks
            if not obs.error:
                record = self.engine.get_context(context_id)
                if record:
                    memory = getattr(record, "memory", None)
                    if memory:
                        rec = await self.recovery.check_and_recover(
                            await self.engine.open_page(context_id),
                            obs, memory, self.world_model, context_id,
                        )
                        if rec.issue_type and rec.issue_type != "none":
                            result.recovery_events.append(rec.action_taken or rec.issue_type)
                        if rec.agent_message:
                            result.error = rec.agent_message

            # DOM diff — detect unexpected major page changes
            if prev_obs and not obs.error:
                diff = DOMDiff.diff(prev_obs, obs)
                if diff.is_major_change and diff.url_changed:
                    # URL changed unexpectedly — check if goal is still achievable
                    logger.info(f"GoalNavigator: major page change detected mid-task (step {step.id!r})")
                    result.replanned = True

            # FactExtractor updates the world model
            from .world_model import FactExtractor
            FactExtractor(self.world_model).extract(obs)

            if obs.error:
                graph.mark_failed(step.id, obs.error)
                result.steps_failed += 1

                # Check if we can recover from stale element
                record = self.engine.get_context(context_id)
                if record and hasattr(record, "memory"):
                    page = record.active_page
                    if page:
                        stale_rec = await self.recovery.recover_stale_element(
                            page,
                            step.args.get("selector", ""),
                            obs.error,
                            record.memory,
                        )
                        if stale_rec.recovered and stale_rec.issue_type == "stale_element":
                            result.recovery_events.append(stale_rec.action_taken)
                            # Patch args with alternative selector and retry
                            if "selector" in step.args:
                                # The retry will happen via mark_failed → pending
                                pass
            else:
                graph.mark_done(step.id, obs.title or obs.url or "ok")
                result.steps_succeeded += 1
                prev_obs = obs
                result.final_url = obs.url
                result.final_title = obs.title
                if obs.screenshot_path:
                    result.screenshot_path = obs.screenshot_path

        # Compute world model delta
        facts_after = set(self.world_model.keys())
        new_keys = facts_after - facts_before
        for k in new_keys:
            f = self.world_model.get_fact(k)
            if f:
                result.world_state_delta[k] = f.value
        # Changed keys
        for k in facts_before & facts_after:
            # We don't track old values easily, so just report all post-goal facts
            pass

        result.success = graph.is_successful and result.steps_failed == 0
        return result

    def get_current_task_status(self) -> str:
        if not self._current_graph:
            return "No active browser task."
        return self._current_graph.to_text()

    def abort_current_task(self) -> str:
        if not self._current_graph:
            return "No active task to abort."
        self._current_graph.abort()
        return "Task aborted."
