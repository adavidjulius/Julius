#!/usr/bin/env python3
"""
Auto-fix tool for 'except Exception: pass' patterns across the codebase.
Replaces bare exception swallowing with proper logging.

Categories:
  PASS_WITHOUT_VAR - "except Exception: pass"
  PASS_WITH_VAR    - "except Exception as e: pass"
  LOG_ONLY         - already has logger but no exc_info
  NEEDS_SPECIFIC   - should use specific exception type

Usage:
  python3 scripts/fix_except_patterns.py            # Scan only (dry-run)
  python3 scripts/fix_except_patterns.py --apply    # Apply fixes
  python3 scripts/fix_except_patterns.py --file src/action_executor.py  # Fix single file
"""

import argparse
import logging
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("fix_except")

# Paths that are SAFE to auto-fix with PASS -> LOGGER replacement
SAFE_FIX_CATEGORIES = {
    "pass_no_var": {
        "pattern": re.compile(
            r'except\s+Exception\s*:\s*\n\s+pass\s*',
            re.MULTILINE,
        ),
        "replacement": 'except Exception:\n            logger.warning("Operation failed", exc_info=True)',
    },
    "pass_with_var": {
        "pattern": re.compile(
            r'except\s+Exception\s+as\s+(\w+)\s*:\s*\n\s+pass\s*',
            re.MULTILINE,
        ),
        "replacement": lambda m: f'except Exception as {m.group(1)}:\n            logger.warning(f"Operation failed: {{{m.group(1)}}}", exc_info=True)',
    },
}

# Files to exclude from auto-fix (complex control flow)
EXCLUDE_FILES = {
    "src/browser/actions.py",  # Complex browser dispatch logic
    "src/browser/engine.py",   # Engine startup/shutdown has intentional silencing
}

# Files with HIGH priority (agent execution path)
HIGH_PRIORITY_FILES = [
    "src/web_agent.py",
    "src/action_executor.py",
    "src/llm_web_client.py",
    "src/rag_engine.py",
    "src/ledger.py",
    "src/security_policy.py",
    "src/shell_manager.py",
    "src/memory/engine.py",
    "src/memory/storage.py",
    "src/memory/retriever.py",
    "src/memory/updater.py",
    "src/memory/composer.py",
    "src/memory/agent_state.py",
]


def scan_file(filepath: str) -> List[Tuple[int, str, str]]:
    """Scan a file and return list of (line_number, pattern_type, context)."""
    results = []
    try:
        with open(filepath) as f:
            content = f.read()

        for match in SAFE_FIX_CATEGORIES["pass_no_var"]["pattern"].finditer(content):
            line_num = content[: match.start()].count("\n") + 1
            results.append((line_num, "PASS_NO_VAR", match.group()))

        for match in SAFE_FIX_CATEGORIES["pass_with_var"]["pattern"].finditer(content):
            line_num = content[: match.start()].count("\n") + 1
            results.append((line_num, "PASS_WITH_VAR", match.group()))

    except Exception as e:
        logger.error(f"Error scanning {filepath}: {e}")

    return results


