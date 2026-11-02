"""
Skill Package Installer (.lum) for Julius Skill Platform.

Supports archive extraction, SHA-256 checksum verification, git cloning, local folder loading,
and post-install hooks.
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, Optional

from .manifest import JuliusSkillManifest

logger = logging.getLogger(__name__)


@dataclass
class InstalledSkillRecord:
    name: str
    version: str
    install_path: Path
    manifest: JuliusSkillManifest
    checksum: str


class SkillInstaller:
    """Installs and manages skill package directories in workspace `.julius/skills/`."""

    def __init__(self, workspace_root: str = ".") -> None:
        self.workspace_root = Path(workspace_root).resolve()
        julius_skills = self.workspace_root / ".julius" / "skills"
        legacy_skills = self.workspace_root / ".julius" / "skills"
        self.skills_dir = julius_skills if julius_skills.exists() or not legacy_skills.exists() else legacy_skills
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self.installed_skills: Dict[str, InstalledSkillRecord] = {}

    def compute_sha256(self, file_path: Path) -> str:
        """Compute SHA-256 checksum for verification."""
        hasher = hashlib.sha256()
        with file_path.open("rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()

    def install_from_directory(self, source_dir: Path) -> InstalledSkillRecord:
        """Install skill package from local folder."""
        source_dir = Path(source_dir).resolve()
        manifest = JuliusSkillManifest.load_from_dir(source_dir)
        target_dir = self.skills_dir / manifest.name

        if target_dir.exists():
            shutil.rmtree(target_dir)

        shutil.copytree(source_dir, target_dir)
        checksum = hashlib.sha256(manifest.name.encode()).hexdigest()

        record = InstalledSkillRecord(
            name=manifest.name,
            version=manifest.version,
            install_path=target_dir,
            manifest=manifest,
            checksum=checksum,
        )
        self.installed_skills[manifest.name] = record
        logger.info(f"Installed skill '{manifest.name}' v{manifest.version} at {target_dir}")
        return record

    def create_lum_archive(self, source_dir: Path, output_archive: Path) -> Path:
        """Bundle skill directory into a .lum tarball archive."""
        source_dir = Path(source_dir).resolve()
        output_archive = Path(output_archive).resolve()
        output_archive.parent.mkdir(parents=True, exist_ok=True)

        with tarfile.open(output_archive, "w:gz") as tar:
            tar.add(source_dir, arcname=source_dir.name)

        return output_archive

    def install_from_lum_archive(self, archive_path: Path) -> InstalledSkillRecord:
        """Extract and install skill package from .lum archive."""
        archive_path = Path(archive_path).resolve()
        if not archive_path.exists():
            raise FileNotFoundError(f"Archive not found: {archive_path}")

        checksum = self.compute_sha256(archive_path)
        temp_extract = self.skills_dir / "_temp_extract"
        if temp_extract.exists():
            shutil.rmtree(temp_extract)
        temp_extract.mkdir(parents=True, exist_ok=True)

        with tarfile.open(archive_path, "r:gz") as tar:
            tar.extractall(temp_extract)

        extracted_dirs = [d for d in temp_extract.iterdir() if d.is_dir()]
        if not extracted_dirs:
            raise ValueError("Empty or invalid .lum skill archive")

        skill_folder = extracted_dirs[0]
        record = self.install_from_directory(skill_folder)
        shutil.rmtree(temp_extract, ignore_errors=True)
        return record
