"""Structural validator for LLM action responses.

Validates that parsed JSON from the LLM matches the expected action schema
before it reaches the action dispatch layer. This is a safety net against
malformed responses with automatic self-healing for common model variances.

Supports both Julius 1.0 (single action: Shape A) and Julius 2.0 (batch: Shape B).
"""

from __future__ import annotations

from typing import Any
from .agent_prompts import (
    CORE_ACTIONS,
    EXTENDED_ACTIONS,
    VALID_ACTIONS,
    TERMINAL_ACTIONS,
    MAX_PARALLEL_ACTIONS,
)

# ── Required top-level keys for single action response ────────────────────────
REQUIRED_KEYS: frozenset[str] = frozenset({'thought', 'action', 'args'})

# ── Action Synonyms & Aliases for Resilient Model Interoperability ──────────────
ACTION_SYNONYMS: dict[str, str] = {
    # Conversational / informative aliases
    'answer': 'converse',
    'reply': 'converse',
    'respond': 'converse',
    'say': 'converse',
    'chat': 'converse',
    'message': 'converse',
    'explain': 'converse',
    'tell': 'converse',
    'info': 'converse',
    'information': 'converse',
    'talk': 'converse',
    'speak': 'converse',
    # Completion aliases
    'finish': 'done',
    'complete': 'done',
    'completed': 'done',
    'final': 'done',
    'stop': 'done',
    'end': 'done',
    'exit': 'done',
    'terminate': 'done',
    # Human interaction aliases
    'ask': 'ask_human',
    'question': 'ask_human',
    'prompt_user': 'ask_human',
    'user_question': 'ask_human',
    'askuserquestion': 'ask_human',
    # Shell execution aliases
    'bash': 'run_bash',
    'sh': 'run_bash',
    'shell': 'run_bash',
    'cmd': 'run_bash',
    'command': 'run_bash',
    'exec': 'run_bash',
    'terminal': 'run_bash',
    # File operation aliases
    'read': 'read_file',
    'cat': 'read_file',
    'view': 'read_file',
    'write': 'write_file',
    'save': 'write_file',
    'create': 'write_file',
    'edit': 'edit_file',
    'patch': 'edit_file',
    'replace': 'edit_file',
    'list_directory': 'list_dir',
    'ls': 'list_dir',
    'dir': 'list_dir',
    'search': 'search_files',
    'grep': 'search_files',
    'find': 'search_files',
    'find_files': 'glob',
    # Deletion aliases
    'delete': 'delete_file',
    'delete_file': 'delete_file',
    'remove': 'delete_file',
    'remove_file': 'delete_file',
    'rm': 'delete_file',
    'unlink': 'delete_file',
}

