"""
Ambient Voice Listener & Auditory Earcons Engine for Julius.

Provides continuous acoustic wake-word listening ("Hey Julius" / "Julius"),
subtle auditory earcons (chimes for wake, thinking, completion, warning),
and full-duplex conversational voice dispatch.
"""

from __future__ import annotations

import asyncio
import logging
import os
import platform
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .voice_manager import VoiceManager

logger = logging.getLogger(__name__)


class EarconCue(str, Enum):
    WAKE = "wake"          # User activated / wake word heard
    THINKING = "thinking"  # Agent processing / reasoning
    SUCCESS = "success"    # Task completed / action confirmed
    ALERT = "alert"        # Warning / attention needed
    CANCEL = "cancel"      # Operation cancelled / barge-in


class WakeWordState(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"
    WAKE_DETECTED = "wake_detected"
    RECORDING_UTTERANCE = "recording_utterance"
    PROCESSING = "processing"
    SPEAKING = "speaking"


def play_earcon(cue: EarconCue) -> bool:
    """
    Play a subtle auditory earcon chime matching the system event.
    Non-blocking, low-latency execution.
    """
    os_name = platform.system().lower()

    if os_name == "darwin":
        # Map cues to elegant built-in macOS sound effects
        sound_map = {
            EarconCue.WAKE: "/System/Library/Sounds/Tink.aiff",
            EarconCue.THINKING: "/System/Library/Sounds/Pop.aiff",
            EarconCue.SUCCESS: "/System/Library/Sounds/Glass.aiff",
            EarconCue.ALERT: "/System/Library/Sounds/Basso.aiff",
            EarconCue.CANCEL: "/System/Library/Sounds/Blow.aiff",
        }
        sound_file = sound_map.get(cue, "/System/Library/Sounds/Tink.aiff")
        if os.path.exists(sound_file) and shutil.which("afplay"):
            try:
                subprocess.Popen(["afplay", "-v", "0.4", sound_file], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True
            except Exception as exc:
                logger.debug("afplay error: %s", exc)

    elif os_name == "linux":
        # Linux paplay / aplay fallback
        if shutil.which("paplay"):
            for cand in [
                f"/usr/share/sounds/freedesktop/stereo/{cue.value}.oga",
                "/usr/share/sounds/freedesktop/stereo/bell.oga",
            ]:
                if os.path.exists(cand):
                    try:
                        subprocess.Popen(["paplay", cand], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        return True
                    except Exception:
                        pass

    elif os_name == "windows":
        # Windows SystemSounds via PowerShell
        sound_type = "Asterisk" if cue in (EarconCue.WAKE, EarconCue.SUCCESS) else "Hand"
        ps = f"[System.Media.SystemSounds]::{sound_type}.Play()"
        try:
            subprocess.Popen(["powershell", "-NoProfile", "-Command", ps], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except Exception:
            pass

    return False


@dataclass
class VoiceInteractionEvent:
    """Event emitted during ambient voice interactions."""
    state: WakeWordState
    transcript: str = ""
    timestamp: float = field(default_factory=time.time)
    audio_bytes: bytes = b""


class AmbientVoiceListener:
    """
    Ambient continuous listener managing wake-word activation,
    utterance processing, and acoustic feedback.
    """

    def __init__(
        self,
        voice_manager: Optional[VoiceManager] = None,
        wake_words: Optional[List[str]] = None,
        on_event: Optional[Callable[[VoiceInteractionEvent], None]] = None,
        on_command: Optional[Callable[[str], Any]] = None,
    ) -> None:
        self.voice_manager = voice_manager or VoiceManager()
        self.wake_words = [w.lower() for w in (wake_words or ["hey julius", "julius"])]
        self.on_event = on_event
        self.on_command = on_command
        self.state = WakeWordState.IDLE
        self._is_running = False
        logger.info("AmbientVoiceListener created with wake words: %s", self.wake_words)

    def is_wake_word_detected(self, text: str) -> bool:
        """Check if an utterance contains any registered wake word."""
        clean = text.lower().strip()
        for ww in self.wake_words:
            if ww in clean:
                return True
        return False

    def extract_command(self, text: str) -> str:
        """Strip wake word prefix from text to extract the actual command."""
        clean = text.strip()
        for ww in self.wake_words:
            idx = clean.lower().find(ww)
            if idx != -1:
                cmd = clean[idx + len(ww):].strip(" ,:.-?!")
                return cmd
        return clean

    def trigger_wake(self) -> None:
        """Manual wake trigger (e.g. from hotkey or UI button)."""
        logger.info("Wake triggered manually")
        self.state = WakeWordState.WAKE_DETECTED
        play_earcon(EarconCue.WAKE)
        if self.on_event:
            self.on_event(VoiceInteractionEvent(state=self.state))

    def handle_transcript(self, transcript: str) -> Optional[str]:
        """
        Process incoming speech transcript:
        If wake word is present, play chime, extract command, and dispatch.
        """
        if not transcript.strip():
            return None

        if self.is_wake_word_detected(transcript):
            self.state = WakeWordState.WAKE_DETECTED
            play_earcon(EarconCue.WAKE)
            command = self.extract_command(transcript)
            logger.info("Wake-word detected! Extracted command: '%s'", command)

            if command:
                self.state = WakeWordState.PROCESSING
                play_earcon(EarconCue.THINKING)
                if self.on_command:
                    self.on_command(command)
                return command
        return None

    def notify_task_complete(self, success: bool = True) -> None:
        """Play completion or alert chime upon agent task finalization."""
        self.state = WakeWordState.IDLE
        if success:
            play_earcon(EarconCue.SUCCESS)
        else:
            play_earcon(EarconCue.ALERT)
        if self.on_event:
            self.on_event(VoiceInteractionEvent(state=self.state))


# Singleton instance
_ambient_listener: Optional[AmbientVoiceListener] = None


def get_ambient_listener() -> AmbientVoiceListener:
    """Get or create global AmbientVoiceListener."""
    global _ambient_listener
    if _ambient_listener is None:
        _ambient_listener = AmbientVoiceListener()
    return _ambient_listener
