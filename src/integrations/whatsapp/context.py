"""
Julius WhatsApp Integration — Conversation Context Manager.

Manages per-chat conversation context with sliding window
and rolling summaries for efficient LLM prompting.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Dict, List, Optional

from .media_manager import get_media_manager
from .models import ChatConfig, ContactProfile, StyleProfile, WhatsAppMessage
from .storage import WhatsAppStorage

logger = logging.getLogger(__name__)

# Regex for Tamil Unicode block (U+0B80 to U+0BFF)
TAMIL_SCRIPT_REGEX = re.compile(r"[\u0B80-\u0BFF]")

# Vocabulary for distinct Tamil/Tanglish words in Latin script
TANGLISH_VOCAB_REGEX = re.compile(
    r"\b("
    r"machi|machan|thala|thalaiva|nanba|dei|"
    r"enna|ethu|enge|enga|epdi|eppadi|eppudi|"
    r"panra|panre|pannura|pannuringa|senja|panren|"
    r"iruka|irukka|irukken|irukkinga|irukku|"
    r"solra|solre|sollu|sollunga|sonna|"
    r"sapdiya|saaptiya|saapadu|sapten|"
    r"aama|aamanda|illa|illada|illai|"
    r"seri|serida|podhum|podhumda|"
    r"vanthuten|varen|pore|poren|poriya|"
    r"padichiya|mudinjutha|mudichitiya|"
    r"semma|paaru|theriyum|theriyathu|puriyala|purinjutha|"
    r"nalla|nallaa|kelambu|kelambiten|seekiram"
    r")\b",
    re.IGNORECASE,
)


def detect_preferred_language(text: str) -> str:
    """
    Detect whether the incoming message is Tamil script, Tanglish, or default English.

    Policy:
    - If Tamil script is present -> 'tamil'
    - If Tanglish words are present -> 'tanglish'
    - Default is 'english'
    """
    if not text:
        return "english"

    if TAMIL_SCRIPT_REGEX.search(text):
        return "tamil"

    if TANGLISH_VOCAB_REGEX.search(text):
        return "tanglish"

    return "english"

from pathlib import Path

def get_media_manifest_prompt_section() -> str:
    """
    Build a live, dynamically rescanned manifest of available images, documents, and
    videos in the shared common workspace for the LLM's system prompt instructions.
    """
    from .media_manager import get_media_manager
    from .materials import list_all_data_files

    media_mgr = get_media_manager()
    inventory = media_mgr.get_dynamic_inventory(force_rescan=True)

    img_descriptions = []
    seen_fnames = set()
    for it in inventory.get("images", []):
        fname = it.get("filename", "")
        if not fname or fname in seen_fnames:
            continue
        seen_fnames.add(fname)
        ents = [e for e in it.get("entities", []) if e and e.lower() not in ("photo", "image")]
        desc = it.get("title") or it.get("caption") or (", ".join(ents) if ents else "Photo")
        ent_str = f" [Person/Subject: {', '.join(ents)}]" if ents else ""
        img_descriptions.append(f"- {fname} -> {desc}{ent_str}")

    doc_descriptions = []
    seen_docs = set()
    # First include dynamically discovered and received documents
    for it in inventory.get("documents", []):
        fname = it.get("filename", "")
        if not fname or fname in seen_docs:
            continue
        seen_docs.add(fname)
        title = it.get("title") or fname
        cat = it.get("category", "document")
        doc_descriptions.append(f"- {fname} -> {title} ({cat.title()})")

    # Merge static materials if any remain unlisted
    doc_files = list_all_data_files()
    for f in doc_files:
        if f.get("type") in [".pdf", ".docx", ".xlsx", ".pptx", ".doc"]:
            fname = f["name"]
            if fname in seen_docs:
                continue
            seen_docs.add(fname)
            fn_low = fname.lower()
            if "assessment" in fn_low or "ca 1" in fn_low or "cat" in fn_low:
                role = "CAT 1 Assessment/Exam Test Timetable"
            elif "first_semester" in fn_low:
                role = "First Semester Class Routine / Timetable"
            elif "batch2" in fn_low:
                role = "IT Batch 2 Class Timetable"
            elif "physics" in fn_low:
                role = "Engineering Physics Notes (PH23C11)"
            else:
                role = "Academic Document"
            doc_descriptions.append(f"- {fname} -> {role}")

    vid_descriptions = []
    seen_vids = set()
    for it in inventory.get("videos", []):
        fname = it.get("filename", "")
        if not fname or fname in seen_vids:
            continue
        seen_vids.add(fname)
        ents = [e for e in it.get("entities", []) if e and e.lower() not in ("video", "vid")]
        desc = it.get("title") or (", ".join(ents) if ents else "Video")
        sender = it.get("sender", "David Julius")
        sender_str = f" [From: {sender}]" if sender else ""
        vid_descriptions.append(f"- {fname} -> {desc}{sender_str}")

    manifest_lines = [
        "COMMON WORKSPACE MEMORY & AVAILABLE MEDIA INVENTORY:",
        "All media and files belong to a SHARED workspace accessible across all chats and contacts.",
        "If one colleague sends a video or document, and another asks for it, send it directly from the common workspace inventory!",
        "",
        "1. Images Folder: materials/received_media/images/",
        "   Available Photos:",
    ]
    if img_descriptions:
        manifest_lines.extend("   " + d for d in img_descriptions[:15])
    else:
        manifest_lines.append("   (No photos currently in workspace memory)")

    manifest_lines.extend([
        "",
        "2. Documents Folder: materials/received_media/documents/",
        "   Available Documents:",
    ])
    if doc_descriptions:
        manifest_lines.extend("   " + d for d in doc_descriptions[:15])
    else:
        manifest_lines.append("   (No documents currently in workspace memory)")

    manifest_lines.extend([
        "",
        "3. Videos Folder: materials/received_media/videos/",
        "   Available Videos:",
    ])
    if vid_descriptions:
        manifest_lines.extend("   " + d for d in vid_descriptions[:15])
    else:
        manifest_lines.append("   (No videos currently in workspace memory)")

    manifest_lines.extend([
        "",
        "ACTION INSTRUCTION & JSON RESPONSE SCHEMA:",
        "You have autonomous intelligence to decide whether to SEND AN IMAGE, SEND A VIDEO, SEND A DOCUMENT, RENAME/SAVE MEDIA, or JUST CHAT.",
        "NEVER prefix replies with 'REPLY:' or quotes. Output natural conversation in reply_text.",
        "You MUST respond ONLY with a valid JSON object matching this schema:",
        "```json",
        "{",
        '  "thought": "1 short sentence explaining your decision based on the available files and the user\'s message",',
        '  "action": "SEND_IMAGE" | "SEND_VIDEO" | "SEND_DOCUMENT" | "RENAME_MEDIA" | "SAVE_MEDIA" | "REPLY",',
        '  "action_params": {',
        '    "file_path": "filename from Available Photos, Documents, or Videos (e.g. sample_photo.jpg, demo_video.mp4, project_schedule.pdf)",',
        '    "new_name": "person or subject name to save/rename recent media (e.g. SamplePhoto)",',
        '    "media_type": "image" | "video" | "document"',
        "  },",
        '  "reply_text": "your natural, authentic message to send to your friend on WhatsApp (1-2 sentences in casual English, without any \\"REPLY:\\" prefix)"',
        "}",
        "```",
        "",
        "HOW TO CHOOSE THE RIGHT ACTION:",
        "• ACTION 'SEND_IMAGE':",
        "  - Use when the friend asks to send a photo/image (e.g. 'send me the image', 'send Alex photo', 'show me team photo').",
        "  - Look at the Available Photos list!",
        "  - If requested photo exists (e.g. 'alex.jpg' for Alex, or recent photo for 'the image'):",
        "    set action='SEND_IMAGE', action_params={'file_path': 'alex.jpg', 'media_type': 'image'}, reply_text='Here is the photo 📸'.",
        "  - If requested photo does NOT exist:",
        "    set action='REPLY' and reply_text='I don\\'t have that photo in workspace memory yet. If you send it, I\\'ll save and index it right away!'.",
        "• ACTION 'SEND_VIDEO':",
        "  - Use when the friend asks to send a video (e.g. 'send the demo video', 'send the video', 'give that video').",
        "  - Look at the Available Videos list! If requested video exists in the common workspace (e.g. 'demo_video.mp4'):",
        "    set action='SEND_VIDEO', action_params={'file_path': 'demo_video.mp4', 'media_type': 'video'}, reply_text='Here is the video 🎥'.",
        "  - If requested video does NOT exist in workspace memory:",
        "    set action='REPLY' and reply_text='I don\\'t have that video in workspace memory yet. If you send it, I\\'ll save and index it right away!'.",
        "• ACTION 'SEND_DOCUMENT':",
        "  - Use when the friend asks for a PDF/document (e.g. 'send assessment timetable', 'send timetable pdf', 'physics notes').",
        "  - If CAT/assessment/exam timetable is asked: file_path='Schedule for First Assessment Test -16.09.2026.pdf'.",
        "  - If regular semester timetable is asked: file_path='First_Semester_Timetable_2026.pdf'.",
        "  - set action='SEND_DOCUMENT', action_params={'file_path': '<filename>', 'media_type': 'document'}, reply_text='Here is the document bro 📄'.",
        "• ACTION 'RENAME_MEDIA' or 'SAVE_MEDIA':",
        "  - Use when the friend tells you who or what media is (e.g. 'Rohit images save it', 'Name of the image is Rohit', 'it is rohit', 'save as rohit').",
        "  - set action='RENAME_MEDIA', action_params={'new_name': 'Rohit'}, reply_text='Got it! 📸 Saved and indexed as \\'Rohit\\' in workspace memory. Ready whenever anyone asks 👍'.",
        "• ACTION 'REPLY':",
        "  - Use for normal casual conversation, greetings, questions, or when a requested file doesn't exist.",
        "  - set action='REPLY', reply_text='<natural friendly text in casual English without REPLY prefix>'.",
    ])
    return "\n".join(manifest_lines)


class ConversationContext:
    """
    Per-chat conversation context manager.

    Assembles the context window for LLM prompting:
    - Recent messages (configurable window)
    - Rolling conversation summary
    - Per-chat memory (facts, topics, questions)
    - User style profile
    """

    def __init__(self, storage: WhatsAppStorage) -> None:
        self._storage = storage

    def build_context(
        self,
        message: WhatsAppMessage,
        chat_config: ChatConfig,
        style_profile: Optional[StyleProfile] = None,
    ) -> Dict[str, Any]:
        """
        Build the full context dict for LLM prompting.

        Returns:
            {
                "current_message": {...},
                "recent_messages": [...],
                "conversation_summary": "...",
                "memory": {...},
                "style_profile": {...},
                "chat_config": {...},
            }
        """
        # Get recent messages by chat_name or chat_id
        window_size = chat_config.context_window
        recent = self._storage.get_recent_messages(message.chat_name, limit=window_size)
        if not recent and message.chat_id:
            recent = self._storage.get_recent_messages(message.chat_id, limit=window_size)

        # Exclude the current incoming message if already in recent_messages
        clean_recent = []
        for r in recent:
            if r.get("id") == message.id:
                continue
            if not r.get("is_from_me") and r.get("text", "").strip() == message.text.strip():
                if abs(float(r.get("timestamp", 0)) - message.timestamp) < 10.0:
                    continue
            clean_recent.append(r)

        # Get conversation summary
        summary_data = self._storage.get_conversation_summary(message.chat_id) or self._storage.get_conversation_summary(message.chat_name)

        # Retrieve dynamic contact profile (learned continuously from chats)
        contact_prof = self._storage.get_contact_profile(message.chat_name)

        # Check for mutual peer inquiry (Interconnected Social Graph)
        peer_query_match = re.search(
            r"(?:where is|where's|enga|did|have you seen|what is|how is)\s+([A-Za-z]+)",
            message.text,
            re.IGNORECASE,
        )
        mutual_peer_info = None
        if peer_query_match:
            cand = peer_query_match.group(1).strip()
            if cand.lower() not in ("you", "u", "he", "she", "it", "they", "this", "that", "the", "your", "ur"):
                mutual_peer_info = self._storage.find_peer_status(cand)
        else:
            # Also check for presence of known peer names in the text
            from .config import TARGET_PEERS_CONFIG
            known_peer_tokens = [tok for p in TARGET_PEERS_CONFIG for tok in p.get("tokens", [])]
            txt_lower = message.text.lower()
            for tok in known_peer_tokens:
                # Disambiguation: alex must not match inside alexander
                if tok == "alex" and "alexander" in txt_lower:
                    continue
                # Use word-boundary matching
                if re.search(r"\b" + re.escape(tok) + r"\b", txt_lower) and tok not in message.chat_name.lower():
                    mutual_peer_info = self._storage.find_peer_status(tok)
                    if mutual_peer_info:
                        break

        # Structured Per-Person Knowledge Graph (from whatsapp_person_memories)
        person_memories = self._storage.search_relevant_memories(
            chat_name=message.chat_name,
            query=message.text,
            limit=8,
        )

        # Conversation State (NEW, ACTIVE, ENDING, ENDED, REOPENED, etc.)
        conv_state = self._storage.get_conversation_state(message.chat_name)

        # Build context
        context = {
            "current_message": {
                "sender": message.sender_name,
                "text": message.text,
                "is_group": message.is_group,
                "chat_name": message.chat_name,
                "quoted_text": message.quoted_text,
            },
            "recent_messages": self._format_recent_messages(clean_recent),
            "conversation_summary": summary_data.get("summary", "") if summary_data else "",
            "memory": {
                "important_facts": summary_data.get("important_facts", []) if summary_data else [],
                "ongoing_topics": summary_data.get("ongoing_topics", []) if summary_data else [],
                "pending_questions": summary_data.get("pending_questions", []) if summary_data else [],
                "relationship_label": summary_data.get("relationship_label", "") if summary_data else "",
            },
            "contact_profile": contact_prof.to_dict() if contact_prof else None,
            "person_memories": [m.to_dict() for m in person_memories],
            "conversation_state": conv_state.to_dict() if conv_state else None,
            "mutual_peer_info": mutual_peer_info,
            "style_profile": style_profile.to_dict() if style_profile else {},
            "chat_config": {
                "mode": chat_config.mode.value,
                "persona": chat_config.persona,
                "response_style": chat_config.response_style,
            },
        }

        return context

    def build_prompt(
        self,
        message: WhatsAppMessage,
        chat_config: ChatConfig,
        style_profile: Optional[StyleProfile] = None,
    ) -> str:
        """
        Build the complete LLM prompt for generating a WhatsApp reply.

        Returns a structured prompt string.
        """
        ctx = self.build_context(message, chat_config, style_profile)
        return self.build_prompt_from_ctx(message, chat_config, style_profile, ctx)

    def build_prompt_from_ctx(
        self,
        message: WhatsAppMessage,
        chat_config: ChatConfig,
        style_profile: Optional[StyleProfile],
        ctx: Dict[str, Any],
    ) -> str:
        """
        Build the complete LLM prompt from a pre-built context dict.
        Avoids duplicate DB lookups when context is already built.
        """
        friend_name = message.sender_name or message.chat_name

        # Exact time awareness using Asia/Kolkata tools layer
        from .tools import get_current_datetime
        dt_info = get_current_datetime("Asia/Kolkata")
        hour = dt_info["hour"]
        if 5 <= hour < 9:
            time_context = "early morning — probably just woke up, getting ready for class"
        elif 9 <= hour < 13:
            time_context = "morning — likely in class or lab at MIT campus"
        elif 13 <= hour < 15:
            time_context = "afternoon — lunch break, maybe at canteen or back in hostel"
        elif 15 <= hour < 17:
            time_context = "afternoon — probably in lab or free period, might be coding or studying"
        elif 17 <= hour < 20:
            time_context = "evening — back in hostel room, tea time, free time"
        elif 20 <= hour < 23:
            time_context = "night — in hostel room, studying or just chilling with roommates"
        else:
            time_context = "late night — probably in bed, scrolling phone, or working on Julius"

        lines = [
            f"You are Julius, chatting with your contact {friend_name} on WhatsApp.",
            f"CURRENT DATE & TIME (IST): {dt_info['formatted']}",
            "",
            "WHO YOU ARE & YOUR ROLE:",
            "You are Julius WhatsApp Assistant, representing the user in peer communication and scheduling.",
            "Known team / peer contacts: Contact Alex (Engineering), Contact Alexander (Product), Contact Charlie (Operations), Contact Dave (Design), Contact Grace (Software).",
            f"Right now it's {time_context}.",
            "",
        ]

        # Dynamic Per-Contact Memory
        if ctx.get("contact_profile"):
            cp = ctx["contact_profile"]
            lines.append(f"ABOUT {friend_name.upper()} (DYNAMIC PROFILE FOR {friend_name.upper()}):")
            if cp.get("contact_type"):
                lines.append(f"- {cp.get('contact_type', 'college friend')}")
            if cp.get("slang_used"):
                lines.append(f"- Uses slangs like: {', '.join(cp['slang_used'])} — match his vibe naturally")
            if cp.get("favorite_topics"):
                lines.append(f"- Usually talks about: {', '.join(cp['favorite_topics'])}")
            if cp.get("important_facts"):
                for fact in cp['important_facts'][:5]:
                    lines.append(f"- {fact}")
            lines.append("")

        # Structured Evidence-Based Knowledge Graph
        if ctx.get("person_memories"):
            lines.append(f"STRUCTURED KNOWLEDGE & EVIDENCE-BASED FACTS ABOUT {friend_name.upper()}:")
            for mem in ctx["person_memories"]:
                status_tag = mem.get("status", "current").upper()
                fact = mem.get("fact", "")
                conf = mem.get("confidence", 1.0)
                if status_tag == "CURRENT":
                    lines.append(f"- [CONFIRMED CURRENT] {fact} (confidence: {conf:.2f})")
                elif status_tag == "HISTORICAL":
                    lines.append(f"- [HISTORICAL PAST] {fact} (Past info only; do not confuse with current situation)")
                elif status_tag == "PLANNED":
                    lines.append(f"- [PLANNED/TENTATIVE] {fact} (Future/intended, not current reality)")
                elif status_tag == "SUPERSEDED":
                    lines.append(f"- [SUPERSEDED] {fact} (Obsolete; do NOT assert as true)")
                elif status_tag == "UNCERTAIN":
                    lines.append(f"- [UNCERTAIN] {fact} (Inference; verify casually if relevant, do not assume)")
            lines.append("")

        # Conversation State (Ending awareness)
        c_state = ctx.get("conversation_state")
        if c_state and c_state.get("state") in ("ENDING", "ending"):
            lines.append("CONVERSATION STATE: ENDING")
            lines.append(f"The contact ({friend_name}) is ending or wrapping up the chat (e.g. said '{c_state.get('termination_phrase', 'bye')}').")
            lines.append("Reply with a short, warm, natural farewell (e.g. 'ok da bye', 'see you later', 'take care'). DO NOT ask questions or bring up new topics.")
            lines.append("")

        # Mutual Peer Context
        if ctx.get("mutual_peer_info"):
            mp = ctx["mutual_peer_info"]
            lines.append(f"MUTUAL PEER SOCIAL CONTEXT: {friend_name} is asking about {mp['peer_name']}.")
            if mp.get("status"):
                lines.append(f"You know {mp['peer_name']} was recently: {mp['status']}")
            lines.append("Mention it casually, don't over-explain.")
            lines.append("")

        # Conversation summary + memory
        if ctx["conversation_summary"]:
            lines.append(f"RECENT CONTEXT: {ctx['conversation_summary'][:400]}")
            lines.append("")

        if ctx["memory"].get("important_facts"):
            lines.append(f"THINGS YOU KNOW: {', '.join(ctx['memory']['important_facts'][:6])}")
            lines.append("")

        # Recent messages
        if ctx["recent_messages"]:
            lines.append("CONVERSATION SO FAR:")
            for msg in ctx["recent_messages"][-15:]:
                prefix = "You" if msg.get("is_from_me") else msg.get("sender", friend_name)
                lines.append(f"  {prefix}: {msg.get('text', '')}")
            lines.append("")

        # Current message
        current = ctx["current_message"]
        lines.append(f"→ {friend_name}: {current['text']}")
        if current["quoted_text"]:
            lines.append(f"  (replying to: {current['quoted_text'][:100]})")
        lines.append("")

        lines.append("HOW TO REPLY:")
        lines.append("- Be yourself. Short, casual, natural. Like texting your actual friend.")
        lines.append("- 1-2 sentences max. Lowercase okay. Use emojis naturally (👍😅🔥) not excessively.")
        lines.append("- If they ask 'what are you doing/where are you': answer realistically based on the time of day above.")
        lines.append("- If they ask 'why no reply': say something friendly like 'got caught up in code' or 'phone was away while compiling'.")
        lines.append("- If they ask something you genuinely don't know the answer to: say 'not sure let me check' or similar.")
        lines.append("- LANGUAGE POLICY: CONVERSE EXCLUSIVELY IN CASUAL ENGLISH. Understand colloquial expressions, but ALWAYS reply in casual, friendly English.")
        lines.append("- ANTI-HALLUCINATION & GROUNDING (STRICT): NEVER invent facts, files, or images. Every factual claim must come from verified context, database, or tool results. If information is not in verified sources, state that you don't have it.")
        lines.append("- SCHEDULED VS REAL LOCATION: Never claim the user is physically somewhere based only on a timetable. State: 'According to the schedule, they are set for...'")
        lines.append("- IDENTITY & INTENT SEPARATION: Purely informational queries must NEVER trigger media/file sending! Only send an image or document when explicitly requested.")
        lines.append("- NO CROSS-PERSON SUBSTITUTION: Never substitute someone else's photo or document if the requested person's image is not found. State that no verified photo is available.")
        lines.append("- NO ACCIDENTAL SENDS: Mentioning a document (e.g. 'I have the timetable') must NEVER trigger a send action. Only execute [SEND_FILE: ...] on explicit commands to send/share.")
        lines.append("- NO corporate AI speak. NO 'Certainly!' or 'How can I assist?'")
        lines.append("- NO vulgarity or swear words.")
        lines.append("- MESSAGE REACTIONS (EMOJIS) WITH MEANING & CONTEXT: [REACT: emoji] only when it genuinely fits.")
        lines.append("- GIFS & STICKERS (WITH MEANING AND CONTEXT ONLY): [GIF: query], or sticker: [STICKER].")
        lines.append("- FULL PERMISSION TO RECEIVE & SAVE MEDIA: You have 100% permission to save all photos, images, PDFs, timetables, and documents from your friends into David Julius's data folder (workspace memory). If anyone asks if you can save an image/file (e.g. 'can you save that image into David Julius data folder?'), ALWAYS say YES warmly and invite them to send it over! NEVER say the folder is read-only or external images cannot be saved.")
        lines.append("- SAVING CONFIRMATION: When someone sends an image or tells you to save something (e.g. 'save that', 'save it in your memory'), confirm warmly that it is saved and indexed in workspace memory ready for David or anyone who asks.")
        lines.append("")
        lines.append(get_media_manifest_prompt_section())
        lines.append("")
        lines.append("- If the message doesn't need a reply (like someone just reacting, or a forwarded broadcast), respond with [NO_RESPONSE].")
        lines.append("- Output ONLY the structured JSON response schema specified above. Nothing else.")

        return "\n".join(lines)

    def update_summary(
        self,
        chat_id: str,
        summary: str,
        important_facts: Optional[List[str]] = None,
        ongoing_topics: Optional[List[str]] = None,
        pending_questions: Optional[List[str]] = None,
        relationship_label: str = "",
    ) -> None:
        """Update the rolling conversation summary for a chat."""
        self._storage.save_conversation_summary(
            chat_id=chat_id,
            summary=summary,
            important_facts=important_facts,
            ongoing_topics=ongoing_topics,
            pending_questions=pending_questions,
            relationship_label=relationship_label,
        )

    def clear_memory(self, chat_id: str) -> None:
        """Clear all conversation memory for a chat."""
        self._storage.clear_conversation_memory(chat_id)
        logger.info("Cleared conversation memory for chat %s", chat_id)

    def build_chat_messages(
        self,
        message: WhatsAppMessage,
        chat_config: ChatConfig,
        style_profile: Optional[StyleProfile] = None,
    ) -> List[Dict[str, str]]:
        """
        Build a structured list of {role, content} dicts for OpenAI-compatible
        chat completion APIs.
        """
        ctx = self.build_context(message, chat_config, style_profile)
        return self.build_chat_messages_from_ctx(message, chat_config, style_profile, ctx)

    def build_chat_messages_from_ctx(
        self,
        message: WhatsAppMessage,
        chat_config: ChatConfig,
        style_profile: Optional[StyleProfile],
        ctx: Dict[str, Any],
    ) -> List[Dict[str, str]]:
        """
        Build structured chat messages from a pre-built context dict.
        Avoids duplicate DB lookups when context is already built.

        Returns a proper multi-turn conversation:
        - system: persona + rules + context knowledge
        - user/assistant alternating: recent conversation history
        - user: the latest incoming message to reply to
        """
        friend_name = message.sender_name or message.chat_name

        current_text = message.text or ""

        # Exact time awareness using Asia/Kolkata tools layer
        from .tools import get_current_datetime
        dt_info = get_current_datetime("Asia/Kolkata")
        hour = dt_info["hour"]
        if 5 <= hour < 9:
            time_vibe = "early morning, probably just woke up or getting ready for class"
        elif 9 <= hour < 13:
            time_vibe = "morning, likely in class or lab at MIT"
        elif 13 <= hour < 15:
            time_vibe = "afternoon, lunch time, maybe at canteen or hostel"
        elif 15 <= hour < 17:
            time_vibe = "afternoon, in lab/free period, maybe coding or studying"
        elif 17 <= hour < 20:
            time_vibe = "evening, back in hostel, tea time, relaxing"
        elif 20 <= hour < 23:
            time_vibe = "night, in hostel room, studying or chilling"
        else:
            time_vibe = "late night, in bed scrolling phone or working on Julius"

        # ── System message ──
        system_parts = [
            f"You are Julius WhatsApp Assistant, an intelligent, helpful agent chatting with {friend_name} on behalf of the user.",
            f"EXACT CURRENT DATE & TIME (IST): {dt_info['formatted']}",
            "",
            "COLLABORATOR & PEER CIRCLE:",
            "- Contact Alex: Engineering Team (Room 101)",
            "- Contact Alexander: Product Team (distinct collaborator from Alex)",
            "- Contact Charlie: Operations / Classmate (Room 102)",
            "- Contact Dave: Design Team (Room 103)",
            "- Contact Grace: Software Team (Room 104)",
            f"- Right now: {time_vibe}.",
        ]

        # Dynamic per-contact knowledge
        if ctx.get("contact_profile"):
            cp = ctx["contact_profile"]
            system_parts.append("")
            system_parts.append(f"ABOUT {friend_name.upper()} (DYNAMIC PROFILE FOR {friend_name.upper()}):")
            if cp.get("contact_type"):
                system_parts.append(f"- Type: {cp['contact_type']}")
            if cp.get("tone_style"):
                system_parts.append(f"- Vibe: {cp['tone_style']}")
            if cp.get("slang_used"):
                system_parts.append(f"- Uses: {', '.join(cp['slang_used'])} — match his energy naturally")
            if cp.get("favorite_topics"):
                system_parts.append(f"- Talks about: {', '.join(cp['favorite_topics'])}")
            if cp.get("important_facts"):
                for fact in cp["important_facts"][:5]:
                    system_parts.append(f"- {fact}")

        # Structured Evidence-Based Knowledge Graph
        if ctx.get("person_memories"):
            system_parts.append("")
            system_parts.append(f"STRUCTURED KNOWLEDGE & EVIDENCE-BASED FACTS ABOUT {friend_name.upper()}:")
            for mem in ctx["person_memories"]:
                status_tag = mem.get("status", "current").upper()
                fact = mem.get("fact", "")
                conf = mem.get("confidence", 1.0)
                if status_tag == "CURRENT":
                    system_parts.append(f"- [CONFIRMED CURRENT] {fact} (confidence: {conf:.2f})")
                elif status_tag == "HISTORICAL":
                    system_parts.append(f"- [HISTORICAL PAST] {fact} (Past info only; do not confuse with current situation)")
                elif status_tag == "PLANNED":
                    system_parts.append(f"- [PLANNED/TENTATIVE] {fact} (Future/intended, not current reality)")
                elif status_tag == "SUPERSEDED":
                    system_parts.append(f"- [SUPERSEDED] {fact} (Obsolete; do NOT assert as true)")
                elif status_tag == "UNCERTAIN":
                    system_parts.append(f"- [UNCERTAIN] {fact} (Inference; verify casually if relevant, do not assume)")

        # Conversation State (Ending awareness)
        c_state = ctx.get("conversation_state")
        if c_state and c_state.get("state") in ("ENDING", "ending"):
            system_parts.append("")
            system_parts.append("CONVERSATION STATE: ENDING")
            system_parts.append(f"The contact ({friend_name}) is wrapping up or saying goodbye (e.g. said '{c_state.get('termination_phrase', 'bye')}').")
            system_parts.append("Reply with a short, warm, natural farewell (e.g. 'ok da bye', 'see you later', 'take care'). DO NOT ask questions or start new topics.")

        # Mutual peer info
        if ctx.get("mutual_peer_info"):
            mp = ctx["mutual_peer_info"]
            system_parts.append("")
            system_parts.append(f"MUTUAL PEER SOCIAL CONTEXT: {friend_name} might be asking about {mp['peer_name']}.")
            if mp.get("status"):
                system_parts.append(f"You know: {mp['peer_name']} was {mp['status']} recently. Mention casually if relevant.")

        # Memory & context
        if ctx["memory"].get("relationship_label"):
            system_parts.append("")
            system_parts.append(f"RELATIONSHIP: {ctx['memory']['relationship_label']}")

        if ctx["conversation_summary"]:
            system_parts.append("")
            system_parts.append(f"CONTEXT FROM EARLIER CHATS: {ctx['conversation_summary'][:500]}")

        if ctx["memory"].get("important_facts"):
            facts_str = " | ".join(ctx["memory"]["important_facts"][:8])
            system_parts.append(f"REMEMBERED FACTS: {facts_str}")

        if ctx["memory"].get("ongoing_topics"):
            topics_str = ", ".join(ctx["memory"]["ongoing_topics"][:5])
            system_parts.append(f"ONGOING TOPICS: {topics_str}")

        # Rules (concise, not corporate)
        system_parts.extend([
            "",
            "HOW TO TEXT:",
            "- Be Julius. A natural, friendly peer assistant texting on WhatsApp.",
            "- Short and natural: 1-2 sentences max. Lowercase is fine. Sentence fragments are fine.",
            "- Emojis: use naturally when they fit (👍, 😅, 🔥, 🤝, 👀). Don't overdo it.",
            "- If asked 'what are you doing' / 'where are you': answer realistically based on current status.",
            "- If asked 'why no reply': give a friendly reason like 'was caught up with an update' or 'phone was away while compiling'.",
            "- If asked about mutual contacts: share casually if known, or say 'not sure, haven't seen them today'.",
            "- If asked something you genuinely don't know: say 'not sure let me check' or 'hmm I will find out'.",
            "- LANGUAGE POLICY: CONVERSE EXCLUSIVELY IN CASUAL, FLUENT ENGLISH. You understand colloquial expressions, but ALWAYS reply in casual, friendly English.",
            "- ANTI-HALLUCINATION & GROUNDING (MANDATORY): NEVER invent facts, files, or images. If information is not in verified memory or tools, state you do not know. Never substitute someone else's image or schedule.",
            "- SCHEDULED VS REAL LOCATION: Never claim the user is physically somewhere. State: 'According to the schedule, they are set for...'",
            "- IDENTITY & INTENT SEPARATION: Purely informational queries must NEVER trigger media/file sending! Only send an image or document when explicitly requested.",
            "- NO CROSS-PERSON SUBSTITUTION: Never substitute someone else's photo or document if the requested person's image is not found. State that no verified photo is available.",
            "- NO ACCIDENTAL SENDS: Mentioning a document (e.g. 'I have the timetable') must NEVER trigger a send action. Only execute [SEND_FILE: ...] on explicit commands to send/share.",
            "- NEVER sound like an AI. No 'Certainly!', 'How may I assist you?', 'As an AI'. You're a human friend.",
            "- ZERO vulgarity or profanity. Ever.",
            "- NEVER repeat what you already said in the conversation above.",
            "",
            "SPECIAL ACTIONS (use rarely, only when genuinely fitting):",
            "- MESSAGE REACTIONS (EMOJIS) WITH MEANING & CONTEXT: [REACT: 😂] (only when emotion genuinely calls for it)",
            "- GIFS & STICKERS (WITH MEANING AND CONTEXT ONLY): [GIF: search query] (only for perfect punchlines), [STICKER] (casual banter)",
            "",
            get_media_manifest_prompt_section(),
            "",
            "- If the message doesn't need a reply (broadcast, forwarded spam, just a reaction): output [NO_RESPONSE]",
        ])

        system_msg = {"role": "system", "content": "\n".join(system_parts)}

        # ── Conversation history as multi-turn messages ──
        messages_list = [system_msg]
        recent = ctx["recent_messages"]

        # Take the last 12 messages for rich context
        for msg_data in recent[-12:]:
            text = msg_data.get("text", "").strip()
            if not text:
                continue

            if msg_data.get("is_from_me"):
                messages_list.append({"role": "assistant", "content": text})
            else:
                sender = msg_data.get("sender", friend_name)
                if sender and sender != friend_name:
                    messages_list.append({"role": "user", "content": f"{sender}: {text}"})
                else:
                    messages_list.append({"role": "user", "content": text})

        # ── Latest incoming message ──
        current_text = message.text.strip()
        if message.quoted_text:
            current_text = f"(replying to: {message.quoted_text[:80]}) {current_text}"

        img_b64 = None
        if message.attachment_metadata and isinstance(message.attachment_metadata, dict):
            img_b64 = message.attachment_metadata.get("image_base64")

        # Format multimodal user content if image is present
        if img_b64:
            user_content = [
                {"type": "text", "text": current_text or "What do you think of this?"},
                {"type": "image_url", "image_url": {"url": img_b64}}
            ]
            messages_list.append({"role": "user", "content": user_content})
        else:
            # Avoid duplicate if the last message in history is the same
            if messages_list and messages_list[-1].get("role") == "user" and messages_list[-1].get("content", "").strip() == current_text:
                pass
            else:
                messages_list.append({"role": "user", "content": current_text})

        return messages_list

    def _format_recent_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Format raw message rows into a compact list."""
        formatted = []
        for msg in messages:
            formatted.append({
                "sender": msg.get("sender_name", ""),
                "text": msg.get("text", ""),
                "is_from_me": bool(msg.get("is_from_me", 0)),
                "timestamp": msg.get("timestamp", 0),
            })
        return formatted