# ── Per-action required argument keys ─────────────────────────────────────────
ACTION_ARG_SCHEMAS: dict[str, set[str]] = {
    # Core actions
    'run_bash':                {'command'},
    'read_file':               {'path'},
    'write_file':              {'path', 'content'},
    'edit_file':               {'path', 'old_text', 'new_text'},
    'delete_file':             {'path'},
    'remove_file':             {'path'},
    'list_dir':                {'path'},
    'search_files':            {'pattern'},
    'search_semantic':         {'query'},
    'git':                     {'subcommand'},
    'list_symbols':            {'path'},
    'read_symbol':             {'path', 'symbol'},
    'ask_human':               {'question'},
    'done':                    {'summary'},
    'converse':                {'message'},
    # Extended actions
    'multi_edit':              {'path', 'edits'},
    'glob':                    {'pattern'},
    'run_tests':               set(),
    'todo':                    {'items'},
    'checkpoint':              {'action'},
    'fetch_url':               {'url'},
    'run_python':              {'code'},
    # Canonical & Deferred Tool Names
    'Bash':                    {'command'},
    'Read':                    {'file_path'},
    'Write':                   {'file_path', 'content'},
    'Edit':                    {'file_path', 'old_string', 'new_string'},
    'Glob':                    {'pattern'},
    'Grep':                    {'pattern'},
    'AskUserQuestion':         {'questions'},
    'ToolSearch':              {'query'},
    'Agent':                   {'prompt'},
    'Skill':                   {'skill'},
    'Workflow':                set(),
    'TaskCreate':              {'title'},
    'TaskGet':                 {'task_id'},
    'TaskUpdate':              {'task_id', 'status'},
    'TaskList':                set(),
    'TaskStop':                {'task_id'},
    'NotebookEdit':            {'notebook_path'},
    'ReportFindings':          {'findings'},
    'ScheduleWakeup':          set(),
    'EnterWorktree':           set(),
    'ExitWorktree':            set(),
    # Multimodal & System Mastery Actions
    'capture_screen':          set(),
    'CaptureScreen':           set(),
    'get_active_window':       set(),
    'GetActiveWindow':         set(),
    'get_system_vitals':       set(),
    'GetSystemVitals':         set(),
    'send_system_notification': {'title', 'message'},
    'SendSystemNotification':  {'title', 'message'},
    'manage_clipboard':        {'action'},
    'ManageClipboard':         {'action'},
    'app_control':             {'action'},
    'AppControl':              {'action'},
    'run_teamwork':            {'goal'},
    'RunTeamwork':             {'goal'},
    'generate_image':          {'prompt'},
    'GenerateImage':           {'prompt'},
    'analyze_image':           {'image_path'},
    'AnalyzeImage':            {'image_path'},
    # Music actions
    'import_spotify_playlist': {'playlist_url'},
    'music_status':            {'job_id'},
    'music_retry':             {'job_id'},
    'music_cancel':            {'job_id'},
    'music_library':           set(),
    # CapCut actions
    'capcut_list_projects':            set(),
    'capcut_get_project':              {'project_name'},
    'capcut_create_project':           {'project_name'},
    'capcut_set_canvas':               {'project_name'},
    'capcut_add_video_clip':           {'project_name', 'file_path'},
    'capcut_add_audio_clip':           {'project_name', 'file_path'},
    'capcut_add_image':                {'project_name', 'file_path'},
    'capcut_add_text':                 {'project_name', 'text'},
    'capcut_add_keyframe':             {'project_name'},
    'capcut_add_sticker':              {'project_name'},
    'capcut_get_media_duration':       {'file_path'},
    'capcut_save_draft':               {'project_name'},
    'capcut_import_srt':               {'project_name', 'srt_path'},
    'capcut_duplicate_project':        {'source_name', 'target_name'},
    'capcut_delete_project':           {'project_name'},
    'capcut_open_in_app':              set(),
    'capcut_fix_network_and_effects':  set(),
    'capcut_list_available_effects':   set(),
    'capcut_list_available_filters':   set(),
    'capcut_list_available_transitions': set(),
    'capcut_list_available_animations': set(),
    'capcut_add_effect':               {'project_name', 'effect_name'},
    'capcut_add_filter':               {'project_name', 'filter_name'},
    'capcut_add_transition':           {'project_name', 'transition_name'},
    'capcut_add_video_animation':       {'project_name', 'animation_name'},
    'capcut_list_pro_effects':         set(),
    'capcut_add_pro_effect':           {'project_name'},
    'capcut_unlock_all_pro_features':  set(),
    'capcut_split_clip':               {'project_name'},
    'capcut_trim_clip':                {'project_name'},
    'capcut_beat_sync_edit':           {'project_name'},
    'capcut_inspect_timeline_ui':      {'project_name'},
    # Sarvam & Remote actions
    'sarvam_translate':                {'text'},
    'sarvam_tts':                      {'text'},
    'sarvam_stt':                      {'audio_path'},
    'sarvam_ocr':                      set(),
    'run_remote':                      {'command'},
}


