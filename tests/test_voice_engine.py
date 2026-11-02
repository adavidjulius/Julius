"""Tests for the Julius voice engine subsystem."""

from __future__ import annotations

import asyncio
import io
import os
import struct
import tempfile
import unittest
import wave
from unittest.mock import MagicMock, patch, AsyncMock


# ── Helper: generate a minimal valid WAV file ────────────────────────────────

def make_wav_bytes(duration_ms: int = 100, sample_rate: int = 16000) -> bytes:
    """Create a minimal silent WAV file in memory."""
    num_samples = int(sample_rate * duration_ms / 1000)
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(b'\x00\x00' * num_samples)
    return buf.getvalue()


# ── STT Engine Tests ──────────────────────────────────────────────────────────

class TestSTTEngine(unittest.TestCase):
    """Tests for the Speech-to-Text engine."""

    def test_import(self):
        """STT engine module imports cleanly."""
        from src.voice.stt_engine import STTEngine, STTConfig
        self.assertIsNotNone(STTEngine)
        self.assertIsNotNone(STTConfig)

    def test_config_defaults(self):
        """STTConfig has reasonable defaults."""
        from src.voice.stt_engine import STTConfig
        config = STTConfig()
        self.assertEqual(config.language, 'en-US')
        self.assertEqual(config.energy_threshold, 300)
        self.assertEqual(config.pause_threshold, 1.0)
        self.assertTrue(config.dynamic_energy)

    def test_engine_init(self):
        """STTEngine initialises without errors."""
        from src.voice.stt_engine import STTEngine, STTConfig
        config = STTConfig(language='en-GB', energy_threshold=500)
        engine = STTEngine(config=config)
        self.assertEqual(engine.config.language, 'en-GB')
        self.assertEqual(engine.config.energy_threshold, 500)

    def test_transcribe_empty_audio(self):
        """Transcribing empty/invalid audio returns empty string."""
        from src.voice.stt_engine import STTEngine
        engine = STTEngine()

        # Empty bytes should not crash
        result = asyncio.run(
            engine.transcribe_wav(b'')
        )
        self.assertEqual(result, '')

    def test_transcribe_invalid_wav(self):
        """Transcribing garbage bytes returns empty string."""
        from src.voice.stt_engine import STTEngine
        engine = STTEngine()

        result = asyncio.run(
            engine.transcribe_wav(b'not a wav file')
        )
        self.assertEqual(result, '')

    def test_transcribe_valid_wav(self):
        """Transcribing a valid WAV calls Google Speech and returns text."""
        import pytest
        pytest.importorskip("speech_recognition")
        from unittest.mock import patch
        with patch('speech_recognition.Recognizer.recognize_google', return_value='hello world') as mock_recognize:
            from src.voice.stt_engine import STTEngine
            engine = STTEngine()

            wav_bytes = make_wav_bytes(duration_ms=200)
            result = asyncio.run(
                engine.transcribe_wav(wav_bytes)
            )
            self.assertEqual(result, 'hello world')
            mock_recognize.assert_called_once()


# ── TTS Engine Tests ──────────────────────────────────────────────────────────

class TestTTSEngine(unittest.TestCase):
    """Tests for the Text-to-Speech engine."""

    def test_import(self):
        """TTS engine module imports cleanly."""
        from src.voice.tts_engine import TTSEngine, VoiceModelConfig, CustomVoiceAdapter
        self.assertIsNotNone(TTSEngine)
        self.assertIsNotNone(VoiceModelConfig)
        self.assertIsNotNone(CustomVoiceAdapter)

    def test_config_defaults(self):
        """VoiceModelConfig has reasonable defaults."""
        from src.voice.tts_engine import VoiceModelConfig
        config = VoiceModelConfig()
        self.assertEqual(config.voice_name, 'Samantha')
        self.assertEqual(config.rate, 185)
        self.assertEqual(config.model_path, '')
        self.assertEqual(config.adapter_class, '')

    def test_engine_init(self):
        """TTSEngine initialises without errors."""
        from src.voice.tts_engine import TTSEngine, VoiceModelConfig
        config = VoiceModelConfig(voice_name='Daniel', rate=200)
        engine = TTSEngine(config=config)
        self.assertEqual(engine.config.voice_name, 'Daniel')
        self.assertEqual(engine.config.rate, 200)

    def test_speak_empty_text(self):
        """Speaking empty text returns empty bytes."""
        from src.voice.tts_engine import TTSEngine
        engine = TTSEngine()
        result = asyncio.run(
            engine.speak('')
        )
        self.assertEqual(result, b'')

    def test_speak_whitespace_only(self):
        """Speaking whitespace-only text returns empty bytes."""
        from src.voice.tts_engine import TTSEngine
        engine = TTSEngine()
        result = asyncio.run(
            engine.speak('   ')
        )
        self.assertEqual(result, b'')

    def test_set_voice(self):
        """set_voice changes the voice name."""
        from src.voice.tts_engine import TTSEngine
        engine = TTSEngine()
        engine.set_voice('Daniel')
        self.assertEqual(engine.config.voice_name, 'Daniel')

    def test_set_rate_clamp(self):
        """set_rate clamps values to valid range."""
        from src.voice.tts_engine import TTSEngine
        engine = TTSEngine()
        engine.set_rate(50)
        self.assertEqual(engine.config.rate, 80)  # clamped to min
        engine.set_rate(500)
        self.assertEqual(engine.config.rate, 400)  # clamped to max
        engine.set_rate(200)
        self.assertEqual(engine.config.rate, 200)

    def test_get_available_voices(self):
        """get_available_voices returns a non-empty list on macOS."""
        import sys
        if sys.platform != 'darwin':
            self.skipTest('macOS only')
        from src.voice.tts_engine import TTSEngine
        engine = TTSEngine()
        voices = engine.get_available_voices()
        self.assertIsInstance(voices, list)
        self.assertGreater(len(voices), 0)
        self.assertIn('Samantha', voices)


