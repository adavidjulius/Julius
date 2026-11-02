"""
Unit tests for the browser module.

Run with:
  python3 -m pytest src/browser/tests/ -v

These tests cover the structured observation, anti-bot detection,
and the BrowserObservation text serializer without needing a real browser.
"""

import pytest
from src.browser.structured_obs import (
    BrowserObservation,
    InteractiveElement,
    NetworkEntry,
    BotDetection,
    _truncate_url,
)
from src.browser.anti_bot import detect_bot_block, AntiBotMode, pick_stealth_context_options


# ── BrowserObservation ─────────────────────────────────────────────────────────

class TestBrowserObservation:
    def test_empty_observation_to_text(self):
        obs = BrowserObservation(action="browser_navigate")
        text = obs.to_text()
        assert "BROWSER OBSERVATION" in text
        assert "browser_navigate" in text

    def test_success_property_no_error(self):
        obs = BrowserObservation(action="browser_navigate")
        assert obs.success is True

    def test_success_property_with_error(self):
        obs = BrowserObservation(action="browser_navigate", error="timeout")
        assert obs.success is False

    def test_error_appears_in_text(self):
        obs = BrowserObservation(action="browser_click", error="Element not found")
        text = obs.to_text()
        assert "ERROR" in text
        assert "Element not found" in text

    def test_interactive_elements_in_text(self):
        obs = BrowserObservation(
            action="browser_get_snapshot",
            interactive_elements=[
                InteractiveElement(role="button", label="Submit", selector="#submit"),
                InteractiveElement(role="textbox", label="Email", selector="input[type=email]", value="test@example.com"),
            ]
        )
        text = obs.to_text()
        assert "[button]" in text
        assert "Submit" in text
        assert "[textbox]" in text
        assert "Email" in text
        assert "test@example.com" in text

    def test_interactive_elements_capped_at_20_in_text(self):
        obs = BrowserObservation(
            action="browser_get_snapshot",
            interactive_elements=[
                InteractiveElement(role="button", label=f"Btn{i}", selector=f"#b{i}")
                for i in range(25)
            ]
        )
        text = obs.to_text()
        assert "and 5 more" in text

    def test_console_logs_in_text(self):
        obs = BrowserObservation(
            action="browser_navigate",
            console_logs=["[info] page loaded", "[warning] deprecated API"],
        )
        text = obs.to_text()
        assert "CONSOLE" in text
        assert "[info] page loaded" in text

    def test_network_requests_in_text(self):
        obs = BrowserObservation(
            action="browser_navigate",
            network_requests=[
                NetworkEntry(url="https://api.example.com/data", method="GET", status=200, duration_ms=42),
                NetworkEntry(url="https://api.example.com/submit", method="POST", status=422),
            ]
        )
        text = obs.to_text()
        assert "NETWORK" in text
        assert "GET" in text
        assert "200" in text
        assert "POST" in text
        assert "422" in text

    def test_bot_detection_in_text(self):
        obs = BrowserObservation(
            action="browser_navigate",
            bot_detection=BotDetection(
                detected=True,
                detection_type="cloudflare_challenge",
                page_title="Just a moment...",
                suggested_action="Use browser_load_session",
            )
        )
        text = obs.to_text()
        assert "BOT DETECTION" in text
        assert "cloudflare_challenge" in text

    def test_screenshot_in_text(self):
        obs = BrowserObservation(action="browser_navigate", screenshot_path="verify_123.png")
        text = obs.to_text()
        assert "verify_123.png" in text

    def test_extra_data_in_text(self):
        obs = BrowserObservation(
            action="browser_eval_js",
            extra={"js_result": "Hello World"},
        )
        text = obs.to_text()
        assert "EXTRA DATA" in text
        assert "Hello World" in text

    def test_to_dict_is_serialisable(self):
        import json
        obs = BrowserObservation(
            action="browser_navigate",
            url="https://example.com",
            title="Example",
            interactive_elements=[InteractiveElement(role="button", label="OK", selector="#ok")],
            network_requests=[NetworkEntry(url="https://example.com/", method="GET", status=200)],
            bot_detection=BotDetection(detected=False),
        )
        d = obs.to_dict()
        # Should be JSON serializable without error
        serialised = json.dumps(d)
        assert "browser_navigate" in serialised

    def test_dom_snapshot_truncated_in_text(self):
        long_snapshot = "<div>" + ("a" * 100 + "\n") * 100 + "</div>"
        obs = BrowserObservation(action="browser_get_snapshot", dom_snapshot=long_snapshot)
        text = obs.to_text()
        assert "truncated" in text


class TestTruncateUrl:
    def test_short_url_unchanged(self):
        url = "https://example.com/page"
        assert _truncate_url(url) == url

    def test_long_url_truncated(self):
        url = "https://example.com/" + "a" * 100
        result = _truncate_url(url, max_len=30)
        assert len(result) <= 30
        assert result.endswith("...")


# ── Anti-bot ──────────────────────────────────────────────────────────────────

class TestBotDetection:
    def test_no_detection_on_normal_page(self):
        result = detect_bot_block("Welcome to Example", "https://example.com")
        assert result.detected is False

    def test_cloudflare_challenge_by_title(self):
        result = detect_bot_block("Just a moment...", "https://shop.example.com/cart")
        assert result.detected is True
        assert result.detection_type == "cloudflare_challenge"

    def test_access_denied(self):
        result = detect_bot_block("Access Denied", "https://restricted.example.com")
        assert result.detected is True
        assert result.detection_type == "access_denied"

    def test_recaptcha_detected(self):
        result = detect_bot_block("Verify you are human", "https://example.com/login")
        assert result.detected is True
        assert "recaptcha" in result.detection_type

    def test_rate_limited(self):
        result = detect_bot_block("Too Many Requests", "https://api.example.com")
        assert result.detected is True
        assert result.detection_type == "rate_limited"

    def test_suggestion_populated_on_detection(self):
        result = detect_bot_block("Just a moment...", "https://shop.example.com")
        assert len(result.suggested_action) > 0

    def test_case_insensitive(self):
        result = detect_bot_block("CAPTCHA REQUIRED", "https://example.com")
        assert result.detected is True


class TestStealthContextOptions:
    def test_off_mode_returns_viewport_only(self):
        opts = pick_stealth_context_options(AntiBotMode.OFF)
        assert "viewport" in opts
        assert "user_agent" not in opts

    def test_human_mode_has_user_agent(self):
        opts = pick_stealth_context_options(AntiBotMode.HUMAN)
        assert "user_agent" in opts
        assert "viewport" in opts

    def test_stealth_mode_has_sec_fetch_headers(self):
        opts = pick_stealth_context_options(AntiBotMode.STEALTH)
        headers = opts.get("extra_http_headers", {})
        assert "Sec-Fetch-Mode" in headers

    def test_user_agent_rotates(self):
        # Run multiple times — should not always be the same UA
        agents = {pick_stealth_context_options(AntiBotMode.HUMAN).get("user_agent") for _ in range(10)}
        assert len(agents) > 1  # at least 2 different UAs seen