def _auto_heal_action_item(item: dict[str, Any]) -> dict[str, Any]:
    """Auto-heal structural variances, aliases, and argument mismatches in an action dict."""
    if not isinstance(item, dict):
        return item

    import json

    # 0. Strip transport / wrapper metadata
    for junk in ('requestor', 'recipient', 'role', 'type'):
        item.pop(junk, None)

    # 1. Ensure thought key exists
    if 'thought' not in item:
        item['thought'] = item.get('reasoning', '') or ''

    # 2. Hoist action name from alternative keys if missing
    if 'action' not in item:
        for alt_k in ('tool', 'function', 'name', 'call'):
            if alt_k in item and isinstance(item[alt_k], str):
                item['action'] = item.pop(alt_k)
                break

    # 3. Detect conversational or command intent if action is still missing
    if 'action' not in item and 'actions' not in item:
        if any(k in item for k in ('message', 'answer', 'response', 'text', 'reply')):
            item['action'] = 'converse'
            msg = item.get('message') or item.get('answer') or item.get('response') or item.get('text') or item.get('reply') or ''
            item['args'] = {'message': msg}
        elif 'summary' in item:
            item['action'] = 'done'
            item['args'] = {'summary': item['summary']}
        elif 'command' in item or 'cmd' in item:
            item['action'] = 'run_bash'
            item['args'] = {'command': item.get('command') or item.get('cmd')}

    # 4. Normalize action name aliases
    action = item.get('action')
    if isinstance(action, str) and action:
        cleaned_act = action.strip()
        lower_act = cleaned_act.lower()
        if lower_act in ACTION_SYNONYMS:
            action = ACTION_SYNONYMS[lower_act]
            item['action'] = action
        else:
            item['action'] = cleaned_act

    # 5. Hoist 'arguments', 'parameters', 'params' into 'args'
    if 'args' not in item or not isinstance(item.get('args'), dict):
        for alt_arg in ('arguments', 'parameters', 'params'):
            if alt_arg in item:
                val = item.pop(alt_arg)
                if isinstance(val, str):
                    try:
                        val = json.loads(val)
                    except Exception:
                        pass
                if isinstance(val, dict):
                    item['args'] = val
                    break

    # 6. Parse args if it's a JSON string
    if isinstance(item.get('args'), str):
        try:
            item['args'] = json.loads(item['args'])
        except Exception:
            pass

    # 7. Hoist flat arguments into args dictionary if still missing
    if 'action' in item and ('args' not in item or not isinstance(item.get('args'), dict)):
        args = {k: v for k, v in item.items() if k not in ('action', 'thought', 'actions', 'mode', 'id')}
        item['args'] = args

    # 8. Unwrap nested arguments / parameters if args was wrapped as {"arguments": {...}}
    args = item.get('args')
    if isinstance(args, dict):
        for sub_k in ('arguments', 'parameters', 'params'):
            if sub_k in args and isinstance(args[sub_k], dict) and len(args) == 1:
                item['args'] = args[sub_k]
                args = item['args']
                break

    # 9. Normalize per-action argument keys
    if isinstance(args, dict) and 'action' in item:
        act = item['action']
        if act == 'done':
            if 'summary' not in args:
                for alt in ('message', 'text', 'answer', 'response', 'result', 'output', 'content'):
                    if alt in args and args[alt]:
                        args['summary'] = str(args[alt])
                        break
                if 'summary' not in args:
                    args['summary'] = 'Task completed.'
        elif act == 'converse':
            if 'message' not in args:
                for alt in ('summary', 'text', 'answer', 'response', 'result', 'output', 'content', 'reply'):
                    if alt in args and args[alt]:
                        args['message'] = str(args[alt])
                        break
                if 'message' not in args:
                    args['message'] = ''
        elif act == 'ask_human':
            if 'question' not in args:
                for alt in ('message', 'prompt', 'text', 'query'):
                    if alt in args and args[alt]:
                        args['question'] = str(args[alt])
                        break
                if 'question' not in args:
                    args['question'] = 'Clarification requested.'
        elif act in ('run_bash', 'Bash'):
            if 'command' not in args:
                for alt in ('cmd', 'command_line', 'script', 'exec', 'code'):
                    if alt in args and args[alt]:
                        args['command'] = str(args[alt])
                        break
        elif act in ('read_file', 'write_file', 'edit_file', 'list_dir', 'delete_file', 'remove_file'):
            if 'path' not in args:
                for alt in ('file_path', 'filepath', 'file', 'target', 'directory', 'dir', 'path_name'):
                    if alt in args:
                        args['path'] = args[alt]
                        break
        elif act in ('Read', 'Write', 'Edit'):
            if 'file_path' not in args and 'path' in args:
                args['file_path'] = args['path']
            if act == 'Edit':
                if 'old_string' not in args and 'old_text' in args:
                    args['old_string'] = args['old_text']
                if 'new_string' not in args and 'new_text' in args:
                    args['new_string'] = args['new_text']
        elif act in ('search_files', 'Grep'):
            if 'pattern' not in args:
                for alt in ('query', 'text', 'regex', 'keyword', 'term'):
                    if alt in args:
                        args['pattern'] = args[alt]
                        break

    return item

    return item


