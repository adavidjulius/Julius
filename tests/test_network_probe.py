"""
Tests for Stage 3: network_probe.py — Real network condition measurement.

These tests verify that measure_network() produces concrete numeric evidence,
not generic unverified assertions. Key invariants:
- All numeric fields are either a real float or None (with an error message).
- summary always contains numeric evidence when measurements succeeded.
- is_degraded reflects actual threshold logic, not a hardcoded result.
"""

from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from src.network_probe import (
    measure_network,
    NetworkMeasurement,
    _probe_ping,
    _probe_download_speed,
    _compute_degraded,
    _build_summary,
    _fmt_speed,
    _DEGRADED_PING_MS,
    _DEGRADED_LOSS_PCT,
    _DEGRADED_SPEED_BPS,
)


# ---------------------------------------------------------------------------
# Unit tests for threshold / summary logic (no network calls)
# ---------------------------------------------------------------------------

class TestComputeDegraded:
    """Tests for the degradation threshold logic."""

    def test_good_connection_not_degraded(self):
        assert _compute_degraded(50.0, 0.0, 5_000_000) is False

    def test_high_ping_is_degraded(self):
        assert _compute_degraded(_DEGRADED_PING_MS + 1, 0.0, 5_000_000) is True

    def test_high_loss_is_degraded(self):
        assert _compute_degraded(50.0, _DEGRADED_LOSS_PCT + 1, 5_000_000) is True

    def test_slow_download_is_degraded(self):
        assert _compute_degraded(50.0, 0.0, _DEGRADED_SPEED_BPS - 1) is True

    def test_all_none_not_degraded(self):
        # If we have no measurements, we can't claim degraded
        assert _compute_degraded(None, None, None) is False

    def test_partial_measurement_degraded_by_ping(self):
        assert _compute_degraded(600.0, None, None) is True

    def test_partial_measurement_degraded_by_loss(self):
        assert _compute_degraded(None, 50.0, None) is True


class TestFormatSpeed:
    """Tests for _fmt_speed helper."""

    def test_kilobytes(self):
        assert 'KB/s' in _fmt_speed(100_000)

    def test_megabytes(self):
        assert 'MB/s' in _fmt_speed(5_000_000)


class TestBuildSummary:
    """Tests that summary always includes evidence."""

    def test_good_connection_summary_has_numbers(self):
        summary = _build_summary(50.0, 0.0, 500_000, False, None, None)
        assert '50' in summary        # ping RTT
        assert 'KB/s' in summary or 'MB/s' in summary  # speed
        assert 'functional' in summary

    def test_degraded_connection_summary_says_degraded(self):
        summary = _build_summary(600.0, 0.0, 1_000, True, None, None)
        assert 'DEGRADED' in summary

    def test_error_summary_reports_error_not_generic(self):
        summary = _build_summary(None, None, None, False, 'ping timed out after 15s', 'curl binary not found')
        # Must report the actual error messages, not "network seems fine"
        assert 'ping timed out' in summary
        assert 'curl binary not found' in summary

    def test_partial_success_reports_what_succeeded(self):
        # Ping succeeded, speed check failed
        summary = _build_summary(100.0, 2.0, None, False, None, 'curl timed out')
        assert '100' in summary  # ping RTT should be in summary
        assert 'curl timed out' in summary


# ---------------------------------------------------------------------------
# Integration test: real measure_network() call
# ---------------------------------------------------------------------------

