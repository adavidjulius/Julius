"""
Julius WhatsApp Integration — Intent Engine.

Classifies incoming message intents deterministically.
Strictly separates informational questions from media/file execution actions.
"""

from __future__ import annotations

import logging
import re
from enum import Enum
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class MessageIntent(str, Enum):
    ASK_PERSON_INFO = "ask_person_info"          # "Who is Narendra?" -> NEVER sends media!
    ASK_SCHEDULE_LOCATION = "ask_schedule_loc"    # "Where is the user?" -> TimetableEngine
    ASK_DATE_TIME = "ask_date_time"              # "What date is today?" / "What is the time in Tokyo?"
    ASK_EXTERNAL_INFO = "ask_external_info"      # "Who is the CEO of Google?" -> web_search
    USER_CORRECTION = "user_correction"          # "That is false information", "You are wrong"
    SEND_PERSON_IMAGE = "send_person_image"      # "Send Alex's image" -> MediaResolver
    SEND_VIDEO = "send_video"                    # "Send the demo video" / "Send the video" -> MediaResolver
    SEND_DOCUMENT = "send_document"              # "Send the timetable PDF" -> MediaResolver
    RENAME_MEDIA_OR_DOCUMENT = "rename_media"    # "This is Alex image save the photo name as Alex"
    SAVE_MEDIA_CONFIRM = "save_media_confirm"    # "Save that in memory"
    INFORMATIONAL_STATEMENT = "info_statement"   # "I have the timetable" -> NEVER sends media!
    DEVICE_QUERY = "device_query"                # "What is running on port 8080"
    GENERAL_CONVERSATION = "general_chat"