def validate_action(data: dict[str, Any]) -> tuple[bool, str]:
    """
    Validate an action dict against the expected schema.

    Supports:
    - Shape A: {"thought": "...", "action": "...", "args": {...}}
    - Shape B: {"thought": "...", "actions": [...], "mode": "parallel"|"sequential"}

    Returns:
        A tuple of (is_valid, error_message).
        If is_valid is True, error_message is an empty string.
    """
    if not isinstance(data, dict):
        return False, 'Response is not a JSON object.'

    # Check thought
    if 'thought' not in data:
        return False, "Missing required top-level key: 'thought'"

    has_action = 'action' in data
    has_actions = 'actions' in data

    if has_action and has_actions:
        return False, 'Use either "action" or "actions", not both'

    if not has_action and not has_actions:
        missing_keys = REQUIRED_KEYS - set(data.keys())
        return False, f'Missing required top-level keys: {sorted(missing_keys)}'

    # Shape B — Batch
    if has_actions:
        items = data['actions']
        if not isinstance(items, list) or not items:
            return False, 'The "actions" field must be a non-empty list.'
        if len(items) > MAX_PARALLEL_ACTIONS:
            return False, f'At most {MAX_PARALLEL_ACTIONS} actions per batch, got {len(items)}.'

        mode = data.get('mode', 'parallel')
        if mode not in ('parallel', 'sequential'):
            return False, f'Invalid mode: {mode!r}. Must be "parallel" or "sequential".'

        seen_ids: set[str] = set()
        written_paths: set[str] = set()

        for idx, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                return False, f'Action item {idx} must be a JSON object.'

            action_name = item.get('action')
            if not isinstance(action_name, str) or not action_name:
                return False, f'Action item {idx} must have a non-empty string "action".'

            if action_name not in ACTION_ARG_SCHEMAS:
                return False, (
                    f'Unknown action: "{action_name}". '
                    f'Valid actions: {", ".join(sorted(ACTION_ARG_SCHEMAS.keys()))}'
                )

            args = item.get('args')
            if not isinstance(args, dict):
                return False, f'Action item {idx} "args" must be a JSON object, got {type(args).__name__}.'

            req_args = ACTION_ARG_SCHEMAS[action_name]
            missing = req_args - set(args.keys())
            if missing:
                return False, (
                    f'Action "{action_name}" is missing required argument(s): {sorted(missing)}. '
                    f'Required: {sorted(req_args)}'
                )

            for arg_name in req_args:
                if args[arg_name] is None:
                    return False, f'Action item {idx} "{action_name}" has a null value for required arg "{arg_name}".'

            item_id = str(item.get('id') or f'a{idx}')
            if item_id in seen_ids:
                return False, f'Duplicate action id "{item_id}" in batch.'
            seen_ids.add(item_id)

            if mode == 'parallel' and action_name in ('write_file', 'edit_file', 'multi_edit'):
                target_path = args.get('path')
                if target_path:
                    if target_path in written_paths:
                        return False, f'Two writes to {target_path} in one parallel batch.'
                    written_paths.add(target_path)

        if len(items) > 1 and any(i.get('action') in TERMINAL_ACTIONS for i in items):
            return False, 'Terminal actions (done, converse, ask_human) cannot be mixed with other actions in a batch.'

        return True, ''

    # Shape A — Single action
    missing_keys = REQUIRED_KEYS - set(data.keys())
    if missing_keys:
        return False, f'Missing required top-level keys: {sorted(missing_keys)}'

    action = data.get('action', '')
    if not isinstance(action, str) or not action:
        return False, 'The "action" field must be a non-empty string.'

    if action not in ACTION_ARG_SCHEMAS:
        return False, (
            f'Unknown action: "{action}". '
            f'Valid actions: {", ".join(sorted(ACTION_ARG_SCHEMAS.keys()))}'
        )

    args = data.get('args')
    if not isinstance(args, dict):
        return False, f'The "args" field must be a JSON object, got {type(args).__name__}.'

    required_args = ACTION_ARG_SCHEMAS[action]
    missing_args = required_args - set(args.keys())
    if missing_args:
        return False, (
            f'Action "{action}" is missing required argument(s): {sorted(missing_args)}. '
            f'Required: {sorted(required_args)}'
        )

    for arg_name in required_args:
        if args[arg_name] is None:
            return False, f'Action "{action}" has a null value for required arg "{arg_name}".'

    return True, ''