class TestMeasureNetworkReal:
    """Integration test — calls the real measure_network() function.

    This confirms that the function:
    1. Runs without crashing
    2. Returns a NetworkMeasurement dataclass
    3. Produces a summary with actual evidence (not a vacuous string)
    4. All numeric fields are either real floats or None (never fabricated)
    """

    def test_measure_network_returns_measurement(self):
        """measure_network() must return a NetworkMeasurement — no exceptions."""
        result = measure_network()
        assert isinstance(result, NetworkMeasurement)

    def test_summary_is_not_empty_or_generic(self):
        """Summary must contain some concrete information, not a placeholder."""
        result = measure_network()
        assert len(result.summary) > 10
        # Must NOT be a vague generic claim with no evidence
        assert result.summary != 'network seems fine'
        assert result.summary != 'connection ok'
        assert result.summary != ''

    def test_summary_contains_numeric_evidence_or_explicit_error(self):
        """Either the summary has a number (RTT / speed) or reports a specific error."""
        result = measure_network()
        summary = result.summary
        has_number = any(char.isdigit() for char in summary)
        has_error_word = any(w in summary.lower() for w in [
            'failed', 'not found', 'timed out', 'error', 'unavailable', 'unparseable'
        ])
        assert has_number or has_error_word, (
            f"Summary has neither a numeric measurement nor an error explanation: {summary!r}"
        )

    def test_ping_result_is_float_or_none_not_fabricated(self):
        """ping_ms must be a real float ≥ 0 if set, or None with a ping_error."""
        result = measure_network()
        if result.ping_ms is not None:
            assert isinstance(result.ping_ms, float)
            assert result.ping_ms >= 0.0
        else:
            # If ping_ms is None, there must be a ping_error explaining why
            assert result.ping_error is not None, (
                "ping_ms is None but ping_error is also None — "
                "this is a fabricated/assumed result without evidence"
            )

    def test_download_bps_is_float_or_none_not_fabricated(self):
        """download_bps must be a real float ≥ 0 if set, or None with speed_error."""
        result = measure_network()
        if result.download_bps is not None:
            assert isinstance(result.download_bps, float)
            assert result.download_bps >= 0.0
        else:
            assert result.speed_error is not None, (
                "download_bps is None but speed_error is also None — "
                "this is a fabricated/assumed result without evidence"
            )

    def test_is_degraded_reflects_measured_values(self):
        """is_degraded must logically follow from the actual measured values."""
        result = measure_network()
        expected = _compute_degraded(result.ping_ms, result.packet_loss_pct, result.download_bps)
        assert result.is_degraded == expected, (
            f"is_degraded={result.is_degraded} does not match threshold computation "
            f"(ping={result.ping_ms}, loss={result.packet_loss_pct}, speed={result.download_bps})"
        )


# ---------------------------------------------------------------------------
# Mocked unit tests for _probe_ping and _probe_download_speed
# ---------------------------------------------------------------------------

class TestProbePingParsing:
    """Test ping output parsing without real network calls."""

    def test_parses_macos_style_output(self):
        macos_output = (
            "PING 8.8.8.8 (8.8.8.8): 56 data bytes\n"
            "64 bytes from 8.8.8.8: icmp_seq=0 ttl=57 time=14.123 ms\n"
            "64 bytes from 8.8.8.8: icmp_seq=1 ttl=57 time=13.456 ms\n"
            "64 bytes from 8.8.8.8: icmp_seq=2 ttl=57 time=15.789 ms\n"
            "--- 8.8.8.8 ping statistics ---\n"
            "3 packets transmitted, 3 packets received, 0.0% packet loss\n"
            "round-trip min/avg/max/stddev = 13.456/14.456/15.789/0.959 ms\n"
        )
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                stdout=macos_output, stderr='', returncode=0
            )
            avg_ms, loss_pct, error = _probe_ping()
        assert error is None
        assert avg_ms == pytest.approx(14.456)
        assert loss_pct == pytest.approx(0.0)

    def test_parses_linux_style_output(self):
        linux_output = (
            "PING 8.8.8.8 56(84) bytes of data.\n"
            "64 bytes from 8.8.8.8: icmp_seq=1 ttl=57 time=312 ms\n"
            "--- 8.8.8.8 ping statistics ---\n"
            "3 packets transmitted, 3 received, 0% packet loss, time 2003ms\n"
            "rtt min/avg/max/mdev = 312.000/315.000/320.000/2.000 ms\n"
        )
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                stdout=linux_output, stderr='', returncode=0
            )
            avg_ms, loss_pct, error = _probe_ping()
        assert error is None
        assert avg_ms == pytest.approx(315.0)
        assert loss_pct == pytest.approx(0.0)

    def test_handles_100_percent_loss(self):
        loss_output = (
            "PING 8.8.8.8: 56 data bytes\n"
            "--- 8.8.8.8 ping statistics ---\n"
            "3 packets transmitted, 0 received, 100% packet loss\n"
        )
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                stdout=loss_output, stderr='', returncode=1
            )
            avg_ms, loss_pct, error = _probe_ping()
        assert loss_pct == pytest.approx(100.0)

    def test_reports_error_on_timeout(self):
        import subprocess
        with patch('subprocess.run', side_effect=subprocess.TimeoutExpired('ping', 15)):
            avg_ms, loss_pct, error = _probe_ping()
        assert avg_ms is None
        assert loss_pct is None
        assert 'timed out' in error


class TestProbeDownloadSpeedParsing:
    """Test download speed parsing without real network calls."""

    def test_parses_curl_speed_output(self):
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                stdout='184523.456', stderr='', returncode=0
            )
            bps, error = _probe_download_speed()
        assert error is None
        assert bps == pytest.approx(184523.456)

    def test_handles_empty_curl_output(self):
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                stdout='', stderr='Connection refused', returncode=7
            )
            bps, error = _probe_download_speed()
        assert bps is None
        assert error is not None
        assert 'no speed value' in error

    def test_handles_curl_not_found(self):
        with patch('subprocess.run', side_effect=FileNotFoundError):
            bps, error = _probe_download_speed()
        assert bps is None
        assert 'not found' in error
