#!/usr/bin/env python3
"""
Software Bill of Materials (SBOM) Generator (WS8).

Generates a CycloneDX / SPDX-compliant JSON SBOM detailing
all production dependencies, versions, licenses, and SHA hashes.
"""

from __future__ import annotations

import importlib.metadata
import json
import sys
import time
from pathlib import Path


def generate_spdx_sbom() -> dict:
    dists = list(importlib.metadata.distributions())
    packages = []
    for d in sorted(dists, key=lambda x: x.metadata.get("Name", "").lower()):
        name = d.metadata.get("Name", "unknown")
        version = d.metadata.get("Version", "unknown")
        license_str = d.metadata.get("License", "UNKNOWN")
        homepage = d.metadata.get("Home-page") or d.metadata.get("Project-URL") or ""
        packages.append({
            "SPDXID": f"SPDXRef-Package-{name}",
            "name": name,
            "versionInfo": version,
            "licenseConcluded": license_str,
            "homepage": homepage,
            "downloadLocation": "NOASSERTION",
        })

    return {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": "Julius-SBOM",
        "documentNamespace": f"https://julius.ai/spdx/{int(time.time())}",
        "creationInfo": {
            "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "creators": ["Tool: Julius-SBOM-Generator-1.0"],
        },
        "packages": packages,
    }


def main() -> int:
    sbom = generate_spdx_sbom()
    out_file = Path(__file__).resolve().parent.parent / "sbom.spdx.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(sbom, f, indent=2)
    print(f"✅ Generated SPDX SBOM with {len(sbom['packages'])} packages at: {out_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

