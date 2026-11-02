"""
AgentSkills Standard Importer for Julius Skill Platform.

Converts standard AgentSkills repository packages (SKILL.md format) into Julius
production skills with JULIUS_SKILL.yaml manifests and typed capability permissions.
"""

from __future__ import annotations

import logging
try:
    import yaml
except ImportError:
    yaml = None
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, List, Optional

from .manifest import JuliusSkillManifest, SkillPermissionSpec

logger = logging.getLogger(__name__)


class AgentSkillsImporter:
    """Imports and adapts open standard AgentSkills SKILL.md packages into Julius's skill store."""

    def __init__(self, workspace_root: str = ".") -> None:
        self.workspace_root = Path(workspace_root).resolve()
        julius_skills = self.workspace_root / ".julius" / "skills"
        legacy_skills = self.workspace_root / ".julius" / "skills"
        self.julius_skills_dir = julius_skills if julius_skills.exists() or not legacy_skills.exists() else legacy_skills
        self.julius_skills_dir.mkdir(parents=True, exist_ok=True)
        self.julius_skills_dir = self.julius_skills_dir  # Backward compatibility alias

    def import_agentskill_markdown(self, skill_name: str, raw_markdown: str, capabilities: Optional[List[str]] = None) -> Path:
        """
        Import a standard SKILL.md document string into a full Julius skill package directory.
        """
        target_dir = self.julius_skills_dir / skill_name
        target_dir.mkdir(parents=True, exist_ok=True)

        # Write SKILL.md
        skill_md = target_dir / "SKILL.md"
        skill_md.write_text(raw_markdown, encoding="utf-8")

        # Parse frontmatter if present
        description = f"AgentSkill: {skill_name}"
        version = "1.0.0"
        tags = [skill_name, "agentskills"]

        if raw_markdown.startswith("---") and yaml is not None:
            parts = raw_markdown.split("---", 2)
            if len(parts) >= 3:
                try:
                    fm = yaml.safe_load(parts[1]) or {}
                    description = fm.get("description", description)
                    version = fm.get("version", version)
                    if "tags" in fm:
                        tags.extend(fm["tags"])
                except Exception as exc:
                    logger.warning(f"Could not parse frontmatter in {skill_name}: {exc}")

        # Create JULIUS_SKILL.yaml manifest
        manifest_yaml = target_dir / "JULIUS_SKILL.yaml"
        if yaml is not None:
            manifest_data = {
                "name": skill_name,
                "version": version,
                "description": description,
                "publisher": "agentskills",
                "license": "Apache-2.0",
                "permissions": {
                    "required": capabilities or ["filesystem.read", "terminal.execute"],
                    "role": "standard",
                },
                "tags": list(set(tags)),
                "execution_mode": "interpreter",
            }
            manifest_yaml.write_text(yaml.dump(manifest_data, indent=2), encoding="utf-8")
        else:
            manifest_yaml.write_text(f"name: {skill_name}\nversion: {version}\ndescription: {description}\n", encoding="utf-8")

        logger.info(f"Successfully imported AgentSkill '{skill_name}' to {target_dir}")
        return target_dir
