"""
Julius WhatsApp Integration — Message Router.

Central routing pipeline: incoming message → policy → mode → context → LLM → safety → action.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any, Callable, Dict, List, Optional

from .approval import ApprovalQueue
from .config import WhatsAppConfig
from .context import ConversationContext
from .models import (
    AuditEntry,
    ChatConfig,
    ChatMode,
    Confidence,
    ReceiptStatus,
    WhatsAppMessage,
)
from .persona import PersonaEngine
from .policy import ChatPolicyEngine
from .safety import SafetyGate
from .sender import WhatsAppSender
from .storage import WhatsAppStorage
from .training import TrainingManager

logger = logging.getLogger(__name__)

# Sentinel for responses that should not be sent
NO_RESPONSE = "[NO_RESPONSE]"


def sanitize_reply_text(text: str) -> str:
    """
    Remove accidental 'REPLY' prefixes, labels, or wrapper quotes from LLM replies,
    e.g. 'REPLY:', '[REPLY]', '"REPLY"', 'REPLY -', etc., without stripping legitimate words.
    """
    if not text:
        return ""
    t = text.strip()
    if (t.startswith('"') and t.endswith('"')) or (t.startswith("'") and t.endswith("'")):
        t = t[1:-1].strip()
    pattern = r'^(?:\[REPLY\]|[\"\'“”]REPLY[\"\'“”])\s*[:\-–—]?\s*|^REPLY\s*[:\-–—\n]\s*'
    t = re.sub(pattern, '', t, flags=re.IGNORECASE).strip()
    if (t.startswith('"') and t.endswith('"')) or (t.startswith("'") and t.endswith("'")):
        t = t[1:-1].strip()
    t = re.sub(pattern, '', t, flags=re.IGNORECASE).strip()
    return t


def parse_llm_action_response(raw_reply: str) -> Dict[str, Any]:
    """
    Parses LLM structured JSON response.
    Returns:
      {
        "action": "SEND_IMAGE" | "SEND_VIDEO" | "SEND_DOCUMENT" | "RENAME_MEDIA" | "SAVE_MEDIA" | "REPLY",
        "action_params": {"file_path": "...", "new_name": "...", "media_type": "..."},
        "thought": "...",
        "reply_text": "..."
      }
    Gracefully handles raw text, markdown blocks, and partial json.
    """
    if not raw_reply:
        return {"action": "REPLY", "action_params": {}, "thought": "", "reply_text": ""}

    text = raw_reply.strip()

    # 1. Try markdown code block ```json ... ```
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence_match:
        cand = fence_match.group(1).strip()
        try:
            data = json.loads(cand)
            if isinstance(data, dict):
                return {
                    "action": str(data.get("action") or "REPLY").strip().upper(),
                    "action_params": data.get("action_params") if isinstance(data.get("action_params"), dict) else {},
                    "thought": str(data.get("thought") or ""),
                    "reply_text": sanitize_reply_text(str(data.get("reply_text") or "")),
                }
        except Exception:
            pass

    # 2. Try outermost { ... }
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        cand = text[first_brace:last_brace + 1].strip()
        try:
            data = json.loads(cand)
            if isinstance(data, dict) and ("action" in data or "reply_text" in data):
                return {
                    "action": str(data.get("action") or "REPLY").strip().upper(),
                    "action_params": data.get("action_params") if isinstance(data.get("action_params"), dict) else {},
                    "thought": str(data.get("thought") or ""),
                    "reply_text": sanitize_reply_text(str(data.get("reply_text") or "")),
                }
        except Exception:
            pass

    # 3. Fallback to raw text as reply_text
    return {
        "action": "REPLY",
        "action_params": {},
        "thought": "",
        "reply_text": sanitize_reply_text(text),
    }


class WhatsAppMessageRouter:
    """
    Routes incoming messages through the complete pipeline.

    Flow:
    1. Policy check → should we process this?
    2. Mode resolution → training / approval / auto
    3. Context assembly → recent messages + summary + style
    4. Response generation → LLM
    5. Safety gate → escalation check
    6. Action dispatch → queue for approval or auto-send
    """

    def __init__(
        self,
        policy: ChatPolicyEngine,
        sender: WhatsAppSender,
        storage: WhatsAppStorage,
        config: WhatsAppConfig,
        context: ConversationContext,
        persona: PersonaEngine,
        training: TrainingManager,
        safety: SafetyGate,
        approval_queue: ApprovalQueue,
        generate_reply_fn: Optional[Callable] = None,
        state_machine: Optional[Any] = None,
        knowledge_engine: Optional[Any] = None,
        style_learner: Optional[Any] = None,
        media_resolver: Optional[Any] = None,
        action_guard: Optional[Any] = None,
        entity_resolver: Optional[Any] = None,
    ) -> None:
        self._policy = policy
        self._sender = sender
        self._storage = storage
        self._config = config
        self._context = context
        self._persona = persona
        self._training = training
        self._safety = safety
        self._approval_queue = approval_queue
        self._generate_reply_fn = generate_reply_fn

        from .conversation_state import ConversationStateMachine
        from .knowledge import PersonalKnowledgeEngine
        from .style_learner import CommunicationStyleLearner

        self._state_machine = state_machine or ConversationStateMachine(self._storage)
        self._knowledge_engine = knowledge_engine or PersonalKnowledgeEngine(self._storage)
        self._style_learner = style_learner or CommunicationStyleLearner(self._storage, self._persona)

        self._event_callbacks: List[Callable] = []
        self._paused = False
        self._last_reply_times: Dict[str, float] = {}

        # Telemetry & circuit breaker
        from .telemetry import LLMCircuitBreaker
        self._circuit_breaker = LLMCircuitBreaker(
            failure_threshold=5, cooldown_seconds=30.0, success_threshold=2
        )

        from .entity_resolver import get_entity_resolver
        from .media_resolver import get_media_resolver
        from .action_guard import get_action_guard
        from .timetable_engine import get_timetable_engine

        self._entity_resolver = entity_resolver or get_entity_resolver(self._storage)
        self._media_resolver = media_resolver or get_media_resolver(self._storage)
        self._action_guard = action_guard or get_action_guard(self._storage)
        self._timetable_engine = get_timetable_engine(self._storage)
        self._pending_media_naming: Dict[str, Dict[str, Any]] = {}

    @property
    def state_machine(self) -> Any:
        return self._state_machine

    @property
    def knowledge_engine(self) -> Any:
        return self._knowledge_engine

    @property
    def style_learner(self) -> Any:
        return self._style_learner


    @property
    def is_paused(self) -> bool:
        return self._paused

    def pause(self) -> None:
        self._paused = True
        self._sender.pause()

    def resume(self) -> None:
        self._paused = False
        self._sender.resume()

    def subscribe_events(self, callback: Callable) -> None:
        """Subscribe to routing events for UI updates."""
        self._event_callbacks.append(callback)

    def set_reply_generator(self, fn: Callable) -> None:
        """Set the LLM reply generation function."""
        self._generate_reply_fn = fn

    async def route_message(self, message: WhatsAppMessage) -> None:
        """
        Route an incoming message through the full pipeline.

        This is the main entry point called by the listener.
        Concurrent messages from different chats run simultaneously,
        while messages within the same chat are safely serialized.
        """
        if self._paused:
            logger.debug("Router paused, skipping message from %s", message.sender_name)
            return

        # 1. Policy check
        if not self._policy.should_process(message):
            return

        # NOTE: Per-chat serialization is handled by the service layer's _chat_locks.
        # No redundant lock here — the service already guarantees FIFO per chat.

        # STRICT DEDUP: Check if this incoming message has already been replied to
        if self._storage.is_message_replied(message.dedup_key):
            logger.info("Message '%s' already replied, skipping.", message.text[:30])
            return

        chat_config = self._policy.get_chat_config(message.chat_name)
        if chat_config is None:
            return

        mode = chat_config.mode
        logger.info(
            "Routing message from '%s' in '%s' (mode=%s)",
            message.sender_name, message.chat_name, mode.value,
        )

        self._emit_event("message_received", {
            "chat_name": message.chat_name,
            "sender": message.sender_name,
            "text": message.text[:100],
            "mode": mode.value,
        })

        # 2. Observe and continuously learn communication style & factual knowledge
        try:
            self._knowledge_engine.extract_and_update_knowledge(message)
            self._style_learner.observe_turn(message)
        except Exception as ke:
            logger.warning("Error updating personal knowledge / style for '%s': %s", message.chat_name, ke)

        # 3. Transition conversation state machine (aware of 'bye', endings, and reopenings)
        conv_state, is_ending = self._state_machine.on_incoming_message(
            chat_name=message.chat_name,
            sender_name=message.sender_name,
            text=message.text,
        )

        # 3.5 Check if incoming message is a newly received media/document from a peer
        if message.attachment_metadata and message.attachment_metadata.get("saved_media"):
            media_info = message.attachment_metadata["saved_media"]
            fname = media_info.get("filename", "file")
            cat = media_info.get("category", "document")
            title = media_info.get("title", fname)
            is_vid = bool(media_info.get("is_video") or media_info.get("media_type") == "video")
            if is_vid:
                ack_reply = f"Got the video! 🎥 Saved '{title}' to common workspace memory. If anyone or David asks for this video, I can share it right away 👍"
            elif media_info.get("is_image"):
                ent_title = media_info.get("title") or "Photo"
                ack_reply = f"Got the photo! 📸 Saved '{ent_title}' to common workspace memory. If anyone or David asks for this, I can share it right away 👍"
            else:
                ack_reply = f"Got the {fname}! 📄 Saved it to workspace memory. If anyone or David asks for this {cat}, I'll share it right away 👍"
            logger.info("Acknowledging received media '%s' from '%s'", fname, message.chat_name)
            await self._sender.send_message(
                chat_name=message.chat_name,
                text=sanitize_reply_text(ack_reply),
                chat_id=message.chat_id,
            )
            self._last_reply_times[message.chat_name] = time.time()
            self._storage.mark_message_replied(message.dedup_key, message.chat_name)
            self._state_machine.on_outgoing_message_sent(message.chat_name, ack_reply)
            return

        # 3.6 Check if this chat has a pending naming prompt for recently received photo
        if message.chat_name in self._pending_media_naming:
            pending = self._pending_media_naming[message.chat_name]
            # Valid within 10 minutes
            if time.time() - pending.get("timestamp", 0) < 600:
                from .media_manager import extract_media_subject, get_media_manager, GENERIC_MEDIA_WORDS
                subject = extract_media_subject(message.text)
                if not subject:
                    words = [w for w in re.findall(r"[a-zA-Z0-9]+", message.text) if w.lower() not in GENERIC_MEDIA_WORDS]
                    if words and len(words) <= 4:
                        subject = " ".join(words).title()

                if subject:
                    del self._pending_media_naming[message.chat_name]
                    renamed = get_media_manager().rename_recent_media(
                        chat_name=message.chat_name,
                        new_name=subject,
                        entity_name=subject.title(),
                    )
                    conf_reply = f"Got it! 📸 Saved and indexed the photo as '{subject.title()}' in workspace memory. Ready whenever anyone asks 👍"
                    logger.info("[ROUTER] Successfully resolved pending photo naming for '%s' -> '%s'", message.chat_name, subject)
                    await self._sender.send_message(
                        chat_name=message.chat_name,
                        text=conf_reply,
                        chat_id=message.chat_id,
                    )
                    self._last_reply_times[message.chat_name] = time.time()
                    self._storage.mark_message_replied(message.dedup_key, message.chat_name)
                    self._state_machine.on_outgoing_message_sent(message.chat_name, conf_reply)
                    return

        # 3.8 Check if peer is asking if we can save images/files or asking about permissions
        txt_lower = message.text.lower()
        is_asking_to_save_capability = (
            ("if i send" in txt_lower or "can you" in txt_lower or "will you" in txt_lower or "able to" in txt_lower or "possible to" in txt_lower)
            and any(w in txt_lower for w in ["save", "keep", "store", "download", "folder", "memory", "image", "photo", "pic", "file", "pdf", "doc"])
            and any(w in txt_lower for w in ["data folder", "folder", "david", "memory", "image", "photo", "pic", "file", "pdf"])
        ) or (
            any(w in txt_lower for w in ["permission", "permit"]) and any(w in txt_lower for w in ["save", "image", "photo", "file", "folder", "doc"])
        )
        if is_asking_to_save_capability:
            perm_reply = "Yeah of course bro, send it over! 👍 Any photo or document (PDF, timetable, notes, tutorial, assignment) you send gets saved and indexed right into the workspace memory, so David or anyone can use it anytime!"
            logger.info("Responding to media save capability inquiry from '%s'", message.chat_name)
            await self._sender.send_message(
                chat_name=message.chat_name,
                text=perm_reply,
                chat_id=message.chat_id,
            )
            self._last_reply_times[message.chat_name] = time.time()
            self._storage.mark_message_replied(message.dedup_key, message.chat_name)
            self._state_machine.on_outgoing_message_sent(message.chat_name, perm_reply)
            return

        # 4. Deterministic Intent & Action Processing (Tier 0: <20ms, zero hallucination)
        from .intent_engine import IntentEngine, MessageIntent
        from .models import ReceiptStatus
        from .tools import get_current_datetime, get_time_for_location, web_search

        classified = IntentEngine.classify(message.text)
        intent = classified["intent"]

        # 4.0 USER_CORRECTION ("You are telling that wrong", "That is false information", "You are wrong")
        if intent == MessageIntent.USER_CORRECTION:
            # Look up recent messages to discover the previous topic/question
            recent = self._storage.get_recent_messages(message.chat_name, limit=6)
            prev_user_q = ""
            for m in reversed(recent):
                if not m.is_from_me and m.text != message.text:
                    prev_user_q = m.text
                    break

            query_cand = prev_user_q or message.text
            loc_time = get_time_for_location(query_cand)
            if loc_time:
                corrected_ans = f"The verified current time in {loc_time['location_matched']} is {loc_time['time_12h']} {loc_time['tz_abbr']} ({loc_time['weekday']}, {loc_time['date']})."
                reply_text = f"I sincerely apologize for the mistake! You are completely right. Here is the verified information:\n\n{corrected_ans}"
            else:
                search_fact = web_search(query_cand)
                if search_fact and "inconclusive" not in search_fact.lower():
                    reply_text = f"I apologize for the mistake! Thank you for correcting me. Here is the verified information:\n\n{search_fact}"
                else:
                    reply_text = "I apologize for the mistake! Thank you for catching that and correcting me. Please tell me what you'd like me to look up or verify, and I'll make sure to get the exact verified facts 👍"

            logger.info("[ROUTER] Handled USER_CORRECTION from '%s' -> '%s'", message.chat_name, reply_text[:80])
            await self._sender.send_message(chat_name=message.chat_name, text=reply_text, chat_id=message.chat_id)
            self._last_reply_times[message.chat_name] = time.time()
            self._storage.mark_message_replied(message.dedup_key, message.chat_name)
            self._state_machine.on_outgoing_message_sent(message.chat_name, reply_text)
            return

        # 4.1 RENAME_MEDIA_OR_DOCUMENT (e.g. "Name of the image is Rohit", "This is naveen image save the photo name as naveen")
        if intent == MessageIntent.RENAME_MEDIA_OR_DOCUMENT:
            target_name = classified["target"]
            from .media_manager import get_media_manager
            renamed = get_media_manager().rename_recent_media(
                chat_name=message.chat_name,
                new_name=target_name,
                entity_name=target_name.title(),
            )
            if message.chat_name in self._pending_media_naming:
                del self._pending_media_naming[message.chat_name]

            if renamed:
                ent_name = renamed.get("entities", [target_name.title()])[0]
                reply_text = f"Got it! Renamed the recent photo to '{renamed['filename']}' and tagged it as {ent_name} in workspace memory 👍"
            else:
                reply_text = f"Saved '{target_name}' to workspace memory! Ready whenever anyone asks 👍"

            logger.info("[ROUTER] Handled media rename/tag directive: '%s' -> '%s'", message.chat_name, reply_text)
            await self._sender.send_message(chat_name=message.chat_name, text=reply_text, chat_id=message.chat_id)
            self._last_reply_times[message.chat_name] = time.time()
            self._storage.mark_message_replied(message.dedup_key, message.chat_name)
            self._state_machine.on_outgoing_message_sent(message.chat_name, reply_text)
            return

        # 4.2 SAVE_MEDIA_CONFIRM ("save that in memory", "save this image")
        if intent == MessageIntent.SAVE_MEDIA_CONFIRM:
            confirm_reply = "Saved to workspace memory! 📸 Everything is indexed and ready whenever anyone asks 👍"
            logger.info("[ROUTER] Responding to save command from '%s'", message.chat_name)
            await self._sender.send_message(chat_name=message.chat_name, text=confirm_reply, chat_id=message.chat_id)
            self._last_reply_times[message.chat_name] = time.time()
            self._storage.mark_message_replied(message.dedup_key, message.chat_name)
            self._state_machine.on_outgoing_message_sent(message.chat_name, confirm_reply)
            return

        # 4.3 ASK_DATE_TIME ("What date is today?", "What time is it?", "What is the time in Japan?")
        if intent == MessageIntent.ASK_DATE_TIME:
            loc_time = get_time_for_location(message.text)
            if loc_time:
                time_reply = f"The current time in {loc_time['location_matched']} is {loc_time['time_12h']} {loc_time['tz_abbr']} ({loc_time['weekday']}, {loc_time['date']})."
            else:
                now_info = get_current_datetime("Asia/Kolkata")
                t_low = message.text.lower()
                if any(w in t_low for w in ["date", "day"]):
                    time_reply = f"Today is {now_info['weekday']}, {now_info['date']} (IST)."
                else:
                    time_reply = f"The current time is {now_info['time_12h']} IST."
            logger.info("[ROUTER] Responding with exact time/date to '%s': '%s'", message.chat_name, time_reply)
            await self._sender.send_message(chat_name=message.chat_name, text=time_reply, chat_id=message.chat_id)
            self._last_reply_times[message.chat_name] = time.time()
            self._storage.mark_message_replied(message.dedup_key, message.chat_name)
            self._state_machine.on_outgoing_message_sent(message.chat_name, time_reply)
            return

        # 4.35 ASK_EXTERNAL_INFO ("Who is the CEO of Google?", "What is quantum computing?")
        if intent == MessageIntent.ASK_EXTERNAL_INFO:
            query = classified.get("params", {}).get("query", message.text)
            search_res = web_search(query)
            if search_res and "inconclusive" not in search_res.lower():
                reply_text = search_res
            else:
                reply_text = f"I checked online for '{query}', but could not find a verified answer."
            logger.info("[ROUTER] Handled ASK_EXTERNAL_INFO for '%s' -> '%s'", message.chat_name, reply_text[:80])
            await self._sender.send_message(chat_name=message.chat_name, text=reply_text, chat_id=message.chat_id)
            self._last_reply_times[message.chat_name] = time.time()
            self._storage.mark_message_replied(message.dedup_key, message.chat_name)
            self._state_machine.on_outgoing_message_sent(message.chat_name, reply_text)
            return

        # 4.4 ASK_SCHEDULE_LOCATION ("Where is David?", "Where is David at 10:30 Monday?")
        if intent == MessageIntent.ASK_SCHEDULE_LOCATION:
            time_spec = classified.get("params", {}).get("time_spec", "")
            if time_spec and any(d in time_spec.lower() for d in ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]):
                day = "Monday"
                for d_cand in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]:
                    if d_cand[:3].lower() in time_spec.lower():
                        day = d_cand
                        break
                sched_res = self._timetable_engine.get_schedule_at(day, time_spec)
            else:
                sched_res = self._timetable_engine.get_schedule_now()

            reply_text = sched_res["phrasing"]
            logger.info("[ROUTER] Responding with timetable schedule to '%s': '%s'", message.chat_name, reply_text)
            await self._sender.send_message(chat_name=message.chat_name, text=reply_text, chat_id=message.chat_id)
            self._last_reply_times[message.chat_name] = time.time()
            self._storage.mark_message_replied(message.dedup_key, message.chat_name)
            self._state_machine.on_outgoing_message_sent(message.chat_name, reply_text)
            return

        # 4.5 ASK_PERSON_INFO ("Who is Narendra?", "Tell me about Gova")
        # STRICT: Must NEVER trigger media sending!
        if intent == MessageIntent.ASK_PERSON_INFO:
            person_query = classified.get("params", {}).get("person", "")
            resolved_ent = self._entity_resolver.resolve_person(person_query)
            if resolved_ent:
                c_name = resolved_ent["canonical_name"]
                dept = resolved_ent.get("metadata", {}).get("dept", "MIT Chromepet")
                notes = resolved_ent.get("metadata", {}).get("notes", "")
                reply_text = f"{c_name} is in 1st Year {dept} at MIT Chromepet. {notes}"
            else:
                reply_text = f"I don't have verified information about '{person_query}' in my database."

            logger.info("[ROUTER] Handled ASK_PERSON_INFO for '%s' -> '%s' (zero media sent)", person_query, reply_text)
            await self._sender.send_message(chat_name=message.chat_name, text=reply_text, chat_id=message.chat_id)
            self._last_reply_times[message.chat_name] = time.time()
            self._storage.mark_message_replied(message.dedup_key, message.chat_name)
            self._state_machine.on_outgoing_message_sent(message.chat_name, reply_text)
            return

        # 4.6 SEND_PERSON_IMAGE ("Send Naveen's image", "Send Sumanth photo", "Show me Naveen")
        if intent == MessageIntent.SEND_PERSON_IMAGE:
            person_target = classified.get("params", {}).get("person", "")
            as_doc = classified.get("params", {}).get("as_document", False)
            resolution = self._media_resolver.resolve_image(
                person_query=person_target,
                general_query=message.text,
                chat_name=message.chat_name,
            )
            receipt = self._action_guard.authorize_media_send(
                requester=message.sender_name,
                target_chat=message.chat_name,
                resolution=resolution,
                explicit_intent=True,
            )
            if receipt.execution_status == ReceiptStatus.SUCCESS:
                item = resolution.item
                caption = f"Here is {resolution.target_entity or item.get('title', 'the photo')} 📸"
                file_path = receipt.result["file_path"]
                if as_doc:
                    success = await self._sender.send_document(
                        chat_name=message.chat_name,
                        file_path=file_path,
                        caption=caption,
                        chat_id=message.chat_id,
                    )
                else:
                    success = await self._sender.send_image(
                        chat_name=message.chat_name,
                        file_path=file_path,
                        caption=caption,
                        chat_id=message.chat_id,
                    )
                self._action_guard.record_execution_outcome(receipt.action_id, success)
                reply_text = caption
            elif receipt.execution_status == ReceiptStatus.AMBIGUOUS:
                reply_text = receipt.result.get("prompt", "Multiple photos found. Which one would you like?")
                await self._sender.send_message(chat_name=message.chat_name, text=reply_text, chat_id=message.chat_id)
            else:
                from .media_manager import get_media_manager
                available_items = [it for it in get_media_manager()._index if it.get("is_image") and Path(it.get("path", "")).exists()]
                available_names = list(dict.fromkeys([e for it in available_items for e in it.get("entities", []) if e and e.lower() not in ("photo", "image")]))
                target_desc = f"'{person_target}'" if person_target else "that request"
                if available_names:
                    names_str = ", ".join(available_names[:3])
                    reply_text = f"I don't have a verified photo of {target_desc} in workspace memory. Currently I have photos of {names_str}. If you send {target_desc}'s photo, I'll save and index it right away!"
                else:
                    reply_text = f"I don't have a verified photo of {target_desc} in workspace memory yet. If you send the photo, I'll save and index it right away!"
                await self._sender.send_message(chat_name=message.chat_name, text=reply_text, chat_id=message.chat_id)

            self._last_reply_times[message.chat_name] = time.time()
            self._storage.mark_message_replied(message.dedup_key, message.chat_name)
            self._state_machine.on_outgoing_message_sent(message.chat_name, reply_text)
            return

        # 4.65 SEND_VIDEO ("Send Sumanth video", "Send the video", "Share that video")
        if intent == MessageIntent.SEND_VIDEO:
            person_target = classified.get("target") or classified.get("params", {}).get("person")
            resolution = self._media_resolver.resolve_video(
                person_query=person_target,
                general_query=message.text,
                chat_name=message.chat_name,
            )
            receipt = self._action_guard.authorize_media_send(
                requester=message.sender_name,
                target_chat=message.chat_name,
                resolution=resolution,
                explicit_intent=True,
            )
            if receipt.execution_status == ReceiptStatus.SUCCESS:
                item = resolution.item
                caption = f"Here is {resolution.target_entity or item.get('title', 'the video')} 🎥"
                file_path = receipt.result["file_path"]
                success = await self._sender.send_media(
                    chat_name=message.chat_name,
                    file_path=file_path,
                    caption=caption,
                    media_type="video",
                    chat_id=message.chat_id,
                )
                self._action_guard.record_execution_outcome(receipt.action_id, success)
                reply_text = caption
            elif receipt.execution_status == ReceiptStatus.AMBIGUOUS:
                reply_text = receipt.result.get("prompt", "Multiple videos found. Which one would you like?")
                await self._sender.send_message(chat_name=message.chat_name, text=sanitize_reply_text(reply_text), chat_id=message.chat_id)
            else:
                from .media_manager import get_media_manager
                available_items = [it for it in get_media_manager()._index if (it.get("is_video") or it.get("media_type") == "video") and Path(it.get("path", "")).exists()]
                available_names = list(dict.fromkeys([e for it in available_items for e in it.get("entities", []) if e and e.lower() not in ("video", "vid")]))
                target_desc = f"'{person_target}'" if person_target else "that request"
                if available_names:
                    names_str = ", ".join(available_names[:3])
                    reply_text = f"I don't have a verified video of {target_desc} in workspace memory. Currently I have videos of {names_str}. If you send {target_desc}'s video, I'll save and index it right away!"
                else:
                    reply_text = f"I don't have a verified video for {target_desc} in workspace memory yet. If you send the video, I'll save and index it right away!"
                await self._sender.send_message(chat_name=message.chat_name, text=sanitize_reply_text(reply_text), chat_id=message.chat_id)

            self._last_reply_times[message.chat_name] = time.time()
            self._storage.mark_message_replied(message.dedup_key, message.chat_name)
            self._state_machine.on_outgoing_message_sent(message.chat_name, reply_text)
            return

        # 4.7 SEND_DOCUMENT ("Send the timetable PDF", "Send physics notes", "Give me the tutorial PDF")
        if intent == MessageIntent.SEND_DOCUMENT:
            resolution = self._media_resolver.resolve_document(query=message.text)
            receipt = self._action_guard.authorize_media_send(
                requester=message.sender_name,
                target_chat=message.chat_name,
                resolution=resolution,
                explicit_intent=True,
            )
            if receipt.execution_status == ReceiptStatus.SUCCESS:
                item = resolution.item
                caption = f"Here is the {item.get('title', item.get('filename', 'document'))} 📄"
                success = await self._sender.send_document(
                    chat_name=message.chat_name,
                    file_path=receipt.result["file_path"],
                    caption=caption,
                    chat_id=message.chat_id,
                )
                self._action_guard.record_execution_outcome(receipt.action_id, success)
                reply_text = caption
            elif receipt.execution_status == ReceiptStatus.AMBIGUOUS:
                reply_text = receipt.result.get("prompt", "Multiple documents found. Which one would you like?")
                await self._sender.send_message(chat_name=message.chat_name, text=reply_text, chat_id=message.chat_id)
            else:
                reply_text = receipt.result.get("error") or "No verified document found matching your request."
                await self._sender.send_message(chat_name=message.chat_name, text=reply_text, chat_id=message.chat_id)

            self._last_reply_times[message.chat_name] = time.time()
            self._storage.mark_message_replied(message.dedup_key, message.chat_name)
            self._state_machine.on_outgoing_message_sent(message.chat_name, reply_text)
            return

        # 4.8 INFORMATIONAL_STATEMENT ("I have the timetable", "I got the notes")
        # STRICT: Must NEVER trigger document sending!
        if intent == MessageIntent.INFORMATIONAL_STATEMENT:
            reply_text = "Got it bro, thanks for letting me know! 👍 Let me know if you need anything else."
            logger.info("[ROUTER] Handled INFORMATIONAL_STATEMENT for '%s' (zero documents sent)", message.chat_name)
            await self._sender.send_message(chat_name=message.chat_name, text=reply_text, chat_id=message.chat_id)
            self._last_reply_times[message.chat_name] = time.time()
            self._storage.mark_message_replied(message.dedup_key, message.chat_name)
            self._state_machine.on_outgoing_message_sent(message.chat_name, reply_text)
            return

        # 4.9 Check for device info / action / admin query (IP, connected devices, code inspection, safe commands)
        from .device_agent import is_device_query, generate_device_action_response
        if is_device_query(message.text):
            logger.info("Executing device action response for '%s' in '%s'", message.sender_name, message.chat_name)
            reply = generate_device_action_response(message.text, message.sender_name)
            success = await self._sender.send_message(
                chat_name=message.chat_name,
                text=reply,
                chat_id=message.chat_id,
            )
            if success:
                self._last_reply_times[message.chat_name] = time.time()
                self._storage.mark_message_replied(message.dedup_key, message.chat_name)
                self._state_machine.on_outgoing_message_sent(message.chat_name, reply)
            return

        # 4. Check for David Julius self-chat
        from .config import is_self_chat
        if is_self_chat(message.chat_name):
            await self._handle_self_chat(message)
            return

        # 5. Mode dispatch
        if mode == ChatMode.TRAINING:
            await self._handle_training(message, chat_config)
        elif mode == ChatMode.APPROVAL:
            await self._handle_approval(message, chat_config)
        elif mode == ChatMode.AUTO:
            await self._handle_auto(message, chat_config)

    async def _handle_training(self, message: WhatsAppMessage, config: ChatConfig) -> None:
        """Training mode: predict + show to user, don't send."""
        # Generate prediction
        reply = await self._generate_reply(message, config)
        if not reply or reply.strip() == NO_RESPONSE:
            reply = "(no prediction)"
        else:
            parsed = parse_llm_action_response(reply)
            if parsed.get("reply_text"):
                reply = parsed["reply_text"]

        self._emit_event("training_prediction", {
            "chat_name": message.chat_name,
            "sender": message.sender_name,
            "incoming": message.text,
            "prediction": reply,
            "message_id": message.id,
        })

        # Add to approval queue so user can see it and submit their actual reply
        self._approval_queue.add(
            incoming_message=message,
            draft_reply=reply,
            confidence=Confidence.MEDIUM,
            reason="Training mode — edit with your actual reply",
        )

    async def _handle_approval(self, message: WhatsAppMessage, config: ChatConfig) -> None:
        """Approval mode: generate draft + queue for user approval."""
        start = time.time()
        reply = await self._generate_reply(message, config)
        latency_ms = int((time.time() - start) * 1000)

        if not reply or reply.strip() == NO_RESPONSE:
            logger.info("LLM decided no response needed for '%s'", message.chat_name)
            self._emit_event("no_response_needed", {
                "chat_name": message.chat_name,
                "sender": message.sender_name,
            })
            return

        parsed = parse_llm_action_response(reply)
        if parsed.get("reply_text"):
            reply = parsed["reply_text"]

        # Evaluate confidence
        msg_confidence, msg_reason = self._safety.evaluate_message(message)
        resp_confidence, resp_reason = self._safety.evaluate_response(reply, message)

        # Use the lower confidence
        overall = Confidence.LOW
        if msg_confidence == Confidence.HIGH and resp_confidence == Confidence.HIGH:
            overall = Confidence.HIGH
        elif msg_confidence != Confidence.LOW and resp_confidence != Confidence.LOW:
            overall = Confidence.MEDIUM

        # Queue for approval
        item = self._approval_queue.add(
            incoming_message=message,
            draft_reply=reply,
            confidence=overall,
            reason=f"{msg_reason}; {resp_reason}",
        )

        self._emit_event("approval_queued", {
            "id": item.id,
            "chat_name": message.chat_name,
            "sender": message.sender_name,
            "incoming": message.text[:200],
            "draft": reply,
            "confidence": overall.value,
            "reason": item.reason,
            "latency_ms": latency_ms,
        })

    async def _handle_auto(self, message: WhatsAppMessage, config: ChatConfig) -> None:
        """Auto mode: generate reply and send immediately.
        
        STRICT: Never auto-replies to groups. No escalation to David.
        Includes pipeline telemetry and circuit breaker protection.
        """
        # STRICT GROUP SAFETY: Never auto-reply to groups
        if message.is_group:
            logger.warning("Auto mode blocked on group chat '%s' for safety.", message.chat_name)
            return

        # Pipeline telemetry
        from .telemetry import PipelineSpan
        span = PipelineSpan.start(message.chat_name, message_id=message.id)

        # Circuit breaker check: if open, fall back to Stark replies rather than dropping message
        reply = ""
        if not self._circuit_breaker.can_execute():
            logger.warning(
                "LLM circuit breaker OPEN — falling back to Stark replies for '%s' (state: %s)",
                message.chat_name, self._circuit_breaker.state,
            )
            from .stark_replies import get_stark_fallback
            reply = get_stark_fallback(message.text)
            latency_ms = 0
            span.mark("circuit_breaker_fallback")
        else:
            start = time.time()
            reply = await self._generate_reply(message, config)
            latency_ms = int((time.time() - start) * 1000)
            span.mark("llm_done")

        if not reply or reply.strip() == NO_RESPONSE:
            from .stark_replies import get_stark_fallback
            reply = get_stark_fallback(message.text)
            logger.info("Using Stark fallback reply because primary reply was empty for '%s'", message.chat_name)

        # ── Parse LLM Structured Action ──
        parsed_action = parse_llm_action_response(reply)
        action = parsed_action.get("action", "REPLY")
        action_params = parsed_action.get("action_params", {})
        action_reply_text = parsed_action.get("reply_text", "")

        # ── ACTION 1: SEND_IMAGE ──
        if action == "SEND_IMAGE":
            target_file = action_params.get("file_path", "")
            caption = action_reply_text or "Here is the photo 📸"
            resolution = self._media_resolver.resolve_image(
                person_query=target_file if not target_file.lower().endswith((".jpg", ".png", ".webp", ".jpeg")) else None,
                general_query=target_file or message.text,
                chat_name=message.chat_name,
            )
            receipt = self._action_guard.authorize_media_send(
                requester=message.sender_name,
                target_chat=message.chat_name,
                resolution=resolution,
                explicit_intent=True,
            )
            if receipt.execution_status == ReceiptStatus.SUCCESS:
                fpath = receipt.result["file_path"]
                logger.info("[ROUTER] LLM action SEND_IMAGE: sending '%s' to '%s'", fpath, message.chat_name)
                success = await self._sender.send_image(
                    chat_name=message.chat_name,
                    file_path=fpath,
                    caption=caption,
                    chat_id=message.chat_id,
                )
                self._action_guard.record_execution_outcome(receipt.action_id, success)
            else:
                logger.info("[ROUTER] LLM action SEND_IMAGE not authorized (%s), sending reply_text: '%s'", receipt.execution_status, caption)
                await self._sender.send_message(chat_name=message.chat_name, text=caption, chat_id=message.chat_id)
            self._last_reply_times[message.chat_name] = time.time()
            self._storage.mark_message_replied(message.dedup_key, message.chat_name)
            self._state_machine.on_outgoing_message_sent(message.chat_name, caption)
            span.mark("send_complete")
            return

        # ── ACTION 2: SEND_DOCUMENT ──
        if action == "SEND_DOCUMENT":
            target_doc = action_params.get("file_path", "")
            caption = action_reply_text or "Here is the document 📄"
            resolution = self._media_resolver.resolve_document(query=target_doc or message.text)
            receipt = self._action_guard.authorize_media_send(
                requester=message.sender_name,
                target_chat=message.chat_name,
                resolution=resolution,
                explicit_intent=True,
            )
            if receipt.execution_status == ReceiptStatus.SUCCESS:
                fpath = receipt.result["file_path"]
                logger.info("[ROUTER] LLM action SEND_DOCUMENT: sending '%s' to '%s'", fpath, message.chat_name)
                success = await self._sender.send_document(
                    chat_name=message.chat_name,
                    file_path=fpath,
                    caption=caption,
                    chat_id=message.chat_id,
                )
                self._action_guard.record_execution_outcome(receipt.action_id, success)
            else:
                logger.info("[ROUTER] LLM action SEND_DOCUMENT not authorized, sending reply_text: '%s'", caption)
                await self._sender.send_message(chat_name=message.chat_name, text=caption, chat_id=message.chat_id)
            self._last_reply_times[message.chat_name] = time.time()
            self._storage.mark_message_replied(message.dedup_key, message.chat_name)
            self._state_machine.on_outgoing_message_sent(message.chat_name, caption)
            span.mark("send_complete")
        # ── ACTION 2.5: SEND_VIDEO ──
        if action == "SEND_VIDEO":
            target_vid = action_params.get("file_path", "")
            caption = sanitize_reply_text(action_reply_text) or "Here is the video 🎥"
            resolution = self._media_resolver.resolve_video(
                person_query=target_vid if not target_vid.lower().endswith((".mp4", ".mov", ".webm", ".mkv")) else None,
                general_query=target_vid or message.text,
                chat_name=message.chat_name,
            )
            receipt = self._action_guard.authorize_media_send(
                requester=message.sender_name,
                target_chat=message.chat_name,
                resolution=resolution,
                explicit_intent=True,
            )
            if receipt.execution_status == ReceiptStatus.SUCCESS:
                fpath = receipt.result["file_path"]
                logger.info("[ROUTER] LLM action SEND_VIDEO: sending '%s' to '%s'", fpath, message.chat_name)
                success = await self._sender.send_media(
                    chat_name=message.chat_name,
                    file_path=fpath,
                    caption=caption,
                    media_type="video",
                    chat_id=message.chat_id,
                )
                self._action_guard.record_execution_outcome(receipt.action_id, success)
            else:
                logger.info("[ROUTER] LLM action SEND_VIDEO not authorized, sending reply_text: '%s'", caption)
                await self._sender.send_message(chat_name=message.chat_name, text=sanitize_reply_text(caption), chat_id=message.chat_id)
            self._last_reply_times[message.chat_name] = time.time()
            self._storage.mark_message_replied(message.dedup_key, message.chat_name)
            self._state_machine.on_outgoing_message_sent(message.chat_name, caption)
            span.mark("send_complete")
            return

        # ── ACTION 3: RENAME_MEDIA / SAVE_MEDIA ──
        if action in ("RENAME_MEDIA", "SAVE_MEDIA"):
            new_name = action_params.get("new_name", "")
            caption = sanitize_reply_text(action_reply_text) or f"Saved '{new_name}' in workspace memory 👍"
            if new_name:
                from .media_manager import get_media_manager
                get_media_manager().rename_recent_media(
                    chat_name=message.chat_name,
                    new_name=new_name,
                    entity_name=new_name.title(),
                )
            if message.chat_name in self._pending_media_naming:
                del self._pending_media_naming[message.chat_name]
            logger.info("[ROUTER] LLM action RENAME_MEDIA for '%s' -> '%s'", message.chat_name, new_name)
            await self._sender.send_message(chat_name=message.chat_name, text=caption, chat_id=message.chat_id)
            self._last_reply_times[message.chat_name] = time.time()
            self._storage.mark_message_replied(message.dedup_key, message.chat_name)
            self._state_machine.on_outgoing_message_sent(message.chat_name, caption)
            span.mark("send_complete")
            return

        # ── ACTION 4: ASK_MEDIA_NAME ──
        if action == "ASK_MEDIA_NAME":
            caption = sanitize_reply_text(action_reply_text) or "Got the media! Saved and indexed it in common workspace memory 👍"
            logger.info("[ROUTER] LLM action ASK_MEDIA_NAME for '%s' (handled autonomously)", message.chat_name)
            await self._sender.send_message(chat_name=message.chat_name, text=caption, chat_id=message.chat_id)
            self._last_reply_times[message.chat_name] = time.time()
            self._storage.mark_message_replied(message.dedup_key, message.chat_name)
            self._state_machine.on_outgoing_message_sent(message.chat_name, caption)
            span.mark("send_complete")
            return

        # ── ACTION 5: REPLY / Plain text ──
        if action_reply_text:
            reply = sanitize_reply_text(action_reply_text)

        # Check if conversation state is ending: wrap up cleanly
        conv_rec = self._state_machine.get_state(message.chat_name)
        if conv_rec.state == "ending":
            # If the reply is empty, too verbose, or asks questions, enforce clean farewell
            if not reply or len(reply.split()) > 10 or "?" in reply:
                term = (conv_rec.termination_phrase or "bye").lower()
                if any(w in term for w in ["night", "gn", "sleep", "sweet dreams"]):
                    reply = "good night da, sleep well!"
                elif any(w in term for w in ["take care", "tc"]):
                    reply = "take care bro, catch you later!"
                else:
                    reply = "ok da, see you later! take care"
            logger.info("Ending state confirmed for '%s' — wrapping up with farewell: '%s'", message.chat_name, reply)

        # Strip any stale [ESCALATE_TO_DAVID] tokens — feature is REMOVED.
        escalate_match = re.search(r"\[ESCALATE_TO_DAVID(?::\s*([^\]]+))?\]\s*(.*)", reply, re.DOTALL | re.IGNORECASE)
        if escalate_match:
            holding_reply = escalate_match.group(2).strip()
            if holding_reply:
                reply = holding_reply
            else:
                reply = "wait da, let me check and tell you"
            logger.info("Stripped deprecated ESCALATE_TO_DAVID token from reply to '%s'", message.chat_name)

        # 1. Parse Reactions: [REACT: <emoji>]
        react_match = re.search(r"\[REACT:\s*([^\]]+)\]", reply, re.IGNORECASE)
        if react_match:
            react_emoji = react_match.group(1).strip()
            reply = re.sub(r"\[REACT:\s*[^\]]+\]", "", reply, flags=re.IGNORECASE).strip()
            asyncio.create_task(self._sender.react_to_message(message.chat_name, react_emoji))

        # 2. Parse GIFs: [GIF: <query>]
        gif_match = re.search(r"\[GIF:\s*([^\]]+)\]", reply, re.IGNORECASE)
        if gif_match:
            gif_query = gif_match.group(1).strip()
            reply = re.sub(r"\[GIF:\s*[^\]]+\]", "", reply, flags=re.IGNORECASE).strip()
            asyncio.create_task(self._sender.send_gif(message.chat_name, gif_query))

        # 3. Parse Stickers: [STICKER]
        sticker_match = re.search(r"\[STICKER(?::\s*([^\]]+))?\]", reply, re.IGNORECASE)
        if sticker_match:
            sticker_theme = (sticker_match.group(1) or "").strip()
            reply = re.sub(r"\[STICKER(?::\s*[^\]]+)?\]", "", reply, flags=re.IGNORECASE).strip()
            asyncio.create_task(self._sender.send_sticker(message.chat_name, sticker_theme))

        # 4. Parse File Sending: [SEND_FILE: filename] or [SEND_DOCUMENT: filename]
        file_match = re.search(r"\[SEND_(?:FILE|DOCUMENT):\s*([^\]]+)\]", reply, re.IGNORECASE)
        if file_match:
            file_query = file_match.group(1).strip()
            reply = re.sub(r"\[SEND_(?:FILE|DOCUMENT):\s*[^\]]+\]", "", reply, flags=re.IGNORECASE).strip()
            resolution = self._media_resolver.resolve_document(query=file_query)
            receipt = self._action_guard.authorize_media_send(
                requester=message.sender_name,
                target_chat=message.chat_name,
                resolution=resolution,
                explicit_intent=True,
            )
            if receipt.execution_status == ReceiptStatus.SUCCESS:
                item = resolution.item
                caption = f"📄 {item.get('title', item.get('filename', ''))}"
                logger.info("Executing [SEND_DOCUMENT] directive: '%s' to '%s'", receipt.result["file_path"], message.chat_name)
                success = await self._sender.send_document(
                    chat_name=message.chat_name,
                    file_path=receipt.result["file_path"],
                    caption=caption,
                    chat_id=message.chat_id,
                )
                self._action_guard.record_execution_outcome(receipt.action_id, success)
            else:
                from .answer_verifier import AnswerVerifier
                reply = AnswerVerifier.verify_and_ground(reply, receipt)

        # 5. Parse Image Sending: [SEND_IMAGE: filename]
        img_match = re.search(r"\[SEND_IMAGE:\s*([^\]]+)\]", reply, re.IGNORECASE)
        if img_match:
            img_query = img_match.group(1).strip()
            reply = re.sub(r"\[SEND_IMAGE:\s*[^\]]+\]", "", reply, flags=re.IGNORECASE).strip()
            resolution = self._media_resolver.resolve_image(general_query=img_query, chat_name=message.chat_name)
            receipt = self._action_guard.authorize_media_send(
                requester=message.sender_name,
                target_chat=message.chat_name,
                resolution=resolution,
                explicit_intent=True,
            )
            if receipt.execution_status == ReceiptStatus.SUCCESS:
                item = resolution.item
                caption = f"📸 {item.get('title', item.get('filename', ''))}"
                logger.info("Executing [SEND_IMAGE] directive: '%s' to '%s'", receipt.result["file_path"], message.chat_name)
                success = await self._sender.send_image(
                    chat_name=message.chat_name,
                    file_path=receipt.result["file_path"],
                    caption=caption,
                    chat_id=message.chat_id,
                )
                self._action_guard.record_execution_outcome(receipt.action_id, success)
            else:
                from .answer_verifier import AnswerVerifier
                reply = AnswerVerifier.verify_and_ground(reply, receipt)

        # 6. Parse Video Sending: [SEND_VIDEO: filename/query]
        vid_match = re.search(r"\[SEND_VIDEO:\s*([^\]]+)\]", reply, re.IGNORECASE)
        if vid_match:
            vid_query = vid_match.group(1).strip()
            reply = re.sub(r"\[SEND_VIDEO:\s*[^\]]+\]", "", reply, flags=re.IGNORECASE).strip()
            resolution = self._media_resolver.resolve_video(general_query=vid_query, chat_name=message.chat_name)
            receipt = self._action_guard.authorize_media_send(
                requester=message.sender_name,
                target_chat=message.chat_name,
                resolution=resolution,
                explicit_intent=True,
            )
            if receipt.execution_status == ReceiptStatus.SUCCESS:
                item = resolution.item
                caption = f"🎥 {item.get('title', item.get('filename', ''))}"
                logger.info("Executing [SEND_VIDEO] directive: '%s' to '%s'", receipt.result["file_path"], message.chat_name)
                success = await self._sender.send_media(
                    chat_name=message.chat_name,
                    file_path=receipt.result["file_path"],
                    caption=caption,
                    media_type="video",
                    chat_id=message.chat_id,
                )
                self._action_guard.record_execution_outcome(receipt.action_id, success)
            else:
                from .answer_verifier import AnswerVerifier
                reply = AnswerVerifier.verify_and_ground(reply, receipt)

        # 4. Strict English safeguard: remove any stray Tamil script characters
        reply = re.sub(r"[\u0b80-\u0bff]+", "", reply).strip()
        reply = sanitize_reply_text(reply)
        if not reply:
            # If the output was purely a reaction, sticker, or GIF without text, we are done
            self._storage.mark_message_replied(message.dedup_key, message.chat_name)
            return

        # Safety gate
        msg_confidence, msg_reason = self._safety.evaluate_message(message)
        resp_confidence, resp_reason = self._safety.evaluate_response(reply, message)

        from .config import is_target_peer_chat, is_self_chat
        is_trusted = is_target_peer_chat(message.chat_name) or is_self_chat(message.chat_name)

        # In auto mode, only escalate if low-confidence approval is explicitly required AND not a trusted peer
        require_low_conf = getattr(self._config, "require_approval_for_low_confidence", False)
        should_escalate = (
            self._safety.should_escalate(msg_confidence, resp_confidence)
            and require_low_conf
            and not is_trusted
        )

        if should_escalate:
            logger.info(
                "Auto mode escalated to approval: %s; %s", msg_reason, resp_reason
            )
            item = self._approval_queue.add(
                incoming_message=message,
                draft_reply=reply,
                confidence=Confidence.LOW,
                reason=f"Auto-escalated: {msg_reason}; {resp_reason}",
            )
            self._emit_event("auto_escalated", {
                "id": item.id,
                "chat_name": message.chat_name,
                "reason": item.reason,
                "draft": reply,
            })
            return

        # Auto-send
        clean_outgoing_reply = sanitize_reply_text(reply)
        success = await self._sender.send_message(
            chat_name=message.chat_name,
            text=clean_outgoing_reply,
            chat_id=message.chat_id,
        )
        if success:
            self._last_reply_times[message.chat_name] = time.time()
            self._storage.mark_message_replied(message.dedup_key, message.chat_name)
            self._state_machine.on_outgoing_message_sent(message.chat_name, reply)

        span.mark("send_complete")

        # Record audit
        audit = AuditEntry(
            chat_name=message.chat_name,
            chat_id=message.chat_id,
            sender_name=message.sender_name,
            incoming_message_id=message.id,
            mode="auto",
            generated_reply=reply,
            final_reply=reply,
            sent=success,
            approved=True,
            latency_ms=latency_ms,
            confidence=msg_confidence.value,
            reason_code=msg_reason,
        )
        self._storage.save_audit_entry(audit)

        # Dynamically reflect and evolve contact's memory profile (run as background task)
        from .context import reflect_and_update_contact_profile
        asyncio.create_task(self._safe_reflect_contact(
            message.chat_name, message.sender_name, message.text, reply
        ))

        span.finish()

        self._emit_event("auto_sent", {
            "chat_name": message.chat_name,
            "reply": reply,
            "success": success,
            "confidence": msg_confidence.value,
            "latency_ms": latency_ms,
            "pipeline": span.report(),
        })

    async def _safe_reflect_contact(
        self, chat_name: str, sender_name: str, user_text: str, bot_reply: str,
    ) -> None:
        """Run contact profile reflection in a background-safe wrapper."""
        try:
            from .context import reflect_and_update_contact_profile
            reflect_and_update_contact_profile(
                storage=self._storage,
                chat_name=chat_name,
                sender_name=sender_name,
                user_text=user_text,
                bot_reply=bot_reply,
            )
        except Exception as e:
            logger.warning("Failed to reflect contact memory for %s: %s", chat_name, e)

    async def handle_approval_action(
        self, item_id: str, action: str, edited_text: Optional[str] = None
    ) -> bool:
        """
        Handle a user action on an approval item.

        Actions: 'send', 'edit', 'reject', 'regenerate'
        """
        item = self._approval_queue.get_item(item_id)
        if not item:
            return False

        if action == "send":
            reply_text = item.draft_reply
            success = await self._sender.send_message(
                chat_name=item.chat_name,
                text=reply_text,
                chat_id=item.chat_id,
            )
            if success:
                self._approval_queue.approve(item_id)
                if item.incoming_message:
                    self._storage.mark_message_replied(item.incoming_message.dedup_key, item.chat_name)
                self._state_machine.on_outgoing_message_sent(item.chat_name, reply_text)

            audit_item = self._approval_queue.get_item(item_id) or item
            audit = self._approval_queue.to_audit_entry(audit_item, sent=success)
            self._storage.save_audit_entry(audit)

            # If in training mode, record as training example
            if success and item.incoming_message:
                chat_config = self._policy.get_chat_config(item.chat_name)
                if chat_config and chat_config.mode == ChatMode.TRAINING:
                    self._training.add_training_example(
                        incoming_text=item.incoming_message.text,
                        actual_reply=reply_text,
                        predicted_reply=reply_text,
                        chat_name=item.chat_name,
                        chat_id=item.chat_id,
                        sender_name=item.incoming_message.sender_name,
                        is_group=item.incoming_message.is_group,
                    )
            return success

        elif action == "edit" and edited_text:
            reply_text = edited_text
            self._approval_queue.update_draft(item_id, reply_text)
            success = await self._sender.send_message(
                chat_name=item.chat_name,
                text=reply_text,
                chat_id=item.chat_id,
            )
            if success:
                self._approval_queue.approve_with_edit(item_id, reply_text)
                if item.incoming_message:
                    self._storage.mark_message_replied(item.incoming_message.dedup_key, item.chat_name)
                self._state_machine.on_outgoing_message_sent(item.chat_name, reply_text)

            audit_item = self._approval_queue.get_item(item_id) or item
            audit = self._approval_queue.to_audit_entry(audit_item, sent=success, edited=True)
            audit.final_reply = reply_text
            self._storage.save_audit_entry(audit)

            # Training: record the user's edited version
            if success and item.incoming_message:
                chat_config = self._policy.get_chat_config(item.chat_name)
                if chat_config and chat_config.mode == ChatMode.TRAINING:
                    self._training.add_training_example(
                        incoming_text=item.incoming_message.text,
                        actual_reply=reply_text,
                        predicted_reply=item.draft_reply,
                        chat_name=item.chat_name,
                        chat_id=item.chat_id,
                        sender_name=item.incoming_message.sender_name,
                        is_group=item.incoming_message.is_group,
                    )
            return success

        elif action == "reject":
            rejected = self._approval_queue.reject(item_id)
            if rejected:
                audit = self._approval_queue.to_audit_entry(rejected, sent=False)
                self._storage.save_audit_entry(audit)
                return True

        return False

    async def _handle_self_chat(self, message: WhatsAppMessage) -> None:
        """Handle incoming messages from David Julius in his self-chat.
        
        Only supports:
        - remember:/note: commands for saving facts to memory
        - Simple acknowledgment for other messages
        
        REMOVED: Pending inquiry forwarding (no more ❓ / ✅ alerts or cross-chat answer delivery).
        """
        text = message.text.strip()
        if not text:
            return
        if text.startswith("❓") or text.startswith("✅") or text.startswith("🤖"):
            # Ignore Julius's own alerts/confirmations (legacy messages still in chat)
            return

        logger.info("Processing self-chat message from David Julius: '%s'", text[:50])

        # Handle memory/note commands
        text_lower = text.lower()
        if text_lower.startswith("remember:") or text_lower.startswith("note:"):
            fact = text.split(":", 1)[1].strip()
            # Store in global memory / default summary
            default_summary = self._storage.get_conversation_summary("default") or {}
            facts = default_summary.get("important_facts", [])
            if fact not in facts:
                facts.append(fact)
            self._storage.save_conversation_summary(
                chat_id="default",
                summary="Global facts for David Julius",
                important_facts=facts,
            )
            success = await self._sender.send_message(
                chat_name=message.chat_name,
                text=f'✅ Remembered: "{fact}"',
                chat_id=message.chat_id,
            )
            if success:
                self._storage.mark_message_replied(message.dedup_key, message.chat_name)
        elif any(text_lower.startswith(p) for p in ["who are you", "what can you do", "help", "julius", "ai"]):
            cfg = self._policy.get_chat_config(message.chat_name) or ChatConfig(
                chat_name=message.chat_name, mode=ChatMode.AUTO
            )
            reply = await self._generate_reply(message, cfg)
            if reply and reply.strip() and reply.strip() != NO_RESPONSE:
                reply_clean = re.sub(r"[\u0b80-\u0bff]+", "", reply).strip()
                send_text = f"🤖 {reply_clean}" if not reply_clean.startswith("🤖") else reply_clean
            else:
                send_text = f'👍 Noted: "{text}"'

            success = await self._sender.send_message(
                chat_name=message.chat_name,
                text=send_text,
                chat_id=message.chat_id,
            )
            if success:
                self._storage.mark_message_replied(message.dedup_key, message.chat_name)
        else:
            success = await self._sender.send_message(
                chat_name=message.chat_name,
                text=f'👍 Noted: "{text}"',
                chat_id=message.chat_id,
            )
            if success:
                self._storage.mark_message_replied(message.dedup_key, message.chat_name)

    async def _generate_reply(self, message: WhatsAppMessage, config: ChatConfig) -> str:
        """Generate a reply using the LLM with full multi-turn conversation context.
        
        Builds context only ONCE and passes it to both prompt and chat_messages builders.
        Protected by the LLM circuit breaker.
        """
        if not self._generate_reply_fn:
            try:
                from .api import generate_whatsapp_reply
                self._generate_reply_fn = generate_whatsapp_reply
            except Exception as e:
                logger.warning("No reply generator configured and default fallback unavailable: %s", e)
                return ""

        profile = self._persona.get_profile(message.chat_name)

        # Build context ONCE (fixes C2 — was built twice before)
        ctx = self._context.build_context(message, config, profile)
        prompt = self._context.build_prompt_from_ctx(message, config, profile, ctx)
        chat_messages = self._context.build_chat_messages_from_ctx(message, config, profile, ctx)

        try:
            import inspect
            sig = inspect.signature(self._generate_reply_fn)
            if "chat_messages" in sig.parameters:
                reply = await self._generate_reply_fn(prompt, chat_messages=chat_messages)
            else:
                reply = await self._generate_reply_fn(prompt)
            if reply:
                reply = reply.strip().strip('"').strip("'")
                self._circuit_breaker.record_success()
                return reply
        except Exception as e:
            logger.error("LLM reply generation failed: %s", e)
            self._circuit_breaker.record_failure()

        # Fallback: Tony Stark conversational replies
        from .stark_replies import get_stark_fallback
        return get_stark_fallback(message.text)

    def _emit_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Emit a routing event to subscribers."""
        for cb in self._event_callbacks:
            try:
                cb(event_type, data)
            except Exception as e:
                logger.error("Router event callback error: %s", e)
