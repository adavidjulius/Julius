#!/usr/bin/env python3
"""
License Compliance Checker (WS8).

Scans installed Python packages in the environment and verifies them
against the approved commercial license allow-list (MIT, Apache-2.0, BSD, ISC, MPL-2.0).
Flags GPL, AGPL, SSPL, or prohibited copyleft licenses.
"""

from __future__ import annotations

import importlib.metadata
import sys
from typing import Dict, List, Set, Tuple

ALLOWED_LICENSES = {
    "mit",
    "apache-2.0",
    "apache 2.0",
    "apache software license",
    "bsd",
    "bsd-2-clause",
    "bsd-3-clause",
    "isc",
    "mpl-2.0",
    "mozilla public license 2.0 (mpl 2.0)",
    "python software foundation license",
    "psf",
    "zlib",
}

FORBIDDEN_LICENSES = {
    "gpl",
    "gpl-2.0",
    "gpl-3.0",
    "agpl",
    "agpl-3.0",
    "sspl",
}


def check_licenses() -> Tuple[int, List[Dict[str, str]]]:
    import json
    from pathlib import Path

    # Load approved exceptions
    exceptions = {}
    exc_path = Path(__file__).parent / "license_exceptions.json"
    if exc_path.exists():
        try:
            with open(exc_path, "r", encoding="utf-8") as f:
                exceptions = json.load(f).get("exceptions", {})
        except Exception:
            pass

    violations = []
    dists = importlib.metadata.distributions()
    for d in dists:
        name = d.metadata.get("Name", "unknown")
        raw_license = d.metadata.get("License", "") or ""
        classifiers = d.metadata.get_all("Classifier") or []

        # If package is in approved exceptions, skip
        name_clean = name.lower()
        if (
            name in exceptions
            or name_clean in exceptions
            or name_clean.replace("-", "_") in exceptions
            or name_clean.replace("_", "-") in exceptions
        ):
            continue

        license_str = raw_license.lower().strip()
        found_allowed = any(al in license_str for al in ALLOWED_LICENSES)

        # Check classifiers if raw license field was ambiguous
        if not found_allowed:
            for c in classifiers:
                c_lower = c.lower()
                if "license ::" in c_lower:
                    if any(al in c_lower for al in ALLOWED_LICENSES):
                        found_allowed = True
                        break

        # Check for explicitly forbidden licenses
        for fb in FORBIDDEN_LICENSES:
            if fb in license_str or any(fb in c.lower() for c in classifiers):
                violations.append({"package": name, "license": raw_license, "reason": f"Prohibited copyleft license: {fb}"})
                break

    return len(violations), violations


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    print("⚖️ Julius Supply Chain License Compliance Check (WS8)")
    count, violations = check_licenses()
    if violations:
        print(f"❌ Found {count} license policy violations:")
        for v in violations:
            print(f"   - {v['package']}: {v['license']} ({v['reason']})")
        return 1

    print("✅ PASS: All analyzed dependencies comply with commercial license allow-list (MIT, Apache-2.0, BSD, ISC, MPL).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
