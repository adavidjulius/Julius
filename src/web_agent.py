"""
Autonomous web-chat-driven agent loop.

This is the main orchestrator that ties together:
- Observation (workspace state)
- Reasoning (web chat LLM)
- Action execution (bash, file ops, git)
- Safety (confirmation, abort, limits)

Loop: observe → build prompt → send to web chat → parse JSON → safety check → execute → repeat
"""

from __future__ import annotations
from typing import Callable

import asyncio
import json
import logging
import os
import signal
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .action_executor import ActionExecutor, ActionResult
from .agent_config import AgentConfig
from .agent_prompts import (
    SYSTEM_PROMPT,
    VALID_ACTIONS,
    build_error_prompt,
    build_initial_prompt,
    build_step_prompt,
    attempt_json_fix,
    extract_json_block,
    is_json_or_protocol,
    normalize_actions,
    format_batch_results,
)
from .context_injector import build_workspace_context
from src.providers import LLMRouter, ProviderRouter, create_default_router, LLMResponse
from src.telemetry.cost import CostTracker
from .prompt_linter import lint_prompt
from .response_validator import validate_action
from .memory import WorkingStateManager, TaskWorkingState
from .cli.presenter import (
    Spinner,
    render_confirmation_prompt,
    render_final_answer,
    render_error,
)

try:
    from .self_healer import SelfHealer
    _HEALER_AVAILABLE = True
except ImportError:
    _HEALER_AVAILABLE = False


logger = logging.getLogger(__name__)


@dataclass
class StepRecord:
    """Record of a single agent step."""
    step: int
    thought: str
    action: str
    args: dict
    result: str
    success: bool
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    duration_ms: int = 0


@dataclass
class AgentResult:
    """Final result after the agent loop completes."""
    success: bool
    summary: str
    steps: list[StepRecord]
    total_steps: int
    elapsed_seconds: float
    stop_reason: str  # 'done' | 'max_steps' | 'abort' | 'error'

    def as_markdown(self) -> str:
        lines = [
            '# Agent Run Report',
            '',
            f'**Status**: {"✅ Success" if self.success else "❌ Failed"}',
            f'**Stop reason**: {self.stop_reason}',
            f'**Total steps**: {self.total_steps}',
            f'**Elapsed**: {self.elapsed_seconds:.1f}s',
            '',
            '## Summary',
            self.summary,
            '',
            '## Step History',
        ]
        for step in self.steps:
            status = '✅' if step.success else '❌'
            lines.append(f'\n### Step {step.step} — {step.action} {status}')
            lines.append(f'**Thought**: {step.thought}')
            lines.append(f'**Result**: {step.result[:200]}...' if len(step.result) > 200 else f'**Result**: {step.result}')
        return '\n'.join(lines)


