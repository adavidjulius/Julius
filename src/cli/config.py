"""
Julius Config Management CLI (WS4.1).

Validates active configuration, displays resolved configuration with
masked secrets, and checks schema compatibility.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from src.settings import Settings, get_settings


def validate_config(workspace: Optional[str] = None) -> bool:
    """Validate settings against schema and print results."""
    try:
        settings = Settings.load_resolved(workspace=workspace)
        print("✅ Configuration is valid according to schema.")
        print(f"   Workspace : {settings.workspace_dir}")
        print(f"   Default Provider : {settings.providers.default_provider}")
        print(f"   Sandbox Tier     : {settings.sandbox.tier}")
        print(f"   Telemetry        : {'Enabled' if settings.telemetry.enabled else 'Disabled (Opt-In)'}")
        return True
    except Exception as e:
        print(f"❌ Configuration validation failed: {e}")
        return False


def show_resolved_config(workspace: Optional[str] = None, json_format: bool = True) -> None:
    """Print resolved configuration with all secrets safely masked."""
    settings = get_settings(workspace=workspace, refresh=True)
    masked = settings.mask_secrets_dump()
    if json_format:
        print(json.dumps(masked, indent=2))
    else:
        for section, values in masked.items():
            print(f"[{section}]")
            if isinstance(values, dict):
                for k, v in values.items():
                    print(f"  {k} = {v}")
            else:
                print(f"  {values}")