def fix_file(filepath: str, dry_run: bool = True) -> bool:
    """Fix except Exception: pass patterns in a file."""
    try:
        with open(filepath) as f:
            content = f.read()

        original = content
        changed = False

        # Fix PASS_NO_VAR
        content = SAFE_FIX_CATEGORIES["pass_no_var"]["pattern"].sub(
            SAFE_FIX_CATEGORIES["pass_no_var"]["replacement"], content
        )
        if content != original:
            changed = True

        # Fix PASS_WITH_VAR
        before = content
        content = SAFE_FIX_CATEGORIES["pass_with_var"]["pattern"].sub(
            lambda m: f'except Exception as {m.group(1)}:\n            logger.warning(f"Operation failed: {{{m.group(1)}}}", exc_info=True)',
            content,
        )
        if content != before:
            changed = True

        if changed:
            # Ensure logger is imported/defined
            if "logger" not in content and "logging" not in content.split("import")[0]:
                # Add logger declaration after imports
                import_section_end = content.find("\n\n", content.rfind("\nimport")) 
                if import_section_end == -1:
                    import_section_end = content.find("\n\n", content.find("import"))
                if import_section_end == -1:
                    import_section_end = content.find("\n\n", content.find("from"))
                if import_section_end == -1:
                    import_section_end = content.find("\n", content.find("import"))
                if import_section_end == -1:
                    import_section_end = 0
                
                logger_line = '\nimport logging\nlogger = logging.getLogger(__name__)\n'
                content = content[:import_section_end] + logger_line + content[import_section_end:]

            if not dry_run:
                with open(filepath, "w") as f:
                    f.write(content)
                logger.info(f"FIXED: {filepath}")
            else:
                logger.info(f"WOULD FIX: {filepath} (dry-run)")

        return changed

    except Exception as e:
        logger.error(f"Error fixing {filepath}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Fix except Exception: pass patterns")
    parser.add_argument("--apply", action="store_true", help="Apply fixes (dry-run by default)")
    parser.add_argument("--file", type=str, help="Fix a single file")
    parser.add_argument("--scan-only", action="store_true", help="Only scan, don't fix")
    args = parser.parse_args()

    if args.file:
        # Fix single file
        rel_path = os.path.relpath(args.file)
        matches = scan_file(rel_path)
        if matches:
            print(f"\n📄 {rel_path}:")
            for line_num, ptype, ctx in matches:
                print(f"   Line {line_num}: [{ptype}] {ctx[:60].strip()}...")
            if not args.scan_only:
                fixed = fix_file(rel_path, dry_run=not args.apply)
                if fixed:
                    print(f"   → {'FIXED' if args.apply else 'WOULD FIX (dry-run)'}")
        else:
            print(f"✅ {rel_path}: No fixable patterns found")
        return

    # Scan all Python files in src/
    src_dir = Path("src")
    all_results: Dict[str, List] = {}

    print("🔍 Scanning for 'except Exception: pass' patterns...")
    print()

    for py_file in sorted(src_dir.rglob("*.py")):
        rel_path = str(py_file.relative_to("."))
        if rel_path in EXCLUDE_FILES:
            continue
        matches = scan_file(rel_path)
        if matches:
            all_results[rel_path] = matches

    # Report
    total = sum(len(v) for v in all_results.values())
    print(f"Found {total} fixable patterns across {len(all_results)} files\n")

    for filepath, matches in sorted(all_results.items()):
        is_high = "⭐" if filepath in HIGH_PRIORITY_FILES else "  "
        print(f"{is_high} {filepath}: {len(matches)} pattern(s)")
        for line_num, ptype, ctx in matches[:3]:  # Show first 3
            print(f"      Line {line_num}: {ctx.strip()[:60]}...")
        if len(matches) > 3:
            print(f"      ... and {len(matches)-3} more")

    # Apply fixes
    if args.apply and not args.scan_only:
        print(f"\n{'='*60}")
        print(f"Applying fixes to {len(HIGH_PRIORITY_FILES)} high-priority files...")
        fixed_count = 0
        for filepath in HIGH_PRIORITY_FILES:
            if filepath in all_results:
                if fix_file(filepath, dry_run=False):
                    fixed_count += 1
        print(f"\n✅ Fixed {fixed_count} high-priority files")
        
        # Fix remaining files
        remaining = [f for f in all_results if f not in HIGH_PRIORITY_FILES]
        print(f"\nApplying fixes to {len(remaining)} remaining files...")
        fixed_count = 0
        for filepath in remaining:
            if fix_file(filepath, dry_run=False):
                fixed_count += 1
        print(f"\n✅ Fixed {fixed_count} remaining files")
    else:
        print(f"\nRun with --apply to fix all files")
        print(f"Run with --file <path> to fix a single file")


if __name__ == "__main__":
    main()
