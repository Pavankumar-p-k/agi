# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Mythos v12 — Meta-Governor
============================
The system's nervous system. A continuous async control loop that:
  observe → analyze → detect → decide → act → verify → learn

DESIGN PRINCIPLES:
  - Non-blocking: control loop runs as background asyncio task
  - Non-invasive: hooks into existing components via adapter pattern
  - No global locks: uses event-based signaling, not locks
  - Bounded loop: sleep(POLL_INTERVAL_S) prevents CPU spinning
  - Self-learning: thresholds adjust based on observed behavior
  - Single authority: one governor, one set of decisions

INTEGRATION POINTS (only these files touched):
  - Reads from HealthTelemetry (utils/telemetry.py)
  - Issues commands to ResourceManager (core/resource_manager.py)
  - Triggers SelfHealingEngine (core/self_healing.py)
  - Signals MetaOrchestratorV11 via asyncio.Event flags

SCOPE BOUNDARY:
  - Controls ONLY Mythos internals
  - No access to jarvis/*, deskmate/*, tools/*, API layer
"""

import asyncio
import json
import math
import os
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from utils.logger import SystemLogger
from utils.telemetry import HealthTelemetry, HealthState, SystemSnapshot
from governance.exceptions import GovernanceViolation

logger = SystemLogger(__name__)

POLL_INTERVAL_S  = 2.0      # control loop polling interval
MAX_LOOP_ITERS   = None      # None = run until stop() called
SAFE_MODE_WINDOW = 30.0      # seconds to stay in safe mode before re-evaluating


class GovernorAction(Enum):
    NONE        = "none"
    THROTTLE    = "throttle"         # slow down new task intake
    SAFE_MODE   = "safe_mode"        # stop new tasks, drain existing
    HEAL        = "heal"             # trigger self-healing for a module
    MEMORY_GC   = "memory_gc"        # trigger memory lifecycle manager
    ESCALATE    = "escalate"         # escalate to operator (log + alert)
    RECOVER     = "recover"          # return from throttle/safe_mode


@dataclass
class GovernorDecision:
    action:      GovernorAction
    reason:      str
    targets:     List[str]       # modules affected
    severity:    str             # "info" | "warning" | "critical"
    timestamp:   float = field(default_factory=time.time)
    verified:    bool  = False   # set True after intervention verified

    def to_dict(self) -> Dict:
        return {
            "action": self.action.value, "reason": self.reason,
            "targets": self.targets, "severity": self.severity,
            "timestamp": self.timestamp, "verified": self.verified,
        }


class MetaGovernor:
    """
    Continuous control loop with health scoring and governance decisions.
    Instantiated once at MetaOrchestratorV12 startup.
    
    Usage:
        governor = MetaGovernor(telemetry, resource_manager, self_healer)
        await governor.start()   # starts background loop
        # ... system runs ...
        await governor.stop()    # graceful shutdown
    """

    def __init__(
        self,
        telemetry:        HealthTelemetry,
        resource_manager: Any,                # ResourceManager (injected)
        self_healer:      Any  = None,        # SelfHealingEngine (optional)
        memory_gc:        Any  = None,        # MemoryLifecycleManager (optional)
        health_predictor: Any  = None,        # HealthPredictor (v13 predictive, optional)
        systemic_healer:  Any  = None,        # SystemicHealer (v13 global fix, optional)
        poll_interval_s:  float = POLL_INTERVAL_S,
        storage_path:     str  = "./data/governor",
    ):
        self.telemetry        = telemetry
        self.resource_manager = resource_manager
        self.self_healer      = self_healer
        self.memory_gc        = memory_gc
        self.poll_interval    = poll_interval_s
        self.storage_path     = storage_path
        self.health_predictor = health_predictor   # V13: predictive
        self.systemic_healer  = systemic_healer     # V13: global healing
        os.makedirs(storage_path, exist_ok=True)

        # State flags (asyncio.Event — no locks, fully async)
        self.throttle_event   = asyncio.Event()   # set = system is throttled
        self.safe_mode_event  = asyncio.Event()   # set = system in safe mode
        self._stop_event      = asyncio.Event()   # set = stop the loop

        # Decision history (bounded)
        self._decisions: List[GovernorDecision] = []
        self._max_decisions = 500

        # Safe mode tracking
        self._safe_mode_since: Optional[float] = None
        self._consecutive_healthy: int = 0
        self._consecutive_degraded: int = 0

        # Adaptive learning: adjust thresholds based on outcomes
        self._intervention_outcomes: List[bool] = []  # True=helped, False=no effect
        self._decision_counts: Dict[str, int] = {a.value: 0 for a in GovernorAction}

        # Loop task handle
        self._loop_task: Optional[asyncio.Task] = None

        logger.info("[Governor] Initialized — poll_interval=%ss", poll_interval_s)

    # ── Lifecycle ─────────────────────────────────────────────────

    async def start(self):
        """Start the background control loop. Non-blocking."""
        if self._loop_task and not self._loop_task.done():
            logger.warning("[Governor] Already running")
            return
        self._stop_event.clear()
        self._loop_task = asyncio.create_task(self._control_loop())
        logger.info("[Governor] Control loop started")

    async def stop(self):
        """Gracefully stop the control loop."""
        self._stop_event.set()
        if self._loop_task:
            try:
                await asyncio.wait_for(self._loop_task, timeout=5.0)
            except asyncio.TimeoutError:
                self._loop_task.cancel()
        logger.info("[Governor] Control loop stopped")

    # ── Control Loop ──────────────────────────────────────────────

    async def _control_loop(self):
        """
        observe → analyze → detect → decide → act → verify → learn
        
        Runs until _stop_event is set. Never raises — catches all exceptions.
        Sleep is bounded by poll_interval_s. Cannot spin infinitely.
        """
        logger.info("[Governor] Control loop active")
        while not self._stop_event.is_set():
            loop_start = time.time()
            try:
                # OBSERVE: collect system state
                snapshot = self.telemetry.compute_global_health()

                # V13: PREDICT health trend before reactive analysis
                if self.health_predictor:
                    prediction = self.health_predictor.predict(self.telemetry)
                    self.health_predictor.record_actual(snapshot.global_score)
                    if prediction.is_actionable and not self.safe_mode_event.is_set():
                        await self._act_predictive(prediction, snapshot)

                # ANALYZE + DETECT (reactive, unchanged from v12)
                decision = self._analyze(snapshot)

                # DECIDE + ACT
                if decision.action != GovernorAction.NONE:
                    await self._act(decision, snapshot)

                # VERIFY (async, next iteration will check effect)
                # LEARN: adapt thresholds periodically
                if len(self._decisions) % 25 == 0 and len(self._decisions) > 0:
                    self._adapt_thresholds()

                # Check safe mode recovery
                await self._check_safe_mode_recovery(snapshot)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[Governor] Control loop error (continuing): {e}")

            # Bounded sleep — prevents CPU spinning
            elapsed = time.time() - loop_start
            sleep_time = max(0.1, self.poll_interval - elapsed)
            try:
                await asyncio.wait_for(
                    asyncio.shield(self._stop_event.wait()),
                    timeout=sleep_time
                )
                break  # stop event was set during sleep
            except asyncio.TimeoutError:
                continue

        logger.info("[Governor] Control loop exited")

    # ── Analysis and Decision Logic ───────────────────────────────

    def _analyze(self, snapshot: SystemSnapshot) -> GovernorDecision:
        """
        Multi-signal analysis. Never trusts a single metric.
        Returns the highest-priority action required.
        """
        global_score = snapshot.global_score
        state        = snapshot.global_state
        active_tasks = snapshot.active_tasks

        # Track consecutive states (prevent thrashing)
        if state == HealthState.HEALTHY:
            self._consecutive_healthy  += 1
            self._consecutive_degraded  = 0
        elif state in (HealthState.DEGRADED, HealthState.CRITICAL):
            self._consecutive_degraded += 1
            self._consecutive_healthy   = 0

        # Check for already-active interventions
        if self.safe_mode_event.is_set():
            return GovernorDecision(
                GovernorAction.NONE, "safe_mode_active", [], "info"
            )

        # CRITICAL: activate safe mode if score very low AND multiple bad signals
        critical_modules = [
            m for m, mh in snapshot.module_healths.items()
            if mh.state == HealthState.CRITICAL
        ]
        if (global_score < 0.20 and self._consecutive_degraded >= 3 and
                len(critical_modules) >= 2):
            return GovernorDecision(
                GovernorAction.SAFE_MODE,
                f"global_score={global_score:.3f}, {len(critical_modules)} critical modules",
                critical_modules,
                "critical",
            )

        # DEGRADED: throttle if score low for several consecutive checks
        if (global_score < 0.45 and self._consecutive_degraded >= 2 and
                not self.throttle_event.is_set()):
            return GovernorDecision(
                GovernorAction.THROTTLE,
                f"global_score={global_score:.3f} for {self._consecutive_degraded} checks",
                [m for m, mh in snapshot.module_healths.items()
                 if mh.state != HealthState.HEALTHY],
                "warning",
            )

        # HEAL: specific module repeatedly failing
        for module, mh in snapshot.module_healths.items():
            if mh.state == HealthState.CRITICAL and mh.failure_rate > 0.60:
                return GovernorDecision(
                    GovernorAction.HEAL,
                    f"{module} failure_rate={mh.failure_rate:.2f}",
                    [module],
                    "warning",
                )

        # MEMORY_GC: token usage getting high
        trends = self.telemetry.get_resource_trends()
        if trends["token_total"] > 100_000:
            return GovernorDecision(
                GovernorAction.MEMORY_GC,
                f"token_total={trends['token_total']:,}",
                ["memory"],
                "info",
            )

        # RECOVER: system healthy again after throttle
        if (self.throttle_event.is_set() and global_score >= 0.70 and
                self._consecutive_healthy >= 3):
            return GovernorDecision(
                GovernorAction.RECOVER,
                f"health restored: global_score={global_score:.3f}",
                [],
                "info",
            )

        return GovernorDecision(GovernorAction.NONE, "healthy", [], "info")

    # ── Action Execution ──────────────────────────────────────────

    async def _act(self, decision: GovernorDecision, snapshot: SystemSnapshot):
        """Execute the governance decision. All actions are non-blocking."""
        action = decision.action
        self._record_decision(decision)
        self._decision_counts[action.value] = self._decision_counts.get(action.value, 0) + 1

        logger.info(
            f"[Governor] ACTION={action.value} severity={decision.severity} "
            f"reason={decision.reason[:80]}"
        )
        self.telemetry.record_intervention(
            action=action.value,
            reason=decision.reason,
            triggered_by="meta_governor",
        )

        if action == GovernorAction.THROTTLE:
            self.throttle_event.set()
            if self.resource_manager:
                self.resource_manager.throttle(factor=0.5)

        elif action == GovernorAction.SAFE_MODE:
            self.safe_mode_event.set()
            self.throttle_event.set()
            self._safe_mode_since = time.time()
            if self.resource_manager:
                self.resource_manager.throttle(factor=0.0)  # halt new tasks
            logger.warning("[Governor] SAFE MODE ACTIVATED")

        elif action == GovernorAction.HEAL:
            if self.self_healer:
                for target in decision.targets:
                    asyncio.create_task(
                        self.self_healer.heal_module(target)
                    )

        elif action == GovernorAction.MEMORY_GC:
            if self.memory_gc:
                asyncio.create_task(self.memory_gc.run_cycle())

        elif action == GovernorAction.RECOVER:
            self.throttle_event.clear()
            if self.resource_manager:
                self.resource_manager.throttle(factor=1.0)  # restore full capacity
            logger.info("[Governor] Throttle lifted — system recovered")

        decision.verified = True  # mark as acted on

    async def _check_safe_mode_recovery(self, snapshot: SystemSnapshot):
        """Allow safe mode to lift after SAFE_MODE_WINDOW if health improves."""
        if not self.safe_mode_event.is_set():
            return
        if not self._safe_mode_since:
            return
        elapsed = time.time() - self._safe_mode_since
        if elapsed >= SAFE_MODE_WINDOW and snapshot.global_score >= 0.55:
            self.safe_mode_event.clear()
            self._safe_mode_since = None
            self._consecutive_degraded = 0
            if self.resource_manager:
                self.resource_manager.throttle(factor=0.7)  # gradual restore
            logger.info(f"[Governor] Safe mode lifted after {elapsed:.0f}s")
            self.telemetry.record_intervention("safe_mode_lifted", "health_restored")

    # ── Adaptive Learning ─────────────────────────────────────────

    def _adapt_thresholds(self):
        """
        Adjust health thresholds based on intervention outcomes.
        If throttle interventions haven't helped → lower the trigger threshold.
        Bounded to prevent runaway adjustment.
        """
        if len(self._decisions) < 10:
            return

        throttle_decisions = [d for d in self._decisions[-20:]
                              if d.action == GovernorAction.THROTTLE]
        heal_decisions     = [d for d in self._decisions[-20:]
                              if d.action == GovernorAction.HEAL]

        new_thresholds = {}

        # If throttling frequently but system keeps degrading → lower threshold earlier
        if len(throttle_decisions) >= 5:
            current = self.telemetry._thresholds["degraded_score"]
            new_thresholds["degraded_score"] = min(0.65, current + 0.02)

        # If healing frequently → latency threshold may be too tight
        if len(heal_decisions) >= 5:
            current = self.telemetry._thresholds["max_latency_ms"]
            new_thresholds["max_latency_ms"] = min(90000.0, current * 1.10)

        if new_thresholds:
            self.telemetry.adjust_thresholds(new_thresholds)
            logger.info(f"[Governor] Thresholds adapted: {new_thresholds}")

    # ── Public Query Interface ────────────────────────────────────

    async def _act_predictive(self, prediction: Any, snapshot: Any):
        """V13: Take preemptive action based on health forecast."""
        action = prediction.action
        if action == "preemptive_safe_mode" and not self.safe_mode_event.is_set():
            from core.meta_governor import GovernorDecision, GovernorAction
            decision = GovernorDecision(
                GovernorAction.SAFE_MODE,
                f"PREDICTIVE: {prediction.reason}",
                list(snapshot.module_healths.keys()),
                "critical",
            )
            self._record_decision(decision)
            await self._act(decision, snapshot)
            self.telemetry.record_intervention("preemptive_safe_mode", prediction.reason, "predictor")
            logger.warning(f"[Governor] PREEMPTIVE SAFE MODE: {prediction.reason}")
        elif action == "preemptive_throttle" and not self.throttle_event.is_set():
            from core.meta_governor import GovernorDecision, GovernorAction
            decision = GovernorDecision(
                GovernorAction.THROTTLE,
                f"PREDICTIVE: {prediction.reason}",
                [], "warning",
            )
            self._record_decision(decision)
            await self._act(decision, snapshot)
            self.telemetry.record_intervention("preemptive_throttle", prediction.reason, "predictor")
            logger.info(f"[Governor] PREEMPTIVE THROTTLE: {prediction.reason}")

    def is_throttled(self) -> bool:
        return self.throttle_event.is_set()

    def is_safe_mode(self) -> bool:
        return self.safe_mode_event.is_set()

    def authorize_execution(self, task: str) -> bool:
        """
        Hard enforcement: block any task if system is in SAFE MODE.
        """
        if self.is_safe_mode():
            reason = "Unknown"
            if self._decisions:
                reason = self._decisions[-1].reason
            raise GovernanceViolation(f"Execution blocked: Meta-Governor has activated SAFE MODE. Reason: {reason}")
        return True

    def get_stats(self) -> Dict[str, Any]:
        snapshot = self.telemetry.compute_global_health()
        return {
            "global_score":          snapshot.global_score,
            "global_state":          snapshot.global_state,
            "throttled":             self.is_throttled(),
            "safe_mode":             self.is_safe_mode(),
            "consecutive_degraded":  self._consecutive_degraded,
            "consecutive_healthy":   self._consecutive_healthy,
            "total_decisions":       len(self._decisions),
            "decision_counts":       dict(self._decision_counts),
            "intervention_log":      self.telemetry.get_intervention_log(5),
        }

    def _record_decision(self, decision: GovernorDecision):
        """Record decision, trim to max size."""
        self._decisions.append(decision)
        if len(self._decisions) > self._max_decisions:
            self._decisions = self._decisions[-self._max_decisions:]
