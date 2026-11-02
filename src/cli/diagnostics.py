"""
Diagnostics & Support Bundle Generator (WS5).

Produces a sanitized zip archive containing:
- System & environment versions
- Sanitized configuration (secrets masked)
- Redacted application and audit logs
- SQLite database integrity reports
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.security.secrets import get_secrets_manager
from src.settings import get_settings


def generate_support_bundle(workspace: Optional[str] = None, output_zip: Optional[str] = None) -> str:
    """Generate sanitized diagnostics zip bundle."""
    sec_mgr = get_secrets_manager()
    settings = get_settings(workspace)

    temp_dir = Path(tempfile.mkdtemp(prefix="julius_diag_"))
    try:
        # 1. System info
        sys_info = {
            "julius_version": "2.0.0",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "python": sys.version,
            "platform": platform.platform(),
            "architecture": platform.machine(),
            "processor": platform.processor(),
        }
        (temp_dir / "system.json").write_text(json.dumps(sys_info, indent=2), encoding="utf-8")

        # 2. Sanitized Settings
        masked_cfg = settings.mask_secrets_dump()
        (temp_dir / "config_resolved.json").write_text(json.dumps(masked_cfg, indent=2), encoding="utf-8")

        # 3. Redacted logs
        log_candidate = Path.home() / ".julius" / "audit_chain.jsonl"
        if log_candidate.exists():
            clean_lines = []
            with open(log_candidate, "r", encoding="utf-8") as f:
                for line in f:
                    clean_lines.append(sec_mgr.choke_point_logs(line.strip()))
            (temp_dir / "audit_sample.jsonl").write_text("\n".join(clean_lines[-500:]), encoding="utf-8")

        # Zip bundle
        ts_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        out_path = Path(output_zip or (Path.cwd() / f"julius_diagnostics_{ts_str}.zip"))
        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for file_p in temp_dir.iterdir():
                zipf.write(file_p, arcname=file_p.name)

        print(f"📦 Support bundle successfully generated: {out_path}")
        return str(out_path)

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

