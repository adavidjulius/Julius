import unittest
from pathlib import Path
import tempfile
import shutil

from src.security.zephon369 import zephon369, zephon369_hex, meets_pow_target
from src.security.audit import CryptographicAuditLedger
from src.integrations.zephon import ZephonClient, ZephonAuditNotary
from src.commands import JULIUS_SLASH_COMMANDS
from src.tools import DEFERRED_TOOL_SCHEMAS, CORE_TOOL_SCHEMAS


class TestZephonBackendIntegrationInJulius(unittest.TestCase):
    """
    Validates that Zephon is strictly a backend security/infrastructure layer
    with zero leak into the user-facing frontend, slash commands, or tool schemas.
    """

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_zephon369_cryptographic_primitive(self):
        data = "Julius Agent Workspace Checkpoint 2026"
        h = zephon369_hex(data)
        self.assertEqual(len(h), 93)
        self.assertEqual(h, zephon369_hex(data))  # Deterministic

        # Different input yields different hash
        h2 = zephon369_hex(data + "_modified")
        self.assertNotEqual(h, h2)

        # PoW target check
        self.assertTrue(meets_pow_target("0000abcde", 4))
        self.assertFalse(meets_pow_target("000abcde", 4))

    def test_zephon_client_offline_safety(self):
        # Must fail fast and not raise unhandled exceptions
        client = ZephonClient(node_url="http://localhost:59999", timeout=0.5)
        self.assertFalse(client.is_available())

    def test_zephon_notary_offline_safety(self):
        notary = ZephonAuditNotary(node_url="http://localhost:59999")
        res = notary.anchor_checkpoint({"head_hash": "test_hash_123", "ts": "2026-11-09T00:00:00Z"})
        self.assertEqual(res["status"], "skipped")
        self.assertEqual(res["reason"], "zephon_node_unavailable")

    def test_audit_ledger_backend_anchor(self):
        ledger_path = Path(self.test_dir) / "audit_chain.jsonl"
        ledger = CryptographicAuditLedger(ledger_path=ledger_path)
        ledger.append_entry("agent", "code_edit", "allowed", "rule.write", {"file": "main.py"})

        res = ledger.anchor_to_zephon(node_url="http://localhost:59999")
        self.assertIn("status", res)
        self.assertTrue(ledger_path.exists())

    def test_zero_frontend_leak_guarantee(self):
        # Verify no Zephon slash commands exist in the UI command list
        for cmd in JULIUS_SLASH_COMMANDS:
            self.assertNotIn("zephon", cmd.lower())

        # Verify no Zephon tool exists in core or deferred tool schemas
        self.assertNotIn("Zephon", DEFERRED_TOOL_SCHEMAS)
        self.assertNotIn("Zephon", CORE_TOOL_SCHEMAS)


if __name__ == "__main__":
    unittest.main()