class WebAgent:
    """
    Autonomous agent that uses a web chat LLM for reasoning and
    executes real actions on the local machine.
    """

    def __init__(self, config: AgentConfig | None = None, on_event: Callable | None = None,
                 shared_client: Any | None = None, keep_browser_open: bool = True) -> None:
        self.config = config or AgentConfig()
        self.on_event = on_event
        # If a shared client is provided or keep_browser_open is True, stay connected across runs
        self._owns_client = shared_client is None
        self.keep_browser_open = keep_browser_open if keep_browser_open is not None else getattr(self.config, 'keep_browser_open', True)
        self.router = create_default_router(self.config.allowed_directory)
        if hasattr(self.router, "active_provider") and getattr(self.config, "provider", None):
            self.router.active_provider = self.config.provider
        self.client = shared_client if shared_client else self.router
        self.cost_tracker = CostTracker(db_path=str(Path(self.config.allowed_directory) / ".julius" / "cost_stats.db"))
        self.executor = ActionExecutor(
            workspace_root=self.config.allowed_directory,
            max_file_read_lines=self.config.max_file_read_lines,
            max_bash_output_chars=self.config.max_bash_output_chars,
            bash_timeout=self.config.bash_timeout,
            user_role=os.getenv("JULIUS_ROLE", "admin"),
        )

        self._steps: list[StepRecord] = []
        self._aborted: bool = False
        self._abort_listener = None
        self._confirm_future: asyncio.Future[bool] | None = None
        self._host_access_granted: bool = False
        self.working_state_mgr = WorkingStateManager(self.config.allowed_directory)
        self.current_working_state: TaskWorkingState | None = None
        self._current_in_flight_action: str | None = None
        self._current_in_flight_file: str | None = None
        self._is_running: bool = False

    def _is_outside_workspace(self, action_name: str, args: dict) -> bool:
        """Return True if the proposed action targets paths or commands outside the workspace."""
        try:
            ws_root = os.path.realpath(self.config.allowed_directory)
        except Exception:
            return False

        # 1. File actions with path argument
        path_arg = args.get("path") or args.get("file") or args.get("directory")
        if path_arg:
            try:
                expanded = os.path.expanduser(str(path_arg).strip())
                target = os.path.realpath(expanded if os.path.isabs(expanded) else os.path.join(ws_root, expanded))
                if target != ws_root and not target.startswith(ws_root + os.sep):
                    return True
            except Exception:
                pass

        # 2. Bash commands referencing outside paths or host directories
        if action_name == "run_bash":
            cmd = args.get("command", "").strip()
            parts = cmd.split()
            for p in parts:
                clean_p = p.strip(';,"\'&|()<>')
                if clean_p.startswith(("~", "/", "..")):
                    try:
                        exp = os.path.expanduser(clean_p)
                        real_p = os.path.realpath(exp if os.path.isabs(exp) else os.path.join(ws_root, exp))
                        if real_p != ws_root and not real_p.startswith(ws_root + os.sep):
                            if exp in ("/dev/null", "/dev/zero", "/dev/urandom", "/dev/stdin", "/dev/stdout", "/dev/stderr"):
                                continue
                            return True
                    except Exception:
                        return True
            # Also check for host paths outside the workspace
            for h in ("/System", "/Library", "/private/var", "/etc", "/Volumes"):
                if h in cmd and not ws_root.startswith(h):
                    return True

        return False

    def set_execution_mode(self, mode: str) -> None:
        """Dynamically update agent execution mode (Autonomous, Supervised, Manual)."""
        self.config.set_execution_mode(mode)

    async def start_new_chat(self) -> None:
        """Start a fresh chat conversation on the active browser session."""
        self._steps = []
        if self.client and self.client.is_initialized:
            await self.client.start_new_conversation()

    async def close(self) -> None:
        """Close the agent's browser client cleanly."""
        if self.client:
            await self.client.close()

    def _emit(self, event_type: str, **kwargs) -> None:
        """Emit a structured event to the GUI callback if set."""
        if self.on_event:
            try:
                self.on_event({"type": event_type, **kwargs})
            except Exception:
                pass  # Never let a UI callback crash the agent loop

    # ── Main entry point ──────────────────────────────────────────

    async def run(self, task: str, max_steps: int | None = None, image_path: str | None = None) -> AgentResult:
        """
        Run the agent loop until the task is complete or limits are reached.

        Args:
            task: Natural language description of the task to accomplish.
            max_steps: Override the config max_steps.
            image_path: Optional path to an image file (e.g. camera live frame).

        Returns:
            AgentResult with full step history and summary.
        """
        # Finding #10: reject oversized task descriptions before any processing
        MAX_TASK_LENGTH = 50_000  # characters (~12,500 tokens)
        if len(task) > MAX_TASK_LENGTH:
            return AgentResult(
                success=False,
                summary=f"Task description too long ({len(task):,} chars, max {MAX_TASK_LENGTH:,}). Please shorten it.",
                steps=[],
                total_steps=0,
                elapsed_seconds=0.0,
                stop_reason='error',
            )

        self._is_running = True
        self._aborted = False
        effective_max = max_steps if max_steps is not None else self.config.max_steps
        is_unlimited = (effective_max is None or effective_max <= 0)
        start_time = time.time()

        # Step 2: Normalize typos and clean whitespace before the agent loop
        task = lint_prompt(task)

        # Check for explicit user authorization or autonomous mode
        task_lower = task.lower()
        if any(term in task_lower for term in ("admin", "permission", "full access", "uncensored", "authorize", "root", "grant")) or not getattr(self.config, 'confirm_actions', True):
            self._host_access_granted = True

        # Setup
        self._setup_safety()
        spinner = None
        stop_reason = 'error'
        summary = 'Agent execution interrupted.'

        try:
            # Stage 3: Startup resumption check
            resumption_context = await self._handle_startup_resumption(task)

            await self._initialize_llm()

            if self.config.verbose:
                print(f'\n🤖 Julius starting...')
                print(f'   Provider: {self.client.provider_name}')
                print(f'   Task: {task}')
                print(f'   Max steps: {"Unlimited (until complete)" if is_unlimited else effective_max}')
                print(f'   Workspace: {self.config.allowed_directory}')
                print(f'   Confirm actions: {self.config.confirm_actions}')
                print()

            # Build the initial observation with dynamic workspace context (Step 5)
            dir_listing = self.executor.list_directory('.').output
            workspace_ctx = build_workspace_context(self.config.allowed_directory)
            # Use fast, high-performance compact system prompt for all web-chat and local providers
            from .agent_prompts import get_compact_system_prompt
            default_sys_pr = get_compact_system_prompt(self.config.allowed_directory)
            sys_pr = getattr(self, 'system_prompt', None) or default_sys_pr
            
            pk = getattr(self.client, "provider_key", "")
            pn = getattr(self.client, "provider_name", "")
            pk_str = pk if isinstance(pk, str) else ""
            pn_str = pn if isinstance(pn, str) else ""
            is_aifree = "aifree" in pk_str.lower() or "aifree" in pn_str.lower()

            if is_aifree:
                initial_prompt = (
                    f"You are Julius, an autonomous software engineering assistant on macOS.\n"
                    f"Working Directory: {self.config.allowed_directory}\n\n"
                    f"### CURRENT TASK TO EXECUTE:\n"
                    f"**{task}**\n\n"
                    f"Respond with ONLY a JSON block inside triple backticks:\n"
                    f"```json\n"
                    f"{{\n"
                    f'  "thought": "concise reasoning",\n'
                    f'  "action": "action_name",\n'
                    f'  "args": {{ ... }}\n'
                    f"}}\n"
                    f"```\n"
                    f"Core actions: converse (for chat/greetings/direct answers), run_bash (shell commands), read_file, write_file, edit_file, list_dir, done (finished)."
                )
            else:
                # Place user task prominently at the top so web LLMs execute immediately instead of acknowledging the manual
                initial_prompt = (
                    f"### CURRENT TASK TO EXECUTE IMMEDIATELY:\n"
                    f"**{task}**\n\n"
                    f"You are Julius. Execute the task above directly using the appropriate tool action(s). "
                    f"Do NOT simply acknowledge or summarize the operating manual. Start working on the task now.\n\n"
                    f"{build_initial_prompt(task, self.config.allowed_directory, dir_listing)}{resumption_context}\n\n"
                    f"{workspace_ctx}\n\n"
                    f"--- OPERATING SPECIFICATIONS & TOOL REFERENCE ---\n"
                    f"{sys_pr}"
                )
            last_result = '(starting — no previous actions)'

            stop_reason = 'max_steps'
            summary = 'Agent reached maximum step limit.'

            # Start single line spinner for non-verbose CLI mode (disabled in GUI/TUI mode where on_event is active)
            spinner = Spinner("Julius working...") if (not self.config.verbose and not self.on_event) else None
            if spinner:
                spinner.start()

            step_num = 0
            while True:
                step_num += 1
                if not is_unlimited and step_num > effective_max:
                    break

                if self._aborted:
                    stop_reason = 'abort'
                    summary = 'Agent was aborted by user.'
                    break

                if self.config.verbose:
                    print(f'\n{"─" * 50}')
                    print(f'📍 Step {step_num}{f"/{effective_max}" if not is_unlimited else ""}')
                self._emit('step_start', step=step_num, max_steps=(0 if is_unlimited else effective_max))

                # Build the prompt for this step
                if step_num == 1:
                    prompt = initial_prompt
                else:
                    if is_aifree:
                        prompt = (
                            f"## Observation (Step {step_num})\n"
                            f"### Task: {task}\n"
                            f"### Previous Action Result:\n"
                            f"{last_result[:800]}\n\n"
                            f"Respond with your next JSON block (converse, run_bash, read_file, edit_file, list_dir, done):"
                        )
                    else:
                        dir_listing = self.executor.list_directory('.').output
                        extra = build_workspace_context(self.config.allowed_directory)
                        if self.config.screenshot_mode:
                            extra += self._capture_observation_screenshot(step_num)

                        prompt = build_step_prompt(
                            step=step_num,
                            max_steps=effective_max,
                            task=task,
                            cwd=self.config.allowed_directory,
                            last_result=last_result,
                            dir_listing=dir_listing,
                            extra_context=extra,
                        )

                stream_buffer = ""
                is_json_action_stream = False
                streamed_message_pos = 0
                last_emitted_thought = ""

                def _on_chunk(text: str) -> None:
                    nonlocal stream_buffer, is_json_action_stream, streamed_message_pos, last_emitted_thought
                    stream_buffer += text
                    trimmed = stream_buffer.strip()

                    # Immediate detection of code fences, JSON blocks, or internal protocol markers
                    if (
                        is_json_action_stream
                        or trimmed.startswith(('```', '{', 'json'))
                        or is_json_or_protocol(trimmed)
                        or is_json_or_protocol(stream_buffer)
                        or "{" in stream_buffer
                    ):
                        is_json_action_stream = True

                        # 1. Extract thought from JSON if present
                        m_th = re.search(r'"thought"\s*:\s*"((?:[^"\\]|\\.)*)', stream_buffer)
                        if m_th:
                            raw_th = m_th.group(1).replace('\\"', '"').replace('\\n', ' ').strip()
                            clean_th = re.sub(r'```(?:json)?', '', raw_th).strip('`{}[] ').strip()
                            if clean_th and clean_th != last_emitted_thought and clean_th.lower() not in ('json', '```', '```json'):
                                last_emitted_thought = clean_th
                                self._emit('thought', text=clean_th)

                        # 2. Extract and stream message/summary for direct conversational responses (stories, answers)
                        # so the user sees live streaming text in real-time!
                        m_msg = re.search(r'"(?:message|summary)"\s*:\s*"((?:[^"\\]|\\.)*)', stream_buffer)
                        if m_msg:
                            content = m_msg.group(1).replace('\\"', '"').replace('\\n', '\n')
                            if len(content) > streamed_message_pos:
                                delta = content[streamed_message_pos:]
                                streamed_message_pos = len(content)
                                if delta and not re.fullmatch(r'(?:\\[nrt]|[\s])+', delta):
                                    self._emit('stream', text=delta.replace('\\n', '\n'))
                        return

                    # Handling non-JSON streams (e.g. DeepSeek-R1 <think> or direct narrative)
                    if "<think>" in stream_buffer:
                        if "</think>" not in stream_buffer:
                            # Inside thinking tag
                            th_part = stream_buffer.split("<think>", 1)[1].strip()
                            clean_th = re.sub(r'```(?:json)?', '', th_part).strip('`{}[] ').strip()
                            if clean_th and clean_th != last_emitted_thought and clean_th.lower() not in ('json', '```', '```json'):
                                last_emitted_thought = clean_th
                                self._emit('thought', text=clean_th)
                        else:
                            # After thinking tag: stream direct output
                            after_think = stream_buffer.split("</think>", 1)[1]
                            if after_think.strip().startswith(('```', '{', 'json')):
                                is_json_action_stream = True
                            elif len(after_think) > streamed_message_pos:
                                delta = after_think[streamed_message_pos:]
                                streamed_message_pos = len(after_think)
                                if delta and not is_json_or_protocol(delta) and not re.fullmatch(r'(?:\\[nrt]|[\s])+', delta):
                                    self._emit('stream', text=delta.replace('\\n', '\n'))
                    else:
                        # Direct conversational text (e.g. uncensored story without JSON)
                        # Ensure we never emit markdown code fences or JSON syntax into chat or thinking
                        if not trimmed.startswith(('```', '{', 'json')) and text and not re.fullmatch(r'(?:\\[nrt]|[\s])+', text):
                            self._emit('stream', text=text.replace('\\n', '\n'))

                step_start = time.time()
                if step_num == 1 and image_path:
                    response = await self.client.send_message_with_image(
                        prompt,
                        image_path,
                        timeout=self.config.response_timeout,
                    )
                else:
                    response = await self.client.send_message(
                        prompt,
                        timeout=self.config.response_timeout,
                        retry_limit=self.config.retry_limit,
                        retry_backoff=self.config.retry_backoff_base,
                        on_chunk=_on_chunk,
                    )

                self._emit('stream_end')

                auto_rec = getattr(self.client, "attempt_auto_recovery", None)
                if getattr(response, "error", None) and callable(auto_rec):
                    try:
                        import inspect
                        rec_res = auto_rec(prompt, on_chunk=_on_chunk)
                        if inspect.isawaitable(rec_res):
                            recovered = await rec_res
                            if recovered and getattr(recovered, "success", False):
                                response = recovered
                    except Exception as _rec_err:
                        logger.debug("Auto-recovery call bypassed: %s", _rec_err)

                if response.error:
                    if spinner:
                        spinner.stop()
                    if self.config.verbose:
                        print(f'   ❌ LLM Error: {response.error}')
                    else:
                        render_error(f'LLM communication failed: {response.error}')
                    self._emit('error', message=f'LLM Error: {response.error}')
                    stop_reason = 'error'
                    summary = f'LLM communication failed: {response.error}'
                    break

                action_data = self._parse_action(response)

                if action_data is None:
                    if self.config.verbose:
                        print(f'   ⚠️  Could not parse JSON action from response.')
                        print(f'   Raw response preview: {response.raw_text[:300]}')
                    last_result = 'ERROR: Your response did not contain valid JSON. Please respond with ONLY a JSON action block as specified in the system prompt.'
                    self._steps.append(StepRecord(
                        step=step_num,
                        thought='(unparseable)',
                        action='parse_error',
                        args={},
                        result=last_result,
                        success=False,
                        duration_ms=int((time.time() - step_start) * 1000),
                    ))
                    continue

                is_valid, validation_error = validate_action(action_data)
                if not is_valid and 'Terminal actions' in validation_error:
                    # Auto-heal:
                    # 1. If non-terminal actions exist, filter out terminal actions and execute tools first.
                    # 2. If all actions in the batch are terminal actions (e.g. converse + done), select primary (converse > ask_human > done).
                    batch_key = next((k for k in ('actions', 'batch', 'steps') if isinstance(action_data.get(k), list)), None) if isinstance(action_data, dict) else None
                    if batch_key:
                        actions_list = action_data[batch_key]
                        non_term = [a for a in actions_list if a.get('action') not in ('done', 'converse', 'ask_human')]
                        if non_term:
                            action_data[batch_key] = non_term
                            is_valid, validation_error = validate_action(action_data)
                        else:
                            conv = [a for a in actions_list if a.get('action') == 'converse']
                            ask = [a for a in actions_list if a.get('action') == 'ask_human']
                            done = [a for a in actions_list if a.get('action') == 'done']
                            chosen = conv or ask or done
                            if chosen:
                                action_data[batch_key] = [chosen[0]]
                                is_valid, validation_error = validate_action(action_data)
                    elif isinstance(action_data, list):
                        non_term = [a for a in action_data if a.get('action') not in ('done', 'converse', 'ask_human')]
                        if non_term:
                            action_data = non_term
                            is_valid, validation_error = validate_action(action_data)
                        else:
                            conv = [a for a in action_data if a.get('action') == 'converse']
                            ask = [a for a in action_data if a.get('action') == 'ask_human']
                            done = [a for a in action_data if a.get('action') == 'done']
                            chosen = conv or ask or done
                            if chosen:
                                action_data = [chosen[0]]
                                is_valid, validation_error = validate_action(action_data)

                if not is_valid:
                    if self.config.verbose:
                        print(f'   ⚠️  Schema validation failed: {validation_error}')
                    last_result = f'ERROR: Your response had a structural issue: {validation_error}. Please fix and respond again with a valid JSON action.'
                    self._steps.append(StepRecord(
                        step=step_num,
                        thought=action_data.get('thought', '(schema validation failed)'),
                        action='validation_error',
                        args=action_data,
                        result=last_result,
                        success=False,
                        duration_ms=int((time.time() - step_start) * 1000),
                    ))
                    continue

                try:
                    actions, mode = normalize_actions(action_data)
                except ValueError as norm_err:
                    last_result = f"ERROR: Action normalization error: {norm_err}"
                    self._steps.append(StepRecord(
                        step=step_num,
                        thought=action_data.get('thought', '(normalization error)'),
                        action='batch_error',
                        args=action_data,
                        result=last_result,
                        success=False,
                        duration_ms=int((time.time() - step_start) * 1000),
                    ))
                    continue

                thought = (action_data.get('thought') or '').strip()
                if thought and thought.lower() not in ('executing action', '(no thought)', 'none'):
                    self._emit('thought', text=thought)

                if len(actions) > 1:
                    if self.config.verbose:
                        print(f'   💭 Thought: {thought[:100]}')
                        print(f'   ⚡ Batch ({mode}): {len(actions)} actions')
                        for a in actions:
                            print(f'      [{a["id"]}] {a["action"]}')

                    # Check confirmations for gated actions or outside-workspace access
                    skip_batch = False
                    for a in actions:
                        is_outside = self._is_outside_workspace(a['action'], a['args'])
                        needs_confirm = self.config.needs_confirmation(a['action']) or (is_outside and not self._host_access_granted)
                        if needs_confirm:
                            if spinner:
                                spinner.stop()
                            allow = await self._get_human_confirmation(
                                a['action'],
                                {
                                    **a['args'],
                                    "_outside_workspace": is_outside,
                                    "_permission_prompt": (
                                        f"Action '{a['action']}' requested access outside the workspace folder.\nAllow un-sandboxed access across your Mac? (y/n)"
                                        if is_outside else ""
                                    ),
                                },
                            )
                            if spinner:
                                spinner.start()
                            if not allow:
                                skip_batch = True
                                break
                            elif is_outside:
                                target_p = a.get("args", {}).get("path") or a.get("args", {}).get("file") or a.get("args", {}).get("directory")
                                if target_p and hasattr(self.executor, "grant_path_access"):
                                    mode = "write" if a.get("action") in ("write_file", "edit_file") else "read"
                                    self.executor.grant_path_access(str(target_p), mode=mode, ttl_seconds=120.0, once=True)

                    if skip_batch:
                        last_result = 'Action batch skipped: Permission declined by user.'
                        for a in actions:
                            self._steps.append(StepRecord(
                                step=step_num,
                                thought=thought,
                                action=a['action'],
                                args=a['args'],
                                result=last_result,
                                success=True,
                                duration_ms=int((time.time() - step_start) * 1000),
                            ))
                        continue

                    if mode == 'parallel':
                        self._emit('status', message=f'Executing {len(actions)} parallel actions…')

                        async def _exec_batch_item(item: dict) -> dict:
                            act_id = item['id']
                            act_name = item['action']
                            act_args = item['args']
                            t0 = time.time()
                            self._emit('action', name=act_name, args=act_args, id=act_id)
                            try:
                                res = await asyncio.to_thread(self.executor.execute, act_name, act_args)
                            except Exception as exc:
                                res = ActionResult(success=False, output=str(exc), action=act_name, error=str(exc))
                            dur = int((time.time() - t0) * 1000)
                            dur_s = max(0.1, time.time() - t0)
                            self._emit('result', name=act_name, args=act_args, output=res.output[:500], success=res.success, id=act_id, duration_s=dur_s)
                            self._update_checkpoint(act_name, act_args, res, thought)
                            return {
                                'id': act_id,
                                'action': act_name,
                                'args': act_args,
                                'ok': res.success,
                                'output': res.output,
                                'duration_ms': dur,
                            }

                        batch_results = await asyncio.gather(*[_exec_batch_item(item) for item in actions])
                        for r in batch_results:
                            self._steps.append(StepRecord(
                                step=step_num,
                                thought=thought,
                                action=r['action'],
                                args=r['args'],
                                result=r['output'],
                                success=r['ok'],
                                duration_ms=r['duration_ms'],
                            ))
                        last_result = format_batch_results(batch_results)
                        continue

                    else:  # sequential mode
                        self._emit('status', message=f'Executing {len(actions)} sequential actions…')
                        batch_results = []
                        for idx, item in enumerate(actions):
                            act_id = item['id']
                            act_name = item['action']
                            act_args = item['args']
                            t0 = time.time()
                            self._emit('action', name=act_name, args=act_args, id=act_id)
                            try:
                                res = await asyncio.to_thread(self.executor.execute, act_name, act_args)
                            except Exception as exc:
                                res = ActionResult(success=False, output=str(exc), action=act_name, error=str(exc))
                            dur = int((time.time() - t0) * 1000)
                            dur_s = max(0.1, time.time() - t0)
                            self._emit('result', name=act_name, args=act_args, output=res.output[:500], success=res.success, id=act_id, duration_s=dur_s)
                            self._update_checkpoint(act_name, act_args, res, thought)
                            batch_results.append({
                                'id': act_id,
                                'action': act_name,
                                'args': act_args,
                                'ok': res.success,
                                'output': res.output,
                                'duration_ms': dur,
                            })
                            self._steps.append(StepRecord(
                                step=step_num,
                                thought=thought,
                                action=act_name,
                                args=act_args,
                                result=res.output,
                                success=res.success,
                                duration_ms=dur,
                            ))
                            if not res.success:
                                for skipped in actions[idx+1:]:
                                    batch_results.append({
                                        'id': skipped['id'],
                                        'action': skipped['action'],
                                        'args': skipped['args'],
                                        'ok': False,
                                        'output': '(skipped due to prior action failure)',
                                        'duration_ms': 0,
                                    })
                                break
                        last_result = format_batch_results(batch_results)
                        continue

                single_item = actions[0]
                action_name = single_item['action']
                action_args = single_item['args']

                if self.config.verbose:
                    print(f'   💭 Thought: {thought[:100]}')
                    print(f'   🎯 Action: {action_name}')
                    if action_name == 'run_bash':
                        print(f'   📝 Command: {action_args.get("command", "")}')
                    elif action_name in ('read_file', 'write_file', 'edit_file'):
                        print(f'   📝 File: {action_args.get("path", "")}')
                self._emit('action', name=action_name, args=action_args)

                if action_name not in VALID_ACTIONS:
                    last_result = f"ERROR: Unknown action '{action_name}'. Valid actions: {', '.join(sorted(VALID_ACTIONS))}"
                    self._steps.append(StepRecord(
                        step=step_num,
                        thought=thought,
                        action=action_name,
                        args=action_args,
                        result=last_result,
                        success=False,
                        duration_ms=int((time.time() - step_start) * 1000),
                    ))
                    continue

                # Safety check — human confirmation
                is_outside = self._is_outside_workspace(action_name, action_args)
                needs_confirm = self.config.needs_confirmation(action_name) or (is_outside and not self._host_access_granted)
                if needs_confirm:
                    if spinner:
                        spinner.stop()
                    allow = await self._get_human_confirmation(
                        action_name,
                        {
                            **action_args,
                            "_outside_workspace": is_outside,
                            "_permission_prompt": (
                                f"Action '{action_name}' requested access outside the workspace folder.\nAllow un-sandboxed access across your Mac? (y/n)"
                                if is_outside else ""
                            ),
                        },
                    )
                    if spinner:
                        spinner.start()
                    if not allow:
                        last_result = 'Action skipped: Outside-workspace access declined by user.' if is_outside else 'Action skipped by human operator.'
                        if self.config.verbose:
                            print(f'   ⏭️  Action skipped.')
                        self._steps.append(StepRecord(
                            step=step_num,
                            thought=thought,
                            action=action_name,
                            args=action_args,
                            result=last_result,
                            success=True,
                            duration_ms=int((time.time() - step_start) * 1000),
                        ))
                        continue
                    elif is_outside:
                        target_p = action_args.get("path") or action_args.get("file") or action_args.get("directory")
                        if target_p and hasattr(self.executor, "grant_path_access"):
                            mode = "write" if action_name in ("write_file", "edit_file") else "read"
                            self.executor.grant_path_access(str(target_p), mode=mode, ttl_seconds=120.0, once=True)

                self._current_in_flight_action = action_name
                self._current_in_flight_file = action_args.get("path") if action_name in ("write_file", "edit_file") else None
                if self._current_in_flight_action in ("write_file", "edit_file") and self._current_in_flight_file and self.current_working_state:
                    self.current_working_state.last_known_good_state = (
                        f"uncertain — last action was writing {self._current_in_flight_file}, outcome unconfirmed"
                    )
                    if self._current_in_flight_file not in self.current_working_state.files_in_progress:
                        self.current_working_state.files_in_progress.append(self._current_in_flight_file)
                    self.working_state_mgr.save_working_state(self.current_working_state)

                if action_name == "ask_human":
                    question = action_args.get("question", "Clarification requested:")
                    options = action_args.get("options", [])
                    if self.on_event:
                        user_ans = await self._ask_user_question_async(question, options)
                        result = ActionResult(success=True, output=f"Human answered: {user_ans}", action="ask_human")
                    else:
                        result = self.executor.ask_human(question)
                else:
                    self._emit('status', message=f'Executing {action_name}...')
                    result = await asyncio.to_thread(self.executor.execute, action_name, action_args)

                last_result = result.output
                self._update_checkpoint(action_name, action_args, result, thought)

                self._current_in_flight_action = None
                self._current_in_flight_file = None

                if (
                    action_name == 'run_bash'
                    and not result.success
                    and _HEALER_AVAILABLE
                    and getattr(self.config, 'enable_self_healing', False)
                ):
                    if self.config.verbose:
                        print(f'   🩹 run_bash failed — attempting autonomous self-heal...')
                    self._emit('heal_start', command=action_args.get('command', ''))
                    healer = SelfHealer(
                        client=self.client,
                        executor=self.executor,
                        max_attempts=getattr(self.config, 'self_heal_attempts', 3),
                        on_event=self._emit,
                    )
                    healed, heal_result, heal_log = await healer.attempt_fix(
                        failed_result=result,
                        original_command=action_args.get('command', ''),
                        task=task,
                    )
                    if self.config.verbose:
                        print(healer.get_heal_summary())
                    if healed:
                        result = heal_result
                        last_result = result.output
                        self._emit('heal_success', summary=healer.get_heal_summary())
                    else:
                        q_msg = (
                            f'Self-heal exhausted after {len(heal_log)} attempts.\n'
                            f'{healer.get_heal_summary()}\n\n'
                            f'What should I do next?'
                        )
                        user_ans = await self._ask_user_question_async(q_msg, [
                            "1. Retry bash command with modified parameters",
                            "2. Skip failed command and proceed to next subtask",
                            "3. Stop execution"
                        ])
                        last_result = f"Human answered: {user_ans}"
                        self._emit('heal_failed', summary=healer.get_heal_summary())

                status = '✅' if result.success else '❌'
                if self.config.verbose:
                    print(f'   {status} Result: {result.output[:200]}')
                step_dur_s = max(0.1, time.time() - step_start)
                self._emit('result', name=action_name, args=action_args, output=result.output[:500], success=result.success, duration_s=step_dur_s)

                self._steps.append(StepRecord(
                    step=step_num,
                    thought=thought,
                    action=action_name,
                    args=action_args,
                    result=result.output,
                    success=result.success,
                    duration_ms=int((time.time() - step_start) * 1000),
                ))

                if action_name == 'done':
                    # Guard 1: Reject premature 'done' if a previous tool action in this run failed!
                    recent_failures = [
                        s for s in self._steps
                        if not s.success and s.action not in ('done', 'converse', 'validation_error', 'parse_error', 'ask_human')
                    ]
                    if recent_failures and (is_unlimited or step_num < effective_max):
                        last_failed = recent_failures[-1]
                        last_result = (
                            f"ERROR: Cannot mark task as 'done' because action '{last_failed.action}' failed with output:\n"
                            f"{last_failed.result[:500]}\n"
                            f"You must resolve this failure, troubleshoot with correct parameters, or clearly explain the exact blocker."
                        )
                        continue

                    # Guard 2: Reject premature 'done' on actionable user tasks when no tools were run!
                    action_verbs = ('send', 'create', 'write', 'edit', 'modify', 'delete', 'remove', 'install', 'build', 'run', 'execute', 'playwright', 'email', 'mail')
                    user_task_lower = task.lower()
                    has_action_intent = any(v in user_task_lower for v in action_verbs)
                    executed_tools = [
                        s for s in self._steps
                        if s.action not in ('done', 'converse', 'ask_human', 'validation_error', 'parse_error')
                    ]
                    if has_action_intent and not executed_tools and (is_unlimited or step_num < effective_max):
                        last_result = (
                            f"ERROR: You signaled 'done' without executing any actions. The user requested: '{task}'. "
                            f"You must execute the necessary tool (e.g. run_bash, write_file, edit_file) to perform and complete the task before calling 'done'."
                        )
                        continue

                    # Guard 3: Guarantee summary honesty — never accept generic lazy placeholders
                    raw_summary = action_args.get('summary', '') or action_args.get('message', '') or action_args.get('text', '')
                    clean_summary = raw_summary.strip()
                    generic_placeholders = {
                        'task complete.', 'task completed.', 'task completed', 'task complete',
                        'done.', 'done', 'completed.', 'completed', 'finished.', 'finished',
                        'all done.', 'all done', 'task marked as complete.'
                    }
                    if not clean_summary or clean_summary.lower() in generic_placeholders:
                        if executed_tools:
                            successful_tools = [s for s in executed_tools if s.success]
                            if successful_tools:
                                last_succ = successful_tools[-1]
                                out_preview = (last_succ.result or '').strip()
                                clean_summary = f"Executed {last_succ.action}:\n{out_preview[:400]}" if out_preview else f"Executed {last_succ.action} successfully."
                            else:
                                last_fail = executed_tools[-1]
                                clean_summary = f"Task stopped: {last_fail.action} failed with output: {last_fail.result[:300]}"
                        else:
                            clean_summary = f"Task completed: {task[:80]}"

                    stop_reason = 'done'
                    summary = clean_summary
                    if self.config.verbose:
                        print(f'\n✅ Task complete: {summary}')
                    self._emit('done', summary=summary, duration_s=step_dur_s)
                    break

                if action_name == 'converse':
                    message = action_args.get('message', '')
                    # If user asked for an action and no tools have run on step 1, remind model to execute rather than just chat
                    action_verbs = ('send', 'create', 'write', 'edit', 'modify', 'delete', 'remove', 'install', 'build', 'run', 'execute', 'playwright', 'email', 'mail')
                    user_task_lower = task.lower()
                    has_action_intent = any(v in user_task_lower for v in action_verbs)
                    executed_tools = [
                        s for s in self._steps
                        if s.action not in ('done', 'converse', 'ask_human', 'validation_error', 'parse_error')
                    ]
                    if has_action_intent and not executed_tools and step_num == 1 and (is_unlimited or step_num < effective_max):
                        last_result = (
                            f"You responded with a conversational message: '{message[:200]}'.\n"
                            f"However, the user asked you to execute an action: '{task}'.\n"
                            f"Please execute the required tool action (e.g. run_bash, write_file, edit_file) to perform the task."
                        )
                        continue

                    summary = message
                    stop_reason = 'converse'
                    if self.config.verbose:
                        print(f'\n💬 Julius: {message[:200]}')
                    self._emit('converse', message=message, duration_s=step_dur_s)
                    break

        except asyncio.CancelledError:
            stop_reason = 'abort'
            summary = 'Agent task was cancelled.'
            if spinner:
                spinner.stop()
            # Cancellation is a user action, NOT an error — emit status only
            self._emit('status', message='Task cancelled.')
            raise
        except Exception as exc:
            stop_reason = 'error'
            summary = f'Agent run failed: {exc}'
            if spinner:
                spinner.stop()
            if self.config.verbose:
                print(f'\n❌ Error: {exc}')
            else:
                render_error(str(exc))
            self._emit('error', message=str(exc))
            raise
        finally:
            if spinner:
                spinner.stop()
            self._is_running = False
            safe_stop_reason = stop_reason if 'stop_reason' in locals() else 'error'
            safe_summary = summary if 'summary' in locals() else 'Agent execution interrupted.'
            self._write_working_state_exit(
                safe_stop_reason,
                safe_summary,
                getattr(self, "_current_in_flight_action", None),
                getattr(self, "_current_in_flight_file", None),
            )
            if self._owns_client and not self.keep_browser_open:
                await self.client.close()
            self._teardown_safety()

        elapsed = time.time() - start_time

        log_path = Path(self.config.log_dir) / f'session_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
        self.client.save_session_log(str(log_path))
        self._save_step_history(str(log_path).replace('.json', '_steps.json'))

        safe_stop_reason = stop_reason if 'stop_reason' in locals() else 'error'
        safe_summary = summary if 'summary' in locals() else 'Agent execution interrupted.'
        agent_result = AgentResult(
            success=safe_stop_reason == 'done',
            summary=safe_summary,
            steps=self._steps,
            total_steps=len(self._steps),
            elapsed_seconds=elapsed,
            stop_reason=safe_stop_reason,
        )

        if self.config.verbose:
            print(f'\n{"═" * 50}')
            print(f'🏁 Agent finished: {stop_reason}')
            print(f'   Steps: {len(self._steps)} | Time: {elapsed:.1f}s')
            print(f'   Summary: {summary}')
        else:
            render_final_answer(summary)

        # Record task execution into MemoryStorage (task_memory) for recent activity tracking
        try:
            from .memory.storage import MemoryStorage
            storage = MemoryStorage(self.config.allowed_directory)
            task_id = self.current_working_state.task_id if self.current_working_state else str(uuid.uuid4())
            modified_files = [s.args.get("path") for s in self._steps if s.action in ("write_file", "edit_file") and s.args.get("path")]
            storage.save_task(
                task_id=task_id,
                summary=summary or task,
                status="completed" if agent_result.success else "failed",
                files_modified=modified_files,
            )
        except Exception as exc:
            logger.warning(f"Failed to record task into MemoryStorage: {exc}")

        self._emit('finished', success=agent_result.success, summary=summary,
                   total_steps=len(self._steps), elapsed=elapsed, stop_reason=stop_reason)

        return agent_result

    # ── Working State & Resumption ────────────────────────────────

    async def _handle_startup_resumption(self, task: str) -> str:
        """
        Stage 3, 4, 6: Startup resumption check and state re-verification.
        Surfaces all active tasks for the project without silent assumptions.
        Re-verifies uncertain disk state before treating tasks as valid.
        """
        project_id = str(Path(self.config.allowed_directory).resolve())
        active_tasks = self.working_state_mgr.get_active_tasks(project_id)

        if not active_tasks:
            # Create a new working state record for this task
            task_id = str(uuid.uuid4())
            self.current_working_state = TaskWorkingState(
                task_id=task_id,
                project_id=project_id,
                goal=task,
                current_plan="1. Observe workspace state\n2. Execute subtasks\n3. Verify completion",
                completed_subtasks=[],
                remaining_subtasks=[task],
                last_known_good_state=f"Initialized new task: '{task}'",
                blockers=[],
                files_in_progress=[],
                last_updated=time.time(),
                session_count=1,
                status="in_progress",
            )
            self.working_state_mgr.save_working_state(self.current_working_state)
            return ""

        # Priority 3a: Disambiguate when multiple active tasks exist
        matching_task = None
        if len(active_tasks) > 1:
            options = [f"Resume Task: '{t.goal[:40]}' (ID: {t.task_id[:8]})" for t in active_tasks]
            options.append("Start new task & archive existing tasks")
            q_text = f"Multiple ({len(active_tasks)}) active tasks exist for this workspace. Which task would you like to work on?"
            user_ans = await self._ask_user_question_async(q_text, options)
            
            selected = None
            for idx, t in enumerate(active_tasks):
                if f"ID: {t.task_id[:8]}" in user_ans or f"Resume Task: '{t.goal[:40]}" in user_ans or f"{idx + 1}." in user_ans:
                    selected = t
                    break
            
            if selected:
                matching_task = selected
            elif "Start new task" in user_ans:
                matching_task = None
        else:
            # Check if the new task matches an existing active task goal or explicitly requests resumption
            task_lower = task.strip().lower()
            for t in active_tasks:
                g_lower = t.goal.strip().lower()
                if g_lower in task_lower or task_lower in g_lower or "resume" in task_lower or "continue" in task_lower:
                    matching_task = t
                    break

        if not matching_task:
            # User submitted a new distinct task — archive old active tasks so they don't hijack the prompt
            for t in active_tasks:
                t.status = "archived"
                self.working_state_mgr.save_working_state(t)
            
            task_id = str(uuid.uuid4())
            self.current_working_state = TaskWorkingState(
                task_id=task_id,
                project_id=project_id,
                goal=task,
                current_plan="1. Observe workspace state\n2. Execute subtasks\n3. Verify completion",
                completed_subtasks=[],
                remaining_subtasks=[task],
                last_known_good_state=f"Initialized new task: '{task}'",
                blockers=[],
                files_in_progress=[],
                last_updated=time.time(),
                session_count=1,
                status="in_progress",
            )
            self.working_state_mgr.save_working_state(self.current_working_state)
            return ""

        self.current_working_state = matching_task
        self.current_working_state.session_count += 1
        self.current_working_state.last_updated = time.time()

        # Re-verify uncertain disk state
        if "uncertain" in (matching_task.last_known_good_state or "").lower():
            verified_notes = []
            for fp in matching_task.files_in_progress:
                full_p = Path(self.config.allowed_directory) / fp
                if full_p.exists():
                    verified_notes.append(f"Confirmed file {fp} exists on disk")
                else:
                    verified_notes.append(f"File {fp} not found on disk")
            if verified_notes:
                matching_task.last_known_good_state = (
                    f"{matching_task.last_known_good_state} | Re-verification: {', '.join(verified_notes)}"
                )

        self.working_state_mgr.save_working_state(self.current_working_state)

        resumption_info_blocks = [
            f"Task ID: {matching_task.task_id}",
            f"Goal: {matching_task.goal}",
            f"Last Known Good State: {matching_task.last_known_good_state}",
            f"Completed Subtasks: {', '.join(matching_task.completed_subtasks) if matching_task.completed_subtasks else 'None'}",
            f"Remaining Subtasks: {', '.join(matching_task.remaining_subtasks) if matching_task.remaining_subtasks else 'None'}",
            f"Files in Progress: {', '.join(matching_task.files_in_progress) if matching_task.files_in_progress else 'None'}",
        ]

        resumption_context = (
            f"\n\nRESUMPTION SYSTEM CONTEXT:\n"
            f"You are resuming execution on an existing task working state.\n"
            + "\n".join(resumption_info_blocks) +
            "\nContinue from the last known good state. Do NOT start over or re-verify unnecessary steps."
        )
        return resumption_context

    def _update_checkpoint(self, action_name: str, action_args: dict, result: ActionResult, thought: str) -> None:
        """Stage 2: Update working state at natural checkpoints."""
        if not self.current_working_state:
            return

        if action_name in ("write_file", "edit_file"):
            fpath = action_args.get("path", "")
            if fpath and fpath not in self.current_working_state.files_in_progress:
                self.current_working_state.files_in_progress.append(fpath)

            if result.success:
                subtask = f"Modified file '{fpath}'"
                if subtask not in self.current_working_state.completed_subtasks:
                    self.current_working_state.completed_subtasks.append(subtask)
                self.current_working_state.last_known_good_state = (
                    f"Implemented edits in {fpath} (verified write output)."
                )
            else:
                blocker = f"Failed editing {fpath}: {result.output[:100]}"
                if blocker not in self.current_working_state.blockers:
                    self.current_working_state.blockers.append(blocker)
                self.current_working_state.last_known_good_state = (
                    f"Attempted to edit {fpath} but failed: {result.output[:100]}"
                )

        elif action_name == "run_bash":
            cmd = action_args.get("command", "")
            if result.success:
                subtask = f"Ran bash command: {cmd[:60]}"
                if subtask not in self.current_working_state.completed_subtasks:
                    self.current_working_state.completed_subtasks.append(subtask)
                self.current_working_state.last_known_good_state = (
                    f"Executed command '{cmd[:60]}' successfully."
                )
            else:
                blocker = f"Command failed: {cmd[:60]}"
                if blocker not in self.current_working_state.blockers:
                    self.current_working_state.blockers.append(blocker)
                self.current_working_state.last_known_good_state = (
                    f"Ran command '{cmd[:60]}' but output indicated failure."
                )

        elif action_name == "done":
            summary = action_args.get("summary", "Task completed.")
            self.current_working_state.last_known_good_state = f"Completed task: {summary}"
            self.current_working_state.status = "completed"
            self.current_working_state.remaining_subtasks = []
            self.working_state_mgr.mark_completed(self.current_working_state.task_id, summary)
            return

        if thought:
            self.current_working_state.current_plan = f"Current focus: {thought[:200]}"

        self.working_state_mgr.save_working_state(self.current_working_state)

    def _write_working_state_exit(self, stop_reason: str, summary: str, in_flight_action: str | None = None, in_flight_file: str | None = None) -> None:
        """Stage 2 & 4: Always write working state on exit path with honesty guarantees."""
        if not self.current_working_state:
            return

        if self.current_working_state.status == "completed":
            return

        if in_flight_action in ("write_file", "edit_file") and in_flight_file:
            self.current_working_state.last_known_good_state = (
                f"uncertain — last action was writing {in_flight_file}, outcome unconfirmed"
            )
            if in_flight_file not in self.current_working_state.files_in_progress:
                self.current_working_state.files_in_progress.append(in_flight_file)
        else:
            self.current_working_state.last_known_good_state = (
                f"Stopped ({stop_reason}): {summary}. Last verified checkpoint: {self.current_working_state.last_known_good_state}"
            )

        if stop_reason == "done":
            self.current_working_state.status = "completed"

        self.working_state_mgr.save_working_state(self.current_working_state)

    # ── LLM initialization ────────────────────────────────────────

    async def _initialize_llm(self) -> None:
        """Initialize the web LLM client (skips if already initialized via shared client or previous command)."""
        if self.client is None:
            self.client = self.router

        if self.client and getattr(self.client, "is_initialized", False):
            # Verify provider matches requested provider
            req_provider = (self.config.provider or "").lower().strip()
            if req_provider in ("ollama", "llama", "local", "r1", "r1-14b", "r1-local", "deepseek-r1", "deepseek-14b", "deepseek-r1-14b", "hushus", "uncalibrated", "lexi", "qwen", "llama70b"):
                req_provider = "ollama"

            prov_key_attr = getattr(self.client, "provider_key", "")
            if callable(prov_key_attr) and not isinstance(prov_key_attr, str):
                try:
                    prov_key_attr = prov_key_attr()
                except Exception:
                    prov_key_attr = ""
            client_prov = str(prov_key_attr or "").lower().strip()
            if not client_prov or "mock" in client_prov:
                raw_curr = getattr(self.client, "provider_name", "")
                if callable(raw_curr):
                    try:
                        raw_curr = raw_curr()
                    except Exception:
                        raw_curr = ""
                raw_s = str(raw_curr).lower().strip()
                if raw_s and "mock" not in raw_s:
                    client_prov = "ollama" if "ollama" in raw_s else raw_s.split()[0].strip()
                else:
                    client_prov = req_provider

            if req_provider != client_prov:
                logger.info(f"Re-initializing LLM client: provider changed from '{client_prov}' to '{req_provider}'")
                await self.client.close()
            else:
                page = getattr(self.client, "_page", None)
                page_is_closed = False
                if page is not None and not str(type(page)).lower().endswith("mock'>"):
                    try:
                        page_is_closed = bool(getattr(page, "is_closed", lambda: False)())
                    except Exception:
                        page_is_closed = False

                if page_is_closed:
                    logger.warning(f"Cached {getattr(self.client, 'provider_name', '')} page was closed externally. Re-initializing...")
                    await self.client.close()
                else:
                    # Browser is active and matches provider: reuse same session without closing/reopening
                    p_name = getattr(self.client, "provider_name", "")
                    if self.config.verbose:
                        print(f'♻️  Reusing existing {p_name} session')
                    self._emit('status', message=f'Reusing {p_name} session')
                    return

        await self.client.initialize(
            provider_name=self.config.provider,
            profile_dir=self.config.profile_dir,
            headless=self.config.headless,
        )

    # ── Action parsing ────────────────────────────────────────────

    @staticmethod
    def _parse_action(response) -> dict | None:
        """Extract the action dict (Shape A single action or Shape B batch) from an LLM response, strictly ignoring leaked thinking blocks."""
        import re

        def _normalize_action_args(action: str | None, args: dict) -> None:
            if not action or not isinstance(args, dict):
                return
            if action == 'done':
                if 'summary' not in args:
                    args['summary'] = args.get('message') or args.get('text') or args.get('result') or 'Task complete.'
            elif action == 'converse':
                if 'message' not in args:
                    args['message'] = args.get('summary') or args.get('text') or args.get('content') or ''
            elif action in ('run_bash', 'run_remote'):
                if 'command' not in args and 'cmd' in args:
                    args['command'] = args['cmd']
            elif action in ('read_file', 'write_file', 'list_dir', 'list_symbols'):
                if 'path' not in args:
                    for alt in ('file', 'filepath', 'file_path', 'dir', 'directory', 'path_name'):
                        if alt in args:
                            args['path'] = args[alt]
                            break
            elif action == 'search_files':
                if 'pattern' not in args:
                    if 'query' in args:
                        args['pattern'] = args['query']
                    elif 'text' in args:
                        args['pattern'] = args['text']

        def _clean_payload(data: dict) -> dict:
            """Sanitize thought and terminal action args of any leaked thinking tags and auto-heal missing thought/args."""
            if not isinstance(data, dict):
                return data
            # Hoist 'tool', 'function', 'name', 'call' to 'action' for broad model compatibility
            if 'action' not in data:
                for k in ('tool', 'function', 'name', 'call'):
                    if k in data and isinstance(data[k], str):
                        data['action'] = data.pop(k)
                        break
            # Hoist 'parameters' or 'arguments' to 'args'
            if 'args' not in data:
                for k in ('parameters', 'arguments', 'params'):
                    if k in data and isinstance(data[k], dict):
                        data['args'] = data.pop(k)
                        break
            if 'thought' not in data:
                data['thought'] = ''
            elif isinstance(data['thought'], str):
                th = re.sub(r'<think>.*?</think>', '', data['thought'], flags=re.DOTALL)
                th = re.sub(r'<thought>.*?</thought>', '', th, flags=re.DOTALL)
                th = re.sub(r'<reasoning>.*?</reasoning>', '', th, flags=re.DOTALL)
                data['thought'] = th.strip()
            if 'action' in data and ('args' not in data or not isinstance(data.get('args'), dict)):
                # If model emitted flat args e.g. {"action": "write_file", "path": "...", "content": "..."}
                # or {"tool": "read_file", "path": "README.md"}
                args = {k: v for k, v in data.items() if k not in ('action', 'thought', 'id', 'tool', 'function', 'name')}
                data['args'] = args
            action_name = data.get('action')
            args = data.get('args')
            if isinstance(args, dict):
                _normalize_action_args(action_name, args)
                for k in ('summary', 'message'):
                    if k in args and isinstance(args[k], str):
                        val = re.sub(r'<think>.*?</think>', '', args[k], flags=re.DOTALL)
                        val = re.sub(r'<thought>.*?</thought>', '', val, flags=re.DOTALL)
                        val = re.sub(r'<reasoning>.*?</reasoning>', '', val, flags=re.DOTALL)
                        args[k] = val.strip()
            batch_key = next((k for k in ('actions', 'batch', 'steps') if isinstance(data.get(k), list)), None)
            if batch_key:
                for item in data[batch_key]:
                    if isinstance(item, dict):
                        if 'action' not in item:
                            for k in ('tool', 'function', 'name'):
                                if k in item and isinstance(item[k], str):
                                    item['action'] = item.pop(k)
                                    break
                        if 'action' in item and ('args' not in item or not isinstance(item.get('args'), dict)):
                            item['args'] = {k: v for k, v in item.items() if k not in ('action', 'id', 'tool', 'function', 'name')}
                        act = item.get('action')
                        it_args = item.get('args')
                        if isinstance(it_args, dict):
                            _normalize_action_args(act, it_args)
            return data

        def _has_action(d: Any) -> bool:
            return bool(
                isinstance(d, dict)
                and (
                    'action' in d
                    or 'actions' in d
                    or 'tool' in d
                    or 'function' in d
                    or 'name' in d
                )
            )

        # First, try the parsed JSON from the client
        if response.parsed_json and isinstance(response.parsed_json, dict):
            data = response.parsed_json
            if _has_action(data):
                return _clean_payload(data)

        raw = response.raw_text or ""
        # Clean thinking blocks from raw text before parsing
        raw = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL)
        raw = re.sub(r'<thought>.*?</thought>', '', raw, flags=re.DOTALL)
        raw = re.sub(r'<reasoning>.*?</reasoning>', '', raw, flags=re.DOTALL)
        raw = re.sub(r'^(?:Thinking Process|Thought):\s*.*?(?=\n\n(?:```|{)|\Z)', '', raw, flags=re.DOTALL | re.IGNORECASE)
        raw = raw.strip()

        try:
            data = extract_json_block(raw)
            if _has_action(data):
                return _clean_payload(data)
        except Exception:
            pass

        # Try extracting from markdown code blocks (from last to first)
        json_blocks = list(re.finditer(r'```(?:json)?\s*\n?(.*?)\n?```', raw, re.DOTALL))
        for match in reversed(json_blocks):
            content = match.group(1).strip()
            try:
                data = json.loads(content, strict=False)
                if _has_action(data):
                    return _clean_payload(data)
            except Exception:
                fixed = attempt_json_fix(content)
                if fixed and _has_action(fixed):
                    return _clean_payload(fixed)
                continue

        # Try finding raw JSON objects (balanced curly braces, last to first)
        brace_depth = 0
        start_idx = -1
        candidates = []
        for i, char in enumerate(raw):
            if char == '{':
                if brace_depth == 0:
                    start_idx = i
                brace_depth += 1
            elif char == '}':
                brace_depth -= 1
                if brace_depth == 0 and start_idx >= 0:
                    candidates.append(raw[start_idx:i + 1])
                    start_idx = -1

        for candidate in reversed(candidates):
            try:
                data = json.loads(candidate, strict=False)
                if _has_action(data):
                    return _clean_payload(data)
            except Exception:
                fixed = attempt_json_fix(candidate)
                if fixed and _has_action(fixed):
                    return _clean_payload(fixed)
                continue

        # Fallback for uncensored or conversational responses without JSON wrapping
        if raw and len(raw.strip()) > 1:
            trimmed = raw.strip()
            # If the response was an attempt at an internal JSON action or protocol block but failed to parse,
            # DO NOT treat it as done! Treating failed action JSON as done terminates the task prematurely.
            if is_json_or_protocol(trimmed):
                return None

            lower_trimmed = trimmed.lower()

            # Guard against observation prompt leakage, dropzone text, or echoed system headers
            if (
                "current observation" in lower_trimmed or
                "previous action result" in lower_trimmed or
                "critical instructions:" in lower_trimmed or
                "directory listing" in lower_trimmed or
                "now respond with your next json block" in lower_trimmed or
                "drag and drop folders" in lower_trimmed or
                "drag and drop" in lower_trimmed or
                "drop files here" in lower_trimmed or
                lower_trimmed.startswith("working directory") or
                lower_trimmed.startswith("task:") or
                lower_trimmed.startswith("tasks/") or
                lower_trimmed.startswith("# julius — operating manual")
            ):
                return None

            # If the response is a known LLM web error, system failure, or rate-limit message,
            # DO NOT treat it as done! It must be retried or corrected.
            if any(err in lower_trimmed for err in (
                "encountered an error",
                "something went wrong",
                "try again later",
                "rate limit",
                "you stopped this response",
                "stopped the response",
                "capacity is full",
                "service is unavailable",
                "unable to load response",
                "please try again",
            )):
                return None

            # If the output starts with a shell command
            if re.match(r'^(?:\$\s*)?(?:brew|sudo|apt|pip|git|python3?|hydra|nmap|curl|ls|cd|cat|sh|bash)\b', trimmed):
                clean_cmd = re.sub(r'^\$\s*', '', trimmed).strip()
                return {"thought": "Executing direct command", "action": "run_bash", "args": {"command": clean_cmd}}
            # Otherwise, treat as direct conversational response (NOT done!)
            return {"thought": "Direct response", "action": "converse", "args": {"message": trimmed}}

        return None



    # ── Safety ────────────────────────────────────────────────────

    def _setup_safety(self) -> None:
        """Setup safety mechanisms."""
        # PyAutoGUI failsafe
        if self.config.enable_pyautogui_failsafe:
            try:
                import pyautogui
                pyautogui.FAILSAFE = True
            except (ImportError, Exception):
                pass

        # Abort hotkey listener
        self._setup_abort_listener()

        # Signal handler for clean shutdown
        signal.signal(signal.SIGINT, self._signal_handler)

    def _teardown_safety(self) -> None:
        """Clean up safety mechanisms."""
        if self._abort_listener:
            try:
                self._abort_listener.stop()
            except Exception:
                pass

    def _setup_abort_listener(self) -> None:
        """Setup keyboard listener for abort hotkey."""
        if not self.config.abort_hotkey:
            return

        try:
            from pynput import keyboard

            # Parse hotkey
            hotkey_parts = self.config.abort_hotkey.split('+')
            key_combo = set()
            for part in hotkey_parts:
                part = part.strip().lower()
                if part == 'ctrl':
                    key_combo.add(keyboard.Key.ctrl_l)
                elif part == 'shift':
                    key_combo.add(keyboard.Key.shift_l)
                elif part == 'alt':
                    key_combo.add(keyboard.Key.alt_l)
                elif part == 'cmd' or part == 'meta':
                    key_combo.add(keyboard.Key.cmd)
                elif len(part) == 1:
                    key_combo.add(keyboard.KeyCode.from_char(part))

            current_keys = set()

            def on_press(key):
                current_keys.add(key)
                if key_combo.issubset(current_keys):
                    print(f'\n🛑 ABORT HOTKEY PRESSED ({self.config.abort_hotkey})')
                    self._aborted = True

            def on_release(key):
                current_keys.discard(key)

            self._abort_listener = keyboard.Listener(on_press=on_press, on_release=on_release)
            self._abort_listener.start()
            logger.info(f'Abort hotkey listener active: {self.config.abort_hotkey}')

        except ImportError:
            logger.warning('pynput not installed — abort hotkey disabled.')
        except Exception as exc:
            logger.warning(f'Could not setup abort hotkey: {exc}')

    def _signal_handler(self, signum, frame) -> None:
        """Handle Ctrl+C / SIGINT for graceful shutdown and state writing."""
        if not getattr(self, '_is_running', False):
            # Not working (idle at REPL), so bubble up KeyboardInterrupt to exit
            raise KeyboardInterrupt()

        if getattr(self, '_aborted', False):
            print('\n\n🛑 Force quitting...')
            import sys
            sys.exit(1)

        print('\n\n🛑 Interrupted (Ctrl+C). Writing working state before exit... (Press Ctrl+C again to force quit)')
        self._aborted = True
        self._write_working_state_exit('abort', 'Interrupted by signal handler', self._current_in_flight_action, self._current_in_flight_file)

    def cancel_active_action(self) -> bool:
        """Cancel currently executing active action (e.g. stuck bash command)."""
        if hasattr(self, 'executor') and self.executor:
            return self.executor.cancel_active_action()
        return False

    def get_active_action_details(self) -> dict:
        """Get live status and details of in-flight action."""
        if hasattr(self, 'executor') and self.executor:
            return self.executor.get_active_action_details()
        return {"is_running": False}


    async def _get_human_confirmation(self, action_name: str, args: dict) -> bool:
        """Ask the human operator to confirm an action."""
        if self.on_event:
            self._confirm_future = asyncio.get_running_loop().create_future()
            self._emit('confirm_action', action=action_name, args=args)
            try:
                allow = await self._confirm_future
                return allow
            except asyncio.CancelledError:
                return False
            finally:
                self._confirm_future = None

        if not self.config.verbose and sys.stdin and sys.stdin.isatty():
            prompt_str = render_confirmation_prompt(action_name, args)
            self._emit('confirm_action', action=action_name, args=args)
            try:
                print(prompt_str, end='', flush=True)
                ans = ""
                try:
                    import termios, tty
                    fd = sys.stdin.fileno()
                    old_settings = termios.tcgetattr(fd)
                    try:
                        tty.setraw(fd)
                        ch = sys.stdin.read(1)
                        print(ch)
                        ans = ch.strip().lower()
                    finally:
                        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                except Exception:
                    ans = sys.stdin.readline().strip().lower()

                allow = ans in ('a', 'accept', 'y', 'yes', '')
                if not allow:
                    print("   ⏭️  Action declined.")
                return allow
            except (KeyboardInterrupt, EOFError):
                return False

        # Fallback to verbose or non-tty / GUI confirmation future
        print(f'\n{"=" * 50}')
        print(f'⚠️  ACTION REQUIRES CONFIRMATION')
        print(f'   Action: {action_name}')

        if action_name == 'run_bash':
            print(f'   Command: {args.get("command", "")}')
        elif action_name == 'write_file':
            path = args.get('path', '')
            content = args.get('content', '')
            print(f'   File: {path}')
            print(f'   Content length: {len(content)} chars')
        elif action_name == 'edit_file':
            print(f'   File: {args.get("path", "")}')
            print(f'   Replace: {args.get("old_text", "")[:100]}')
            print(f'   With: {args.get("new_text", "")[:100]}')
        elif action_name == 'git':
            print(f'   Subcommand: {args.get("subcommand", "")}')

        print(f'{"=" * 50}')

        self._emit('confirm_action', action=action_name, args=args)
        if sys.stdin and sys.stdin.isatty():
            try:
                print("[a]ccept / [d]ecline: ", end='', flush=True)
                ans = ""
                try:
                    import termios, tty
                    fd = sys.stdin.fileno()
                    old_settings = termios.tcgetattr(fd)
                    try:
                        tty.setraw(fd)
                        ch = sys.stdin.read(1)
                        print(ch)
                        ans = ch.strip().lower()
                    finally:
                        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                except Exception:
                    ans = sys.stdin.readline().strip().lower()
                return ans in ('a', 'accept', 'y', 'yes', '')
            except Exception:
                pass

        self._confirm_future = asyncio.get_running_loop().create_future()
        try:
            allow = await self._confirm_future
            return allow
        except asyncio.CancelledError:
            print('   🛑 Confirmation cancelled.')
            raise
        finally:
            self._confirm_future = None

    def set_confirmation_result(self, allow: bool) -> None:
        """Resolve pending confirmation future from TUI or GUI."""
        if self._confirm_future and not self._confirm_future.done():
            self._confirm_future.set_result(allow)

    async def _ask_user_question_async(self, question: str, options: list[str] | None = None) -> str:
        """Emit ask_user_question event and await user choice or custom text answer."""
        if options is None:
            options = []

        if self.on_event:
            self._question_future = asyncio.get_running_loop().create_future()
            self._emit('ask_user_question', question=question, options=options)
            try:
                answer = await self._question_future
                return answer
            except asyncio.CancelledError:
                return "User cancelled or declined to answer."
            finally:
                self._question_future = None

        # Fallback when on_event is None: check if interactive TTY
        if sys.stdin and sys.stdin.isatty():
            print(f"\n❓ AGENT QUESTION: {question}")
            if options:
                for idx, opt in enumerate(options, 1):
                    print(f"  {idx}. {opt}")
            print("Your answer: ", end="", flush=True)
            loop = asyncio.get_running_loop()
            try:
                line = await loop.run_in_executor(None, sys.stdin.readline)
                ans = line.strip()
                return ans if ans else "No response provided."
            except Exception:
                return "User input interrupted."

        # Non-interactive environment fallback
        return "Non-interactive environment: human question auto-skipped."

    def set_question_result(self, answer: str) -> None:
        """Resolve pending question future from TUI or GUI."""
        if hasattr(self, '_question_future') and self._question_future and not self._question_future.done():
            self._question_future.set_result(answer)

    # ── Observation ───────────────────────────────────────────────

    @staticmethod
    def _capture_desktop_file(save_path: str) -> str:
        """Take a desktop screenshot safely."""
        path = Path(save_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            import subprocess
            res = subprocess.run(["screencapture", "-x", str(path)], capture_output=True)
            if res.returncode == 0 and path.exists() and path.stat().st_size > 0:
                return str(path)
        except Exception:
            pass
        try:
            import pyautogui
            screenshot = pyautogui.screenshot()
            screenshot.save(str(path))
            return str(path)
        except Exception:
            return ""

    def _capture_observation_screenshot(self, step: int) -> str:
        """Capture and reference a desktop screenshot for the observation."""
        screenshot_path = str(
            Path(self.config.screenshot_dir) / f'step_{step}.png'
        )

        result = self._capture_desktop_file(screenshot_path)
        if result:
            return f'\n### Desktop Screenshot\nScreenshot saved at: {screenshot_path}\n'
        return ''

    # ── Persistence ───────────────────────────────────────────────

    def _save_step_history(self, path: str) -> None:
        """Save the full step history to a JSON file."""
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        records = [
            {
                'step': s.step,
                'thought': s.thought,
                'action': s.action,
                'args': s.args,
                'result': s.result[:1000],  # truncate large results
                'success': s.success,
                'timestamp': s.timestamp,
                'duration_ms': s.duration_ms,
            }
            for s in self._steps
        ]
        Path(path).write_text(json.dumps(records, indent=2))
