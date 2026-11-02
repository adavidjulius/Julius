"""
Julius Audit CLI Command (WS2.6).

Verifies the cryptographic continuity of the HMAC-chained audit ledger.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from src.security.audit import CryptographicAuditLedger


def run_audit_verify(ledger_path: Optional[str] = None) -> int:
    """Verify audit log integrity and print results."""
    ledger = CryptographicAuditLedger(ledger_path=ledger_path)
    print("\n🔍 Verifying Julius Cryptographic Audit Chain...")
    ok, message, count = ledger.verify_chain()
    if ok:
        print(f"✅ PASS: Audit chain verified successfully ({count} entries validated).")
        print(f"   Status: {message}\n")
        return 0
    else:
        print(f"❌ FAIL: Tampering or corruption detected in audit chain!")
        print(f"   Details: {message}\n")
        return 1

