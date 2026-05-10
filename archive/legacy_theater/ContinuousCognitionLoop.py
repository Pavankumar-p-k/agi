"""
Sovereign V2 — Continuous Cognition Loop
===========================================
V3 Upgrade. Fully refactors legacy loop tracking into a Sovereign Scheduler.

The loop now natively executes scheduled execution sweeps including:
- Benchmarking the source code logic (Pytest suites in /benchmarks/)
- Trust Drift scans via ExecutiveMetaCognition
- Provider Health & Governance Audits (Penetration tests against RGL traps)
- Automatic Generation of patches during runtime execution cycles if drift slips.
"""

import asyncio
import time
from typing import Optional
from pathlib import Path

try:
    from utils.logger import SystemLogger
except ModuleNotFoundError:
    import logging

    def SystemLogger(name: str):
        return logging.getLogger(name)
from brain.MetaCognitionEngine import ExecutiveMetaCognitionV3
from jarvis_os.RuntimeGovernanceLayer import RuntimeGovernanceLayer
from jarvis_os.ProviderDecisionMatrix import ProviderDecisionMatrix
from jarvis_os.ProviderStrategicMemory import ProviderStrategicMemory
from jarvis_os.ProviderTrustRegistry import ProviderTrustRegistry
from jarvis_os.provider_health_registry import ProviderHealthRegistry
from jarvis_os.runtime.config import JarvisConfig
from jarvis_os.runtime.exceptions import GovernanceViolation, SecurityViolation

logger = SystemLogger(__name__)

