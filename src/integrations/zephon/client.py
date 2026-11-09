"""
Julius Zephon Integration Client.
Enables Julius AI copilot to interact with the local or remote Zephon (ZPH) blockchain node.
"""

from __future__ import annotations

import json
import logging
import urllib.request
import urllib.error
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

DEFAULT_NODE_URL = "http://localhost:8332"
DEFAULT_TIMEOUT = 2.0


class ZephonClient:
    """HTTP JSON-RPC Client for Zephon Core."""

    def __init__(self, node_url: str = DEFAULT_NODE_URL, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.node_url = node_url.rstrip("/")
        self.timeout = timeout

    def _get(self, path: str) -> Dict[str, Any]:
        url = f"{self.node_url}{path}"
        req = urllib.request.Request(url, headers={"User-Agent": "Julius-Agent/1.0"})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _post(self, path: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{self.node_url}{path}"
        data = json.dumps(payload or {}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json", "User-Agent": "Julius-Agent/1.0"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def is_available(self) -> bool:
        """Check if Zephon node is running and reachable."""
        try:
            status = self.get_status()
            return status.get("chain") == "Zephon" or "height" in status
        except Exception:
            return False

    def get_status(self) -> Dict[str, Any]:
        """Fetch chain stats (height, difficulty, latest_hash, mempool_txs)."""
        return self._get("/status")

    def get_balance(self, address: str) -> float:
        """Fetch ZPH balance for an address."""
        res = self._get(f"/balance/{address}")
        return float(res.get("balance", 0.0))

    def get_blocks(self, limit: int = 10, offset: int = 0) -> Dict[str, Any]:
        """Fetch recent blocks."""
        return self._get(f"/blocks?limit={limit}&offset={offset}")

    def get_block(self, index: int) -> Dict[str, Any]:
        """Fetch a specific block by index."""
        return self._get(f"/block/{index}")

    def mine_block(self) -> Dict[str, Any]:
        """Trigger mining of a new block on the connected node."""
        return self._post("/mine")

    def broadcast_transaction(self, tx_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Broadcast a signed transaction map to the mempool."""
        return self._post("/tx/send", tx_dict)
