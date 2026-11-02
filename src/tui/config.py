"""
Configuration manager and greeting generator for Julius.

Manages ~/.config/julius/config.toml, detects user name, and generates
personalized, calm Julius time-of-day greetings.
"""

from __future__ import annotations

import datetime
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

# In Python 3.11+, tomllib is in standard library
try:
    import tomllib
except ImportError:
    tomllib = None  # type: ignore


CONFIG_DIR = Path.home() / ".config" / "julius"
CONFIG_FILE = CONFIG_DIR / "config.toml"


@dataclass
class JuliusConfig:
    """User preferences stored in ~/.config/julius/config.toml."""
    theme: str = "dark"
    model: str = "nvidia"
    reduce_motion: bool = False
    user_name: Optional[str] = None
    onboarding_completed: bool = False
    max_content_width: int = 0  # 0 = unlimited full width; >0 caps assistant prose width

    def to_toml(self) -> str:
        lines = [
            "# Julius Configuration",
            f'theme = "{self.theme}"',
            f'model = "{self.model}"',
            f'reduce_motion = {"true" if self.reduce_motion else "false"}',
            f'onboarding_completed = {"true" if self.onboarding_completed else "false"}',
        ]
        if self.max_content_width > 0:
            lines.append(f"max_content_width = {self.max_content_width}")
        if self.user_name:
            lines.append(f'user_name = "{self.user_name}"')
        return "\n".join(lines) + "\n"


def load_config() -> JuliusConfig:
    """Load configuration from ~/.config/julius/config.toml or return defaults."""
    if not CONFIG_FILE.exists():
        return JuliusConfig()

    try:
        content = CONFIG_FILE.read_text(encoding="utf-8")
        if tomllib:
            data = tomllib.loads(content)
        else:
            # Simple fallback parser for basic key = "val" lines
            data = {}
            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    if v.lower() == "true":
                        data[k] = True
                    elif v.lower() == "false":
                        data[k] = False
                    else:
                        data[k] = v
        return JuliusConfig(
            theme=data.get("theme", "auto"),
            model=data.get("model", "deepseek"),
            reduce_motion=data.get("reduce_motion", False),
            user_name=data.get("user_name"),
            onboarding_completed=data.get("onboarding_completed", True),
            max_content_width=int(data.get("max_content_width", 0)),
        )
    except Exception:
        return JuliusConfig()


def save_config(config: JuliusConfig) -> None:
    """Save configuration to ~/.config/julius/config.toml."""
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(config.to_toml(), encoding="utf-8")
    except Exception:
        pass


def detect_user_first_name(configured_name: Optional[str] = None) -> str:
    """
    Detect the user's first name:
    1. Configured name if present
    2. macOS id -F (full name -> first name)
    3. Git config user.name
    4. os.getlogin()
    """
    if configured_name and configured_name.strip():
        return configured_name.strip().split()[0]

    # Try macOS full name via `id -F`
    try:
        proc = subprocess.run(["id", "-F"], capture_output=True, text=True, timeout=1.0)
        if proc.returncode == 0 and proc.stdout.strip():
            full = proc.stdout.strip()
            # E.g. "David Julius" -> "David"
            return full.split()[0].capitalize()
    except Exception:
        pass

    # Try git config
    try:
        proc = subprocess.run(["git", "config", "user.name"], capture_output=True, text=True, timeout=1.0)
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip().split()[0].capitalize()
    except Exception:
        pass

    # Fallback to system login username
    try:
        login = os.getlogin()
        if login:
            return login.capitalize()
    except Exception:
        pass

    return ""


def get_greeting(first_name: str = "") -> str:
    """
    Generate a calm Julius time-of-day greeting.
    Example: "Good morning, David. What are we working on?"
    """
    now = datetime.datetime.now()
    hour = now.hour

    if 5 <= hour < 12:
        salutation = "Good morning"
    elif 12 <= hour < 17:
        salutation = "Good afternoon"
    else:
        salutation = "Good evening"

    if first_name:
        return f"{salutation}, {first_name}. What are we working on?"
    return f"{salutation}. What are we working on?"
