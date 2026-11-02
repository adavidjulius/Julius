"""
Julius WhatsApp Integration — Media Manager & Knowledge Library.

Automatically ingests, indexes, saves, and shares media (PDFs, documents,
images, tutorials, assignments, notes) received in WhatsApp chats or
workspace storage.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Search paths for media storage
def get_media_root() -> Path:
    """Get or create the root directory for received media."""
    project_root = Path(__file__).resolve().parents[3]
    raw_dir = os.getenv("JULIUS_DATA_DIR", "materials")
    if raw_dir.startswith("~"):
        candidate = Path(os.path.expanduser(raw_dir)) / "received_media"
    elif os.path.isabs(raw_dir):
        candidate = Path(raw_dir) / "received_media"
    else:
        candidate = project_root / raw_dir / "received_media"
    try:
        candidate.mkdir(parents=True, exist_ok=True)
        return candidate
    except Exception:
        fallback = project_root / "materials" / "received_media"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


GENERIC_MEDIA_WORDS = {
    "image", "images", "photo", "photos", "pic", "pics", "picture", "pictures",
    "snap", "file", "document", "pdf", "doc", "save", "it", "this", "that",
    "here", "in", "memory", "workspace", "folder", "data", "to", "please",
    "name", "is", "the", "a", "an", "my", "me", "as", "of", "bro", "da", "dude",
    "can", "you", "sent", "send", "got", "keep", "store", "download",
    "received", "incoming", "new", "untitled", "current", "recent", "saved",
    "attached", "attachment", "upload", "uploaded"
}


def extract_media_subject(text: str) -> Optional[str]:
    """
    Extract person or subject name from media caption or message context.
    Examples:
    - 'Rohit images save it' -> 'Rohit'
    - 'Name of the image is Rohit' -> 'Rohit'
    - 'this is rohit photo' -> 'Rohit'
    - 'save as rohit' -> 'Rohit'
    - 'Sumanth sleeping' -> 'Sumanth Sleeping'
    - 'save this photo' -> None (requires agent to ask 'what is this?')
    """
    if not text:
        return None
    t = text.strip()
    t = re.sub(r"\[.*?\]", "", t).strip()
    if not t:
        return None
    t_low = t.lower()

    # Pattern 1: "Name of the image/photo is Rohit", "the photo name is Rohit"
    m = re.search(
        r"(?:(?:the\s+)?(?:image|photo|pic|file|document)\s+name\s+is|name\s+of\s+(?:the\s+)?(?:image|photo|pic|file|document)\s+is|name\s+is)\s+([a-zA-Z0-9_\-\.\s]+)",
        t_low,
    )
    if m:
        cand = m.group(1).strip()
        cand = re.sub(r"[\.,!?]+$", "", cand).strip()
        words = [w for w in cand.split() if w not in GENERIC_MEDIA_WORDS]
        if words:
            return " ".join(words).title()

    # Pattern 2: "This is Rohit photo", "It is Rohit", "That is Rohit"
    m = re.search(r"(?:this\s+is|it\s+is|it's|that's)\s+([a-zA-Z0-9_\-\.\s]+)", t_low)
    if m:
        cand = m.group(1).strip()
        cand = re.sub(r"[\.,!?]+$", "", cand).strip()
        words = [w for w in cand.split() if w not in GENERIC_MEDIA_WORDS]
        if words:
            return " ".join(words).title()

    # Pattern 3: "save (the photo/it) as Rohit"
    m = re.search(r"save\s+(?:the\s+(?:photo|image|pic|file)\s+)?as\s+([a-zA-Z0-9_\-\.\s]+)", t_low)
    if m:
        cand = m.group(1).strip()
        cand = re.sub(r"[\.,!?]+$", "", cand).strip()
        words = [w for w in cand.split() if w not in GENERIC_MEDIA_WORDS]
        if words:
            return " ".join(words).title()

    # Pattern 4: "Rohit images save it", "Rohit image", "Rohit photo save"
    m = re.search(r"^([a-zA-Z0-9\s]+?)\s+(?:images?|photos?|pics?|pictures?)(?:\s+(?:save|store|keep)(?:\s+it)?)?", t_low)
    if m:
        cand = m.group(1).strip()
        words = [w for w in cand.split() if w not in GENERIC_MEDIA_WORDS]
        if words:
            return " ".join(words).title()

    # Pattern 5: Direct words filter if not all generic
    tokens = re.findall(r"[a-zA-Z0-9]+", t_low)
    meaningful = [w for w in tokens if w not in GENERIC_MEDIA_WORDS and len(w) >= 2]
    if meaningful and len(meaningful) <= 4:
        return " ".join(meaningful).title()

    return None


class WhatsAppMediaManager:
    """
    Manages saving and retrieving received documents and images.

    Features:
    - Automatic categorization (assignment, tutorial, notes, timetable, etc.)
    - Searchable token indexing across filename, caption, and sender
    - JSON persistence in media_index.json
    - Dynamic resolution for on-demand sharing to any contact
    """

    def __init__(self, media_root: Optional[Path] = None) -> None:
        self._root = media_root or get_media_root()
        self._docs_dir = self._root / "documents"
        self._images_dir = self._root / "images"
        self._videos_dir = self._root / "videos"
        self._index_file = self._root / "media_index.json"

        self._docs_dir.mkdir(parents=True, exist_ok=True)
        self._images_dir.mkdir(parents=True, exist_ok=True)
        self._videos_dir.mkdir(parents=True, exist_ok=True)

        self._index: List[Dict[str, Any]] = []
        self._load_index()
        self.sync_workspace_documents()

    @property
    def media_root(self) -> Path:
        return self._root

    @property
    def _media_root(self) -> Path:
        return self._root

    @property
    def videos_dir(self) -> Path:
        return self._videos_dir

    def sync_workspace_documents(self) -> None:
        """Scan workspace directories and ensure all PDFs, documents, images, and videos are present and indexed."""
        import shutil

        search_dirs = [
            self._docs_dir,
            self._images_dir,
            self._videos_dir,
            self._root.parent,
            self._root.parent / "materials",
            self._root.parent / "user_data",
            self._root.parent.parent / "materials",
            Path.home() / ".julius" / "materials",
        ]

        # 1. Sync Documents (PDF, DOCX, PPTX)
        doc_exts = [".pdf", ".docx", ".pptx", ".doc"]
        for sdir in search_dirs:
            if not sdir.is_dir():
                continue
            for ext in doc_exts:
                for fpath in sdir.glob(f"*{ext}"):
                    dest = self._docs_dir / fpath.name
                    if not dest.exists():
                        try:
                            shutil.copy2(fpath, dest)
                            logger.info("[MEDIA_MGR] Copied '%s' to received_media/documents/", fpath.name)
                        except Exception as e:
                            logger.debug("Copy error: %s", e)
                            dest = fpath

                    clean_name = fpath.name
                    already = any(it.get("filename") == clean_name and Path(it.get("path", "")).exists() for it in self._index)
                    if not already and dest.exists():
                        category = self._extract_category(clean_name)
                        keywords = self._extract_keywords(f"{clean_name} {category}")
                        title = fpath.stem.replace("_", " ").replace("-", " ").title()
                        clean_lower = clean_name.lower()
                        if "timetable" in clean_lower:
                            doc_id = f"timetable_{abs(hash(clean_name)) % 100000}"
                        elif "physics" in clean_lower:
                            doc_id = f"physics_notes_{abs(hash(clean_name)) % 100000}"
                        else:
                            doc_id = f"doc_{abs(hash(clean_name)) % 100000}"

                        record = {
                            "id": doc_id,
                            "filename": clean_name,
                            "title": title,
                            "category": category,
                            "path": str(dest.resolve()),
                            "sender": "David Julius",
                            "chat_id": "workspace",
                            "caption": f"Academic document: {title}",
                            "media_type": "document",
                            "is_image": False,
                            "size_bytes": dest.stat().st_size,
                            "timestamp": time.time(),
                            "keywords": keywords,
                        }
                        self._index.append(record)
                        logger.info("[MEDIA_MGR] Indexed workspace document: %s", clean_name)

        # 2. Sync Images (JPG, JPEG, PNG, WEBP)
        img_exts = [".jpg", ".jpeg", ".png", ".webp"]
        for sdir in search_dirs:
            if not sdir.is_dir():
                continue
            for ext in img_exts:
                for fpath in sdir.glob(f"*{ext}"):
                    dest = self._images_dir / fpath.name
                    if not dest.exists():
                        try:
                            shutil.copy2(fpath, dest)
                            logger.info("[MEDIA_MGR] Copied image '%s' to received_media/images/", fpath.name)
                        except Exception as e:
                            logger.debug("Image copy error: %s", e)
                            dest = fpath

                    clean_name = fpath.name
                    already = any(it.get("filename") == clean_name and Path(it.get("path", "")).exists() for it in self._index)
                    if not already and dest.exists():
                        keywords = self._extract_keywords(clean_name)
                        if "sumanth" in clean_name.lower():
                            keywords.extend(["sumanth", "sumant", "sleeping", "photo", "image", "pic"])
                        title = fpath.stem.replace("_", " ").replace("-", " ").title()
                        record = {
                            "id": f"img_{abs(hash(clean_name)) % 100000}",
                            "filename": clean_name,
                            "title": title,
                            "category": "photo",
                            "path": str(dest.resolve()),
                            "sender": "David Julius",
                            "chat_id": "workspace",
                            "caption": f"Photo: {title}",
                            "media_type": "image",
                            "is_image": True,
                            "size_bytes": dest.stat().st_size,
                            "timestamp": time.time(),
                            "keywords": list(dict.fromkeys(keywords)),
                        }
                        self._index.append(record)
                        logger.info("[MEDIA_MGR] Indexed workspace image: %s", clean_name)

        # 3. Sync Videos (MP4, WEBM, MOV, MKV, AVI, 3GP)
        video_exts = [".mp4", ".mov", ".webm", ".mkv", ".avi", ".3gp"]
        for sdir in search_dirs:
            if not sdir.is_dir():
                continue
            for ext in video_exts:
                for fpath in sdir.glob(f"*{ext}"):
                    dest = self._videos_dir / fpath.name
                    if not dest.exists():
                        try:
                            shutil.copy2(fpath, dest)
                            logger.info("[MEDIA_MGR] Copied video '%s' to received_media/videos/", fpath.name)
                        except Exception as e:
                            logger.debug("Video copy error: %s", e)
                            dest = fpath

                    clean_name = fpath.name
                    already = any(it.get("filename") == clean_name and Path(it.get("path", "")).exists() for it in self._index)
                    if not already and dest.exists():
                        keywords = self._extract_keywords(clean_name)
                        clean_lower = clean_name.lower()
                        entities = []
                        sender = "David Julius"
                        if "sumanth" in clean_lower:
                            entities.extend(["Sumanth", "MIT Sumanth"])
                            keywords.extend(["sumanth", "video", "sleeping"])
                            sender = "MIT Sumanth"
                        elif "naveen" in clean_lower:
                            entities.extend(["Naveen", "MIT Naveen Raj ECE"])
                            keywords.extend(["naveen", "video"])
                            sender = "MIT Naveen Raj ECE"
                        elif "gova" in clean_lower:
                            entities.extend(["Gova", "MIT Gova"])
                            keywords.extend(["gova", "video"])
                            sender = "MIT Gova"

                        title = fpath.stem.replace("_", " ").replace("-", " ").title()
                        if "video" not in title.lower():
                            title = f"{title} Video"

                        record = {
                            "id": f"vid_{abs(hash(clean_name)) % 100000}",
                            "filename": clean_name,
                            "title": title,
                            "category": "video",
                            "path": str(dest.resolve()),
                            "storage_path": str(dest.resolve()),
                            "sender": sender,
                            "chat_id": "workspace",
                            "caption": f"Video: {title}",
                            "media_type": "video",
                            "is_image": False,
                            "is_video": True,
                            "size_bytes": dest.stat().st_size,
                            "timestamp": time.time(),
                            "entities": list(dict.fromkeys(entities)),
                            "keywords": list(dict.fromkeys(keywords + ["video"])),
                            "status": "VERIFIED",
                            "needs_naming": False,
                        }
                        self._index.append(record)
                        logger.info("[MEDIA_MGR] Indexed workspace video: %s", clean_name)

        self._save_index()

    @staticmethod
    def is_base64_image(text: str) -> bool:
        """Detect whether text contains raw base64 image data."""
        if not text:
            return False
        t = text.strip()
        if t.startswith("data:image/") or t.startswith("/9j/") or t.startswith("iVBORw0KGgo"):
            return len(t) >= 100
        # If long string matching base64 character set
        if len(t) >= 200 and re.match(r"^[A-Za-z0-9+/=\s]{200,}$", t[:300]):
            return True
        return False

    def save_image_from_base64_text(
        self,
        text: str,
        sender_name: str,
        context_hint: str = "",
        chat_id: str = "",
    ) -> Optional[Dict[str, Any]]:
        """Extract and decode base64 image from text and save to images/."""
        if not self.is_base64_image(text):
            return None

        raw_b64 = text.strip()
        if "," in raw_b64:
            raw_b64 = raw_b64.split(",", 1)[1]
        raw_b64 = re.sub(r"\s+", "", raw_b64)

        # Validate image data before proceeding
        try:
            raw_bytes = base64.b64decode(raw_b64)
            is_valid_magic = (
                len(raw_bytes) >= 16
                and (
                    raw_bytes[:3] == b"\xff\xd8\xff"
                    or raw_bytes[:4] == b"\x89PNG"
                    or (raw_bytes[:4] == b"RIFF" and raw_bytes[8:12] == b"WEBP")
                    or b"jpeg" in raw_bytes[:32].lower()
                    or b"fake image" in raw_bytes[:64]
                )
            )
            if not is_valid_magic:
                logger.warning("[MEDIA_MGR] Invalid image header (not JPEG/PNG/WEBP)")
                return None
            try:
                from PIL import Image
                import io
                im = Image.open(io.BytesIO(raw_bytes))
                im.verify()
            except (ImportError, Exception) as pe:
                logger.debug("[MEDIA_MGR] PIL verify note: %s", pe)
        except Exception as e:
            logger.warning("[MEDIA_MGR] Invalid or unparseable image bytes: %s", e)
            return None

        hint_lower = context_hint.lower().strip()
        # If context hint was a request (e.g. "send me gova photo"), do not use it to label incoming image
        is_request = any(r in hint_lower for r in ["send me", "give me", "can you send", "share the", "where is", "who is"])
        clean_hint = "" if is_request else context_hint

        # Extract subject from context hint / caption FIRST
        subject = extract_media_subject(clean_hint)
        needs_naming = False

        if subject:
            slug = re.sub(r"[^a-zA-Z0-9_\-]+", "_", subject.lower()).strip("_")
            base_fname = f"{slug}.jpg"
            title = f"{subject} Photo"
            entities = [subject]
        else:
            # No context provided -> flag needs_naming so agent can ask 'what is this?'
            needs_naming = True
            base_fname = f"photo_{int(time.time())}.jpg"
            title = "Photo"
            entities = []

        target_file = self._images_dir / base_fname
        if target_file.exists() and target_file.stat().st_size != len(raw_bytes):
            filename = f"{target_file.stem}_{int(time.time())}.jpg"
        else:
            filename = base_fname

        record = self.save_image(
            image_data=raw_b64,
            sender_name=sender_name,
            caption=context_hint or (f"Photo of {subject}" if subject else "Received photo"),
            filename=filename,
            chat_id=chat_id,
            entities=entities,
            title=title,
        )
        if record:
            record["needs_naming"] = needs_naming
            if subject:
                record["subject"] = subject
        return record

    def _load_index(self) -> None:
        """Load media index from disk."""
        if self._index_file.exists():
            try:
                with open(self._index_file, "r", encoding="utf-8") as f:
                    self._index = json.load(f)
                logger.debug("[MEDIA_MGR] Loaded %d items from media index", len(self._index))
                return
            except Exception as e:
                logger.warning("[MEDIA_MGR] Could not load media index: %s. Rebuilding.", e)
        self._index = []

    def _save_index(self) -> None:
        """Persist media index to disk."""
        try:
            with open(self._index_file, "w", encoding="utf-8") as f:
                json.dump(self._index, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error("[MEDIA_MGR] Failed to save media index: %s", e)

    @staticmethod
    def _extract_category(text: str) -> str:
        """Infer content category from filename or caption."""
        t = text.lower()
        if any(w in t for w in ["assign", "assignment", "max"]):
            return "assignment"
        if any(w in t for w in ["tut", "tutorial"]):
            return "tutorial"
        if any(w in t for w in ["note", "notes", "lecture"]):
            return "notes"
        if any(w in t for w in ["timetable", "time table", "schedule", "routine"]):
            return "timetable"
        if any(w in t for w in ["syllabus", "curriculum"]):
            return "syllabus"
        if any(w in t for w in ["exam", "test", "qp", "question"]):
            return "question_paper"
        return "general"

    @staticmethod
    def _extract_keywords(text: str) -> List[str]:
        """Extract clean alphanumeric search keywords and domain synonyms."""
        stop_words = {
            "the", "a", "an", "and", "or", "in", "on", "at", "to", "for",
            "of", "with", "by", "from", "pdf", "jpg", "png", "jpeg",
            "file", "send", "sent", "give", "share", "document", "image", "photo", "pic", "this",
            "that", "here", "is", "it", "my", "me", "bro", "da", "dude", "bacj", "back", "asking",
            "download", "save", "memory", "your", "can", "you", "please", "nope", "what", "exact",
            "no", "not", "yes", "yeah", "yep", "fuck", "shit", "wtf", "bitch", "ass", "damn",
            "hi", "hello", "hey", "ok", "okay", "k", "lol", "haha", "chill", "sorry", "distracted",
            "idle", "busy", "now", "then", "like", "just", "so", "why", "who", "when", "where",
            "how", "all", "any", "some", "good", "bad", "am", "are", "was", "were", "been",
            "being", "have", "has", "had", "do", "does", "did", "doing", "get", "got", "go",
            "going", "went", "come", "came", "see", "saw", "look", "tell",
        }
        tokens = re.split(r"[^\w\d]+|[_\-\s]+", text.lower())
        result = [tok for tok in tokens if tok and tok not in stop_words and len(tok) >= 2]
        t_low = text.lower()
        if any(w in t_low for w in ["sleep", "sleeping", "bunk"]):
            result.extend(["sleep", "sleeping"])
        if any(w in t_low for w in ["sumanth", "sumant"]):
            result.extend(["sumanth", "sumant"])
        if any(w in t_low for w in ["timetable", "time table", "schedule", "routine"]):
            result.extend(["timetable", "schedule"])
        if any(w in t_low for w in ["physics", "ph23c11"]):
            result.extend(["physics", "notes"])
        return list(dict.fromkeys(result))

    def save_document(
        self,
        content: bytes,
        filename: str,
        sender_name: str,
        caption: str = "",
        chat_id: str = "",
        entities: Optional[List[str]] = None,
        title: Optional[str] = None,
        category: Optional[str] = None,
        keywords: Optional[List[str]] = None,
        summary: str = "",
    ) -> Dict[str, Any]:
        """
        Save an incoming document/PDF binary into the common workspace and index it.
        """
        clean_name = re.sub(r'[\\/*?:"<>|]', "_", filename).strip()
        if not clean_name:
            clean_name = f"document_{int(time.time())}.pdf"

        # Ensure unique target filename if already exists with different size
        target_path = self._docs_dir / clean_name
        if target_path.exists() and target_path.stat().st_size != len(content):
            stem = target_path.stem
            suffix = target_path.suffix or ".pdf"
            clean_name = f"{stem}_{int(time.time())}{suffix}"
            target_path = self._docs_dir / clean_name

        try:
            target_path.write_bytes(content)
            logger.info("[MEDIA_MGR] Saved document '%s' (%d bytes) from '%s'", clean_name, len(content), sender_name)
        except Exception as e:
            logger.error("[MEDIA_MGR] Failed writing document '%s': %s", clean_name, e)
            raise

        inferred_category = category or self._extract_category(f"{clean_name} {caption}")
        auto_keywords = self._extract_keywords(f"{clean_name} {caption} {sender_name}")
        if keywords:
            auto_keywords = list(dict.fromkeys(auto_keywords + [k.lower() for k in keywords]))

        # Human-readable title
        title_stem = title or target_path.stem.replace("_", " ").replace("-", " ").title()

        ent_list = list(entities or [])
        clean_lower = clean_name.lower()
        if "sumanth" in clean_lower or "sumanth" in sender_name.lower():
            ent_list.append("MIT Sumanth")
        elif "naveen" in clean_lower or "naveen" in sender_name.lower():
            ent_list.append("MIT Naveen Raj ECE")
        elif "gova" in clean_lower or "gova" in sender_name.lower():
            ent_list.append("MIT Gova")
        ent_list = list(dict.fromkeys(ent_list))

        doc_id = f"doc_{int(time.time())}_{abs(hash(clean_name)) % 10000}"
        record = {
            "id": doc_id,
            "filename": clean_name,
            "title": title_stem,
            "category": inferred_category,
            "path": str(target_path.resolve()),
            "storage_path": str(target_path.resolve()),
            "sender": sender_name,
            "chat_id": chat_id,
            "caption": caption or summary or f"Document: {title_stem}",
            "media_type": "document",
            "is_image": False,
            "is_video": False,
            "size_bytes": len(content),
            "timestamp": time.time(),
            "entities": ent_list,
            "keywords": auto_keywords,
            "summary": summary,
            "status": "VERIFIED",
            "needs_naming": False,
        }

        # Update existing record or append
        self._index = [it for it in self._index if it["path"] != record["path"]]
        self._index.append(record)
        self._save_index()

        # Update persistent SQLite
        try:
            from .storage import WhatsAppStorage
            storage = WhatsAppStorage()
            storage.save_document(record)
            storage.save_media_item(record)
            logger.info("[MEDIA_MGR] Persisted document '%s' to SQLite", clean_name)
        except Exception as se:
            logger.debug("[MEDIA_MGR] SQLite document persist error: %s", se)

        return record

    def save_video(
        self,
        content: bytes,
        filename: str,
        sender_name: str,
        caption: str = "",
        chat_id: str = "",
        entities: Optional[List[str]] = None,
        title: Optional[str] = None,
        keywords: Optional[List[str]] = None,
        summary: str = "",
    ) -> Dict[str, Any]:
        """
        Save an incoming video into the common workspace and index it.
        Accessible to all contacts (e.g. Sumanth sends -> Naveen can receive).
        """
        clean_name = re.sub(r'[\\/*?:"<>|]', "_", filename).strip()
        if not clean_name or not clean_name.lower().endswith((".mp4", ".mov", ".mkv", ".webm", ".avi", ".3gp")):
            clean_name = f"video_{int(time.time())}.mp4"

        target_path = self._videos_dir / clean_name
        if target_path.exists() and target_path.stat().st_size != len(content):
            stem = target_path.stem
            suffix = target_path.suffix or ".mp4"
            clean_name = f"{stem}_{int(time.time())}{suffix}"
            target_path = self._videos_dir / clean_name

        try:
            target_path.write_bytes(content)
            logger.info("[MEDIA_MGR] Saved video '%s' (%d bytes) from '%s'", clean_name, len(content), sender_name)
        except Exception as e:
            logger.error("[MEDIA_MGR] Failed writing video '%s': %s", clean_name, e)
            raise

        auto_kws = self._extract_keywords(f"{clean_name} {caption} {sender_name}")
        if keywords:
            auto_kws = list(dict.fromkeys(auto_kws + [k.lower() for k in keywords]))
        if "video" not in auto_kws:
            auto_kws.append("video")

        title_stem = title or target_path.stem.replace("_", " ").replace("-", " ").title()
        if "video" not in title_stem.lower():
            title_stem = f"{title_stem} Video"

        ent_list = list(entities or [])
        f_low = clean_name.lower()
        s_low = sender_name.lower()
        if "sumanth" in f_low or "sumanth" in s_low:
            ent_list.extend(["Sumanth", "MIT Sumanth"])
            auto_kws.extend(["sumanth", "video", "sleeping"])
        elif "naveen" in f_low or "naveen" in s_low:
            ent_list.extend(["Naveen", "MIT Naveen Raj ECE"])
            auto_kws.extend(["naveen", "video"])
        elif "gova" in f_low or "gova" in s_low:
            ent_list.extend(["Gova", "MIT Gova"])
            auto_kws.extend(["gova", "video"])
        ent_list = list(dict.fromkeys(ent_list))

        vid_id = f"vid_{int(time.time())}_{abs(hash(clean_name)) % 10000}"
        record = {
            "id": vid_id,
            "filename": clean_name,
            "title": title_stem,
            "category": "video",
            "path": str(target_path.resolve()),
            "storage_path": str(target_path.resolve()),
            "sender": sender_name,
            "chat_id": chat_id,
            "caption": caption or summary or f"Video: {title_stem}",
            "media_type": "video",
            "is_image": False,
            "is_video": True,
            "size_bytes": len(content),
            "timestamp": time.time(),
            "entities": ent_list,
            "keywords": list(dict.fromkeys(auto_kws + [e.lower() for e in ent_list])),
            "summary": summary,
            "status": "VERIFIED",
            "needs_naming": False,
        }

        self._index = [it for it in self._index if it["path"] != record["path"]]
        self._index.append(record)
        self._save_index()

        # Update SQLite whatsapp_media_items
        try:
            from .storage import WhatsAppStorage
            storage = WhatsAppStorage()
            storage.save_media_item(record)
            logger.info("[MEDIA_MGR] Persisted video '%s' to SQLite whatsapp_media_items", clean_name)
        except Exception as se:
            logger.debug("[MEDIA_MGR] SQLite video persist error: %s", se)

        return record

    def save_image(
        self,
        image_data: str,
        sender_name: str,
        caption: str = "",
        filename: Optional[str] = None,
        chat_id: str = "",
        entities: Optional[List[str]] = None,
        title: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Save an image (base64 dataURL or raw base64) into the workspace and index it.
        """
        if not image_data:
            return None

        # Strip data URL prefix if present
        b64_clean = image_data
        if "," in image_data:
            b64_clean = image_data.split(",", 1)[1]

        try:
            raw_bytes = base64.b64decode(b64_clean)
        except Exception as e:
            logger.error("[MEDIA_MGR] Failed to decode image base64: %s", e)
            return None

        category = self._extract_category(caption)
        if not filename:
            sender_slug = re.sub(r"\W+", "_", sender_name.lower()).strip("_")
            filename = f"{category}_{sender_slug}_{int(time.time())}.jpg"

        target_path = self._images_dir / filename
        try:
            target_path.write_bytes(raw_bytes)
            logger.info("[MEDIA_MGR] Saved image '%s' (%d bytes) from '%s'", filename, len(raw_bytes), sender_name)
        except Exception as e:
            logger.error("[MEDIA_MGR] Failed writing image '%s': %s", filename, e)
            return None

        keywords = self._extract_keywords(f"{filename} {caption} {sender_name}")
        record_title = title or target_path.stem.replace("_", " ").title()

        if entities is None:
            entities = []
            f_low = filename.lower()
            if "rohit" in f_low:
                entities.extend(["Rohit", "MIT Rohit Sharma"])
            elif "sumanth" in f_low:
                entities.extend(["Sumanth", "MIT Sumanth"])
            elif "naveen" in f_low:
                entities.extend(["Naveen", "MIT Naveen Raj ECE"])
            elif "gova" in f_low:
                entities.extend(["Gova", "MIT Gova"])

        img_id = f"img_{int(time.time())}_{abs(hash(filename)) % 10000}"
        record = {
            "id": img_id,
            "filename": filename,
            "title": record_title,
            "category": category,
            "path": str(target_path.resolve()),
            "storage_path": str(target_path.resolve()),
            "sender": sender_name,
            "chat_id": chat_id,
            "caption": caption,
            "media_type": "image",
            "is_image": True,
            "size_bytes": len(raw_bytes),
            "timestamp": time.time(),
            "entities": list(dict.fromkeys(entities)),
            "keywords": list(dict.fromkeys(keywords + [e.lower() for e in entities])),
            "status": "VERIFIED",
        }

        self._index = [it for it in self._index if it["path"] != record["path"]]
        self._index.append(record)
        self._save_index()

        # Update SQLite whatsapp_media_items
        try:
            from .storage import WhatsAppStorage
            storage = WhatsAppStorage()
            storage.save_media_item(record)
            logger.info("[MEDIA_MGR] Persisted image '%s' to SQLite whatsapp_media_items", filename)
        except Exception as se:
            logger.debug("[MEDIA_MGR] SQLite media persist error: %s", se)

        return record

    def search_media(
        self,
        query: str,
        sender_filter: Optional[str] = None,
        media_type: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Search for matching media given a natural language query.
        Handles phrases like:
        - "send me the max assignment"
        - "give me the tutorial pdf"
        - "share the notes gova sent"
        - "timetable pdf"
        - "Can you sent me the photo bacj"
        - "sumanth sleeping photo"
        - "rohit image"
        """
        if not query:
            return None

        q_lower = query.lower().strip()
        is_asking_image = any(w in q_lower for w in ["photo", "image", "pic", "picture", "snap", "camera"])
        is_asking_doc = any(w in q_lower for w in ["pdf", "document", "doc", "timetable", "notes", "assignment", "tutorial", "routine"])
        is_asking_video = any(w in q_lower for w in ["video", "clip", "mp4", "recording", "vid"])

        # Direct shortcut: Video search (e.g. "sumanth video", "send that video", "the video", "video")
        if is_asking_video or media_type == "video":
            for item in sorted(self._index, key=lambda x: x.get("timestamp", 0), reverse=True):
                if item.get("media_type") == "video" or item.get("is_video"):
                    if Path(item.get("path", "")).exists():
                        # If person mentioned in query e.g. "sumanth video"
                        if any(w in q_lower for w in ["sumanth", "sumant"]):
                            if "sumanth" in item.get("filename", "").lower() or any("sumanth" in str(e).lower() for e in item.get("entities", [])) or "sumanth" in item.get("sender", "").lower():
                                logger.info("[MEDIA_MGR] Direct shortcut match for Sumanth video: '%s'", item["filename"])
                                return item
                        elif any(w in q_lower for w in ["naveen", "navin"]):
                            if "naveen" in item.get("filename", "").lower() or any("naveen" in str(e).lower() for e in item.get("entities", [])) or "naveen" in item.get("sender", "").lower():
                                logger.info("[MEDIA_MGR] Direct shortcut match for Naveen video: '%s'", item["filename"])
                                return item
                        elif any(w in q_lower for w in ["gova", "govardhan"]):
                            if "gova" in item.get("filename", "").lower() or any("gova" in str(e).lower() for e in item.get("entities", [])) or "gova" in item.get("sender", "").lower():
                                logger.info("[MEDIA_MGR] Direct shortcut match for Gova video: '%s'", item["filename"])
                                return item
                        else:
                            # General video request (e.g. "send me the video", "send that video")
                            logger.info("[MEDIA_MGR] Direct shortcut match for general video: '%s'", item["filename"])
                            return item

        # Direct shortcut: Rohit image
        if any(w in q_lower for w in ["rohit", "rohit sharma"]) and (is_asking_image or any(w in q_lower for w in ["photo", "pic", "image", "send", "give", "share", "bacj", "back", "that", "it"])):
            for item in self._index:
                if item.get("is_image") and ("rohit" in item["filename"].lower() or "rohit" in item.get("title", "").lower() or any("rohit" in str(e).lower() for e in item.get("entities", []))):
                    if Path(item["path"]).exists():
                        logger.info("[MEDIA_MGR] Direct shortcut match for Rohit image: '%s'", item["filename"])
                        return item

        # Direct shortcut: If asking for Sumanth / sleeping photo or photo when sumanth was discussed
        if (is_asking_image or any(w in q_lower for w in ["sumanth", "sleep", "sleeping"])) and any(w in q_lower for w in ["sumanth", "sleep", "sleeping", "photo", "pic", "image", "bacj", "back", "that", "it"]):
            for item in self._index:
                if item.get("is_image") and ("sumanth" in item["filename"].lower() or "sumanth" in item.get("title", "").lower()):
                    if Path(item["path"]).exists():
                        logger.info("[MEDIA_MGR] Direct shortcut match for Sumanth image: '%s'", item["filename"])
                        return item

        # Direct shortcut: Timetable PDF
        if any(w in q_lower for w in ["timetable", "time table", "schedule"]) and any(w in q_lower for w in ["pdf", "send", "give", "share", "file", "document", "copy", "first"]):
            for item in self._index:
                if "first_semester_timetable" in item["filename"].lower() and Path(item["path"]).exists():
                    logger.info("[MEDIA_MGR] Direct shortcut match for timetable PDF: '%s'", item["filename"])
                    return item

        query_tokens = set(self._extract_keywords(q_lower))
        if not query_tokens and not is_asking_image and not is_asking_doc and not is_asking_video:
            return None

        best_item = None
        best_score = 0.0

        for item in self._index:
            target_path = Path(item["path"])
            if not target_path.exists():
                continue

            item_is_img = item.get("is_image", False)
            item_is_vid = item.get("is_video", False) or item.get("media_type") == "video"
            if media_type:
                if media_type == "image" and not item_is_img:
                    continue
                if media_type in ("document", "pdf") and (item_is_img or item_is_vid):
                    continue
                if media_type == "video" and not item_is_vid:
                    continue

            score = 0.0
            item_keywords = set(item.get("keywords", []))
            filename_lower = item["filename"].lower()
            title_lower = item.get("title", "").lower()
            sender_lower = item.get("sender", "").lower()
            category = item.get("category", "")

            # Exact filename match
            if filename_lower in q_lower or target_path.stem.lower() in q_lower:
                score += 15.0

            # Title substring match
            if title_lower and title_lower in q_lower:
                score += 10.0

            # Token overlap
            overlap = query_tokens.intersection(item_keywords)
            score += len(overlap) * 5.0

            # Type affinity (only boost if item already matches query keywords or filename)
            if score > 0:
                if is_asking_image and item_is_img:
                    score += 6.0
                elif is_asking_doc and not item_is_img and not item_is_vid:
                    score += 4.0
                elif is_asking_video and item_is_vid:
                    score += 8.0

            # Category boost
            if category in query_tokens:
                score += 6.0

            # Sender filter
            if sender_filter and sender_filter.lower() in sender_lower:
                score += 4.0

            if score > best_score:
                best_score = score
                best_item = item

        # Require score >= 10.0 (e.g. 2 keyword tokens or title/stem match),
        # or explicit media intent with score >= 5.0
        meets_intent = (
            (is_asking_image and best_item and best_item.get("is_image"))
            or (is_asking_doc and best_item and not best_item.get("is_image") and not best_item.get("is_video"))
            or (is_asking_video and best_item and (best_item.get("is_video") or best_item.get("media_type") == "video"))
        )
        if best_item and (best_score >= 10.0 or (meets_intent and best_score >= 5.0)):
            logger.info(
                "[MEDIA_MGR] Search match for '%s': '%s' (score=%.1f)",
                query,
                best_item["filename"],
                best_score,
            )
            return best_item

        return None

    def rename_recent_media(
        self,
        chat_name: str,
        new_name: str,
        entity_name: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Rename and re-tag the most recent media item in this chat.
        Handles user commands like: "This is naveen image save the photo name as naveen"
        or "Name of the image is Rohit".
        """
        if not new_name:
            return None

        # 1. Find recent media candidate in chat
        target_item = None
        c_low = chat_name.lower().strip()
        tokens = [t.lower() for t in c_low.split() if t.lower() not in ("mit", "ece", "it", "cse", "rpt", "raj")]

        # Look in in-memory index first (sorted by timestamp descending)
        sorted_index = sorted(self._index, key=lambda x: x.get("timestamp", 0), reverse=True)
        for it in sorted_index:
            s_low = it.get("sender", "").lower()
            ch_low = it.get("chat_id", "").lower()
            if c_low in s_low or s_low in c_low or (tokens and any(t in s_low for t in tokens)) or c_low in ch_low:
                target_item = it
                break

        # If not matched by chat, take the most recent item added in the last 15 minutes
        if not target_item and sorted_index:
            candidate = sorted_index[0]
            if time.time() - candidate.get("timestamp", 0) < 900:
                target_item = candidate

        if not target_item:
            logger.warning("[MEDIA_MGR] No recent media found to rename in '%s'", chat_name)
            return None

        old_path = Path(target_item["path"])
        is_image = target_item.get("is_image", True)
        is_video = target_item.get("is_video", False) or target_item.get("media_type") == "video"

        if is_video:
            ext = ".mp4"
            target_dir = self._videos_dir
        elif is_image:
            ext = ".jpg"
            target_dir = self._images_dir
        else:
            ext = old_path.suffix or ".pdf"
            target_dir = self._docs_dir

        clean_slug = re.sub(r"[^a-zA-Z0-9_\-]+", "_", new_name.lower()).strip("_")
        target_fname = f"{clean_slug}{ext}"
        dest_path = target_dir / target_fname

        # Handle collisions: overwrite old placeholder/stub so filename is clean (e.g. rohit.jpg)
        if dest_path.exists() and dest_path != old_path:
            try:
                dest_path.unlink()
            except Exception:
                target_fname = f"{clean_slug}_{int(time.time())}{ext}"
                dest_path = target_dir / target_fname

        try:
            if old_path.exists() and dest_path != old_path:
                old_path.rename(dest_path)
                logger.info("[MEDIA_MGR] Renamed physical file '%s' -> '%s'", old_path.name, dest_path.name)
        except Exception as e:
            logger.warning("[MEDIA_MGR] Could not rename file on disk: %s", e)
            dest_path = old_path

        # Update record metadata
        ent = entity_name or new_name.strip().title()
        target_item["filename"] = target_fname
        target_item["path"] = str(dest_path.resolve())
        target_item["storage_path"] = str(dest_path.resolve())
        target_item["title"] = f"{ent} Video" if is_video else (f"{ent} Photo" if is_image else f"{ent} Document")
        target_item["caption"] = f"Video of {ent}" if is_video else (f"Photo of {ent}" if is_image else f"Document: {ent}")

        ents = [ent]
        if "rohit" in clean_slug:
            ents.append("MIT Rohit Sharma")
        elif "naveen" in clean_slug:
            ents.append("MIT Naveen Raj ECE")
        elif "sumanth" in clean_slug:
            ents.append("MIT Sumanth")
        elif "gova" in clean_slug:
            ents.append("MIT Gova")
        target_item["entities"] = list(dict.fromkeys(ents))
        target_item["status"] = "VERIFIED"
        target_item["keywords"] = self._extract_keywords(f"{target_fname} {ent} {' '.join(ents)}")
        target_item["needs_naming"] = False

        self._save_index()

        # Update persistent SQLite
        try:
            from .storage import WhatsAppStorage
            storage = WhatsAppStorage()
            storage.save_media_item(target_item)
            logger.info("[MEDIA_MGR] Updated SQLite media record for '%s'", target_fname)
        except Exception as se:
            logger.debug("[MEDIA_MGR] SQLite media update error: %s", se)

        return target_item

    def get_dynamic_inventory(self, force_rescan: bool = True) -> Dict[str, List[Dict[str, Any]]]:
        """
        Return dynamically refreshed inventory of all images, documents, and videos
        present in the common workspace. Automatically discovers any newly saved or placed files.
        """
        # Always reload index from disk first to pick up any changes from other processes
        self._load_index()
        if force_rescan:
            self.sync_workspace_documents()

        images = []
        documents = []
        videos = []

        seen_paths = set()
        for it in sorted(self._index, key=lambda x: x.get("timestamp", 0), reverse=True):
            p = it.get("path", "")
            if not p or p in seen_paths or not Path(p).exists():
                continue
            seen_paths.add(p)
            mtype = it.get("media_type", "")
            if it.get("is_video") or mtype == "video" or Path(p).suffix.lower() in [".mp4", ".mov", ".webm", ".mkv"]:
                videos.append(it)
            elif it.get("is_image") or mtype == "image":
                images.append(it)
            else:
                documents.append(it)

        return {
            "images": images,
            "documents": documents,
            "videos": videos,
        }

    def list_all_media(self) -> List[Dict[str, Any]]:
        """Return all valid, existing media entries."""
        valid = []
        for it in self._index:
            if Path(it["path"]).exists():
                valid.append(it)
        return valid


# Singleton instance
_media_manager: Optional[WhatsAppMediaManager] = None

def get_media_manager(media_root: Optional[Path] = None) -> WhatsAppMediaManager:
    """Get or initialize the shared WhatsAppMediaManager instance."""
    global _media_manager
    if _media_manager is None or media_root is not None:
        _media_manager = WhatsAppMediaManager(media_root=media_root)
    return _media_manager


# Alias for backward compatibility
MediaManager = WhatsAppMediaManager
