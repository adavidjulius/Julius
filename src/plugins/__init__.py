"""
Julius Plugin & Skill Marketplace Subsystem.

Provides hot-reloadable skill discovery, dynamic runtime toggles,
and sandboxed execution environments for autonomous capabilities.
"""

from __future__ import annotations

from .loader import SkillLoader, SkillManifest
from .registry import PluginRegistry, get_plugin_registry
from .wasm_runtime import WasmPluginEngine, WasmPluginManifest
from .isolation import IsolatedPluginRunner, PluginCapabilityManifest

__all__ = [
    "SkillLoader",
    "SkillManifest",
    "PluginRegistry",
    "get_plugin_registry",
    "WasmPluginEngine",
    "WasmPluginManifest",
    "IsolatedPluginRunner",
    "PluginCapabilityManifest",
]
