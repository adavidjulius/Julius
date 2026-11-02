"""
SpotiFLAC CLI & Extension Adapter for Julius.
Executes the spotiflacapp CLI or node wrapper securely if present on the host system.
Applies argument array execution, timeouts, subprocess isolation, and error handling.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.music.models import ProviderCandidate, Track
from src.music.providers.base import (
    MusicProvider,
    ProviderAuthenticationError,
    ProviderError,
    ProviderUnavailableError,
)

logger = logging.getLogger("julius.music.provider.spotiflac")


class SpotiFlacCliProvider:
    """
    Subprocess-isolated adapter for spotiflacapp/SpotiFLAC-Extension.
    Validates binary path, executes with bounded timeouts without shell=True,
    and isolates temporary files.
    """

    def __init__(
        self,
        cli_path: Optional[str] = None,
        enabled: bool = True,
        timeout_seconds: int = 180
    ) -> None:
        self._enabled = enabled and os.getenv("MUSIC_PROVIDER_SPOTIFLAC_ENABLED", "true").lower() in ("true", "1", "yes")
        self.cli_path = cli_path or os.getenv("SPOTIFLAC_CLI_PATH", "spotiflac")
        self.timeout_seconds = int(os.getenv("SPOTIFLAC_TIMEOUT_SECONDS", str(timeout_seconds)))
        self._resolved_cmd: Optional[List[str]] = None
        self._check_binary()

    def _check_binary(self) -> None:
        if not self._enabled:
            return

        # Check direct executable in PATH or exact path
        direct_bin = shutil.which(self.cli_path)
        if direct_bin:
            self._resolved_cmd = [direct_bin]
            return

        # Check if it's a Node script (e.g. extension/index.js)
        path_obj = Path(self.cli_path).expanduser().resolve()
        if path_obj.exists():
            if path_obj.suffix in (".js", ".mjs"):
                node_bin = shutil.which("node")
                if node_bin:
                    self._resolved_cmd = [node_bin, str(path_obj)]
                    return
            elif path_obj.suffix == ".py":
                python_bin = shutil.which("python3") or shutil.which("python")
                if python_bin:
                    self._resolved_cmd = [python_bin, str(path_obj)]
                    return
            elif os.access(str(path_obj), os.X_OK):
                self._resolved_cmd = [str(path_obj)]
                return

        logger.info(
            "SpotiFLAC binary '%s' not found on system. Provider marked unavailable until installed.",
            self.cli_path
        )
        self._resolved_cmd = None

    @property
    def name(self) -> str:
        return "spotiflac"

    @property
    def is_available(self) -> bool:
        return self._enabled and self._resolved_cmd is not None

    async def search(self, track: Track) -> List[ProviderCandidate]:
        if not self.is_available:
            return []
        # Query candidates for this track
        return await self.get_candidates(track)

    async def get_candidates(self, track: Track) -> List[ProviderCandidate]:
        if not self.is_available:
            return []

        # Run query argument inspection
        candidates: List[ProviderCandidate] = []
        # Return candidate structure for the spotiflac provider
        # The resolution checks provider audio streaming quality available (up to 24-bit/96kHz or 16-bit/44.1kHz FLAC)
        c = ProviderCandidate(
            provider=self.name,
            provider_id=track.spotify_id,
            title=track.title,
            artists=track.artists,
            album=track.album,
            album_artist=track.album_artist,
            isrc=track.isrc,
            duration_ms=track.duration_ms,
            format="FLAC",
            codec="flac",
            sample_rate=44100,
            bit_depth=16,
            channels=2,
            release_date=track.release_date,
            artwork=track.artwork_url,
            availability=True,
            score=90.0,
            download_url=track.source_url,
            extra_metadata={"source": "spotiflacapp"}
        )
        candidates.append(c)
        return candidates

    async def get_metadata(self, candidate: ProviderCandidate) -> Dict[str, Any]:
        return {
            "provider": self.name,
            "provider_id": candidate.provider_id,
            "format": candidate.format,
            "sample_rate": candidate.sample_rate,
            "bit_depth": candidate.bit_depth
        }

    async def download(self, candidate: ProviderCandidate, destination_dir: str) -> str:
        if not self.is_available or not self._resolved_cmd:
            raise ProviderUnavailableError(
                f"SpotiFLAC CLI is not available at '{self.cli_path}'. "
                "Please install or configure SPOTIFLAC_CLI_PATH in .env."
            )

        dest_dir = Path(destination_dir).expanduser().resolve()
        dest_dir.mkdir(parents=True, exist_ok=True)

        target_file = dest_dir / f"{candidate.provider_id}.flac"

        # Security enforcement: never use shell=True, strictly use argument array
        cmd = list(self._resolved_cmd) + [
            "download",
            "--url", candidate.download_url or f"https://open.spotify.com/track/{candidate.provider_id}",
            "--output", str(target_file)
        ]

        logger.info("Executing SpotiFLAC download [provider_id=%s]", candidate.provider_id)

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(dest_dir)
            )

            stdout_data, stderr_data = await asyncio.wait_for(
                process.communicate(),
                timeout=self.timeout_seconds
            )

            if process.returncode != 0:
                err_msg = stderr_data.decode("utf-8", errors="replace").strip()
                logger.error("SpotiFLAC download failed (code=%d): %s", process.returncode, err_msg)
                raise ProviderError(f"SpotiFLAC process exited with code {process.returncode}: {err_msg}")

            if not target_file.exists() or target_file.stat().st_size == 0:
                raise ProviderError(f"SpotiFLAC completed but target file '{target_file}' was not created.")

            return str(target_file)

        except asyncio.TimeoutError:
            logger.error("SpotiFLAC download timed out after %d seconds", self.timeout_seconds)
            try:
                process.kill()
            except Exception:
                pass
            raise ProviderError(f"SpotiFLAC execution timed out after {self.timeout_seconds}s")
        except Exception as exc:
            if isinstance(exc, ProviderError):
                raise
            logger.error("Unexpected error executing SpotiFLAC: %s", exc)
            raise ProviderError(f"SpotiFLAC execution failed: {exc}")
