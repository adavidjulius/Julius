"""Architecture Discovery Framework for Julius."""

from __future__ import annotations

import sys

# Register module alias in sys.modules so `from arch_discovery...` works directly.
sys.modules["arch_discovery"] = sys.modules[__name__]
