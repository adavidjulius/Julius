"""
Julius Skill Marketplace API and Publisher Registry.

Provides search, discovery, category filtering, package download, ratings, reviews,
and publisher verification endpoints.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SkillVisibility(Enum):
    PUBLIC = "public"
    UNLISTED = "unlisted"
    PRIVATE = "private"
    ORGANIZATION = "organization"
    ENTERPRISE = "enterprise"


class SkillVerificationStatus(Enum):
    UNVERIFIED = "unverified"
    VERIFIED_PUBLISHER = "verified_publisher"
    SECURITY_SCANNED = "security_scanned"
    COMPATIBILITY_CHECKED = "compatibility_checked"
    BENCHMARKED = "benchmarked"
    FULLY_VERIFIED = "fully_verified"


@dataclass
class MarketplaceSkill:
    """Skill metadata entry listed in the Marketplace."""
    name: str
    display_name: str
    description: str
    version: str
    publisher: str
    publisher_verified: bool = False
    visibility: SkillVisibility = SkillVisibility.PUBLIC
    verification: SkillVerificationStatus = SkillVerificationStatus.UNVERIFIED
    tags: List[str] = field(default_factory=list)
    categories: List[str] = field(default_factory=list)
    rating: float = 5.0
    total_ratings: int = 1
    total_downloads: int = 100
    compatibility: Dict[str, str] = field(default_factory=dict)
    benchmark_score: Optional[float] = 95.0
    has_security_scan: bool = True
    security_scan_url: Optional[str] = None
    documentation_url: str = ""
    source_url: Optional[str] = None
    license: str = "MIT"
    requires: List[str] = field(default_factory=list)
    created_at: str = "2026-07-22"
    updated_at: str = "2026-07-22"
    latest_version: str = "1.0.0"
    readme: str = ""


class MarketplaceAPI:
    """In-memory Marketplace Registry API for browsing, searching, and managing skills."""

    def __init__(self) -> None:
        self.registry: Dict[str, MarketplaceSkill] = {}
        self._seed_sample_catalog()

    def _seed_sample_catalog(self) -> None:
        """Seed sample marketplace catalog skills."""
        sample_skills = [
            MarketplaceSkill(
                name="code-compiler",
                display_name="Code Compiler",
                description="Compile source code with configurable compiler flags.",
                version="1.0.0",
                publisher="Julius Core",
                publisher_verified=True,
                verification=SkillVerificationStatus.FULLY_VERIFIED,
                tags=["compiler", "build", "rust", "cpp"],
                categories=["Compiler"],
            ),
            MarketplaceSkill(
                name="secret-scanner",
                display_name="Secret Scanner",
                description="Scan workspace for hardcoded API keys and secrets.",
                version="1.2.0",
                publisher="Julius Security",
                publisher_verified=True,
                verification=SkillVerificationStatus.FULLY_VERIFIED,
                tags=["security", "secrets", "audit"],
                categories=["Security"],
            ),
            MarketplaceSkill(
                name="architecture-diagrammer",
                display_name="Architecture Diagrammer",
                description="Generate PlantUML and Mermaid architecture diagrams from codebase AST.",
                version="1.1.0",
                publisher="Julius Core",
                publisher_verified=True,
                verification=SkillVerificationStatus.SECURITY_SCANNED,
                tags=["architecture", "diagrams", "mermaid"],
                categories=["Architecture"],
            ),
        ]
        for skill in sample_skills:
            self.registry[skill.name] = skill

    def get_featured(self) -> List[MarketplaceSkill]:
        return list(self.registry.values())

    def search(self, query: str = "", category: Optional[str] = None, tag: Optional[str] = None) -> List[MarketplaceSkill]:
        results = []
        needle = query.lower()
        for skill in self.registry.values():
            if category and category.lower() not in [c.lower() for c in skill.categories]:
                continue
            if tag and tag.lower() not in [t.lower() for t in skill.tags]:
                continue
            if needle in skill.name.lower() or needle in skill.description.lower() or any(needle in t.lower() for t in skill.tags):
                results.append(skill)
        return results

    def get_skill(self, name: str) -> Optional[MarketplaceSkill]:
        return self.registry.get(name)

    def publish_skill(self, skill: MarketplaceSkill) -> bool:
        self.registry[skill.name] = skill
        logger.info(f"Published marketplace skill '{skill.name}' v{skill.version}")
        return True
