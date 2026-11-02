"""
Julius WhatsApp Integration — Top-Level Service Orchestrator.

Integrates all WhatsApp subsystems: browser adapter, session manager,
listener, sender, policy engine, context, persona, training, safety gate,
approval queue, router, health monitoring, and watchdog.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Set

from .approval import ApprovalQueue
from .browser import WhatsAppBrowserAdapter
from .config import WhatsAppConfig
from .context import ConversationContext
from .health import WhatsAppHealth
from .listener import WhatsAppEventListener
from .models import (
    ApprovalItem,
    ChatConfig,
    ChatMode,
    Confidence,
    HealthState,
    StyleProfile,
    TrainingExample,
    WhatsAppMessage,
)
from .persona import PersonaEngine
from .policy import ChatPolicyEngine
from .router import WhatsAppMessageRouter
from .safety import SafetyGate
from .sender import WhatsAppSender
from .session import WhatsAppSession
from .storage import WhatsAppStorage
from .supervisor import SupervisorConfig, WhatsAppSupervisor
from .training import TrainingManager
from .watchdog import WhatsAppWatchdog

logger = logging.getLogger(__name__)


class WhatsAppService:
    """
    Top-level WhatsApp personal assistant service for Julius.
    """

    def __init__(
        self,
        config: Optional[WhatsAppConfig] = None,
        db_path: Optional[str] = None,
        profile_dir: Optional[str] = None,
    ) -> None:
        self._config = config or WhatsAppConfig.from_env()
        if profile_dir:
            self._config.profile_dir = profile_dir

        self._storage = WhatsAppStorage(db_path=db_path)
        self._session = WhatsAppSession(profile_dir=self._config.profile_dir)
        self._browser = WhatsAppBrowserAdapter(
            profile_dir=self._config.profile_dir,
            headless=self._config.headless,
        )
        from .adapter import WhatsAppAdapter
        from .conversation_state import ConversationStateMachine
        from .knowledge import PersonalKnowledgeEngine
        from .style_learner import CommunicationStyleLearner

        self._adapter = WhatsAppAdapter(browser=self._browser)
        self._health = WhatsAppHealth()
        self._sender = WhatsAppSender(
            browser=self._browser,
            storage=self._storage,
            config=self._config,
            adapter=self._adapter,
        )
        self._policy = ChatPolicyEngine(
            storage=self._storage,
            config=self._config,
        )
        self._context = ConversationContext(storage=self._storage)
        self._persona = PersonaEngine(storage=self._storage)
        self._training = TrainingManager(
            storage=self._storage,
            persona_engine=self._persona,
        )
        self._safety = SafetyGate()
        self._approval_queue = ApprovalQueue()

        self._state_machine = ConversationStateMachine(storage=self._storage)
        self._knowledge_engine = PersonalKnowledgeEngine(storage=self._storage)
        self._style_learner = CommunicationStyleLearner(
            storage=self._storage,
            persona=self._persona,
        )

        self._router = WhatsAppMessageRouter(
            policy=self._policy,
            sender=self._sender,
            storage=self._storage,
            config=self._config,
            context=self._context,
            persona=self._persona,
            training=self._training,
            safety=self._safety,
            approval_queue=self._approval_queue,
            state_machine=self._state_machine,
            knowledge_engine=self._knowledge_engine,
            style_learner=self._style_learner,
        )

        self._listener = WhatsAppEventListener(
            browser=self._browser,
            storage=self._storage,
        )

        supervisor_config = SupervisorConfig.from_config(self._config)
        self._supervisor = WhatsAppSupervisor(
            browser=self._browser,
            health=self._health,
            restart_callback=self._restart_subsystem,
            listener=self._listener,
            config=supervisor_config,
            check_interval_seconds=float(self._config.watchdog_interval),
        )
        self._watchdog = self._supervisor

        # Adaptive message debouncer — accumulates rapid-fire messages
        # before dispatching to the router (prevents multiple LLM calls
        # for burst messages like "dei" / "where are you" / "coming?")
        from .debouncer import MessageDebouncer
        self._debouncer = MessageDebouncer(
            dispatch_fn=self._dispatch_to_router,
        )

        self._subscribers: List[Callable[[str, Dict[str, Any]], None]] = []
        self._is_started = False
        self._chat_locks: Dict[str, asyncio.Lock] = {}
        self._ensure_target_contacts_configured()
        self._init_subscribers()

    def _ensure_target_contacts_configured(self) -> None:
        """Ensure all priority contacts are seeded in AUTO mode."""
        from .config import TARGET_PEERS_CONFIG
        for peer in TARGET_PEERS_CONFIG:
            canonical = peer["canonical"]
            all_names = [canonical] + [a for a in peer["aliases"] if a != canonical]
            for name in all_names:
                existing = self._storage.get_chat_config(name)
                if not existing:
                    cfg = ChatConfig(
                        chat_name=name,
                        enabled=True,
                        mode=ChatMode.AUTO,
                        persona=f"Julius Assistant chatting with {canonical}",
                        auto_reply_delay_min=0.0,
                        auto_reply_delay_max=0.0,
                        max_messages_per_hour=200,
                        context_window=35,
                        memory_enabled=True,
                    )
                    self._storage.save_chat_config(cfg)
                    logger.info("Initialized priority contact '%s' in AUTO mode", name)
                elif existing.mode != ChatMode.AUTO or not existing.enabled:
                    existing.mode = ChatMode.AUTO
                    existing.enabled = True
                    existing.auto_reply_delay_min = 0.0
                    existing.auto_reply_delay_max = 0.0
                    existing.context_window = max(existing.context_window, 35)
                    existing.memory_enabled = True
                    self._storage.save_chat_config(existing)
        self._policy.reload()

    def _init_subscribers(self) -> None:
        """Connect internal event emitters to the public event broadcaster."""
        # Router events
        self._router.subscribe_events(
            lambda evt, data: self._emit_event(f"router:{evt}", data)
        )

        # Approval queue events
        self._approval_queue.subscribe(
            lambda action, item: self._emit_event(
                f"approval:{action}",
                item.to_dict() if item else {},
            )
        )

        # Listener incoming messages -> router (dispatch non-blocking so listener loop never stalls)
        self._listener.subscribe(lambda msg: asyncio.create_task(self._on_incoming_message(msg)))

    def subscribe_events(self, callback: Callable[[str, Dict[str, Any]], None]) -> None:
        """Register a subscriber for all WhatsApp subsystem events."""
        self._subscribers.append(callback)

    def _emit_event(self, event_name: str, data: Dict[str, Any]) -> None:
        """Broadcast an event to all subscribers."""
        for sub in self._subscribers:
            try:
                res = sub(event_name, data)
                if asyncio.iscoroutine(res):
                    asyncio.create_task(res)
            except Exception as e:
                logger.debug("Error in WhatsApp subscriber callback: %s", e)

    async def _on_incoming_message(self, message: WhatsAppMessage) -> None:
        """Handle message emitted by the listener.
        
        Dispatches directly to router with per-chat FIFO lock serialization.
        """
        self._health.record_event()
        if hasattr(self, "_supervisor") and self._supervisor:
            self._supervisor.update_heartbeat("last_message_received")
        self._emit_event("message_received", message.to_dict())
        await self._dispatch_to_router(message)

    async def _dispatch_to_router(self, message: WhatsAppMessage) -> None:
        """Dispatch a (possibly debounced/merged) message to the router.
        
        Per-chat FIFO serialization via asyncio.Lock ensures messages
        within the same chat are processed sequentially, while different
        chats process concurrently.
        """
        chat_key = message.chat_name.lower().strip()
        if chat_key not in self._chat_locks:
            self._chat_locks[chat_key] = asyncio.Lock()

        async with self._chat_locks[chat_key]:
            if hasattr(self, "_supervisor") and self._supervisor:
                self._supervisor.update_heartbeat("last_processing_started")
            await self._router.route_message(message)
            if hasattr(self, "_supervisor") and self._supervisor:
                self._supervisor.update_heartbeat("last_processing_completed")
                self._supervisor.update_heartbeat("last_end_to_end_success")

    async def _restart_subsystem(self) -> None:
        """Restart browser adapter and listener after failure."""
        logger.warning("Restarting WhatsApp browser subsystem...")
        try:
            await self._listener.stop()
        except Exception:
            pass

        try:
            await self._browser.stop()
        except Exception:
            pass

        await asyncio.sleep(2.0)
        await self._browser.start()

        # Update monitored chats
        active_names = {c.chat_name for c in self._policy.get_all_configs() if c.enabled}
        self._listener.set_monitored_chats(active_names)
        await self._listener.start()
        logger.info("WhatsApp browser subsystem restarted successfully")

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the WhatsApp integration."""
        if self._is_started:
            return

        logger.info("Starting WhatsApp service (profile: %s)...", self._config.profile_dir)
        self._health.record_start()
        self._is_started = True

        try:
            # 1. Start browser
            await self._browser.start()
            self._health.update_browser(alive=True, ready=True)

            # 2. Check login state
            login_state = await self._browser.detect_login_state()
            if login_state == "connected":
                self._health.set_authenticated(True)
                self._session.mark_connected()
            elif login_state == "qr_required":
                self._health.set_state(HealthState.WAITING_FOR_QR)

            # 3. Refresh policies and configure listener
            active_names = {c.chat_name for c in self._policy.get_all_configs() if c.enabled}
            self._listener.set_monitored_chats(active_names)

            # 4. Start listener
            await self._listener.start()
            self._health.set_listener_running(True)
            logger.info("WhatsApp service initial start complete (state: %s)", self._health.state.value)

        except Exception as e:
            logger.error("Initial start of WhatsApp browser/listener failed: %s", e, exc_info=True)
            self._health.record_error(f"Startup issue: {e}")
            self._health.set_state(HealthState.ERROR)
        finally:
            # ALWAYS start the supervisor so the system continuously self-heals
            # and revives after interruptions or cold boot errors
            try:
                await self._supervisor.start()
                self._health.set_watchdog_running(True)
            except Exception as w_err:
                logger.error("Failed to start supervisor: %s", w_err)
            self._emit_event("status", self.get_health())

    async def stop(self) -> None:
        """Stop the WhatsApp integration."""
        if not self._is_started:
            return

        logger.info("Stopping WhatsApp service...")
        self._is_started = False

        try:
            await self._supervisor.stop()
        except Exception as e:
            logger.debug("Error stopping supervisor: %s", e)

        try:
            await self._listener.stop()
        except Exception as e:
            logger.debug("Error stopping listener: %s", e)

        try:
            await self._browser.stop()
        except Exception as e:
            logger.debug("Error stopping browser: %s", e)

        self._health.record_stop()
        self._session.mark_disconnected()
        logger.info("WhatsApp service stopped")
        self._emit_event("status", self.get_health())

    def pause(self) -> None:
        """Pause message routing and outbound sending."""
        self._router.pause()
        self._sender.pause()
        logger.info("WhatsApp service paused")
        self._emit_event("paused", {})

    def resume(self) -> None:
        """Resume message routing and outbound sending."""
        self._router.resume()
        self._sender.resume()
        logger.info("WhatsApp service resumed")
        self._emit_event("resumed", {})

    def emergency_stop(self) -> int:
        """
        Emergency stop: immediately pause all processing and clear pending approvals.
        Returns the number of cancelled approval items.
        """
        logger.warning("EMERGENCY STOP requested on WhatsApp service")
        self.pause()
        cleared = self._approval_queue.clear_all()
        self._health.set_state(HealthState.STOPPED)
        self._emit_event("emergency_stopped", {"cleared_approvals": cleared})
        return cleared

    # ── QR & Connection ───────────────────────────────────────────────────────

    async def get_qr_image(self, force_reload: bool = False) -> Optional[str]:
        """Get base64 QR code image if currently waiting for QR scan."""
        return await self._browser.get_qr_code_image(force_reload=force_reload)

    async def screenshot(self) -> Optional[bytes]:
        """Take a full-page screenshot of WhatsApp Web."""
        return await self._browser.screenshot()

    async def send_message(self, chat_name: str, text: str, chat_id: str = "") -> bool:
        """Send a message to a chat directly."""
        if hasattr(self, "_supervisor") and self._supervisor:
            self._supervisor.update_heartbeat("last_send_attempt")
        result = await self._sender.send_message(chat_name=chat_name, text=text, chat_id=chat_id)
        if result and hasattr(self, "_supervisor") and self._supervisor:
            self._supervisor.update_heartbeat("last_successful_send")
        return result

    async def send_image(self, chat_name: str, file_path: str, caption: str = "", chat_id: str = "") -> bool:
        """Send an image to a chat directly using WhatsAppAdapter."""
        return await self._sender.send_image(chat_name=chat_name, file_path=file_path, caption=caption, chat_id=chat_id)

    async def send_document(self, chat_name: str, file_path: str, caption: str = "", chat_id: str = "") -> bool:
        """Send a document or PDF to a chat directly using WhatsAppAdapter."""
        return await self._sender.send_document(chat_name=chat_name, file_path=file_path, caption=caption, chat_id=chat_id)

    async def send_media(self, chat_name: str, file_path: str, media_type: str = "auto", caption: str = "", chat_id: str = "") -> bool:
        """Send media (image, document, PDF) to a chat directly using WhatsAppAdapter."""
        return await self._sender.send_media(chat_name=chat_name, file_path=file_path, media_type=media_type, caption=caption, chat_id=chat_id)

    async def sync_chat_history(self, chat_name: str, max_scrolls: int = 5) -> int:
        """
        Ingest historical messages from WhatsApp Web for chat_name,
        store them into SQLite storage, update conversational context & memory,
        and fine-tune David's persona style profile.

        Returns the number of messages successfully ingested.
        """
        if not self._browser.is_connected:
            logger.warning("Cannot sync history: WhatsApp not connected")
            return 0

        raw_messages = await self._browser.fetch_chat_history(chat_name, max_scrolls=max_scrolls)
        if not raw_messages:
            logger.info("No messages found in history for '%s'", chat_name)
            return 0

        # Resolve chat config and chat_id
        config = self._policy.get_chat_config(chat_name)
        chat_id = config.chat_id if config and config.chat_id else f"chat_{chat_name.lower().replace(' ', '_')}"
        is_group = isinstance(chat_id, str) and chat_id.endswith("@g.us")

        saved_count = 0
        user_messages = []
        for idx, m in enumerate(raw_messages):
            msg_text = m.get("text", "").strip()
            if not msg_text:
                continue
            sender = m.get("sender") or ("David" if m.get("is_from_me") else chat_name)
            msg_id = f"hist_{chat_id}_{int(time.time())}_{idx}"

            sender_id = "me" if m.get("is_from_me") else f"user_{sender.lower().replace(' ', '_')}"
            wa_msg = WhatsAppMessage(
                id=msg_id,
                chat_id=chat_id,
                chat_name=chat_name,
                sender_id=sender_id,
                sender_name=sender,
                text=msg_text,
                is_from_me=bool(m.get("is_from_me")),
                is_group=is_group,
                quoted_text=m.get("quoted_text"),
                timestamp=time.time() - (len(raw_messages) - idx) * 60,
            )
            self._storage.save_message(wa_msg)
            saved_count += 1
            if wa_msg.is_from_me:
                user_messages.append(msg_text)

        # Train style profile if user has sent messages in this chat
        if user_messages:
            self._training.train_from_chat_history(user_messages)
            logger.info("Updated David's style profile from %d user messages in '%s'", len(user_messages), chat_name)

        # Build initial summary from historical messages
        recent = self._storage.get_recent_messages(chat_id, limit=30)
        if recent:
            summary_lines = []
            for r in recent[-10:]:
                p = "David" if r.get("is_from_me") else r.get("sender_name", "Other")
                summary_lines.append(f"{p}: {r.get('text', '')}")
            quick_summary = "Recent discussion topics:\n" + "\n".join(summary_lines)
            self._context.update_summary(
                chat_id=chat_id,
                summary=quick_summary,
                important_facts=[f"Chat history synchronized with {saved_count} messages."],
            )

        logger.info("Synchronized %d historical messages for '%s'", saved_count, chat_name)
        self._emit_event("history_synced", {"chat_name": chat_name, "message_count": saved_count})
        return saved_count

    def get_health(self) -> Dict[str, Any]:
        """Get comprehensive health snapshot."""
        active_count = len(self._policy.get_all_configs())
        pending_count = self._approval_queue.pending_count
        self._health.update_counts(active_chats=active_count, pending_approvals=pending_count)
        data = self._health.to_dict()
        if hasattr(self, "_supervisor") and self._supervisor:
            data["supervisor"] = self._supervisor.get_diagnostics()
            if self._supervisor.last_snapshot:
                data["subsystems"] = self._supervisor.last_snapshot.to_dict()
        return data

    @property
    def supervisor(self) -> WhatsAppSupervisor:
        return self._supervisor

    # ── Chat Policy Management ────────────────────────────────────────────────

    def get_chats(self) -> List[Dict[str, Any]]:
        """List all configured chats."""
        return [c.to_dict() for c in self._policy.get_all_configs()]

    def save_chat_config(self, chat_config: ChatConfig) -> None:
        """Add or update a chat configuration in allowlist."""
        self._storage.save_chat_config(chat_config)
        self._policy.reload()
        # Update listener monitored chats
        active_names = {c.chat_name for c in self._policy.get_all_configs() if c.enabled}
        self._listener.set_monitored_chats(active_names)
        self._emit_event("chat_updated", chat_config.to_dict())

        # If connected, trigger async historical context ingestion
        if self._browser.is_connected:
            asyncio.create_task(self.sync_chat_history(chat_config.chat_name))

    def remove_chat(self, chat_name: str) -> bool:
        """Remove a chat from the allowlist."""
        success = self._storage.delete_chat_config(chat_name)
        if success:
            self._policy.reload()
            active_names = {c.chat_name for c in self._policy.get_all_configs() if c.enabled}
            self._listener.set_monitored_chats(active_names)
            self._emit_event("chat_removed", {"chat_name": chat_name})
        return success

    # ── Approvals ─────────────────────────────────────────────────────────────

    def get_approvals(self) -> List[Dict[str, Any]]:
        """Get all pending approval items."""
        return [item.to_dict() for item in self._approval_queue.get_pending()]

    async def approve(self, item_id: str, edited_text: Optional[str] = None) -> bool:
        """
        Approve and send a pending draft reply.
        """
        item = self._approval_queue.get_item(item_id)
        if not item or item.status != "pending":
            logger.warning("Approval item %s not found or not pending", item_id)
            return False

        reply_text = edited_text if edited_text is not None else item.draft_reply
        was_edited = edited_text is not None and edited_text != item.draft_reply

        # Keep a draft pending until the send succeeds.  The prior flow marked
        # it approved first, making a transient browser failure unrecoverable.
        if was_edited:
            self._approval_queue.update_draft(item_id, reply_text)

        sent = await self._sender.send_message(
            chat_name=item.chat_name,
            text=reply_text,
            chat_id=item.chat_id,
        )

        if sent:
            if was_edited:
                self._approval_queue.approve_with_edit(item_id, reply_text)
            else:
                self._approval_queue.approve(item_id)
            self._health.record_send()
            self._storage.mark_message_replied(
                item.incoming_message.dedup_key, item.chat_name
            ) if item.incoming_message else None

        # Audit log entry
        audit_item = self._approval_queue.get_item(item_id) or item
        audit_entry = self._approval_queue.to_audit_entry(audit_item, sent=sent, edited=was_edited)
        self._storage.save_audit_entry(audit_entry)

        # Ingest into training if enabled
        if sent and item.incoming_message:
            training_ex = TrainingExample(
                incoming_text=item.incoming_message.text,
                predicted_reply=item.draft_reply,
                actual_reply=reply_text,
                chat_name=item.chat_name,
                chat_id=item.chat_id,
                sender_name=item.incoming_message.sender_name,
                is_group=item.incoming_message.is_group,
            )
            self._training.add_example(training_ex)

        return sent

    def reject(self, item_id: str) -> bool:
        """Reject a pending draft reply."""
        item = self._approval_queue.reject(item_id)
        if item:
            audit_entry = self._approval_queue.to_audit_entry(item, sent=False, edited=False)
            self._storage.save_audit_entry(audit_entry)
            return True
        return False

    # ── Training & Persona ────────────────────────────────────────────────────

    def get_training_stats(self) -> Dict[str, Any]:
        """Get training mode progress, stats, and curriculum status."""
        return self._training.get_stats()

    def submit_training_example(self, example: TrainingExample) -> None:
        """Submit a manual or captured training example."""
        self._training.add_example(example)

    def get_style_profile(self, chat_name: Optional[str] = None) -> StyleProfile:
        """Get the effective communication style profile."""
        return self._persona.get_profile(chat_name)

    def update_style_profile(self, profile: StyleProfile) -> None:
        """Update the default style profile."""
        self._persona.update_default_profile(profile)

    # ── Audit Log ─────────────────────────────────────────────────────────────

    def get_audit_log(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Fetch recent audit log entries."""
        entries = self._storage.get_audit_entries(limit=limit)
        return [e.to_dict() for e in entries]

    # ── LLM Hook ──────────────────────────────────────────────────────────────

    def set_reply_generator(self, fn: Callable) -> None:
        """Set custom LLM reply generator function for the router."""
        self._router.set_reply_generator(fn)

    # ── Context & Components Access ───────────────────────────────────────────

    @property
    def config(self) -> WhatsAppConfig:
        return self._config

    @property
    def storage(self) -> WhatsAppStorage:
        return self._storage

    @property
    def is_connected(self) -> bool:
        return self._browser.is_connected

    @property
    def adapter(self) -> Any:
        return self._adapter

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
    def sender(self) -> WhatsAppSender:
        return self._sender

    @property
    def router(self) -> WhatsAppMessageRouter:
        return self._router