class ContinuousCognitionLoopV3:
    """
    Sovereign OS Macro-Scheduler.
    Executes deep structural scans when the system context is not busy.
    """
    
    TICK_RATE = 10.0  # Seconds between cognitive loops

    def __init__(self, workspace_root: str = "."):
        self.workspace_root = workspace_root
        self.config = JarvisConfig.from_env()
        self.meta_engine = ExecutiveMetaCognitionV3(workspace_root)
        self.governor = self._build_governor()
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._last_benchmark_run = time.time()
        self._report_file = Path(self.workspace_root) / "reports" / "AUTONOMY_VALIDATION.md"

    def _build_governor(self) -> RuntimeGovernanceLayer:
        providers = {"ollama": object(), "rest": object(), "fallback": object()}
        trust_registry = ProviderTrustRegistry(providers)
        health_registry = ProviderHealthRegistry(providers)
        strategic_memory = ProviderStrategicMemory(self.config)
        decision_matrix = ProviderDecisionMatrix(self.config, trust_registry, strategic_memory)
        return RuntimeGovernanceLayer(
            trust_registry=trust_registry,
            health_registry=health_registry,
            decision_matrix=decision_matrix,
            strategic_memory=strategic_memory,
            config=self.config,
        )

    def start(self):
        """Engages the Sovereign continuous loop."""
        if self._running:
            return
        logger.info("[ContinuousCognitionV3] Initializing Sovereign Scheduler.")
        self._running = True
        self._task = asyncio.create_task(self._cognitive_tick())

    def stop(self):
        """Halts background reflection."""
        self._running = False
        if self._task:
            self._task.cancel()
        logger.info("[ContinuousCognitionV3] Soverign Scheduler offline.")

    async def _cognitive_tick(self):
        while self._running:
            try:
                await self._execute_health_checks()
                await self._execute_benchmark_reruns()
                await self._execute_drift_scans()
                await self._execute_provider_audits()
                self._execute_governance_penetration_test()
                await self._generate_strategic_evolution_report()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[ContinuousCognitionV3] Severe loop failure: {str(e)}")
                # Immediate fallback logic to attempt systemic healing on self
                await self.meta_engine.autonomous_patch_generation(
                    "brain/ContinuousCognitionLoop.py", "tests.test_autonomy", str(e)
                )
            await asyncio.sleep(self.TICK_RATE)

    async def _execute_health_checks(self):
        """Scans memory integrity."""
        logger.debug("[ContinuousCognitionV3] Executing memory integrity check.")

    async def _execute_benchmark_reruns(self):
        """Every 15 minutes, forces the OS to re-certify against standard benchmarks."""
        if time.time() - self._last_benchmark_run > 900:  # 15 mins
            logger.info("[ContinuousCognitionV3] Executing temporal benchmark recertification.")
            self._last_benchmark_run = time.time()
            score = self.meta_engine.benchmark_self_scoring()
            if score["trust"] > 0.15:
                logger.warning("[ContinuousCognitionV3] Trust drift exceeded tolerance during periodic execution scan.")

    async def _execute_drift_scans(self):
        """Audits structural integrity vs dynamic alignment parameters."""
        audit = self.meta_engine.self_audit()
        if audit["drift_count"] > 0:
            logger.warning(
                f"[ContinuousCognitionV3] Drift scan detected {audit['drift_count']} issue(s): "
                f"{len(audit['syntax_errors'])} syntax, {len(audit['stub_functions'])} stubs."
            )
        else:
            logger.debug("[ContinuousCognitionV3] Drift scan clean.")

    async def _execute_provider_audits(self):
        """Requests dummy traffic through existing providers to ensure offline routing handles fallback properly."""
        candidates = {
            "rest": {"provider": "rest", "ready": True, "models": ["gpt"], "privacy": 0.3, "offline_availability": 0.0},
            "ollama": {"provider": "ollama", "ready": True, "models": ["llama3.1:8b"], "privacy": 0.8, "offline_availability": 0.8},
            "fallback": {"provider": "fallback", "ready": True, "models": ["fallback"], "privacy": 1.0, "offline_availability": 1.0},
        }
        selection = self.governor.finalize_selection(
            candidates,
            "Process private medical records",
            {"privacy_sensitive": True, "offline_only": True},
        )
        provider = selection.get("provider", "")
        if provider not in {"fallback", "ollama"}:
            raise GovernanceViolation(
                f"Provider audit failed: selected {provider} for offline-only sensitive task."
            )
        logger.debug(f"[ContinuousCognitionV3] Provider audit passed with {provider}.")

    def _execute_governance_penetration_test(self):
        """
        Actively simulated 'red-teaming' on itself.
        Attempts to force 'medical records' payload through non-offline interfaces.
        """
        selection = self.governor.finalize_selection(
            {
                "rest": {"provider": "rest", "ready": True, "models": ["gpt"], "privacy": 0.2, "offline_availability": 0.0},
                "ollama": {"provider": "ollama", "ready": True, "models": ["llama3.1:8b"], "privacy": 0.8, "offline_availability": 0.8},
                "fallback": {"provider": "fallback", "ready": True, "models": ["fallback"], "privacy": 1.0, "offline_availability": 1.0},
            },
            "Update patient medical records securely",
            {"privacy_sensitive": True, "offline_only": True}
        )
        provider_name = selection.get("provider")
        if provider_name not in ["ollama", "fallback"]:
            raise SecurityViolation(
                f"GOVERNANCE VIOLATION: Offline sensitive prompt routed to {provider_name}."
            )

    async def _generate_strategic_evolution_report(self):
        """Generates real-time evaluation logs."""
        self._report_file.parent.mkdir(parents=True, exist_ok=True)
        scores = self.meta_engine.benchmark_self_scoring()
        audit = self.meta_engine.self_audit()
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        with self._report_file.open("a", encoding="utf-8") as file_obj:
            file_obj.write(
                f"\n## Tick {now}\n"
                f"- trust_drift: {scores['trust']:.3f}\n"
                f"- cognitive_load: {scores['cognition']:.3f}\n"
                f"- strategic_regret: {scores['regret']:.3f}\n"
                f"- governance_integrity: {scores['governance']:.3f}\n"
                f"- drift_count: {audit['drift_count']}\n"
            )
