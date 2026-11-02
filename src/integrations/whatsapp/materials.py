"""
Julius WhatsApp Integration — Materials & Academic Documents Registry.
Provides document discovery, resolution, and metadata for sending PDFs,
plus complete first semester timetables for all friends and branches.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .media_manager import get_media_manager

logger = logging.getLogger(__name__)

# Root materials folder (checks workspace materials and user-configured paths)
_POSSIBLE_DIRS = [
    Path(__file__).resolve().parents[3] / "materials",
    Path(__file__).resolve().parents[3] / "user_data",
    Path.home() / ".julius" / "materials",
    Path.home() / ".Julius" / "materials",
]

# Primary data folder for user-managed PDFs, images, and files
_DATA_FOLDER_NAMES = [
    "materials",
    "user_data",
    "JuliusData",
]


def get_data_folder() -> Path:
    """Get the materials folder (primary) or configured user data folder."""
    project_root = Path(__file__).resolve().parents[3]
    for name in _DATA_FOLDER_NAMES:
        d = project_root / name
        if d.is_dir():
            return d
    # Default to materials folder
    d = project_root / "materials"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_materials_dir() -> Path:
    for d in _POSSIBLE_DIRS:
        if d.is_dir():
            return d
    # Default fallback
    d = Path(__file__).resolve().parents[3] / "materials"
    d.mkdir(parents=True, exist_ok=True)
    return d


MATERIALS_CATALOG: List[Dict[str, Any]] = [
    {
        "id": "ca_exam_timetable",
        "filename": "Schedule for First Assessment Test -16.09.2026.pdf",
        "title": "First Assessment Test Schedule (CA-1 / CAT-1)",
        "description": "Sample Academic Schedule for First Assessment Test (CA-1 / CAT-1).",
        "keywords": [
            "first assessment test",
            "assessment test",
            "ca 1 test",
            "ca1 test",
            "cat 1 test",
            "cat1 test",
            "ca 1 timetable",
            "ca1 timetable",
            "cat 1 timetable",
            "cat1 timetable",
            "ca timetable",
            "cat timetable",
            "exam timetable",
            "test timetable",
            "assessment timetable",
            "assessment schedule",
            "ca test timetable",
            "cat exam",
            "ca exam",
            "assessment",
        ],
    },
    {
        "id": "timetable",
        "filename": "First_Semester_Timetable_2026.pdf",
        "title": "First Semester Timetable (General)",
        "description": "Semester 1 Timetable template for branches including Engineering, Product, and Design.",
        "keywords": [
            "timetable pdf",
            "time table pdf",
            "timetable",
            "time table",
            "schedule pdf",
            "college timetable",
            "class timetable",
            "regular timetable",
        ],
    },
    {
        "id": "it_timetable",
        "filename": "Timetable_IT_Batch2.pdf",
        "title": "Team Timetable (Room 004)",
        "description": "Information Technology Batch 2 Schedule template, Room 004.",
        "keywords": [
            "it timetable",
            "it schedule",
            "batch 2 timetable",
            "it 2 timetable",
            "our timetable",
            "batch 2 pdf",
            "it timetable pdf",
        ],
    },
    {
        "id": "physics_notes",
        "filename": "Engineering_Physics_PH23C11_Notes.pdf",
        "title": "Engineering Physics (PH23C11) Notes",
        "description": "Unit 1 Oscillations, Optics, Laser Physics & Lab Experiments reference notes.",
        "keywords": [
            "physics material",
            "physics materials",
            "physics notes",
            "physics pdf",
            "physics study material",
            "ph23c11",
            "physics note",
            "physics",
        ],
    },
]


BRANCH_TIMETABLES: Dict[str, Dict[str, Any]] = {
    "automobile": {
        "title": "Automobile Engineering (M-AU, Room 205)",
        "friend": "Contact Alex",
        "aliases": ["automobile", "alex", "alex timetable", "m-au", "auto", "room 205", "gova", "gova timetable"],
        "schedule": (
            "🚗 Automobile Engineering (Room 205) — Contact Alex's Timetable:\n"
            "• Mon: Engineering Drawing (8:30-10:15) | Physics (10:30-12:10) | Calculus (1:10-2:55) | Library\n"
            "• Tue: Physics Lab (8:30-10:15) | English (10:30-12:10) | Python Lab (1:10-2:55) | Library\n"
            "• Wed: Basics of EEE (8:30-10:15) | Calculus (10:30-12:10) | English Lab (1:10-2:55) | Activity (3:00-4:45)\n"
            "• Thu: Seminar (8:30-9:20) | Python (9:25-10:15) | Heritage Studies (10:30-11:20) | Engineering Drawing Lab (1:10-4:45)\n"
            "• Fri: Physics (8:30-9:20) | Seminar (9:25-10:15) | Python (10:30-12:10) | EEE Lab (1:10-2:55) | Library"
        ),
    },
    "it1": {
        "title": "IT Batch 1 (M-IT B1, Room 001)",
        "friend": "Contact Kevin",
        "aliases": ["it 1", "it batch 1", "kevin", "kevin timetable", "room 001", "sumanth", "sumanth timetable"],
        "schedule": (
            "💻 IT Batch 1 (Room 001) — Contact Kevin's Timetable:\n"
            "• Mon: Makerspace Lab (8:30-12:10) | Engineering Drawing (1:10-2:00) | English Lab (2:05-3:50)\n"
            "• Tue: Library | Physics (10:30-11:20) | FEEE (11:20-12:10) | Heritage Studies (1:10-2:00) | Library\n"
            "• Wed: English (8:30-9:20) | Physics Lab (9:25-11:20) | Makerspace Theory (2:05-2:55) | Activity (3:00-4:45)\n"
            "• Thu: Calculus (9:25-11:20) | Seminar (11:20-1:05) | Library\n"
            "• Fri: FEEE (8:30-9:20) | Calculus (9:25-11:20) | Engineering Drawing Lab (1:10-4:45)"
        ),
    },
    "it2": {
        "title": "IT Batch 2 (M-IT B2, Room 004)",
        "friend": "Team 2 (Room 004)",
        "aliases": ["it 2", "it batch 2", "charlie", "ian", "jack", "my timetable", "our timetable", "team", "room 004", "sundar", "reddy", "vishal"],
        "schedule": (
            "💻 IT Batch 2 (Room 004) — Team Schedule:\n"
            "• Mon: Foundation English (8:30-9:20) | Physics Lab (9:20-12:15) | Calculus (1:30-2:20) | FEEE (2:20-3:10)\n"
            "• Tue: Makerspace Lab (8:30-11:25) | EG Drawing (11:25-12:15) | Physics (1:30-2:20)\n"
            "• Wed: Physics (8:30-9:20) | Makerspace Theory (9:20-10:10) | English Lab (10:30-12:15) | Library/Seminar\n"
            "• Thu: Engineering Graphics Lab (8:30-12:15) | Activity (1:30-3:10)\n"
            "• Fri: Calculus (8:30-9:20) | FEEE (9:20-10:10) | Heritage Studies (10:30-11:25)"
        ),
    },
    "ece": {
        "title": "ECE Batch 1 (M-ECE B1, Room 101)",
        "friend": "Contact Frank & Contact Dave",
        "aliases": ["ece", "frank", "dave", "room 101", "chandru", "naveen", "naveen raj"],
        "schedule": (
            "📡 ECE Batch 1 (Room 101) — Contact Frank & Contact Dave's Timetable:\n"
            "• Mon: Calculus (8:30-10:15) | Heritage Studies (10:30-11:20) | Drawing (1:10-2:00) | Activity (2:05-3:50)\n"
            "• Tue: Physics (10:30-12:10) | Calculus (1:10-2:55) | C Programming (3:00-4:45)\n"
            "• Wed: Engineering Drawing Lab (8:30-12:10) | C Programming Lab (1:10-4:45)\n"
            "• Thu: Makerspace Lab (8:30-12:10) | Physics Lab (1:10-2:55) | English Lab (3:00-4:45)\n"
            "• Fri: English (8:30-10:15) | Physics (10:30-11:20) | Makerspace (11:20-12:10) | Seminar/Library"
        ),
    },
    "cse": {
        "title": "CSE Batch 1 (M-CSE B1, Room 201)",
        "friend": "Contact Grace",
        "aliases": ["cse", "grace", "grace timetable", "room 201"],
        "schedule": (
            "🖥️ CSE Batch 1 (Room 201) — Contact Grace's Timetable:\n"
            "• Mon: Physics (8:30-10:15) | Calculus (10:30-12:10) | Heritage Studies (1:10-2:00) | Computational Thinking Lab (2:05-4:45)\n"
            "• Tue: Physics Lab (10:30-12:10) | English Lab (1:10-2:55) | Library\n"
            "• Wed: Calculus (8:30-10:15) | FEEE (10:30-11:20) | Physics (11:20-12:10) | Seminar/Library\n"
            "• Thu: C Programming Lab (8:30-12:10) | FEEE (1:10-2:00) | Library\n"
            "• Fri: C Programming (8:30-10:15) | English (1:10-2:00) | Activity (2:05-4:45)"
        ),
    },
    "rpt": {
        "title": "Rubber and Plastics Technology (M-RPT, 1st Year)",
        "friend": "Contact Max",
        "aliases": ["rpt", "rubber and plastics", "max", "max timetable", "rpt timetable", "rubber technology"],
        "schedule": (
            "🧪 Rubber and Plastics Technology (RPT) — Contact Max's Timetable:\n"
            "• Mon: Engineering Physics (8:30-10:15) | Calculus (10:30-12:10) | Engineering Graphics (1:10-2:55)\n"
            "• Tue: Chemistry (8:30-10:15) | Chemistry Lab (10:30-1:05) | Python Programming (1:50-3:30)\n"
            "• Wed: Basics of Mechanical & Electrical (8:30-10:15) | Heritage Studies (10:30-11:20) | Workshop Lab (1:10-4:45)\n"
            "• Thu: Calculus (8:30-10:15) | Physics Lab (10:30-1:05) | English (1:50-3:30)\n"
            "• Fri: Python Programming Lab (8:30-12:10) | Activity (1:30-3:10) | Seminar/Library"
        ),
    },
}


def get_all_timetables_summary() -> str:
    """Return a complete text summary of all team schedules."""
    parts = ["📅 **Team & Department Schedules**:"]
    for k, v in BRANCH_TIMETABLES.items():
        parts.append(v["schedule"])
    return "\n\n".join(parts)


def find_timetable_for_query(query: str) -> Optional[str]:
    """
    Check if query asks for a specific or all timetables and return formatted schedule.
    """
    if not query:
        return None
    q = query.lower().strip()

    # Query asking to see all guys' timetables
    if any(k in q for k in [
        "all timetable", "all timetables", "all guys timetable", "every guy timetable",
        "list timetable", "timetable list", "all classes", "everyone's timetable",
    ]):
        return get_all_timetables_summary()

    # Query asking for a specific branch or friend
    for k, v in BRANCH_TIMETABLES.items():
        for alias in v["aliases"]:
            if re.search(rf"\b{re.escape(alias)}\b", q):
                if any(w in q for w in ["timetable", "time table", "schedule", "class", "classes", "routine", "period", "today", "tomorrow"]):
                    return v["schedule"]

    return None


def find_matching_document(query: str) -> Optional[Dict[str, Any]]:
    """
    Match an incoming query against registered academic materials.
    Returns metadata dict with absolute file path if found and file exists.
    Also searches materials folder for any matching file.
    """
    if not query:
        return None
    q = query.lower().strip()

    materials_dir = get_materials_dir()
    data_dir = get_data_folder()
    search_dirs = [data_dir, materials_dir] if data_dir != materials_dir else [materials_dir]

    # Disambiguation: Exam / CA Assessment Timetable vs Regular Class Timetable
    is_exam_query = any(k in q for k in [
        "ca 1", "ca1", "cat 1", "cat1", "ca test", "cat test", "assessment",
        "exam timetable", "test timetable", "ca timetable", "cat timetable", "assessment test", "ca schedule"
    ])

    # 1. If asking for assignment, tutorial, or specific shared file, prioritize received media
    try:
        media_match = get_media_manager().search_media(q)
        if media_match:
            is_match_exam = (
                "assessment" in media_match.get("filename", "").lower()
                or "ca" in media_match.get("filename", "").lower()
                or media_match.get("category") == "exam_timetable"
            )
            # If user asked for an exam timetable, NEVER return a regular class timetable
            if is_exam_query and not is_match_exam:
                media_match = None

            if media_match and (
                any(w in q for w in ["assignment", "assign", "tutorial", "tut", "max", "shared", "sent"])
                or (is_exam_query and is_match_exam)
                or media_match.get("category") in q
                or media_match.get("filename", "").lower() in q
            ):
                return media_match
    except Exception as e:
        logger.debug("[MATERIALS] Error searching media manager: %s", e)

    # 2. Exact keyword or substring matching against catalog
    for doc in MATERIALS_CATALOG:
        # STRICT ISOLATION: Never send class routine if user asks for exam/assessment
        if is_exam_query and doc["id"] in ("timetable", "it_timetable"):
            continue
        if not is_exam_query and doc["id"] == "ca_exam_timetable" and "assessment" not in q and "exam" not in q:
            continue

        for kw in doc["keywords"]:
            if re.search(rf"\b{re.escape(kw)}\b", q) or kw in q:
                for sdir in search_dirs:
                    target_file = sdir / doc["filename"]
                    if target_file.exists():
                        res = dict(doc)
                        res["path"] = str(target_file)
                        return res
                    # Also check subdirectories (received_media/documents)
                    sub_file = sdir / "received_media" / "documents" / doc["filename"]
                    if sub_file.exists():
                        res = dict(doc)
                        res["path"] = str(sub_file)
                        return res
                # Also check root directory fallback
                root_file = materials_dir.parent / doc["filename"]
                if root_file.exists():
                    res = dict(doc)
                    res["path"] = str(root_file)
                    return res

    # 3. Check dynamically indexed received media (general search)
    try:
        media_match = get_media_manager().search_media(q)
        if media_match:
            is_match_exam = (
                "assessment" in media_match.get("filename", "").lower()
                or "ca" in media_match.get("filename", "").lower()
                or media_match.get("category") == "exam_timetable"
            )
            if is_exam_query and not is_match_exam:
                media_match = None
            if media_match:
                return media_match
    except Exception as e:
        logger.debug("[MATERIALS] Error searching media manager: %s", e)

    # 4. Dynamic: search data folder for any file matching the query
    match = find_file_in_data_folder(q)
    if match:
        return match

    return None


def find_file_in_data_folder(query: str) -> Optional[Dict[str, Any]]:
    """
    Recursively search data folder (and materials) for any file
    whose name matches the query. Supports PDFs, images, and documents.
    """
    if not query:
        return None
    q = query.lower().strip()
    data_dir = get_data_folder()

    # Extract likely filename keywords from the query
    # e.g. "send me the physics notes pdf" → search for "physics", "notes"
    stop_words = {
        "send", "me", "the", "a", "an", "my", "to", "for", "of", "in",
        "share", "attach", "give", "pdf", "file", "document", "image",
        "photo", "pic", "picture", "please", "can", "you", "bro", "da",
        "hey", "want", "need", "it", "this", "that", "and", "or", "with",
    }
    keywords = [w for w in re.split(r"\W+", q) if w and w not in stop_words and len(w) >= 3]

    if not keywords:
        return None

    supported_exts = {
        ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp",
        ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt",
        ".csv", ".zip", ".rar", ".mp4", ".mp3", ".wav",
    }

    best_match = None
    best_score = 0

    search_dirs = [data_dir]
    materials_dir = get_materials_dir()
    if materials_dir != data_dir:
        search_dirs.append(materials_dir)

    is_exam_query = any(k in q for k in [
        "ca 1", "ca1", "cat 1", "cat1", "ca test", "cat test", "assessment",
        "exam timetable", "test timetable", "ca timetable", "cat timetable", "assessment test", "ca schedule"
    ])

    for sdir in search_dirs:
        if not sdir.is_dir():
            continue
        for fpath in sdir.rglob("*"):
            if not fpath.is_file():
                continue
            if fpath.suffix.lower() not in supported_exts:
                continue
            fname_lower = fpath.stem.lower().replace("_", " ").replace("-", " ")

            # STRICT ISOLATION: Never match regular class timetable for exam query
            if is_exam_query and not any(k in fname_lower for k in ["assessment", "ca", "cat", "exam"]):
                continue

            score = sum(1 for kw in keywords if kw in fname_lower)
            if score > best_score:
                best_score = score
                best_match = fpath

    if best_match and best_score > 0:
        is_image = best_match.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
        return {
            "id": f"dynamic_{best_match.stem}",
            "filename": best_match.name,
            "title": best_match.stem.replace("_", " ").replace("-", " ").title(),
            "description": f"File from data folder: {best_match.name}",
            "path": str(best_match),
            "is_image": is_image,
            "keywords": keywords,
        }

    return None


def list_all_data_files() -> List[Dict[str, str]]:
    """List all files in data folder for reference."""
    data_dir = get_data_folder()
    results = []
    supported_exts = {
        ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp",
        ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt",
        ".csv", ".zip", ".mp4", ".mp3",
    }
    if data_dir.is_dir():
        for fpath in sorted(data_dir.rglob("*")):
            if fpath.is_file() and fpath.suffix.lower() in supported_exts:
                results.append({
                    "name": fpath.name,
                    "path": str(fpath),
                    "type": fpath.suffix.lower(),
                    "size_kb": round(fpath.stat().st_size / 1024, 1),
                })
    return results
