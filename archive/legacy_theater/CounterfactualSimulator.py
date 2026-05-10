"""
V6 Failure Simulation Engine + Confidence Calibration System
=============================================================
Addresses:
  - V5 Weakness #2 (False-positive verification)
  - V5 Weakness #3 (Confidence miscalibration)

FAILURE SIMULATION:
Before final output, actively try to BREAK the answer.
Simulates adversarial inputs, edge cases, and failure scenarios.
An answer that survives attack is much more likely to be correct.

CONFIDENCE CALIBRATION:
Tracks predicted confidence vs actual correctness.
Computes Expected Calibration Error (ECE) — the gold standard metric.
Dynamically adjusts confidence scores to match empirical accuracy.
"""

import asyncio
import json
import math
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from utils.logger import SystemLogger

logger = SystemLogger(__name__)


# ══════════════════════════════════════════════════════════════════
# PART 1: FAILURE SIMULATION ENGINE
# ══════════════════════════════════════════════════════════════════

@dataclass
class FailureScenario:
    scenario_type: str    # "edge_case" | "adversarial" | "boundary" | "stress"
    description:   str    # what failure we're simulating
    survived:      bool   # did the answer survive this scenario?
    evidence:      str    # specific evidence of survival or failure
    severity:      str    # "minor" | "moderate" | "critical"


@dataclass
class SimulationReport:
    total_scenarios: int
    survived: int
    failed: int
    survival_rate: float
    critical_failures: List[FailureScenario]
    all_scenarios: List[FailureScenario]
    robustness_score: float    # 0-1
    should_output: bool
    revision_needed: List[str]


EDGE_CASE_PROMPT = """Try to BREAK this answer by testing it against edge cases.

TASK: {task}
ANSWER: {answer}

Find 3 edge cases where this answer would be WRONG or INCOMPLETE:
- Boundary conditions (extreme values, empty inputs, nulls)
- Unusual inputs the solution doesn't handle
- Conditions where the solution fails silently

For each edge case found, explain WHY the answer fails.

Respond in JSON:
{{
  "edge_cases": [
    {{
      "scenario": "description of edge case",
      "why_fails": "specific reason the answer fails",
      "severity": "minor" | "moderate" | "critical"
    }}
  ],
  "answer_is_robust": true/false,
  "critical_weaknesses": ["..."]
}}"""

ADVERSARIAL_PROMPT = """You are an adversarial critic. Your ONLY goal is to find flaws.

TASK: {task}
ANSWER: {answer}

Attack this answer aggressively:
1. Find a scenario where following this answer leads to a WRONG result
2. Find a claim in the answer that is FACTUALLY QUESTIONABLE
3. Find a step in the reasoning that is LOGICALLY INVALID
4. Find an assumption the answer makes that could be WRONG

Be specific. "This could be wrong" is not acceptable — explain EXACTLY why.

Respond in JSON:
{{
  "scenario_attack": {{"description": "...", "why_wrong": "..."}},
  "factual_attack": {{"claim": "...", "why_questionable": "..."}},
  "logic_attack": {{"step": "...", "why_invalid": "..."}},
  "assumption_attack": {{"assumption": "...", "why_wrong": "..."}},
  "survived_all_attacks": true/false,
  "most_critical_weakness": "..."
}}"""


