#!/usr/bin/env python3
"""
Julius Offsite Consecutive Backup & Google Drive Packager.

Creates clean, production-ready, lightweight backups of Julius source code, configurations,
knowledge base, and dependencies, ready to be restored on any machine.

Strictly excludes bloatware (.venv, node_modules, browser caches, log files, pycache)
to keep archive sizes between 10-25MB, allowing hundreds of consecutive versioned
backups to fit comfortably within the 15GB Google Drive storage.

Target Google Drive Folder:
https://drive.google.com/drive/folders/1rAnwUte_byClYSyB9OSixPGh7ElnJRva
Folder ID: 1rAnwUte_byClYSyB9OSixPGh7ElnJRva
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("julius.backup")

# Target Google Drive destination
GOOGLE_DRIVE_FOLDER_ID = "1rAnwUte_byClYSyB9OSixPGh7ElnJRva"
GOOGLE_DRIVE_FOLDER_URL = f"https://drive.google.com/drive/folders/{GOOGLE_DRIVE_FOLDER_ID}"

# Maximum number of consecutive versioned backups to keep locally and in Drive
MAX_CONSECUTIVE_BACKUPS = 50

# Strict exclusions: unwanted bulk and machine-specific artifacts
EXCLUDE_DIRS = {
    ".venv",
    "tts-env",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    "chrome_profile",
    ".chrome_profile",
    ".webtop_config",
    "Julius_Browser",
    "whatsapp_profile",
    "logs",
    "dist",
    "build",
    "rpm_build",
    ".git",
    "timetable_pages",
    "OPPO A16",
    "New Login Page",
    "JuliusData",
    ".julius",
    "backups",
}

EXCLUDE_EXTENSIONS = {
    ".pyc",
    ".pyo",
    ".log",
    ".db",
    ".db-wal",
    ".db-shm",
    ".dmg",
    ".exe",
    ".msi",
    ".rar",
    ".zip",
    ".tar.gz",
    ".tar",
    ".pma",
    ".store",
}

EXCLUDE_PATTERNS = [
    "scratch/timetable_pages",
    "scratch/*.png",
    "backups/",
]


def get_repo_root() -> Path:
    """Find the root directory of the Julius repository."""
    current = Path(__file__).resolve().parent.parent
    if (current / "julius_gui.py").exists() or (current / "src").exists():
        return current
    return Path.cwd()


def get_git_info(repo_root: Path) -> Dict[str, str]:
    """Retrieve git commit hash and branch if git is available."""
    info = {"commit": "unknown", "branch": "unknown", "dirty": "unknown"}
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=repo_root, stderr=subprocess.DEVNULL
        ).decode().strip()
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_root, stderr=subprocess.DEVNULL
        ).decode().strip()
        status = subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=repo_root, stderr=subprocess.DEVNULL
        ).decode().strip()
        info["commit"] = commit
        info["branch"] = branch
        info["dirty"] = "true" if status else "false"
    except Exception:
        pass
    return info


def compute_sha256(file_path: Path) -> str:
    """Compute SHA-256 checksum of an archive file."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def generate_restore_script() -> str:
    """Generate the turnkey restore.sh script to be included in the archive."""
    return """#!/usr/bin/env bash
# ==============================================================================
# Julius Automated Project Restore Script
# Restores dependencies and sets up Julius environment on any Linux or macOS device.
# ==============================================================================
set -e

echo "🚀 [Julius Restore] Starting environment setup..."
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

# 1. Detect Python
PYTHON_BIN=""
for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
    if command -v $candidate >/dev/null 2>&1; then
        PYTHON_BIN=$candidate
        break
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    echo "❌ Error: Python 3.10+ is required but not found in PATH."
    exit 1
fi
echo "✓ Using Python: $($PYTHON_BIN --version) ($PYTHON_BIN)"

# 2. Setup Virtual Environment
if [ ! -d ".venv" ]; then
    echo "📦 Creating virtual environment (.venv)..."
    $PYTHON_BIN -m venv .venv
fi

source .venv/bin/activate
echo "✓ Virtual environment activated."

# 3. Upgrade pip and install core dependencies
echo "📥 Installing requirements..."
pip install --upgrade pip setuptools wheel
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
fi

# 4. Create necessary local storage directories
mkdir -p data logs backups

# 5. Verify installation
python3 -c "
import src
print('✓ Julius core packages verified successfully!')
"

echo "=============================================================================="
echo "🎉 Julius Project restored successfully!"
echo "To run server:  python3 julius_gui.py"
echo "To run tests:   pytest tests/"
echo "=============================================================================="
"""


def should_exclude(rel_path: Path) -> bool:
    """Check if a file or directory relative path should be excluded from the backup."""
    parts = set(rel_path.parts)
    # Check directory names
    if any(p in EXCLUDE_DIRS for p in parts):
        return True

    # Any hidden directory or file in path
    if any(p.startswith(".") and p not in (".", "..") for p in rel_path.parts[:-1]):
        return True

    # Check extension
    if rel_path.suffix.lower() in EXCLUDE_EXTENSIONS:
        return True

    # Check scratch png/out/bak files
    if "scratch" in parts and rel_path.suffix.lower() in (".png", ".out", ".bak", ".jpg"):
        return True

    return False


