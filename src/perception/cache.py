"""
Perception Cache Module

Computes image hashes to cache visual analysis and avoid redundant vision inference on duplicate frames.
"""

import hashlib
import logging
from typing import Any, Dict, List, Optional, Tuple
from PIL import Image
import io

logger = logging.getLogger(__name__)

class PerceptionCache:
    def __init__(self, dhash_threshold: int = 2) -> None:
        self.prev_hash: Optional[str] = None
        self.prev_detections: List[Dict[str, Any]] = []
        self.dhash_threshold = dhash_threshold

    def get_exact_hash(self, image_bytes: bytes) -> str:
        """Returns SHA-256 hash of raw image bytes."""
        return hashlib.sha256(image_bytes).hexdigest()

    def get_dhash(self, image_bytes: bytes) -> str:
        """
        Computes the Difference Hash (dhash) of the image.
        Suitable for near-duplicate frame detection.
        """
        try:
            img = Image.open(io.BytesIO(image_bytes)).convert('L').resize((9, 8), Image.Resampling.BILINEAR)
            pixels = list(img.getdata())
            
            # Compute difference between adjacent pixels horizontally
            diff = []
            for row in range(8):
                for col in range(8):
                    left = pixels[row * 9 + col]
                    right = pixels[row * 9 + col + 1]
                    diff.append(left > right)
            
            # Convert boolean array to hex string
            decimal_val = 0
            hex_string = []
            for index, value in enumerate(diff):
                if value:
                    decimal_val += 2 ** (index % 8)
                if (index % 8) == 7:
                    hex_string.append(hex(decimal_val)[2:].zfill(2))
                    decimal_val = 0
            return "".join(hex_string)
        except Exception as exc:
            logger.error("Failed to compute dhash: %s", exc)
            return ""

    def should_skip(self, image_bytes: bytes) -> Tuple[bool, List[Dict[str, Any]]]:
        """
        Checks if the image matches the previous image within the similarity threshold.
        Returns:
            Tuple of (should_skip: bool, cached_detections: list)
        """
        if not image_bytes:
            return False, []

        curr_exact = self.get_exact_hash(image_bytes)
        
        # 1. Check exact match
        if self.prev_hash == curr_exact:
            logger.debug("Exact frame match. Skipping vision pipeline.")
            return True, self.prev_detections

        # 2. Check perceptual match (dhash)
        curr_dhash = self.get_dhash(image_bytes)
        if hasattr(self, 'prev_dhash') and self.prev_dhash and curr_dhash:
            hamming_dist = self._hamming_distance(self.prev_dhash, curr_dhash)
            if hamming_dist <= self.dhash_threshold:
                logger.debug("Near-identical frame match (distance: %d). Skipping vision pipeline.", hamming_dist)
                return True, self.prev_detections

        # Store for next check
        self.prev_hash = curr_exact
        self.prev_dhash = curr_dhash
        return False, []

    def update(self, detections: List[Dict[str, Any]]) -> None:
        """Updates the cache with the latest visual detections."""
        self.prev_detections = detections

    def _hamming_distance(self, hex_a: str, hex_b: str) -> int:
        """Computes Hamming distance between two hex strings."""
        if len(hex_a) != len(hex_b):
            return 999
        val_a = int(hex_a, 16)
        val_b = int(hex_b, 16)
        return bin(val_a ^ val_b).count('1')
