"""
Julius Skill Manifest and SemVer Parser.

Provides schema validation, semver parsing, and manifest loading for JULIUS_SKILL.yaml
and SKILL.md frontmatter.
"""

from __future__ import annotations

import re
import yaml
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SemverVersion:
    major: int
    minor: int
    patch: int
    prerelease: str = ""

    @classmethod
    def parse(cls, version_str: str) -> SemverVersion:
        cleaned = version_str.lstrip("v").strip()
        match = re.match(r"^(\d+)\.(\d+)\.(\d+)(?:-(.+))?$", cleaned)
        if not match:
            return cls(1, 0, 0)
        major, minor, patch, prerelease = match.groups()
        return cls(int(major), int(minor), int(patch), prerelease or "")

    def satisfies(self, constraint: str) -> bool:
        """Evaluate semver constraint matching (e.g. >=1.0.0, ^1.2.0, ~1.2.3)."""
        constraint = constraint.strip()
        if not constraint or constraint == "*":
            return True

        if constraint.startswith(">="):
            target = SemverVersion.parse(constraint[2:])
            return (self.major, self.minor, self.patch) >= (target.major, target.minor, target.patch)
        elif constraint.startswith("^"):
            target = SemverVersion.parse(constraint[1:])
            return self.major == target.major and (self.minor, self.patch) >= (target.minor, target.patch)
        elif constraint.startswith("~"):
            target = SemverVersion.parse(constraint[1:])
            return self.major == target.major and self.minor == target.minor and self.patch >= target.patch
        elif constraint.startswith("==") or constraint.startswith("="):
            target = SemverVersion.parse(constraint.lstrip("="))
            return (self.major, self.minor, self.patch) == (target.major, target.minor, target.patch)

        target = SemverVersion.parse(constraint)
        return (self.major, self.minor, self.patch) >= (target.major, target.minor, target.patch)

    def __str__(self) -> str:
        base = f"{self.major}.{self.minor}.{self.patch}"
        return f"{base}-{self.prerelease}" if self.prerelease else base


@dataclass
class SkillPermissionSpec:
    required: List[str] = field(default_factory=list)
    optional: List[str] = field(default_factory=list)
    denied: List[str] = field(default_factory=list)
    role: str = "standard"


@dataclass
class JuliusSkillManifest:
    name: str
    version: str
    description: str
    publisher: str = "local"
    license: str = "MIT"
    permissions: SkillPermissionSpec = field(default_factory=SkillPermissionSpec)
    dependencies: Dict[str, str] = field(default_factory=dict)
    tools: List[str] = field(default_factory=list)
    execution_mode: str = "interpreter"  # interpreter | sandboxed | wasm | container
    entrypoint: str = "SKILL.md"
    tags: List[str] = field(default_factory=list)
    checksum: Optional[str] = None

    def __post_init__(self) -> None:
        if isinstance(self.permissions, dict):
            p_dict = self.permissions
            self.permissions = SkillPermissionSpec(
                required=p_dict.get("required", []),
                optional=p_dict.get("optional", []),
                denied=p_dict.get("denied", []),
                role=p_dict.get("role", "standard"),
            )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> JuliusSkillManifest:
        perm_data = data.get("permissions", {})
        if isinstance(perm_data, dict):
            perm_spec = SkillPermissionSpec(
                required=perm_data.get("required", []),
                optional=perm_data.get("optional", []),
                denied=perm_data.get("denied", []),
                role=perm_data.get("role", "standard"),
            )
        else:
            perm_spec = SkillPermissionSpec(required=list(perm_data) if isinstance(perm_data, list) else [])

        return cls(
            name=data.get("name", "unnamed-skill"),
            version=data.get("version", "1.0.0"),
            description=data.get("description", ""),
            publisher=data.get("publisher", "local"),
            license=data.get("license", "MIT"),
            permissions=perm_spec,
            dependencies=data.get("dependencies", {}),
            tools=data.get("tools", data.get("allowed-tools", [])),
            execution_mode=data.get("execution_mode", "interpreter"),
            entrypoint=data.get("entrypoint", "SKILL.md"),
            tags=data.get("tags", []),
            checksum=data.get("checksum"),
        )

    @classmethod
    def load_from_dir(cls, skill_dir: Path) -> JuliusSkillManifest:
        """Load manifest from JULIUS_SKILL.yaml, JULIUS_SKILL.yaml, or SKILL.md frontmatter."""
        yaml_path = skill_dir / "JULIUS_SKILL.yaml"
        if not yaml_path.exists():
            yaml_path = skill_dir / "JULIUS_SKILL.yaml"

        if yaml_path.exists():
            content = yaml_path.read_text(encoding="utf-8")
            data = yaml.safe_load(content) or {}
            return cls.from_dict(data)

        skill_md = skill_dir / "SKILL.md"
        if skill_md.exists():
            text = skill_md.read_text(encoding="utf-8")
            if text.startswith("---"):
                parts = text.split("---", 2)
                if len(parts) >= 3:
                    frontmatter = yaml.safe_load(parts[1]) or {}
                    return cls.from_dict(frontmatter)

        return cls(name=skill_dir.name, version="1.0.0", description=f"Skill from {skill_dir.name}")


# Backward compatibility alias
JuliusSkillManifest = JuliusSkillManifest
