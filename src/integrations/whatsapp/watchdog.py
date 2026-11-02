"""
Julius WhatsApp Integration — Watchdog.

24/7 background health monitor and crash recovery for the WhatsApp subsystem.
Monitors browser liveliness, session state, page responsiveness, and triggers
exponential-backoff recovery upon failure.
"""

from __future__ import annotations

import asyncio
import logging
import time
import socket
from typing import Any, Awaitable, Callable, Optional

from .browser import WhatsAppBrowserAdapter
from .health import WhatsAppHealth
from .models import HealthState
from .supervisor import SupervisorConfig, WhatsAppSupervisor

logger = logging.getLogger(__name__)

# Bounded exponential backoff progression (seconds)
BACKOFF_DELAYS = [2, 5, 10, 30, 60, 120, 300]

__all__ = [
    "WhatsAppWatchdog",
    "WhatsAppSupervisor",
    "SupervisorConfig",
    "is_network_online",
    "BACKOFF_DELAYS",
]


def is_network_online(host: str = "web.whatsapp.com", port: int = 443, timeout: float = 3.0) -> bool:
    """Verify outbound internet connectivity before attempting browser re-launch."""
    try:
        socket.setdefaulttimeout(timeout)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((host, port))
        s.close()
        return True
    except Exception:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect(("8.8.8.8", 53))
            s.close()
            return True
        except Exception:
            return False


