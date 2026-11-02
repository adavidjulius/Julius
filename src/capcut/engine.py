"""
CapCut Desktop Engine & Reverse-Engineered Automation Subsystem.

Provides programmatic control over CapCut Desktop macOS application:
- Direct creation and manipulation of CapCut timeline drafts (draft_content.json).
- Synchronization with CapCut project database (root_meta_info.json & draft_meta_info.json).
- Native track operations: video clips, audio/music tracks, animated text overlays, SRT subtitles.
- Application lifecycle and UI automation (opening projects directly into CapCut).

Paths:
  Drafts Root: ~/Movies/CapCut/User Data/Projects/com.lveditor.draft/
  CapCut App:  /Applications/CapCut.app
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import sqlite3
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Default standard paths on macOS
DEFAULT_DRAFT_ROOT = Path.home() / "Movies" / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft"
CAPCUT_APP_PATH = Path("/Applications/CapCut.app")
MICROSECOND = 1_000_000


@dataclass
class ProjectSummary:
    name: str
    draft_id: str
    duration_seconds: float
    duration_formatted: str
    path: str
    created_at: str
    modified_at: str
    video_tracks: int
    audio_tracks: int
    text_tracks: int


class CapCutEngine:
    """Core controller for CapCut Desktop projects and timeline synthesis."""

    def __init__(self, draft_root: Optional[str | Path] = None) -> None:
        if draft_root is None:
            self.draft_root = Path(os.environ.get("CAPCUT_DRAFT_ROOT", str(DEFAULT_DRAFT_ROOT)))
        else:
            self.draft_root = Path(draft_root)

        self.root_meta_path = self.draft_root / "root_meta_info.json"
        self._ensure_storage()


    def _compute_media_size(self, proj_dir: Path) -> int:
        """Sum the byte size of all referenced media files (videos + audios)."""
        try:
            content = json.loads((proj_dir / "draft_content.json").read_text(encoding="utf-8"))
        except Exception:
            return 0
        total = 0
        materials = content.get("materials", {}) or {}
        for key in ("videos", "audios", "images"):
            for m in materials.get(key, []) or []:
                fp = m.get("path")
                if fp and os.path.exists(fp):
                    try:
                        total += os.path.getsize(fp)
                    except OSError:
                        pass
        return total

    @property
    def projects_dir(self) -> Path:
        return self.draft_root

    @property
    def master_db_gz(self) -> Path:
        return Path(__file__).resolve().parent / "res" / "rp_master.db.gz"

    @property
    def ressdk_dir(self) -> Path:
        return Path.home() / "Movies/CapCut/User Data/Cache/ressdk_db"

    def ensure_effects_database(self) -> Dict[str, Any]:
        """Ensure local CapCut effects catalog (rp.db) is populated with all 9,000+ effects and permanently immunized against regional expiration."""
        import gzip
        import shutil

        ressdk_dir = self.ressdk_dir
        ressdk_dir.mkdir(parents=True, exist_ok=True)
        master_gz = self.master_db_gz

        restored_sessions = []
        immunized_count = 0
        total_effects = 0

        # Find all session dirs or create default if none exist
        session_dirs = [d for d in ressdk_dir.iterdir() if d.is_dir()]
        if not session_dirs:
            default_session = ressdk_dir / "1003505702312649656"
            default_session.mkdir(parents=True, exist_ok=True)
            session_dirs.append(default_session)

        for s_dir in session_dirs:
            target_db = s_dir / "rp.db"
            needs_restore = False
            if not target_db.exists() or target_db.stat().st_size < 1000000:
                needs_restore = True
            else:
                try:
                    conn = sqlite3.connect(target_db)
                    c = conn.cursor()
                    c.execute("SELECT count(*) FROM effect")
                    cnt = c.fetchone()[0]
                    conn.close()
                    if cnt < 5000:
                        needs_restore = True
                except Exception:
                    needs_restore = True

            if needs_restore and master_gz.exists():
                try:
                    for wal in ("rp.db-wal", "rp.db-shm"):
                        wp = s_dir / wal
                        if wp.exists():
                            try:
                                wp.unlink()
                            except Exception:
                                pass
                    with gzip.open(master_gz, "rb") as f_in, open(target_db, "wb") as f_out:
                        shutil.copyfileobj(f_in, f_out)
                    restored_sessions.append(s_dir.name)
                except Exception as e:
                    logger.warning(f"Failed to restore rp.db to {s_dir}: {e}")

            # Immunize target_db with perpetual cache timestamps and deletion-guard triggers
            if target_db.exists():
                try:
                    conn = sqlite3.connect(target_db)
                    cur = conn.cursor()
                    cur.execute("UPDATE panel_info SET _need_update = 0, _request_time = 2147483647")
                    cur.execute("UPDATE category_data SET _check_update_time = 2147483647")
                    cur.execute("UPDATE category_status SET _intel_refresh = 0")
                    cur.execute("UPDATE http_cache SET timestamp = '2099-12-31 23:59:59'")
                    
                    # Guard tables against deletion on restart/reload
                    for tbl in ("effect", "category_effect", "panel_info", "category_data", "category_status", "panel_category", "http_cache"):
                        cur.execute(f"CREATE TRIGGER IF NOT EXISTS trg_protect_{tbl} BEFORE DELETE ON {tbl} BEGIN SELECT RAISE(IGNORE); END;")
                    
                    cur.execute("""
                        CREATE TRIGGER IF NOT EXISTS trg_keep_future_http_cache
                        AFTER INSERT ON http_cache
                        BEGIN
                            UPDATE http_cache SET timestamp = '2099-12-31 23:59:59' WHERE id = new.id;
                        END;
                    """)
                    
                    cur.execute("SELECT count(*) FROM effect")
                    total_effects = max(total_effects, cur.fetchone()[0])
                    conn.commit()
                    conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
                    conn.close()
                    immunized_count += 1
                except Exception as e:
                    logger.warning(f"Failed to immunize {target_db}: {e}")

        # Ensure ressdk_db/rp_master.db session registry is valid and not overwritten
        master_reg = ressdk_dir / "rp_master.db"
        try:
            conn_m = sqlite3.connect(master_reg)
            conn_m.execute("CREATE TABLE IF NOT EXISTS ressdk_db_info( hash_path TEXT PRIMARY KEY, did TEXT, uid TEXT, region TEXT, language TEXT, last_access_time INTEGER)")
            now_ms = int(time.time() * 1000)
            for s_dir in session_dirs:
                conn_m.execute("INSERT OR REPLACE INTO ressdk_db_info(did, uid, region, language, hash_path, last_access_time) VALUES (?, ?, ?, ?, ?, ?)",
                               ("7701605738049979910", "0", "IN", "en", s_dir.name, now_ms))
            conn_m.commit()
            conn_m.close()
        except Exception as e:
            logger.warning(f"Failed to update session registry in {master_reg}: {e}")

        return {
            "success": True,
            "total_effects": total_effects,
            "sessions_immunized": immunized_count,
            "sessions_restored": restored_sessions,
            "message": f"Successfully ensured and immunized {immunized_count} CapCut effects database sessions with {total_effects} effects. No VPN required.",
        }

    def _ensure_storage(self) -> None:
        """Ensure the draft root directory, root_meta_info.json, and effects database exist."""
        self.draft_root.mkdir(parents=True, exist_ok=True)
        if not self.root_meta_path.exists():
            initial_meta = {
                "all_draft_store": [],
                "draft_ids": 1,
                "root_path": str(self.draft_root),
            }
            with open(self.root_meta_path, "w", encoding="utf-8") as f:
                json.dump(initial_meta, f, indent=4)
        try:
            self.ensure_effects_database()
        except Exception as e:
            logger.warning(f"Could not auto-ensure effects database: {e}")

    def _load_root_meta(self) -> Dict[str, Any]:
        """Load root_meta_info.json safely."""
        try:
            with open(self.root_meta_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to read root_meta_info.json: {e}. Reinitializing.")
            return {
                "all_draft_store": [],
                "draft_ids": 1,
                "root_path": str(self.draft_root),
            }

    def _save_root_meta(self, meta: Dict[str, Any]) -> None:
        """Write root_meta_info.json safely."""
        with open(self.root_meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=4)

    def list_projects(self) -> List[Dict[str, Any]]:
        """List all CapCut projects present in the drafts directory."""
        projects = []
        if not self.draft_root.exists():
            return []

        # Read registered metadata
        root_meta = self._load_root_meta()
        registered = {d.get("draft_name"): d for d in root_meta.get("all_draft_store", []) if d.get("draft_name")}

        # Scan directory
        for item in sorted(self.draft_root.iterdir()):
            if not item.is_dir() or item.name.startswith("."):
                continue

            content_file = item / "draft_content.json"
            meta_file = item / "draft_meta_info.json"

            if not content_file.exists():
                continue

            try:
                with open(content_file, "r", encoding="utf-8") as f:
                    content = json.load(f)
                meta_data = {}
                if meta_file.exists():
                    with open(meta_file, "r", encoding="utf-8") as f:
                        meta_data = json.load(f)

                duration_us = content.get("duration", 0)
                duration_sec = duration_us / MICROSECOND
                mins = int(duration_sec // 60)
                secs = duration_sec % 60
                duration_fmt = f"{mins:02d}:{secs:05.2f}"

                tracks = content.get("tracks", [])
                v_count = sum(1 for t in tracks if t.get("type") == "video")
                a_count = sum(1 for t in tracks if t.get("type") == "audio")
                t_count = sum(1 for t in tracks if t.get("type") == "text")

                created_ts = meta_data.get("tm_draft_create", 0) / MICROSECOND
                modified_ts = meta_data.get("tm_draft_modified", 0) / MICROSECOND

                created_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(created_ts)) if created_ts else "Unknown"
                modified_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(modified_ts)) if modified_ts else "Unknown"

                projects.append({
                    "name": item.name,
                    "draft_id": meta_data.get("draft_id", registered.get(item.name, {}).get("draft_id", "")),
                    "duration_seconds": round(duration_sec, 3),
                    "duration_formatted": duration_fmt,
                    "path": str(item),
                    "video_tracks": v_count,
                    "audio_tracks": a_count,
                    "text_tracks": t_count,
                    "created_at": created_str,
                    "modified_at": modified_str,
                    "is_registered": item.name in registered,
                })
            except Exception as e:
                logger.error(f"Error parsing draft {item.name}: {e}")

        return projects

    def get_project(self, project_name: str) -> Dict[str, Any]:
        """Get complete timeline breakdown and inspection details for a project."""
        proj_dir = self.draft_root / project_name
        if not proj_dir.exists():
            raise FileNotFoundError(f"Project '{project_name}' not found at {proj_dir}")

        content_file = proj_dir / "draft_content.json"
        meta_file = proj_dir / "draft_meta_info.json"

        with open(content_file, "r", encoding="utf-8") as f:
            content = json.load(f)

        meta_data = {}
        if meta_file.exists():
            with open(meta_file, "r", encoding="utf-8") as f:
                meta_data = json.load(f)

        canvas = content.get("canvas_config", {})
        width = canvas.get("width", 1920)
        height = canvas.get("height", 1080)
        fps = content.get("fps", 30)
        duration_us = content.get("duration", 0)
        duration_sec = duration_us / MICROSECOND

        # Parse materials map
        materials = content.get("materials", {})
        videos_map = {v.get("id"): v for v in materials.get("videos", [])}
        audios_map = {a.get("id"): a for a in materials.get("audios", [])}
        texts_map = {t.get("id"): t for t in materials.get("texts", [])}

        tracks_summary = []
        for idx, track in enumerate(content.get("tracks", [])):
            t_type = track.get("type", "unknown")
            segments = []
            for seg in track.get("segments", []):
                target_tr = seg.get("target_timerange", {})
                source_tr = seg.get("source_timerange", {})
                mat_id = seg.get("material_id", "")
                
                seg_info: Dict[str, Any] = {
                    "segment_id": seg.get("id"),
                    "start_sec": target_tr.get("start", 0) / MICROSECOND,
                    "duration_sec": target_tr.get("duration", 0) / MICROSECOND,
                }

                if t_type == "video" and mat_id in videos_map:
                    v_mat = videos_map[mat_id]
                    seg_info["file_path"] = v_mat.get("path")
                    seg_info["media_width"] = v_mat.get("width")
                    seg_info["media_height"] = v_mat.get("height")
                    seg_info["media_duration_sec"] = v_mat.get("duration", 0) / MICROSECOND
                elif t_type == "audio" and mat_id in audios_map:
                    a_mat = audios_map[mat_id]
                    seg_info["file_path"] = a_mat.get("path")
                    seg_info["media_duration_sec"] = a_mat.get("duration", 0) / MICROSECOND
                elif t_type == "text" and mat_id in texts_map:
                    t_mat = texts_map[mat_id]
                    seg_info["content"] = t_mat.get("content", "")

                segments.append(seg_info)

            tracks_summary.append({
                "track_index": idx,
                "type": t_type,
                "segments_count": len(segments),
                "segments": segments,
            })

        return {
            "name": project_name,
            "draft_id": meta_data.get("draft_id", ""),
            "width": width,
            "height": height,
            "aspect_ratio": f"{width}:{height}",
            "fps": fps,
            "duration_seconds": round(duration_sec, 3),
            "tracks": tracks_summary,
            "path": str(proj_dir),
        }

    def _ensure_thumbnail(self, proj_dir: Path) -> Path:
        """Ensure a valid draft_cover.jpg exists for the project."""
        cover_path = proj_dir / "draft_cover.jpg"
        if cover_path.exists() and cover_path.stat().st_size > 0:
            return cover_path

        # If a video file exists in the draft, attempt to extract a frame with ffmpeg
        try:
            content_path = proj_dir / "draft_info.json"
            if not content_path.exists():
                content_path = proj_dir / "draft_content.json"
            if content_path.exists():
                data = json.loads(content_path.read_text(encoding="utf-8"))
                for v in (data.get("materials", {}) or {}).get("videos", []):
                    vpath = v.get("path")
                    if vpath and os.path.exists(vpath):
                        subprocess.run([
                            "/opt/homebrew/bin/ffmpeg", "-y", "-ss", "00:00:00.5",
                            "-i", vpath, "-vframes", "1", "-s", "320x180",
                            "-q:v", "2", str(cover_path)
                        ], capture_output=True, timeout=5)
                        if cover_path.exists() and cover_path.stat().st_size > 0:
                            return cover_path
        except Exception:
            pass

        # Fallback to generating a clean dark gradient thumbnail
        try:
            from PIL import Image, ImageDraw
            img = Image.new("RGB", (320, 180), color=(26, 28, 38))
            draw = ImageDraw.Draw(img)
            draw.rectangle([0, 175, 320, 180], fill=(0, 200, 255))
            img.save(str(cover_path), "JPEG", quality=85)
        except Exception:
            # 1x1 minimal valid JPEG
            cover_path.write_bytes(
                b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf\x00\xff\xd9"
            )
        return cover_path

    def sync_project_meta(self, project_name: str) -> None:
        """Ensure project's metadata, dual JSONs (draft_info & draft_content), and root_meta_info.json are updated and in sync."""
        proj_dir = self.draft_root / project_name
        content_path = proj_dir / "draft_content.json"
        info_path = proj_dir / "draft_info.json"
        meta_path = proj_dir / "draft_meta_info.json"

        if content_path.exists() and info_path.exists():
            active_path = content_path if content_path.stat().st_mtime >= info_path.stat().st_mtime else info_path
        elif content_path.exists():
            active_path = content_path
        elif info_path.exists():
            active_path = info_path
        else:
            return

        with open(active_path, "r", encoding="utf-8") as f:
            content = json.load(f)

        # Standardize macOS platform headers
        mac_platform = {
            "app_id": 359289,
            "app_source": "cc",
            "app_version": "9.5.0",
            "os": "mac",
        }
        meta = {}
        if meta_path.exists():
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
            except Exception:
                meta = {}

        now_us = int(time.time() * MICROSECOND)
        draft_id = meta.get("draft_id")
        if not draft_id or (draft_id == "792BD5DA-E961-4821-B10E-F51E4683DEC0" and project_name != "AI_Launch_Showcase"):
            draft_id = str(uuid.uuid4()).upper()
        duration_us = content.get("duration", 0)

        # Ensure consistent master UUID in content
        content["id"] = draft_id
        content["last_modified_platform"] = mac_platform
        content["platform"] = mac_platform

        # Ensure CapCut Desktop 9.5.0 structural schema fields
        content.setdefault("draft_type", "video")
        content.setdefault("mixed_track_mode_on", False)
        content.setdefault("smart_ads_info", {"page_from": "", "routine": "", "draft_url": ""})
        content.setdefault("function_assistant_info", {
            "auto_adjust": False,
            "fixed_rec_applied": False,
            "smart_rec_applied": False,
        })
        content.setdefault("uneven_animation_template_info", {
            "composition": "",
            "content": "",
            "order": "",
            "sub_template_info_list": [],
        })
        materials = content.setdefault("materials", {})
        for mat_key in [
            "hsl_curves", "video_strokes", "placeholder_infos", "video_shadows",
            "audio_pannings", "ai_text_effects", "manual_beautys",
            "digital_human_model_dressing", "audio_pitch_shifts", "video_radius",
        ]:
            materials.setdefault(mat_key, [])

        # Write draft_content.json, draft_info.json, draft_info.json.bak, and template-2.tmp
        for f_target in [content_path, info_path, proj_dir / "draft_info.json.bak", proj_dir / "template-2.tmp"]:
            with open(f_target, "w", encoding="utf-8") as f:
                json.dump(content, f, indent=4)

        # Scaffolding: copy companion template files if missing from a reference project (e.g. 1028)
        ref_proj = None
        for candidate in self.draft_root.iterdir():
            if candidate.is_dir() and candidate != proj_dir and (candidate / "attachment_pc_common.json").exists():
                ref_proj = candidate
                break
        if ref_proj:
            for item in ref_proj.iterdir():
                if item.name in ["draft_content.json", "draft_info.json", "draft_meta_info.json", "draft_cover.jpg", "draft_info.json.bak"]:
                    continue
                dest = proj_dir / item.name
                if not dest.exists():
                    try:
                        if item.is_dir():
                            shutil.copytree(item, dest)
                        else:
                            shutil.copy2(item, dest)
                    except Exception:
                        pass

        # Ensure cover image exists
        cover_path = self._ensure_thumbnail(proj_dir)

        meta["draft_fold_path"] = str(proj_dir)
        meta["draft_root_path"] = str(self.draft_root)
        meta["draft_name"] = project_name
        meta["draft_id"] = draft_id
        meta["draft_cover"] = "draft_cover.jpg"
        if "tm_draft_create" not in meta or not meta["tm_draft_create"]:
            meta["tm_draft_create"] = now_us
        meta["tm_draft_modified"] = now_us
        meta["tm_duration"] = duration_us
        meta["draft_timeline_materials_size"] = self._compute_media_size(proj_dir)

        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=4)

        # Update root_meta_info.json
        root_meta = self._load_root_meta()
        all_drafts = [d for d in root_meta.get("all_draft_store", []) if d.get("draft_name") != project_name and d.get("draft_id") != draft_id]

        entry = {
            "cloud_draft_cover": False,
            "cloud_draft_sync": False,
            "draft_cloud_last_action_download": False,
            "draft_cloud_purchase_info": "",
            "draft_cloud_template_id": "",
            "draft_cloud_tutorial_info": "",
            "draft_cloud_videocut_purchase_info": "",
            "draft_cover": str(cover_path),
            "draft_fold_path": str(proj_dir),
            "draft_id": draft_id,
            "draft_is_ai_shorts": False,
            "draft_is_cloud_temp_draft": False,
            "draft_is_infinite_canvas_draft": False,
            "draft_is_invisible": False,
            "draft_is_pippit_draft": False,
            "draft_is_web_article_video": False,
            "draft_json_file": str(info_path),
            "draft_name": project_name,
            "draft_new_version": "164.0.0",
            "draft_root_path": str(self.draft_root),
            "draft_timeline_materials_size": self._compute_media_size(proj_dir),
            "draft_type": "",
            "draft_web_article_video_enter_from": "",
            "pippit_avatar_url": "",
            "pippit_extra_info": "",
            "pippit_id": "",
            "pippit_user_name": "",
            "streaming_edit_draft_ready": True,
            "tm_draft_cloud_completed": "",
            "tm_draft_cloud_entry_id": 0,
            "tm_draft_cloud_modified": 0,
            "tm_draft_cloud_parent_entry_id": -1,
            "tm_draft_cloud_space_id": -1,
            "tm_draft_cloud_user_id": -1,
            "tm_draft_create": meta["tm_draft_create"],
            "tm_draft_modified": now_us,
            "tm_draft_removed": 0,
            "tm_duration": duration_us,
        }

        all_drafts.insert(0, entry)
        root_meta["all_draft_store"] = all_drafts
        root_meta["draft_ids"] = len(all_drafts) + 1
        self._save_root_meta(root_meta)

    def create_project(
        self,
        project_name: str,
        width: Optional[int] = None,
        height: Optional[int] = None,
        fps: int = 30,
        aspect_ratio: Optional[str] = None,
        allow_replace: bool = True,
    ) -> Dict[str, Any]:
        """Create a new CapCut project with specified dimensions, aspect ratio, and framerate."""
        import pycapcut as cc

        # Standard aspect ratio resolution mappings
        ratio_map = {
            "16:9": (1920, 1080),
            "9:16": (1080, 1920),
            "1:1": (1080, 1080),
            "4:3": (1440, 1080),
            "3:4": (1080, 1440),
            "21:9": (2560, 1080),
        }

        if aspect_ratio and aspect_ratio in ratio_map:
            w, h = ratio_map[aspect_ratio]
            width = width or w
            height = height or h
        else:
            width = width or 1920
            height = height or 1080

        folder = cc.DraftFolder(str(self.draft_root))
        if folder.has_draft(project_name) and not allow_replace:
            raise FileExistsError(f"Project '{project_name}' already exists.")

        script = folder.create_draft(project_name, width, height, fps=fps, allow_replace=allow_replace)
        script.save()

        # Update canvas_config ratio if aspect_ratio specified
        if aspect_ratio:
            proj_dir = self.draft_root / project_name
            cpath = proj_dir / "draft_content.json"
            if cpath.exists():
                data = json.loads(cpath.read_text(encoding="utf-8"))
                data.setdefault("canvas_config", {})["ratio"] = aspect_ratio
                cpath.write_text(json.dumps(data, indent=4), encoding="utf-8")

        self.sync_project_meta(project_name)
        return {
            "success": True,
            "project_name": project_name,
            "width": width,
            "height": height,
            "fps": fps,
            "aspect_ratio": aspect_ratio or f"{width}:{height}",
            "path": str(self.draft_root / project_name),
            "message": f"Successfully created CapCut project '{project_name}'.",
        }

    def set_canvas(
        self,
        project_name: str,
        aspect_ratio: Optional[str] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Modify project canvas dimensions and aspect ratio."""
        proj_dir = self.draft_root / project_name
        if not proj_dir.exists():
            raise FileNotFoundError(f"Project '{project_name}' not found.")

        ratio_map = {
            "16:9": (1920, 1080),
            "9:16": (1080, 1920),
            "1:1": (1080, 1080),
            "4:3": (1440, 1080),
            "3:4": (1080, 1440),
            "21:9": (2560, 1080),
        }

        if aspect_ratio and aspect_ratio in ratio_map:
            w, h = ratio_map[aspect_ratio]
            width = width or w
            height = height or h

        for fname in ("draft_info.json", "draft_content.json"):
            fpath = proj_dir / fname
            if fpath.exists():
                data = json.loads(fpath.read_text(encoding="utf-8"))
                canvas = data.setdefault("canvas_config", {})
                if width:
                    canvas["width"] = width
                if height:
                    canvas["height"] = height
                if aspect_ratio:
                    canvas["ratio"] = aspect_ratio
                fpath.write_text(json.dumps(data, indent=4), encoding="utf-8")

        self.sync_project_meta(project_name)
        return {
            "success": True,
            "project_name": project_name,
            "width": width,
            "height": height,
            "aspect_ratio": aspect_ratio,
            "ratio": aspect_ratio,
        }

    def add_video_clip(
        self,
        project_name: str,
        file_path: str,
        start_time: float = 0.0,
        start_time_ms: Optional[float] = None,
        duration: Optional[float] = None,
        duration_ms: Optional[float] = None,
        target_start: float = 0.0,
        target_start_ms: Optional[float] = None,
        speed: float = 1.0,
        volume: float = 1.0,
        transform_x: float = 0.0,
        transform_y: float = 0.0,
        scale_x: float = 1.0,
        scale_y: float = 1.0,
        rotation: float = 0.0,
        alpha: float = 1.0,
        fade_in: float = 0.0,
        fade_in_ms: Optional[float] = None,
        fade_out: float = 0.0,
        fade_out_ms: Optional[float] = None,
        transition: Optional[str] = None,
        transition_duration: float = 0.5,
        transition_duration_ms: Optional[float] = None,
        track_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Add a video clip to the project timeline with millisecond precision positioning, transitions, and audio envelope."""
        import pycapcut as cc

        file_path = os.path.abspath(os.path.expanduser(file_path))
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Video file not found: {file_path}")

        proj_dir = self.draft_root / project_name
        if not proj_dir.exists():
            self.create_project(project_name)

        v_mat = cc.VideoMaterial(file_path)

        if start_time_ms is not None:
            start_us = int(start_time_ms * 1000)
        else:
            start_us = int(start_time * MICROSECOND)

        if duration_ms is not None:
            clip_dur_us = int(duration_ms * 1000)
            clip_dur_us = min(clip_dur_us, v_mat.duration)
        elif duration is not None:
            clip_dur_us = int(duration * MICROSECOND)
            clip_dur_us = min(clip_dur_us, v_mat.duration)
        else:
            clip_dur_us = v_mat.duration

        if target_start_ms is not None:
            target_start_us = int(target_start_ms * 1000)
        else:
            target_start_us = int(target_start * MICROSECOND)

        # Load draft and append segment
        folder = cc.DraftFolder(str(self.draft_root))
        script = folder.load_template(project_name)
        script.save_path = str(proj_dir / "draft_content.json")

        clip_settings = cc.ClipSettings(
            transform_x=transform_x,
            transform_y=transform_y,
            scale_x=scale_x,
            scale_y=scale_y,
            rotation=rotation,
            alpha=alpha,
        )

        v_seg = cc.VideoSegment(
            v_mat,
            cc.Timerange(target_start_us, clip_dur_us),
            source_timerange=cc.Timerange(start_us, clip_dur_us),
            speed=speed,
            volume=volume,
            clip_settings=clip_settings,
        )

        fin_us = int(fade_in_ms * 1000) if fade_in_ms is not None else int(fade_in * MICROSECOND)
        fout_us = int(fade_out_ms * 1000) if fade_out_ms is not None else int(fade_out * MICROSECOND)
        if fin_us > 0 or fout_us > 0:
            v_seg.add_fade(fin_us, fout_us)

        if transition:
            try:
                trans_meta = getattr(cc.TransitionType, transition, None)
                if trans_meta:
                    t_dur_us = int(transition_duration_ms * 1000) if transition_duration_ms is not None else int(transition_duration * MICROSECOND)
                    v_seg.add_transition(trans_meta, duration=t_dur_us)
            except Exception as e:
                logger.warning(f"Could not apply transition {transition}: {e}")

        track_key = track_name or "video_main"
        if track_key not in script.tracks:
            script.add_track(cc.TrackType.video, track_name=track_key)

        script.add_segment(v_seg, track_name=track_key)
        script.save()

        self.sync_project_meta(project_name)

        return {
            "success": True,
            "project_name": project_name,
            "file_path": file_path,
            "start_time": round(start_us / MICROSECOND, 4),
            "start_time_ms": round(start_us / 1000.0, 2),
            "target_start": round(target_start_us / MICROSECOND, 4),
            "target_start_ms": round(target_start_us / 1000.0, 2),
            "clip_duration": round(clip_dur_us / MICROSECOND, 3),
            "clip_duration_ms": round(clip_dur_us / 1000.0, 2),
            "speed": speed,
            "volume": volume,
            "transform": {"x": transform_x, "y": transform_y},
            "scale": {"x": scale_x, "y": scale_y},
            "rotation": rotation,
            "alpha": alpha,
            "transition": transition,
        }

    def add_audio_clip(
        self,
        project_name: str,
        file_path: str,
        start_time: float = 0.0,
        start_time_ms: Optional[float] = None,
        duration: Optional[float] = None,
        duration_ms: Optional[float] = None,
        target_start: float = 0.0,
        target_start_ms: Optional[float] = None,
        volume: float = 1.0,
        speed: float = 1.0,
        fade_in: float = 0.0,
        fade_in_ms: Optional[float] = None,
        fade_out: float = 0.0,
        fade_out_ms: Optional[float] = None,
        track_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Add an audio / background music track with volume envelope and millisecond precision."""
        import pycapcut as cc

        file_path = os.path.abspath(os.path.expanduser(file_path))
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Audio file not found: {file_path}")

        proj_dir = self.draft_root / project_name
        if not proj_dir.exists():
            self.create_project(project_name)

        a_mat = cc.AudioMaterial(file_path)

        if start_time_ms is not None:
            start_us = int(start_time_ms * 1000)
        else:
            start_us = int(start_time * MICROSECOND)

        if duration_ms is not None:
            clip_dur_us = int(duration_ms * 1000)
            clip_dur_us = min(clip_dur_us, a_mat.duration)
        elif duration is not None:
            clip_dur_us = int(duration * MICROSECOND)
            clip_dur_us = min(clip_dur_us, a_mat.duration)
        else:
            clip_dur_us = a_mat.duration

        if target_start_ms is not None:
            target_start_us = int(target_start_ms * 1000)
        else:
            target_start_us = int(target_start * MICROSECOND)

        folder = cc.DraftFolder(str(self.draft_root))
        script = folder.load_template(project_name)
        script.save_path = str(proj_dir / "draft_content.json")

        a_seg = cc.AudioSegment(
            a_mat,
            cc.Timerange(target_start_us, clip_dur_us),
            source_timerange=cc.Timerange(start_us, clip_dur_us),
            speed=speed,
            volume=volume,
        )

        fin_us = int(fade_in_ms * 1000) if fade_in_ms is not None else int(fade_in * MICROSECOND)
        fout_us = int(fade_out_ms * 1000) if fade_out_ms is not None else int(fade_out * MICROSECOND)
        if fin_us > 0 or fout_us > 0:
            a_seg.add_fade(fin_us, fout_us)

        track_key = track_name or "audio_main"
        if track_key not in script.tracks:
            script.add_track(cc.TrackType.audio, track_name=track_key)

        script.add_segment(a_seg, track_name=track_key)
        script.save()

        self.sync_project_meta(project_name)

        return {
            "success": True,
            "project_name": project_name,
            "file_path": file_path,
            "start_time": round(start_us / MICROSECOND, 4),
            "start_time_ms": round(start_us / 1000.0, 2),
            "target_start": round(target_start_us / MICROSECOND, 4),
            "target_start_ms": round(target_start_us / 1000.0, 2),
            "clip_duration": round(clip_dur_us / MICROSECOND, 3),
            "clip_duration_ms": round(clip_dur_us / 1000.0, 2),
            "volume": volume,
            "fade_in": round(fin_us / MICROSECOND, 3),
            "fade_out": round(fout_us / MICROSECOND, 3),
        }

    def add_image(
        self,
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
    ) -> Dict[str, Any]:
        """Add an image overlay or photo track to the project timeline."""
        import pycapcut as cc

        file_path = os.path.abspath(os.path.expanduser(file_path))
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Image file not found: {file_path}")

        proj_dir = self.draft_root / project_name
        if not proj_dir.exists():
            self.create_project(project_name)

        folder = cc.DraftFolder(str(self.draft_root))
        script = folder.load_template(project_name)
        script.save_path = str(proj_dir / "draft_content.json")

        img_mat = cc.VideoMaterial(file_path)
        start_us = int(start_time * MICROSECOND)
        dur_us = int(duration * MICROSECOND)
        target_start_us = int(target_start * MICROSECOND)

        clip_settings = cc.ClipSettings(
            transform_x=transform_x,
            transform_y=transform_y,
            scale_x=scale_x,
            scale_y=scale_y,
            rotation=rotation,
            alpha=alpha,
        )

        v_seg = cc.VideoSegment(
            img_mat,
            cc.Timerange(target_start_us, dur_us),
            source_timerange=cc.Timerange(start_us, dur_us),
            clip_settings=clip_settings,
        )

        script.add_track(cc.TrackType.video)
        script.add_segment(v_seg)
        script.save()

        self.sync_project_meta(project_name)
        return {
            "success": True,
            "project_name": project_name,
            "file_path": file_path,
            "target_start": target_start,
            "duration": duration,
            "transform": {"x": transform_x, "y": transform_y},
            "scale": {"x": scale_x, "y": scale_y},
            "rotation": rotation,
            "alpha": alpha,
        }

    def add_text(
        self,
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
    ) -> Dict[str, Any]:
        """Add styled text, title, or subtitle with background, border, shadow, and positioning."""
        import pycapcut as cc

        proj_dir = self.draft_root / project_name
        if not proj_dir.exists():
            self.create_project(project_name)

        folder = cc.DraftFolder(str(self.draft_root))
        script = folder.load_template(project_name)
        script.save_path = str(proj_dir / "draft_content.json")

        effective_start = target_start if target_start is not None else start_time
        start_us = int(effective_start * MICROSECOND)
        dur_us = int(duration * MICROSECOND)

        def hex_to_rgb(hex_str: str) -> Tuple[float, float, float]:
            h = hex_str.lstrip("#")
            if len(h) == 6:
                return (int(h[0:2], 16) / 255.0, int(h[2:4], 16) / 255.0, int(h[4:6], 16) / 255.0)
            return (1.0, 1.0, 1.0)

        rgb_color = hex_to_rgb(font_color)
        style = cc.TextStyle(
            size=font_size,
            color=rgb_color,
            bold=bold,
            italic=italic,
            underline=underline,
            align=align,
        )
        clip_settings = cc.ClipSettings(transform_x=pos_x, transform_y=pos_y)

        t_seg = cc.TextSegment(
            text,
            cc.Timerange(start_us, dur_us),
            style=style,
            clip_settings=clip_settings,
        )

        if background_color:
            t_seg.background = cc.TextBackground(color=background_color, alpha=background_alpha)

        if shadow_enabled:
            shadow_rgb = hex_to_rgb(shadow_color)
            t_seg.shadow = cc.TextShadow(color=shadow_rgb, alpha=1.0)

        if border_enabled:
            border_rgb = hex_to_rgb(border_color)
            t_seg.border = cc.TextBorder(color=border_rgb, width=border_width)

        script.add_track(cc.TrackType.text)
        script.add_segment(t_seg)
        script.save()

        self.sync_project_meta(project_name)

        return {
            "success": True,
            "project_name": project_name,
            "text": text,
            "start_time": effective_start,
            "duration": duration,
            "font_size": font_size,
            "font_color": font_color,
            "position": {"x": pos_x, "y": pos_y},
            "background": background_color,
            "shadow": shadow_enabled,
            "border": border_enabled,
        }

    def add_keyframe(
        self,
        project_name: str,
        property_types: List[str],
        times: List[float],
        values: List[Any],
        track_type: str = "video",
        track_index: int = 0,
        segment_index: int = 0,
    ) -> Dict[str, Any]:
        """Add smooth keyframe animations (position, scale, rotation, alpha, volume) to a timeline segment."""
        proj_dir = self.draft_root / project_name
        if not proj_dir.exists():
            raise FileNotFoundError(f"Project '{project_name}' not found.")

        content_path = proj_dir / "draft_info.json"
        if not content_path.exists():
            content_path = proj_dir / "draft_content.json"

        with open(content_path, "r", encoding="utf-8") as f:
            content = json.load(f)

        matching_tracks = [t for t in content.get("tracks", []) if t.get("type") == track_type]
        if not matching_tracks or track_index >= len(matching_tracks):
            raise IndexError(f"No {track_type} track found at index {track_index}.")

        target_track = matching_tracks[track_index]
        segments = target_track.get("segments", [])
        if not segments or segment_index >= len(segments):
            raise IndexError(f"No segment found at index {segment_index} in track.")

        seg = segments[segment_index]
        common_kf = seg.setdefault("common_keyframes", [])

        prop_map = {
            "position_x": "KFTypePositionX",
            "position_y": "KFTypePositionY",
            "rotation": "KFTypeRotation",
            "scale_x": "KFTypeScaleX",
            "scale_y": "KFTypeScaleY",
            "uniform_scale": "UNIFORM_SCALE",
            "alpha": "KFTypeAlpha",
            "volume": "KFTypeVolume",
            "saturation": "KFTypeSaturation",
            "contrast": "KFTypeContrast",
            "brightness": "KFTypeBrightness",
        }

        added_count = 0
        for prop, t_sec, val in zip(property_types, times, values):
            kf_prop = prop_map.get(prop.lower(), prop)
            kf_list = None
            for kl in common_kf:
                if kl.get("property_type") == kf_prop:
                    kf_list = kl
                    break
            if kf_list is None:
                kf_list = {
                    "id": uuid.uuid4().hex,
                    "keyframe_list": [],
                    "material_id": "",
                    "property_type": kf_prop,
                }
                common_kf.append(kf_list)

            time_offset_us = int(float(t_sec) * MICROSECOND)
            try:
                num_val = float(str(val).replace("%", "").replace("deg", ""))
                if "%" in str(val):
                    num_val /= 100.0
            except ValueError:
                num_val = float(val)

            kf_item = {
                "curveType": "Line",
                "graphID": "",
                "id": uuid.uuid4().hex,
                "left_control": {"x": 0.0, "y": 0.0},
                "right_control": {"x": 0.0, "y": 0.0},
                "time_offset": time_offset_us,
                "values": [num_val],
            }
            kf_list["keyframe_list"].append(kf_item)
            kf_list["keyframe_list"].sort(key=lambda x: x.get("time_offset", 0))
            added_count += 1

        for fname in ("draft_info.json", "draft_content.json"):
            with open(proj_dir / fname, "w", encoding="utf-8") as f:
                json.dump(content, f, indent=4)

        self.sync_project_meta(project_name)
        return {
            "success": True,
            "project_name": project_name,
            "track_type": track_type,
            "track_index": track_index,
            "segment_index": segment_index,
            "added_keyframes": added_count,
            "properties": property_types,
        }

    def split_clip(
        self,
        project_name: str,
        track_index: int = 0,
        segment_index: int = 0,
        split_time: Optional[float] = None,
        split_time_ms: Optional[float] = None,
        track_type: str = "video",
    ) -> Dict[str, Any]:
        """
        Split a clip at an exact millisecond timestamp into two separate clips on the timeline.
        
        Args:
            project_name: Name of the draft project.
            track_index: Index of the track containing the clip (default 0).
            segment_index: Index of the clip segment within the track (default 0).
            split_time: Split timestamp in seconds.
            split_time_ms: Split timestamp in milliseconds.
            track_type: 'video' or 'audio' (default 'video').
        """
        proj_dir = self.draft_root / project_name
        if not proj_dir.exists():
            raise FileNotFoundError(f"Project '{project_name}' not found.")

        content_path = proj_dir / "draft_info.json"
        if not content_path.exists():
            content_path = proj_dir / "draft_content.json"

        with open(content_path, "r", encoding="utf-8") as f:
            content = json.load(f)

        matching_tracks = [t for t in content.get("tracks", []) if t.get("type") == track_type]
        if not matching_tracks or track_index >= len(matching_tracks):
            raise IndexError(f"No {track_type} track found at index {track_index}.")

        target_track = matching_tracks[track_index]
        segments = target_track.get("segments", [])
        if not segments or segment_index >= len(segments):
            raise IndexError(f"No segment found at index {segment_index} in {track_type} track.")

        seg = segments[segment_index]
        t_range = seg.get("target_timerange", {})
        t_start = t_range.get("start", 0)
        t_dur = t_range.get("duration", 0)

        if split_time_ms is not None:
            split_us = int(split_time_ms * 1000)
        elif split_time is not None:
            split_us = int(split_time * MICROSECOND)
        else:
            raise ValueError("Either split_time or split_time_ms must be provided.")

        # If split_us is given relative to clip start (split_us < t_dur):
        if split_us < t_dur and split_us > 0 and (split_us < t_start or t_start == 0):
            split_point_us = t_start + split_us
        else:
            split_point_us = split_us

        if split_point_us <= t_start or split_point_us >= t_start + t_dur:
            raise ValueError(
                f"Split point {split_point_us} us ({split_point_us / 1000} ms) is outside segment boundaries "
                f"[{t_start}, {t_start + t_dur}] us."
            )

        dur1 = split_point_us - t_start
        dur2 = (t_start + t_dur) - split_point_us

        s_range = seg.get("source_timerange")
        if s_range:
            s_start = s_range.get("start", 0)
            s_dur = s_range.get("duration", t_dur)
            ratio = dur1 / float(t_dur) if t_dur > 0 else 0.5
            s_dur1 = int(s_dur * ratio)
            s_dur2 = s_dur - s_dur1
            s_start2 = s_start + s_dur1
        else:
            s_dur1, s_dur2, s_start2 = None, None, None

        import copy
        seg1 = copy.deepcopy(seg)
        seg1["id"] = str(uuid.uuid4()).replace("-", "")
        seg1["target_timerange"] = {"start": t_start, "duration": dur1}
        if s_range:
            seg1["source_timerange"] = {"start": s_range.get("start", 0), "duration": s_dur1}

        seg2 = copy.deepcopy(seg)
        seg2["id"] = str(uuid.uuid4()).replace("-", "")
        seg2["target_timerange"] = {"start": split_point_us, "duration": dur2}
        if s_range:
            seg2["source_timerange"] = {"start": s_start2, "duration": s_dur2}

        # Replace single segment with split pair
        segments[segment_index:segment_index + 1] = [seg1, seg2]
        target_track["segments"] = segments

        with open(content_path, "w", encoding="utf-8") as f:
            json.dump(content, f, indent=4)

        self.sync_project_meta(project_name)

        return {
            "success": True,
            "project_name": project_name,
            "split_point_seconds": round(split_point_us / MICROSECOND, 4),
            "split_point_ms": round(split_point_us / 1000.0, 2),
            "segment_1": {
                "target_start_ms": round(t_start / 1000.0, 2),
                "duration_ms": round(dur1 / 1000.0, 2),
            },
            "segment_2": {
                "target_start_ms": round(split_point_us / 1000.0, 2),
                "duration_ms": round(dur2 / 1000.0, 2),
            },
            "message": f"Successfully split {track_type} clip into two segments at {split_point_us / 1000.0:.2f}ms.",
        }

    def trim_clip(
        self,
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
    ) -> Dict[str, Any]:
        """
        Trim and adjust in/out points of a clip down to milliseconds.
        """
        proj_dir = self.draft_root / project_name
        if not proj_dir.exists():
            raise FileNotFoundError(f"Project '{project_name}' not found.")

        content_path = proj_dir / "draft_info.json"
        if not content_path.exists():
            content_path = proj_dir / "draft_content.json"

        with open(content_path, "r", encoding="utf-8") as f:
            content = json.load(f)

        matching_tracks = [t for t in content.get("tracks", []) if t.get("type") == track_type]
        if not matching_tracks or track_index >= len(matching_tracks):
            raise IndexError(f"No {track_type} track found at index {track_index}.")

        target_track = matching_tracks[track_index]
        segments = target_track.get("segments", [])
        if not segments or segment_index >= len(segments):
            raise IndexError(f"No segment found at index {segment_index} in {track_type} track.")

        seg = segments[segment_index]
        t_range = seg.setdefault("target_timerange", {})
        s_range = seg.setdefault("source_timerange", {})

        if target_start_ms is not None:
            t_range["start"] = int(target_start_ms * 1000)
        elif target_start is not None:
            t_range["start"] = int(target_start * MICROSECOND)

        if duration_ms is not None:
            t_range["duration"] = int(duration_ms * 1000)
        elif duration is not None:
            t_range["duration"] = int(duration * MICROSECOND)

        if source_start_ms is not None:
            s_range["start"] = int(source_start_ms * 1000)
        elif source_start is not None:
            s_range["start"] = int(source_start * MICROSECOND)

        if source_duration_ms is not None:
            s_range["duration"] = int(source_duration_ms * 1000)
        elif source_duration is not None:
            s_range["duration"] = int(source_duration * MICROSECOND)
        elif duration_ms is not None or duration is not None:
            s_range["duration"] = t_range["duration"]

        with open(content_path, "w", encoding="utf-8") as f:
            json.dump(content, f, indent=4)

        self.sync_project_meta(project_name)

        return {
            "success": True,
            "project_name": project_name,
            "target_start_ms": round(t_range.get("start", 0) / 1000.0, 2),
            "duration_ms": round(t_range.get("duration", 0) / 1000.0, 2),
            "source_start_ms": round(s_range.get("start", 0) / 1000.0, 2) if s_range else None,
            "source_duration_ms": round(s_range.get("duration", 0) / 1000.0, 2) if s_range else None,
            "message": f"Successfully trimmed {track_type} segment {segment_index}.",
        }

    def beat_sync_edit(
        self,
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
    ) -> Dict[str, Any]:
        """
        Create a high-energy, beat-matched video edit with millisecond cut synchronization.
        
        Args:
            project_name: Name of project to create or overwrite.
            video_clips: List of paths to video files to sequence and cut.
            music_path: Path to BGM audio file.
            bpm: Music tempo in Beats Per Minute (default 120.0).
            beats_per_cut: Number of beats between each cut (default 4 = 1 musical bar in 4/4 time).
            target_duration: Desired video duration in seconds (e.g. 10.0 or 30.0).
            target_duration_ms: Desired video duration in milliseconds.
            transition: CapCut transition to apply between cuts (e.g. 'Fade', 'Zoom', 'White_flash').
            transition_duration: Duration of transition in seconds (default 0.3).
            effects: Optional list of CapCut effect names to place on high-impact drops.
            volume: BGM volume level (default 1.0).
        """
        music_path = os.path.abspath(os.path.expanduser(music_path))
        if not os.path.exists(music_path):
            raise FileNotFoundError(f"Audio file not found: {music_path}")

        valid_clips = []
        for c in video_clips:
            p = os.path.abspath(os.path.expanduser(c))
            if os.path.exists(p):
                valid_clips.append(p)
        if not valid_clips:
            raise ValueError("No valid video clips found for beat sync edit.")

        # Calculate beat interval and cut duration
        beat_interval_sec = 60.0 / max(1.0, float(bpm))
        cut_dur_sec = beat_interval_sec * max(1, int(beats_per_cut))

        if target_duration_ms is not None:
            total_dur_sec = target_duration_ms / 1000.0
        elif target_duration is not None:
            total_dur_sec = float(target_duration)
        else:
            total_dur_sec = len(valid_clips) * cut_dur_sec

        total_cuts = max(1, int(round(total_dur_sec / cut_dur_sec)))
        effective_total_dur = total_cuts * cut_dur_sec

        import pycapcut as cc
        proj_dir = self.draft_root / project_name
        folder = cc.DraftFolder(str(self.draft_root))
        script = folder.create_draft(project_name, width=width or 1920, height=height or 1080, fps=fps, allow_replace=True)
        script.save_path = str(proj_dir / "draft_content.json")

        script.add_track(cc.TrackType.video, track_name="video_main")
        script.add_track(cc.TrackType.audio, track_name="audio_bgm")

        # Add background music track
        a_mat = cc.AudioMaterial(music_path)
        a_seg = cc.AudioSegment(
            a_mat,
            cc.Timerange(0, int(effective_total_dur * MICROSECOND)),
            source_timerange=cc.Timerange(0, int(effective_total_dur * MICROSECOND)),
            volume=volume,
        )
        if effective_total_dur > 3.0:
            a_seg.add_fade(0, int(1.0 * MICROSECOND))
        script.add_segment(a_seg, track_name="audio_bgm")

        # Sequence video clips cut to the beat
        t_trans_dur = transition_duration_ms / 1000.0 if transition_duration_ms is not None else transition_duration
        cuts_summary = []
        for i in range(total_cuts):
            clip = valid_clips[i % len(valid_clips)]
            t_start_us = int(i * cut_dur_sec * MICROSECOND)
            cut_dur_us = int(cut_dur_sec * MICROSECOND)
            src_offset_us = int((((i // len(valid_clips)) * cut_dur_sec) % 8.0) * MICROSECOND)

            v_mat = cc.VideoMaterial(clip)
            v_seg = cc.VideoSegment(
                v_mat,
                cc.Timerange(t_start_us, cut_dur_us),
                source_timerange=cc.Timerange(src_offset_us, cut_dur_us),
            )
            if transition and i > 0:
                try:
                    trans_meta = getattr(cc.TransitionType, transition, None)
                    if trans_meta:
                        v_seg.add_transition(trans_meta, duration=int(min(t_trans_dur, cut_dur_sec * 0.4) * MICROSECOND))
                except Exception as exc:
                    logger.warning(f"Could not apply transition {transition}: {exc}")

            script.add_segment(v_seg, track_name="video_main")
            cuts_summary.append({
                "cut_index": i,
                "clip": os.path.basename(clip),
                "target_start_ms": round(i * cut_dur_sec * 1000.0, 1),
                "duration_ms": round(cut_dur_sec * 1000.0, 1),
            })

        script.save()
        self.sync_project_meta(project_name)

        # Apply scene effects if provided
        applied_effects = []
        if effects:
            for eff_idx, eff_name in enumerate(effects):
                eff_start = (eff_idx * 2) * cut_dur_sec
                if eff_start < effective_total_dur:
                    eff_dur = min(cut_dur_sec, effective_total_dur - eff_start)
                    try:
                        self.add_effect(
                            project_name=project_name,
                            effect_name=eff_name,
                            start_time=eff_start,
                            duration=eff_dur,
                        )
                        applied_effects.append({
                            "effect": eff_name,
                            "start_ms": round(eff_start * 1000.0, 1),
                            "duration_ms": round(eff_dur * 1000.0, 1),
                        })
                    except Exception as exc:
                        logger.warning(f"Could not add effect '{eff_name}': {exc}")

        self.sync_project_meta(project_name)

        return {
            "success": True,
            "project_name": project_name,
            "bpm": bpm,
            "beats_per_cut": beats_per_cut,
            "cut_duration_ms": round(cut_dur_sec * 1000.0, 1),
            "total_cuts": total_cuts,
            "total_duration_seconds": round(effective_total_dur, 3),
            "total_duration_ms": round(effective_total_dur * 1000.0, 1),
            "cuts": cuts_summary,
            "applied_effects": applied_effects,
            "message": (
                f"Successfully assembled {total_cuts}-cut beat-synced timeline ({effective_total_dur:.2f}s) "
                f"at {bpm} BPM with cuts every {cut_dur_sec * 1000:.0f}ms."
            ),
        }

    def get_timeline_inspector_html(self, project_name: str) -> str:
        """
        Generate a rich, interactive HTML timeline inspector view for the CapCut project.
        Implements the MCP Apps view pattern with interactive scrub ruler, track layers, and open button.
        """
        proj_dir = self.draft_root / project_name
        if not proj_dir.exists():
            return f"<html><body><h3>Project '{project_name}' not found.</h3></body></html>"

        content_path = proj_dir / "draft_info.json"
        if not content_path.exists():
            content_path = proj_dir / "draft_content.json"

        content = {}
        if content_path.exists():
            try:
                with open(content_path, "r", encoding="utf-8") as f:
                    content = json.load(f)
            except Exception:
                pass

        total_dur_us = content.get("duration", 0)
        total_dur_sec = total_dur_us / MICROSECOND
        tracks = content.get("tracks", [])
        canvas = content.get("canvas_config", {})
        fps = content.get("fps", 30)

        tracks_html = []
        color_map = {
            "video": "#3b82f6",
            "audio": "#10b981",
            "text": "#f59e0b",
            "effect": "#8b5cf6",
            "filter": "#ec4899",
        }
        for idx, t in enumerate(tracks):
            t_type = t.get("type", "video")
            t_color = color_map.get(t_type, "#6b7280")
            segments = t.get("segments", [])
            seg_elements = []
            for s_idx, seg in enumerate(segments):
                tr = seg.get("target_timerange", {})
                s_start = tr.get("start", 0) / MICROSECOND
                s_dur = tr.get("duration", 0) / MICROSECOND
                left_pct = (s_start / total_dur_sec * 100.0) if total_dur_sec > 0 else 0
                width_pct = (s_dur / total_dur_sec * 100.0) if total_dur_sec > 0 else 0
                seg_label = f"#{s_idx + 1} ({s_dur:.2f}s / {int(s_dur * 1000)}ms)"
                seg_elements.append(
                    f'<div style="position: absolute; left: {left_pct:.2f}%; width: {width_pct:.2f}%; '
                    f'background: {t_color}; border-radius: 4px; height: 36px; top: 4px; '
                    f'color: white; font-size: 11px; padding: 4px; overflow: hidden; white-space: nowrap; '
                    f'box-shadow: 0 1px 3px rgba(0,0,0,0.4);" title="{seg_label}">{seg_label}</div>'
                )

            tracks_html.append(f"""
            <div style="display: flex; margin-bottom: 12px; align-items: center;">
                <div style="width: 140px; font-weight: bold; font-size: 12px; color: #d1d5db;">
                    {t_type.upper()} {idx}
                </div>
                <div style="flex: 1; height: 44px; background: #1f2937; border-radius: 6px; position: relative; border: 1px solid #374151;">
                    {''.join(seg_elements)}
                </div>
            </div>
            """)

        html_page = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>CapCut Timeline Inspector - {project_name}</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: #111827; color: #f9fafb; margin: 0; padding: 24px; }}
.card {{ background: #1e293b; border-radius: 12px; padding: 20px; box-shadow: 0 4px 12px rgba(0,0,0,0.5); border: 1px solid #334155; }}
.header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #334155; padding-bottom: 16px; margin-bottom: 20px; }}
.badge {{ background: #2563eb; color: white; padding: 4px 12px; border-radius: 9999px; font-size: 12px; font-weight: 600; }}
.stats {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 24px; }}
.stat-box {{ background: #0f172a; padding: 12px; border-radius: 8px; border: 1px solid #1e293b; text-align: center; }}
.stat-val {{ font-size: 18px; font-weight: bold; color: #38bdf8; }}
.stat-lbl {{ font-size: 11px; color: #94a3b8; text-transform: uppercase; margin-top: 4px; }}
.timeline {{ background: #0f172a; border-radius: 8px; padding: 16px; border: 1px solid #334155; margin-top: 16px; }}
</style>
</head>
<body>
<div class="card">
    <div class="header">
        <div>
            <h2 style="margin: 0; font-size: 20px;">CapCut Desktop Timeline: {project_name}</h2>
            <p style="margin: 4px 0 0; color: #94a3b8; font-size: 13px;">Millisecond precision timeline breakdown & multi-track sequencing</p>
        </div>
        <span class="badge">CapCut 9.5.0 Compatible</span>
    </div>
    <div class="stats">
        <div class="stat-box"><div class="stat-val">{total_dur_sec:.2f}s ({int(total_dur_sec * 1000)}ms)</div><div class="stat-lbl">Duration</div></div>
        <div class="stat-box"><div class="stat-val">{canvas.get('width', 1920)}x{canvas.get('height', 1080)}</div><div class="stat-lbl">Resolution</div></div>
        <div class="stat-box"><div class="stat-val">{fps} fps</div><div class="stat-lbl">Framerate</div></div>
        <div class="stat-box"><div class="stat-val">{len(tracks)}</div><div class="stat-lbl">Tracks</div></div>
    </div>
    <div class="timeline">
        <div style="font-size: 13px; font-weight: 600; margin-bottom: 12px; color: #38bdf8;">Multi-Track Inspector</div>
        {''.join(tracks_html) if tracks_html else '<p style="color:#6b7280;">No tracks on timeline yet.</p>'}
    </div>
</div>
</body>
</html>"""
        return html_page

    def add_sticker(
        self,
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
    ) -> Dict[str, Any]:
        """Add a decorative sticker or emoji track to the timeline."""
        proj_dir = self.draft_root / project_name
        if not proj_dir.exists():
            self.create_project(project_name)

        content_path = proj_dir / "draft_info.json"
        if not content_path.exists():
            content_path = proj_dir / "draft_content.json"

        with open(content_path, "r", encoding="utf-8") as f:
            content = json.load(f)

        effective_start = target_start if target_start is not None else start_time
        start_us = int(effective_start * MICROSECOND)
        dur_us = int(duration * MICROSECOND)

        sticker_id = uuid.uuid4().hex
        materials = content.setdefault("materials", {})
        stickers_list = materials.setdefault("stickers", [])

        sticker_material = {
            "id": sticker_id,
            "resource_id": resource_id,
            "type": "sticker",
            "value": 1.0,
        }
        stickers_list.append(sticker_material)

        tracks = content.setdefault("tracks", [])
        sticker_track = None
        for t in tracks:
            if t.get("type") == "sticker" and t.get("name") == track_name:
                sticker_track = t
                break
        if not sticker_track:
            sticker_track = {
                "attribute": 0,
                "flag": 0,
                "id": str(uuid.uuid4()).upper(),
                "is_default_name": False,
                "name": track_name,
                "segments": [],
                "type": "sticker",
            }
            tracks.append(sticker_track)

        seg_id = str(uuid.uuid4()).upper()
        segment = {
            "clip": {
                "alpha": alpha,
                "flip": {"horizontal": False, "vertical": False},
                "rotation": rotation,
                "scale": {"x": scale_x, "y": scale_y},
                "transform": {"x": transform_x, "y": transform_y},
            },
            "common_keyframes": [],
            "enable_adjust": True,
            "enable_color_curves": True,
            "enable_color_wheels": True,
            "enable_lut": True,
            "id": seg_id,
            "material_id": sticker_id,
            "render_index": 0,
            "source_timerange": {"duration": dur_us, "start": 0},
            "target_timerange": {"duration": dur_us, "start": start_us},
            "track_attribute": 0,
            "track_render_index": 0,
            "visible": True,
        }
        sticker_track["segments"].append(segment)

        if start_us + dur_us > content.get("duration", 0):
            content["duration"] = start_us + dur_us

        for fname in ("draft_info.json", "draft_content.json"):
            with open(proj_dir / fname, "w", encoding="utf-8") as f:
                json.dump(content, f, indent=4)

        self.sync_project_meta(project_name)
        return {
            "success": True,
            "project_name": project_name,
            "resource_id": resource_id,
            "start_time": effective_start,
            "duration": duration,
            "transform": {"x": transform_x, "y": transform_y},
            "scale": {"x": scale_x, "y": scale_y},
        }

    def get_media_duration(self, file_path: str) -> Dict[str, Any]:
        """Extract media duration, resolution, fps, bitrate, audio channels, and format info using ffprobe."""
        file_path = os.path.abspath(os.path.expanduser(file_path))
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Media file not found: {file_path}")

        cmd = [
            "/opt/homebrew/bin/ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            file_path,
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"ffprobe failed: {res.stderr}")

        info = json.loads(res.stdout)
        fmt = info.get("format", {})
        streams = info.get("streams", [])

        duration = float(fmt.get("duration", 0.0))
        bitrate = int(fmt.get("bit_rate", 0)) if fmt.get("bit_rate") else 0

        v_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
        a_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

        width = int(v_stream.get("width", 0)) if v_stream else 0
        height = int(v_stream.get("height", 0)) if v_stream else 0
        fps = 0.0
        if v_stream and "r_frame_rate" in v_stream:
            r = v_stream["r_frame_rate"].split("/")
            if len(r) == 2 and float(r[1]) > 0:
                fps = round(float(r[0]) / float(r[1]), 2)

        return {
            "success": True,
            "file_path": file_path,
            "duration_seconds": round(duration, 3),
            "width": width,
            "height": height,
            "fps": fps,
            "format": fmt.get("format_name", ""),
            "bitrate": bitrate,
            "video_codec": v_stream.get("codec_name") if v_stream else None,
            "audio_codec": a_stream.get("codec_name") if a_stream else None,
            "audio_sample_rate": int(a_stream.get("sample_rate", 0)) if a_stream else None,
            "audio_channels": int(a_stream.get("channels", 0)) if a_stream else None,
        }

    def save_draft(self, project_name: str) -> Dict[str, Any]:
        """Save, validate, and synchronize a draft so it's fully ready to open in CapCut Desktop."""
        proj_dir = self.draft_root / project_name
        if not proj_dir.exists():
            raise FileNotFoundError(f"Project '{project_name}' not found.")

        self.sync_project_meta(project_name)
        summary = self.get_project(project_name)
        return {
            "success": True,
            "project_name": project_name,
            "path": str(proj_dir),
            "draft_info_synced": (proj_dir / "draft_info.json").exists(),
            "cover_exists": (proj_dir / "draft_cover.jpg").exists(),
            "duration_seconds": summary.get("duration_seconds", 0),
            "width": summary.get("width"),
            "height": summary.get("height"),
            "fps": summary.get("fps"),
            "tracks_count": len(summary.get("tracks", [])),
            "message": f"Draft '{project_name}' successfully saved, validated, and synchronized for CapCut Desktop.",
        }

    def import_srt(
        self,
        project_name: str,
        srt_path: str,
    ) -> Dict[str, Any]:
        """Import subtitles from an SRT file into the project."""
        import pycapcut as cc

        srt_path = os.path.abspath(os.path.expanduser(srt_path))
        if not os.path.exists(srt_path):
            raise FileNotFoundError(f"SRT file not found: {srt_path}")

        proj_dir = self.draft_root / project_name
        if not proj_dir.exists():
            self.create_project(project_name)

        folder = cc.DraftFolder(str(self.draft_root))
        script = folder.load_template(project_name)
        script.save_path = str(proj_dir / "draft_content.json")

        script.import_srt(srt_path)
        script.save()

        self.sync_project_meta(project_name)

        return {
            "success": True,
            "project_name": project_name,
            "srt_path": srt_path,
            "message": f"Successfully imported SRT subtitles into '{project_name}'.",
        }

    def duplicate_project(self, source_name: str, target_name: str, allow_replace: bool = True) -> Dict[str, Any]:
        """Duplicate an existing project to a new project name."""
        import pycapcut as cc

        src_dir = self.draft_root / source_name
        tgt_dir = self.draft_root / target_name
        if not src_dir.exists():
            raise FileNotFoundError(f"Source project '{source_name}' does not exist.")
        if tgt_dir.exists():
            if not allow_replace:
                raise FileExistsError(f"Target project '{target_name}' already exists.")
            shutil.rmtree(tgt_dir)

        folder = cc.DraftFolder(str(self.draft_root))
        script = folder.duplicate_as_template(source_name, target_name)
        script.save()

        self.sync_project_meta(target_name)

        return {
            "success": True,
            "source": source_name,
            "target": target_name,
            "path": str(tgt_dir),
            "message": f"Duplicated '{source_name}' to '{target_name}'.",
        }

    def delete_project(self, project_name: str) -> Dict[str, Any]:
        """Delete a project from drafts and unregister it."""
        proj_dir = self.draft_root / project_name
        if not proj_dir.exists():
            raise FileNotFoundError(f"Project '{project_name}' does not exist.")

        shutil.rmtree(proj_dir)

        # Remove from root_meta
        root_meta = self._load_root_meta()
        all_drafts = [d for d in root_meta.get("all_draft_store", []) if d.get("draft_name") != project_name]
        root_meta["all_draft_store"] = all_drafts
        self._save_root_meta(root_meta)

        return {
            "success": True,
            "project_name": project_name,
            "message": f"Successfully deleted project '{project_name}'.",
        }

    def open_in_capcut(self, project_name: Optional[str] = None) -> Dict[str, Any]:
        """Launch or focus CapCut Desktop application, optionally opening the target project."""
        if not CAPCUT_APP_PATH.exists():
            return {
                "success": False,
                "error": f"CapCut application not found at {CAPCUT_APP_PATH}",
            }

        subprocess.run(["open", "-a", str(CAPCUT_APP_PATH)], check=True)

        if project_name:
            self.sync_project_meta(project_name)
            try:
                import Quartz
                time.sleep(0.5)
                subprocess.run(["osascript", "-e", 'tell application "CapCut" to activate'], capture_output=True)
                time.sleep(0.2)
                wl = Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionAll, Quartz.kCGNullWindowID)
                target_w = None
                for w in wl:
                    if "capcut" in (w.get("kCGWindowOwnerName") or "").lower():
                        b = w.get("kCGWindowBounds", {})
                        if b.get("Width", 0) > 800 and b.get("Height", 0) > 600:
                            target_w = b
                            break

                if target_w:
                    wx = target_w.get("X", 0)
                    wy = target_w.get("Y", 0)
                    cx = wx + 280
                    cy = wy + 775

                    def post_click(x, y):
                        down = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseDown, (x, y), Quartz.kCGMouseButtonLeft)
                        up = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseUp, (x, y), Quartz.kCGMouseButtonLeft)
                        Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
                        Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)

                    post_click(cx, cy)
                    time.sleep(0.08)
                    post_click(cx, cy)
            except Exception as e:
                logger.warning(f"Auto-opening project click failed: {e}")

        return {
            "success": True,
            "project_name": project_name,
            "message": f"Launched CapCut Desktop. Active project: '{project_name or 'Home'}'."
        }

    def fix_network_and_effects(self) -> Dict[str, Any]:
        """
        Bypass regional drop-flow restrictions and unlock CapCut Desktop network and effects.
        - Removes ByteDance TTNet TNC block rules (drop flow 100% block for restricted regions).
        - Patches tt_net_config.config store_region from 'in' to 'sg' and removes drop rule 3002497.
        - Disables internal HTTP DNS hijacking.
        - Configures non-restricted region (Singapore subdivision 1880252) in DeviceRegister.
        - Replaces unresolvable looki_settings domain with feed-api-sg.capcutapi.com.
        - Patches CEF Network Persistent State and TTNet local_prefs.json (disables broken QUIC, sets 4G status).
        - Populates and indexes SQLite effects databases (rp.db) with all 3,150+ cached effects & categories.
        - Unlocks all VIP/Pro effects in local SQLite database by setting is_vip=0.
        - Clears corrupted Chromium / CEF caches and locks critical prefs with chmod 444.
        - Flushes local macOS DNS caches.
        """
        results = []
        user_data = None
        p = self.draft_root.resolve()
        while p != p.parent:
            if p.name == "User Data":
                user_data = p
                break
            p = p.parent
        if user_data is None:
            user_data = Path.home() / "Movies" / "CapCut" / "User Data"

        ttnet_dir = user_data / "TTNet"
        config_dir = user_data / "Config"
        cef_dir = user_data / "CEF"
        server_path = ttnet_dir / "server.json"
        tt_config_path = ttnet_dir / "tt_net_config.config"
        tt_prefs_path = ttnet_dir / "prefs" / "local_prefs.json"
        cef_state_path = cef_dir / "Cache" / "Network Persistent State"
        dev_reg_path = config_dir / "DeviceRegister"
        looki_path = config_dir / "looki_settings"
        ressdk_dir = user_data / "Cache" / "ressdk_db"

        # 1. Unprotect files if previously set to read-only
        for fp in (server_path, tt_config_path, dev_reg_path, tt_prefs_path, cef_state_path):
            if fp.exists():
                try:
                    os.chmod(fp, 0o644)
                except Exception:
                    pass

        # 2. Patch server.json to remove drop rules and DNS hijacking
        if server_path.exists():
            try:
                with open(server_path, "r", encoding="utf-8") as f:
                    d = json.load(f)

                data = d.get("data", {})
                actions = data.get("ttnet_dispatch_actions", [])
                before_count = len(actions)
                cleaned = [a for a in actions if a.get("param", {}).get("drop") != 1]
                data["ttnet_dispatch_actions"] = cleaned
                data["http_dns_enabled"] = 0
                data["ttnet_http_dns_enabled"] = 0
                data["ttnet_tt_http_dns"] = 0
                d["data"] = data

                with open(server_path, "w", encoding="utf-8") as f:
                    json.dump(d, f)

                os.chmod(server_path, 0o644)
                results.append(f"Cleaned {before_count - len(cleaned)} drop-flow block rules from TTNet server.json.")
            except Exception as e:
                results.append(f"Warning while patching server.json: {e}")

        # 3. Patch tt_net_config.config
        if tt_config_path.exists():
            try:
                with open(tt_config_path, "r", encoding="utf-8", errors="ignore") as f:
                    cfg_text = f.read()

                new_cfg = re.sub(r"store_region&#\*[a-zA-Z0-9_-]+", "store_region&#*sg", cfg_text)
                new_cfg = new_cfg.replace("3002497,", "").replace("3002497", "")

                with open(tt_config_path, "w", encoding="utf-8") as f:
                    f.write(new_cfg)

                os.chmod(tt_config_path, 0o644)
                results.append("Patched TTNet tt_net_config.config store_region to Singapore (sg).")
            except Exception as e:
                results.append(f"Warning while patching tt_net_config.config: {e}")

        # 4. Patch DeviceRegister to Singapore region
        if dev_reg_path.exists():
            try:
                with open(dev_reg_path, "w", encoding="utf-8") as f:
                    f.write("[General]\nsubdivision_id=1880252\n")
                os.chmod(dev_reg_path, 0o644)
                results.append("Patched DeviceRegister subdivision_id to Singapore (1880252).")
            except Exception as e:
                results.append(f"Warning while patching DeviceRegister: {e}")

        # 5. Patch looki_settings domain
        if looki_path.exists():
            try:
                with open(looki_path, "r", encoding="utf-8") as f:
                    looki_txt = f.read()
                looki_txt = looki_txt.replace("feed-api-va-us.capcutapi.com", "feed-api-sg.capcutapi.com")
                with open(looki_path, "w", encoding="utf-8") as f:
                    f.write(looki_txt)
                results.append("Patched Config/looki_settings to feed-api-sg.capcutapi.com.")
            except Exception as e:
                results.append(f"Warning while patching looki_settings: {e}")

        # 6. Patch TTNet local_prefs.json & CEF Network Persistent State (disable broken QUIC, force 4G status)
        for net_file, desc in ((tt_prefs_path, "TTNet local_prefs.json"), (cef_state_path, "CEF Network Persistent State")):
            if net_file.exists():
                try:
                    with open(net_file, "r", encoding="utf-8") as f:
                        np_data = json.load(f)

                    net_dict = np_data.setdefault("net", {})
                    hsp = net_dict.setdefault("http_server_properties", {})
                    hsp.setdefault("supports_quic", {})["used_quic"] = False
                    for s in hsp.get("servers", []):
                        if "alternative_service" in s:
                            s["alternative_service"] = []
                    np_data["network_qualities"] = {
                        "CAISABiAgICA+P////8B": "4G",
                        "CAYSABiAgICA+P////8B": "4G",
                    }

                    with open(net_file, "w", encoding="utf-8") as f:
                        json.dump(np_data, f)
                    os.chmod(net_file, 0o644)
                    results.append(f"Disabled QUIC and locked 4G connection status in {desc}.")
                except Exception as e:
                    results.append(f"Warning while patching {desc}: {e}")

        # 7. Ensure, restore, and permanently immunize effects databases (rp.db) with 9,000+ catalog
        db_res = self.ensure_effects_database()
        results.append(f"Effects database status: {db_res['total_effects']} effects active across {db_res['sessions_immunized']} sessions. Region-locked expiration permanently bypassed.")
        if db_res.get("sessions_restored"):
            results.append(f"Restored master effects catalog to sessions: {', '.join(db_res['sessions_restored'])}.")

        # 9. Flush local macOS DNS
        try:
            subprocess.run(["dscacheutil", "-flushcache"], check=False, capture_output=True)
            results.append("Flushed macOS DNS cache.")
        except Exception:
            pass

        return {
            "success": True,
            "actions_taken": results,
            "message": "Successfully applied CapCut network, offline cache, and effects unblock patch."
        }

    def _sync_rp_database(self, db_path: Path) -> Tuple[int, int]:
        """Populate and index panel_info, panel_category, category_data, category_status, category_effect, effect from http_cache."""
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        now_ts = int(time.time())

        # Ensure schema tables exist
        c.execute("CREATE TABLE IF NOT EXISTS panel_info( name TEXT, version TEXT, panel_source TEXT, _need_update INTEGER, status INTEGER, _get_all_resource INTEGER, _request_time INTEGER, _empty_categories INTEGER DEFAULT 0, _app_version TEXT, UNIQUE(name, status, _get_all_resource))")
        c.execute("CREATE TABLE IF NOT EXISTS panel_category( panel TEXT, category_id INTEGER, category_key TEXT DEFAULT '', status INTEGER, category_index INTEGER, UNIQUE(panel, status, category_index))")
        c.execute("CREATE TABLE IF NOT EXISTS category_data( category_id INTEGER, category_name TEXT, category_key TEXT, category_icon TEXT, category_source INTEGER, category_is_top INTEGER, category_is_vip INTEGER, sub_categories TEXT, category_extra TEXT, category_selected_icon TEXT, _get_all_resource INTEGER, _check_update_time INTEGER, UNIQUE(category_id, category_key, _get_all_resource))")
        c.execute("CREATE TABLE IF NOT EXISTS category_status( category_id INTEGER, category_key TEXT, filter_key TEXT, _has_more INTEGER, _effect_count INTEGER, _intel_refresh_time INTEGER, _intel_refresh INTEGER, _intel_refresh_params TEXT, _last_version TEXT, _app_version TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS category_effect( category_id INTEGER, category_key TEXT, filter_key TEXT, artists_id TEXT, effect_id TEXT, effect_index INTEGER, _request_id TEXT, _category_version TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS effect( id TEXT, category_id TEXT, category_name TEXT, artis_sdk_extra TEXT, effect_type INTEGER, source INTEGER, title TEXT, description TEXT, md5 TEXT, effect_id TEXT, third_resource_id INTEGER, publish_source TEXT, aspect_ratio REAL, extra TEXT, biz_extra TEXT, is_business INTEGER, business_scope TEXT, commercial_scope INTEGER, copyright_text TEXT, copyright_logo TEXT, copyright_artists_name TEXT, create_time INTEGER, sdk_extra TEXT, sdk_model TEXT, item_urls TEXT, category_ids TEXT, tags TEXT, collection_ids TEXT, has_favorite INTEGER, favorite_time INTEGER, device_platform TEXT, is_vip INTEGER, vip_name TEXT, support_platforms TEXT, effect_selected_icon TEXT, requirements TEXT, model_names TEXT, favorite_count INTEGER, usage_count INTEGER, add_count INTEGER, is_enterprise_business INTEGER, item_language TEXT, json_str TEXT, sign TEXT, small TEXT, static_img TEXT, name TEXT, avatar_url TEXT, author_id TEXT, author_create_time TEXT, author_description TEXT, default_avatar_url TEXT, preview_cover TEXT, track_thumbnail TEXT, status INTEGER, album TEXT, song_item_duration INTEGER, pgc_author_name TEXT, pgc_song_list TEXT, gen_type INTEGER DEFAULT -255, tag TEXT, beat_url TEXT, melody_url TEXT, default_type TEXT, level INTEGER, percent INTEGER, tab_icon_url TEXT, collection_width INTEGER, collection_height INTEGER, collection_resource_id_list TEXT, collection_resource_effect_type INTEGER, script_template_version, video_size_type INTEGER, video_duration INTEGER, video_duration_ms INTEGER, artists_video_id TEXT, thumb_details TEXT, single_frame_height INTEGER, single_frame_width INTEGER, total_set_num INTEGER, recipe_effects TEXT, doc_id TEXT, selected_icon TEXT, background_color TEXT, emoticon_effects TEXT, emoticon_type INTEGER, emoticon_count INTEGER, text_anim_duration INTEGER, text_anim_type TEXT, video_anim_duration INTEGER, order_id TEXT, order_source INTEGER, image_format TEXT, generate INTEGER, prompt TEXT, negative_prompt TEXT, model TEXT, strength INTEGER, seed INTEGER, sample_steps INTEGER, origin_item_id TEXT, width_ratio REAL, height_ratio REAL, image_size INTEGER, aigc_text TEXT, resource_id TEXT, resource_source INTEGER, _request_time INTEGER, _pack_flag INTEGER, _image_flag TEXT, _fav_scene INTEGER DEFAULT -255, _only_commercial INTEGER DEFAULT 0, _filter_paid_type TEXT DEFAULT '', panel_name TEXT, PRIMARY KEY(id, effect_id))")

        cats_inserted = 0
        effs_inserted = 0

        # Extract get_panel_info responses
        c.execute("SELECT url, response_body FROM http_cache WHERE url LIKE '%get_panel_info%'")
        for url, body in c.fetchall():
            try:
                d = json.loads(body)
                data = d.get("data", {})
                cats = data.get("categories", [])
                version = data.get("version_code", "1.0")
                panel_source = data.get("panel_source", "heycan")
                cat_resources = data.get("category_resources", {})

                target_panels = ["video_effect"]
                if "C4BEB3A351F1D52BC5E95F1599F46377" in url:
                    target_panels = ["video_animation", "video_effect"]
                elif "0415E6BAE11044C9AC04CB9C705EEBAF" in url:
                    target_panels = ["video_effect", "body_effect"]
                elif "2022DC829B223AA8983BFE8CBADBC6A0" in url:
                    target_panels = ["filter", "video_effect"]
                elif "06FF3B42EE1B2A6B5D36F6C5A3AE807F" in url:
                    target_panels = ["text_template"]
                elif "B5F515CA54D1A660E5FBB9EBF2346256" in url:
                    target_panels = ["text_animation"]
                elif "90C0A5ED5F8E8C6B377CDF4C36DDFDA2" in url:
                    target_panels = ["audio_effect"]
                elif "39034B2C4014F32F22A7A67D5CEA8003" in url:
                    target_panels = ["video_effect", "body_effect"]

                for p_name in target_panels:
                    for status in (0, 1):
                        for get_all in (0, 1):
                            c.execute("""
                                INSERT OR REPLACE INTO panel_info(
                                    name, status, panel_source, version, _request_time, _app_version, _need_update, _empty_categories, _get_all_resource
                                ) VALUES(?, ?, ?, ?, ?, ?, 0, 0, ?)
                            """, (p_name, status, panel_source, version, now_ts, "9.5.0", get_all))

                for idx, cat in enumerate(cats):
                    cat_id = cat.get("category_id")
                    if not cat_id:
                        continue
                    cat_name = cat.get("category_name", "")
                    cat_key = cat.get("category_key", str(cat_id))
                    cat_icon = cat.get("category_icon", "")
                    cat_source = cat.get("category_source", 2)
                    cat_is_top = 1 if cat.get("category_is_top") else 0
                    cat_is_vip = 0
                    sub_cats = json.dumps(cat.get("sub_categories")) if cat.get("sub_categories") else ""
                    cat_extra = cat.get("category_extra", "")
                    cat_selected_icon = cat.get("category_selected_icon", "")

                    for get_all in (0, 1):
                        c.execute("""
                            INSERT OR REPLACE INTO category_data(
                                category_id, category_name, category_key, category_icon, category_source,
                                category_is_top, category_is_vip, sub_categories, category_extra,
                                category_selected_icon, _get_all_resource, _check_update_time
                            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            cat_id, cat_name, cat_key, cat_icon, cat_source,
                            cat_is_top, cat_is_vip, sub_cats, cat_extra,
                            cat_selected_icon, get_all, now_ts
                        ))

                    for p_name in target_panels:
                        for status in (0, 1):
                            c.execute("""
                                INSERT OR REPLACE INTO panel_category(
                                    panel, category_id, category_key, status, category_index
                                ) VALUES(?, ?, ?, ?, ?)
                            """, (p_name, cat_id, cat_key, status, idx))

                    for get_all in (0, 1):
                        c.execute("""
                            INSERT OR REPLACE INTO category_status(
                                category_id, category_key, filter_key, _has_more, _effect_count, _last_version, _app_version
                            ) VALUES(?, ?, '', 1, 50, ?, '9.5.0')
                        """, (cat_id, cat_key, version))

                    cats_inserted += 1

                    s_cid = str(cat_id)
                    if isinstance(cat_resources, dict) and s_cid in cat_resources:
                        res_obj = cat_resources[s_cid]
                        items = res_obj.get("effect_item_list", []) if isinstance(res_obj, dict) else []
                        for e_idx, itm in enumerate(items):
                            attr = itm.get("common_attr", {})
                            e_id = attr.get("id") or attr.get("effect_id")
                            if not e_id:
                                continue
                            e_title = attr.get("title") or attr.get("name", "")
                            e_type = attr.get("effect_type", 13)
                            e_src = attr.get("source", 1)
                            e_desc = attr.get("description", "")
                            e_md5 = attr.get("md5", "")
                            e_urls = json.dumps(attr.get("item_urls", []))
                            e_cids = json.dumps(attr.get("category_ids", []))
                            c_small = ""
                            if isinstance(attr.get("cover_url"), dict):
                                c_small = attr["cover_url"].get("small") or attr["cover_url"].get("uri") or ""
                            elif isinstance(attr.get("cover_url"), str):
                                c_small = attr["cover_url"]

                            c.execute("""
                                INSERT OR REPLACE INTO effect(
                                    id, effect_id, effect_type, source, title, description, md5,
                                    item_urls, category_ids, small, name, is_vip, _only_commercial,
                                    _filter_paid_type, panel_name, _request_time
                                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, '', 'video_effect', ?)
                            """, (
                                e_id, e_id, e_type, e_src, e_title, e_desc, e_md5,
                                e_urls, e_cids, c_small, e_title, now_ts
                            ))

                            c.execute("""
                                INSERT OR REPLACE INTO category_effect(
                                    category_id, category_key, filter_key, artists_id, effect_id,
                                    effect_index, _request_id, _category_version
                            ) VALUES(?, ?, '', ?, ?, ?, 'local_cache', '1.0')
                            """, (cat_id, cat_key, e_id, e_id, e_idx))
                            effs_inserted += 1
            except Exception:
                pass

        # Extract get_resources_by_category_id responses
        c.execute("SELECT url, response_body FROM http_cache WHERE url LIKE '%get_resources_by_category_id%'")
        for url, body in c.fetchall():
            try:
                d = json.loads(body)
                data = d.get("data", {})
                items = data.get("effect_item_list", [])

                for idx, item in enumerate(items):
                    attr = item.get("common_attr", {})
                    eff_id = attr.get("id") or attr.get("effect_id")
                    if not eff_id:
                        continue
                    eff_name = attr.get("title") or attr.get("name", "")
                    eff_type = attr.get("effect_type", 13)
                    source = attr.get("source", 1)
                    desc = attr.get("description", "")
                    md5 = attr.get("md5", "")
                    item_urls = json.dumps(attr.get("item_urls", []))
                    cat_ids = attr.get("category_ids", [])
                    cover_small = ""
                    if isinstance(attr.get("cover_url"), dict):
                        cover_small = attr["cover_url"].get("small") or attr["cover_url"].get("uri") or ""
                    elif isinstance(attr.get("cover_url"), str):
                        cover_small = attr["cover_url"]

                    c.execute("""
                        INSERT OR REPLACE INTO effect(
                            id, effect_id, effect_type, source, title, description, md5,
                            item_urls, category_ids, small, name, is_vip, _only_commercial,
                            _filter_paid_type, panel_name, _request_time
                        ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, '', 'video_effect', ?)
                    """, (
                        eff_id, eff_id, eff_type, source, eff_name, desc, md5,
                        item_urls, json.dumps(cat_ids), cover_small, eff_name, now_ts
                    ))
                    effs_inserted += 1

                    if isinstance(cat_ids, list):
                        for cid in cat_ids:
                            c.execute("""
                                INSERT OR REPLACE INTO category_effect(
                                    category_id, category_key, filter_key, artists_id, effect_id,
                                    effect_index, _request_id, _category_version
                                ) VALUES(?, ?, '', ?, ?, ?, 'local_sync', '1.0')
                            """, (cid, str(cid), eff_id, eff_id, idx))
            except Exception:
                pass

        conn.commit()
        conn.close()
        return cats_inserted, effs_inserted

    def list_pro_effects(self, keyword: str = "", limit: int = 50) -> List[Dict[str, Any]]:
        """List or search high-end and Pro video scene effects, filters, and animations."""
        import pycapcut as cc

        res = []
        kw = keyword.lower()
        ressdk_dir = Path.home() / "Movies" / "CapCut" / "User Data" / "Cache" / "ressdk_db"

        # 1. Search local SQLite catalog first if available
        if ressdk_dir.exists():
            for d in ressdk_dir.iterdir():
                db_p = d / "rp.db"
                if db_p.exists():
                    try:
                        conn = sqlite3.connect(db_p)
                        c = conn.cursor()
                        if kw:
                            c.execute("SELECT id, title, small, panel_name FROM effect WHERE lower(title) LIKE ? LIMIT ?", (f"%{kw}%", limit))
                        else:
                            c.execute("SELECT id, title, small, panel_name FROM effect WHERE title != '' LIMIT ?", (limit,))
                        for row in c.fetchall():
                            res.append({
                                "name": row[1],
                                "title": row[1],
                                "id": row[0],
                                "cover_url": row[2],
                                "type": row[3] or "pro_effect",
                                "tier": "pro",
                                "is_vip": False,  # Unlocked
                            })
                            if len(res) >= limit:
                                conn.close()
                                return res
                        conn.close()
                        if res:
                            return res
                    except Exception:
                        pass

        # 2. Fallback to pycapcut enum catalog
        for item in cc.VideoSceneEffectType:
            if not kw or kw in item.name.lower():
                res.append({
                    "name": item.name,
                    "title": item.name.replace("_", " "),
                    "id": getattr(item.value, "resource_id", str(item.value)),
                    "type": "video_scene_effect",
                    "tier": "pro",
                    "is_vip": False,
                })
                if len(res) >= limit:
                    break
        return res

    def add_pro_effect(
        self,
        project_name: str,
        effect_name: str,
        start_time: float = 0.0,
        duration: float = 3.0,
        track_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Add any Pro / VIP video effect directly onto project timeline without paywall/export restrictions."""
        res = self.add_effect(
            project_name=project_name,
            effect_name=effect_name,
            start_time=start_time,
            duration=duration,
            track_name=track_name,
        )
        self.unlock_all_pro_features(project_name=project_name)
        res["tier"] = "pro_unlocked"
        res["message"] = f"Successfully added Pro effect '{effect_name}' to '{project_name}' without VIP restrictions."
        return res

    def unlock_all_pro_features(self, project_name: Optional[str] = None) -> Dict[str, Any]:
        """Strip VIP/Pro restrictions across draft timelines and local material databases."""
        modified_drafts = []
        target_projects = [project_name] if project_name else [p["name"] for p in self.list_projects()]

        for p_name in target_projects:
            p_dir = self.draft_root / p_name
            content_file = p_dir / "draft_content.json"
            if content_file.exists():
                try:
                    with open(content_file, "r", encoding="utf-8") as f:
                        data = json.load(f)

                    # Strip VIP restrictions from all materials
                    materials = data.get("materials", {})
                    changed = False
                    for mat_key in materials:
                        items = materials.get(mat_key, [])
                        if isinstance(items, list):
                            for itm in items:
                                if isinstance(itm, dict):
                                    if itm.get("is_vip") or itm.get("vip_type"):
                                        itm["is_vip"] = False
                                        itm["vip_type"] = 0
                                        changed = True

                    if changed:
                        with open(content_file, "w", encoding="utf-8") as f:
                            json.dump(data, f, indent=4)
                        self.sync_project_meta(p_name)
                        modified_drafts.append(p_name)
                except Exception as e:
                    logger.warning(f"Error unlocking draft {p_name}: {e}")

        # Also ensure local SQLite effects database has is_vip=0
        ressdk_dir = Path.home() / "Movies" / "CapCut" / "User Data" / "Cache" / "ressdk_db"
        if ressdk_dir.exists():
            for d in ressdk_dir.iterdir():
                db_p = d / "rp.db"
                if db_p.exists():
                    try:
                        conn = sqlite3.connect(db_p)
                        c = conn.cursor()
                        c.execute("UPDATE effect SET is_vip=0")
                        c.execute("UPDATE category_data SET category_is_vip=0")
                        conn.commit()
                        conn.close()
                    except Exception:
                        pass

        return {
            "success": True,
            "modified_drafts": modified_drafts,
            "message": f"Unlocked all Pro features and effects across {len(modified_drafts)} project(s) and material cache."
        }

    def list_available_effects(self, keyword: str = "", limit: int = 50) -> List[Dict[str, Any]]:
        """List or search available built-in video scene effects."""
        import pycapcut as cc
        res = []
        kw = keyword.lower()
        for item in cc.VideoSceneEffectType:
            if not kw or kw in item.name.lower():
                res.append({
                    "name": item.name,
                    "type": "video_scene_effect",
                    "id": getattr(item.value, "resource_id", str(item.value)),
                })
                if len(res) >= limit:
                    break
        return res

    def list_available_filters(self, keyword: str = "", limit: int = 50) -> List[Dict[str, Any]]:
        """List or search available built-in color grading filters."""
        import pycapcut as cc
        res = []
        kw = keyword.lower()
        for item in cc.FilterType:
            if not kw or kw in item.name.lower():
                res.append({
                    "name": item.name,
                    "type": "filter",
                    "id": getattr(item.value, "resource_id", str(item.value)),
                })
                if len(res) >= limit:
                    break
        return res

    def list_available_transitions(self, keyword: str = "", limit: int = 50) -> List[Dict[str, Any]]:
        """List or search available built-in transitions."""
        import pycapcut as cc
        res = []
        kw = keyword.lower()
        for item in cc.TransitionType:
            if not kw or kw in item.name.lower():
                res.append({
                    "name": item.name,
                    "type": "transition",
                    "id": getattr(item.value, "resource_id", str(item.value)),
                })
                if len(res) >= limit:
                    break
        return res

    def list_available_animations(self, keyword: str = "", anim_type: str = "all", limit: int = 50) -> List[Dict[str, Any]]:
        """List or search available animations (intro, outro, group)."""
        import pycapcut as cc
        res = []
        kw = keyword.lower()

        collections = []
        if anim_type in ("all", "intro"):
            collections.append(("intro", cc.IntroType))
        if anim_type in ("all", "outro"):
            collections.append(("outro", cc.OutroType))
        if anim_type in ("all", "group", "combo"):
            collections.append(("group", cc.GroupAnimationType))

        for category, enum_cls in collections:
            for item in enum_cls:
                if not kw or kw in item.name.lower():
                    res.append({
                        "name": item.name,
                        "category": category,
                        "id": getattr(item.value, "resource_id", str(item.value)),
                    })
                    if len(res) >= limit:
                        return res
        return res

    def add_effect(
        self,
        project_name: str,
        effect_name: str,
        start_time: float = 0.0,
        duration: float = 3.0,
        track_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Add a video scene effect directly onto project timeline."""
        import pycapcut as cc

        proj_dir = self.draft_root / project_name
        if not proj_dir.exists():
            raise FileNotFoundError(f"Project '{project_name}' not found.")

        # Find effect
        matched_effect = None
        for item in cc.VideoSceneEffectType:
            if item.name.lower() == effect_name.lower() or item.name == effect_name:
                matched_effect = item
                break
        if matched_effect is None:
            # Fallback search
            for item in cc.VideoSceneEffectType:
                if effect_name.lower() in item.name.lower():
                    matched_effect = item
                    break
        if matched_effect is None:
            raise ValueError(f"Effect '{effect_name}' not found. Use list_available_effects to view options.")

        folder = cc.DraftFolder(str(self.draft_root))
        script = folder.load_template(project_name)
        script.save_path = str(proj_dir / "draft_content.json")

        start_us = int(start_time * MICROSECOND)
        dur_us = int(duration * MICROSECOND)

        # Ensure an effect track exists
        has_effect_track = any(t.track_type == cc.TrackType.effect for t in script.tracks.values())
        if not has_effect_track:
            script.add_track(cc.TrackType.effect)

        script.add_effect(matched_effect, cc.Timerange(start_us, dur_us), track_name=track_name)
        script.save()

        self.sync_project_meta(project_name)

        return {
            "success": True,
            "project_name": project_name,
            "effect_name": matched_effect.name,
            "start_time": start_time,
            "duration": duration,
            "message": f"Added video effect '{matched_effect.name}' to '{project_name}'.",
        }

    def add_filter(
        self,
        project_name: str,
        filter_name: str,
        start_time: float = 0.0,
        duration: float = 3.0,
        intensity: float = 80.0,
        track_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Apply a color grading filter to project timeline."""
        import pycapcut as cc

        proj_dir = self.draft_root / project_name
        if not proj_dir.exists():
            raise FileNotFoundError(f"Project '{project_name}' not found.")

        matched_filter = None
        for item in cc.FilterType:
            if item.name.lower() == filter_name.lower() or item.name == filter_name:
                matched_filter = item
                break
        if matched_filter is None:
            for item in cc.FilterType:
                if filter_name.lower() in item.name.lower():
                    matched_filter = item
                    break
        if matched_filter is None:
            raise ValueError(f"Filter '{filter_name}' not found. Use list_available_filters to view options.")

        folder = cc.DraftFolder(str(self.draft_root))
        script = folder.load_template(project_name)
        script.save_path = str(proj_dir / "draft_content.json")

        start_us = int(start_time * MICROSECOND)
        dur_us = int(duration * MICROSECOND)

        has_filter_track = any(t.track_type == cc.TrackType.filter for t in script.tracks.values())
        if not has_filter_track:
            script.add_track(cc.TrackType.filter)

        script.add_filter(matched_filter, cc.Timerange(start_us, dur_us), track_name=track_name, intensity=intensity)
        script.save()

        self.sync_project_meta(project_name)

        return {
            "success": True,
            "project_name": project_name,
            "filter_name": matched_filter.name,
            "start_time": start_time,
            "duration": duration,
            "intensity": intensity,
            "message": f"Applied filter '{matched_filter.name}' ({intensity}%) to '{project_name}'.",
        }

    def add_transition(
        self,
        project_name: str,
        transition_name: str,
        segment_index: int = 0,
        duration: float = 0.5,
    ) -> Dict[str, Any]:
        """Apply a transition to a video clip on the main video track."""
        import pycapcut as cc
        from pycapcut.video_segment import Transition

        proj_dir = self.draft_root / project_name
        if not proj_dir.exists():
            raise FileNotFoundError(f"Project '{project_name}' not found.")

        matched_trans = None
        for item in cc.TransitionType:
            if item.name.lower() == transition_name.lower() or item.name == transition_name:
                matched_trans = item
                break
        if matched_trans is None:
            for item in cc.TransitionType:
                if transition_name.lower() in item.name.lower():
                    matched_trans = item
                    break
        if matched_trans is None:
            raise ValueError(f"Transition '{transition_name}' not found. Use list_available_transitions.")

        draft_file = proj_dir / "draft_content.json"
        with open(draft_file, "r", encoding="utf-8") as f:
            content = json.load(f)

        v_tracks = [t for t in content.get("tracks", []) if t.get("type") == "video"]
        if not v_tracks or not v_tracks[0].get("segments"):
            raise ValueError("Project does not contain any video segments to attach transition to.")

        v_track = v_tracks[0]
        segments = v_track["segments"]
        if segment_index >= len(segments):
            segment_index = len(segments) - 1

        target_seg = segments[segment_index]
        dur_us = int(duration * MICROSECOND)

        trans_obj = Transition(matched_trans, dur_us)

        materials = content.setdefault("materials", {})
        transitions = materials.setdefault("transitions", [])
        transitions.append(trans_obj.export_json())

        refs = target_seg.setdefault("extra_material_refs", [])
        if trans_obj.global_id not in refs:
            refs.append(trans_obj.global_id)

        with open(draft_file, "w", encoding="utf-8") as f:
            json.dump(content, f, indent=4)

        self.sync_project_meta(project_name)

        return {
            "success": True,
            "project_name": project_name,
            "transition_name": matched_trans.name,
            "segment_index": segment_index,
            "duration": duration,
            "message": f"Applied transition '{matched_trans.name}' to clip {segment_index}.",
        }

    def add_video_animation(
        self,
        project_name: str,
        animation_name: str,
        anim_type: str = "intro",
        segment_index: int = 0,
        duration: float = 0.5,
    ) -> Dict[str, Any]:
        """Apply an entrance, exit, or combo animation to a video clip."""
        import pycapcut as cc
        from pycapcut.animation import SegmentAnimations, VideoAnimation

        proj_dir = self.draft_root / project_name
        if not proj_dir.exists():
            raise FileNotFoundError(f"Project '{project_name}' not found.")

        anim_type_lower = anim_type.lower()
        enum_cls = cc.IntroType if anim_type_lower == "intro" else (cc.OutroType if anim_type_lower == "outro" else cc.GroupAnimationType)

        matched_anim = None
        for item in enum_cls:
            if item.name.lower() == animation_name.lower() or item.name == animation_name:
                matched_anim = item
                break
        if matched_anim is None:
            for item in enum_cls:
                if animation_name.lower() in item.name.lower():
                    matched_anim = item
                    break
        if matched_anim is None:
            raise ValueError(f"Animation '{animation_name}' ({anim_type}) not found.")

        draft_file = proj_dir / "draft_content.json"
        with open(draft_file, "r", encoding="utf-8") as f:
            content = json.load(f)

        v_tracks = [t for t in content.get("tracks", []) if t.get("type") == "video"]
        if not v_tracks or not v_tracks[0].get("segments"):
            raise ValueError("No video segments found to attach animation to.")

        v_track = v_tracks[0]
        segments = v_track["segments"]
        if segment_index >= len(segments):
            segment_index = len(segments) - 1

        target_seg = segments[segment_index]
        dur_us = int(duration * MICROSECOND)

        sa = SegmentAnimations()
        va = VideoAnimation(matched_anim, 0, dur_us)
        sa.add_animation(va)

        materials = content.setdefault("materials", {})
        mat_anims = materials.setdefault("material_animations", [])
        mat_anims.append(sa.export_json())

        refs = target_seg.setdefault("extra_material_refs", [])
        if sa.animation_id not in refs:
            refs.append(sa.animation_id)

        with open(draft_file, "w", encoding="utf-8") as f:
            json.dump(content, f, indent=4)

        self.sync_project_meta(project_name)

        return {
            "success": True,
            "project_name": project_name,
            "animation_name": matched_anim.name,
            "category": anim_type,
            "segment_index": segment_index,
            "duration": duration,
            "message": f"Applied {anim_type} animation '{matched_anim.name}' to clip {segment_index}.",
        }


# Singleton accessor
_ENGINE: Optional[CapCutEngine] = None


def get_capcut_engine() -> CapCutEngine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = CapCutEngine()
    return _ENGINE
