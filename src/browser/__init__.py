"""
src/browser — Julius's first-class Playwright browser engine.

Public surface:
  PlaywrightEngine  — async lifecycle manager (contexts, sessions, pages)
  BrowserObservation — structured JSON observation returned by every action
  BROWSER_ACTIONS   — dispatch table: action_name → async fn
  dispatch          — route action name + args to the right function
"""

from .engine import PlaywrightEngine
from .structured_obs import BrowserObservation, InteractiveElement, NetworkEntry, BotDetection
from .actions import BROWSER_ACTIONS, dispatch
from .anti_bot import AntiBotMode
from .memory import BrowserMemory
from .world_model import WorldModel
from .dom_diff import DOMDiff
from .verifier import ActionVerifier
from .recovery import RecoveryEngine
from .planner import BrowserTaskGraph
from .goal_navigator import GoalNavigator

__all__ = [
    "PlaywrightEngine",
    "BrowserObservation",
    "InteractiveElement",
    "NetworkEntry",
    "BotDetection",
    "BROWSER_ACTIONS",
    "dispatch",
    "AntiBotMode",
    "BrowserMemory",
    "WorldModel",
    "DOMDiff",
    "ActionVerifier",
    "RecoveryEngine",
    "BrowserTaskGraph",
    "GoalNavigator",
]
