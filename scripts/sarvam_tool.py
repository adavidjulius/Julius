#!/usr/bin/env python3
"""Sarvam AI CLI tool for Julius.

Commands:
  translate  Translate text between Indic languages and English
  tts        Convert text to speech audio WAV
  stt        Transcribe audio to text
  ocr        Parse document layout and text

Example usage:
  python3 scripts/sarvam_tool.py translate "Hello World" --target ta-IN
  python3 scripts/sarvam_tool.py tts "வணக்கம்" --out greeting.wav
  python3 scripts/sarvam_tool.py stt audio.wav --lang ta-IN
  python3 scripts/sarvam_tool.py ocr document.pdf
"""

import argparse
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

from src.services.sarvam_service import get_sarvam_service, is_sarvam_available


def main() -> None:
    parser = argparse.ArgumentParser(description="Sarvam AI CLI Tool for Julius")
    subparsers = parser.add_subparsers(dest="command", help="Sub-command to execute")

    # Translate command
    trans_p = subparsers.add_parser("translate", help="Translate text")
    trans_p.add_argument("text", type=str, help="Text to translate")
    trans_p.add_argument("--target", "-t", type=str, default="ta-IN", help="Target language code (default: ta-IN)")
    trans_p.add_argument("--source", "-s", type=str, default="en-IN", help="Source language code (default: en-IN)")

    # TTS command
    tts_p = subparsers.add_parser("tts", help="Convert text to speech audio WAV")
    tts_p.add_argument("text", type=str, help="Text to speak")
    tts_p.add_argument("--out", "-o", type=str, default="output_speech.wav", help="Output WAV file path")
    tts_p.add_argument("--lang", "-l", type=str, default="ta-IN", help="Target language code")
    tts_p.add_argument("--speaker", type=str, default="anushka", help="Speaker voice name")

    # STT command
    stt_p = subparsers.add_parser("stt", help="Transcribe audio file")
    stt_p.add_argument("audio_path", type=str, help="Path to input audio file")
    stt_p.add_argument("--lang", "-l", type=str, default="ta-IN", help="Audio language code")

    # OCR command
    ocr_p = subparsers.add_parser("ocr", help="Parse PDF/Image document")
    ocr_p.add_argument("document_path", type=str, help="Path to input document")

    args = parser.parse_args()

    if not is_sarvam_available():
        print("Error: SARVAM_API_KEY is not set in environment or .env file.", file=sys.stderr)
        sys.exit(1)

    sarvam = get_sarvam_service()

    if args.command == "translate":
        res = sarvam.translate(args.text, target_language_code=args.target, source_language_code=args.source)
        print("Translated text:")
        print(res.get("translated_text", ""))
    elif args.command == "tts":
        wav_bytes = sarvam.text_to_speech(args.text, target_language_code=args.lang, speaker=args.speaker)
        out_path = Path(args.out)
        out_path.write_bytes(wav_bytes)
        print(f"Speech audio saved to {out_path.resolve()} ({len(wav_bytes)} bytes)")
    elif args.command == "stt":
        audio_file = Path(args.audio_path)
        if not audio_file.exists():
            print(f"Error: File {audio_file} not found.", file=sys.stderr)
            sys.exit(1)
        res = sarvam.speech_to_text(audio_file.read_bytes(), language_code=args.lang, filename=audio_file.name)
        print("Transcription:")
        print(res.get("transcript", ""))
    elif args.command == "ocr":
        doc_file = Path(args.document_path)
        if not doc_file.exists():
            print(f"Error: File {doc_file} not found.", file=sys.stderr)
            sys.exit(1)
        res = sarvam.parse_document(doc_file.read_bytes(), filename=doc_file.name)
        import json
        print(json.dumps(res, indent=2))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
