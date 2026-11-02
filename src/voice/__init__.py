"""Julius voice subsystem — live voice conversation engine.

Provides bidirectional voice conversation:
  - **STT** (Speech-to-Text): Microphone → text via ``speech_recognition``.
  - **TTS** (Text-to-Speech): Text → audio via macOS ``say`` command.
  - **VoiceManager**: Central orchestrator for per-session voice state.

Usage from ``julius_gui.py``::

    from src.voice import VoiceManager

    vm = VoiceManager()
    vm.start_session(session_id)
    text = await vm.transcribe(session_id, audio_bytes)
    audio = await vm.speak(session_id, "Hello!")
"""

from __future__ import annotations

from .voice_manager import VoiceManager, VoiceSession
from .tts_engine import TTSEngine, VoiceModelConfig, CustomVoiceAdapter
from .stt_engine import STTEngine, STTConfig

__all__ = [
    'VoiceManager',
    'VoiceSession',
    'TTSEngine',
    'VoiceModelConfig',
    'CustomVoiceAdapter',
    'STTEngine',
    'STTConfig',
]
