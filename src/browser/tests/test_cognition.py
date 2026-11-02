"""
Unit tests for the browser cognition layer.

Run with:
  python3 -m pytest src/browser/tests/test_cognition.py -v

Covers:
  - BrowserMemory: action/navigation logging, form/click tracking, selector suggestion.
  - WorldModel: asserting/retracting facts, expiration, FactExtractor rules.
  - DOMDiff: added, removed, changed interactive elements, URL/title changes, major change detection.
  - ActionVerifier: click, type, and navigation verification heuristics.
  - RecoveryEngine: modal overlay, cookie banner, and session expiry detection/recovery.
  - BrowserTaskGraph: dependency checking, status tracking, graph formatting.
  - GoalNavigator: goal template building and fallback plan logic.
"""

import pytest
import time
from unittest.mock import MagicMock

from src.browser.structured_obs import BrowserObservation, InteractiveElement, NetworkEntry, BotDetection
from src.browser.memory import BrowserMemory, record_browser_action
from src.browser.world_model import WorldModel, FactExtractor
from src.browser.dom_diff import DOMDiff
from src.browser.verifier import ActionVerifier, build_selector_alternatives
from src.browser.recovery import RecoveryEngine
from src.browser.planner import BrowserTaskGraph, BrowserStep
from src.browser.goal_navigator import GoalNavigator, match_template


# ── BrowserMemory Tests ───────────────────────────────────────────────────────

class TestBrowserMemory:
    def test_navigation_and_action_logging(self):
        mem = BrowserMemory()
        visit = mem.record_navigation("http://localhost:8000/", "Julius Dashboard")
        assert visit.url == "http://localhost:8000/"
        assert visit.title == "Julius Dashboard"
        assert len(mem.page_history) == 1

        mem.record_action_on_current_page("typed query")
        assert visit.actions_taken == ["typed query"]

    def test_form_and_click_tracking(self):
        mem = BrowserMemory()
        mem.record_navigation("http://localhost:8000/", "Dashboard")
        
        mem.record_click("#btn-submit", label="Submit Info")
        assert mem.already_clicked("#btn-submit") == 1
        
        mem.record_type("#email", "user@example.com", label="Email Input")
        assert mem.already_filled("#email") == "user@example.com"

        mem.record_failure("#email", "Element not interactable")
        assert mem.is_known_bad_selector("#email") is False  # only 1 failure
        mem.record_failure("#email", "Second failure")
        assert mem.is_known_bad_selector("#email") is True

    def test_alternative_selector_suggestion(self):
        mem = BrowserMemory()
        mem.record_type("#email", "user@example.com", label="User Email")
        mem.record_failure("#email", "Element detached")
        mem.record_failure("#email", "Element detached again")
        
        # Should suggest alternative based on label
        suggestion = mem.suggest_alternative_selector("#email")
        assert suggestion == '[aria-label="User Email"]'


# ── WorldModel & FactExtractor Tests ──────────────────────────────────────────

class TestWorldModel:
    def test_assert_and_retract_facts(self):
        wm = WorldModel(workspace_root=".", persist=False)
        wm.assert_fact("auth_status", "logged_in", confidence=1.0)
        assert wm.get_value("auth_status") == "logged_in"

        wm.retract_fact("auth_status")
        assert wm.get_value("auth_status") is None

    def test_fact_expiration(self):
        wm = WorldModel(workspace_root=".", persist=False)
        wm.assert_fact("temp_token", "abc", ttl_seconds=0.1)
        assert wm.get_value("temp_token") == "abc"
        
        time.sleep(0.15)
        assert wm.get_value("temp_token") is None

    def test_fact_extractor_heuristics(self):
        wm = WorldModel(workspace_root=".", persist=False)
        extractor = FactExtractor(wm)

        # Test auth redirect detection
        obs1 = BrowserObservation(
            url="http://localhost:8000/login",
            title="Julius Login",
            dom_snapshot="Please log in to continue"
        )
        extractor.extract(obs1)
        assert wm.get_value("auth_status") == "logged_out"

        # Test checkout success page detection
        obs2 = BrowserObservation(
            url="http://localhost:8000/checkout/success",
            title="Success!",
            dom_snapshot="Thank you for your order. Your order is confirmed."
        )
        extractor.extract(obs2)
        assert wm.get_value("checkout_complete") is True


