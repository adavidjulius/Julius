"""
Runtime Perception Scheduler Module

Orchestrates the entire end-to-end perception-planning-execution-verification loop.
"""

import logging
import asyncio
import time
from typing import Any, Dict, List, Optional, Tuple

from ..perception.capture import capture_state
from ..perception.accessibility import AccessibilityTreeParser
from ..perception.dom_parser import DOMParser
from ..perception.omniparser import OmniParser
from ..perception.fusion import DOMVisualFusion
from ..perception.scene_graph import SceneGraph
from ..perception.diff_engine import DiffEngine
from ..perception.cache import PerceptionCache

from ..planner.planner import Planner

from ..executor.click import click_element
from ..executor.keyboard import type_text, press_key
from ..executor.mouse import hover_element, scroll_page, drag_element
from ..executor.verify import ActionVerifier

from .world_model import WorldModel
from .event_bus import EventBus

logger = logging.getLogger(__name__)

class PerceptionScheduler:
    def __init__(self, llm_client: Any = None) -> None:
        # Core components
        self.ax_parser = AccessibilityTreeParser()
        self.dom_parser = DOMParser()
        self.omniparser = OmniParser()
        self.fusion = DOMVisualFusion()
        self.diff_engine = DiffEngine()
        self.cache = PerceptionCache()
        
        self.planner = Planner(llm_client)
        self.verifier = ActionVerifier()
        self.world_model = WorldModel()
        self.event_bus = EventBus()

    async def step(self, page: Any, goal: str) -> Tuple[bool, str]:
        """
        Executes a single end-to-end perception-planning-execution-verification step.
        
        Returns:
            Tuple of (done_flag: bool, summary_string: str)
        """
        # Save URL state for verification later
        prev_url = page.url if hasattr(page, "url") else ""

        # Event: Start step
        self.event_bus.publish("step_start", {"time": time.time(), "goal": goal})

        # ── STAGE 1: Parallel Capture ──────────────────────────────────────────
        capture_start = time.monotonic()
        ax_tree, dom_html, screenshot_bytes = await capture_state(page)
        capture_latency = (time.monotonic() - capture_start) * 1000.0
        self.event_bus.publish("capture_done", {"latency_ms": capture_latency})

        # ── STAGE 2 & Optimization: Cache check & OmniParser ───────────────────
        skip_visual, visual_detections = self.cache.should_skip(screenshot_bytes)
        
        if not skip_visual:
            # Call visual detection
            visual_detections = self.omniparser.detect(screenshot_bytes)
            self.cache.update(visual_detections)

        # ── STAGE 3: Accessibility / DOM Extraction & Fusion ───────────────────
        dom_elements = await self.dom_parser.parse(page)
        fused_elements = self.fusion.fuse(dom_elements, visual_detections)

        # ── STAGE 4: Scene Graph Construction ──────────────────────────────────
        scene_graph = SceneGraph()
        scene_graph.build(fused_elements)

        # ── STAGE 5 & 6: Diff Engine & World Model ──────────────────────────────
        diffs = self.diff_engine.diff(scene_graph)
        self.world_model.update(scene_graph, diffs)

        # ── STAGE 7: Planner Reasoning ──────────────────────────────────────────
        action, args, thought = await self.planner.plan(goal, scene_graph, diffs)
        self.event_bus.publish("planner_decision", {"action": action, "args": args, "thought": thought})
        logger.info("Planner Decision: %s with args %s. Thought: %s", action, args, thought)

        if action == "done":
            summary = args.get("summary", "Goal completed.")
            self.event_bus.publish("step_done", {"success": True, "summary": summary})
            return True, summary

        # ── STAGE 8: Executor Actions ───────────────────────────────────────────
        executor_start = time.monotonic()
        success = False
        
        if action == "click":
            success = await click_element(page, args.get("element_id", ""), scene_graph)
        elif action == "type":
            success = await type_text(page, args.get("element_id", ""), args.get("text", ""), scene_graph)
        elif action == "press":
            success = await press_key(page, args.get("key", ""))
        elif action == "hover":
            success = await hover_element(page, args.get("element_id", ""), scene_graph)
        elif action == "scroll":
            success = await scroll_page(page, args.get("direction", "down"))
        elif action == "drag":
            success = await drag_element(page, args.get("source_id", ""), args.get("target_id", ""), scene_graph)
        elif action == "wait":
            ms = args.get("ms", 1000)
            await asyncio.sleep(ms / 1000.0)
            success = True

        exec_latency = (time.monotonic() - executor_start) * 1000.0
        self.event_bus.publish("execution_done", {"action": action, "success": success, "latency_ms": exec_latency})

        # ── STAGE 9: Verification ──────────────────────────────────────────────
        if success:
            verified = await self.verifier.verify(page, action, args, prev_url)
            self.event_bus.publish("verification_done", {"verified": verified})
            if not verified:
                logger.warning("Verification failed for action '%s'", action)
        else:
            logger.error("Action execution failed for '%s'", action)

        return False, f"Executed action: {action}"
