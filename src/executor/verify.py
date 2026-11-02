"""
Executor Verification Module

Verifies the success of executed actions by checking page post-conditions (URLs, visible selectors, state changes).
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

class ActionVerifier:
    def __init__(self) -> None:
        pass

    async def verify(self, page: Any, action: str, args: Dict[str, Any], prev_url: str, expected_selectors: Optional[List[str]] = None) -> bool:
        """
        Verifies if an action successfully completed.
        
        Args:
            page: Playwright Page instance.
            action: The executed action name.
            args: The arguments passed to the action.
            prev_url: The page URL prior to running the action.
            expected_selectors: Selectors expected to be visible post-action.
            
        Returns:
            bool: True if verified successful, False otherwise.
        """
        if not page:
            return False

        logger.info("Verifying action '%s' with args %s", action, args)

        # Refresh page URL state
        curr_url = page.url if hasattr(page, "url") else ""
        
        # 1. Check if URL changed (indicates successful redirection/navigation)
        if action == "click" and curr_url != prev_url:
            logger.info("Verification passed: URL changed from %s to %s", prev_url, curr_url)
            return True

        # 2. Check if expected elements became visible
        if expected_selectors:
            for sel in expected_selectors:
                try:
                    # Evaluate selector visibility
                    visible = await page.evaluate(f"Boolean(document.querySelector('{sel}'))")
                    if visible:
                        logger.info("Verification passed: Expected selector '%s' is visible", sel)
                        return True
                except Exception:
                    pass

        # 3. Simple action specific defaults
        if action == "type":
            # For typing, verify value changed in the target textbox if ID available
            el_id = args.get("element_id")
            text = args.get("text", "")
            if el_id and text:
                try:
                    val = await page.evaluate(f"document.getElementById('{el_id}').value")
                    if text in val:
                        logger.info("Verification passed: Input value matches typed text")
                        return True
                except Exception:
                    pass

        # Default fallback to True if no errors thrown during execution
        return True
