"""Text-to-Speech engine for Julius voice conversations.

Uses the macOS ``say`` command to generate audio.  The ``say`` command
can write AIFF files directly; we then convert to WAV for browser playback
using the ``scipy`` library (or fall back to raw subprocess + afconvert).

Design goals:
  - Zero external API keys — uses system voices.
  - Pluggable custom voice adapter for user-provided voice models.
  - Async-friendly: all I/O runs in an executor.
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import subprocess
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


# ── Configuration ─────────────────────────────────────────────────────────────

@dataclass
class VoiceModelConfig:
    """Configuration for a voice model.

    For the built-in macOS voice, only ``voice_name`` and ``rate`` matter.
    For a custom voice model, ``model_path`` points to the model file and
    ``adapter_class`` names the CustomVoiceAdapter subclass to load.
    """
    voice_name: str = 'Samantha'
    rate: int = 185                # words per minute (say -r flag)
    pitch: int = 50                # 0-100 (not used by macOS say, reserved for custom)
    model_path: str = ''           # path to custom voice model file
    adapter_class: str = ''        # e.g. 'my_voice_adapter.MyAdapter'


# ── Abstract adapter for custom voice models ──────────────────────────────────

class CustomVoiceAdapter(ABC):
    """Base class for plugging in a custom TTS voice model.

    To add your own voice:
    1. Create a subclass of ``CustomVoiceAdapter`` in ``custom_voice_models/``.
    2. Implement ``synthesise(text) → bytes`` returning WAV audio.
    3. Set ``JULIUS_VOICE_ADAPTER`` env var to your class path.
    """

    @abstractmethod
    def load(self, model_path: str) -> None:
        """Load the voice model from disk."""
        ...

    @abstractmethod
    def synthesise(self, text: str) -> bytes:
        """Convert text to WAV audio bytes."""
        ...


# ── macOS TTS Engine ──────────────────────────────────────────────────────────

class SarvamVoiceAdapter(CustomVoiceAdapter):
    """Adapter for Sarvam AI Bulbul TTS."""

    def __init__(self, target_language_code: str = "ta-IN", speaker: str = "anushka") -> None:
        self.target_language_code = target_language_code
        self.speaker = speaker

    def load(self, model_path: str) -> None:
        pass

    def synthesise(self, text: str) -> bytes:
        from src.services.sarvam_service import get_sarvam_service
        sarvam = get_sarvam_service()
        return sarvam.text_to_speech(
            text=text,
            target_language_code=self.target_language_code,
            speaker=self.speaker,
            model="bulbul:v2",
        )


class TTSEngine:
    """
    Text-to-Speech engine using macOS ``say`` command or Sarvam AI.

    Usage::

        engine = TTSEngine()
        wav_bytes = await engine.speak("Hello, I am Julius.")
    """

    def __init__(self, config: VoiceModelConfig | None = None) -> None:
        self.config = config or VoiceModelConfig()
        self._custom_adapter: CustomVoiceAdapter | None = None

        # If a custom adapter is configured, try to load it
        if self.config.adapter_class:
            self._load_custom_adapter()

        logger.info(
            'TTSEngine initialised (voice=%s, rate=%d, custom=%s)',
            self.config.voice_name,
            self.config.rate,
            bool(self._custom_adapter),
        )

    # ── Public API ────────────────────────────────────────────────────────────

    async def speak(self, text: str) -> bytes:
        """Convert text to WAV audio bytes.

        Args:
            text: The text to speak.

        Returns:
            WAV audio data as bytes, ready for browser playback.
        """
        if not text or not text.strip():
            return b''

        loop = asyncio.get_running_loop()

        # Use custom adapter if available
        if self._custom_adapter:
            return await loop.run_in_executor(
                None, self._custom_adapter.synthesise, text,
            )

        # Check if Sarvam API key is present and text contains Indic characters or Sarvam requested
        from src.services.sarvam_service import is_sarvam_available, get_sarvam_service
        if is_sarvam_available():
            # Check for non-ASCII/Indic characters or voice_name == 'Sarvam'
            is_indic = any(ord(char) > 127 for char in text)
            if is_indic or self.config.voice_name.lower() == 'sarvam':
                try:
                    sarvam_adapter = SarvamVoiceAdapter()
                    return await loop.run_in_executor(None, sarvam_adapter.synthesise, text)
                except Exception as exc:
                    logger.warning('Sarvam TTS failed, falling back to macOS say: %s', exc)

        # Otherwise use macOS say
        return await loop.run_in_executor(None, self._speak_macos, text)

    def get_available_voices(self) -> list[str]:
        """List available macOS voices."""
        try:
            result = subprocess.run(
                ['say', '--voice', '?'],
                capture_output=True,
                text=True,
                timeout=5,
            )
            voices = []
            for line in result.stdout.strip().split('\n'):
                if line.strip():
                    # Format: "VoiceName   locale   # description"
                    name = line.split()[0].strip()
                    voices.append(name)
            return voices
        except Exception as exc:
            logger.error('Could not list voices: %s', exc)
            return []

    def set_voice(self, voice_name: str) -> None:
        """Change the active voice."""
        self.config.voice_name = voice_name
        logger.info('Voice changed to: %s', voice_name)

    def set_rate(self, rate: int) -> None:
        """Change the speech rate (words per minute)."""
        self.config.rate = max(80, min(400, rate))
        logger.info('Speech rate changed to: %d', self.config.rate)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _speak_macos(self, text: str) -> bytes:
        """Generate audio using macOS ``say`` command.

        Pipeline: say → AIFF file → afconvert → WAV bytes
        """
        aiff_path = None
        wav_path = None
        try:
            # Create temp file for AIFF output
            fd, aiff_path = tempfile.mkstemp(suffix='.aiff')
            os.close(fd)
            wav_path = aiff_path.replace('.aiff', '.wav')

            # Generate AIFF using say
            result = subprocess.run(
                [
                    'say',
                    '-v', self.config.voice_name,
                    '-r', str(self.config.rate),
                    '-o', aiff_path,
                    text,
                ],
                capture_output=True,
                timeout=30,
            )

            if result.returncode != 0:
                logger.error(
                    'say command failed: %s',
                    result.stderr.decode()[:200],
                )
                return b''

            # Convert AIFF → WAV using afconvert (macOS built-in)
            result = subprocess.run(
                [
                    'afconvert',
                    '-f', 'WAVE',
                    '-d', 'LEI16@16000',
                    aiff_path,
                    wav_path,
                ],
                capture_output=True,
                timeout=15,
            )

            if result.returncode != 0:
                # Fallback: try ffmpeg
                logger.warning('afconvert failed, trying ffmpeg...')
                result = subprocess.run(
                    [
                        'ffmpeg', '-y', '-i', aiff_path,
                        '-ar', '16000', '-ac', '1', '-f', 'wav',
                        wav_path,
                    ],
                    capture_output=True,
                    timeout=15,
                )
                if result.returncode != 0:
                    logger.error('Audio conversion failed')
                    return b''

            # Read the WAV file
            with open(wav_path, 'rb') as f:
                wav_bytes = f.read()

            logger.info('TTS generated %d bytes of audio', len(wav_bytes))
            return wav_bytes

        except subprocess.TimeoutExpired:
            logger.error('TTS timed out')
            return b''
        except Exception as exc:
            logger.error('TTS error: %s', exc)
            return b''
        finally:
            # Cleanup temp files
            for p in (aiff_path, wav_path):
                if p:
                    try:
                        os.unlink(p)
                    except Exception:
                        pass

    def _load_custom_adapter(self) -> None:
        """Dynamically load a custom voice adapter class."""
        try:
            module_path, class_name = self.config.adapter_class.rsplit('.', 1)
            import importlib
            module = importlib.import_module(module_path)
            adapter_cls = getattr(module, class_name)
            self._custom_adapter = adapter_cls()
            if self.config.model_path:
                self._custom_adapter.load(self.config.model_path)
            logger.info('Custom voice adapter loaded: %s', self.config.adapter_class)
        except Exception as exc:
            logger.error('Failed to load custom voice adapter: %s', exc)
            self._custom_adapter = None