# ── Voice Manager Tests ───────────────────────────────────────────────────────

class TestVoiceManager(unittest.TestCase):
    """Tests for the central VoiceManager."""

    def test_import(self):
        """VoiceManager imports cleanly."""
        from src.voice import VoiceManager
        self.assertIsNotNone(VoiceManager)

    def test_init(self):
        """VoiceManager initialises with defaults from env."""
        from src.voice import VoiceManager
        vm = VoiceManager()
        self.assertTrue(vm.is_enabled)

    def test_start_stop_session(self):
        """Start and stop a voice session."""
        from src.voice import VoiceManager
        vm = VoiceManager()
        sid = 'test-session-001'

        self.assertFalse(vm.is_active(sid))
        result = vm.start_session(sid)
        self.assertTrue(result)
        self.assertTrue(vm.is_active(sid))

        vm.stop_session(sid)
        self.assertFalse(vm.is_active(sid))

    def test_start_session_idempotent(self):
        """Starting an already-active session is a no-op."""
        from src.voice import VoiceManager
        vm = VoiceManager()
        sid = 'test-session-002'

        vm.start_session(sid)
        result = vm.start_session(sid)
        self.assertTrue(result)
        vm.stop_session(sid)

    def test_transcribe_no_session(self):
        """Transcribing without an active session returns empty."""
        from src.voice import VoiceManager
        vm = VoiceManager()
        result = asyncio.run(
            vm.transcribe('nonexistent', b'data')
        )
        self.assertEqual(result, '')

    def test_speak_no_session(self):
        """Speaking without an active session returns empty bytes."""
        from src.voice import VoiceManager
        vm = VoiceManager()
        result = asyncio.run(
            vm.speak('nonexistent', 'hello')
        )
        self.assertEqual(result, b'')

    def test_configure_no_session(self):
        """Configuring without a session returns error."""
        from src.voice import VoiceManager
        vm = VoiceManager()
        result = vm.configure('nonexistent', voice_name='Daniel')
        self.assertIn('error', result)

    def test_configure_active_session(self):
        """Configuring an active session changes settings."""
        from src.voice import VoiceManager
        vm = VoiceManager()
        sid = 'test-session-003'
        vm.start_session(sid)

        result = vm.configure(sid, voice_name='Daniel', rate=200)
        self.assertEqual(result['voice_name'], 'Daniel')
        self.assertEqual(result['rate'], 200)

        vm.stop_session(sid)

    def test_cleanup_all(self):
        """cleanup_all stops all active sessions."""
        from src.voice import VoiceManager
        vm = VoiceManager()
        vm.start_session('s1')
        vm.start_session('s2')
        self.assertTrue(vm.is_active('s1'))
        self.assertTrue(vm.is_active('s2'))

        vm.cleanup_all()
        self.assertFalse(vm.is_active('s1'))
        self.assertFalse(vm.is_active('s2'))

    @patch.dict(os.environ, {'JULIUS_VOICE_ENABLED': 'false'})
    def test_disabled_voice(self):
        """Voice mode disabled via env var prevents session start."""
        from src.voice import VoiceManager
        vm = VoiceManager()
        self.assertFalse(vm.is_enabled)
        result = vm.start_session('test-disabled')
        self.assertFalse(result)

    def test_barge_in_interruption(self):
        """Barge-In stops speech generation immediately and resets speaking state in <100ms."""
        import time
        from src.voice import VoiceManager
        vm = VoiceManager()
        sid = 'test-bargein-session'
        vm.start_session(sid)

        vm.set_speaking(sid, True)
        self.assertTrue(vm.is_speaking(sid))

        t0 = time.time()
        was_speaking = vm.interrupt(sid)
        elapsed_ms = (time.time() - t0) * 1000

        self.assertTrue(was_speaking)
        self.assertFalse(vm.is_speaking(sid))
        self.assertLess(elapsed_ms, 100.0, "Interruption took longer than 100ms threshold")

        vm.stop_session(sid)


# ── Custom Voice Adapter Tests ────────────────────────────────────────────────

class TestCustomVoiceAdapter(unittest.TestCase):
    """Tests for the CustomVoiceAdapter interface."""

    def test_abstract_methods(self):
        """CustomVoiceAdapter cannot be instantiated directly."""
        from src.voice.tts_engine import CustomVoiceAdapter
        with self.assertRaises(TypeError):
            CustomVoiceAdapter()

    def test_concrete_adapter(self):
        """A concrete adapter can be instantiated and called."""
        from src.voice.tts_engine import CustomVoiceAdapter

        class MockAdapter(CustomVoiceAdapter):
            def load(self, model_path: str) -> None:
                self.loaded = True

            def synthesise(self, text: str) -> bytes:
                return b'mock_audio_' + text.encode()

        adapter = MockAdapter()
        adapter.load('/fake/model.bin')
        self.assertTrue(adapter.loaded)

        audio = adapter.synthesise('hello')
        self.assertEqual(audio, b'mock_audio_hello')


if __name__ == '__main__':
    unittest.main()
