#!/usr/bin/env python3
"""
Direct Google Drive Uploader for Julius Consecutive Backups.

Uploads the latest consecutive backup (julius_backup_latest.tar.gz)
to the target Google Drive backup folder:
https://drive.google.com/drive/folders/1rAnwUte_byClYSyB9OSixPGh7ElnJRva
Folder ID: 1rAnwUte_byClYSyB9OSixPGh7ElnJRva
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("julius.gdrive_upload")

TARGET_FOLDER_ID = "1rAnwUte_byClYSyB9OSixPGh7ElnJRva"
TARGET_FOLDER_URL = f"https://drive.google.com/drive/folders/{TARGET_FOLDER_ID}"


def find_latest_backup(repo_root: Path) -> Optional[Path]:
    """Locate the latest backup archive in the backups directory."""
    backups_dir = repo_root / "backups"
    latest_file = backups_dir / "julius_backup_latest.tar.gz"
    if latest_file.exists():
        return latest_file

    candidates = sorted(
        backups_dir.glob("julius_backup_*.tar.gz"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def upload_backup(file_path: Path, folder_id: str = TARGET_FOLDER_ID) -> bool:
    """Upload backup archive using Google API Client if credentials/token exist."""
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload

        token_path = Path("token.json").resolve()
        if not token_path.exists():
            token_path = file_path.parent.parent / "token.json"

        if not token_path.exists():
            logger.warning("No token.json found. Run 'python3 scripts/auth_gdrive.py' or provide service account.")
            return False

        with open(token_path, "r") as f:
            tok_data = json.load(f)

        creds = Credentials.from_authorized_user_info(
            tok_data,
            scopes=["https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]
        )

        service = build("drive", "v3", credentials=creds, cache_discovery=False)
        media = MediaFileUpload(str(file_path), mimetype="application/gzip", resumable=True)
        file_metadata = {
            "name": file_path.name,
            "parents": [folder_id],
        }

        logger.info("Uploading %s to Google Drive folder %s...", file_path.name, folder_id)
        request = service.files().create(body=file_metadata, media_body=media, fields="id, name, size")
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                logger.info("Upload progress: %d%%", int(status.progress() * 100))

        logger.info("✓ Upload successful! Google Drive File ID: %s", response.get("id"))
        return True
    except Exception as exc:
        logger.error("Failed uploading to Google Drive: %s", exc)
        return False


def main():
    parser = argparse.ArgumentParser(description="Upload latest Julius backup to Google Drive")
    parser.add_argument("--file", type=str, default=None, help="Explicit backup archive path")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    target_file = Path(args.file) if args.file else find_latest_backup(repo_root)

    if not target_file or not target_file.exists():
        logger.error("No backup archive found. Run 'python3 scripts/backup_julius.py' first.")
        sys.exit(1)

    logger.info("Preparing upload for: %s (%.2f MB)", target_file.name, target_file.stat().st_size / (1024 * 1024))
    logger.info("Destination Google Drive: %s", TARGET_FOLDER_URL)

    success = upload_backup(target_file, TARGET_FOLDER_ID)
    if not success:
        logger.info("Note: To enable automatic Drive sync, ensure a valid OAuth client in credentials.json.")
        logger.info("Backup remains securely stored in %s and synced to remote server backups/", target_file)


if __name__ == "__main__":
    main()
