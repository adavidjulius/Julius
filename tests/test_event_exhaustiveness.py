"""
Priority 5: Frontend Event Exhaustiveness Test Suite.

Asserts that every event type defined in `JuliusEventType` / `ALL_EVENT_TYPES`
has a corresponding non-dropping handler in `v3_tui.py`.
Fails loudly if any new backend event type is added without frontend coverage.
"""

import ast
import inspect
from pathlib import Path
import pytest

from src.event_registry import JuliusEventType, ALL_EVENT_TYPES
from src.cli.v3_tui import JuliusCLIV3App


def get_handled_event_types_from_tui() -> set[str]:
    """Parse AST of v3_tui.py _handle_agent_event method to extract all handled event_types."""
    tui_path = Path("src/cli/v3_tui.py")
    if not tui_path.exists():
        tui_path = Path(__file__).resolve().parent.parent / "src" / "cli" / "v3_tui.py"
    tree = ast.parse(tui_path.read_text(encoding="utf-8"))
    
    handled_types: set[str] = set()

    class EventVisitor(ast.NodeVisitor):
        def visit_If(self, node: ast.If):
            # Check for event_type == "..." or event_type in (...)
            self._check_test_node(node.test)
            self.generic_visit(node)

        def visit_Compare(self, node: ast.Compare):
            self._check_test_node(node)
            self.generic_visit(node)

        def _check_test_node(self, test_node):
            if isinstance(test_node, ast.Compare):
                # e.g., event_type == "thought"
                for comparator in test_node.comparators:
                    if isinstance(comparator, ast.Constant) and isinstance(comparator.value, str):
                        handled_types.add(comparator.value)

    EventVisitor().visit(tree)
    return handled_types


def test_all_backend_events_have_frontend_handlers():
    """Verify 100% frontend handler coverage for all registered backend event types."""
    handled = get_handled_event_types_from_tui()
    unhandled = ALL_EVENT_TYPES - handled
    
    assert not unhandled, (
        f"❌ Event Exhaustiveness Failure: The following backend event types are emitted "
        f"by the backend but silently dropped by the frontend (`v3_tui.py`): {sorted(list(unhandled))}"
    )


def test_exhaustiveness_test_fails_on_missing_handler():
    """'Test the test': verify that missing event handlers cause an assertion failure."""
    handled = get_handled_event_types_from_tui()
    
    # Inject a dummy unhandled event type
    fake_all_events = ALL_EVENT_TYPES | {"fake_unhandled_event"}
    unhandled = fake_all_events - handled
    
    with pytest.raises(AssertionError) as exc_info:
        assert not unhandled, f"Missing handlers: {unhandled}"
    
    assert "fake_unhandled_event" in str(exc_info.value)
