"""Agent Skills Registry engine for Julius.

Scans, validates, and manages Agent Skills using agentskills/skills-ref.
Generates <available_skills> XML blocks for LLM system prompts.
"""

from __future__ import annotations

import os
import sys
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# Ensure agentskills/skills-ref/src is in sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_SKILLS_REF_SRC = _PROJECT_ROOT / "agentskills" / "skills-ref" / "src"
if _SKILLS_REF_SRC.exists() and str(_SKILLS_REF_SRC) not in sys.path:
    sys.path.insert(0, str(_SKILLS_REF_SRC))

try:
    from skills_ref import find_skill_md, read_properties, validate, to_prompt, SkillProperties
    HAS_SKILLS_REF = True
except ImportError:
    HAS_SKILLS_REF = False

logger = logging.getLogger("julius.skills.registry")


@dataclass
class RegisteredSkill:
    """Data model representing a loaded Agent Skill."""
    name: str
    description: str
    path: Path
    skill_md_path: Path
    allowed_tools: Optional[str] = None
    compatibility: Optional[str] = None
    license: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_valid: bool = True
    validation_errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "path": str(self.path),
            "skill_md_path": str(self.skill_md_path),
            "allowed_tools": self.allowed_tools,
            "compatibility": self.compatibility,
            "license": self.license,
            "metadata": self.metadata,
            "is_valid": self.is_valid,
            "validation_errors": self.validation_errors,
        }


class AgentSkillsRegistry:
    """Discovers, validates, and indexes Agent Skills for Julius."""

    def __init__(self, root_skills_dir: Optional[Path | str] = None) -> None:
        self.root_skills_dir = Path(root_skills_dir or (_PROJECT_ROOT / "skills" / "skills")).resolve()
        self._skills: Dict[str, RegisteredSkill] = {}
        self.discover_skills()

    def discover_skills(self) -> int:
        """Scan candidate skill root directories for SKILL.md files."""
        self._skills.clear()
        
        candidate_dirs = [
            _PROJECT_ROOT / ".agents" / "skills",
            _PROJECT_ROOT / "agentskills" / "skills",
            _PROJECT_ROOT / "skills" / "skills",
            _PROJECT_ROOT / ".julius" / "skills",
            self.root_skills_dir,
        ]
        
        seen_dirs = set()
        for root in candidate_dirs:
            try:
                resolved = root.resolve()
            except Exception:
                continue
                
            if not resolved.exists() or not resolved.is_dir() or resolved in seen_dirs:
                continue
            seen_dirs.add(resolved)
            
            for entry in sorted(resolved.iterdir()):
                if entry.is_dir() and not entry.name.startswith("."):
                    skill_md = entry / "SKILL.md"
                    if not skill_md.exists():
                        skill_md = entry / "skill.md"

                    if skill_md.exists():
                        self.load_skill(entry)

        logger.info(f"Discovered {len(self._skills)} unique Agent Skills across {len(seen_dirs)} directories")
        return len(self._skills)

    def load_skill(self, skill_dir: Path) -> Optional[RegisteredSkill]:
        """Load and validate a single skill directory."""
        skill_dir = Path(skill_dir).resolve()
        if not HAS_SKILLS_REF:
            logger.error("skills_ref library not available")
            return None

        errors = validate(skill_dir)
        try:
            props = read_properties(skill_dir)
            skill_md = find_skill_md(skill_dir) or (skill_dir / "SKILL.md")
            registered = RegisteredSkill(
                name=props.name,
                description=props.description,
                path=skill_dir,
                skill_md_path=skill_md,
                allowed_tools=props.allowed_tools,
                compatibility=props.compatibility,
                license=props.license,
                metadata=props.metadata or {},
                is_valid=len(errors) == 0,
                validation_errors=errors,
            )
            self._skills[props.name] = registered
            return registered
        except Exception as e:
            logger.error(f"Failed to parse skill at {skill_dir}: {e}")
            return None

    def get_skill(self, name: str) -> Optional[RegisteredSkill]:
        return self._skills.get(name)

    def list_skills(self) -> List[RegisteredSkill]:
        return list(self._skills.values())

    def get_available_skills_prompt(self) -> str:
        """Generate <available_skills> XML prompt block for active valid skills."""
        valid_paths = [s.path for s in self._skills.values() if s.is_valid]
        if not HAS_SKILLS_REF or not valid_paths:
            return "<available_skills>\n</available_skills>"
        return to_prompt(valid_paths)


# Global singleton instance for easy import
_registry_instance: Optional[AgentSkillsRegistry] = None


def get_agent_skills_registry() -> AgentSkillsRegistry:
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = AgentSkillsRegistry()
    return _registry_instance
