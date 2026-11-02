"""Speech-to-Text engine for Julius voice conversations — Full-Duplex v2.

Phase 4.1 — Milestone 4.1: Upgraded with:
  - Streaming VAD (Voice Activity Detection) via Silero VAD
  - Local faster-whisper / mlx-whisper support for low-latency transcription
  - Continuous microphone stream support for barge-in detection
  - Google Web Speech fallback

Design goals:
  - STT latency < 180ms with local Whisper
  - Streaming VAD for real-time barge-in detection
  - Thread-safe: heavy I/O in executor, event loop stays responsive
"""

from __future__ import annotations

import asyncio
import io
import logging
import wave
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

try:
    import speech_recognition as sr
except ImportError:
    sr = None

logger = logging.getLogger(__name__)


# ── Configuration ─────────────────────────────────────────────────────────────

@dataclass
class STTConfig:
    """Tuneable parameters for speech recognition."""
    language: str = 'en-US'
    energy_threshold: int = 300
    pause_threshold: float = 1.0        # seconds of silence to consider end-of-phrase
    phrase_time_limit: float | None = 30.0   # max seconds per phrase
    dynamic_energy: bool = True
    use_local_whisper: bool = True       # Prefer local whisper over Google
    whisper_model: str = 'base'          # tiny, base, small, medium, large
    vad_threshold: float = 0.5           # Silero VAD speech probability threshold
    vad_min_speech_ms: int = 250         # Minimum speech duration to trigger


# ── Silero VAD ────────────────────────────────────────────────────────────────

class SileroVAD:
    """Voice Activity Detection using Silero VAD model.

    Detects speech presence in audio chunks for barge-in detection.
    """

    def __init__(self, threshold: float = 0.5) -> None:
        self.threshold = threshold
        self._model = None
        self._available = False

        try:
            import torch
            model, utils = torch.hub.load(
                repo_or_dir='snakers4/silero-vad',
                model='silero_vad',
                force_reload=False,
                onnx=True,
            )
            self._model = model
            self._get_speech_timestamps = utils[0]
            self._available = True
            logger.info("Silero VAD loaded successfully")
        except Exception as exc:
            logger.info("Silero VAD not available: %s — using energy-based detection", exc)

    @property
    def is_available(self) -> bool:
        return self._available

    def detect_speech(self, audio_chunk: bytes, sample_rate: int = 16000) -> bool:
        """Check if audio chunk contains speech.

        Args:
            audio_chunk: Raw PCM audio bytes (16-bit, mono).
            sample_rate: Audio sample rate.

        Returns:
            True if speech is detected above the threshold.
        """
        if not self._available:
            return self._energy_fallback(audio_chunk)

        try:
            import torch
            import numpy as np

            # Convert bytes to float tensor
            audio_np = np.frombuffer(audio_chunk, dtype=np.int16).astype(np.float32) / 32768.0
            audio_tensor = torch.from_numpy(audio_np)

            # Get speech probability
            speech_prob = self._model(audio_tensor, sample_rate).item()
            return speech_prob > self.threshold

        except Exception as exc:
            logger.debug("VAD detection error: %s", exc)
            return self._energy_fallback(audio_chunk)

    def _energy_fallback(self, audio_chunk: bytes) -> bool:
        """Simple energy-based speech detection fallback."""
        import numpy as np
        try:
            audio = np.frombuffer(audio_chunk, dtype=np.int16)
            rms = float(np.sqrt(np.mean(audio.astype(np.float32) ** 2)))
            return rms > 500  # Basic energy threshold
        except Exception:
            return False


# ── Local Whisper Engine ──────────────────────────────────────────────────────

