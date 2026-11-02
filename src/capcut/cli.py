"""
CapCut Desktop Command-Line Interface for Julius.
Usage:
    python -m src.capcut.cli list
    python -m src.capcut.cli get <project_name>
    python -m src.capcut.cli create <project_name> [--width 1920] [--height 1080] [--fps 30]
    python -m src.capcut.cli add-video <project_name> <file_path> [--start 0.0] [--duration 5.0] [--speed 1.0] [--volume 1.0]
    python -m src.capcut.cli add-audio <project_name> <file_path> [--start 0.0] [--duration 5.0] [--volume 1.0]
    python -m src.capcut.cli add-text <project_name> <text> [--start 0.0] [--duration 3.0] [--size 15] [--color "#FFFFFF"]
    python -m src.capcut.cli import-srt <project_name> <srt_path>
    python -m src.capcut.cli duplicate <source_name> <target_name>
    python -m src.capcut.cli delete <project_name>
    python -m src.capcut.cli open [project_name]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure repo root is on sys.path
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.capcut.engine import get_capcut_engine


def main() -> None:
    parser = argparse.ArgumentParser(description="CapCut Desktop CLI controller for Julius")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # list
    subparsers.add_parser("list", help="List all CapCut projects")

    # get
    get_p = subparsers.add_parser("get", help="Get project timeline details")
    get_p.add_argument("project_name", help="Name of project to inspect")

    # create
    create_p = subparsers.add_parser("create", help="Create a new CapCut project draft")
    create_p.add_argument("project_name", help="Project name")
    create_p.add_argument("--ratio", default=None, help="Aspect ratio (e.g. 16:9, 9:16, 1:1, 4:3, 21:9)")
    create_p.add_argument("--width", type=int, default=None, help="Canvas width (default: 1920)")
    create_p.add_argument("--height", type=int, default=None, help="Canvas height (default: 1080)")
    create_p.add_argument("--fps", type=int, default=30, help="Framerate (default: 30)")
    create_p.add_argument("--no-replace", action="store_true", help="Disallow overwriting existing draft")

    # set-canvas
    canvas_p = subparsers.add_parser("set-canvas", help="Set canvas aspect ratio and resolution")
    canvas_p.add_argument("project_name", help="Project name")
    canvas_p.add_argument("--ratio", default=None, help="Aspect ratio (e.g. 16:9, 9:16, 1:1, 4:3, 21:9)")
    canvas_p.add_argument("--width", type=int, default=None, help="Canvas width in pixels")
    canvas_p.add_argument("--height", type=int, default=None, help="Canvas height in pixels")

    # add-video
    v_p = subparsers.add_parser("add-video", help="Add a video clip to timeline")
    v_p.add_argument("project_name", help="Project name")
    v_p.add_argument("file_path", help="Path to video file")
    v_p.add_argument("--start", type=float, default=0.0, help="Source start offset in seconds")
    v_p.add_argument("--duration", type=float, default=None, help="Clip duration in seconds")
    v_p.add_argument("--target-start", type=float, default=0.0, help="Timeline target start offset in seconds")
    v_p.add_argument("--speed", type=float, default=1.0, help="Playback speed multiplier")
    v_p.add_argument("--volume", type=float, default=1.0, help="Audio volume (0.0 to 1.0)")
    v_p.add_argument("--x", type=float, default=0.0, help="Horizontal position offset (-1.0 to 1.0)")
    v_p.add_argument("--y", type=float, default=0.0, help="Vertical position offset (-1.0 to 1.0)")
    v_p.add_argument("--scale-x", type=float, default=1.0, help="Scale factor X")
    v_p.add_argument("--scale-y", type=float, default=1.0, help="Scale factor Y")
    v_p.add_argument("--rotation", type=float, default=0.0, help="Rotation angle in degrees")
    v_p.add_argument("--alpha", type=float, default=1.0, help="Opacity (0.0 to 1.0)")
    v_p.add_argument("--fade-in", type=float, default=0.0, help="Audio fade-in duration in seconds")
    v_p.add_argument("--fade-out", type=float, default=0.0, help="Audio fade-out duration in seconds")
    v_p.add_argument("--transition", default=None, help="Transition name")
    v_p.add_argument("--transition-duration", type=float, default=0.5, help="Transition duration in seconds")
    v_p.add_argument("--track", default=None, help="Target track name")

    # add-image
    img_p = subparsers.add_parser("add-image", help="Add image overlay or photo to timeline")
    img_p.add_argument("project_name", help="Project name")
    img_p.add_argument("file_path", help="Path to image file")
    img_p.add_argument("--start", type=float, default=0.0, help="Source start offset in seconds")
    img_p.add_argument("--duration", type=float, default=3.0, help="Clip duration in seconds")
    img_p.add_argument("--target-start", type=float, default=0.0, help="Timeline target start in seconds")
    img_p.add_argument("--x", type=float, default=0.0, help="Horizontal position (-1.0 to 1.0)")
    img_p.add_argument("--y", type=float, default=0.0, help="Vertical position (-1.0 to 1.0)")
    img_p.add_argument("--scale-x", type=float, default=1.0, help="Scale factor X")
    img_p.add_argument("--scale-y", type=float, default=1.0, help="Scale factor Y")
    img_p.add_argument("--rotation", type=float, default=0.0, help="Rotation angle in degrees")
    img_p.add_argument("--alpha", type=float, default=1.0, help="Opacity (0.0 to 1.0)")
    img_p.add_argument("--track", default=None, help="Target track name")

    # add-audio
    a_p = subparsers.add_parser("add-audio", help="Add audio/music track to timeline")
    a_p.add_argument("project_name", help="Project name")
    a_p.add_argument("file_path", help="Path to audio file")
    a_p.add_argument("--start", type=float, default=0.0, help="Start offset in seconds")
    a_p.add_argument("--duration", type=float, default=None, help="Clip duration in seconds")
    a_p.add_argument("--target-start", type=float, default=0.0, help="Timeline target start in seconds")
    a_p.add_argument("--volume", type=float, default=1.0, help="Audio volume (0.0 to 1.0)")
    a_p.add_argument("--speed", type=float, default=1.0, help="Playback speed multiplier")
    a_p.add_argument("--fade-in", type=float, default=0.0, help="Fade-in duration in seconds")
    a_p.add_argument("--fade-out", type=float, default=0.0, help="Fade-out duration in seconds")
    a_p.add_argument("--track", default=None, help="Target track name")

    # add-text
    t_p = subparsers.add_parser("add-text", help="Add styled text overlay or caption to timeline")
    t_p.add_argument("project_name", help="Project name")
    t_p.add_argument("text", help="Text string")
    t_p.add_argument("--start", type=float, default=0.0, help="Start offset in seconds")
    t_p.add_argument("--duration", type=float, default=3.0, help="Display duration in seconds")
    t_p.add_argument("--target-start", type=float, default=None, help="Timeline target start in seconds")
    t_p.add_argument("--size", type=float, default=15.0, help="Font size in points")
    t_p.add_argument("--color", default="#FFFFFF", help="Hex color code (default #FFFFFF)")
    t_p.add_argument("--x", type=float, default=0.0, help="Horizontal position (-1.0 to 1.0)")
    t_p.add_argument("--y", type=float, default=-0.6, help="Vertical position (-1.0 to 1.0)")
    t_p.add_argument("--bold", action="store_true", help="Bold text style")
    t_p.add_argument("--italic", action="store_true", help="Italic text style")
    t_p.add_argument("--underline", action="store_true", help="Underline text style")
    t_p.add_argument("--align", type=int, default=1, choices=[0, 1, 2], help="Alignment: 0=left, 1=center, 2=right")
    t_p.add_argument("--bg-color", default=None, help="Background highlight hex color (e.g. #000000)")
    t_p.add_argument("--bg-alpha", type=float, default=0.8, help="Background opacity (0.0 to 1.0)")
    t_p.add_argument("--shadow", action="store_true", help="Enable text drop shadow")
    t_p.add_argument("--shadow-color", default="#000000", help="Shadow hex color")
    t_p.add_argument("--border", action="store_true", help="Enable text border / stroke")
    t_p.add_argument("--border-color", default="#000000", help="Border hex color")
    t_p.add_argument("--border-width", type=float, default=20.0, help="Border width")
    t_p.add_argument("--animation", default=None, help="Text animation name")
    t_p.add_argument("--anim-duration", type=float, default=0.5, help="Animation duration in seconds")

    # add-keyframe
    kf_p = subparsers.add_parser("add-keyframe", help="Add keyframe animation interpolation")
    kf_p.add_argument("project_name", help="Project name")
    kf_p.add_argument("--properties", required=True, help="Comma-separated properties (e.g. position_x,scale_x)")
    kf_p.add_argument("--times", required=True, help="Comma-separated time offsets in seconds (e.g. 0.0,1.5)")
    kf_p.add_argument("--values", required=True, help="Comma-separated values (e.g. 0.0,0.5)")
    kf_p.add_argument("--track-type", default="video", choices=["video", "audio", "text"], help="Track type")
    kf_p.add_argument("--track-index", type=int, default=0, help="Track index (0-based)")
    kf_p.add_argument("--segment-index", type=int, default=0, help="Segment index (0-based)")

    # add-sticker
    stk_p = subparsers.add_parser("add-sticker", help="Add decorative sticker to timeline")
    stk_p.add_argument("project_name", help="Project name")
    stk_p.add_argument("resource_id", help="Sticker resource ID or identifier")
    stk_p.add_argument("--start", type=float, default=0.0, help="Start offset in seconds")
    stk_p.add_argument("--duration", type=float, default=3.0, help="Duration in seconds")
    stk_p.add_argument("--target-start", type=float, default=None, help="Timeline target start in seconds")
    stk_p.add_argument("--x", type=float, default=0.0, help="Horizontal position (-1.0 to 1.0)")
    stk_p.add_argument("--y", type=float, default=0.0, help="Vertical position (-1.0 to 1.0)")
    stk_p.add_argument("--scale-x", type=float, default=1.0, help="Scale factor X")
    stk_p.add_argument("--scale-y", type=float, default=1.0, help="Scale factor Y")
    stk_p.add_argument("--rotation", type=float, default=0.0, help="Rotation angle in degrees")
    stk_p.add_argument("--alpha", type=float, default=1.0, help="Opacity (0.0 to 1.0)")
    stk_p.add_argument("--track", default="sticker_main", help="Target track name")

    # media-info
    info_p = subparsers.add_parser("media-info", help="Extract video/audio media metadata with ffprobe")
    info_p.add_argument("file_path", help="Path to video or audio file")

    # save-draft
    save_p = subparsers.add_parser("save-draft", help="Synchronize, generate cover thumbnail, and save draft")
    save_p.add_argument("project_name", help="Project name")

    # import-srt
    srt_p = subparsers.add_parser("import-srt", help="Import subtitles from .srt file")
    srt_p.add_argument("project_name", help="Project name")
    srt_p.add_argument("srt_path", help="Path to .srt file")

    # duplicate
    dup_p = subparsers.add_parser("duplicate", help="Duplicate a project")
    dup_p.add_argument("source_name", help="Source project name")
    dup_p.add_argument("target_name", help="Target project name")

    # delete
    del_p = subparsers.add_parser("delete", help="Delete a project")
    del_p.add_argument("project_name", help="Project name to delete")

    # open
    open_p = subparsers.add_parser("open", help="Open project in CapCut Desktop")
    open_p.add_argument("project_name", nargs="?", default=None, help="Optional project name")

    # fix-network
    subparsers.add_parser("fix-network", help="Bypass regional drop rules & fix effects loading without VPN")

    # effects
    eff_p = subparsers.add_parser("effects", help="List or search available video scene effects")
    eff_p.add_argument("--keyword", default="", help="Search query")
    eff_p.add_argument("--limit", type=int, default=50, help="Max items to list")

    # filters
    fil_p = subparsers.add_parser("filters", help="List or search available color grading filters")
    fil_p.add_argument("--keyword", default="", help="Search query")
    fil_p.add_argument("--limit", type=int, default=50, help="Max items to list")

    # transitions
    trans_p = subparsers.add_parser("transitions", help="List or search available transitions")
    trans_p.add_argument("--keyword", default="", help="Search query")
    trans_p.add_argument("--limit", type=int, default=50, help="Max items to list")

    # animations
    anim_p = subparsers.add_parser("animations", help="List or search available animations")
    anim_p.add_argument("--keyword", default="", help="Search query")
    anim_p.add_argument("--type", default="all", choices=["all", "intro", "outro", "group"], help="Animation category")
    anim_p.add_argument("--limit", type=int, default=50, help="Max items to list")

    # add-effect
    ae_p = subparsers.add_parser("add-effect", help="Add video scene effect to project timeline")
    ae_p.add_argument("project_name", help="Project name")
    ae_p.add_argument("effect_name", help="Effect name (e.g. Flickery_Shots)")
    ae_p.add_argument("--start", type=float, default=0.0, help="Start offset in seconds")
    ae_p.add_argument("--duration", type=float, default=3.0, help="Effect duration in seconds")

    # add-filter
    af_p = subparsers.add_parser("add-filter", help="Add color grading filter to project timeline")
    af_p.add_argument("project_name", help="Project name")
    af_p.add_argument("filter_name", help="Filter name (e.g. BW_2)")
    af_p.add_argument("--start", type=float, default=0.0, help="Start offset in seconds")
    af_p.add_argument("--duration", type=float, default=3.0, help="Filter duration in seconds")
    af_p.add_argument("--intensity", type=float, default=80.0, help="Filter intensity 0-100")

    # add-transition
    at_p = subparsers.add_parser("add-transition", help="Add transition to video clip")
    at_p.add_argument("project_name", help="Project name")
    at_p.add_argument("transition_name", help="Transition name (e.g. White_Flash)")
    at_p.add_argument("--segment", type=int, default=0, help="Target clip index (0-based)")
    at_p.add_argument("--duration", type=float, default=0.5, help="Transition duration in seconds")

    # add-animation
    aa_p = subparsers.add_parser("add-animation", help="Add intro/outro/group animation to video clip")
    aa_p.add_argument("project_name", help="Project name")
    aa_p.add_argument("animation_name", help="Animation name")
    aa_p.add_argument("--type", default="intro", choices=["intro", "outro", "group"], help="Animation category")
    aa_p.add_argument("--segment", type=int, default=0, help="Target clip index (0-based)")
    # list-pro-effects
    lpe_p = subparsers.add_parser("list-pro-effects", help="List available Pro / VIP video effects")
    lpe_p.add_argument("--keyword", default="", help="Filter keyword")
    lpe_p.add_argument("--limit", type=int, default=50, help="Maximum results to return")

    # add-pro-effect
    ape_p = subparsers.add_parser("add-pro-effect", help="Add Pro effect to timeline without restrictions")
    ape_p.add_argument("project_name", help="Project name")
    ape_p.add_argument("effect_name", help="Effect name (e.g. Flickery_Shots)")
    ape_p.add_argument("--start", type=float, default=0.0, help="Start offset in seconds")
    ape_p.add_argument("--duration", type=float, default=3.0, help="Effect duration in seconds")

    # unlock-pro
    up_p = subparsers.add_parser("unlock-pro", help="Unlock all Pro/VIP restrictions across draft projects")
    up_p.add_argument("project_name", nargs="?", default=None, help="Optional project name")

    # split
    split_p = subparsers.add_parser("split", help="Split clip at millisecond timestamp")
    split_p.add_argument("project_name", help="Project name")
    split_p.add_argument("--time", type=float, default=None, help="Split time in seconds")
    split_p.add_argument("--time-ms", type=float, default=None, help="Split time in milliseconds")
    split_p.add_argument("--segment", type=int, default=0, help="Segment index (default 0)")
    split_p.add_argument("--track", type=int, default=0, help="Track index (default 0)")
    split_p.add_argument("--track-type", default="video", choices=["video", "audio"], help="Track type")

    # trim
    trim_p = subparsers.add_parser("trim", help="Trim clip in/out points down to milliseconds")
    trim_p.add_argument("project_name", help="Project name")
    trim_p.add_argument("--segment", type=int, default=0, help="Segment index")
    trim_p.add_argument("--track", type=int, default=0, help="Track index")
    trim_p.add_argument("--target-start-ms", type=float, default=None, help="Timeline start in ms")
    trim_p.add_argument("--duration-ms", type=float, default=None, help="Duration in ms")
    trim_p.add_argument("--source-start-ms", type=float, default=None, help="Source in-point in ms")
    trim_p.add_argument("--source-duration-ms", type=float, default=None, help="Source duration in ms")
    trim_p.add_argument("--track-type", default="video", choices=["video", "audio"], help="Track type")

    # beat-sync
    beat_p = subparsers.add_parser("beat-sync", help="Assemble multi-clip montage beat-synced to music")
    beat_p.add_argument("project_name", help="Project name")
    beat_p.add_argument("music_path", help="Path to BGM audio file")
    beat_p.add_argument("--clips", nargs="+", required=True, help="List of video clip paths")
    beat_p.add_argument("--bpm", type=float, default=120.0, help="BPM tempo (default 120.0)")
    beat_p.add_argument("--beats-per-cut", type=int, default=4, help="Beats per cut (default 4)")
    beat_p.add_argument("--duration", type=float, default=None, help="Target duration in seconds")
    beat_p.add_argument("--transition", default=None, help="Transition name")
    beat_p.add_argument("--effects", nargs="+", default=None, help="Effects to apply on drops")

    # ui
    ui_p = subparsers.add_parser("ui", help="Generate interactive HTML timeline inspector view")
    ui_p.add_argument("project_name", help="Project name")

    # validate
    val_p = subparsers.add_parser("validate", help="Validate and scaffold draft for CapCut Desktop")
    val_p.add_argument("project_name", help="Project name")

    args = parser.parse_args()
    engine = get_capcut_engine()

    try:
        if args.subcommand == "list":
            projects = engine.list_projects()
            print(json.dumps({"count": len(projects), "projects": projects}, indent=2))
        elif args.subcommand == "get":
            details = engine.get_project(args.project_name)
            print(json.dumps(details, indent=2))
        elif args.subcommand == "create":
            res = engine.create_project(
                args.project_name,
                width=args.width,
                height=args.height,
                fps=args.fps,
                aspect_ratio=args.ratio,
                allow_replace=not args.no_replace,
            )
            print(json.dumps(res, indent=2))
        elif args.subcommand == "set-canvas":
            res = engine.set_canvas(
                project_name=args.project_name,
                aspect_ratio=args.ratio,
                width=args.width,
                height=args.height,
            )
            print(json.dumps(res, indent=2))
        elif args.subcommand == "add-video":
            res = engine.add_video_clip(
                args.project_name,
                args.file_path,
                start_time=args.start,
                duration=args.duration,
                target_start=args.target_start,
                speed=args.speed,
                volume=args.volume,
                transform_x=args.x,
                transform_y=args.y,
                scale_x=args.scale_x,
                scale_y=args.scale_y,
                rotation=args.rotation,
                alpha=args.alpha,
                fade_in=args.fade_in,
                fade_out=args.fade_out,
                transition=args.transition,
                transition_duration=args.transition_duration,
                track_name=args.track,
            )
            print(json.dumps(res, indent=2))
        elif args.subcommand == "add-image":
            res = engine.add_image(
                args.project_name,
                args.file_path,
                start_time=args.start,
                duration=args.duration,
                target_start=args.target_start,
                transform_x=args.x,
                transform_y=args.y,
                scale_x=args.scale_x,
                scale_y=args.scale_y,
                rotation=args.rotation,
                alpha=args.alpha,
                track_name=args.track,
            )
            print(json.dumps(res, indent=2))
        elif args.subcommand == "add-audio":
            res = engine.add_audio_clip(
                args.project_name,
                args.file_path,
                start_time=args.start,
                duration=args.duration,
                target_start=args.target_start,
                volume=args.volume,
                speed=args.speed,
                fade_in=args.fade_in,
                fade_out=args.fade_out,
                track_name=args.track,
            )
            print(json.dumps(res, indent=2))
        elif args.subcommand == "add-text":
            res = engine.add_text(
                args.project_name,
                args.text,
                start_time=args.start,
                duration=args.duration,
                target_start=args.target_start,
                font_size=args.size,
                font_color=args.color,
                pos_x=args.x,
                pos_y=args.y,
                bold=args.bold,
                italic=args.italic,
                underline=args.underline,
                align=args.align,
                background_color=args.bg_color,
                background_alpha=args.bg_alpha,
                shadow_enabled=args.shadow,
                shadow_color=args.shadow_color,
                border_enabled=args.border,
                border_color=args.border_color,
                border_width=args.border_width,
                animation=args.animation,
                animation_duration=args.anim_duration,
            )
            print(json.dumps(res, indent=2))
        elif args.subcommand == "add-keyframe":
            prop_list = [p.strip() for p in args.properties.split(",") if p.strip()]
            times_list = [float(t.strip()) for t in args.times.split(",") if t.strip()]
            raw_vals = [v.strip() for v in args.values.split(",") if v.strip()]
            parsed_vals = []
            for v in raw_vals:
                try:
                    parsed_vals.append(float(v))
                except ValueError:
                    parsed_vals.append(v)
            res = engine.add_keyframe(
                project_name=args.project_name,
                property_types=prop_list,
                times=times_list,
                values=parsed_vals,
                track_type=args.track_type,
                track_index=args.track_index,
                segment_index=args.segment_index,
            )
            print(json.dumps(res, indent=2))
        elif args.subcommand == "add-sticker":
            res = engine.add_sticker(
                project_name=args.project_name,
                resource_id=args.resource_id,
                start_time=args.start,
                duration=args.duration,
                target_start=args.target_start,
                transform_x=args.x,
                transform_y=args.y,
                scale_x=args.scale_x,
                scale_y=args.scale_y,
                rotation=args.rotation,
                alpha=args.alpha,
                track_name=args.track,
            )
            print(json.dumps(res, indent=2))
        elif args.subcommand == "media-info":
            res = engine.get_media_duration(args.file_path)
            print(json.dumps(res, indent=2))
        elif args.subcommand == "save-draft":
            res = engine.save_draft(args.project_name)
            print(json.dumps(res, indent=2))
        elif args.subcommand == "import-srt":
            res = engine.import_srt(args.project_name, args.srt_path)
            print(json.dumps(res, indent=2))
        elif args.subcommand == "duplicate":
            res = engine.duplicate_project(args.source_name, args.target_name)
            print(json.dumps(res, indent=2))
        elif args.subcommand == "delete":
            res = engine.delete_project(args.project_name)
            print(json.dumps(res, indent=2))
        elif args.subcommand == "open":
            res = engine.open_in_capcut(args.project_name)
            print(json.dumps(res, indent=2))
        elif args.subcommand == "fix-network":
            res = engine.fix_network_and_effects()
            print(json.dumps(res, indent=2))
        elif args.subcommand == "effects":
            effs = engine.list_available_effects(keyword=args.keyword, limit=args.limit)
            print(json.dumps({"count": len(effs), "effects": effs}, indent=2))
        elif args.subcommand == "filters":
            fils = engine.list_available_filters(keyword=args.keyword, limit=args.limit)
            print(json.dumps({"count": len(fils), "filters": fils}, indent=2))
        elif args.subcommand == "transitions":
            trans = engine.list_available_transitions(keyword=args.keyword, limit=args.limit)
            print(json.dumps({"count": len(trans), "transitions": trans}, indent=2))
        elif args.subcommand == "animations":
            anims = engine.list_available_animations(keyword=args.keyword, anim_type=args.type, limit=args.limit)
            print(json.dumps({"count": len(anims), "animations": anims}, indent=2))
        elif args.subcommand == "add-effect":
            res = engine.add_effect(
                project_name=args.project_name,
                effect_name=args.effect_name,
                start_time=args.start,
                duration=args.duration,
            )
            print(json.dumps(res, indent=2))
        elif args.subcommand == "add-filter":
            res = engine.add_filter(
                project_name=args.project_name,
                filter_name=args.filter_name,
                start_time=args.start,
                duration=args.duration,
                intensity=args.intensity,
            )
            print(json.dumps(res, indent=2))
        elif args.subcommand == "add-transition":
            res = engine.add_transition(
                project_name=args.project_name,
                transition_name=args.transition_name,
                segment_index=args.segment,
                duration=args.duration,
            )
            print(json.dumps(res, indent=2))
        elif args.subcommand == "add-animation":
            res = engine.add_video_animation(
                project_name=args.project_name,
                animation_name=args.animation_name,
                anim_type=args.type,
                segment_index=args.segment,
                duration=args.duration,
            )
            print(json.dumps(res, indent=2))
        elif args.subcommand == "list-pro-effects":
            effs = engine.list_pro_effects(keyword=args.keyword, limit=args.limit)
            print(json.dumps({"count": len(effs), "effects": effs}, indent=2))
        elif args.subcommand == "add-pro-effect":
            res = engine.add_pro_effect(
                project_name=args.project_name,
                effect_name=args.effect_name,
                start_time=args.start,
                duration=args.duration,
            )
            print(json.dumps(res, indent=2))
        elif args.subcommand == "unlock-pro":
            res = engine.unlock_all_pro_features(project_name=args.project_name)
            print(json.dumps(res, indent=2))
        elif args.subcommand == "split":
            res = engine.split_clip(
                project_name=args.project_name,
                track_index=args.track,
                segment_index=args.segment,
                split_time=args.time,
                split_time_ms=args.time_ms,
                track_type=args.track_type,
            )
            print(json.dumps(res, indent=2))
        elif args.subcommand == "trim":
            res = engine.trim_clip(
                project_name=args.project_name,
                track_index=args.track,
                segment_index=args.segment,
                target_start_ms=args.target_start_ms,
                duration_ms=args.duration_ms,
                source_start_ms=args.source_start_ms,
                source_duration_ms=args.source_duration_ms,
                track_type=args.track_type,
            )
            print(json.dumps(res, indent=2))
        elif args.subcommand == "beat-sync":
            res = engine.beat_sync_edit(
                project_name=args.project_name,
                video_clips=args.clips,
                music_path=args.music_path,
                bpm=args.bpm,
                beats_per_cut=args.beats_per_cut,
                target_duration=args.duration,
                transition=args.transition,
                effects=args.effects,
            )
            print(json.dumps(res, indent=2))
        elif args.subcommand == "ui":
            html = engine.get_timeline_inspector_html(args.project_name)
            out = Path.cwd() / f"{args.project_name}_timeline_inspector.html"
            out.write_text(html, encoding="utf-8")
            print(json.dumps({"success": True, "path": str(out)}, indent=2))
        elif args.subcommand == "validate":
            res = engine.save_draft(args.project_name)
            print(json.dumps(res, indent=2))
    except Exception as e:
        print(json.dumps({"success": False, "error": str(e)}, indent=2), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
