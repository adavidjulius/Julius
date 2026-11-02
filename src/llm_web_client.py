"""
Deprecated: Legacy web client module.
All production model inference is routed through src.providers.ProviderRouter.
Original legacy scraping code has been quarantined under contrib/experimental_web_providers/.
"""

import warnings
from src.providers.router import ProviderRouter, LLMRouter, CircuitBreaker
from src.providers.base import LLMResponse

warnings.warn(
    "src.llm_web_client.WebLLMClient is deprecated under Phase 2 architecture. "
    "Use src.providers.ProviderRouter instead.",
    DeprecationWarning,
    stacklevel=2,
)

WebLLMClient = ProviderRouter
__all__ = ["WebLLMClient", "LLMResponse", "ProviderRouter", "LLMRouter", "CircuitBreaker"]