class LocalWhisperSTT:
    """Local Whisper transcription engine.

    Tries faster-whisper first (CTranslate2 backend, ~3x faster),
    then falls back to standard whisper or mlx-whisper on Apple Silicon.
    """

    def __init__(self, model_size: str = 'base', language: str = 'en') -> None:
        self.model_size = model_size
        self.language = language.split('-')[0] if '-' in language else language
        self._engine = None
        self._engine_type: str = "none"
        self._available = False

        self._init_engine()

    def _init_engine(self) -> None:
        """Initialize the best available Whisper engine."""
        # Try faster-whisper first (best performance)
        try:
            from faster_whisper import WhisperModel
            self._engine = WhisperModel(
                self.model_size,
                device="auto",
                compute_type="auto",
            )
            self._engine_type = "faster_whisper"
            self._available = True
            logger.info("STT: using faster-whisper (%s)", self.model_size)
            return
        except ImportError:
            pass

        # Try mlx-whisper on Apple Silicon
        try:
            import mlx_whisper
            self._engine = mlx_whisper
            self._engine_type = "mlx_whisper"
            self._available = True
            logger.info("STT: using mlx-whisper (%s)", self.model_size)
            return
        except ImportError:
            pass

        # Try standard whisper
        try:
            import whisper
            self._engine = whisper.load_model(self.model_size)
            self._engine_type = "whisper"
            self._available = True
            logger.info("STT: using standard whisper (%s)", self.model_size)
            return
        except ImportError:
            pass

        logger.info("No local Whisper engine available — will use Google Web Speech")

    @property
    def is_available(self) -> bool:
        return self._available

    def transcribe(self, wav_bytes: bytes, language: str | None = None) -> str:
        """Transcribe WAV audio bytes using local Whisper.

        Args:
            wav_bytes: Raw WAV file content.
            language: Override language code.

        Returns:
            Transcribed text.
        """
        lang = language or self.language
        start = time.time()

        try:
            if self._engine_type == "faster_whisper":
                return self._transcribe_faster_whisper(wav_bytes, lang)
            elif self._engine_type == "mlx_whisper":
                return self._transcribe_mlx(wav_bytes, lang)
            elif self._engine_type == "whisper":
                return self._transcribe_standard(wav_bytes, lang)
        except Exception as exc:
            logger.error("Local Whisper transcription failed: %s", exc)

        return ""

    def _transcribe_faster_whisper(self, wav_bytes: bytes, language: str) -> str:
        """Transcribe using faster-whisper."""
        import tempfile
        import os

        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
            f.write(wav_bytes)
            tmp_path = f.name

        try:
            segments, _ = self._engine.transcribe(
                tmp_path,
                language=language if language != 'auto' else None,
                beam_size=5,
                vad_filter=True,
            )
            text = " ".join(s.text for s in segments).strip()
            return text
        finally:
            os.unlink(tmp_path)

    def _transcribe_mlx(self, wav_bytes: bytes, language: str) -> str:
        """Transcribe using mlx-whisper."""
        import tempfile
        import os

        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
            f.write(wav_bytes)
            tmp_path = f.name

        try:
            result = self._engine.transcribe(
                tmp_path,
                language=language,
            )
            return result.get("text", "").strip()
        finally:
            os.unlink(tmp_path)

    def _transcribe_standard(self, wav_bytes: bytes, language: str) -> str:
        """Transcribe using standard whisper."""
        import tempfile
        import os

        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
            f.write(wav_bytes)
            tmp_path = f.name

        try:
            result = self._engine.transcribe(
                tmp_path,
                language=language,
            )
            return result.get("text", "").strip()
        finally:
            os.unlink(tmp_path)


# ── STT Engine ────────────────────────────────────────────────────────────────

