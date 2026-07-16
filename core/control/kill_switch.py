"""Global Agent Kill Switch — emergency stop for runaway agent loops.

Provides:
- SIGTERM/SIGINT handler for graceful shutdown
- Watchdog timer for max execution time
- Programmatic kill switch API
"""
from __future__ import annotations

import asyncio
import logging
import signal
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger("kill_switch")


@dataclass
class KillSwitchState:
    """Current state of the kill switch."""
    triggered: bool = False
    trigger_reason: str = ""
    triggered_at: float = 0.0
    active_agents: set[str] = field(default_factory=set)
    callbacks: list[Callable[[], None]] = field(default_factory=list)


class KillSwitch:
    """Global emergency stop for all agent execution.

    Usage:
        # In main/startup
        kill_switch = KillSwitch(max_runtime_seconds=3600)
        kill_switch.install_signal_handlers()

        # In agent loop
        async def agent_loop():
            while not kill_switch.is_triggered:
                await do_work()
                kill_switch.check()  # Raises if triggered

        # Emergency stop from anywhere
        kill_switch.trigger("Manual emergency stop")
    """

    def __init__(
        self,
        max_runtime_seconds: Optional[float] = None,
        watchdog_interval: float = 1.0,
    ):
        self._state = KillSwitchState()
        self._lock = threading.RLock()
        self._watchdog_task: Optional[asyncio.Task] = None
        self._max_runtime = max_runtime_seconds
        self._start_time = time.monotonic()
        self._watchdog_interval = watchdog_interval
        self._signal_installed = False

    # ── Public API ──────────────────────────────────────────────────────

    @property
    def is_triggered(self) -> bool:
        with self._lock:
            return self._state.triggered

    @property
    def trigger_reason(self) -> str:
        with self._lock:
            return self._state.trigger_reason

    def trigger(self, reason: str = "Manual trigger") -> None:
        """Trigger the kill switch immediately."""
        with self._lock:
            if not self._state.triggered:
                self._state.triggered = True
                self._state.trigger_reason = reason
                self._state.triggered_at = time.monotonic()
                logger.critical("KILL SWITCH TRIGGERED: %s", reason)
                for cb in self._state.callbacks:
                    try:
                        cb()
                    except Exception as e:
                        logger.warning("Kill switch callback failed: %s", e)

    def register_agent(self, agent_id: str) -> None:
        """Register an active agent for tracking."""
        with self._lock:
            self._state.active_agents.add(agent_id)

    def unregister_agent(self, agent_id: str) -> None:
        """Unregister an agent."""
        with self._lock:
            self._state.active_agents.discard(agent_id)

    def check(self) -> None:
        """Check if triggered, raise if so. Call in agent loops."""
        if self.is_triggered:
            raise KillSwitchException(self.trigger_reason)

    def on_trigger(self, callback: Callable[[], None]) -> None:
        """Register a callback to run when triggered."""
        with self._lock:
            self._state.callbacks.append(callback)

    def get_status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "triggered": self._state.triggered,
                "reason": self._state.trigger_reason,
                "triggered_at": self._state.triggered_at,
                "active_agents": list(self._state.active_agents),
                "uptime_seconds": time.monotonic() - self._start_time,
            }

    # ── Signal Handling ────────────────────────────────────────────────

    def install_signal_handlers(self) -> None:
        """Install SIGTERM/SIGINT handlers."""
        if self._signal_installed:
            return

        def handler(signum, frame):
            sig_name = signal.Signals(signum).name
            logger.warning("Received %s, triggering kill switch", sig_name)
            self.trigger(f"Signal {sig_name} received")

        signal.signal(signal.SIGTERM, handler)
        signal.signal(signal.SIGINT, handler)
        self._signal_installed = True
        logger.info("Kill switch signal handlers installed")

    # ── Watchdog ──────────────────────────────────────────────────────

    async def start_watchdog(self) -> None:
        """Start the watchdog timer task."""
        if self._watchdog_task is not None:
            return

        async def watchdog():
            while not self.is_triggered:
                await asyncio.sleep(self._watchdog_interval)
                # Check max runtime
                if self._max_runtime is not None:
                    elapsed = time.monotonic() - self._start_time
                    if elapsed >= self._max_runtime:
                        self.trigger(f"Max runtime ({self._max_runtime}s) exceeded")
                        break
                # Check for stuck agents (no progress)
                if self._state.active_agents:
                    logger.debug("Watchdog: %d active agents", len(self._state.active_agents))

        self._watchdog_task = asyncio.create_task(watchdog())
        logger.info("Kill switch watchdog started")

    async def stop_watchdog(self) -> None:
        """Stop the watchdog task."""
        if self._watchdog_task:
            self._watchdog_task.cancel()
            try:
                await self._watchdog_task
            except asyncio.CancelledError:
                pass
            self._watchdog_task = None


class KillSwitchException(Exception):
    """Raised when kill switch is triggered."""
    pass


# Global singleton
kill_switch = KillSwitch()


def get_kill_switch() -> KillSwitch:
    return kill_switch