def create_backup_archive(repo_root: Path, output_dir: Path) -> Tuple[Path, Dict[str, any]]:
    """Create a clean, compressed .tar.gz archive of the Julius codebase."""
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_name = f"julius_backup_{timestamp_str}.tar.gz"
    archive_path = output_dir / archive_name
    latest_path = output_dir / "julius_backup_latest.tar.gz"

    git_info = get_git_info(repo_root)

    # Collect files
    included_files: List[Path] = []
    for root, dirs, files in os.walk(repo_root):
        # Prune excluded directories in-place for speed
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith(".")]

        for f in files:
            full_path = Path(root) / f
            rel_path = full_path.relative_to(repo_root)
            if not should_exclude(rel_path):
                included_files.append(rel_path)

    logger.info("Packaging %d files into %s...", len(included_files), archive_name)

    # Write tar.gz
    with tarfile.open(archive_path, "w:gz", compresslevel=9) as tar:
        for rel_path in included_files:
            full_path = repo_root / rel_path
            tar.add(full_path, arcname=f"Julius/{rel_path}")

        # Inject turnkey restore.sh script
        restore_content = generate_restore_script().encode("utf-8")
        restore_info = tarfile.TarInfo(name="Julius/restore.sh")
        restore_info.size = len(restore_content)
        restore_info.mtime = int(datetime.datetime.now().timestamp())
        restore_info.mode = 0o755  # Executable
        import io
        tar.addfile(restore_info, io.BytesIO(restore_content))

    # Also update latest copy
    shutil.copyfile(archive_path, latest_path)

    size_bytes = archive_path.stat().st_size
    size_mb = size_bytes / (1024 * 1024)
    checksum = compute_sha256(archive_path)

    meta = {
        "filename": archive_name,
        "timestamp": datetime.datetime.now().isoformat(),
        "size_bytes": size_bytes,
        "size_mb": round(size_mb, 2),
        "sha256": checksum,
        "file_count": len(included_files) + 1,
        "git": git_info,
        "gdrive_folder_id": GOOGLE_DRIVE_FOLDER_ID,
        "gdrive_folder_url": GOOGLE_DRIVE_FOLDER_URL,
    }

    # Record in manifest
    manifest_path = output_dir / "backup_manifest.json"
    manifest: List[Dict] = []
    if manifest_path.exists():
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
        except Exception:
            manifest = []

    manifest.insert(0, meta)
    # Prune manifest
    manifest = manifest[:MAX_CONSECUTIVE_BACKUPS]

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    logger.info("✓ Backup created: %s (%.2f MB, SHA256: %s...)", archive_name, size_mb, checksum[:12])
    return archive_path, meta


def enforce_retention(output_dir: Path) -> None:
    """Enforce retention policy to keep only the latest MAX_CONSECUTIVE_BACKUPS."""
    backups = sorted(
        output_dir.glob("julius_backup_*.tar.gz"),
        key=lambda p: p.stat().st_mtime,
        reverse=True
    )
    # Exclude julius_backup_latest.tar.gz from deletion list
    versioned_backups = [b for b in backups if b.name != "julius_backup_latest.tar.gz"]

    if len(versioned_backups) > MAX_CONSECUTIVE_BACKUPS:
        to_delete = versioned_backups[MAX_CONSECUTIVE_BACKUPS:]
        for p in to_delete:
            try:
                p.unlink()
                logger.info("Pruned old backup: %s", p.name)
            except Exception as e:
                logger.warning("Could not delete old backup %s: %s", p.name, e)


def upload_to_google_drive(archive_path: Path, meta: Dict) -> bool:
    """Attempt upload to Google Drive folder 1rAnwUte_byClYSyB9OSixPGh7ElnJRva."""
    logger.info("Connecting to Google Drive folder: %s", GOOGLE_DRIVE_FOLDER_URL)

    # 1. Try Google Drive API service
    try:
        from src.services.gdrive_service import gdrive_service
        if gdrive_service.is_available:
            logger.info("Uploading %s via Google Drive API...", archive_path.name)
            # Synchronous run of async upload
            import asyncio
            file_id = asyncio.run(gdrive_service.upload_file(
                local_path=str(archive_path),
                remote_rel_path=archive_path.name,
                mime_type="application/gzip",
            ))
            logger.info("✓ Uploaded to Google Drive successfully! File ID: %s", file_id)
            return True
    except Exception as e:
        logger.debug("Google Drive API direct upload not available: %s", e)

    # 2. Inform user and store locally for sync
    logger.info("Google Drive offsite destination: %s", GOOGLE_DRIVE_FOLDER_URL)
    logger.info("Archive ready for Google Drive: %s", archive_path)
    return False


def main():
    parser = argparse.ArgumentParser(description="Julius Offsite Consecutive Backup Tool")
    parser.add_argument("--dest", type=str, default=None, help="Destination directory for backups (default: <repo>/backups)")
    parser.add_argument("--upload", action="store_true", help="Trigger Google Drive upload attempt")
    args = parser.parse_args()

    repo_root = get_repo_root()
    output_dir = Path(args.dest) if args.dest else (repo_root / "backups")

    logger.info("=== Julius Offsite Consecutive Backup Initiated ===")
    logger.info("Source Repository: %s", repo_root)
    logger.info("Destination Directory: %s", output_dir)
    logger.info("Target Google Drive: %s", GOOGLE_DRIVE_FOLDER_URL)

    archive_path, meta = create_backup_archive(repo_root, output_dir)
    enforce_retention(output_dir)

    if args.upload:
        upload_to_google_drive(archive_path, meta)

    print("\n" + "=" * 70)
    print("✓ BACKUP COMPLETED CONSECUTIVELY")
    print(f"• File:       {archive_path.name}")
    print(f"• Size:       {meta['size_mb']} MB (Clean code & configs only)")
    print(f"• SHA256:     {meta['sha256']}")
    print(f"• Location:   {archive_path}")
    print(f"• Drive URL:  {GOOGLE_DRIVE_FOLDER_URL}")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