class STTEngine:
    """
    Speech-to-Text engine with local Whisper, VAD, and barge-in support.

    Usage::

        engine = STTEngine()
        text = await engine.transcribe_wav(wav_bytes)
        is_speaking = engine.detect_speech(audio_chunk)
    """

    def __init__(self, config: STTConfig | None = None) -> None:
        self.config = config or STTConfig()

        # Initialize VAD for barge-in detection
        self._vad = SileroVAD(threshold=self.config.vad_threshold)

        # Initialize local Whisper
        self._local_whisper: LocalWhisperSTT | None = None
        if self.config.use_local_whisper:
            self._local_whisper = LocalWhisperSTT(
                model_size=self.config.whisper_model,
                language=self.config.language,
            )

        # Initialize Google Web Speech fallback
        if sr is not None:
            self._recogniser = sr.Recognizer()
            self._recogniser.energy_threshold = self.config.energy_threshold
            self._recogniser.pause_threshold = self.config.pause_threshold
            self._recogniser.dynamic_energy_threshold = self.config.dynamic_energy
        else:
            self._recogniser = None

        engine_name = "none"
        if self._local_whisper and self._local_whisper.is_available:
            engine_name = self._local_whisper._engine_type
        elif sr is not None:
            engine_name = "google_web_speech"

        logger.info(
            'STTEngine v2 initialised (engine=%s, lang=%s, vad=%s)',
            engine_name,
            self.config.language,
            "silero" if self._vad.is_available else "energy",
        )

    # ── Public API ────────────────────────────────────────────────────────────

    def detect_speech(self, audio_chunk: bytes, sample_rate: int = 16000) -> bool:
        """Check if an audio chunk contains speech (for barge-in detection).

        Args:
            audio_chunk: Raw PCM audio bytes (16-bit, mono).
            sample_rate: Audio sample rate.

        Returns:
            True if speech energy is detected above threshold.
        """
        return self._vad.detect_speech(audio_chunk, sample_rate)

    async def transcribe_wav(self, wav_bytes: bytes) -> str:
        """Transcribe WAV audio bytes to text.

        Uses local Whisper if available, otherwise falls back to
        Google Web Speech API.

        Args:
            wav_bytes: Raw WAV file content (must include the RIFF header).

        Returns:
            Transcribed text string, or empty string on failure.
        """
        start = time.time()
        loop = asyncio.get_running_loop()

        # Try local Whisper first
        if self._local_whisper and self._local_whisper.is_available:
            text = await loop.run_in_executor(
                None, self._local_whisper.transcribe, wav_bytes, self.config.language,
            )
            if text:
                elapsed_ms = (time.time() - start) * 1000
                logger.info('STT (local): %s (%.0fms)', text[:80], elapsed_ms)
                return text

        # Fall back to Google Web Speech (or Sarvam for Indic)
        return await loop.run_in_executor(None, self._transcribe_sync, wav_bytes)

    async def transcribe_webm(self, webm_bytes: bytes) -> str:
        """Transcribe WebM/Opus audio from the browser.

        The browser MediaRecorder typically outputs WebM. We convert it
        to WAV first using ffmpeg.

        Args:
            webm_bytes: Raw WebM audio blob from the browser.

        Returns:
            Transcribed text string, or empty string on failure.
        """
        loop = asyncio.get_running_loop()
        wav_bytes = await loop.run_in_executor(None, self._webm_to_wav, webm_bytes)
        if wav_bytes is None:
            return ''
        return await self.transcribe_wav(wav_bytes)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _transcribe_sync(self, wav_bytes: bytes) -> str:
        """Blocking transcription call with Sarvam AI support for Indic languages."""
        # Check if Sarvam API is available
        try:
            from src.services.sarvam_service import is_sarvam_available, get_sarvam_service

            if is_sarvam_available() and (self.config.language.startswith(('ta', 'hi', 'te', 'kn', 'ml', 'mr', 'bn', 'gu', 'pa')) or self.config.language == 'en-IN'):
                try:
                    sarvam = get_sarvam_service()
                    res = sarvam.speech_to_text(wav_bytes, language_code=self.config.language)
                    transcript = res.get('transcript', '').strip()
                    if transcript:
                        logger.info('Sarvam STT result: %s', transcript[:80])
                        return transcript
                except Exception as exc:
                    logger.warning('Sarvam STT failed, falling back to Google Web Speech: %s', exc)
        except ImportError:
            pass

        if self._recogniser is None:
            logger.error("No speech recognition backend available")
            return ""

        try:
            audio_file = io.BytesIO(wav_bytes)
            with sr.AudioFile(audio_file) as source:
                audio_data = self._recogniser.record(source)

            text = self._recogniser.recognize_google(
                audio_data,
                language=self.config.language,
            )
            logger.info('STT result: %s', text[:80])
            return text
        except sr.UnknownValueError:
            logger.info('STT could not understand audio (silence)')
            return ''
        except sr.RequestError as exc:
            logger.error('STT service error: %s', exc)
            return ''
        except Exception as exc:
            logger.error('STT unexpected error: %s', exc)
            return ''

    @staticmethod
    def _webm_to_wav(webm_bytes: bytes) -> bytes | None:
        """Convert WebM/Opus audio to WAV using ffmpeg."""
        import subprocess
        import tempfile
        import os

        in_path = None
        out_path = None

        try:
            with tempfile.NamedTemporaryFile(suffix='.webm', delete=False) as f_in:
                f_in.write(webm_bytes)
                in_path = f_in.name

            out_path = in_path.replace('.webm', '.wav')

            result = subprocess.run(
                [
                    'ffmpeg', '-y', '-i', in_path,
                    '-ar', '16000', '-ac', '1', '-f', 'wav',
                    out_path,
                ],
                capture_output=True,
                timeout=10,
            )

            if result.returncode != 0:
                logger.error('ffmpeg conversion failed: %s', result.stderr.decode()[:200])
                return None

            with open(out_path, 'rb') as f_out:
                wav_bytes = f_out.read()

            return wav_bytes
        except FileNotFoundError:
            logger.error('ffmpeg not found — cannot convert WebM to WAV')
            return None
        except Exception as exc:
            logger.error('WebM→WAV conversion error: %s', exc)
            return None
        finally:
            # Cleanup temp files
            for p in (in_path, out_path):
                if p:
                    try:
                        os.unlink(p)
                    except Exception:
                        pass
