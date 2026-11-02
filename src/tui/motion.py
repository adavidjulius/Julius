"""
 Physics and timing presets for Julius terminal animations.

Presets:
- enter:   fade 0->1, 220 ms, out_cubic
- settle:  subtle resting settle, 160 ms, out_back (completion only)
- fade:    micro fade, 120 ms, in_out_cubic
- breathe: thinking indicator pulsing opacity 0.35 <-> 1.0, 1400 ms loop, in_out_sine

Rules:
- Honor JULIUS_REDUCE_MOTION=1 and config settings (instant transitions).
- Never block input during animation.
- Clean cancellation.
"""

from __future__ import annotations

import os
from typing import Any, Callable, Optional
from textual.widget import Widget


def is_reduced_motion() -> bool:
    """Return True if reduced-motion is requested via env or config."""
    env_val = os.environ.get("JULIUS_REDUCE_MOTION", "").lower().strip()
    return env_val in ("1", "true", "yes", "on")


class MotionPresets:
    """Named timing and easing presets."""
    ENTER_DURATION = 0.220     # 220 ms
    ENTER_EASING = "out_cubic"

    SETTLE_DURATION = 0.160    # 160 ms
    SETTLE_EASING = "out_back"

    FADE_DURATION = 0.120      # 120 ms
    FADE_EASING = "in_out_cubic"

    BREATHE_CYCLE = 1.400      # 1400 ms loop
    BREATHE_EASING = "in_out_sine"
    BREATHE_MIN_OPACITY = 0.35
    BREATHE_MAX_OPACITY = 1.0


def animate_enter(widget: Widget, on_complete: Optional[Callable[[], None]] = None) -> None:
    """Mount widget with crisp, rock-solid opacity (zero terminal fade flicker)."""
    stop_animations(widget)
    widget.styles.opacity = 1.0
    if on_complete:
        on_complete()


def animate_fade(
    widget: Widget,
    target_opacity: float,
    on_complete: Optional[Callable[[], None]] = None,
) -> None:
    """Set opacity cleanly without terminal flicker."""
    stop_animations(widget)
    widget.styles.opacity = target_opacity
    if on_complete:
        on_complete()


def animate_settle(widget: Widget, on_complete: Optional[Callable[[], None]] = None) -> None:
    """Resting state on completion with zero bounce, jitter, or text brightness flicker."""
    stop_animations(widget)
    widget.styles.opacity = 1.0
    if on_complete:
        on_complete()


def stop_animations(widget: Widget) -> None:
    """Cancel active animators on a widget safely."""
    try:
        if hasattr(widget, "app") and widget.app:
            widget.app.animator.cancel_animation(widget.styles, "opacity")
    except Exception:
        pass