class FailureSimulationEngine:
    """
    Actively tries to break the answer before outputting it.
    An answer that survives adversarial attack has higher truth probability.

    V5 WEAKNESS FIXED: V5 verifies structure, not robustness.
    This engine simulates FAILURE MODES before accepting any answer.
    """

    def __init__(self, model_router: Any):
        self.router = model_router

    async def simulate(
        self, task: str, answer: str, task_type: str = "general"
    ) -> SimulationReport:
        """Run all failure simulations in parallel."""
        scenarios = []

        # Rule-based simulations (always run, no LLM needed)
        rule_scenarios = self._rule_based_simulations(task, answer)
        scenarios.extend(rule_scenarios)

        if self.router:
            # Run LLM simulations in parallel
            llm_results = await asyncio.gather(
                self._edge_case_simulation(task, answer),
                self._adversarial_simulation(task, answer),
                return_exceptions=True
            )
            for r in llm_results:
                if isinstance(r, list):
                    scenarios.extend(r)
                elif not isinstance(r, Exception):
                    scenarios.append(r)

        # Tally results
        survived = sum(1 for s in scenarios if s.survived)
        failed_scenarios = [s for s in scenarios if not s.survived]
        critical = [s for s in failed_scenarios if s.severity == "critical"]

        survival_rate = survived / max(len(scenarios), 1)
        # Weight by severity: critical failures count more
        weighted_survived = sum(
            (1.0 if s.survived else (0.0 if s.severity == "critical" else 0.3))
            for s in scenarios
        )
        robustness = weighted_survived / max(len(scenarios), 1)

        revision_needed = [f.description for f in failed_scenarios[:3]]
        should_output = len(critical) == 0 and survival_rate >= 0.6

        report = SimulationReport(
            total_scenarios=len(scenarios),
            survived=survived,
            failed=len(failed_scenarios),
            survival_rate=round(survival_rate, 4),
            critical_failures=critical,
            all_scenarios=scenarios,
            robustness_score=round(robustness, 4),
            should_output=should_output,
            revision_needed=revision_needed
        )

        logger.info(
            f"[FailureSim] survived={survived}/{len(scenarios)} "
            f"robustness={robustness:.3f} critical={len(critical)}"
        )
        return report

    def _rule_based_simulations(self, task: str, answer: str) -> List[FailureScenario]:
        scenarios = []
        answer_lower = answer.lower()
        task_lower = task.lower()

        # Scenario 1: Empty input handling
        if any(w in task_lower for w in ["list", "array", "string", "input"]):
            handles_empty = any(w in answer_lower for w in
                               ["empty", "none", "null", "if not", "if len", "edge"])
            scenarios.append(FailureScenario(
                scenario_type="edge_case",
                description="Empty input handling",
                survived=handles_empty,
                evidence="Checks for empty input" if handles_empty else "No empty input handling found",
                severity="moderate" if not handles_empty else "minor"
            ))

        # Scenario 2: Error handling in code
        if any(w in answer_lower for w in ["def ", "function", "class "]):
            handles_errors = any(w in answer_lower for w in
                                ["try", "except", "raise", "error", "exception"])
            scenarios.append(FailureScenario(
                scenario_type="edge_case",
                description="Code error handling",
                survived=handles_errors,
                evidence="Has error handling" if handles_errors else "No try/except or error handling",
                severity="moderate" if not handles_errors else "minor"
            ))

        # Scenario 3: Completeness check
        placeholders = re.findall(r'\bTODO|FIXME|placeholder|your_[a-z_]+\b', answer, re.IGNORECASE)
        scenarios.append(FailureScenario(
            scenario_type="boundary",
            description="Completeness (no placeholders)",
            survived=len(placeholders) == 0,
            evidence=f"No placeholders" if not placeholders else f"Contains: {placeholders[:3]}",
            severity="critical" if placeholders else "minor"
        ))

        return scenarios

    async def _edge_case_simulation(self, task: str, answer: str) -> List[FailureScenario]:
        try:
            resp = await self.router.complete(
                model="reasoning",
                prompt=EDGE_CASE_PROMPT.format(task=task[:400], answer=answer[:600]),
                temperature=0.6,   # more creative to find unusual edge cases
                max_tokens=600
            )
            parsed = self._parse(resp.get("text", ""))
            if not parsed:
                return []

            edge_cases = parsed.get("edge_cases", [])
            is_robust = parsed.get("answer_is_robust", True)

            scenarios = []
            for ec in edge_cases[:3]:
                severity = ec.get("severity", "moderate")
                scenarios.append(FailureScenario(
                    scenario_type="edge_case",
                    description=ec.get("scenario", "")[:100],
                    survived=is_robust,
                    evidence=ec.get("why_fails", "")[:100],
                    severity=severity
                ))
            return scenarios

        except Exception as e:
            logger.debug(f"[FailureSim] Edge case simulation error: {e}")
            return []

    async def _adversarial_simulation(self, task: str, answer: str) -> List[FailureScenario]:
        try:
            resp = await self.router.complete(
                model="reasoning",
                prompt=ADVERSARIAL_PROMPT.format(task=task[:400], answer=answer[:600]),
                temperature=0.7,
                max_tokens=600
            )
            parsed = self._parse(resp.get("text", ""))
            if not parsed:
                return []

            survived_all = parsed.get("survived_all_attacks", False)
            most_critical = parsed.get("most_critical_weakness", "")

            scenarios = []
            for attack_type in ["scenario_attack", "factual_attack", "logic_attack", "assumption_attack"]:
                attack = parsed.get(attack_type, {})
                if attack:
                    scenarios.append(FailureScenario(
                        scenario_type="adversarial",
                        description=f"{attack_type}: {list(attack.values())[0] if attack else ''}",
                        survived=survived_all,
                        evidence=list(attack.values())[-1] if attack else "",
                        severity="moderate" if not survived_all else "minor"
                    ))

            return scenarios[:2]  # cap at 2 adversarial scenarios

        except Exception as e:
            logger.debug(f"[FailureSim] Adversarial simulation error: {e}")
            return []

    def _parse(self, text: str) -> Optional[Dict]:
        try:
            return json.loads(text)
        except Exception:
            m = re.search(r'\{.*\}', text, re.DOTALL)
            if m:
                try: return json.loads(m.group())
                except Exception: pass
        return None


# ══════════════════════════════════════════════════════════════════
# PART 2: CONFIDENCE CALIBRATION SYSTEM
# ══════════════════════════════════════════════════════════════════