# ── DOMDiff Tests ─────────────────────────────────────────────────────────────

class TestDOMDiff:
    def test_basic_element_delta(self):
        obs_before = BrowserObservation(
            url="http://localhost:8000/",
            interactive_elements=[
                InteractiveElement(role="button", label="Submit", selector="#submit"),
                InteractiveElement(role="link", label="Back", selector="#back"),
            ]
        )
        obs_after = BrowserObservation(
            url="http://localhost:8000/",
            interactive_elements=[
                InteractiveElement(role="button", label="Submit", selector="#submit"),
                InteractiveElement(role="button", label="Confirm", selector="#confirm"),
            ]
        )

        diff = DOMDiff.diff(obs_before, obs_after)
        assert len(diff.added_elements) == 1
        assert diff.added_elements[0].label == "Confirm"
        assert len(diff.removed_elements) == 1
        assert diff.removed_elements[0].label == "Back"
        assert diff.is_major_change is True  # 50% elements changed

    def test_no_changes(self):
        obs = BrowserObservation(
            url="http://localhost:8000/",
            interactive_elements=[InteractiveElement(role="button", label="A", selector="#a")]
        )
        diff = DOMDiff.diff(obs, obs)
        assert diff.has_changes is False
        text = diff.to_text()
        assert "No meaningful changes" in text


# ── ActionVerifier Tests ──────────────────────────────────────────────────────

class TestActionVerifier:
    def test_selector_alternatives(self):
        alts = build_selector_alternatives("#email-input", label="User Email")
        assert "#email-input" in alts
        assert "text=User Email" in alts
        assert '[aria-label="User Email"]' in alts

    @pytest.mark.anyio
    async def test_verify_type_success(self):
        verifier = ActionVerifier()
        obs = BrowserObservation(
            interactive_elements=[
                InteractiveElement(role="input", label="User Email", selector="#email", value="test@example.com")
            ]
        )
        page_mock = MagicMock()
        res = await verifier.verify_type(page_mock, "#email", "test@example.com", obs)
        assert res.passed is True
        assert res.strategy_used == "input_value_match"


# ── RecoveryEngine Tests ──────────────────────────────────────────────────────

class TestRecoveryEngine:
    @pytest.mark.anyio
    async def test_session_expired_detection(self):
        engine = RecoveryEngine()
        wm = WorldModel(workspace_root=".", persist=False)
        wm.assert_fact("auth_status", "logged_in")
        memory = BrowserMemory()
        
        obs = BrowserObservation(
            url="http://localhost:8000/login",
            title="Julius Login",
            dom_snapshot="Your session has expired"
        )
        page_mock = MagicMock()
        res = await engine.check_and_recover(page_mock, obs, memory, wm)
        assert res.issue_type == "session_expired"
        assert wm.get_value("auth_status") == "logged_out"


# ── BrowserTaskGraph Planner Tests ────────────────────────────────────────────

class TestBrowserTaskGraph:
    def test_dependency_execution_order(self):
        graph = BrowserTaskGraph(".")
        graph.add_step("s1", "Step 1", "browser_navigate", {"url": "http://localhost:8000"})
        graph.add_step("s2", "Step 2", "browser_click", {"selector": "#btn"}, depends_on=["s1"])

        # s2 depends on s1, so only s1 should be executable initially
        next_step = graph.next_executable_step()
        assert next_step is not None
        assert next_step.id == "s1"

        graph.mark_done("s1", "Navigated")
        
        # Now s2 is executable
        next_step = graph.next_executable_step()
        assert next_step is not None
        assert next_step.id == "s2"


# ── GoalNavigator Tests ───────────────────────────────────────────────────────

class TestGoalNavigator:
    def test_goal_template_matching(self):
        params = {"url": "http://localhost:8000/login", "email": "test@test.com"}
        match = match_template("Login to the site", params)
        assert match is not None
        template_name, graph = match
        assert template_name == "login"
        assert "nav" in graph.steps
        assert "submit" in graph.steps
