#!/usr/bin/env python3
"""
CI Guard: Ensure no raw input() calls exist in backend modules.

This script scans core backend files (web_agent.py, action_executor.py, etc.)
for raw Python `input(` function calls which cause session freezes in TUI/async contexts.
"""

import sys
import re
from pathlib import Path

BACKEND_FILES = [
    Path("src/web_agent.py"),
    Path("src/action_executor.py"),
    Path("src/self_healer.py"),
    Path("src/app_builder/builder.py"),
]

def check_file(path: Path) -> list[tuple[int, str]]:
    if not path.exists():
        return []
    
    violations = []
    lines = path.read_text(encoding="utf-8").splitlines()
    pattern = re.compile(r'(?<![a-zA-Z0-9_])input\(')
    
    for idx, line in enumerate(lines, 1):
        # Ignore comments
        stripped = line.strip()
        if stripped.startswith('#'):
            continue
        if pattern.search(line):
            violations.append((idx, line))
            
    return violations

def main() -> int:
    total_violations = 0
    repo_root = Path(__file__).resolve().parent.parent
    
    print("🔍 Auditing backend modules for prohibited raw input() calls...")
    
    for rel_path in BACKEND_FILES:
        full_path = repo_root / rel_path
        violations = check_file(full_path)
        if violations:
            print(f"❌ VIOLATION FOUND in {rel_path}:")
            for line_no, content in violations:
                print(f"   Line {line_no}: {content.strip()}")
            total_violations += len(violations)
        else:
            print(f"✅ {rel_path}: Clean (no raw input() calls)")

    if total_violations > 0:
        print(f"\n💥 Audit FAILED: {total_violations} raw input() call(s) detected.")
        return 1
    
    print("\n🎉 Audit PASSED: Zero raw input() calls found in backend modules.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
