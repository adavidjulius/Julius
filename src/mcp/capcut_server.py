#!/usr/bin/env python3
"""
CapCut Desktop Model Context Protocol (MCP) Server.

Enables AI agents (Julius, Antigravity IDE, Claude, etc.) to programmatically inspect,
create, edit, and control CapCut Desktop video projects.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure project root is in sys.path
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.capcut.engine import get_capcut_engine

try:
    from mcp.server.mcpserver import MCPServer
except ImportError:
    print("Error: 'mcp' package is required. Install via: pip install mcp", file=sys.stderr)
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("capcut_mcp")

server = MCPServer(
    name="capcut",
    description="CapCut Desktop Video Editor MCP Server for autonomous video editing and timeline management."
)
engine = get_capcut_engine()


@server.tool(
    name="capcut_list_projects",
    description="List all CapCut Desktop projects, drafts, durations, and metadata."
)
def list_projects() -> str:
    """List all CapCut Desktop projects."""
    projects = engine.list_projects()
    return json.dumps({"count": len(projects), "projects": projects}, indent=2)


@server.tool(
    name="capcut_get_project",
    description="Get full timeline breakdown, track structure, clips, text overlays, and audio for a CapCut project."
)
def get_project(project_name: str) -> str:
    """Get project details and timeline breakdown."""
    details = engine.get_project(project_name)
    return json.dumps(details, indent=2)


@server.tool(
    name="capcut_create_project",
    description="Create a new CapCut project draft with specified resolution, aspect ratio (16:9, 9:16, 1:1, etc.), and framerate."
)
def create_project(
    project_name: str,
    width: Optional[int] = None,
    height: Optional[int] = None,
    fps: int = 30,
    aspect_ratio: Optional[str] = None,
    allow_replace: bool = True,
) -> str:
    """Create a new CapCut project."""
    res = engine.create_project(
        project_name=project_name,
        width=width,
        height=height,
        fps=fps,
        aspect_ratio=aspect_ratio,
        allow_replace=allow_replace,
    )
    return json.dumps(res, indent=2)


@server.tool(
    name="capcut_set_canvas",
    description="Set or change the canvas dimensions and aspect ratio (e.g. '16:9', '9:16', '1:1', '4:3', '21:9') of a project."
)
def set_canvas(
    project_name: str,
    aspect_ratio: Optional[str] = None,
    width: Optional[int] = None,
    height: Optional[int] = None,
) -> str:
    """Change project canvas resolution and ratio."""
    res = engine.set_canvas(
        project_name=project_name,
        aspect_ratio=aspect_ratio,
        width=width,
        height=height,
    )
    return json.dumps(res, indent=2)


@server.tool(
    name="capcut_add_video_clip",
    description="Add a video clip to a CapCut project timeline with granular positioning (x, y, scale, rotation), fade in/out, transition, and timing."
)
def add_video_clip(
    project_name: str,
    file_path: str,
    start_time: float = 0.0,
    duration: Optional[float] = None,
    target_start: float = 0.0,
    speed: float = 1.0,
    volume: float = 1.0,
    transform_x: float = 0.0,
    transform_y: float = 0.0,
    scale_x: float = 1.0,
    scale_y: float = 1.0,
    rotation: float = 0.0,
    alpha: float = 1.0,
    fade_in: float = 0.0,
    fade_out: float = 0.0,
    transition: Optional[str] = None,
    transition_duration: float = 0.5,
    track_name: Optional[str] = None,
) -> str:
    """Add a video clip to project timeline with granular controls."""
    res = engine.add_video_clip(
        project_name=project_name,
        file_path=file_path,
        start_time=start_time,
        duration=duration,
        target_start=target_start,
        speed=speed,
        volume=volume,
        transform_x=transform_x,
        transform_y=transform_y,
        scale_x=scale_x,
        scale_y=scale_y,
        rotation=rotation,
        alpha=alpha,
        fade_in=fade_in,
        fade_out=fade_out,
        transition=transition,
        transition_duration=transition_duration,
        track_name=track_name,
    )
    return json.dumps(res, indent=2)


@server.tool(
    name="capcut_add_audio_clip",
    description="Add an audio or background music track to timeline with volume envelope, fade in/out, speed, and timing."
)
def add_audio_clip(
    project_name: str,
    file_path: str,
    start_time: float = 0.0,
    duration: Optional[float] = None,
    target_start: float = 0.0,
    volume: float = 1.0,
    speed: float = 1.0,
    fade_in: float = 0.0,
    fade_out: float = 0.0,
    track_name: Optional[str] = None,
) -> str:
    """Add an audio track to project timeline."""
    res = engine.add_audio_clip(
        project_name=project_name,
        file_path=file_path,
        start_time=start_time,
        duration=duration,
        target_start=target_start,
        volume=volume,
        speed=speed,
        fade_in=fade_in,
        fade_out=fade_out,
        track_name=track_name,
    )
    return json.dumps(res, indent=2)


@server.tool(
    name="capcut_add_image",
    description="Add an image overlay or photo track to the project timeline with positioning (x, y, scale, rotation) and duration."
)
def add_image(
    project_name: str,
    file_path: str,
    start_time: float = 0.0,
    duration: float = 3.0,
    target_start: float = 0.0,
    transform_x: float = 0.0,
    transform_y: float = 0.0,
    scale_x: float = 1.0,
    scale_y: float = 1.0,
    rotation: float = 0.0,
    alpha: float = 1.0,
    track_name: Optional[str] = None,
) -> str:
    """Add an image or photo to project timeline."""
    res = engine.add_image(
        project_name=project_name,
        file_path=file_path,
        start_time=start_time,
        duration=duration,
        target_start=target_start,
        transform_x=transform_x,
        transform_y=transform_y,
        scale_x=scale_x,
        scale_y=scale_y,
        rotation=rotation,
        alpha=alpha,
        track_name=track_name,
    )
    return json.dumps(res, indent=2)


@server.tool(
    name="capcut_add_text",
    description="Add styled text, title, caption, or subtitle with background color/alpha, border, shadow, alignment, and position."
)
def add_text(
    project_name: str,
    text: str,
    start_time: float = 0.0,
    duration: float = 3.0,
    target_start: Optional[float] = None,
    font_size: float = 15.0,
    font_color: str = "#FFFFFF",
    pos_x: float = 0.0,
    pos_y: float = -0.6,
    bold: bool = False,
    italic: bool = False,
    underline: bool = False,
    align: int = 1,
    background_color: Optional[str] = None,
    background_alpha: float = 0.8,
    shadow_enabled: bool = False,
    shadow_color: str = "#000000",
    border_enabled: bool = False,
    border_color: str = "#000000",
    border_width: float = 20.0,
    animation: Optional[str] = None,
    animation_duration: float = 0.5,
) -> str:
    """Add styled text overlay to project timeline."""
    res = engine.add_text(
        project_name=project_name,
        text=text,
        start_time=start_time,
        duration=duration,
        target_start=target_start,
        font_size=font_size,
        font_color=font_color,
        pos_x=pos_x,
        pos_y=pos_y,
        bold=bold,
        italic=italic,
        underline=underline,
        align=align,
        background_color=background_color,
        background_alpha=background_alpha,
        shadow_enabled=shadow_enabled,
        shadow_color=shadow_color,
        border_enabled=border_enabled,
        border_color=border_color,
        border_width=border_width,
        animation=animation,
        animation_duration=animation_duration,
    )
    return json.dumps(res, indent=2)


@server.tool(
    name="capcut_add_keyframe",
    description="Add keyframe animation interpolation (position_x, position_y, scale_x, scale_y, rotation, alpha, volume) to any track segment."
)
def add_keyframe(
    project_name: str,
    property_types: List[str],
    times: List[float],
    values: List[Any],
    track_type: str = "video",
    track_index: int = 0,
    segment_index: int = 0,
) -> str:
    """Add keyframes to a track segment."""
    res = engine.add_keyframe(
        project_name=project_name,
        property_types=property_types,
        times=times,
        values=values,
        track_type=track_type,
        track_index=track_index,
        segment_index=segment_index,
    )
    return json.dumps(res, indent=2)


@server.tool(
    name="capcut_add_sticker",
    description="Add a decorative sticker or emoji to the project timeline with positioning and duration."
)
def add_sticker(
    project_name: str,
    resource_id: str,
    start_time: float = 0.0,
    duration: float = 3.0,
    target_start: Optional[float] = None,
    transform_x: float = 0.0,
    transform_y: float = 0.0,
    scale_x: float = 1.0,
    scale_y: float = 1.0,
    rotation: float = 0.0,
    alpha: float = 1.0,
    track_name: str = "sticker_main",
) -> str:
    """Add a sticker to project timeline."""
    res = engine.add_sticker(
        project_name=project_name,
        resource_id=resource_id,
        start_time=start_time,
        duration=duration,
        target_start=target_start,
        transform_x=transform_x,
        transform_y=transform_y,
        scale_x=scale_x,
        scale_y=scale_y,
        rotation=rotation,
        alpha=alpha,
        track_name=track_name,
    )
    return json.dumps(res, indent=2)


@server.tool(
    name="capcut_get_media_duration",
    description="Analyze a video or audio media file to extract exact duration, dimensions (width/height), FPS, codecs, and bitrate."
)
def get_media_duration(file_path: str) -> str:
    """Get media duration and properties using ffprobe."""
    res = engine.get_media_duration(file_path=file_path)
    return json.dumps(res, indent=2)


@server.tool(
    name="capcut_save_draft",
    description="Validate, save, and synchronize a draft with CapCut Desktop project store and generate thumbnails."
)
def save_draft(project_name: str) -> str:
    """Save and validate draft for CapCut Desktop."""
    res = engine.save_draft(project_name=project_name)
    return json.dumps(res, indent=2)


@server.tool(
    name="capcut_split_clip",
    description="Split a clip on the CapCut timeline at an exact millisecond timestamp into two separate clips."
)
def split_clip(
    project_name: str,
    track_index: int = 0,
    segment_index: int = 0,
    split_time: Optional[float] = None,
    split_time_ms: Optional[float] = None,
    track_type: str = "video",
) -> str:
    """Split a clip into two segments at a millisecond timestamp."""
    res = engine.split_clip(
        project_name=project_name,
        track_index=track_index,
        segment_index=segment_index,
        split_time=split_time,
        split_time_ms=split_time_ms,
        track_type=track_type,
    )
    return json.dumps(res, indent=2)


@server.tool(
    name="capcut_trim_clip",
    description="Trim and adjust clip in/out points and timeline placement down to milliseconds."
)
def trim_clip(
    project_name: str,
    track_index: int = 0,
    segment_index: int = 0,
    target_start: Optional[float] = None,
    target_start_ms: Optional[float] = None,
    duration: Optional[float] = None,
    duration_ms: Optional[float] = None,
    source_start: Optional[float] = None,
    source_start_ms: Optional[float] = None,
    source_duration: Optional[float] = None,
    source_duration_ms: Optional[float] = None,
    track_type: str = "video",
) -> str:
    """Trim clip in/out points down to milliseconds."""
    res = engine.trim_clip(
        project_name=project_name,
        track_index=track_index,
        segment_index=segment_index,
        target_start=target_start,
        target_start_ms=target_start_ms,
        duration=duration,
        duration_ms=duration_ms,
        source_start=source_start,
        source_start_ms=source_start_ms,
        source_duration=source_duration,
        source_duration_ms=source_duration_ms,
        track_type=track_type,
    )
    return json.dumps(res, indent=2)


@server.tool(
    name="capcut_beat_sync_edit",
    description="Automatically assemble a multi-clip video edit synchronized with music beats down to the millisecond."
)
def beat_sync_edit(
    project_name: str,
    video_clips: List[str],
    music_path: str,
    bpm: float = 120.0,
    beats_per_cut: int = 4,
    target_duration: Optional[float] = None,
    target_duration_ms: Optional[float] = None,
    transition: Optional[str] = None,
    transition_duration: float = 0.3,
    transition_duration_ms: Optional[float] = None,
    effects: Optional[List[str]] = None,
    volume: float = 1.0,
    width: Optional[int] = 1920,
    height: Optional[int] = 1080,
    fps: int = 30,
) -> str:
    """Assemble a beat-synchronized timeline with millisecond precision cuts."""
    res = engine.beat_sync_edit(
        project_name=project_name,
        video_clips=video_clips,
        music_path=music_path,
        bpm=bpm,
        beats_per_cut=beats_per_cut,
        target_duration=target_duration,
        target_duration_ms=target_duration_ms,
        transition=transition,
        transition_duration=transition_duration,
        transition_duration_ms=transition_duration_ms,
        effects=effects,
        volume=volume,
        width=width,
        height=height,
        fps=fps,
    )
    return json.dumps(res, indent=2)


@server.tool(
    name="capcut_inspect_timeline_ui",
    description="Generate and retrieve an interactive HTML timeline inspector view (MCP App UI) for a CapCut project."
)
def inspect_timeline_ui(project_name: str) -> str:
    """Generate an interactive HTML timeline viewer for the CapCut project."""
    html_content = engine.get_timeline_inspector_html(project_name)
    return html_content


@server.tool(
    name="capcut_import_srt",
    description="Import subtitle file (.srt) directly into a CapCut project timeline."
)
def import_srt(
    project_name: str,
    srt_path: str,
) -> str:
    """Import SRT subtitles into project."""
    res = engine.import_srt(project_name=project_name, srt_path=srt_path)
    return json.dumps(res, indent=2)


@server.tool(
    name="capcut_duplicate_project",
    description="Duplicate an existing CapCut project to create a new draft copy."
)
def duplicate_project(
    source_name: str,
    target_name: str,
) -> str:
    """Duplicate an existing project."""
    res = engine.duplicate_project(source_name=source_name, target_name=target_name)
    return json.dumps(res, indent=2)


@server.tool(
    name="capcut_delete_project",
    description="Permanently delete a CapCut project draft from disk and unregister it."
)
def delete_project(project_name: str) -> str:
    """Delete a CapCut project draft."""
    res = engine.delete_project(project_name=project_name)
    return json.dumps(res, indent=2)


@server.tool(
    name="capcut_open_in_app",
    description="Launch or switch to CapCut Desktop macOS application and open the project."
)
def open_in_app(project_name: Optional[str] = None) -> str:
    """Open CapCut app with target project."""
    res = engine.open_in_capcut(project_name=project_name)
    return json.dumps(res, indent=2)


@server.tool(
    name="capcut_fix_network_and_effects",
    description="Fix CapCut network dropping & geo-restrictions so effects, filters, and online materials work without VPN."
)
def fix_network_and_effects() -> str:
    """Bypass regional network drop and unlock CapCut effects and materials."""
    res = engine.fix_network_and_effects()
    return json.dumps(res, indent=2)


@server.tool(
    name="capcut_list_available_effects",
    description="List or search available built-in video scene effects (e.g. Flickery_Shots, Glitch, Blur, Diamond_Zoom)."
)
def list_available_effects(keyword: str = "", limit: int = 50) -> str:
    """List available video scene effects."""
    effects = engine.list_available_effects(keyword=keyword, limit=limit)
    return json.dumps({"count": len(effects), "effects": effects}, indent=2)


@server.tool(
    name="capcut_list_available_filters",
    description="List or search available color grading filters (e.g. BW_2, Film, Vintage, Cyberpunk)."
)
def list_available_filters(keyword: str = "", limit: int = 50) -> str:
    """List available color grading filters."""
    filters = engine.list_available_filters(keyword=keyword, limit=limit)
    return json.dumps({"count": len(filters), "filters": filters}, indent=2)


@server.tool(
    name="capcut_list_available_transitions",
    description="List or search available video transitions (e.g. White_Flash, Black_Fade, Left_Right, Pull_In)."
)
def list_available_transitions(keyword: str = "", limit: int = 50) -> str:
    """List available video transitions."""
    transitions = engine.list_available_transitions(keyword=keyword, limit=limit)
    return json.dumps({"count": len(transitions), "transitions": transitions}, indent=2)


@server.tool(
    name="capcut_list_available_animations",
    description="List or search available video animations (intro, outro, group/combo)."
)
def list_available_animations(keyword: str = "", anim_type: str = "all", limit: int = 50) -> str:
    """List available video animations."""
    animations = engine.list_available_animations(keyword=keyword, anim_type=anim_type, limit=limit)
    return json.dumps({"count": len(animations), "animations": animations}, indent=2)


@server.tool(
    name="capcut_add_effect",
    description="Add a video scene effect directly onto a CapCut project timeline with start time and duration."
)
def add_effect(
    project_name: str,
    effect_name: str,
    start_time: float = 0.0,
    duration: float = 3.0,
    track_name: Optional[str] = None,
) -> str:
    """Add a video effect to project timeline."""
    res = engine.add_effect(
        project_name=project_name,
        effect_name=effect_name,
        start_time=start_time,
        duration=duration,
        track_name=track_name,
    )
    return json.dumps(res, indent=2)


@server.tool(
    name="capcut_add_filter",
    description="Apply a color grading filter to a CapCut project timeline with custom intensity (0-100)."
)
def add_filter(
    project_name: str,
    filter_name: str,
    start_time: float = 0.0,
    duration: float = 3.0,
    intensity: float = 80.0,
    track_name: Optional[str] = None,
) -> str:
    """Apply a filter to project timeline."""
    res = engine.add_filter(
        project_name=project_name,
        filter_name=filter_name,
        start_time=start_time,
        duration=duration,
        intensity=intensity,
        track_name=track_name,
    )
    return json.dumps(res, indent=2)


@server.tool(
    name="capcut_add_transition",
    description="Apply a transition (e.g. White_Flash) to a video clip on the main video track."
)
def add_transition(
    project_name: str,
    transition_name: str,
    segment_index: int = 0,
    duration: float = 0.5,
) -> str:
    """Apply a transition to video clip."""
    res = engine.add_transition(
        project_name=project_name,
        transition_name=transition_name,
        segment_index=segment_index,
        duration=duration,
    )
    return json.dumps(res, indent=2)


@server.tool(
    name="capcut_add_video_animation",
    description="Apply an intro, outro, or combo animation to a video clip on the main video track."
)
def add_video_animation(
    project_name: str,
    animation_name: str,
    anim_type: str = "intro",
    segment_index: int = 0,
    duration: float = 0.5,
) -> str:
    """Apply an animation to video clip."""
    res = engine.add_video_animation(
        project_name=project_name,
        animation_name=animation_name,
        anim_type=anim_type,
        segment_index=segment_index,
        duration=duration,
    )
    return json.dumps(res, indent=2)


@server.tool(
    name="capcut_list_pro_effects",
    description="List or search high-end and Pro video scene effects, filters, and animations from CapCut library."
)
def list_pro_effects(keyword: str = "", limit: int = 50) -> str:
    """List available Pro video effects."""
    effects = engine.list_pro_effects(keyword=keyword, limit=limit)
    return json.dumps({"count": len(effects), "effects": effects}, indent=2)


@server.tool(
    name="capcut_add_pro_effect",
    description="Add a Pro / VIP video effect directly to the timeline without paywall or export watermark restrictions."
)
def add_pro_effect(
    project_name: str,
    effect_name: str,
    start_time: float = 0.0,
    duration: float = 3.0,
    track_name: Optional[str] = None,
) -> str:
    """Add a Pro effect to timeline."""
    res = engine.add_pro_effect(
        project_name=project_name,
        effect_name=effect_name,
        start_time=start_time,
        duration=duration,
        track_name=track_name,
    )
    return json.dumps(res, indent=2)


@server.tool(
    name="capcut_unlock_all_pro_features",
    description="Strip VIP / Pro restriction tokens from project drafts and local material database to enable unrestricted export."
)
def unlock_all_pro_features(project_name: Optional[str] = None) -> str:
    """Unlock all Pro features on draft projects and material database."""
    res = engine.unlock_all_pro_features(project_name=project_name)
    return json.dumps(res, indent=2)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="CapCut Desktop MCP Server")
    parser.add_argument("--transport", default="stdio", choices=["stdio", "sse", "streamable-http"], help="Transport mode")
    parser.add_argument("--port", type=int, default=8000, help="Port for SSE/HTTP transport")
    args = parser.parse_args()

    if args.transport == "stdio":
        server.run(transport="stdio")
    elif args.transport == "sse":
        server.run(transport="sse", port=args.port)
    elif args.transport == "streamable-http":
        server.run(transport="streamable-http", port=args.port)


if __name__ == "__main__":
    main()
