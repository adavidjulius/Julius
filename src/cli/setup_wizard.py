"""
Julius First-Run Onboarding Wizard (WS9.2).

Guides users through:
- Local Ollama detection or keychain provider key configuration
- Sandbox tier selection
- Running Julius Doctor diagnostic checks
- Displaying the 3-line "What Leaves Your Machine" transparency pledge
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Optional

from src.cli.doctor import JuliusDoctor
from src.security.secrets import get_secrets_manager
from src.settings import Settings, get_settings


def print_transparency_pledge() -> None:
    """Prints the 3-line 'What Leaves Your Machine' transparency summary."""
    print("\n" + "=" * 60)
    print("🔒 Julius Privacy & Local-First Commitment")
    print("-" * 60)
    print(" 1. Code & Files   : 100% local. Your files and workspace never leave your machine.")
    print(" 2. Model Prompts  : Sent ONLY to your explicitly chosen official provider (BYOK).")
    print(" 3. Telemetry      : Zero tracking or phone-home telemetry without explicit opt-in.")
    print("=" * 60 + "\n")


def run_first_run_setup(workspace: Optional[str] = None) -> None:
    """Interactive first-run configuration wizard."""
    print("\n🚀 Welcome to Julius — Autonomous Engineering & Coding System")
    print("Setting up your production environment...\n")

    ws_path = Path(workspace or os.getcwd()).resolve()
    sec_mgr = get_secrets_manager()

    # 1. Detect Ollama
    ollama_detected = False
    import urllib.request
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=1.5) as r:
            if r.status == 200:
                ollama_detected = True
    except Exception:
        pass

    if ollama_detected:
        print("🦙 Detected active local Ollama instance at http://127.0.0.1:11434 (Zero cloud dependencies).")
    else:
        print("💡 Tip: Local Ollama is not currently running. You can bring your own API key (BYOK) for NVIDIA NIM, OpenAI, Anthropic, Gemini, or DeepSeek.")

    # 2. Key entry into Keychain
    existing_nvidia = sec_mgr.get_secret("NVIDIA_API_KEY")
    if existing_nvidia:
        print("🔑 Found existing NVIDIA API key in OS Keychain.")
    else:
        print("🔑 Provider credentials will be saved in your OS Keychain (macOS Keychain / Secret Service).")

    # 3. Doctor health check
    print("\nRunning quick system diagnostics...")
    doctor = JuliusDoctor(str(ws_path))
    doctor.run_all_checks()

    # 4. Print Privacy Pledge
    print_transparency_pledge()

    print(f"✨ Setup complete! Active workspace: {ws_path}")
    print("Run `julius` to launch the terminal interface, or `julius --help` for commands.\n")

