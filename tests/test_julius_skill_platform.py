"""
Unit test suite for the complete Julius Skill Platform Architecture.

Verifies:
1. Semver & manifest loading.
2. Capability permission engine & tokens.
3. SAT dependency resolver.
4. Progressive 6-stage context loader.
5. Production skill runtime execution & hooks.
6. Skill installer (.lum archives & checksums).
7. Skill Marketplace API.
8. CapabilityRegistry & Catalog integration.
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
import pytest

from src.skills.manifest import JuliusSkillManifest, SemverVersion
from src.skills.permission_manager import SkillPermissionManager
from src.skills.resolver import SATDependencyResolver
from src.skills.context_loader import ProgressiveSkillContextLoader
from src.skills.runtime import ProductionSkillRuntime
from src.skills.installer import SkillInstaller
from src.skills.marketplace import MarketplaceAPI, MarketplaceSkill
from src.skills.registry import CapabilityRegistry


def test_semver_parsing_and_constraints():
    """Verify SemVer parsing and requirement satisfaction."""
    v1 = SemverVersion.parse("1.2.3")
    assert v1.major == 1 and v1.minor == 2 and v1.patch == 3

    assert v1.satisfies(">=1.0.0") is True
    assert v1.satisfies("^1.0.0") is True
    assert v1.satisfies("~1.2.0") is True
    assert v1.satisfies(">=2.0.0") is False


def test_permission_manager():
    """Verify capability negotiation and token authorization."""
    mgr = SkillPermissionManager()
    token = mgr.create_capability_token(
        skill_name="code-compiler",
        role="standard",
        required=["filesystem.read"],
        optional=["terminal.execute"],
        denied=["database.query"],
    )

    assert token.validate("filesystem.read") is True
    assert token.validate("terminal.execute") is True
    assert token.validate("database.query") is False


def test_sat_dependency_resolver():
    """Verify transitive dependency tree resolution."""
    resolver = SATDependencyResolver()

    dep1 = JuliusSkillManifest(name="helper-utils", version="1.0.0", description="Helper")
    root = JuliusSkillManifest(
        name="my-skill",
        version="2.0.0",
        description="Main skill",
        dependencies={"helper-utils": ">=1.0.0"},
    )

    resolver.register_available_manifest(dep1)
    tree = resolver.resolve(root)

    assert tree.success is True
    assert "my-skill" in tree.nodes
    assert "helper-utils" in tree.nodes


def test_progressive_context_loader():
    """Verify 6-stage progressive disclosure loader."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        skill_dir = Path(tmp_dir) / "sec_skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# Security Skill\nPerform deep audit.", encoding="utf-8")

        manifest = JuliusSkillManifest(name="sec_skill", version="1.0.0", description="Audit security", tags=["security"])
        loader = ProgressiveSkillContextLoader()

        matched = loader.match_intent("Run security audit", [manifest])
        assert len(matched) == 1

        compiled = loader.assemble_context_stage6("Run security audit", manifest, skill_dir)
        assert compiled.stage == 6
        assert "Security Skill" in compiled.system_instruction


def test_production_skill_runtime():
    """Verify sandboxed skill runtime execution and hooks."""
    runtime = ProductionSkillRuntime()
    hook_called = []

    def on_pre_execute(payload):
        hook_called.append("pre_execute")

    runtime.register_hook("pre_execute", on_pre_execute)

    manifest = JuliusSkillManifest(
        name="test-skill",
        version="1.0.0",
        description="Test",
        permissions={"required": ["filesystem.read"]},
    )

    res = runtime.execute_skill(manifest, {"cmd": "run"})
    assert res.status == "SUCCESS"
    assert "pre_execute" in hook_called


def test_skill_installer_and_lum_archives():
    """Verify creating and installing .lum package archives."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        src_dir = Path(tmp_dir) / "my_custom_skill"
        src_dir.mkdir()
        (src_dir / "JULIUS_SKILL.yaml").write_text("name: my_custom_skill\nversion: 1.0.0\ndescription: Custom skill\n", encoding="utf-8")
        (src_dir / "SKILL.md").write_text("# Custom Skill Instructions", encoding="utf-8")

        installer = SkillInstaller(workspace_root=tmp_dir)

        # Create .lum archive
        archive_path = Path(tmp_dir) / "my_custom_skill.lum"
        installer.create_lum_archive(src_dir, archive_path)
        assert archive_path.exists()

        # Install from archive
        record = installer.install_from_lum_archive(archive_path)
        assert record.name == "my_custom_skill"
        assert record.install_path.exists()


def test_marketplace_api():
    """Verify Marketplace search and discovery API."""
    api = MarketplaceAPI()
    featured = api.get_featured()
    assert len(featured) >= 3

    search_res = api.search("compiler")
    assert len(search_res) >= 1
    assert search_res[0].name == "code-compiler"


@pytest.mark.asyncio
async def test_capability_registry_catalog():
    """Verify CapabilityRegistry integration with built-in production skill catalog."""
    registry = CapabilityRegistry()
    caps = registry.discover_capabilities()

    assert "julius/skill/code-compiler" in caps["skills"]
    assert "COMPILE_CODE" in caps["actions"]

    skill_instance = registry.get_skill("julius/skill/code-compiler")
    assert skill_instance is not None

    res = await skill_instance.execute({"command": "python3 -m py_compile"})
    assert res.success is True
    assert "python3" in res.output
