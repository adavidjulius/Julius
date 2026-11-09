"""
zephon369.py — Quantum-Hardened 369-Bit Cryptographic Hash Primitive for Julius.

Combines SHA3-512 (sponge construction) and BLAKE2b-512 (keyed permutation)
via 512-bit XOR mixing and truncates to 369 bits (46 bytes + 1 bit).
Provides ~184-bit effective quantum resistance against Grover's algorithm.
"""

from __future__ import annotations

import hashlib
from typing import Union


def zephon369(data: Union[bytes, str]) -> bytes:
    """
    Computes a 369-bit Zephon-369 hash digest (47 bytes, byte 46 contains 1 bit).

    Round 1: SHA3-512
    Round 2: BLAKE2b-512 keyed with r1[:32]
    Mix    : XOR both 512-bit outputs
    Trunc  : 46 full bytes + 1 bit from byte 47
    """
    if isinstance(data, str):
        data = data.encode("utf-8")

    r1 = hashlib.sha3_512(data).digest()
    r2 = hashlib.blake2b(data, key=r1[:32], digest_size=64).digest()

    mixed = bytes(a ^ b for a, b in zip(r1, r2))
    # 46 full bytes (368 bits) + 1 bit from byte 46
    return mixed[:46] + bytes([(mixed[46] >> 7) & 1])


def zephon369_hex(data: Union[bytes, str]) -> str:
    """
    Returns 93-character hex representation of Zephon-369:
    92 hex characters (46 bytes) + "0" or "1" (the 369th bit).
    """
    digest = zephon369(data)
    return digest[:46].hex() + str(digest[46])


def meets_pow_target(hex_hash: str, difficulty: int) -> bool:
    """Verifies if a Zephon-369 hex hash satisfies a given PoW difficulty."""
    if difficulty <= 0:
        return True
    return hex_hash.startswith("0" * difficulty)