class WhatsAppWatchdog:
    """
    Continuous 24/7 health monitor and crash recovery for the WhatsApp subsystem.
    
    Monitors:
    - Host network connectivity
    - Chromium process and page state
    - Page responsiveness and loading stalls
    - Session takeover and authentication state
    - Message listener scan liveness
    - Periodic idle memory recycling
    """

    def __init__(
        self,
        browser: WhatsAppBrowserAdapter,
        health: WhatsAppHealth,
        restart_callback: Optional[Callable[[], Awaitable[None]]] = None,
        check_interval_seconds: float = 20.0,
        listener: Optional[Any] = None,
    ) -> None:
        self._browser = browser
        self._health = health
        self._restart_callback = restart_callback
        self._check_interval = check_interval_seconds
        self._listener = listener
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._consecutive_failures = 0
        self._is_recovering = False
        self._loading_since: Optional[float] = None
        self._last_recycle: float = time.time()

    @property
    def is_running(self) -> bool:
        return self._running and self._task is not None and not self._task.done()

    async def start(self) -> None:
        """Start the background watchdog loop."""
        if self.is_running:
            return

        self._running = True
        self._health.set_watchdog_running(True)
        self._task = asyncio.create_task(self._watchdog_loop(), name="whatsapp_watchdog")
        logger.info("WhatsApp watchdog started (check interval: %ss)", self._check_interval)

        # Run an immediate health check on startup to catch cold boot failures
        asyncio.create_task(self._initial_check())

    async def _initial_check(self) -> None:
        """Run first health check immediately instead of waiting for interval."""
        await asyncio.sleep(3.0)  # Small grace period for browser to initialize
        if self._running:
            try:
                await self._check_health()
            except Exception as e:
                logger.debug("Initial health check failed: %s", e)

    async def stop(self) -> None:
        """Stop the watchdog loop cleanly."""
        self._running = False
        self._health.set_watchdog_running(False)
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            self._task = None
        logger.info("WhatsApp watchdog stopped")

    async def trigger_check(self) -> bool:
        """Run an immediate single health check. Returns True if healthy."""
        return await self._check_health()

    async def _watchdog_loop(self) -> None:
        """Periodic health check loop with backoff recovery."""
        while self._running:
            try:
                await asyncio.sleep(self._check_interval)
                if not self._running:
                    break

                is_healthy = await self._check_health()

                if is_healthy:
                    if self._consecutive_failures > 0:
                        logger.info("WhatsApp service recovered after %d failure(s)", self._consecutive_failures)
                    self._consecutive_failures = 0

                    # 24h idle browser hygiene memory check
                    await self._check_scheduled_recycle()
                else:
                    self._consecutive_failures += 1
                    delay = BACKOFF_DELAYS[min(self._consecutive_failures - 1, len(BACKOFF_DELAYS) - 1)]
                    logger.warning(
                        "WhatsApp watchdog detected issue (failure #%d). Attempting recovery in %ds...",
                        self._consecutive_failures,
                        delay,
                    )
                    await self._attempt_recovery(delay)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Unexpected error in WhatsApp watchdog loop: %s", e, exc_info=True)
                self._health.record_error(f"Watchdog loop error: {e}")
                await asyncio.sleep(5.0)

    async def _check_scheduled_recycle(self) -> None:
        """Perform a clean page reload once every 24-48h when idle to free DOM & JS memory."""
        now = time.time()
        if (now - self._last_recycle) < 86400:
            return

        # Ensure system is idle before recycling
        if self._listener:
            active = getattr(self._listener, "_active_processing", set())
            if active:
                return

        logger.info("Watchdog: executing scheduled 24h browser hygiene memory recycle...")
        try:
            if self._browser.page and not self._browser.page.is_closed():
                await self._browser.page.reload(wait_until="domcontentloaded", timeout=20000)
                self._last_recycle = now
                logger.info("Watchdog: browser memory hygiene recycle completed successfully.")
        except Exception as e:
            logger.warning("Watchdog: scheduled browser recycle failed: %s", e)

    async def _check_health(self) -> bool:
        """Verify browser alive, page responsive, and session connected."""
        if self._is_recovering:
            return False

        try:
            # 1. Check browser page
            page = self._browser.page
            if page is None:
                self._health.update_browser(alive=False, ready=False)
                return False

            # Check if page is closed
            try:
                if page.is_closed():
                    self._health.update_browser(alive=False, ready=False)
                    self._health.set_state(HealthState.BROWSER_ERROR)
                    return False
            except Exception:
                self._health.update_browser(alive=False, ready=False)
                return False

            # 2. Check responsiveness with lightweight eval
            try:
                await asyncio.wait_for(page.evaluate("() => document.readyState"), timeout=5.0)
                self._health.update_browser(alive=True, ready=True)
            except Exception as e:
                logger.warning("WhatsApp page unresponsive: %s", e)
                self._health.update_browser(alive=False, ready=False)
                return False

            # 3. Check login status & loading hangs
            status = await self._browser.detect_login_state()
            if status == "connected":
                self._loading_since = None
                self._health.set_authenticated(True)
            elif status == "qr_required":
                self._loading_since = None
                self._health.set_authenticated(False)
                if self._health.state == HealthState.CONNECTED:
                    self._health.set_state(HealthState.SESSION_EXPIRED)
                else:
                    self._health.set_state(HealthState.WAITING_FOR_QR)
                return True
            elif status == "loading":
                now = time.time()
                if self._loading_since is None:
                    self._loading_since = now
                elif (now - self._loading_since) > 90.0:
                    logger.warning(
                        "WhatsApp page stuck in 'loading' state for %.1fs. Triggering reload.",
                        now - self._loading_since,
                    )
                    self._health.record_error(f"Page loading stall: {now - self._loading_since:.0f}s")
                    if self._browser.page and not self._browser.page.is_closed():
                        try:
                            await self._browser.page.reload(wait_until="domcontentloaded", timeout=15000)
                            self._loading_since = time.time()
                            return True
                        except Exception as e:
                            logger.warning("Watchdog reload after loading stall failed: %s", e)
                    return False
                return True
            else:
                self._loading_since = None
                self._health.set_state(HealthState.ERROR)
                return False

            # 4. Check listener liveness
            if self._listener is not None:
                liveness = self._listener.get_liveness() if hasattr(self._listener, "get_liveness") else {}
                is_running = getattr(self._listener, "is_running", False)
                task_alive = liveness.get("task_alive", is_running)
                self._health.set_listener_running(is_running and task_alive)

                if is_running and not task_alive:
                    logger.warning("WhatsApp watchdog: listener flag is True but task is dead!")
                    self._health.record_error("Listener task died unexpectedly")
                    return False

                # If connected and scanning, check if scan is stalled (>90s since last successful scan)
                age = getattr(self._listener, "liveness_age_seconds", 0.0)
                last_scan = getattr(self._listener, "last_successful_scan", 0.0)
                if is_running and last_scan > 0 and age > 90.0:
                    logger.warning(
                        "WhatsApp watchdog: listener scan stalled (%.1fs since last scan)",
                        age,
                    )
                    self._health.record_error(f"Listener stalled: {age:.0f}s since last scan")
                    return False

                consec_errors = getattr(self._listener, "_consecutive_scan_errors", 0)
                if consec_errors >= 10:
                    logger.warning("WhatsApp watchdog: listener accumulated %d consecutive scan errors", consec_errors)
                    self._health.record_error(f"Listener excessive scan errors: {consec_errors}")
                    return False

            return True

        except Exception as e:
            logger.warning("WhatsApp health check exception: %s", e)
            self._health.record_error(f"Health check failed: {e}")
            return False

    async def _attempt_recovery(self, delay: int) -> None:
        """Attempt to restart or recover the WhatsApp browser session."""
        if self._is_recovering or not self._running:
            return

        self._is_recovering = True
        self._health.record_restart()
        try:
            await asyncio.sleep(delay)
            if not self._running:
                return

            # Check network online status
            if not is_network_online():
                logger.warning("Host network appears offline. Waiting for network connectivity before recovery...")
                self._health.record_error("Network offline; awaiting connectivity...")
                # Poll network every 5s up to 60s
                for _ in range(12):
                    await asyncio.sleep(5.0)
                    if not self._running:
                        return
                    if is_network_online():
                        logger.info("Host network connectivity restored. Resuming recovery...")
                        break
                else:
                    logger.warning("Host network still offline; continuing with recovery attempt anyway.")

            # If first failure and page still exists, attempt a soft reload first
            if self._consecutive_failures == 1 and self._browser.page and not self._browser.page.is_closed():
                try:
                    logger.info("Attempting fast soft reload recovery...")
                    await self._browser.page.reload(wait_until="domcontentloaded", timeout=15000)
                    await asyncio.sleep(2.0)
                    if await self._check_health():
                        logger.info("Soft reload recovery succeeded!")
                        return
                except Exception as e:
                    logger.debug("Fast soft reload failed: %s; proceeding to full restart", e)

            logger.info("Executing WhatsApp recovery restart...")
            if self._restart_callback:
                try:
                    await asyncio.wait_for(self._restart_callback(), timeout=60.0)
                    logger.info("WhatsApp recovery restart completed successfully")
                except asyncio.TimeoutError:
                    logger.error("WhatsApp recovery restart timed out after 60s")
                    self._health.record_error("Recovery restart timed out")
            else:
                logger.warning("No restart callback configured for WhatsApp watchdog")

            # After full restart, also restart listener if it died
            if self._listener:
                is_running = getattr(self._listener, "is_running", False)
                task_alive = False
                if hasattr(self._listener, "get_liveness"):
                    liveness = self._listener.get_liveness()
                    task_alive = liveness.get("task_alive", False)
                elif is_running:
                    task_alive = True

                if not task_alive and hasattr(self._listener, "start"):
                    try:
                        logger.info("Restarting dead listener task after recovery...")
                        await self._listener.start()
                    except Exception as le:
                        logger.error("Failed to restart listener after recovery: %s", le)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("WhatsApp recovery restart failed: %s", e, exc_info=True)
            self._health.record_error(f"Recovery failed: {e}")
        finally:
            # CRITICAL: Always reset recovery flag to prevent permanent lockout
            self._is_recovering = False
