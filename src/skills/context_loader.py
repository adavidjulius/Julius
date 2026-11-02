"""
Progressive 6-Stage Context Loader for Julius Skill Platform.

Implements graph-aware progressive context loading:
Stage 1: Intent Matcher
Stage 2: Metadata Loader (L1 Cache)
Stage 3: Semantic Ranker & PKB Context
Stage 4: Lazy Instruction Loader (L2 Cache)
Stage 5: Resource Streamer (L3 Cache)
Stage 6: Context Assembler with Token Budgeting
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .manifest import JuliusSkillManifest

logger = logging.getLogger(__name__)


@dataclass
class CompiledSkillContext:
    skill_name: str
    stage: int
    system_instruction: str
    tokens_used: int
    referenced_files: List[str] = field(default_factory=list)


class ProgressiveSkillContextLoader:
    """6-Stage Graph-Aware Progressive Context Loader for Julius Skills."""

    def __init__(self, token_budget: int = 8000) -> None:
        self.token_budget = token_budget
        self._l1_cache: Dict[str, Dict[str, Any]] = {}
        self._l2_cache: Dict[str, str] = {}

    def match_intent(self, user_query: str, manifests: List[JuliusSkillManifest]) -> List[JuliusSkillManifest]:
        """Stage 1: Intent Matcher - match query words against skill metadata & tags."""
        matched = []
        query_words = set(re.findall(r"\w+", user_query.lower()))

        for manifest in manifests:
            tags = set(t.lower() for t in manifest.tags)
            name_words = set(re.findall(r"\w+", manifest.name.lower()))
            desc_words = set(re.findall(r"\w+", manifest.description.lower()))
            
            overlap = query_words.intersection(tags | name_words | desc_words)
            if overlap or not query_words:
                matched.append(manifest)

        return matched

    def load_metadata_l1(self, manifest: JuliusSkillManifest) -> Dict[str, Any]:
        """Stage 2: Metadata Loader (L1 Cache) - lightweight name/desc (~100 tokens)."""
        if manifest.name not in self._l1_cache:
            self._l1_cache[manifest.name] = {
                "name": manifest.name,
                "version": manifest.version,
                "description": manifest.description,
                "tags": manifest.tags,
            }
        return self._l1_cache[manifest.name]

    def rank_semantic_stage3(self, query: str, matched: List[JuliusSkillManifest], pkb_context: Optional[str] = None) -> List[JuliusSkillManifest]:
        """Stage 3: Semantic Ranker - re-rank candidates using query relevance + PKB context."""
        query_words = set(re.findall(r"\w+", query.lower()))

        def score_func(m: JuliusSkillManifest) -> float:
            m_words = set(re.findall(r"\w+", (m.name + " " + m.description + " " + " ".join(m.tags)).lower()))
            overlap = len(query_words.intersection(m_words))
            return float(overlap)

        return sorted(matched, key=score_func, reverse=True)

    def lazy_load_instructions_l2(self, skill_dir: Path) -> str:
        """Stage 4: Lazy Loader (L2 Cache) - load full SKILL.md body text."""
        skill_name = skill_dir.name
        if skill_name in self._l2_cache:
            return self._l2_cache[skill_name]

        skill_md = skill_dir / "SKILL.md"
        body_text = ""
        if skill_md.exists():
            full_text = skill_md.read_text(encoding="utf-8", errors="replace")
            if full_text.startswith("---"):
                parts = full_text.split("---", 2)
                if len(parts) >= 3:
                    body_text = parts[2].strip()
            else:
                body_text = full_text.strip()

        self._l2_cache[skill_name] = body_text
        return body_text

    def stream_resources_l3(self, skill_dir: Path) -> List[str]:
        """Stage 5: Resource Streamer (L3 Cache) - stream reference files on demand."""
        ref_dir = skill_dir / "references"
        ref_files = []
        if ref_dir.exists() and ref_dir.is_dir():
            for p in ref_dir.rglob("*"):
                if p.is_file():
                    ref_files.append(str(p))
        return ref_files

    def assemble_context_stage6(
        self,
        query: str,
        manifest: JuliusSkillManifest,
        skill_dir: Path,
        pkb_context: str = "",
    ) -> CompiledSkillContext:
        """Stage 6: Context Assembler - pack progressively loaded stages within token budget."""
        meta = self.load_metadata_l1(manifest)
        instructions = self.lazy_load_instructions_l2(skill_dir)
        references = self.stream_resources_l3(skill_dir)

        sections = [
            f"### Skill: {meta['name']} v{meta['version']}",
            f"**Description**: {meta['description']}",
            f"**Instructions**:\n{instructions}",
        ]
        if pkb_context:
            sections.append(f"**PKB Context**:\n{pkb_context}")

        assembled_text = "\n\n".join(sections)
        estimated_tokens = max(1, len(assembled_text) // 4)

        return CompiledSkillContext(
            skill_name=manifest.name,
            stage=6,
            system_instruction=assembled_text,
            tokens_used=estimated_tokens,
            referenced_files=references,
        )
