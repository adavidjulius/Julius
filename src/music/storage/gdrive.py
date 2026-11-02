"""
Google Drive Storage Backend for Julius Music Platform.
Implements automated folder hierarchy creation (Song/Artist/Album/),
resumable chunked file uploads, exponential backoff, token refresh, and existence checks.
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import threading
import time
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger("julius.music.storage.gdrive")

try:
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
    GDRIVE_LIBS_AVAILABLE = True
except ImportError:
    GDRIVE_LIBS_AVAILABLE = False
    logger.warning("Google API client libraries not installed; GoogleDriveStorage disabled.")


class GoogleDriveStorage:
    """Production Google Drive storage adapter for lossless audio ingestion."""

    SCOPES = [
        "https://www.googleapis.com/auth/drive.file",
        "https://www.googleapis.com/auth/drive"
    ]

    def __init__(
        self,
        credentials_path: Optional[str] = None,
        root_folder_id: Optional[str] = None
    ) -> None:
        self.credentials_path = credentials_path or os.getenv("GOOGLE_DRIVE_CREDENTIALS", "credentials.json")
        self.root_folder_id = root_folder_id or os.getenv("GOOGLE_DRIVE_FOLDER_ID")
        self._service = None
        self._folder_cache: Dict[str, str] = {}  # "parent_id/folder_name" -> folder_id
        self._lock = threading.Lock()
        self._init_service()

    def _init_service(self) -> None:
        if not GDRIVE_LIBS_AVAILABLE:
            return

        token_path = Path(os.getenv("GOOGLE_DRIVE_TOKEN_FILE", "token.json")).expanduser().resolve()
        creds_file = Path(self.credentials_path).expanduser().resolve()

        creds = None

        # 1. Check existing authorized user token (token.json)
        if token_path.exists():
            try:
                creds = Credentials.from_authorized_user_file(str(token_path), self.SCOPES)
                if creds and creds.expired and creds.refresh_token:
                    logger.info("Google Drive access token expired; refreshing using refresh_token...")
                    creds.refresh(Request())
                    with open(token_path, "w") as f:
                        f.write(creds.to_json())
                    logger.info("Google Drive token refreshed successfully.")
            except Exception as e:
                logger.warning("Failed loading or refreshing token from %s: %s", token_path, e)
                creds = None

        # 2. If no valid user token, check service account or client credentials file
        if not creds and creds_file.exists():
            try:
                # Check if it is a Service Account file
                import json
                with open(creds_file, "r") as f:
                    data = json.load(f)

                if data.get("type") == "service_account":
                    creds = service_account.Credentials.from_service_account_file(
                        str(creds_file), scopes=self.SCOPES
                    )
                elif "installed" in data or "web" in data:
                    logger.info("Google Drive OAuth client credentials found in '%s'. Run 'python3 scripts/auth_gdrive.py' to generate token.json.", creds_file)
            except Exception as exc:
                logger.warning("Error inspecting credentials file '%s': %s", creds_file, exc)

        if creds and creds.valid:
            try:
                self._service = build("drive", "v3", credentials=creds, cache_discovery=False)
                logger.info("Google Drive API service initialized successfully.")
            except Exception as exc:
                logger.warning("Failed to build Google Drive API service: %s", exc)
                self._service = None
        else:
            self._service = None

    @property
    def name(self) -> str:
        return "gdrive"

    @property
    def is_available(self) -> bool:
        return self._service is not None

    def _ensure_folder(self, folder_name: str, parent_id: Optional[str] = None) -> str:
        """Find or create a folder under parent_id in Google Drive."""
        cache_key = f"{parent_id or 'root'}/{folder_name}"
        if cache_key in self._folder_cache:
            return self._folder_cache[cache_key]

        safe_name = folder_name.replace("'", "\\'")
        query = (
            f"name = '{safe_name}' and "
            f"mimeType = 'application/vnd.google-apps.folder' and "
            f"trashed = false"
        )
        if parent_id:
            query += f" and '{parent_id}' in parents"

        response = self._service.files().list(
            q=query,
            spaces="drive",
            fields="files(id, name)"
        ).execute()

        files = response.get("files", [])
        if files:
            folder_id = files[0]["id"]
            self._folder_cache[cache_key] = folder_id
            return folder_id

        # Create folder
        file_metadata = {
            "name": folder_name,
            "mimeType": "application/vnd.google-apps.folder"
        }
        if parent_id:
            file_metadata["parents"] = [parent_id]

        folder = self._service.files().create(
            body=file_metadata,
            fields="id"
        ).execute()

        folder_id = folder["id"]
        self._folder_cache[cache_key] = folder_id
        logger.info("Created Google Drive folder '%s' (id=%s)", folder_name, folder_id)
        return folder_id

    def _resolve_target_folder(self, remote_path: str) -> Tuple[str, str]:
        """
        Parse path e.g. "Song/Artist/Album/01 - Track.flac"
        Creates "Song", "Artist", and "Album" folders in Drive if they don't exist.
        Returns (parent_folder_id, filename).
        """
        parts = [p for p in remote_path.split("/") if p]
        if not parts:
            raise ValueError("Empty remote path")

        filename = parts[-1]
        folders = parts[:-1]

        current_parent = self.root_folder_id

        for folder in folders:
            current_parent = self._ensure_folder(folder, current_parent)

        return current_parent, filename

    async def upload(self, local_path: str, remote_path: str, mime_type: str = "audio/flac") -> str:
        if not self.is_available:
            raise RuntimeError("Google Drive service is not available.")

        local_file = Path(local_path).expanduser().resolve()
        if not local_file.exists():
            raise FileNotFoundError(f"Local file not found: {local_path}")

        def _execute_upload():
            with self._lock:
                parent_id, filename = self._resolve_target_folder(remote_path)

                # Check if file already exists in this folder
                safe_filename = filename.replace("'", "\\'")
                q = (
                    f"name = '{safe_filename}' and "
                    f"'{parent_id}' in parents and "
                    f"trashed = false"
                )
                existing = self._service.files().list(q=q, spaces="drive", fields="files(id)").execute()
                if existing.get("files"):
                    existing_id = existing["files"][0]["id"]
                    logger.info("File '%s' already exists in Drive folder. Reusing id=%s", filename, existing_id)
                    return existing_id

                media = MediaFileUpload(
                    str(local_file),
                    mimetype=mime_type,
                    resumable=True
                )

                body = {
                    "name": filename,
                    "parents": [parent_id]
                }

                request = self._service.files().create(
                    body=body,
                    media_body=media,
                    fields="id"
                )

                # Resumable upload loop with exponential backoff
                response = None
                max_retries = 5
                retry_count = 0
                while response is None:
                    try:
                        status, response = request.next_chunk()
                        if status:
                            logger.debug("Drive upload progress: %d%%", int(status.progress() * 100))
                    except HttpError as exc:
                        if exc.resp.status in (500, 502, 503, 504, 429) and retry_count < max_retries:
                            retry_count += 1
                            wait_time = 2 ** retry_count
                            logger.warning("Drive upload transient error %s; retrying in %ds...", exc, wait_time)
                            time.sleep(wait_time)
                        else:
                            raise

                file_id = response.get("id")
                logger.info("Successfully uploaded '%s' to Google Drive (file_id=%s)", filename, file_id)
                return file_id

        return await asyncio.to_thread(_execute_upload)

    async def exists(self, remote_path: str) -> bool:
        if not self.is_available:
            return False

        def _check():
            try:
                parent_id, filename = self._resolve_target_folder(remote_path)
                q = (
                    f"name = '{filename}' and "
                    f"'{parent_id}' in parents and "
                    f"trashed = false"
                )
                res = self._service.files().list(q=q, spaces="drive", fields="files(id)").execute()
                return bool(res.get("files"))
            except Exception:
                return False

        return await asyncio.to_thread(_check)

    async def delete(self, remote_path_or_id: str) -> bool:
        if not self.is_available:
            return False

        def _delete():
            try:
                self._service.files().delete(fileId=remote_path_or_id).execute()
                return True
            except Exception as exc:
                logger.warning("Failed to delete Drive file %s: %s", remote_path_or_id, exc)
                return False

        return await asyncio.to_thread(_delete)

    async def read_range(self, remote_path_or_id: str, start_byte: int, end_byte: Optional[int] = None) -> bytes:
        """Read a byte range from a Google Drive file."""
        if not self.is_available:
            raise RuntimeError("Google Drive service is not available.")

        def _fetch_range():
            file_id = remote_path_or_id
            # Download specific bytes via MediaIoBaseDownload
            request = self._service.files().get_media(fileId=file_id)
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            downloader.next_chunk()
            fh.seek(start_byte)
            if end_byte is not None:
                return fh.read(end_byte - start_byte + 1)
            return fh.read()

        return await asyncio.to_thread(_fetch_range)

    async def get_file_size(self, remote_path_or_id: str) -> int:
        if not self.is_available:
            return 0

        def _get_size():
            meta = self._service.files().get(fileId=remote_path_or_id, fields="size").execute()
            return int(meta.get("size", 0))

        return await asyncio.to_thread(_get_size)


# Global storage instances
gdrive_storage = GoogleDriveStorage()