class IntentEngine:
    """Classifies user intent before any action is executed."""

    @staticmethod
    def classify(text: str) -> Dict[str, Any]:
        """
        Extract intent, target entities, and parameters from incoming message text.
        """
        if not text:
            return {"intent": MessageIntent.GENERAL_CONVERSATION, "target": "", "params": {}}

        t_low = text.lower().strip()

        # 0. USER_CORRECTION ("You are telling that wrong", "That is false information", "You are wrong")
        correction_patterns = [
            "telling that wrong", "telling me wrong", "you are wrong", "you're wrong",
            "that is wrong", "that's wrong", "this is wrong", "it is wrong", "it's wrong",
            "false information", "that is false", "that's false", "you are lying",
            "not correct", "that is incorrect", "that's incorrect", "you made a mistake",
            "accept the mistake", "wrong answer", "incorrect answer"
        ]
        if any(p in t_low for p in correction_patterns):
            return {
                "intent": MessageIntent.USER_CORRECTION,
                "target": text,
                "params": {"correction_text": text},
            }

        # 1. RENAME_MEDIA_OR_DOCUMENT
        # Handles user saying: "Name of the image is Rohit", "The image name is Rohit",
        # "This is naveen image save the photo name as naveen", "it is rohit", "save as rohit", "Rohit images save it"
        from .media_manager import extract_media_subject
        extracted_name = extract_media_subject(t_low)
        is_rename_syntax = bool(re.search(
            r"(?:name\s+of\s+(?:the\s+)?(?:image|photo|pic|file|document)\s+is|the\s+(?:image|photo|pic|file|document)\s+name\s+is|name\s+is|rename|save\s+(?:the\s+)?(?:photo|image|pic|file|pdf|document)\s+name\s+as|save\s+(?:the\s+photo\s+)?as|it\s+is|this\s+is|this\s+photo\s+is)",
            t_low,
        )) or bool(re.search(r"^[a-zA-Z0-9\s]+?\s+(?:images?|photos?|pics?)\s+save", t_low))

        if extracted_name and is_rename_syntax:
            return {
                "intent": MessageIntent.RENAME_MEDIA_OR_DOCUMENT,
                "target": extracted_name,
                "params": {"new_name": extracted_name},
            }

        rename_match = re.search(
            r"(?:this is\s+([a-zA-Z0-9\s]+?)\s+(?:image|photo|pic|document|pdf)\s+)?(?:save\s+(?:the\s+)?(?:photo|image|pic|file|pdf|document)\s+name\s+as|rename\s+(?:it|this|the\s+photo|the\s+image|the\s+file|the\s+pdf)?\s+(?:to|as)?|name\s+(?:it|this)?\s+as)\s+([a-zA-Z0-9_\-\.\s]+)",
            t_low,
        )
        if rename_match:
            candidate_name = (rename_match.group(2) or rename_match.group(1) or "").strip()
            # Clean up trailing punctuation
            candidate_name = re.sub(r"[\.,!?]+$", "", candidate_name).strip()
            return {
                "intent": MessageIntent.RENAME_MEDIA_OR_DOCUMENT,
                "target": candidate_name,
                "params": {"new_name": candidate_name},
            }

        # Also check "This is naveen image save it" or "Rohit images save it"
        this_is_match = re.search(r"(?:this is\s+)?([a-zA-Z0-9]+)\s+(?:images?|photos?|pics?)\s+save", t_low)
        if this_is_match:
            person = this_is_match.group(1).strip().title()
            return {
                "intent": MessageIntent.RENAME_MEDIA_OR_DOCUMENT,
                "target": person,
                "params": {"new_name": person},
            }

        # 2. SAVE_MEDIA_CONFIRM
        # Handles "save that", "save in memory", "save this image" without a rename instruction
        if any(p in t_low for p in ["save that", "save it", "save in memory", "save to memory", "store it", "keep it"]) and not any(w in t_low for w in ["send", "share", "give", "back"]):
            return {
                "intent": MessageIntent.SAVE_MEDIA_CONFIRM,
                "target": "",
                "params": {},
            }

        # 3. ASK_DATE_TIME ("What date is today?", "What is the time in Japan?", "Time in Tokyo")
        time_triggers = [
            "what date is today", "what is today's date", "what's the date", "what date",
            "what time is it", "what is the time", "current time", "what day is today",
            "what day is it", "tell me the time", "tell me the date", "time now",
        ]
        is_time_query = any(p in t_low for p in time_triggers) or re.search(r"\btime\s+(?:in|at|of)\b", t_low)
        if is_time_query:
            from .tools import get_time_for_location
            loc_time = get_time_for_location(text)
            loc_name = loc_time.get("location_matched", "") if loc_time else ""
            return {
                "intent": MessageIntent.ASK_DATE_TIME,
                "target": loc_name,
                "params": {"location": loc_name, "has_specific_location": bool(loc_name)},
            }

        # 4. ASK_SCHEDULE_LOCATION ("Where is David?", "Where is David at 10:30 Monday?")
        loc_match = re.search(r"where\s+is\s+david(?:\s+(?:at|on)\s+([a-zA-Z0-9:\s]+))?", t_low)
        if loc_match or any(p in t_low for p in ["where is david", "where is he now", "what class does david have", "what is david's schedule"]):
            time_spec = loc_match.group(1).strip() if loc_match and loc_match.group(1) else ""
            return {
                "intent": MessageIntent.ASK_SCHEDULE_LOCATION,
                "target": "David Julius",
                "params": {"time_spec": time_spec},
            }

        # 5. INFORMATIONAL_STATEMENT ("I have the exam timetable", "I have the notes")
        # STRICT: Must NOT trigger send_document()
        if re.search(r"\b(?:i|we)\s+have\s+(?:the\s+)?(?:exam\s+)?(?:timetable|notes|pdf|document|assignment|tutorial)\b", t_low) and not any(w in t_low for w in ["send", "share", "give", "forward"]):
            return {
                "intent": MessageIntent.INFORMATIONAL_STATEMENT,
                "target": "",
                "params": {},
            }

        # 6. ASK_PERSON_INFO ("Who is Alex?", "Who is Alexander?", "Tell me about Dave")
        # STRICT: Must NEVER trigger send_image()
        who_match = re.search(r"(?:who\s+is|tell\s+me\s+about|do\s+you\s+know)\s+([a-zA-Z0-9\s]+?)(?:\?|$)", t_low)
        if who_match and not any(w in t_low for w in ["send", "show", "give", "share", "photo", "image", "pic"]):
            person = who_match.group(1).strip()
            # Distinguish team peer from outside famous entity
            from .config import TARGET_PEERS_CONFIG
            known_peers = [tok for p in TARGET_PEERS_CONFIG for tok in p.get("tokens", [])]
            if any(kp in person.lower() for kp in known_peers):
                return {
                    "intent": MessageIntent.ASK_PERSON_INFO,
                    "target": person,
                    "params": {"person": person},
                }
            else:
                # Outside person -> live web search
                return {
                    "intent": MessageIntent.ASK_EXTERNAL_INFO,
                    "target": text,
                    "params": {"query": text},
                }

        # 6.8 SEND_VIDEO ("Send Sumanth video", "Send the video", "Share that video", "Give sumanth video")
        send_vid_match = re.search(
            r"(?:send|sene|sned|snd|share|give|show|attach|play)\s+(?:me\s+)?(?:the\s+)?([a-zA-Z0-9\s,]+?)?(?:'s)?\s*(?:video|vid|clip|recording|mp4)\b",
            t_low,
        )
        is_explicit_video_req = bool(send_vid_match) or any(p in t_low for p in [
            "send the video", "send video", "send me the video", "send me video",
            "send sumanth video", "send naveen video", "send gova video", "send rohit video",
            "send me sumanth video", "send me naveen video", "send that video", "share the video",
            "share video", "give the video", "give me the video", "video send", "send vid",
        ])
        if is_explicit_video_req:
            target_str = ""
            if "rohit" in t_low:
                target_str = "Rohit"
            elif "naveen" in t_low or "navin" in t_low:
                target_str = "Naveen"
            elif "sumanth" in t_low:
                target_str = "Sumanth"
            elif "gova" in t_low or "govardhan" in t_low:
                target_str = "Gova"
            elif "david" in t_low:
                target_str = "David Julius"
            elif "chandhru" in t_low or "chandru" in t_low:
                target_str = "Chandhru"
            elif "latchuman" in t_low:
                target_str = "Latchuman"
            elif send_vid_match and send_vid_match.group(1):
                raw = send_vid_match.group(1).strip()
                clean = re.sub(r"\b(please|me|the|that|this)\b", "", raw).strip(" ,")
                target_str = clean.title() if clean else ""

            return {
                "intent": MessageIntent.SEND_VIDEO,
                "target": target_str,
                "params": {"person": target_str, "query": text},
            }

        # 7. SEND_PERSON_IMAGE ("Send Naveen's image", "Sene me the image", "Send Rohit photo")
        send_img_match = re.search(
            r"(?:send|sene|sned|snd|share|give|show|attach)\s+(?:me\s+)?(?:the\s+)?([a-zA-Z0-9\s,]+?)?(?:'s)?\s*(?:photo|image|pic|picture|snap)\b",
            t_low,
        )
        is_explicit_image_req = bool(send_img_match) or any(p in t_low for p in [
            "send the photo", "send photo", "send image", "send me the photo",
            "send me sumanth photo", "send me naveen photo", "send sumanth photo", "send naveen photo",
            "send me rohit photo", "send rohit photo", "send me rohit image", "send rohit image",
            "sene me the image", "sene me image", "sene the image", "sene image", "sene photo",
            "send me the image", "send me image", "send the image",
        ])
        if is_explicit_image_req:
            # Check if user specifically requested sending as a document
            as_document = any(p in t_low for p in ["as document", "in document", "as doc", "in doc"])

            # Resolve target person prioritizing known tokens over loose regex captures
            target_str = ""
            if "rohit" in t_low:
                target_str = "Rohit"
            elif "naveen" in t_low or "navin" in t_low:
                target_str = "Naveen"
            elif "sumanth" in t_low:
                target_str = "Sumanth"
            elif "gova" in t_low or "govardhan" in t_low:
                target_str = "Gova"
            elif "david" in t_low:
                target_str = "David Julius"
            elif "chandhru" in t_low or "chandru" in t_low:
                target_str = "Chandhru"
            elif "latchuman" in t_low:
                target_str = "Latchuman"
            elif send_img_match and send_img_match.group(1):
                raw = send_img_match.group(1).strip()
                # Clean noise phrases
                clean = re.sub(r"\b(in normal format|normal format|normal|please|me|the)\b", "", raw).strip(" ,")
                target_str = clean.title() if clean else ""

            return {
                "intent": MessageIntent.SEND_PERSON_IMAGE,
                "target": target_str,
                "params": {"person": target_str, "as_document": as_document},
            }

        # 8. SEND_DOCUMENT ("Send the timetable PDF", "Send physics notes", "Give me the tutorial PDF")
        if any(w in t_low for w in ["send", "share", "give", "forward", "attach"]) and any(w in t_low for w in ["pdf", "timetable", "notes", "tutorial", "assignment", "doc", "document", "routine"]):
            return {
                "intent": MessageIntent.SEND_DOCUMENT,
                "target": text,
                "params": {"query": text},
            }

        # 9. DEVICE_QUERY
        from .device_agent import is_device_query
        if is_device_query(text):
            return {
                "intent": MessageIntent.DEVICE_QUERY,
                "target": "",
                "params": {},
            }

        # 10. ASK_EXTERNAL_INFO ("weather in chennai", "news", "search online", "who is the ceo of...", "what is ...")
        external_triggers = [
            "weather in", "search online", "search internet", "current news", "latest news", "price of",
            "check online", "check internet", "google", "look up", "capital of", "who is the prime minister",
            "who is the president", "who won", "score of", "definition of", "what is the capital"
        ]
        if any(p in t_low for p in external_triggers) or (t_low.startswith("what is ") and not any(w in t_low for w in ["timetable", "schedule", "class", "david", "date", "time"])):
            return {
                "intent": MessageIntent.ASK_EXTERNAL_INFO,
                "target": text,
                "params": {"query": text},
            }

        return {
            "intent": MessageIntent.GENERAL_CONVERSATION,
            "target": "",
            "params": {},
        }

    def classify_intent(self, text: str, chat_name: str = "") -> tuple[MessageIntent, Dict[str, Any]]:
        """Convenience method returning (intent, params)."""
        res = self.classify(text)
        return res["intent"], res.get("params", {})

