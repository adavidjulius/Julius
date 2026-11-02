#!/usr/bin/env python3
"""
Wiring Audit (T0.2 / Appendix A).

Builds an import graph starting from production entry points:
- run_agent.py
- juliusd.py
- julius_gui.py
- src/web_agent.py
- src/cli/v3_tui.py
- src/tui/app.py
- src/cli/v2_tui.py
- julius.py
- julius_cli.py

Verifies that new architecture modules under:
src/providers, src/policy, src/sandbox, src/security, src/telemetry,
src/jobs, src/updater, src/licensing, src/auth, src/plugins, src/db
are reachable from production entry points.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

DEFAULT_ENTRY = [
    "run_agent.py",
    "juliusd.py",
    "julius_gui.py",
    "src/web_agent.py",
    "src/cli/v3_tui.py",
    "src/tui/app.py",
    "src/cli/v2_tui.py",
    "julius.py",
    "julius_cli.py",
]

DEFAULT_WATCH = [
    "src/providers",
    "src/policy",
    "src/sandbox",
    "src/security",
    "src/telemetry",
    "src/jobs",
    "src/updater",
    "src/licensing",
    "src/auth",
    "src/plugins",
    "src/db",
]


def parse_list_arg(values: list[str] | None, default: list[str]) -> list[str]:
    """Parse comma-separated and/or repeated arguments."""
    if not values:
        return list(default)
    result = []
    for item in values:
        for part in item.split(","):
            part = part.strip()
            if part:
                result.append(part)
    return result if result else list(default)


def to_file(mod: str, root: Path, from_dir: Path | None = None) -> Path | None:
    """Robust multi-path import resolution (workspace root, src/, caller directory)."""
    if not mod:
        return None

    parts = mod.split(".")
    search_dirs: list[Path] = [root]

    src_dir = root / "src"
    if src_dir.is_dir():
        search_dirs.append(src_dir)

    if from_dir and from_dir.is_dir():
        search_dirs.append(from_dir)

    for s_dir in search_dirs:
        # Check from fullest path down to prefixes (e.g. module.ClassName)
        for k in range(len(parts), 0, -1):
            subparts = parts[:k]
            base = s_dir.joinpath(*subparts)

            cand_py = base.with_suffix(".py")
            if cand_py.is_file():
                return cand_py.resolve()

            cand_init = base / "__init__.py"
            if cand_init.is_file():
                return cand_init.resolve()

    return None


def extract_imports(path: Path, root: Path, verbose: bool = False):
    """Extract imported module strings using AST inspection."""
    try:
        rel = path.resolve().relative_to(root.resolve())
        pkg_parts = list(rel.parent.parts)
    except Exception:
        pkg_parts = []

    try:
        source = path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(source, filename=str(path))
    except Exception as e:
        if verbose:
            print(f"[VERBOSE] Failed to parse AST for {path}: {e}", file=sys.stderr)
        return

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                yield a.name
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                # Relative import: compute base package
                up = node.level - 1
                if len(pkg_parts) >= up:
                    target_pkg = pkg_parts[: len(pkg_parts) - up] if up > 0 else list(pkg_parts)
                else:
                    target_pkg = []
                if node.module:
                    full_parts = target_pkg + node.module.split(".")
                else:
                    full_parts = target_pkg
                base = ".".join(full_parts)
            else:
                base = node.module or ""

            if base:
                yield base
            for a in node.names:
                yield f"{base}.{a.name}" if base else a.name


def reachable(root: Path, entry_points: list[str], verbose: bool = False) -> set[Path]:
    """Build reachable set of modules via BFS from entry points."""
    seen: set[Path] = set()
    stack: list[Path] = []

    for e in entry_points:
        entry_path = (root / e).resolve() if not Path(e).is_absolute() else Path(e).resolve()
        if entry_path.exists() and entry_path.is_file():
            stack.append(entry_path)
            if verbose:
                print(f"[VERBOSE] Active entry point loaded: {entry_path}", file=sys.stderr)
        elif verbose:
            print(f"[VERBOSE] Warning: Entry point not found: {entry_path}", file=sys.stderr)

    while stack:
        f = stack.pop()
        try:
            f = f.resolve()
        except Exception:
            pass
        if f in seen:
            continue
        seen.add(f)

        for m in extract_imports(f, root, verbose=verbose):
            resolved = to_file(m, root, f.parent)
            if resolved:
                try:
                    resolved = resolved.resolve()
                except Exception:
                    pass
                if resolved not in seen:
                    if verbose:
                        print(f"[VERBOSE] {f.name} -> imported '{m}' resolved to {resolved}", file=sys.stderr)
                    stack.append(resolved)

    return seen


def run_wiring_audit(
    root: Path,
    entry_points: list[str],
    watch_dirs: list[str],
    output_format: str = "text",
    verbose: bool = False,
) -> tuple[int, dict]:
    """Execute wiring audit and return (exit_code, result_dict)."""
    live = reachable(root, entry_points, verbose=verbose)
    dead: list[Path] = []

    for w in watch_dirs:
        watch_path = (root / w).resolve() if not Path(w).is_absolute() else Path(w).resolve()
        if not watch_path.exists():
            if verbose:
                print(f"[VERBOSE] Watched path not found (skipping): {watch_path}", file=sys.stderr)
            continue
        for p in watch_path.rglob("*.py"):
            if p.name == "__init__.py" or "__pycache__" in str(p):
                continue
            resolved = p.resolve()
            if resolved not in live:
                try:
                    dead.append(resolved.relative_to(root))
                except Exception:
                    dead.append(resolved)

    dead.sort()
    passed = len(dead) == 0
    exit_code = 0 if passed else 1

    result_data = {
        "status": "PASS" if passed else "FAIL",
        "passed": passed,
        "root": str(root),
        "live_count": len(live),
        "dead_count": len(dead),
        "watched_packages": watch_dirs,
        "unreachable_modules": [str(p) for p in dead],
        "reachable_modules": sorted([str(p.relative_to(root) if p.is_relative_to(root) else p) for p in live]),
    }

    if output_format == "json":
        print(json.dumps(result_data, indent=2))
    else:
        if dead:
            print(f"❌ FAIL: {len(dead)} modules are UNREACHABLE from entry points:")
            for p in dead:
                print(f"   UNREACHABLE: {p}")
        else:
            print(f"✅ PASS: All {len(watch_dirs)} watched packages are reachable from entry points ({len(live)} total live modules).")

    return exit_code, result_data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Julius Architecture Wiring Audit (T0.2)")
    parser.add_argument(
        "--root",
        type=str,
        default=None,
        help="Path to workspace root (defaults to Path.cwd())",
    )
    parser.add_argument(
        "--entry",
        action="append",
        default=None,
        help="Optional comma-separated or repeated list of entry point files",
    )
    parser.add_argument(
        "--watch",
        action="append",
        default=None,
        help="Optional comma-separated or repeated list of packages to audit",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format: text (default) or json",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable detailed per-module import logs",
    )

    args = parser.parse_args(argv)

    root = Path(args.root).resolve() if args.root else Path.cwd().resolve()
    entry_points = parse_list_arg(args.entry, DEFAULT_ENTRY)
    watch_dirs = parse_list_arg(args.watch, DEFAULT_WATCH)

    exit_code, _ = run_wiring_audit(
        root=root,
        entry_points=entry_points,
        watch_dirs=watch_dirs,
        output_format=args.format,
        verbose=args.verbose,
    )
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
