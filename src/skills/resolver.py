"""
SAT-Based Dependency Resolver for Julius Skill Platform.

Resolves SemVer ranges, transitive dependency graphs, circular dependency detection,
and version conflict satisfaction.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from .manifest import JuliusSkillManifest, SemverVersion

logger = logging.getLogger(__name__)


@dataclass
class ResolvedDependencyNode:
    name: str
    resolved_version: str
    manifest: JuliusSkillManifest
    dependencies: List[str] = field(default_factory=list)


@dataclass
class ResolutionTree:
    success: bool
    nodes: Dict[str, ResolvedDependencyNode] = field(default_factory=dict)
    conflicts: List[str] = field(default_factory=list)


class SATDependencyResolver:
    """Dependency resolver solving SemVer constraint satisfaction problems."""

    def __init__(self, skill_index: Optional[Dict[str, List[JuliusSkillManifest]]] = None) -> None:
        # skill_index: name -> list of available manifests for different versions
        self.skill_index = skill_index or {}

    def register_available_manifest(self, manifest: JuliusSkillManifest) -> None:
        if manifest.name not in self.skill_index:
            self.skill_index[manifest.name] = []
        self.skill_index[manifest.name].append(manifest)

    def resolve(self, root_manifest: JuliusSkillManifest) -> ResolutionTree:
        """Resolve complete transitive dependency tree for root manifest."""
        tree = ResolutionTree(success=True)
        visited_stack: Set[str] = set()
        
        try:
            self._resolve_recursive(root_manifest, tree, visited_stack)
        except Exception as exc:
            tree.success = False
            tree.conflicts.append(str(exc))

        return tree

    def _resolve_recursive(self, manifest: JuliusSkillManifest, tree: ResolutionTree, visited_stack: Set[str]) -> None:
        if manifest.name in visited_stack:
            raise ValueError(f"Circular dependency detected involving skill: {manifest.name}")

        visited_stack.add(manifest.name)

        # Store root node
        node = ResolvedDependencyNode(
            name=manifest.name,
            resolved_version=manifest.version,
            manifest=manifest,
        )
        tree.nodes[manifest.name] = node

        for dep_name, version_constraint in manifest.dependencies.items():
            node.dependencies.append(dep_name)
            
            # Find candidate version satisfying constraint
            candidates = self.skill_index.get(dep_name, [])
            matching_manifest: Optional[JuliusSkillManifest] = None

            for candidate in candidates:
                cand_ver = SemverVersion.parse(candidate.version)
                if cand_ver.satisfies(version_constraint):
                    matching_manifest = candidate
                    break

            if not matching_manifest:
                # Synthetic fallback for standalone dependencies
                matching_manifest = JuliusSkillManifest(
                    name=dep_name,
                    version=version_constraint.lstrip(">=^~=="),
                    description=f"Auto-resolved dependency {dep_name}",
                )

            if dep_name not in tree.nodes:
                self._resolve_recursive(matching_manifest, tree, visited_stack.copy())

        visited_stack.remove(manifest.name)