@dataclass
class CalibrationRecord:
    """A single data point: predicted confidence vs actual correctness."""
    predicted:   float      # system's stated confidence
    actual:      float      # was the answer actually correct? (0 or 1)
    task_type:   str
    timestamp:   float = field(default_factory=time.time)


class ConfidenceCalibrationSystem:
    """
    Tracks predicted confidence vs actual correctness.
    Computes Expected Calibration Error (ECE) — industry standard metric.
    Applies dynamic recalibration using isotonic regression approximation.

    USAGE:
    1. When system outputs answer with confidence=0.85
    2. Record: calibration.record(predicted=0.85, actual=1.0, task_type="coding")
    3. ECE tells us: if we say 0.85, are we right 85% of the time?
    4. Recalibration adjusts future predictions to match empirical accuracy

    V5 WEAKNESS FIXED: V5 confidence is a static weighted sum.
    This tracks empirical accuracy and adjusts confidence to match reality.
    """

    def __init__(self, n_bins: int = 10):
        self.n_bins = n_bins
        self._records: List[CalibrationRecord] = []
        self._per_type_records: Dict[str, List[CalibrationRecord]] = defaultdict(list)
        # Calibration mapping: predicted confidence → adjusted confidence
        self._calibration_map: Dict[int, float] = {}  # bin_idx → actual_accuracy
        self._ece: float = 0.0       # Expected Calibration Error (ECE) — industry standard
        self._last_calibration: float = 0.0

    def record(self, predicted: float, actual: float, task_type: str = "general"):
        """Record a prediction outcome."""
        rec = CalibrationRecord(predicted=predicted, actual=actual, task_type=task_type)
        self._records.append(rec)
        self._per_type_records[task_type].append(rec)

        # Recalibrate every 20 new records
        if len(self._records) % 20 == 0:
            self._recalibrate()

    def calibrate(self, raw_confidence: float, task_type: str = "general") -> float:
        """
        Apply calibration to a raw confidence score.
        Maps predicted confidence → empirically calibrated confidence.
        """
        if not self._calibration_map or len(self._records) < 10:
            return raw_confidence  # not enough data yet

        bin_idx = min(int(raw_confidence * self.n_bins), self.n_bins - 1)
        if bin_idx in self._calibration_map:
            # Blend: 70% calibrated, 30% raw (to avoid over-fitting)
            calibrated = self._calibration_map[bin_idx]
            return round(raw_confidence * 0.3 + calibrated * 0.7, 4)

        return raw_confidence

    def _recalibrate(self):
        """Recompute calibration map from all records."""
        if len(self._records) < 10:
            return

        bins: Dict[int, List[float]] = defaultdict(list)
        for rec in self._records[-500:]:  # use last 500 records
            bin_idx = min(int(rec.predicted * self.n_bins), self.n_bins - 1)
            bins[bin_idx].append(rec.actual)

        new_map = {}
        total_ece = 0.0
        n = len(self._records[-500:])

        for bin_idx, actuals in bins.items():
            actual_acc = sum(actuals) / len(actuals)
            predicted_mid = (bin_idx + 0.5) / self.n_bins
            new_map[bin_idx] = actual_acc
            # ECE contribution
            total_ece += (len(actuals) / n) * abs(actual_acc - predicted_mid)

        self._calibration_map = new_map
        self._ece = round(total_ece, 4)
        self._last_calibration = time.time()

        logger.info(f"[Calibration] ECE={self._ece:.4f} bins={len(new_map)} records={len(self._records)}")

    def get_ece(self) -> float:
        """Expected Calibration Error / expected_calibration (lower is better, 0 is perfect)."""
        return self._ece

    def get_stats(self) -> Dict[str, Any]:
        if not self._records:
            return {"total_records": 0, "ece": 0.0, "calibrated": False}

        recent = self._records[-100:]
        avg_acc = sum(r.actual for r in recent) / len(recent) if recent else 0.0
        avg_conf = sum(r.predicted for r in recent) / len(recent) if recent else 0.0

        return {
            "total_records": len(self._records),
            "ece": self._ece,
            "recent_avg_accuracy": round(avg_acc, 4),
            "recent_avg_confidence": round(avg_conf, 4),
            "overconfidence_gap": round(avg_conf - avg_acc, 4),
            "calibration_bins": len(self._calibration_map),
            "calibrated": len(self._records) >= 10,
            "task_types": list(self._per_type_records.keys()),
            "last_calibration": self._last_calibration
        }

    def is_overconfident(self) -> bool:
        """Returns True if the system consistently over-estimates its accuracy."""
        stats = self.get_stats()
        return stats.get("overconfidence_gap", 0.0) > 0.10

    def calibration_quality(self) -> str:
        if self._ece < 0.05:
            return "excellent"
        elif self._ece < 0.10:
            return "good"
        elif self._ece < 0.20:
            return "moderate"
        else:
            return "poor"
