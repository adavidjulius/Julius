"""
Event bridge and handler dispatch for Julius TUI.

Guarantees:
1. 100% Event Exhaustiveness: Non-dropping coverage of all 22 JuliusEventType variants.
2. Single-Render Pipeline: An assistant response is rendered exactly once via clean Markdown.
3. Suppresses internal protocol action leaks (done, converse, finish, ask_human).
4. Suppresses raw 'Output:' blocks and internal result strings.
5. Aggregates tool executions into quiet, collapsible ToolSummary items.
"""

from __future__ import annotations

import json
import time
import re
from typing import Any, Dict, Optional, Callable
from rich.text import Text

from .state import SessionState, ToolExecutionRecord
from .components.message import AssistantMessage, UserMessage, ThinkingDot
from .components.tool_summary import ToolSummary
from ..agent_prompts import is_json_or_protocol

_EMOJI_MAP = {
    '✅': '[DONE]',
    '✔': '[DONE]',
    '☑': '[DONE]',
    '❌': '[FAIL]',
    '✖': '[FAIL]',
    '✗': '[FAIL]',
    '⚠️': '[!]',
    '⚡': '[!]',
    '💡': '[INFO]',
    '🚀': '[RUN]',
    '📦': '[PKG]',
    '🔒': '[LOCK]',
    '🔍': '[FIND]',
    '🔎': '[FIND]',
    '🤖': '[AI]',
}
_EMOJI_PATTERN = re.compile(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F700-\U0001F77F\U0001F780-\U0001F7FF\U0001F800-\U0001F8FF\U0001F900-\U0001F9FF\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF\U00002600-\U000026FF\U00002700-\U000027BF]')


def sanitize_terminal_emojis(text: str) -> str:
    """Replace common status emojis with clean ASCII and strip decorative ones to preserve column alignment."""
    if not isinstance(text, str) or not text:
        return text or ""
    res = text
    for emoji_char, ascii_replacement in _EMOJI_MAP.items():
        if emoji_char in res:
            res = res.replace(emoji_char, ascii_replacement)
    res = _EMOJI_PATTERN.sub('', res)
    return res


def _clean_field_text(val: Any, field_name: str) -> str:
    """Extract clean text field from raw strings without truncating on internal quotes."""
    if not isinstance(val, str):
        return sanitize_terminal_emojis(str(val)) if val is not None else ""
    trimmed = val.strip()
    result_text = val
    if trimmed.startswith(('{', 'json{', '```json', '```')) or is_json_or_protocol(trimmed):
        try:
            cleaned = trimmed.strip('`').strip()
            if cleaned.startswith('json'):
                cleaned = cleaned[4:].strip()
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict):
                # 1. Direct field match
                if field_name in parsed and parsed[field_name]:
                    return sanitize_terminal_emojis(str(parsed[field_name]))
                if "args" in parsed and isinstance(parsed["args"], dict) and field_name in parsed["args"] and parsed["args"][field_name]:
                    return sanitize_terminal_emojis(str(parsed["args"][field_name]))
                # 2. Check alternative text fields
                for alt in ("summary", "message", "answer", "text", "response"):
                    if alt in parsed and parsed[alt]:
                        return sanitize_terminal_emojis(str(parsed[alt]))
                    if "args" in parsed and isinstance(parsed["args"], dict) and alt in parsed["args"] and parsed["args"][alt]:
                        return sanitize_terminal_emojis(str(parsed["args"][alt]))
                # 3. Check actions list for commands or summary
                if "actions" in parsed and isinstance(parsed["actions"], list):
                    for a in parsed["actions"]:
                        if isinstance(a, dict):
                            a_args = a.get("args") or a.get("arguments") or {}
                            if isinstance(a_args, dict):
                                if "summary" in a_args:
                                    return sanitize_terminal_emojis(str(a_args["summary"]))
                                if "message" in a_args:
                                    return sanitize_terminal_emojis(str(a_args["message"]))
                                if "command" in a_args or "cmd" in a_args:
                                    cmd = a_args.get("command") or a_args.get("cmd")
                                    return sanitize_terminal_emojis(f"Executed command: {cmd}")
                # 4. Single command in args
                if "args" in parsed and isinstance(parsed["args"], dict):
                    cmd = parsed["args"].get("command") or parsed["args"].get("cmd")
                    if cmd:
                        return sanitize_terminal_emojis(f"Executed command: {cmd}")
                # 5. Fallback to thought if available
                th = (parsed.get("thought") or "").strip()
                if th and not any(kw in th.lower() for kw in ("executing", "running", "finding", "bash")):
                    return sanitize_terminal_emojis(th)
        except Exception:
            pass
        m = re.search(rf'"{field_name}"\s*:\s*"((?:[^"\\]|\\.)*)"', val, re.DOTALL)
        if m:
            result_text = m.group(1).replace('\\"', '"').replace('\\n', '\n').replace('\\\\', '\\')
            return sanitize_terminal_emojis(result_text)
        # If still raw JSON, do not dump raw braces to user
        m_cmd = re.search(r'["\'](?:cmd|command)["\']\s*:\s*["\']([^"\']+)["\']', val)
        if m_cmd:
            return sanitize_terminal_emojis(f"Executed command: {m_cmd.group(1)}")
        return "Task step executed."
    return sanitize_terminal_emojis(result_text)


