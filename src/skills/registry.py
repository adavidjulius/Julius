"""Capability Registry module for Julius Skill Platform."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .catalog import (
    CodeCompilerSkill,
    FileOperationsSkill,
    GitWorkflowSkill,
    TerminalCommandSkill,
    CodebaseSearchSkill,
    WebResearcherSkill,
    LinterFormatterSkill,
    TestRunnerSkill,
    RefactorAssistantSkill,
    SecretScannerSkill,
    ArchitectureDiagrammerSkill,
    TestGeneratorSkill,
)

logger = logging.getLogger(__name__)


class CapabilityRegistry:
    """Registry managing capability discovery, action mapping, and skill retrieval."""

    def __init__(self) -> None:
        skills_dict: Dict[str, Any] = {
            "julius/skill/code-compiler": CodeCompilerSkill(),
            "julius/skill/file-operations": FileOperationsSkill(),
            "julius/skill/git-workflow": GitWorkflowSkill(),
            "julius/skill/terminal-command": TerminalCommandSkill(),
            "julius/skill/codebase-search": CodebaseSearchSkill(),
            "julius/skill/web-researcher": WebResearcherSkill(),
            "julius/skill/linter-formatter": LinterFormatterSkill(),
            "julius/skill/test-runner": TestRunnerSkill(),
            "julius/skill/refactor-assistant": RefactorAssistantSkill(),
            "julius/skill/secret-scanner": SecretScannerSkill(),
            "julius/skill/architecture-diagrammer": ArchitectureDiagrammerSkill(),
            "julius/skill/test-generator": TestGeneratorSkill(),
        }
        # Add julius/skill/* aliases for backward compatibility
        for k, v in list(skills_dict.items()):
            skills_dict[k.replace("julius/skill/", "julius/skill/")] = v

        self._skills = skills_dict

        self._action_mappings: Dict[str, str] = {
            "READ_FILE": "julius/skill/file-operations",
            "WRITE_FILE": "julius/skill/file-operations",
            "EXECUTE_SHELL": "julius/skill/terminal-command",
            "GREP_CODE": "julius/skill/codebase-search",
            "COMPILE_CODE": "julius/skill/code-compiler",
            "GIT_COMMIT": "julius/skill/git-workflow",
            "WEB_RESEARCH": "julius/skill/web-researcher",
            "LINT_CODE": "julius/skill/linter-formatter",
            "RUN_TESTS": "julius/skill/test-runner",
            "REFACTOR": "julius/skill/refactor-assistant",
        }

    def discover_capabilities(self) -> Dict[str, Any]:
        """Discover available skills and mapped actions."""
        return {
            "skills": dict(self._skills),
            "actions": list(self._action_mappings.keys()),
        }

    def resolve_action(self, action_name: str) -> Optional[str]:
        """Map a generic action to its underlying skill identifier."""
        return self._action_mappings.get(action_name)

    def get_skill(self, skill_id: str) -> Optional[Any]:
        """Retrieve a concrete skill instance by its identifier."""
        if skill_id in self._skills:
            return self._skills[skill_id]
        if skill_id.startswith("julius/skill/"):
            return self._skills.get(skill_id.replace("julius/skill/", "julius/skill/"))
        if skill_id.startswith("julius/skill/"):
            return self._skills.get(skill_id.replace("julius/skill/", "julius/skill/"))
        return None
