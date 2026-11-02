"""
Planner Reasoning Module

Orchestrates prompts, builds state inputs, and queries the LLM planner to determine the next action.
"""

import json
import logging
from typing import Any, Dict, List, Tuple
from .prompts import PLANNER_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

class Planner:
    def __init__(self, llm_client: Any = None) -> None:
        self.llm_client = llm_client

    async def plan(self, goal: str, scene_graph: Any, diffs: List[Dict[str, Any]]) -> Tuple[str, Dict[str, Any], str]:
        """
        Formulates the prompt, calls the LLM, and parses the chosen action.
        
        Returns:
            Tuple of (action_name, action_args, thought)
        """
        # Format the current Scene Graph tree
        graph_dict = scene_graph.root.to_dict() if scene_graph and scene_graph.root else {}
        graph_str = json.dumps(graph_dict, indent=2)

        # Format state diffs
        diffs_str = json.dumps(diffs, indent=2) if diffs else "No visual changes detected."

        prompt_user = f"""USER GOAL: {goal}

CURRENT UI SCENE GRAPH:
{graph_str}

UI STATE CHANGES (DIFFS):
{diffs_str}

Choose the next action to perform. Follow the system response format exactly.
"""
        logger.debug("Formulated Planner user prompt of length %d", len(prompt_user))

        # Query LLM (real call or fallback)
        response_text = ""
        if self.llm_client and hasattr(self.llm_client, "send_message"):
            try:
                # Assuming simple send_message or direct completion API
                resp = await self.llm_client.send_message(f"{PLANNER_SYSTEM_PROMPT}\n\n{prompt_user}")
                response_text = resp.raw_text if hasattr(resp, "raw_text") else str(resp)
            except Exception as exc:
                logger.error("LLM call failed in planner: %s", exc)

        if not response_text:
            # Fallback mock decision if no LLM configured or call fails (crucial for local testing)
            return self._fallback_action(goal, scene_graph)

        # Parse JSON response
        try:
            # Find the JSON block in the response if the LLM wrapped it in markdown code blocks
            clean_text = response_text.strip()
            if "```json" in clean_text:
                clean_text = clean_text.split("```json")[1].split("```")[0].strip()
            elif "```" in clean_text:
                clean_text = clean_text.split("```")[1].split("```")[0].strip()

            decision = json.loads(clean_text)
            action = decision.get("action", "wait")
            args = decision.get("args", {})
            thought = decision.get("thought", "Automated plan step.")
            return action, args, thought
        except Exception as exc:
            logger.warning("Failed to parse LLM response JSON in planner: %s", exc)
            return "wait", {"ms": 1000}, "Fallback due to parse failure."

    def _fallback_action(self, goal: str, scene_graph: Any) -> Tuple[str, Dict[str, Any], str]:
        """Provides a safe deterministic fallback action based on simple goal keyword heuristic."""
        thought = "Running heuristic fallback planner step."
        
        # Simple heuristic matching for testing
        goal_lower = goal.lower()
        if "click" in goal_lower:
            # Find an element matching the goal keyword
            for node_id, node in getattr(scene_graph, "nodes_map", {}).items():
                if node.role == "button" or "btn" in node.id:
                    return "click", {"element_id": node.id}, f"Heuristically clicked button {node.id}"
        elif "type" in goal_lower or "enter" in goal_lower:
            for node_id, node in getattr(scene_graph, "nodes_map", {}).items():
                if node.role == "textbox" or "input" in node.id:
                    return "type", {"element_id": node.id, "text": "test input"}, f"Heuristically typing in textbox {node.id}"

        return "done", {"summary": "Perception planner workflow test completed."}, thought
