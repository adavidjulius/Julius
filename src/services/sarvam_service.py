"""Sarvam AI integration service for Julius.

Provides access to Sarvam AI APIs for Indic languages:
- Text Translation (Mayura: v1)
- Text-to-Speech (Bulbul: v1)
- Speech-to-Text (Saarika / Saaras)
- Chat Completions (Sarvam-2B)
- Document Parsing / OCR
"""

from __future__ import annotations

import base64
import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

SARVAM_BASE_URL = "https://api.sarvam.ai"


def get_sarvam_api_key() -> str:
    """Retrieve the Sarvam API key from environment variables."""
    return os.getenv("SARVAM_API_KEY", "").strip()


def is_sarvam_available() -> bool:
    """Check whether a non-empty Sarvam API key is configured."""
    return bool(get_sarvam_api_key())


class SarvamService:
    """Service client for interacting with Sarvam AI APIs."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = (api_key or get_sarvam_api_key()).strip()

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise ValueError("Sarvam API key is not configured. Set SARVAM_API_KEY in .env.")
        return {
            "api-subscription-key": self.api_key,
            "Content-Type": "application/json",
        }

    def translate(
        self,
        text: str,
        target_language_code: str = "ta-IN",
        source_language_code: str = "en-IN",
        speaker_gender: str = "Female",
        mode: str = "formal",
        model: str = "mayura:v1",
    ) -> dict[str, Any]:
        """Translate text between Indic languages and English using Sarvam Mayura.

        Args:
            text: Source text to translate.
            target_language_code: e.g. 'ta-IN' (Tamil), 'hi-IN' (Hindi), 'te-IN' (Telugu), 'en-IN' (English).
            source_language_code: e.g. 'en-IN' or 'ta-IN'.
            speaker_gender: 'Female' or 'Male'.
            mode: 'formal', 'colloquial', or 'code-mixed'.
            model: Sarvam translation model name.

        Returns:
            Dict containing 'translated_text' and response metadata.
        """
        url = f"{SARVAM_BASE_URL}/translate"

        # Format gender nicely ('Female' or 'Male')
        gender_formatted = speaker_gender.strip().capitalize() if speaker_gender else "Female"
        if gender_formatted not in ("Female", "Male"):
            gender_formatted = "Female"

        payload = {
            "input": text,
            "source_language_code": source_language_code,
            "target_language_code": target_language_code,
            "speaker_gender": gender_formatted,
            "mode": mode,
            "model": model,
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=self._headers(), method="POST")

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                logger.info("Sarvam translate success (%s -> %s)", source_language_code, target_language_code)
                return result
        except urllib.error.HTTPError as exc:
            err_body = ""
            try:
                err_body = exc.read().decode("utf-8")
            except Exception:
                pass
            logger.error("Sarvam translate HTTP error %d: %s | Details: %s", exc.code, exc.reason, err_body)
            raise RuntimeError(f"Sarvam translation HTTP {exc.code} error: {exc.reason} - {err_body}") from exc
        except Exception as exc:
            logger.error("Sarvam translate API failed: %s", exc)
            raise RuntimeError(f"Sarvam translation failed: {exc}") from exc

    def text_to_speech(
        self,
        text: str,
        target_language_code: str = "ta-IN",
        speaker: str = "anushka",
        pitch: float = 0.0,
        pace: float = 1.0,
        loudness: float = 1.5,
        speech_sample_rate: int = 16000,
        model: str = "bulbul:v2",
    ) -> bytes:
        """Convert text to speech audio WAV bytes using Sarvam Bulbul TTS.

        Args:
            text: Text string to speak.
            target_language_code: Language code, e.g. 'ta-IN', 'hi-IN', 'te-IN', etc.
            speaker: Speaker voice, e.g., 'meera', 'pavithra', 'maitra', 'arvind', 'amartya', 'shivam'.
            pitch: Pitch shift (-0.5 to 0.5).
            pace: Speed multiplier (0.5 to 2.0).
            loudness: Volume gain (0.5 to 2.0).
            speech_sample_rate: Audio sampling rate (8000, 16000, or 22050).
            model: Model name.

        Returns:
            Decoded WAV audio bytes.
        """
        url = f"{SARVAM_BASE_URL}/text-to-speech"
        payload = {
            "inputs": [text],
            "target_language_code": target_language_code,
            "speaker": speaker,
            "pitch": pitch,
            "pace": pace,
            "loudness": loudness,
            "speech_sample_rate": speech_sample_rate,
            "enable_preprocessing": True,
            "model": model,
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=self._headers(), method="POST")

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                res_json = json.loads(resp.read().decode("utf-8"))
                audios = res_json.get("audios", [])
                if not audios:
                    raise ValueError("No audio returned in Sarvam TTS response")
                return base64.b64decode(audios[0])
        except urllib.error.HTTPError as exc:
            err_body = ""
            try:
                err_body = exc.read().decode("utf-8")
            except Exception:
                pass
            logger.error("Sarvam text_to_speech HTTP error %d: %s | Details: %s", exc.code, exc.reason, err_body)
            raise RuntimeError(f"Sarvam TTS HTTP {exc.code} error: {exc.reason} - {err_body}") from exc
        except Exception as exc:
            logger.error("Sarvam text_to_speech API failed: %s", exc)
            raise RuntimeError(f"Sarvam TTS failed: {exc}") from exc

    def speech_to_text(
        self,
        audio_bytes: bytes,
        language_code: str = "ta-IN",
        model: str = "saarika:v2.5",
        with_timestamps: bool = False,
        filename: str = "audio.wav",
    ) -> dict[str, Any]:
        """Transcribe audio bytes using Sarvam Saarika STT API.

        Args:
            audio_bytes: Raw audio file bytes (WAV, MP3, WebM, etc.).
            language_code: Expected language code e.g. 'ta-IN', 'hi-IN', 'unknown'.
            model: Sarvam STT model ('saarika:v2' or 'saarika:v1' or 'saaras:v1').
            with_timestamps: Whether to include word-level timestamps.
            filename: Audio filename for content-type detection.

        Returns:
            Dict with 'transcript' and optional timestamps.
        """
        url = f"{SARVAM_BASE_URL}/speech-to-text"
        boundary = "----SarvamFormBoundary7MA4YWxkTrZu0gW"
        
        body = []

        # file part
        body.append(f"--{boundary}".encode("utf-8"))
        body.append(f'Content-Disposition: form-data; name="file"; filename="{filename}"'.encode("utf-8"))
        body.append(b"Content-Type: audio/wav\r\n")
        body.append(audio_bytes)

        # language_code part
        body.append(f"--{boundary}".encode("utf-8"))
        body.append(b'Content-Disposition: form-data; name="language_code"\r\n')
        body.append(language_code.encode("utf-8"))

        # model part
        body.append(f"--{boundary}".encode("utf-8"))
        body.append(b'Content-Disposition: form-data; name="model"\r\n')
        body.append(model.encode("utf-8"))

        # with_timestamps part
        if with_timestamps:
            body.append(f"--{boundary}".encode("utf-8"))
            body.append(b'Content-Disposition: form-data; name="with_timestamps"\r\n')
            body.append(b"true")

        body.append(f"--{boundary}--\r\n".encode("utf-8"))

        payload = b"\r\n".join(body)

        headers = {
            "api-subscription-key": self.api_key,
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        }

        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            err_body = ""
            try:
                err_body = exc.read().decode("utf-8")
            except Exception:
                pass
            logger.error("Sarvam speech_to_text HTTP error %d: %s | Details: %s", exc.code, exc.reason, err_body)
            raise RuntimeError(f"Sarvam STT HTTP {exc.code} error: {exc.reason} - {err_body}") from exc
        except Exception as exc:
            logger.error("Sarvam speech_to_text API failed: %s", exc)
            raise RuntimeError(f"Sarvam STT failed: {exc}") from exc

    def chat_completion(
        self,
        messages: list[dict[str, str]],
        model: str = "sarvam-2b",
        max_tokens: int = 1000,
        temperature: float = 0.7,
    ) -> str:
        """Run chat completion with Sarvam LLM.

        Args:
            messages: List of message objects, e.g. [{"role": "user", "content": "..."}].
            model: LLM model name (default 'sarvam-2b').
            max_tokens: Max completion tokens.
            temperature: Sampling temperature.

        Returns:
            Generated response content text.
        """
        url = f"{SARVAM_BASE_URL}/chat/completions"
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=self._headers(), method="POST")

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                res_json = json.loads(resp.read().decode("utf-8"))
                choices = res_json.get("choices", [])
                if choices:
                    return choices[0].get("message", {}).get("content", "")
                return ""
        except urllib.error.HTTPError as exc:
            err_body = ""
            try:
                err_body = exc.read().decode("utf-8")
            except Exception:
                pass
            logger.error("Sarvam chat_completion HTTP error %d: %s | Details: %s", exc.code, exc.reason, err_body)
            raise RuntimeError(f"Sarvam chat completion HTTP {exc.code} error: {exc.reason} - {err_body}") from exc
        except Exception as exc:
            logger.error("Sarvam chat_completion failed: %s", exc)
            raise RuntimeError(f"Sarvam chat completion failed: {exc}") from exc

    def parse_document(self, file_bytes: bytes, filename: str = "document.pdf") -> dict[str, Any]:
        """Parse PDF/Image documents using Sarvam document parsing OCR API.

        Args:
            file_bytes: Document raw bytes.
            filename: Document filename.

        Returns:
            Parsed document layout & text content.
        """
        url = f"{SARVAM_BASE_URL}/parse-document"
        boundary = "----SarvamDocBoundary9ZZ8YWxkTr"
        body = []

        body.append(f"--{boundary}".encode("utf-8"))
        body.append(f'Content-Disposition: form-data; name="file"; filename="{filename}"'.encode("utf-8"))
        body.append(b"Content-Type: application/pdf\r\n")
        body.append(file_bytes)
        body.append(f"--{boundary}--\r\n".encode("utf-8"))

        payload = b"\r\n".join(body)

        headers = {
            "api-subscription-key": self.api_key,
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        }

        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            err_body = ""
            try:
                err_body = exc.read().decode("utf-8")
            except Exception:
                pass
            logger.error("Sarvam parse_document HTTP error %d: %s | Details: %s", exc.code, exc.reason, err_body)
            raise RuntimeError(f"Sarvam document parsing HTTP {exc.code} error: {exc.reason} - {err_body}") from exc
        except Exception as exc:
            logger.error("Sarvam parse_document failed: %s", exc)
            raise RuntimeError(f"Sarvam document parsing failed: {exc}") from exc


# Global singleton instance
_sarvam_instance: SarvamService | None = None


def get_sarvam_service() -> SarvamService:
    """Return global SarvamService instance."""
    global _sarvam_instance
    if _sarvam_instance is None or _sarvam_instance.api_key != get_sarvam_api_key():
        _sarvam_instance = SarvamService()
    return _sarvam_instance
