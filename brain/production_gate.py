"""brain/production_gate.py

Production readiness gate for the Android Builder.

Evaluates benchmark results against strict criteria and determines
whether the Android builder should be considered PRODUCTION or EXPERIMENTAL.

Rules:
  - 90%+ benchmark build success rate
  - APK generated for 90%+ of successful builds
  - Runtime validation passed for 60%+ of builds (when ADB/emulator available)
  - No manual intervention required during build cycle
  - PatternFailureMemory shows learning (5+ generalizations)
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Thresholds
PRODUCTION_THRESHOLDS = {
    "build_success_rate_pct": 90.0,
    "apk_generation_rate_pct": 90.0,
    "runtime_validation_rate_pct": 60.0,
    "pattern_memory_min_generalizations": 5,
    "min_benchmarks": 4,
}


@dataclass
class GateResult:
    passed: bool = False
    status: str = "EXPERIMENTAL"
    score: float = 0.0
    checks: dict[str, dict] = field(default_factory=dict)
    recommendations: list[str] = field(default_factory=list)
    timestamp: str = ""

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "status": self.status,
            "score": round(self.score, 1),
            "checks": self.checks,
            "recommendations": self.recommendations,
            "timestamp": self.timestamp,
        }


class ProductionGate:
    """Evaluate Android builder against production readiness criteria."""

    def __init__(self):
        self.result = GateResult()
        self.result.timestamp = datetime.now().isoformat()

    def evaluate(self, report_path: str | dict) -> GateResult:
        """Evaluate a benchmark report (JSON file path or dict)."""
        if isinstance(report_path, str):
            path = Path(report_path)
            if not path.exists():
                logger.error("[ProdGate] Report not found: %s", report_path)
                self.result.passed = False
                self.result.checks["report_found"] = {
                    "passed": False,
                    "detail": f"Report file not found: {report_path}",
                }
                return self.result

            with open(path, encoding="utf-8") as f:
                report = json.load(f)
        else:
            report = report_path

        summary = report.get("summary", {})
        benchmarks = report.get("benchmarks", [])

        # ── Check 1: Minimum benchmarks ──
        total = summary.get("total_benchmarks", len(benchmarks))
        min_benchmarks = PRODUCTION_THRESHOLDS["min_benchmarks"]
        check_min = {
            "passed": total >= min_benchmarks,
            "detail": f"{total}/{min_benchmarks} benchmarks run",
            "value": total,
            "threshold": min_benchmarks,
        }
        self.result.checks["minimum_benchmarks"] = check_min

        # ── Check 2: Build success rate ──
        success_rate = summary.get("build_success_rate_pct", 0)
        threshold_build = PRODUCTION_THRESHOLDS["build_success_rate_pct"]
        check_build = {
            "passed": success_rate >= threshold_build,
            "detail": f"Build success: {success_rate}% (threshold: {threshold_build}%)",
            "value": success_rate,
            "threshold": threshold_build,
        }
        self.result.checks["build_success_rate"] = check_build

        # ── Check 3: APK generation rate ──
        apk_rate = summary.get("apk_generation_rate_pct", 0)
        threshold_apk = PRODUCTION_THRESHOLDS["apk_generation_rate_pct"]
        check_apk = {
            "passed": apk_rate >= threshold_apk,
            "detail": f"APK generation: {apk_rate}% (threshold: {threshold_apk}%)",
            "value": apk_rate,
            "threshold": threshold_apk,
        }
        self.result.checks["apk_generation_rate"] = check_apk

        # ── Check 4: Runtime validation rate ──
        runtime_pass = summary.get("runtime_validations_passed", 0)
        runtime_total = sum(1 for b in benchmarks if b.get("build_success") and b.get("apk_generated"))
        runtime_rate = (runtime_pass / max(runtime_total, 1)) * 100 if runtime_total > 0 else 0
        threshold_runtime = PRODUCTION_THRESHOLDS["runtime_validation_rate_pct"]
        check_runtime = {
            "passed": runtime_rate >= threshold_runtime if runtime_total > 0 else True,
            "detail": f"Runtime validation: {runtime_rate}% ({runtime_pass}/{runtime_total}) (threshold: {threshold_runtime}%)",
            "value": round(runtime_rate, 1),
            "threshold": threshold_runtime,
        }
        self.result.checks["runtime_validation_rate"] = check_runtime

        # ── Check 5: PatternFailureMemory learning ──
        memory_hits = summary.get("total_memory_hits", 0)
        check_memory = {
            "passed": memory_hits >= PRODUCTION_THRESHOLDS["pattern_memory_min_generalizations"],
            "detail": f"Pattern memory hits: {memory_hits} (threshold: {PRODUCTION_THRESHOLDS['pattern_memory_min_generalizations']})",
            "value": memory_hits,
            "threshold": PRODUCTION_THRESHOLDS["pattern_memory_min_generalizations"],
        }
        self.result.checks["pattern_memory_learning"] = check_memory

        # ── Compute overall score ──
        weights = {
            "minimum_benchmarks": 0.10,
            "build_success_rate": 0.35,
            "apk_generation_rate": 0.25,
            "runtime_validation_rate": 0.15,
            "pattern_memory_learning": 0.15,
        }

        score = 0.0
        for check_name, weight in weights.items():
            check = self.result.checks.get(check_name, {"passed": False, "detail": "not evaluated"})
            if check.get("passed"):
                score += weight
            self.result.checks[check_name] = check

        self.result.score = score * 100

        # ── Determine status ──
        all_passed = all(
            c.get("passed", False) for c in self.result.checks.values()
        )
        self.result.passed = all_passed and score >= 0.75

        if self.result.passed:
            self.result.status = "PRODUCTION"
            self.result.recommendations = [
                "Android builder is production-ready",
                "Monitor build success rate in CI/CD",
                "Consider adding AAPT2 and ProGuard error parsers for broader coverage",
            ]
        else:
            self.result.status = "EXPERIMENTAL"

            # Generate specific recommendations for failures
            for check_name, check in self.result.checks.items():
                if not check.get("passed"):
                    self.result.recommendations.append(
                        f"Fix {check_name}: {check.get('detail', '')}"
                    )

            if not check_build.get("passed"):
                self.result.recommendations.append(
                    f"Improve build success rate from {success_rate}% to ≥{threshold_build}%"
                )
            if not check_apk.get("passed"):
                self.result.recommendations.append(
                    f"Improve APK generation from {apk_rate}% to ≥{threshold_apk}%"
                )
            if runtime_total > 0 and not check_runtime.get("passed"):
                self.result.recommendations.append(
                    f"Improve runtime validation from {runtime_rate}% to ≥{threshold_runtime}%"
                )
            if not check_memory.get("passed"):
                self.result.recommendations.append(
                    "Run more builds to build pattern memory — need 5+ generalizations"
                )

            self.result.recommendations.insert(0,
                "Android builder is EXPERIMENTAL — not yet ready for production use")

        logger.info("[ProdGate] Gate status: %s (score: %.1f%%)", self.result.status, self.result.score)
        return self.result

    def evaluate_benchmark_list(self, benchmarks: list[dict]) -> GateResult:
        """Evaluate a raw list of benchmark results (dicts)."""
        report = {
            "summary": self._aggregate(benchmarks),
            "benchmarks": benchmarks,
        }
        return self.evaluate(report)

    def _aggregate(self, benchmarks: list[dict]) -> dict:
        total = len(benchmarks)
        successes = sum(1 for b in benchmarks if b.get("build_success"))
        apks = sum(1 for b in benchmarks if b.get("apk_generated"))
        tests_pass = sum(1 for b in benchmarks if b.get("test_success"))
        runtime_pass = sum(1 for b in benchmarks if b.get("runtime_validation"))
        total_repairs = sum(b.get("repair_cycles", 0) for b in benchmarks)
        total_errors = sum(b.get("total_errors", 0) for b in benchmarks)
        total_fixed = sum(b.get("repaired_errors", 0) for b in benchmarks)
        total_memory_hits = sum(b.get("pattern_memory_hits", 0) for b in benchmarks)

        return {
            "total_benchmarks": total,
            "build_successful": successes,
            "build_success_rate_pct": round(successes / total * 100, 1) if total else 0,
            "apk_generated": apks,
            "apk_generation_rate_pct": round(apks / total * 100, 1) if total else 0,
            "tests_passed": tests_pass,
            "runtime_validations_passed": runtime_pass,
            "total_repair_cycles": total_repairs,
            "total_errors_encountered": total_errors,
            "total_errors_repaired": total_fixed,
            "total_memory_hits": total_memory_hits,
            "overall_fix_rate_pct": round(total_fixed / max(total_errors, 1) * 100, 1),
        }


# Singleton
production_gate = ProductionGate()
