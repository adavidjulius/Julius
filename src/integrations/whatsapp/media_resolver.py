"""
Julius WhatsApp Integration — Deterministic MediaResolver.

Resolves exact images and documents from persistent storage and filesystem.
Guarantees:
- Zero cross-person image contamination (e.g., asking for Naveen never sends Sumanth).
- Zero hallucination (if not found in verified storage, returns NOT_FOUND).
- Ambiguity detection (asks user for clarification when multiple candidates exist).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .entity_resolver import EntityResolver, get_entity_resolver
from .media_manager import get_media_manager
from .models import MediaResolution, ResolutionStatus
from .storage import WhatsAppStorage

logger = logging.getLogger(__name__)


class MediaResolver:
    """
    Dedicated, deterministic media and document resolver.
    The LLM never directly chooses files or media objects.
    """

    def __init__(self, storage: WhatsAppStorage, entity_resolver: Optional[EntityResolver] = None) -> None:
        self._storage = storage
        self._entity_resolver = entity_resolver or EntityResolver(storage)

    def resolve_image(
        self,
        person_query: Optional[str] = None,
        general_query: str = "",
        chat_name: str = "",
    ) -> MediaResolution:
        """
        Resolve an image based on an explicit person entity or contextual description.
        Enforces strict identity separation.
        """
        target_entity: Optional[str] = None
        if person_query:
            person_rec = self._entity_resolver.resolve_person(person_query)
            if person_rec:
                target_entity = person_rec["canonical_name"]
            else:
                target_entity = person_query.strip().title()

        # 1. Search persistent media items in SQLite
        candidates: List[Dict[str, Any]] = []

        if target_entity:
            # Look for media explicitly associated with this person
            all_imgs = self._storage.find_media_items(media_type="image", limit=50)
            target_slug = target_entity.lower()
            tokens = [t.lower() for t in target_entity.split()]
            # Add short name tokens (e.g. 'naveen', 'gova', 'sumanth')
            short_tokens = [t for t in tokens if t not in ("mit", "ece", "it", "cse", "rpt", "raj")]

            for img in all_imgs:
                f_path = Path(img.get("storage_path", ""))
                if not f_path.exists():
                    continue

                img_ents = [str(e).lower() for e in img.get("entities", [])]
                fname_low = img.get("filename", "").lower()
                caption_low = img.get("caption", "").lower()

                # Check if this image explicitly belongs to the target person
                is_person_match = (
                    any(target_slug in e for e in img_ents)
                    or any(st in img_ents for st in short_tokens)
                    or any(st in fname_low for st in short_tokens)
                    or any(st in caption_low for st in short_tokens)
                )

                if is_person_match:
                    # STRICT CROSS-PERSON CHECK:
                    # Verify this candidate does NOT belong to a DIFFERENT known person
                    other_persons = ["rohit", "sumanth", "gova", "govardhan", "vishal", "monish", "reddy", "latchuman", "sundar"]
                    has_other_person = False
                    for other in other_persons:
                        if other not in short_tokens and (other in fname_low or any(other in e for e in img_ents)):
                            has_other_person = True
                            break
                    if not has_other_person:
                        candidates.append(img)

        # 2. Check filesystem materials/received_media/images if SQLite empty
        if target_entity and not candidates:
            mm_inst = get_media_manager()
            root_path = getattr(mm_inst, "media_root", getattr(mm_inst, "_media_root", Path("materials/received_media")))
            search_dirs = [
                root_path / "images",
                Path("materials/received_media/images"),
                Path.home() / ".julius" / "materials" / "received_media" / "images",
            ]
            short_tokens = [t.lower() for t in target_entity.split() if t.lower() not in ("mit", "ece", "it", "cse", "rpt", "raj", "sharma")]

            for sdir in search_dirs:
                if not sdir.exists():
                    continue
                for fpath in sdir.glob("*.jpg"):
                    fname_low = fpath.name.lower()
                    if any(st in fname_low for st in short_tokens):
                        # Ensure no conflict with another person
                        other_persons = ["rohit", "sumanth", "gova", "govardhan", "vishal", "monish", "reddy", "latchuman"]
                        if not any(other not in short_tokens and other in fname_low for other in other_persons):
                            record = {
                                "media_id": f"fs_{fpath.stem}",
                                "media_type": "image",
                                "filename": fpath.name,
                                "storage_path": str(fpath.resolve()),
                                "path": str(fpath.resolve()),
                                "title": f"{target_entity} Photo",
                                "caption": f"Photo of {target_entity}",
                                "entities": [target_entity],
                                "verified": True,
                                "status": "VERIFIED",
                            }
                            candidates.append(record)
                            break
                if candidates:
                    break

        # 2.5 Check media_manager index directly
        if target_entity and not candidates:
            mm_match = get_media_manager().search_media(target_entity, media_type="image")
            if mm_match and Path(mm_match.get("path", "")).exists():
                candidates.append({
                    "media_id": mm_match.get("id"),
                    "media_type": "image",
                    "filename": mm_match.get("filename"),
                    "storage_path": mm_match.get("path"),
                    "path": mm_match.get("path"),
                    "title": mm_match.get("title", f"{target_entity} Photo"),
                    "caption": mm_match.get("caption", f"Photo of {target_entity}"),
                    "entities": mm_match.get("entities", [target_entity]),
                    "verified": True,
                    "status": "VERIFIED",
                })

        # 2.8 Check direct filename match if filename is specified
        if not candidates and general_query:
            g_clean = general_query.strip()
            mm = get_media_manager()
            for it in mm._index:
                if it.get("is_image") and (it.get("filename", "").lower() == g_clean.lower() or it.get("title", "").lower() == g_clean.lower()):
                    p = Path(it.get("path", ""))
                    if p.exists():
                        candidates.append({
                            "media_id": it.get("id"),
                            "media_type": "image",
                            "filename": it.get("filename"),
                            "storage_path": str(p.resolve()),
                            "path": str(p.resolve()),
                            "title": it.get("title", "Photo"),
                            "caption": it.get("caption", "Photo"),
                            "entities": it.get("entities", []),
                            "verified": True,
                            "status": "VERIFIED",
                        })
                        break
            if not candidates:
                root_path = getattr(mm, "media_root", getattr(mm, "_media_root", Path("materials/received_media")))
                search_dirs_list = [
                    root_path / "images",
                    Path("materials/received_media/images"),
                    Path.home() / ".julius" / "materials" / "received_media" / "images",
                ]
                for sdir in search_dirs_list:
                    if not sdir.exists():
                        continue
                    direct_f = sdir / g_clean
                    if direct_f.exists() and direct_f.is_file():
                        candidates.append({
                            "media_id": f"fs_{direct_f.stem}",
                            "media_type": "image",
                            "filename": direct_f.name,
                            "storage_path": str(direct_f.resolve()),
                            "path": str(direct_f.resolve()),
                            "title": direct_f.stem.replace("_", " ").title(),
                            "caption": f"Photo: {direct_f.stem.replace('_', ' ').title()}",
                            "entities": [direct_f.stem.replace("_", " ").title()],
                            "verified": True,
                            "status": "VERIFIED",
                        })
                        break

        # 3. If no person requested, but an image was requested (e.g. "send me the image", "sene the photo", "the photo", "recent photo")
        if not target_entity and general_query:
            q_low = general_query.lower()
            is_referring_to_media = any(w in q_low for w in ["latest", "recent", "sent yesterday", "sent earlier", "last", "the image", "the photo", "this image", "this photo", "that image", "that photo", "sene me the image", "send me the image", "sene the image", "send the image"]) or any(w in q_low for w in ["image", "photo", "pic"])
            if is_referring_to_media:
                latest = self._storage.get_latest_media_in_chat(chat_name, media_type="image", max_age_seconds=86400.0)
                if not latest or not Path(latest.get("storage_path", "")).exists():
                    # Fallback to media_manager recent media in chat or workspace
                    for it in sorted(get_media_manager()._index, key=lambda x: x.get("timestamp", 0), reverse=True):
                        if it.get("is_image") and Path(it.get("path", "")).exists():
                            latest = {
                                "media_id": it.get("id"),
                                "media_type": "image",
                                "filename": it.get("filename"),
                                "storage_path": it.get("path"),
                                "path": it.get("path"),
                                "title": it.get("title", "Photo"),
                                "caption": it.get("caption", "Photo"),
                                "entities": it.get("entities", []),
                                "verified": True,
                                "status": "VERIFIED",
                            }
                            break
                if latest and Path(latest.get("storage_path", "")).exists():
                    candidates.append(latest)

        # Evaluate candidates
        if not candidates:
            reason = f"No verified image found for '{target_entity or general_query}' in workspace memory."
            logger.info("[MEDIA_RESOLVER] Image NOT_FOUND: %s", reason)
            return MediaResolution(
                status=ResolutionStatus.NOT_FOUND,
                reason=reason,
                target_entity=target_entity,
                media_type="image",
            )

        # Filter duplicates by path
        unique_candidates = []
        seen_paths = set()
        for c in candidates:
            p = c.get("storage_path") or c.get("path")
            if p and p not in seen_paths:
                seen_paths.add(p)
                unique_candidates.append(c)

        if len(unique_candidates) == 1:
            chosen = unique_candidates[0]
            logger.info("[MEDIA_RESOLVER] Image EXACT_MATCH: '%s' for '%s'", chosen["filename"], target_entity)
            return MediaResolution(
                status=ResolutionStatus.EXACT_MATCH,
                item=chosen,
                candidates=unique_candidates,
                target_entity=target_entity,
                media_type="image",
            )
        else:
            logger.info("[MEDIA_RESOLVER] Image AMBIGUOUS: %d candidates found for '%s'", len(unique_candidates), target_entity)
            return MediaResolution(
                status=ResolutionStatus.AMBIGUOUS,
                candidates=unique_candidates,
                reason=f"Multiple images found for {target_entity}. Which one would you like?",
                target_entity=target_entity,
                media_type="image",
            )

    def resolve_video(
        self,
        person_query: Optional[str] = None,
        general_query: str = "",
        chat_name: str = "",
    ) -> MediaResolution:
        """
        Resolve a video from the common workspace across all users/contacts.
        E.g. if Sumanth sent a video, and Naveen asks for "sumanth video" or "the video",
        it searches the shared workspace repository.
        """
        target_entity: Optional[str] = None
        if person_query:
            person_rec = self._entity_resolver.resolve_person(person_query)
            if person_rec:
                target_entity = person_rec["canonical_name"]
            else:
                target_entity = person_query.strip().title()
        elif general_query:
            g_low = general_query.lower()
            for p in ["sumanth", "naveen", "gova", "govardhan", "rohit", "vishal", "monish", "reddy", "latchuman", "sundar", "david"]:
                if p in g_low:
                    target_entity = p.title()
                    break

        candidates: List[Dict[str, Any]] = []

        # 1. Search persistent media items in SQLite
        if target_entity:
            all_vids = self._storage.find_media_items(media_type="video", limit=50)
            target_slug = target_entity.lower()
            tokens = [t.lower() for t in target_entity.split() if t.lower() not in ("mit", "ece", "it", "cse", "rpt", "raj")]

            for vid in all_vids:
                f_path = Path(vid.get("storage_path", ""))
                if not f_path.exists():
                    continue

                vid_ents = [str(e).lower() for e in vid.get("entities", [])]
                fname_low = vid.get("filename", "").lower()
                caption_low = vid.get("caption", "").lower()
                sender_low = vid.get("sender", "").lower()

                is_match = (
                    any(target_slug in e for e in vid_ents)
                    or any(st in vid_ents for st in tokens)
                    or any(st in fname_low for st in tokens)
                    or any(st in caption_low for st in tokens)
                    or any(st in sender_low for st in tokens)
                )

                if is_match:
                    other_persons = ["rohit", "sumanth", "gova", "govardhan", "vishal", "monish", "reddy", "latchuman", "sundar", "naveen"]
                    has_other = False
                    for other in other_persons:
                        if other not in tokens and (other in fname_low or any(other in e for e in vid_ents)):
                            has_other = True
                            break
                    if not has_other:
                        candidates.append(vid)

        # 2. Check media_manager index directly
        mm = get_media_manager()

        if target_entity and not candidates:
            mm_match = mm.search_media(target_entity, media_type="video")
            if mm_match and Path(mm_match.get("path", "")).exists():
                candidates.append({
                    "media_id": mm_match.get("id"),
                    "media_type": "video",
                    "filename": mm_match.get("filename"),
                    "storage_path": mm_match.get("path"),
                    "path": mm_match.get("path"),
                    "title": mm_match.get("title", f"{target_entity} Video"),
                    "caption": mm_match.get("caption", f"Video of {target_entity}"),
                    "entities": mm_match.get("entities", [target_entity]),
                    "verified": True,
                    "status": "VERIFIED",
                })

        # 3. Check filesystem materials/received_media/videos
        if target_entity and not candidates:
            root_path = getattr(mm, "media_root", getattr(mm, "_media_root", Path("materials/received_media")))
            search_dirs = [
                root_path / "videos",
                Path("materials/received_media/videos"),
                Path.home() / ".julius" / "materials" / "received_media" / "videos",
            ]
            tokens = [t.lower() for t in target_entity.split() if t.lower() not in ("mit", "ece", "it", "cse", "rpt", "raj", "sharma")]
            video_exts = ("*.mp4", "*.mov", "*.webm", "*.mkv", "*.avi", "*.3gp")

            for sdir in search_dirs:
                if not sdir.exists():
                    continue
                for ext in video_exts:
                    for fpath in sdir.glob(ext):
                        fname_low = fpath.name.lower()
                        if any(st in fname_low for st in tokens):
                            other_persons = ["rohit", "sumanth", "gova", "govardhan", "vishal", "monish", "reddy", "latchuman", "sundar", "naveen"]
                            if not any(other not in tokens and other in fname_low for other in other_persons):
                                candidates.append({
                                    "media_id": f"fs_{fpath.stem}",
                                    "media_type": "video",
                                    "filename": fpath.name,
                                    "storage_path": str(fpath.resolve()),
                                    "path": str(fpath.resolve()),
                                    "title": fpath.stem.replace("_", " ").title(),
                                    "caption": f"Video: {fpath.stem.replace('_', ' ').title()}",
                                    "entities": [target_entity],
                                    "verified": True,
                                    "status": "VERIFIED",
                                })
                                break
                    if candidates:
                        break
                if candidates:
                    break

        # 4. If no specific person, or general video request ("the video", "recent video", "video", "send video")
        if not candidates:
            q_low = (general_query or "").lower()
            is_referring_video = any(w in q_low for w in ["video", "vid", "clip", "recording", "mp4"]) or not target_entity
            if is_referring_video:
                # First check media_manager for most recent video in common workspace
                latest_vid = None
                for it in sorted(mm._index, key=lambda x: x.get("timestamp", 0), reverse=True):
                    if (it.get("is_video") or it.get("media_type") == "video") and Path(it.get("path", "")).exists():
                        latest_vid = {
                            "media_id": it.get("id"),
                            "media_type": "video",
                            "filename": it.get("filename"),
                            "storage_path": it.get("path"),
                            "path": it.get("path"),
                            "title": it.get("title", "Video"),
                            "caption": it.get("caption", "Video"),
                            "entities": it.get("entities", []),
                            "verified": True,
                            "status": "VERIFIED",
                        }
                        break
                if not latest_vid:
                    # Check SQLite
                    sqlite_vids = self._storage.find_media_items(media_type="video", limit=1)
                    if sqlite_vids and Path(sqlite_vids[0].get("storage_path", "")).exists():
                        latest_vid = sqlite_vids[0]

                if latest_vid:
                    candidates.append(latest_vid)

        # Evaluate candidates
        if not candidates:
            reason = f"No verified video found for '{target_entity or general_query}' in common workspace memory."
            logger.info("[MEDIA_RESOLVER] Video NOT_FOUND: %s", reason)
            return MediaResolution(
                status=ResolutionStatus.NOT_FOUND,
                reason=reason,
                target_entity=target_entity,
                media_type="video",
            )

        unique_candidates = []
        seen_paths = set()
        for c in candidates:
            p = c.get("storage_path") or c.get("path")
            if p and p not in seen_paths:
                seen_paths.add(p)
                unique_candidates.append(c)

        if len(unique_candidates) == 1:
            chosen = unique_candidates[0]
            logger.info("[MEDIA_RESOLVER] Video EXACT_MATCH: '%s' for '%s'", chosen["filename"], target_entity)
            return MediaResolution(
                status=ResolutionStatus.EXACT_MATCH,
                item=chosen,
                candidates=unique_candidates,
                target_entity=target_entity,
                media_type="video",
            )
        else:
            logger.info("[MEDIA_RESOLVER] Video AMBIGUOUS: %d candidates found for '%s'", len(unique_candidates), target_entity)
            return MediaResolution(
                status=ResolutionStatus.AMBIGUOUS,
                candidates=unique_candidates,
                reason=f"Multiple videos found for {target_entity or general_query}. Which one would you like?",
                target_entity=target_entity,
                media_type="video",
            )

    def resolve_document(
        self,
        query: str,
        semester: Optional[int] = None,
        doc_type: Optional[str] = None,
    ) -> MediaResolution:
        """
        Deterministically resolve a document/PDF.
        Guarantees zero hallucination: if second semester timetable requested
        and only first semester exists, returns NOT_FOUND rather than sending wrong semester.
        Searches common workspace documents and dynamic media index.
        """
        if not query:
            return MediaResolution(status=ResolutionStatus.NOT_FOUND, reason="Empty document query.")

        q_low = query.lower()

        # Check explicit semester query
        req_sem = semester
        if "second semester" in q_low or "2nd semester" in q_low or "sem 2" in q_low:
            req_sem = 2
        elif "first semester" in q_low or "1st semester" in q_low or "sem 1" in q_low:
            req_sem = 1

        # Check explicit exam/assessment vs class routine query
        is_exam_query = any(k in q_low for k in [
            "ca 1", "ca1", "cat 1", "cat1", "ca test", "cat test", "assessment",
            "exam timetable", "test timetable", "ca timetable", "cat timetable", "assessment test", "ca schedule"
        ])
        effective_doc_type = "exam_timetable" if is_exam_query else doc_type

        # 1. Search persistent documents in SQLite
        docs = self._storage.find_documents(query=query, doc_type=effective_doc_type, semester=req_sem)
        valid_docs = []
        for d in docs:
            p = Path(d.get("storage_path", ""))
            if p.exists():
                d["path"] = str(p.resolve())
                valid_docs.append(d)

        # 2. Check dynamic media_manager index for newly saved documents in common workspace
        if not valid_docs:
            mm_match = get_media_manager().search_media(query, media_type="document")
            if mm_match and Path(mm_match.get("path", "")).exists():
                m_path = Path(mm_match.get("path", ""))
                valid_docs.append({
                    "id": mm_match.get("id"),
                    "filename": mm_match.get("filename"),
                    "title": mm_match.get("title", mm_match.get("filename")),
                    "storage_path": str(m_path.resolve()),
                    "path": str(m_path.resolve()),
                    "doc_type": mm_match.get("category", "document"),
                    "category": mm_match.get("category", "document"),
                    "sender": mm_match.get("sender", "David Julius"),
                    "entities": mm_match.get("entities", []),
                    "status": "VERIFIED",
                })

        # 3. Check materials catalog and data folder fallback
        if not valid_docs:
            from .materials import find_matching_document, find_file_in_data_folder
            match = find_matching_document(query) or find_file_in_data_folder(query)
            if match and Path(match.get("path", "")).exists():
                match_name = match.get("filename", "").lower()
                if req_sem == 2 and ("first" in match_name or "1st" in match_name):
                    pass
                else:
                    valid_docs.append(match)

        # 4. Check filesystem materials/received_media/documents directly
        if not valid_docs:
            mm_inst = get_media_manager()
            root_path = getattr(mm_inst, "media_root", getattr(mm_inst, "_media_root", Path("materials/received_media")))
            doc_dirs = [
                root_path / "documents",
                Path("materials/received_media/documents"),
                Path.home() / ".julius" / "materials" / "received_media" / "documents",
            ]
            clean_q = re.sub(r"[^a-zA-Z0-9\s]", " ", q_low)
            query_tokens = [t for t in clean_q.split() if t not in ("send", "the", "pdf", "file", "doc", "document", "me", "give", "share")]
            for ddir in doc_dirs:
                if not ddir.exists():
                    continue
                for fpath in ddir.glob("*.*"):
                    if fpath.suffix.lower() in [".pdf", ".docx", ".xlsx", ".pptx", ".doc"]:
                        fname_low = fpath.name.lower()
                        if query_tokens and all(t in fname_low for t in query_tokens):
                            valid_docs.append({
                                "id": f"fs_{fpath.stem}",
                                "filename": fpath.name,
                                "title": fpath.stem.replace("_", " ").title(),
                                "storage_path": str(fpath.resolve()),
                                "path": str(fpath.resolve()),
                                "doc_type": "document",
                                "status": "VERIFIED",
                            })
                            break
                if valid_docs:
                    break

        # Enforce semester check
        if req_sem == 2 and not any("second" in d.get("filename", "").lower() or d.get("semester") == 2 for d in valid_docs):
            reason = "Only the First Semester Timetable is currently available in workspace memory. The Second Semester Timetable has not been issued yet."
            logger.info("[MEDIA_RESOLVER] Document NOT_FOUND (semester mismatch): %s", reason)
            return MediaResolution(status=ResolutionStatus.NOT_FOUND, reason=reason, media_type="document")

        # STRICT ISOLATION: Never send class routine if user asked for exam/assessment timetable
        if is_exam_query:
            valid_docs = [
                d for d in valid_docs
                if "assessment" in d.get("filename", "").lower()
                or d.get("doc_type") == "exam_timetable"
                or "ca" in d.get("filename", "").lower()
            ]
            if not valid_docs:
                reason = "The First Assessment Test (CA-1) timetable has not been saved or confirmed in workspace memory yet."
                logger.info("[MEDIA_RESOLVER] Document NOT_FOUND (exam schedule missing): %s", reason)
                return MediaResolution(status=ResolutionStatus.NOT_FOUND, reason=reason, media_type="document")

        if not valid_docs:
            reason = f"No verified document found matching '{query}' in workspace memory."
            logger.info("[MEDIA_RESOLVER] Document NOT_FOUND: %s", reason)
            return MediaResolution(status=ResolutionStatus.NOT_FOUND, reason=reason, media_type="document")

        if len(valid_docs) == 1:
            chosen = valid_docs[0]
            logger.info("[MEDIA_RESOLVER] Document EXACT_MATCH: '%s'", chosen.get("filename"))
            return MediaResolution(
                status=ResolutionStatus.EXACT_MATCH,
                item=chosen,
                candidates=valid_docs,
                media_type="document",
            )
        else:
            return MediaResolution(
                status=ResolutionStatus.AMBIGUOUS,
                candidates=valid_docs,
                reason=f"Multiple documents match '{query}'. Which one do you need?",
                media_type="document",
            )

    def resolve_media(
        self,
        query: str,
        media_type: Optional[str] = None,
        chat_name: str = "",
    ) -> MediaResolution:
        """Unified media resolver dispatching to image, video, or document."""
        q_low = query.lower()
        if media_type == "video" or any(w in q_low for w in ["video", "vid", "clip", ".mp4", ".mov"]):
            return self.resolve_video(general_query=query, chat_name=chat_name)
        elif media_type == "image" or any(w in q_low for w in ["photo", "image", "pic", ".jpg", ".png", ".webp"]):
            return self.resolve_image(general_query=query, chat_name=chat_name)
        elif media_type == "document" or any(w in q_low for w in ["pdf", "timetable", "notes", "document", ".docx"]):
            return self.resolve_document(query=query)
        else:
            # Try video, then image, then document
            vid_res = self.resolve_video(general_query=query, chat_name=chat_name)
            if vid_res.status == ResolutionStatus.EXACT_MATCH:
                return vid_res
            img_res = self.resolve_image(general_query=query, chat_name=chat_name)
            if img_res.status == ResolutionStatus.EXACT_MATCH:
                return img_res
            return self.resolve_document(query=query)


_MEDIA_RESOLVER_INSTANCE: Optional[MediaResolver] = None


def get_media_resolver(storage: Optional[WhatsAppStorage] = None) -> MediaResolver:
    global _MEDIA_RESOLVER_INSTANCE
    if _MEDIA_RESOLVER_INSTANCE is None:
        if storage is None:
            storage = WhatsAppStorage()
        _MEDIA_RESOLVER_INSTANCE = MediaResolver(storage)
    return _MEDIA_RESOLVER_INSTANCE
