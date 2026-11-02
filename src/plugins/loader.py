"""
Skill and Plugin Loader for Julius Agent.

Phase 4.3 — Milestone 4.3: Discovers and parses ``SKILL.md`` files at runtime,
extracting YAML frontmatter metadata, dependencies, entrypoints, and scoped permissions.
Supports hot reloading and live re-scanning.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class SkillManifest:
    """Metadata describing an autonomous skill/plugin."""
    skill_id: str
    name: str
    description: str
    directory_path: str
    skill_file_path: str
    compatibility: str = "Julius Workspace"
    license: str = "MIT"
    dependencies: List[str] = field(default_factory=list)
    entrypoints: List[str] = field(default_factory=list)
    permissions: List[str] = field(default_factory=list)
    sandboxed: bool = True
    enabled: bool = True
    mtime: float = 0.0
    author: str = "Julius"
    version: str = "1.0.0"
    raw_frontmatter: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert manifest to JSON-serializable dictionary."""
        return {
            "skill_id": self.skill_id,
            "name": self.name,
            "description": self.description,
            "directory_path": self.directory_path,
            "skill_file_path": self.skill_file_path,
            "compatibility": self.compatibility,
            "license": self.license,
            "dependencies": self.dependencies,
            "entrypoints": self.entrypoints,
            "permissions": self.permissions,
            "sandboxed": self.sandboxed,
            "enabled": self.enabled,
            "mtime": self.mtime,
            "author": self.author,
            "version": self.version,
        }


class SkillLoader:
    """Discovers and parses SKILL.md files into SkillManifest objects."""

    @staticmethod
    def parse_yaml_frontmatter(content: str) -> tuple[Dict[str, Any], str]:
        """
        Extract and parse YAML frontmatter from markdown content without requiring external PyYAML.
        """
        frontmatter: Dict[str, Any] = {}
        markdown_body = content

        pattern = r"^---\s*\n(.*?)\n---\s*\n(.*)$"
        match = re.match(pattern, content, re.DOTALL)
        if not match:
            return frontmatter, markdown_body

        raw_yaml = match.group(1)
        markdown_body = match.group(2)

        # Basic key-value parsing supporting strings, booleans, and lists
        current_list_key = None
        for line in raw_yaml.split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            if line.startswith("- ") and current_list_key:
                val = line[2:].strip().strip("\"'")
                if isinstance(frontmatter.get(current_list_key), list):
                    frontmatter[current_list_key].append(val)
                continue

            if ":" in line:
                key, val = line.split(":", 1)
                key = key.strip()
                val = val.strip()

                if not val:
                    # Potential list starter
                    current_list_key = key
                    frontmatter[key] = []
                    continue

                current_list_key = None
                # Strip quotes
                if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                    val = val[1:-1]
                elif val.lower() == "true":
                    val = True
                elif val.lower() == "false":
                    val = False

                frontmatter[key] = val

        return frontmatter, markdown_body

    @classmethod
    def load_skill(cls, skill_dir: Path) -> Optional[SkillManifest]:
        """Parse a skill directory containing a SKILL.md file."""
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.is_file():
            return None

        try:
            mtime = skill_file.stat().st_mtime
            content = skill_file.read_text(encoding="utf-8", errors="replace")
            meta, _ = cls.parse_yaml_frontmatter(content)

            folder_name = skill_dir.name
            skill_id = meta.get("id") or folder_name
            name = meta.get("name") or folder_name.replace("-", " ").replace("_", " ").title()
            description = meta.get("description") or f"Skill provided by {folder_name}"

            # Permissions & dependencies
            dependencies = meta.get("dependencies", [])
            if isinstance(dependencies, str):
                dependencies = [d.strip() for d in dependencies.split(",") if d.strip()]

            entrypoints = meta.get("entrypoints", [])
            if isinstance(entrypoints, str):
                entrypoints = [e.strip() for e in entrypoints.split(",") if e.strip()]

            permissions = meta.get("permissions", ["workspace:read"])
            if isinstance(permissions, str):
                permissions = [p.strip() for p in permissions.split(",") if p.strip()]

            return SkillManifest(
                skill_id=str(skill_id).strip(),
                name=str(name).strip(),
                description=str(description).strip(),
                directory_path=str(skill_dir.resolve()),
                skill_file_path=str(skill_file.resolve()),
                compatibility=str(meta.get("compatibility", "Julius Workspace")),
                license=str(meta.get("license", "MIT")),
                dependencies=dependencies,
                entrypoints=entrypoints,
                permissions=permissions,
                sandboxed=bool(meta.get("sandboxed", True)),
                enabled=bool(meta.get("enabled", True)),
                mtime=mtime,
                author=str(meta.get("author", "Julius Community")),
                version=str(meta.get("version", "1.0.0")),
                raw_frontmatter=meta,
            )
        except Exception as exc:
            logger.error(f"Error loading skill at {skill_dir}: {exc}")
            return None

    @classmethod
    def scan_directory(cls, base_dir: Path) -> Dict[str, SkillManifest]:
        """Scan a root directory for all skills."""
        manifests: Dict[str, SkillManifest] = {}
        if not base_dir.is_dir():
            return manifests

        try:
            for entry in base_dir.iterdir():
                if entry.is_dir() and not entry.name.startswith("."):
                    manifest = cls.load_skill(entry)
                    if manifest:
                        manifests[manifest.skill_id] = manifest
                    # Check nested subdirectories (e.g. skills/skills/)
                    for sub in entry.iterdir():
                        if sub.is_dir() and not sub.name.startswith("."):
                            sub_manifest = cls.load_skill(sub)
                            if sub_manifest:
                                manifests[sub_manifest.skill_id] = sub_manifest
        except Exception as exc:
            logger.warning(f"Error scanning skills directory {base_dir}: {exc}")

        return manifests
