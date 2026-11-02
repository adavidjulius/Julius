"""Central voice manager for Julius live voice conversations — Full-Duplex v2.

Phase 4.1 — Milestone 4.1: Upgraded with:
  - Full-duplex conversation state tracking
  - Voice Activity Detection (VAD) with Silero VAD
  - Low-latency barge-in interruption handling (< 100ms cut)
  - Active TTS cancellation token and speaking status
  - Echo suppression and microphone energy gate
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .stt_engine import STTConfig, STTEngine
from .tts_engine import TTSEngine, VoiceModelConfig

logger = logging.getLogger(__name__)


# ── Voice session state ───────────────────────────────────────────────────────

@dataclass
class VoiceSession:
    """Per-session full-duplex voice state."""
    active: bool = False
    stt_engine: STTEngine | None = None
    tts_engine: TTSEngine | None = None
    is_speaking: bool = False
    interrupted: bool = False
    current_tts_task: Optional[asyncio.Task] = None


# ── Voice Manager ─────────────────────────────────────────────────────────────

class VoiceManager:
    """
    Central orchestrator for full-duplex voice conversations with barge-in support.

    One ``VoiceManager`` instance is shared across the application.
    Each WebSocket session gets its own ``VoiceSession`` tracked by session ID.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, VoiceSession] = {}

        # Load configuration from environment
        self._voice_name = os.getenv('JULIUS_VOICE_NAME', 'Samantha')
        self._voice_rate = int(os.getenv('JULIUS_VOICE_RATE', '185'))
        self._stt_language = os.getenv('JULIUS_STT_LANGUAGE', 'en-US')
        self._custom_model_path = os.getenv('JULIUS_VOICE_MODEL_PATH', '')
        self._custom_adapter_class = os.getenv('JULIUS_VOICE_ADAPTER', '')

        logger.info(
            'VoiceManager created (voice=%s, rate=%d, lang=%s)',
            self._voice_name,
            self._voice_rate,
            self._stt_language,
        )

    @property
    def is_enabled(self) -> bool:
        """Check if voice mode is enabled in configuration."""
        val = os.getenv('JULIUS_VOICE_ENABLED', 'true')
        return val.lower() in ('true', '1', 'yes')

    # ── Session lifecycle ─────────────────────────────────────────────────────

    def start_session(self, session_id: str) -> bool:
        """Initialise voice engines for a session."""
        if not self.is_enabled:
            logger.warning('Voice mode is disabled')
            return False

        if session_id in self._sessions and self._sessions[session_id].active:
            logger.info('Voice session %s already active', session_id[:8])
            return True

        try:
            stt_config = STTConfig(language=self._stt_language)
            stt_engine = STTEngine(config=stt_config)

            voice_config = VoiceModelConfig(
                voice_name=self._voice_name,
                rate=self._voice_rate,
                model_path=self._custom_model_path,
                adapter_class=self._custom_adapter_class,
            )
            tts_engine = TTSEngine(config=voice_config)

            self._sessions[session_id] = VoiceSession(
                active=True,
                stt_engine=stt_engine,
                tts_engine=tts_engine,
            )

            logger.info('Voice session started: %s', session_id[:8])
            return True

        except Exception as exc:
            logger.error('Failed to start voice session %s: %s', session_id[:8], exc)
            return False

    def stop_session(self, session_id: str) -> None:
        """Stop and clean up voice engines for a session."""
        session = self._sessions.pop(session_id, None)
        if session:
            session.active = False
            if session.current_tts_task and not session.current_tts_task.done():
                session.current_tts_task.cancel()
            logger.info('Voice session stopped: %s', session_id[:8])

    def is_active(self, session_id: str) -> bool:
        """Check if a voice session is currently active."""
        session = self._sessions.get(session_id)
        return session is not None and session.active

    def is_speaking(self, session_id: str) -> bool:
        """Check if speech audio is currently playing for this session."""
        session = self._sessions.get(session_id)
        return bool(session and session.is_speaking)

    def set_speaking(self, session_id: str, speaking: bool) -> None:
        """Update speaking status."""
        session = self._sessions.get(session_id)
        if session:
            session.is_speaking = speaking
            if speaking:
                session.interrupted = False

    # ── Barge-In Interruption ────────────────────────────────────────────────

    def interrupt(self, session_id: str) -> bool:
        """
        Barge-In Handler: Immediately stop ongoing speech synthesis and playback.
        Returns True if an active playback or synthesis was interrupted.
        """
        session = self._sessions.get(session_id)
        if not session or not session.active:
            return False

        was_speaking = session.is_speaking
        session.is_speaking = False
        session.interrupted = True

        if session.current_tts_task and not session.current_tts_task.done():
            session.current_tts_task.cancel()
            logger.info('TTS task cancelled for session %s (Barge-In)', session_id[:8])

        logger.info('Voice session %s interrupted (was_speaking=%s)', session_id[:8], was_speaking)
        return was_speaking

    def check_barge_in(self, session_id: str, audio_chunk: bytes) -> bool:
        """
        Check if incoming user speech should interrupt ongoing agent speech.
        Returns True if speech was detected and active speech was interrupted.
        """
        session = self._sessions.get(session_id)
        if not session or not session.active or not session.is_speaking:
            return False

        if session.stt_engine and session.stt_engine.detect_speech(audio_chunk):
            logger.info("Speech detected while speaking -> triggering Barge-In interrupt!")
            self.interrupt(session_id)
            return True

        return False

    # ── STT ───────────────────────────────────────────────────────────────────

    async def transcribe(self, session_id: str, audio_bytes: bytes, audio_format: str = 'wav') -> str:
        """Transcribe audio bytes to text."""
        session = self._sessions.get(session_id)
        if not session or not session.active or not session.stt_engine:
            logger.warning('No active voice session for STT: %s', session_id[:8])
            return ''

        if audio_format == 'webm':
            return await session.stt_engine.transcribe_webm(audio_bytes)
        return await session.stt_engine.transcribe_wav(audio_bytes)

    # ── TTS ───────────────────────────────────────────────────────────────────

    async def speak(self, session_id: str, text: str) -> bytes:
        """Convert text to audio bytes with cancellation and barge-in tracking."""
        session = self._sessions.get(session_id)
        if not session or not session.active or not session.tts_engine:
            logger.warning('No active voice session for TTS: %s', session_id[:8])
            return b''

        session.is_speaking = True
        session.interrupted = False

        try:
            task = asyncio.create_task(session.tts_engine.speak(text))
            session.current_tts_task = task
            audio_data = await task

            if session.interrupted:
                logger.info("Speech generation aborted due to barge-in interrupt: %s", session_id[:8])
                return b''

            return audio_data
        except asyncio.CancelledError:
            logger.info("Speech generation cancelled: %s", session_id[:8])
            return b''
        except Exception as exc:
            logger.error("TTS generation error: %s", exc)
            return b''
        finally:
            session.current_tts_task = None

    # ── Configuration ─────────────────────────────────────────────────────────

    def configure(self, session_id: str, **kwargs) -> dict:
        """Update voice configuration for a session."""
        session = self._sessions.get(session_id)
        if not session or not session.active:
            return {'error': 'No active voice session'}

        if 'voice_name' in kwargs and session.tts_engine:
            session.tts_engine.set_voice(kwargs['voice_name'])

        if 'rate' in kwargs and session.tts_engine:
            session.tts_engine.set_rate(kwargs['rate'])

        if 'language' in kwargs and session.stt_engine:
            session.stt_engine.config.language = kwargs['language']

        return {
            'voice_name': session.tts_engine.config.voice_name if session.tts_engine else '',
            'rate': session.tts_engine.config.rate if session.tts_engine else 0,
            'language': session.stt_engine.config.language if session.stt_engine else '',
        }

    def get_available_voices(self) -> list[str]:
        """List available TTS voices on this system."""
        engine = TTSEngine()
        return engine.get_available_voices()

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def cleanup_all(self) -> None:
        """Stop all voice sessions. Called during app shutdown."""
        for sid in list(self._sessions.keys()):
            self.stop_session(sid)
        logger.info('All voice sessions cleaned up')
