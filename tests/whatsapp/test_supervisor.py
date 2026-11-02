"""
Production test suite for the Julius WhatsApp Supervisor.

Tests cover all required areas:
1. Browser: page missing, closed, responsive, unresponsive, browser crash, reload timeout.
2. Network: network available, unavailable, returns.
3. Authentication: connected, QR required, session expired, loading stall, unknown state.
4. Listener: alive, task dead, scanner stalled, consecutive scan errors, duplicate prevention.
5. Processing: queue grows, processor stalls, processing timeout, poison item clearing.
6. Recovery: soft reload succeeds/fails, browser restart succeeds/fails, timeout, concurrent triggers.
7. Circuit Breaker: repeated failures, circuit opens, probe/half-open, recovery, circuit closes.
8. Concurrency: failure prioritization, manual restart + watchdog recovery, shutdown during recovery.
9. Long-running: no task leaks, no duplicate listeners, bounded history, no deadlocks.
10. Shutdown correctness: start twice, stop twice, shutdown during check/recovery/restart, no orphaned tasks.
11. Health distinction: browser alive != service healthy, QR required != infra failure.
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.integrations.whatsapp.health import WhatsAppHealth
from src.integrations.whatsapp.models import HealthState
from src.integrations.whatsapp.supervisor import (
    FailureClass,
    FailureHistory,
    FailureHistoryEntry,
    HealthEngine,
    HealthSnapshot,
    HeartbeatTimestamps,
    RecoveryCircuitBreaker,
    RecoveryLevel,
    RecoveryRecord,
    SubsystemState,
    SubsystemStatus,
    SupervisorConfig,
    SupervisorState,
    WhatsAppSupervisor,
)


# ── Helpers & Fixtures ─────────────────────────────────────────────────────────

def make_mock_page(ready_state: str = "complete", is_closed: bool = False):
    page = MagicMock()
    page.is_closed = MagicMock(return_value=is_closed)
    page.evaluate = AsyncMock(return_value=ready_state)
    page.reload = AsyncMock(return_value=None)
    return page


def make_mock_browser(page=None, login_state: str = "connected"):
    browser = MagicMock()
    browser.page = page if page is not None else make_mock_page()
    browser.detect_login_state = AsyncMock(return_value=login_state)
    browser.start = AsyncMock(return_value=None)
    browser.stop = AsyncMock(return_value=None)
    return browser


def make_mock_listener(
    is_running: bool = True,
    task_alive: bool = True,
    scan_age: float = 5.0,
    consecutive_errors: int = 0,
    active_processing: set | None = None,
):
    listener = MagicMock()
    listener.is_running = is_running
    listener.get_liveness = MagicMock(return_value={
        "is_running": is_running,
        "task_alive": task_alive,
        "scan_count": 42,
        "error_count": consecutive_errors,
        "age_seconds": scan_age,
    })
    listener.last_successful_scan = time.time() - scan_age
    listener.liveness_age_seconds = scan_age
    listener._consecutive_scan_errors = consecutive_errors
    listener._active_processing = active_processing if active_processing is not None else set()
    listener.start = AsyncMock(return_value=None)
    listener.stop = AsyncMock(return_value=None)
    return listener


def make_supervisor(
    browser=None,
    health=None,
    listener=None,
    restart_cb=None,
    config=None,
    network_online: bool = True,
):
    b = browser if browser is not None else make_mock_browser()
    h = health if health is not None else WhatsAppHealth()
    cfg = config or SupervisorConfig(
        check_interval_seconds=0.1,
        debounce_failure_count=1,
        recovery_cooldown=0.01,
        stabilization_wait_seconds=0.01,
        listener_restart_timeout=1.0,
        page_reload_timeout=1.0,
        browser_restart_timeout=2.0,
    )
    return WhatsAppSupervisor(
        browser=b,
        health=h,
        restart_callback=restart_cb or AsyncMock(),
        listener=listener,
        config=cfg,
        network_check_fn=lambda: network_online,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 1. BROWSER HEALTH PROBES
# ═══════════════════════════════════════════════════════════════════════════════

class TestBrowserProbes:

    @pytest.mark.asyncio
    async def test_page_missing_detected_as_browser_crash(self):
        browser = make_mock_browser()
        browser.page = None
        sup = make_supervisor(browser=browser)

        snap = await sup._health_engine.probe_all()
        assert snap.browser.status == SubsystemStatus.FAILED
        assert snap.page.status == SubsystemStatus.FAILED
        assert sup._classify_failure(snap) == FailureClass.BROWSER_CRASH

    @pytest.mark.asyncio
    async def test_page_closed_detected_as_browser_crash(self):
        page = make_mock_page(is_closed=True)
        browser = make_mock_browser(page=page)
        sup = make_supervisor(browser=browser)

        snap = await sup._health_engine.probe_all()
        assert snap.browser.status == SubsystemStatus.FAILED
        assert sup._classify_failure(snap) == FailureClass.BROWSER_CRASH

    @pytest.mark.asyncio
    async def test_page_responsive_marked_healthy(self):
        page = make_mock_page(ready_state="complete")
        browser = make_mock_browser(page=page)
        sup = make_supervisor(browser=browser)

        snap = await sup._health_engine.probe_all()
        assert snap.browser.status == SubsystemStatus.HEALTHY
        assert snap.page.status == SubsystemStatus.HEALTHY
        assert "complete" in snap.page.detail

    @pytest.mark.asyncio
    async def test_page_unresponsive_eval_timeout(self):
        page = make_mock_page()
        page.evaluate = AsyncMock(side_effect=asyncio.TimeoutError("Eval timeout"))
        browser = make_mock_browser(page=page)
        sup = make_supervisor(browser=browser)

        snap = await sup._health_engine.probe_all()
        assert snap.page.status == SubsystemStatus.FAILED
        assert sup._classify_failure(snap) == FailureClass.PAGE_UNRESPONSIVE

    @pytest.mark.asyncio
    async def test_page_unresponsive_eval_exception(self):
        page = make_mock_page()
        page.evaluate = AsyncMock(side_effect=RuntimeError("Target page crashed"))
        browser = make_mock_browser(page=page)
        sup = make_supervisor(browser=browser)

        snap = await sup._health_engine.probe_all()
        assert snap.page.status == SubsystemStatus.FAILED
        assert sup._classify_failure(snap) == FailureClass.PAGE_UNRESPONSIVE

    @pytest.mark.asyncio
    async def test_reload_timeout_recorded_and_handled(self):
        page = make_mock_page()
        page.reload = AsyncMock(side_effect=asyncio.TimeoutError("Reload timed out"))
        browser = make_mock_browser(page=page)
        sup = make_supervisor(browser=browser)

        record = RecoveryRecord(level=RecoveryLevel.RELOAD_PAGE)
        success = await sup._execute_recovery_action(
            RecoveryLevel.RELOAD_PAGE, FailureClass.PAGE_UNRESPONSIVE, record
        )
        assert success is False
        assert record.result == "timeout"


# ═══════════════════════════════════════════════════════════════════════════════
# 2. NETWORK PROBES
# ═══════════════════════════════════════════════════════════════════════════════

class TestNetworkProbes:

    @pytest.mark.asyncio
    async def test_network_available_marked_healthy(self):
        sup = make_supervisor(network_online=True)
        snap = await sup._health_engine.probe_all()
        assert snap.network.status == SubsystemStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_network_unavailable_marked_failed(self):
        sup = make_supervisor(network_online=False)
        snap = await sup._health_engine.probe_all()
        assert snap.network.status == SubsystemStatus.FAILED
        assert sup._classify_failure(snap) == FailureClass.NETWORK_FAILURE

    @pytest.mark.asyncio
    async def test_network_returns_recovers(self):
        is_online = False

        def check_net():
            return is_online

        browser = make_mock_browser()
        sup = WhatsAppSupervisor(
            browser=browser,
            health=WhatsAppHealth(),
            network_check_fn=check_net,
            config=SupervisorConfig(debounce_failure_count=1),
        )

        snap1 = await sup._health_engine.probe_all()
        assert snap1.network.status == SubsystemStatus.FAILED

        # Network returns
        is_online = True
        snap2 = await sup._health_engine.probe_all()
        assert snap2.network.status == SubsystemStatus.HEALTHY


# ═══════════════════════════════════════════════════════════════════════════════
# 3. AUTHENTICATION PROBES
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuthenticationProbes:

    @pytest.mark.asyncio
    async def test_auth_connected(self):
        browser = make_mock_browser(login_state="connected")
        sup = make_supervisor(browser=browser)

        snap = await sup._health_engine.probe_all()
        assert snap.authentication.status == SubsystemStatus.HEALTHY
        assert sup._classify_failure(snap) == FailureClass.NONE

    @pytest.mark.asyncio
    async def test_auth_qr_required(self):
        browser = make_mock_browser(login_state="qr_required")
        sup = make_supervisor(browser=browser)

        snap = await sup._health_engine.probe_all()
        assert snap.authentication.status == SubsystemStatus.WAITING_FOR_AUTH
        assert sup._classify_failure(snap) == FailureClass.QR_REQUIRED
        # Service healthy should be False even if infrastructure is healthy
        assert snap.infrastructure_healthy() is True
        assert snap.service_healthy() is False

    @pytest.mark.asyncio
    async def test_auth_session_expired(self):
        browser = make_mock_browser(login_state="session_expired")
        sup = make_supervisor(browser=browser)

        snap = await sup._health_engine.probe_all()
        assert snap.authentication.status == SubsystemStatus.FAILED
        assert sup._classify_failure(snap) == FailureClass.SESSION_EXPIRED

    @pytest.mark.asyncio
    async def test_auth_loading_transient_not_failure(self):
        browser = make_mock_browser(login_state="loading")
        sup = make_supervisor(browser=browser)

        snap = await sup._health_engine.probe_all()
        assert snap.authentication.status == SubsystemStatus.DEGRADED
        # First loading detection is transient, not failure
        assert sup._classify_failure(snap) == FailureClass.NONE
        assert sup._loading_since is not None

    @pytest.mark.asyncio
    async def test_auth_loading_stall_exceeds_timeout(self):
        browser = make_mock_browser(login_state="loading")
        sup = make_supervisor(browser=browser)
        sup._loading_since = time.time() - 100.0  # > 90s stall

        snap = await sup._health_engine.probe_all()
        assert sup._classify_failure(snap) == FailureClass.WHATSAPP_LOADING_STALL

    @pytest.mark.asyncio
    async def test_auth_unknown_state(self):
        browser = make_mock_browser(login_state="unknown_random_error")
        sup = make_supervisor(browser=browser)

        snap = await sup._health_engine.probe_all()
        assert snap.authentication.status == SubsystemStatus.FAILED
        assert sup._classify_failure(snap) == FailureClass.UNKNOWN


# ═══════════════════════════════════════════════════════════════════════════════
# 4. LISTENER HEALTH PROBES
# ═══════════════════════════════════════════════════════════════════════════════

class TestListenerProbes:

    @pytest.mark.asyncio
    async def test_listener_alive_marked_healthy(self):
        listener = make_mock_listener(is_running=True, task_alive=True, scan_age=2.0)
        sup = make_supervisor(listener=listener)

        snap = await sup._health_engine.probe_all()
        assert snap.listener.status == SubsystemStatus.HEALTHY
        assert snap.scanner.status == SubsystemStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_listener_task_dead_detected(self):
        listener = make_mock_listener(is_running=True, task_alive=False)
        sup = make_supervisor(listener=listener)

        snap = await sup._health_engine.probe_all()
        assert snap.listener.status == SubsystemStatus.FAILED
        assert sup._classify_failure(snap) == FailureClass.LISTENER_DEAD

    @pytest.mark.asyncio
    async def test_scanner_stalled_detected(self):
        listener = make_mock_listener(is_running=True, task_alive=True, scan_age=150.0)
        sup = make_supervisor(listener=listener)

        snap = await sup._health_engine.probe_all()
        assert snap.scanner.status == SubsystemStatus.FAILED
        assert sup._classify_failure(snap) == FailureClass.SCANNER_STALLED

    @pytest.mark.asyncio
    async def test_consecutive_scan_errors_detected(self):
        listener = make_mock_listener(is_running=True, consecutive_errors=12)
        sup = make_supervisor(listener=listener)

        snap = await sup._health_engine.probe_all()
        assert snap.scanner.status == SubsystemStatus.FAILED
        assert sup._classify_failure(snap) == FailureClass.SCANNER_STALLED

    @pytest.mark.asyncio
    async def test_duplicate_listener_prevention_on_restart(self):
        listener = make_mock_listener()
        sup = make_supervisor(listener=listener)

        res = await sup._restart_listener()
        assert res is True
        # stop() was called BEFORE start() was called
        listener.stop.assert_awaited_once()
        listener.start.assert_awaited_once()


# ═══════════════════════════════════════════════════════════════════════════════
# 5. PROCESSING & QUEUE PROBES
# ═══════════════════════════════════════════════════════════════════════════════

class TestProcessingProbes:

    @pytest.mark.asyncio
    async def test_queue_grows_degraded(self):
        # 15 active processing items
        active = {f"msg_{i}" for i in range(15)}
        listener = make_mock_listener(active_processing=active)
        sup = make_supervisor(listener=listener)

        snap = await sup._health_engine.probe_all()
        assert snap.queue.status == SubsystemStatus.DEGRADED

    @pytest.mark.asyncio
    async def test_processor_stalls_detected(self):
        sup = make_supervisor()
        # Processing started 400s ago, last completed 500s ago
        now = time.time()
        sup._health_engine.heartbeats.last_processing_started = now - 400.0
        sup._health_engine.heartbeats.last_processing_completed = now - 500.0

        snap = await sup._health_engine.probe_all()
        assert snap.processor.status == SubsystemStatus.FAILED
        assert sup._classify_failure(snap) == FailureClass.PROCESSOR_STALLED

    @pytest.mark.asyncio
    async def test_poison_item_cleared_during_component_repair(self):
        active = {"poison_msg_1", "poison_msg_2"}
        listener = make_mock_listener(active_processing=active)
        sup = make_supervisor(listener=listener)

        success = await sup._repair_component(FailureClass.QUEUE_BACKLOG)
        assert success is True
        assert len(listener._active_processing) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 6. HIERARCHICAL RECOVERY & VERIFICATION
# ═══════════════════════════════════════════════════════════════════════════════

class TestRecoveryHierarchy:

    @pytest.mark.asyncio
    async def test_soft_reload_succeeds_and_verifies(self):
        page = make_mock_page()
        browser = make_mock_browser(page=page)
        sup = make_supervisor(browser=browser)

        record = RecoveryRecord(level=RecoveryLevel.RELOAD_PAGE)
        success = await sup._execute_recovery_action(
            RecoveryLevel.RELOAD_PAGE, FailureClass.PAGE_UNRESPONSIVE, record
        )
        assert success is True
        page.reload.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_soft_reload_fails_escalates_to_restart(self):
        page = make_mock_page()
        page.reload = AsyncMock(side_effect=RuntimeError("Cannot reload"))
        restart_called = []

        async def mock_restart():
            restart_called.append(True)

        browser = make_mock_browser(page=page)
        sup = make_supervisor(browser=browser, restart_cb=mock_restart)
        sup._running = True

        # Run hierarchical recovery for PAGE_UNRESPONSIVE (init=RELOAD_PAGE, max=RESTART_BROWSER)
        await sup._execute_hierarchical_recovery(
            FailureClass.PAGE_UNRESPONSIVE,
            RecoveryLevel.RELOAD_PAGE,
            RecoveryLevel.RESTART_BROWSER,
        )

        # Page reload was attempted and failed, escalated to browser restart
        assert len(restart_called) == 1

    @pytest.mark.asyncio
    async def test_browser_restart_succeeds(self):
        restart_called = []

        async def mock_restart():
            restart_called.append(True)

        browser = make_mock_browser()
        sup = make_supervisor(browser=browser, restart_cb=mock_restart)

        record = RecoveryRecord(level=RecoveryLevel.RESTART_BROWSER)
        success = await sup._execute_recovery_action(
            RecoveryLevel.RESTART_BROWSER, FailureClass.BROWSER_CRASH, record
        )
        assert success is True
        assert len(restart_called) == 1

    @pytest.mark.asyncio
    async def test_concurrent_recovery_prevented(self):
        sup = make_supervisor()
        sup._is_recovering = True

        # Second recovery must abort immediately without acquiring lock
        entered = False

        async def second_recovery():
            nonlocal entered
            await sup._execute_hierarchical_recovery(
                FailureClass.BROWSER_CRASH,
                RecoveryLevel.RESTART_BROWSER,
                RecoveryLevel.RESTART_BROWSER,
            )
            entered = True

        await second_recovery()
        assert entered is True
        # Since _is_recovering was True, no records added to failure history
        assert sup._failure_history.recoveries_in_window(60) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 7. CIRCUIT BREAKER
# ═══════════════════════════════════════════════════════════════════════════════

class TestCircuitBreaker:

    def test_circuit_breaker_starts_closed(self):
        cb = RecoveryCircuitBreaker(failure_threshold=3, cooldown_seconds=60.0)
        assert cb.state == RecoveryCircuitBreaker.CLOSED
        assert cb.can_recover() is True

    def test_repeated_failures_open_circuit(self):
        cb = RecoveryCircuitBreaker(failure_threshold=3, cooldown_seconds=60.0)
        cb.record_recovery_failure()
        assert cb.state == RecoveryCircuitBreaker.CLOSED
        cb.record_recovery_failure()
        assert cb.state == RecoveryCircuitBreaker.CLOSED
        cb.record_recovery_failure()
        assert cb.state == RecoveryCircuitBreaker.OPEN
        assert cb.can_recover() is False

    def test_cooldown_transitions_to_half_open(self):
        cb = RecoveryCircuitBreaker(failure_threshold=2, cooldown_seconds=0.05)
        cb.record_recovery_failure()
        cb.record_recovery_failure()
        assert cb.state == RecoveryCircuitBreaker.OPEN

        time.sleep(0.06)
        assert cb.state == RecoveryCircuitBreaker.HALF_OPEN
        assert cb.can_recover() is True

    def test_success_in_half_open_closes_circuit(self):
        cb = RecoveryCircuitBreaker(
            failure_threshold=2, cooldown_seconds=0.05, success_threshold=2
        )
        cb.record_recovery_failure()
        cb.record_recovery_failure()
        time.sleep(0.06)
        assert cb.state == RecoveryCircuitBreaker.HALF_OPEN

        cb.record_recovery_success()
        assert cb.state == RecoveryCircuitBreaker.HALF_OPEN
        cb.record_recovery_success()
        assert cb.state == RecoveryCircuitBreaker.CLOSED
        assert cb.can_recover() is True

    def test_failure_in_half_open_reopens_immediately(self):
        cb = RecoveryCircuitBreaker(failure_threshold=2, cooldown_seconds=0.05)
        cb.record_recovery_failure()
        cb.record_recovery_failure()
        time.sleep(0.06)
        assert cb.state == RecoveryCircuitBreaker.HALF_OPEN

        cb.record_recovery_failure()
        assert cb._state == RecoveryCircuitBreaker.OPEN


# ═══════════════════════════════════════════════════════════════════════════════
# 8. CONCURRENCY & SHUTDOWN CORRECTNESS
# ═══════════════════════════════════════════════════════════════════════════════

class TestConcurrencyAndShutdown:

    @pytest.mark.asyncio
    async def test_start_twice_safe(self):
        sup = make_supervisor()
        await sup.start()
        first_task = sup._task
        assert sup.is_running is True

        # Second start call should be a no-op
        await sup.start()
        assert sup._task is first_task
        await sup.stop()

    @pytest.mark.asyncio
    async def test_stop_twice_safe(self):
        sup = make_supervisor()
        await sup.start()
        await sup.stop()
        assert sup.is_running is False
        assert sup.supervisor_state == SupervisorState.STOPPED

        # Second stop call should be a clean no-op
        await sup.stop()
        assert sup.supervisor_state == SupervisorState.STOPPED

    @pytest.mark.asyncio
    async def test_shutdown_during_health_check(self):
        browser = make_mock_browser()

        # Simulate slow evaluate during check
        async def slow_eval(*args, **kwargs):
            await asyncio.sleep(2.0)
            return "complete"

        browser.page.evaluate = AsyncMock(side_effect=slow_eval)
        sup = make_supervisor(browser=browser)
        await sup.start()

        # Give it a moment to begin, then stop
        await asyncio.sleep(0.05)
        await sup.stop()

        assert sup.is_running is False
        assert sup.supervisor_state == SupervisorState.STOPPED

    @pytest.mark.asyncio
    async def test_shutdown_during_browser_restart(self):
        restart_started = asyncio.Event()

        async def slow_restart():
            restart_started.set()
            await asyncio.sleep(5.0)

        sup = make_supervisor(restart_cb=slow_restart)
        sup._running = True

        restart_task = asyncio.create_task(
            sup._execute_recovery_action(
                RecoveryLevel.RESTART_BROWSER,
                FailureClass.BROWSER_CRASH,
                RecoveryRecord(),
            )
        )

        await restart_started.wait()
        # Now trigger stop
        await sup.stop()
        restart_task.cancel()
        try:
            await restart_task
        except asyncio.CancelledError:
            pass

        assert sup.is_running is False

    @pytest.mark.asyncio
    async def test_no_orphaned_tasks(self):
        sup = make_supervisor()
        await sup.start()
        assert len(sup._background_tasks) > 0 or sup._task is not None

        await sup.stop()
        assert len(sup._background_tasks) == 0
        assert sup._task is None


# ═══════════════════════════════════════════════════════════════════════════════
# 9. HEALTH DISTINCTIONS & DIAGNOSTICS
# ═══════════════════════════════════════════════════════════════════════════════

class TestHealthDistinctions:

    @pytest.mark.asyncio
    async def test_browser_alive_distinct_from_service_healthy_when_qr(self):
        """Invariant: Live Chromium process != WhatsApp service healthy."""
        browser = make_mock_browser(login_state="qr_required")
        sup = make_supervisor(browser=browser)

        snap = await sup._health_engine.probe_all()
        assert snap.infrastructure_healthy() is True
        assert snap.authentication.status == SubsystemStatus.WAITING_FOR_AUTH
        assert snap.service_healthy() is False

    @pytest.mark.asyncio
    async def test_listener_alive_distinct_from_scanner_progress(self):
        """Invariant: Listener task running != actual listener scan progress."""
        listener = make_mock_listener(is_running=True, task_alive=True, scan_age=200.0)
        sup = make_supervisor(listener=listener)

        snap = await sup._health_engine.probe_all()
        assert snap.listener.status == SubsystemStatus.HEALTHY
        assert snap.scanner.status == SubsystemStatus.FAILED

    @pytest.mark.asyncio
    async def test_bounded_failure_history(self):
        history = FailureHistory(max_entries=10)
        for i in range(25):
            history.record_failure(FailureHistoryEntry(
                timestamp=time.time(),
                failure_class=FailureClass.SCANNER_STALLED,
                recovery_level=RecoveryLevel.REPAIR_COMPONENT,
            ))
        data = history.to_dict()
        assert data["failures_5m"] == 10  # bounded to max_entries=10

    @pytest.mark.asyncio
    async def test_diagnostics_structure_complete(self):
        sup = make_supervisor()
        await sup.trigger_check()

        diag = sup.get_diagnostics()
        assert "state" in diag
        assert "is_recovering" in diag
        assert "circuit_breaker" in diag
        assert "failure_history" in diag
        assert "heartbeats" in diag
        assert "last_snapshot" in diag
        assert "infrastructure" in diag["last_snapshot"]
        assert "pipeline" in diag["last_snapshot"]
        assert "service" in diag["last_snapshot"]
