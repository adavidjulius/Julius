#!/usr/bin/env python3
"""
CI Gate: Assert Zero Private IP Literals (T1.2).

Scans production code and configuration for hardcoded private-range IPv4 literals
(192.168.x.x, 10.x.x.x, 172.16-31.x.x).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PRIVATE_IP_PATTERN = re.compile(
    r'(?:^|[^0-9])(192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})(?:[^0-9]|$)'
)

DEFAULT_SCAN_TARGETS = [
    Path("src"),
    Path("config"),
]

SCANNED_EXTENSIONS = {".py", ".env", ".toml", ".json", ".yaml", ".yml"}

EXCLUDED_DIR_NAMES = {
    "node_modules",
    ".git",
    ".venv",
    "venv",
    "__pycache__",
}


def should_skip(path: Path) -> bool:
    """Return True if path contains any excluded directory name."""
    return any(part in EXCLUDED_DIR_NAMES for part in path.parts)


def is_scanned_file(path: Path) -> bool:
    """Check if file should be scanned (by extension or env filename)."""
    name = path.name.lower()
    if name == ".env" or name.startswith(".env."):
        return True
    return path.suffix.lower() in SCANNED_EXTENSIONS


def check_file(path: Path) -> list[str]:
    """Scan a single file for private IP literals."""
    violations = []
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
        for line_no, line in enumerate(content.splitlines(), start=1):
            match = PRIVATE_IP_PATTERN.search(line)
            if match:
                violations.append(f"{path}:{line_no}: {match.group(1)} in '{line.strip()}'")
    except Exception as e:
        violations.append(f"{path}: Failed to read file: {e}")
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Assert no hardcoded private IP literals.")
    parser.add_argument("--root", type=str, default=None, help="Root directory or file to check")
    args = parser.parse_args(argv)

    all_violations = []

    if args.root:
        root_path = Path(args.root).resolve()
        if root_path.is_file():
            all_violations.extend(check_file(root_path))
        elif root_path.is_dir():
            for file_path in root_path.rglob("*"):
                if file_path.is_file() and not should_skip(file_path) and is_scanned_file(file_path):
                    all_violations.extend(check_file(file_path))
    else:
        repo_root = Path(__file__).resolve().parent.parent
        for target in DEFAULT_SCAN_TARGETS:
            full_path = repo_root / target
            if not full_path.exists():
                continue
            if full_path.is_file():
                all_violations.extend(check_file(full_path))
            else:
                for file_path in full_path.rglob("*"):
                    if file_path.is_file() and not should_skip(file_path) and is_scanned_file(file_path):
                        all_violations.extend(check_file(file_path))

        # Check root *.py files
        for root_py in repo_root.glob("*.py"):
            if not should_skip(root_py):
                all_violations.extend(check_file(root_py))

        # Check root .env and .env.example
        for env_name in [".env", ".env.example"]:
            env_file = repo_root / env_name
            if env_file.exists() and env_file.is_file():
                all_violations.extend(check_file(env_file))

    if all_violations:
        print("❌ FAIL: Hardcoded private IP literals detected:")
        for v in all_violations:
            print(f"   {v}")
        return 1

    print("✅ PASS: Zero private IP literals detected in production code and configs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
