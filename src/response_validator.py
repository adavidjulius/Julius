"""Structural validator for LLM action responses.

Validates that parsed JSON from the LLM matches the expected action schema
before it reaches the action dispatch layer. This is a safety net against
malformed responses — not a deep type validator.

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

# ── Per-action required argument keys ─────────────────────────────────────────
# These define the MINIMUM required args for each action.
# Optional args (like start_line/end_line for read_file) are not enforced.

ACTION_ARG_SCHEMAS: dict[str, set[str]] = {
    # Core actions
    'run_bash':                {'command'},
    'read_file':               {'path'},
    'write_file':              {'path', 'content'},
    'edit_file':               {'path', 'old_text', 'new_text'},
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

            args = item.get('args', {})
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
                    return False, f'Action "{action_name}" has a null value for required arg "{arg_name}".'

            item_id = str(item.get('id') or f'a{idx}')
            if item_id in seen_ids:
                return False, f'Duplicate action id: {item_id}'
            seen_ids.add(item_id)

            if mode == 'parallel' and action_name in ('write_file', 'edit_file', 'multi_edit'):
                target_path = args.get('path')
                if target_path:
                    if target_path in written_paths:
                        return False, f'Two writes to {target_path} in one parallel batch.'
                    written_paths.add(target_path)

        if len(items) > 1 and any(i.get('action') in TERMINAL_ACTIONS for i in items):
            return False, 'Terminal actions (done, converse, ask_human) must be sent alone'

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

    args = data.get('args', {})
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