def reflect_and_update_contact_profile(
    storage: WhatsAppStorage,
    chat_name: str,
    sender_name: str,
    user_text: str,
    bot_reply: str,
) -> None:
    """
    Analyze conversation exchange and dynamically evolve the contact's profile in SQLite.
    Continuously updates slang used, topics, mood/tone, activity status, and shareable notes.
    """
    from .config import is_self_chat
    if is_self_chat(chat_name):
        return

    profile = storage.get_contact_profile(chat_name)
    if not profile:
        profile = ContactProfile(
            chat_name=chat_name,
            display_name=sender_name or chat_name,
            contact_type="friend",
            tone_style="casual",
            slang_used=[],
            favorite_topics=[],
            last_status_update="",
            interconnected_notes="",
            important_facts=[],
            total_messages_exchanged=0,
            updated_at=time.time(),
        )

    profile.total_messages_exchanged += 1
    profile.updated_at = time.time()
    if sender_name and not profile.display_name:
        profile.display_name = sender_name

    text_lower = user_text.lower()

    # Detect slangs used by this contact
    known_slangs = ["da", "machi", "machan", "bro", "dude", "thala", "nanba", "dei", "seri", "illa", "thalaiva"]
    for s in known_slangs:
        if re.search(r"\b" + s + r"\b", text_lower):
            if s not in profile.slang_used:
                profile.slang_used.append(s)

    # Detect topics
    topic_keywords = {
        "calculus": "calculus",
        "eg": "engineering graphics",
        "graphics": "engineering graphics",
        "physics": "physics",
        "feee": "FEEE",
        "exam": "exams",
        "ia": "internal assessment",
        "lab": "labs",
        "hostel": "hostel life",
        "canteen": "canteen",
        "tea": "tea break",
        "cricket": "cricket",
        "movie": "movies",
        "record": "record work",
        "drafter": "mini drafter",
        "code": "coding",
        "ai": "AI agents",
    }
    for kw, topic in topic_keywords.items():
        if re.search(r"\b" + kw + r"\b", text_lower):
            if topic not in profile.favorite_topics:
                profile.favorite_topics.append(topic)

    # Detect status / activity update (e.g. "im in hostel", "reading calculus", "chillin")
    status_patterns = [
        r"(?:i am|i'm|im|naan|na)\s+(?:in|at|doing|studying|chilling|going to)\s+([^,\.!?]+)",
        r"(?:in|at)\s+(hostel|room|canteen|lab|library|ground|home)",
        r"(calculus|eg|physics|record)\s+(?:padikren|studying|writing|mudichuten)",
    ]
    for pat in status_patterns:
        m = re.search(pat, text_lower)
        if m:
            clean_status = m.group(0).strip()
            profile.last_status_update = clean_status
            profile.interconnected_notes = f"{clean_status}"
            break

    # Tone detection
    if any(em in user_text for em in ("😂", "🤣", "💀", "jolly", "joly", "fun", "lol", "lmao")):
        profile.tone_style = "playful, humorous"
    elif any(s in text_lower for s in ("machi", "machan", "dei", "da")):
        profile.tone_style = "casual close college peer"
    elif any(s in text_lower for s in ("sir", "anna")):
        profile.tone_style = "respectful peer"

    storage.save_contact_profile(profile)

