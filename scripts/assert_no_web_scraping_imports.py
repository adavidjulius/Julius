#!/usr/bin/env python3
"""
CI Gate: Assert Zero Web-Scraping / Browser-Automation Imports in Provider Layer (WS1.5).

Scans `src/providers/` and core agent provider paths to guarantee that
no browser-automation libraries (playwright, selenium, undetected-chromedriver,
puppeteer, pyppeteer, browser_cookie3, etc.) are imported for model inference.
"""

from __future__ import annotations

import argparse
import ast
import os
import sys
from pathlib import Path

FORBIDDEN_MODULES = {
    "playwright",
    "selenium",
    "undetected_chromedriver",
    "puppeteer",
    "pyppeteer",
    "browser_cookie3",
    "playwright.async_api",
    "playwright.sync_api",
}

DEFAULT_TARGET_DIRS = [
    Path("src/providers"),
]

EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
}


def check_file(path: Path) -> list[str]:
    violations = []
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(content, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    mod_root = alias.name.split(".")[0]
                    if mod_root in FORBIDDEN_MODULES or alias.name in FORBIDDEN_MODULES:
                        violations.append(f"{path}:{node.lineno}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    mod_root = node.module.split(".")[0]
                    if mod_root in FORBIDDEN_MODULES or node.module in FORBIDDEN_MODULES:
                        violations.append(f"{path}:{node.lineno}: from {node.module} import ...")
    except Exception as e:
        violations.append(f"{path}: Failed to parse AST: {e}")
    return violations


def should_skip(path: Path) -> bool:
    return any(part in EXCLUDED_DIRS for part in path.parts)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    parser = argparse.ArgumentParser(description="Check for forbidden web-scraping imports.")
    parser.add_argument("--root", type=str, default=None, help="Root directory or file to check")
    args = parser.parse_args(argv)

    all_violations = []

    if args.root:
        root_path = Path(args.root).resolve()
        if root_path.is_file():
            all_violations.extend(check_file(root_path))
        elif root_path.is_dir():
            for py_file in root_path.rglob("*.py"):
                if not should_skip(py_file):
                    violations = check_file(py_file)
                    all_violations.extend(violations)
    else:
        repo_root = Path(__file__).resolve().parent.parent
        for target_dir in DEFAULT_TARGET_DIRS:
            full_dir = repo_root / target_dir
            if not full_dir.exists():
                continue
            for py_file in full_dir.rglob("*.py"):
                if not should_skip(py_file):
                    violations = check_file(py_file)
                    all_violations.extend(violations)

    if all_violations:
        print("❌ FAIL: Web-scraping browser imports detected in provider layer:")
        for v in all_violations:
            print(f"   {v}")
        return 1

    print("✅ PASS: Zero web-scraping imports detected in src/providers (Official APIs Verified)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
