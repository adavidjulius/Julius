"""
Julius WhatsApp Integration — Perception Layer & Autonomous Media Labeling.

Extracts perceptual content from incoming files (documents, images, videos)
and leverages LLM reasoning to autonomously name, categorize, and label
files without asking the user for clarification.
"""

from __future__ import annotations

import io
import json
import logging
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class PerceptionLayer:
    """
    Perception and autonomous understanding layer for WhatsApp media.
    Extracts text, visual cues, metadata, and surrounding chat context,
    then uses LLM reasoning to determine exact titles, categories, and entities.
    """

    def __init__(self, media_root: Optional[Path] = None) -> None:
        self._media_root = media_root

    @staticmethod
    def extract_text_from_pdf(pdf_bytes: bytes, max_pages: int = 3) -> str:
        """Extract text from the first pages of a PDF using pypdf or pdftotext CLI."""
        if not pdf_bytes:
            return ""

        extracted = ""
        # 1. Try pypdf (fast, in-memory)
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(pdf_bytes))
            pages_to_read = min(len(reader.pages), max_pages)
            parts = []
            for i in range(pages_to_read):
                p_text = reader.pages[i].extract_text()
                if p_text:
                    parts.append(p_text.strip())
            extracted = "\n".join(parts).strip()
            if len(extracted) > 30:
                logger.debug("[PERCEPTION] Extracted %d chars from PDF via pypdf", len(extracted))
                return extracted
        except Exception as e:
            logger.debug("[PERCEPTION] pypdf extraction note: %s", e)

        # 2. Fallback to pdftotext CLI if installed
        pdftotext_bin = shutil.which("pdftotext") or "/opt/homebrew/bin/pdftotext"
        if os.path.exists(pdftotext_bin):
            try:
                proc = subprocess.run(
                    [pdftotext_bin, "-f", "1", "-l", str(max_pages), "-", "-"],
                    input=pdf_bytes,
                    capture_output=True,
                    timeout=5,
                )
                if proc.returncode == 0 and proc.stdout:
                    txt = proc.stdout.decode("utf-8", errors="ignore").strip()
                    if len(txt) > 20:
                        logger.debug("[PERCEPTION] Extracted %d chars via pdftotext CLI", len(txt))
                        return txt
            except Exception as pe:
                logger.debug("[PERCEPTION] pdftotext CLI error: %s", pe)

        # 3. Fallback: inspect raw PDF text streams for readable ASCII strings
        try:
            raw_text = pdf_bytes[:30000].decode("latin1", errors="ignore")
            readable_chunks = re.findall(r"\(([A-Za-z0-9\s,.\-_:]{4,})\)", raw_text)
            if readable_chunks:
                stream_text = " ".join(readable_chunks[:40]).strip()
                if len(stream_text) > 30:
                    return stream_text
        except Exception:
            pass

        return extracted

    @classmethod
    def extract_text_from_document(cls, doc_bytes: bytes, filename: str) -> str:
        """Extract readable text from incoming document."""
        if not doc_bytes:
            return ""
        fn_low = filename.lower()
        if fn_low.endswith(".pdf"):
            return cls.extract_text_from_pdf(doc_bytes)
        elif fn_low.endswith((".txt", ".md", ".csv", ".json")):
            try:
                return doc_bytes.decode("utf-8", errors="ignore")[:4000]
            except Exception:
                return ""
        return ""

    @classmethod
    def fallback_heuristic_identity(
        cls,
        raw_filename: str,
        media_type: str,
        sender_name: str,
        caption: str = "",
        burst_messages: Optional[List[str]] = None,
        extracted_text: str = "",
    ) -> Dict[str, Any]:
        """
        Deterministic, high-accuracy fallback when LLM is unavailable.
        Uses perceptual signals from extracted content, burst messages, and sender.
        """
        burst_text = " ".join(burst_messages or [])
        combined_text = f"{raw_filename} {caption} {burst_text} {extracted_text}".lower()

        entities: List[str] = []
        keywords: List[str] = []

        # Detect sender / friend entities
        sender_low = sender_name.lower()
        peer_map = {
            "alex": "Contact Alex",
            "alexander": "Contact Alexander",
            "charlie": "Contact Charlie",
            "dave": "Contact Dave",
            "eve": "Contact Eve",
            "frank": "Contact Frank",
            "grace": "Contact Grace",
            "henry": "Contact Henry",
            "ian": "Contact Ian",
            "jack": "Contact Jack",
            "kevin": "Contact Kevin",
            "leo": "Contact Leo",
            "max": "Contact Max",
            "nathan": "Contact Nathan",
            "gova": "Contact Alex",
            "govardhan": "Contact Alexander",
            "sundar": "Contact Charlie",
            "naveen": "Contact Dave",
            "anish": "Contact Eve",
            "chandru": "Contact Frank",
            "raj": "Contact Grace",
            "ashwin": "Contact Henry",
            "reddy": "Contact Ian",
            "vishal": "Contact Jack",
            "sumanth": "Contact Kevin",
            "anil": "Contact Leo",
            "monish": "Contact Max",
            "latchuman": "Contact Nathan",
        }
        for token, canonical in peer_map.items():
            if token in combined_text or token in sender_low:
                if canonical not in entities:
                    entities.append(canonical)
                keywords.extend([token, canonical.lower()])

        # Detect Subject / Academic Categories
        title = ""
        category = "general"
        ext = Path(raw_filename).suffix.lower() if raw_filename else ""

        if media_type == "video" or ext in [".mp4", ".mov", ".mkv", ".webm", ".avi", ".3gp"]:
            category = "video"
            ext = ext or ".mp4"
            if "sumanth" in combined_text or "sumanth" in sender_low:
                title = "Sumanth Video"
                if "sleep" in combined_text or "bunk" in combined_text:
                    title = "Sumanth Sleeping Video"
                entities.append("MIT Sumanth")
                keywords.extend(["sumanth", "video", "classroom"])
            elif "naveen" in combined_text or "naveen" in sender_low:
                title = "Naveen Video"
                entities.append("MIT Naveen Raj ECE")
                keywords.extend(["naveen", "video"])
            elif "gova" in combined_text or "gova" in sender_low:
                title = "Gova Video"
                entities.append("MIT Gova")
                keywords.extend(["gova", "video"])
            elif entities:
                ent_name = entities[0].replace("MIT ", "")
                title = f"{ent_name} Video"
            else:
                title = "Campus Video"
                keywords.extend(["video", "clip"])

        elif media_type == "document" or ext in [".pdf", ".docx", ".pptx", ".doc"]:
            ext = ext or ".pdf"
            if any(k in combined_text for k in ["assessment", "ca 1", "ca1", "cat 1", "cat1", "ca-1"]):
                title = "First Assessment Test Schedule (CA-1 / CAT-1)"
                category = "timetable"
                entities.append("First Assessment Test")
                keywords.extend(["assessment", "ca1", "cat1", "exam", "test", "schedule", "timetable"])
            elif any(k in combined_text for k in ["timetable", "time table", "schedule", "routine"]):
                category = "timetable"
                if "batch 2" in combined_text or "batch2" in combined_text:
                    title = "IT Batch 2 Timetable 2026"
                    entities.append("IT Batch 2")
                elif "batch 1" in combined_text or "batch1" in combined_text:
                    title = "IT Batch 1 Timetable 2026"
                    entities.append("IT Batch 1")
                else:
                    title = "First Semester Timetable 2026"
                    entities.append("First Semester Timetable")
                keywords.extend(["timetable", "schedule", "first semester", "2026"])
            elif any(k in combined_text for k in ["physics", "ph23c11", "shm", "oscillations", "optics"]):
                title = "Engineering Physics PH23C11 Notes"
                category = "notes"
                entities.extend(["Engineering Physics", "Physics"])
                keywords.extend(["physics", "ph23c11", "notes", "engineering physics"])
            elif any(k in combined_text for k in ["cad", "drawing", "graphics", "drafting"]):
                title = "Engineering Graphics & CAD Manual"
                category = "notes"
                entities.extend(["Engineering Graphics", "CAD"])
                keywords.extend(["cad", "drawing", "graphics", "manual"])
            elif any(k in combined_text for k in ["math", "calculus", "ma23c11", "integral"]):
                title = "Calculus & Mathematics Tutorial"
                category = "tutorial"
                entities.extend(["Calculus", "Mathematics"])
                keywords.extend(["math", "calculus", "tutorial"])
            elif any(k in combined_text for k in ["feee", "basics of eee", "electrical"]):
                title = "Basics of Electrical & Electronics Notes"
                category = "notes"
                entities.extend(["Basics of EEE", "Electrical"])
                keywords.extend(["feee", "electrical", "notes"])
            elif any(k in combined_text for k in ["python", "programming"]):
                title = "Python Programming Lab Manual"
                category = "notes"
                entities.append("Python Programming")
                keywords.extend(["python", "programming", "lab"])
            else:
                stem = Path(raw_filename).stem.replace("_", " ").replace("-", " ").strip()
                if stem and stem.lower() not in ["document", "scan copy", "doc", "file", "download"]:
                    title = stem.title()
                else:
                    title = f"Academic Document from {sender_name}"
                category = "notes"
                keywords.extend(["document", "notes"])

        elif media_type == "image" or ext in [".jpg", ".jpeg", ".png", ".webp"]:
            category = "photo"
            ext = ext or ".jpg"
            if "rohit" in combined_text:
                title = "Rohit Photo"
                entities.append("MIT Rohit Sharma")
                keywords.extend(["rohit", "photo", "pic"])
            elif "sumanth" in combined_text:
                title = "Sumanth Photo"
                if "sleep" in combined_text:
                    title = "Sumanth Sleeping Photo"
                entities.append("MIT Sumanth")
                keywords.extend(["sumanth", "photo", "sleeping"])
            elif "naveen" in combined_text:
                title = "Naveen Photo"
                entities.append("MIT Naveen Raj ECE")
                keywords.extend(["naveen", "photo"])
            elif "gova" in combined_text:
                title = "Gova Photo"
                if "shirt" in combined_text:
                    title = "Gova No Shirt Photo"
                entities.append("MIT Gova")
                keywords.extend(["gova", "photo"])
            elif entities:
                ent_name = entities[0].replace("MIT ", "")
                title = f"{ent_name} Photo"
            else:
                stem = Path(raw_filename).stem.replace("_", " ").strip()
                if stem and stem.lower() not in ["image", "photo", "pic", "untitled", "img"]:
                    title = stem.title()
                else:
                    title = f"Photo from {sender_name}"

        clean_slug = re.sub(r"[^a-zA-Z0-9_\-]+", "_", title.lower()).strip("_")
        clean_filename = f"{clean_slug}{ext}"

        return {
            "title": title or "Received Media",
            "clean_filename": clean_filename,
            "category": category,
            "entities": list(dict.fromkeys(entities)),
            "keywords": list(dict.fromkeys(keywords + [k.lower() for k in title.split()])),
            "summary": f"{title} received from {sender_name}",
        }

    @classmethod
    async def infer_file_identity(
        cls,
        raw_filename: str = "",
        media_type: str = "document",
        sender_name: str = "",
        file_bytes: Optional[bytes] = None,
        caption: str = "",
        burst_messages: Optional[List[str]] = None,
        original_filename: str = "",
        context_text: str = "",
        mime_type: str = "",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Analyze incoming file using Perception Layer + LLM Auto-Naming.
        Guarantees:
        - NEVER asks the user who or what the file is.
        - Automatically infers canonical title, clean filename, category, entities, and keywords.
        """
        raw_filename = raw_filename or original_filename or ""
        caption = caption or context_text or ""
        if context_text and not burst_messages:
            burst_messages = [context_text]
        # 1. Extract text from document if applicable
        extracted_text = ""
        if file_bytes and media_type in ("document", "text"):
            try:
                extracted_text = cls.extract_text_from_document(file_bytes, raw_filename)
            except Exception as e:
                logger.debug("[PERCEPTION] Text extraction error: %s", e)

        # 2. Prepare contextual signals
        burst_clean = [m.strip() for m in (burst_messages or []) if m and m.strip()]
        burst_str = " | ".join(burst_clean) if burst_clean else "(none)"
        caption_clean = caption.strip() if caption else "(none)"
        content_preview = extracted_text[:1800].strip() if extracted_text else "(No text extracted or binary media)"

        system_prompt = (
            "You are the perception and labeling layer of Julius WhatsApp assistant. "
            "A contact just sent a file on WhatsApp. Often, users send files along with multiple "
            "short burst messages explaining what it is ('everything sent at once').\n"
            "YOUR JOB: Accurately infer the specific title, clean filename, category, and subject/person entities.\n"
            "CRITICAL: DO NOT ASK THE USER WHO OR WHAT THIS IS. You MUST infer and name it autonomously.\n"
            "Return ONLY a valid JSON object matching this exact schema:\n"
            "{\n"
            '  "title": "Clear descriptive title (e.g. Engineering Physics PH23C11 Notes, First Semester Timetable 2026, Sumanth Sleeping Video)",\n'
            '  "clean_filename": "clean_snake_case_name_with_correct_extension (e.g. engineering_physics_ph23c11_notes.pdf, sumanth_sleeping_video.mp4)",\n'
            '  "category": "timetable" | "notes" | "assignment" | "tutorial" | "question_paper" | "photo" | "video" | "general",\n'
            '  "entities": ["entity1", "entity2"],\n'
            '  "keywords": ["keyword1", "keyword2", "keyword3"],\n'
            '  "summary": "1 short sentence describing file"\n'
            "}"
        )

        user_prompt = (
            f"INCOMING FILE PERCEPTION DATA:\n"
            f"- Sender: {sender_name}\n"
            f"- Media Type: {media_type}\n"
            f"- Raw Filename: {raw_filename}\n"
            f"- User Caption: {caption_clean}\n"
            f"- Burst Messages Sent At Once: {burst_str}\n"
            f"- Extracted Content Snippet:\n{content_preview}\n\n"
            f"Infer the title, clean_filename, category, entities, and keywords."
        )

        # 3. Call LLM
        try:
            from .api import generate_whatsapp_reply
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
            raw_llm_resp = await generate_whatsapp_reply(prompt=user_prompt, chat_messages=messages)
            if raw_llm_resp:
                json_text = raw_llm_resp.strip()
                # Parse markdown fence if present
                m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", json_text, re.DOTALL)
                if m:
                    json_text = m.group(1).strip()
                elif "{" in json_text and "}" in json_text:
                    first = json_text.find("{")
                    last = json_text.rfind("}")
                    json_text = json_text[first:last + 1].strip()

                data = json.loads(json_text)
                if isinstance(data, dict) and data.get("title"):
                    title = str(data["title"]).strip()
                    cat = str(data.get("category") or "general").strip().lower()
                    ents = [str(e) for e in data.get("entities", []) if e]
                    kws = [str(k).lower() for k in data.get("keywords", []) if k]
                    clean_fname = str(data.get("clean_filename") or "").strip()

                    orig_ext = Path(raw_filename).suffix.lower() if raw_filename else ""
                    if not orig_ext:
                        if media_type == "video":
                            orig_ext = ".mp4"
                        elif media_type == "image":
                            orig_ext = ".jpg"
                        elif media_type == "document":
                            orig_ext = ".pdf"
                        else:
                            orig_ext = ".bin"

                    if not clean_fname or not clean_fname.endswith(orig_ext):
                        slug = re.sub(r"[^a-zA-Z0-9_\-]+", "_", title.lower()).strip("_")
                        clean_fname = f"{slug}{orig_ext}"

                    logger.info("[PERCEPTION] LLM identified file '%s' -> '%s' (category=%s)", raw_filename, title, cat)
                    return {
                        "title": title,
                        "clean_filename": clean_fname,
                        "category": cat,
                        "entities": list(dict.fromkeys(ents)),
                        "keywords": list(dict.fromkeys(kws + [w.lower() for w in title.split()])),
                        "summary": str(data.get("summary") or f"{title} from {sender_name}"),
                    }
        except Exception as e:
            logger.debug("[PERCEPTION] LLM identification note: %s. Using heuristic fallback.", e)

        # 4. Fallback to heuristic perception
        fallback = cls.fallback_heuristic_identity(
            raw_filename=raw_filename,
            media_type=media_type,
            sender_name=sender_name,
            caption=caption,
            burst_messages=burst_messages,
            extracted_text=extracted_text,
        )
        logger.info("[PERCEPTION] Heuristic labeled file '%s' -> '%s'", raw_filename, fallback["title"])
        return fallback


_PERCEPTION_LAYER_INSTANCE: Optional[PerceptionLayer] = None


def get_perception_layer() -> PerceptionLayer:
    """Get or create singleton instance of PerceptionLayer."""
    global _PERCEPTION_LAYER_INSTANCE
    if _PERCEPTION_LAYER_INSTANCE is None:
        _PERCEPTION_LAYER_INSTANCE = PerceptionLayer()
    return _PERCEPTION_LAYER_INSTANCE