class EventBridge:
    """Dispatches backend agent events to UI widgets and session state."""

    def __init__(
        self,
        session_state: SessionState,
        post_message_callback: Callable[[Any], None],
        update_status_callback: Callable[[str], None],
    ) -> None:
        self.state = session_state
        self.post_message = post_message_callback
        self.update_status = update_status_callback

        self._active_assistant_msg: Optional[AssistantMessage] = None
        self._active_tool_name: str = ""
        self._active_tool_start_time: float = 0.0
        self._active_tool_args: Dict[str, Any] = {}
        self._pending_tools: Dict[str, Dict[str, Any]] = {}
        self._has_finalized_turn: bool = False

    def handle_event(self, event: Dict[str, Any]) -> None:
        """Route event strictly according to event_type with 100% coverage."""
        event_type = event.get("type", "")

        # 1. thought
        if event_type == "thought":
            thought_text = event.get("text") or event.get("thought") or ""
            if thought_text:
                self.post_message({"kind": "thought", "thought": sanitize_terminal_emojis(thought_text)})

        # 2. ask_user_question
        elif event_type == "ask_user_question":
            question = event.get("question", "Clarification requested.")
            options = event.get("options", [])
            self.update_status("Waiting for clarification")
            self.post_message({"kind": "ask_user_question", "question": question, "options": options})

        # 3. confirm_action
        elif event_type == "confirm_action":
            action_name = event.get("action") or event.get("name") or "action"
            args = event.get("args", {})
            self.update_status(f"Confirm action: {action_name}")
            self.post_message({"kind": "confirm_action", "action": action_name, "args": args})

        # 4. action
        elif event_type == "action":
            action_name = event.get("name") or event.get("action") or ""
            args = event.get("args", {})
            act_id = str(event.get("id") or "")

            # Suppress internal protocol actions
            if str(action_name).lower() in ("done", "converse", "finish", "ask_human", "none", "chat", "message"):
                return

            self._active_tool_name = action_name
            self._active_tool_start_time = time.time()
            self._active_tool_args = args

            tool_info = {
                "name": action_name,
                "args": args,
                "start_time": time.time(),
            }
            if act_id:
                self._pending_tools[act_id] = tool_info
            self._pending_tools[f"t_{len(self._pending_tools)}"] = tool_info

            cmd_preview = args.get("command", "") or (f"{action_name} {args.get('path', '')}" if args.get('path') else action_name)
            self.post_message({
                "kind": "action_scheduled",
                "action": action_name,
                "args": args,
                "command": cmd_preview,
            })

            # Record file modifications for Ledger
            if action_name in ("write_file", "edit_file", "multi_edit"):
                p = args.get("path", "")
                if p:
                    self.state.record_file_modification(p)

            # Update quiet status
            if action_name == "run_bash":
                cmd = args.get("command", "")
                self.update_status(f"Running {cmd[:30]}…")
            elif action_name in ("read_file", "write_file", "edit_file", "multi_edit"):
                p = args.get("path", "")
                self.update_status(f"{action_name.replace('_', ' ').title()} {p[:25]}…")
            elif action_name == "search_files":
                pat = args.get("pattern") or args.get("query") or ""
                self.update_status(f"Search files {pat[:25]}…")
            elif action_name == "glob":
                self.update_status(f"Glob {args.get('pattern', '')[:25]}…")
            elif action_name == "run_tests":
                self.update_status("Running tests…")
            elif action_name == "run_python":
                self.update_status("Running Python…")
            elif action_name == "todo":
                self.update_status("Task checklist…")
            elif action_name == "checkpoint":
                self.update_status(f"Checkpoint {args.get('action', '')}…")
            elif action_name == "fetch_url":
                self.update_status(f"Fetch {args.get('url', '')[:25]}…")
            else:
                self.update_status(f"Tool: {action_name}")

        # 5. status
        elif event_type == "status":
            msg = event.get("message", "")
            if msg:
                m_low = msg.lower()
                _suppress = (
                    "connected to" in m_low
                    or "connecting to" in m_low
                    or "reusing" in m_low
                    or "session" in m_low
                )
                if not _suppress:
                    self.update_status(msg)

        # 6. step_start
        elif event_type == "step_start":
            step = event.get("step", 1)
            max_steps = event.get("max_steps", 0)
            self.state.current_step = step
            self.state.max_steps = max_steps
            # Do not display step count at the bottom; preserve command and execution details

        # 7. stream
        elif event_type == "stream":
            text = event.get("text", "")
            if text:
                self.state.token_count += max(1, len(text) // 4)
                clean_chunk = sanitize_terminal_emojis(text.replace('\\n', '\n'))
                if not is_json_or_protocol(clean_chunk) and not re.fullmatch(r'(?:\\[nrt]|[\s])+', clean_chunk):
                    self.post_message({"kind": "stream_chunk", "chunk": clean_chunk})

        # 8. stream_end
        elif event_type == "stream_end":
            self.post_message({"kind": "stream_end"})

        # 9. error
        elif event_type == "error":
            if not self._has_finalized_turn:
                self._has_finalized_turn = True
                msg = event.get("message", "An unexpected error occurred.")
                self.state.is_working = False
                self.update_status("Error")
                self.post_message({"kind": "error", "message": msg})

        # 10. result
        elif event_type == "result":
            out = event.get("output") or event.get("result") or ""
            out_str = str(out).strip()
            # Suppress internal protocol results
            if out_str.startswith("Task completed:") or out_str.startswith("Conversation recorded:"):
                return

            succ = event.get("success", True)
            act_id = str(event.get("id") or "")

            # Look up pending tool info
            pending = None
            if act_id and act_id in self._pending_tools:
                pending = self._pending_tools.pop(act_id)
            elif event.get("name") and event["name"] in self._pending_tools:
                pending = self._pending_tools.pop(event["name"])
            elif self._pending_tools:
                first_k = next(iter(self._pending_tools))
                pending = self._pending_tools.pop(first_k)

            tool_name = (
                event.get("name")
                or event.get("action")
                or (pending and pending.get("name"))
                or self._active_tool_name
                or "tool"
            )

            # Suppress internal protocol actions and conversational responses from tool records
            if str(tool_name).lower() in ("done", "converse", "finish", "ask_human", "none", "chat", "message"):
                return
            args = (
                event.get("args")
                or (pending and pending.get("args"))
                or self._active_tool_args
                or {}
            )
            t_start = (pending and pending.get("start_time")) or self._active_tool_start_time
            ev_dur = event.get("duration_s") or (event.get("duration_ms", 0) / 1000.0)
            if ev_dur and ev_dur > 0:
                duration = max(0.1, float(ev_dur))
            elif t_start > 0:
                duration = max(0.1, time.time() - t_start)
            else:
                duration = max(0.1, time.time() - getattr(self, "_turn_start_time", time.time()))

            # Build detailed command and human-friendly tool summary line
            raw_command = ""
            if tool_name == "run_bash":
                cmd = args.get("command", "")
                raw_command = cmd
                summary = f"Ran bash: {cmd[:45]}"
            elif tool_name in ("read_file", "write_file", "edit_file", "multi_edit"):
                p = args.get("path", "")
                raw_command = f"{tool_name}(path={p!r})"
                summary = f"{tool_name.replace('_', ' ').capitalize()} {p}"
            elif tool_name == "search_files":
                pattern = args.get("pattern") or args.get("query") or ""
                path = args.get("path") or "."
                raw_command = f"search_files(pattern={pattern!r}, path={path!r})"
                summary = f"Executed search_files ({pattern})" if pattern else "Executed search_files"
            elif tool_name == "glob":
                pat = args.get("pattern", "")
                raw_command = f"glob(pattern={pat!r})"
                summary = f"Glob {pat}"
            elif tool_name == "git":
                sub = args.get("subcommand", "")
                raw_command = f"git {sub}"
                summary = f"Git {sub[:40]}"
            elif tool_name == "run_tests":
                cmd = args.get("command") or "pytest"
                raw_command = cmd
                summary = f"Ran tests ({cmd})"
            elif tool_name == "run_python":
                code = args.get("code") or args.get("command") or ""
                raw_command = code
                summary = "Ran Python snippet"
            elif tool_name == "todo":
                raw_command = "todo"
                summary = "Updated task checklist"
            elif tool_name == "checkpoint":
                act = args.get("action", "")
                raw_command = f"checkpoint({act!r})"
                summary = f"Checkpoint {act}"
            elif tool_name == "fetch_url":
                u = args.get("url", "")
                raw_command = f"fetch_url({u!r})"
                summary = f"Fetched {u[:35]}"
            elif tool_name in ("read_symbol", "list_symbols"):
                p = args.get("path", "")
                sym = args.get("symbol", "")
                raw_command = f"{tool_name}(path={p!r}, symbol={sym!r})"
                summary = f"Read symbol {sym}" if sym else f"List symbols {p}"
            else:
                raw_command = f"{tool_name}({args})"
                summary = f"Executed {tool_name.replace('_', ' ')}"

            self.state.record_tool(
                tool_name=tool_name,
                summary=summary,
                duration_s=duration,
                success=succ,
                command=raw_command,
                args=args,
                output=out_str,
            )
            self.post_message({
                "kind": "tool_completed",
                "tool_name": tool_name,
                "command": raw_command,
                "summary": summary,
                "output": out_str[:4000],
                "duration_s": duration,
                "success": succ,
            })
            self._active_tool_name = ""
            self._active_tool_start_time = 0.0

        # 11. heal_start
        elif event_type == "heal_start":
            cmd = event.get("command", "")
            self.state.record_tool("self_healer", f"Diagnosing failure for '{cmd[:30]}'", 0.3, True)

        # 12. heal_step
        elif event_type == "heal_step":
            att = event.get("attempt", 1)
            self.update_status(f"Self-healing attempt {att}")

        # 13. heal_success
        elif event_type == "heal_success":
            sum_txt = event.get("summary", "Self-healed")
            self.state.record_tool("self_healer", f"Healed: {sum_txt[:40]}", 0.5, True)

        # 14. heal_failed
        elif event_type == "heal_failed":
            sum_txt = event.get("summary", "Healing failed")
            self.state.record_tool("self_healer", f"Heal failed: {sum_txt[:40]}", 0.5, False)

        # 15. done
        elif event_type == "done":
            if not self._has_finalized_turn:
                self._has_finalized_turn = True
                turn_dur = max(0.1, time.time() - getattr(self, "_turn_start_time", time.time()))
                summary = event.get("summary", "Task complete.")
                summary = _clean_field_text(summary, "summary")
                if (not summary or summary.strip() in ("Task complete.", "Task completed.", "Done.", "Finished.")) and self.state.current_turn_tools:
                    real_tools = [t for t in self.state.current_turn_tools if t.tool_name not in ("done", "converse", "ask_human")]
                    if real_tools:
                        summary = f"Executed {len(real_tools)} action(s):\n" + "\n".join(f"• {t.summary or t.tool_name}" for t in real_tools)
                self.state.finish_turn(summary)
                self.post_message({"kind": "done", "summary": summary, "tools": list(self.state.current_turn_tools), "duration_s": turn_dur})

        # 16. converse
        elif event_type == "converse":
            if not self._has_finalized_turn:
                self._has_finalized_turn = True
                turn_dur = max(0.1, time.time() - getattr(self, "_turn_start_time", time.time()))
                msg = event.get("message", "")
                msg = _clean_field_text(msg, "message")
                self.state.finish_turn(msg)
                self.post_message({"kind": "converse", "message": msg, "tools": list(self.state.current_turn_tools), "duration_s": turn_dur})

        # 17. finished
        elif event_type == "finished":
            succ = event.get("success", True)
            summary = event.get("summary", "")
            self.state.is_working = False
            self.update_status("")
            if not succ and not self._has_finalized_turn:
                self._has_finalized_turn = True
                self.post_message({"kind": "finished_failure", "summary": summary or "Task failed."})

        # 18. pipeline
        elif event_type == "pipeline":
            stage = event.get("stage", "builder")
            msg = event.get("message", "")
            self.update_status(f"Pipeline: {stage} - {msg}")

        # 19. plan_approval_requested
        elif event_type == "plan_approval_requested":
            plan = event.get("plan", "")
            self.post_message({"kind": "plan_approval", "plan": plan})

        # 20. music_progress
        elif event_type == "music_progress":
            msg = event.get("message", "")
            self.update_status(f"Music: {msg[:30]}")

        # 21. whatsapp_status
        elif event_type == "whatsapp_status":
            st = event.get("data", "")
            self.update_status(f"WhatsApp: {st}")

        # 22. whatsapp_message
        elif event_type == "whatsapp_message":
            self.post_message({"kind": "whatsapp_message", "data": event.get("data", {})})

        # 23. whatsapp_approval
        elif event_type == "whatsapp_approval":
            self.post_message({"kind": "whatsapp_approval", "data": event.get("data", {})})

    def start_turn(self) -> None:
        """Call when user submits prompt to reset turn state."""
        self.state.reset_turn()
        self._turn_start_time = time.time()
        self._has_finalized_turn = False
        self._active_tool_name = ""
        self._active_tool_start_time = 0.0
        self._pending_tools.clear()
