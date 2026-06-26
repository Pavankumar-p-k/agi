"""Capability Benchmark — measures JARVIS across 8 dimensions before/after autonomous improvement cycles.

Usage:
    python benchmarks/capability_benchmark.py --cycles 10

Reports deltas per dimension and an overall capability score.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.analytics.planner import PlannerAnalytics
from core.evidence.generator import EvidenceGenerator
from core.improvement.autonomous_loop import AutonomousLoop
from core.improvement.knob_store import KnobStore
from core.improvement.planner_experiment import PlannerExperimentManager
from core.opportunity.calibration import OpportunityCalibrator
from core.opportunity.engine import OpportunityDiscoveryEngine, DEFAULT_SYSTEM_SCORES
from core.opportunity.store import OpportunityStore

logging.basicConfig(level=logging.WARNING, format="%(message)s")
logger = logging.getLogger(__name__)

REPORT_DIR = Path("benchmark_reports")
REPORT_DIR.mkdir(parents=True, exist_ok=True)


# ═══════════════════════════════════════════════════════════════════════════════
#  Benchmark
# ═══════════════════════════════════════════════════════════════════════════════

class CapabilityBenchmark:
    """Measures system capability across 8 dimensions.

    Dimensions (each 0.0–1.0, 1.0 = best):
      1. planner_health   — prediction accuracy, success rate, calibration error
      2. strategy_diversity — strategy coverage, win rate spread
      3. system_scores    — average subsystem capability score
      4. opportunity_health — open/in_progress ratio, avg score, calibration accuracy
      5. experiment_health  — experiment count, success rate, promotion rate
      6. negotiation_health — sessions, consensus rate
      7. knowledge_health   — knowledge items, experiences (from long_term_memory)
      8. loop_health        — autonomous loop cycles completed, throughput
    """

    def __init__(self):
        self.planner = PlannerAnalytics()
        self.engine = OpportunityDiscoveryEngine()
        self.store = OpportunityStore()
        self.calibrator = OpportunityCalibrator(store=self.store)
        self.exp_mgr = PlannerExperimentManager()
        self.knobs = KnobStore()
        self.loop = AutonomousLoop()

    # ── Public API ─────────────────────────────────────────────────────

    def snapshot(self) -> dict[str, Any]:
        """Take a snapshot of all 8 capability dimensions."""
        # Cache planner analytics since two dimensions use it
        planner_metrics = self._safe_planner_compute()

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "dimensions": {
                "planner_health": self._planner_health(planner_metrics),
                "strategy_diversity": self._strategy_diversity(planner_metrics),
                "system_scores": self._system_scores(),
                "opportunity_health": self._opportunity_health(),
                "experiment_health": self._experiment_health(),
                "negotiation_health": self._negotiation_health(),
                "knowledge_health": self._knowledge_health(),
                "loop_health": self._loop_health(),
            },
        }

    def _safe_planner_compute(self) -> dict[str, Any]:
        """Compute planner analytics once, with error handling."""
        try:
            return self.planner.compute()
        except Exception as e:
            logger.warning(f"planner.compute() failed: {e}")
            return {}

    def overall_score(self, snapshot: dict[str, Any]) -> float:
        """Compute a single 0.0–1.0 overall capability score."""
        dims = snapshot.get("dimensions", {})
        scores = [d.get("score", 0.0) for d in dims.values()]
        return round(sum(scores) / max(len(scores), 1), 4)

    def compute_deltas(
        self, before: dict[str, Any], after: dict[str, Any]
    ) -> dict[str, Any]:
        """Compare two snapshots and return per-dimension deltas."""
        deltas: dict[str, Any] = {
            "overall_before": self.overall_score(before),
            "overall_after": self.overall_score(after),
            "overall_delta": round(
                self.overall_score(after) - self.overall_score(before), 4
            ),
            "dimensions": {},
        }

        b_dims = before.get("dimensions", {})
        a_dims = after.get("dimensions", {})

        for dim in b_dims:
            b_score = b_dims[dim].get("score", 0.0)
            a_score = a_dims[dim].get("score", 0.0)
            deltas["dimensions"][dim] = {
                "before": round(b_score, 4),
                "after": round(a_score, 4),
                "delta": round(a_score - b_score, 4),
                "improved": a_score > b_score,
                "regressed": a_score < b_score,
            }

        # Count improved / regressed dimensions
        improved = sum(1 for d in deltas["dimensions"].values() if d["improved"])
        regressed = sum(1 for d in deltas["dimensions"].values() if d["regressed"])
        deltas["summary"] = {
            "dimensions_improved": improved,
            "dimensions_regressed": regressed,
            "dimensions_unchanged": len(deltas["dimensions"]) - improved - regressed,
        }

        return deltas

    def run_cycle(self) -> dict[str, Any]:
        """Run a single autonomous loop tick and return the result."""
        return self.loop.tick()

    # ── Dimension Computations ─────────────────────────────────────────

    def _planner_health(self, planner_metrics: dict | None = None) -> dict[str, Any]:
        """Dimension 1: Planner prediction accuracy, success rate, calibration."""
        try:
            metrics = planner_metrics if planner_metrics is not None else self._safe_planner_compute()
            overall = metrics.get("overall", {})
            calibration = metrics.get("confidence_calibration", {})

            success_rate = overall.get("success_rate", 0.0) or 0.0
            avg_accuracy = overall.get("avg_prediction_accuracy", 0.0) or 0.0
            cal_error = calibration.get("avg_calibration_error", 1.0) or 1.0

            # Calibration score: lower error = higher score
            cal_score = max(0.0, 1.0 - cal_error)

            # Composite: weighted average
            score = round(
                0.4 * avg_accuracy + 0.3 * success_rate + 0.3 * cal_score, 4
            )

            return {
                "score": score,
                "success_rate": success_rate,
                "avg_prediction_accuracy": avg_accuracy,
                "avg_calibration_error": cal_error,
                "total_plans": overall.get("total_plans", 0),
            }
        except Exception as e:
            logger.warning(f"planner_health failed: {e}")
            return {"score": 0.0, "error": str(e)}

    def _strategy_diversity(self, planner_metrics: dict | None = None) -> dict[str, Any]:
        """Dimension 2: Strategy coverage and win-rate balance."""
        try:
            metrics = planner_metrics if planner_metrics is not None else self._safe_planner_compute()
            win_rates = metrics.get("strategy_win_rates", []) or []

            if not win_rates:
                return {"score": 0.0, "strategies_tried": 0, "message": "No strategies yet"}

            strategies_tried = len(win_rates)
            # Higher diversity = more strategies with non-zero win rates
            active = sum(1 for s in win_rates if s.get("win_rate", 0) > 0)
            diversity_ratio = active / max(strategies_tried, 1)

            # Balance: even distribution is better (lower std dev)
            rates = [s.get("win_rate", 0) for s in win_rates if s.get("win_rate", 0) > 0]
            avg_rate = sum(rates) / max(len(rates), 1) if rates else 0
            variance = sum((r - avg_rate) ** 2 for r in rates) / max(len(rates), 1) if rates else 0
            balance = max(0.0, 1.0 - min(1.0, variance * 2))

            score = round(0.5 * diversity_ratio + 0.5 * balance, 4)

            return {
                "score": score,
                "strategies_tried": strategies_tried,
                "active_strategies": active,
                "avg_win_rate": round(avg_rate, 4),
                "win_rate_variance": round(variance, 4),
            }
        except Exception as e:
            logger.warning(f"strategy_diversity failed: {e}")
            return {"score": 0.0, "error": str(e)}

    def _system_scores(self) -> dict[str, Any]:
        """Dimension 3: Average capability score across all subsystems."""
        try:
            scores = self.engine.get_scored_systems()
            if not scores:
                return {"score": 0.0}

            values = list(scores.values())
            avg = sum(values) / len(values)

            # Weighted: average + bonus for high min score
            min_score = min(values)
            score = round(0.7 * avg + 0.3 * min_score, 4)

            return {
                "score": score,
                "average": round(avg, 4),
                "min": round(min_score, 4),
                "max": round(max(values), 4),
                "systems": scores,
            }
        except Exception as e:
            logger.warning(f"system_scores failed: {e}")
            return {"score": 0.0, "error": str(e)}

    def _opportunity_health(self) -> dict[str, Any]:
        """Dimension 4: Opportunity pipeline health."""
        try:
            all_opps = self.store.list_opportunities(limit=500)
            if not all_opps:
                return {"score": 0.5, "total": 0, "message": "No opportunities yet"}

            total = len(all_opps)
            open_opps = [o for o in all_opps if o.status.value == "open"]
            in_progress = [o for o in all_opps if o.status.value == "in_progress"]
            completed = [o for o in all_opps if o.status.value == "completed"]
            rejected = [o for o in all_opps if o.status.value == "rejected"]

            # Action ratio: in_progress / total (higher = active pipeline)
            action_ratio = len(in_progress) / max(total, 1)

            # Completion rate: completed / (completed + rejected)
            resolved = len(completed) + len(rejected)
            completion_rate = len(completed) / max(resolved, 1) if resolved > 0 else 0.0

            # Average score of open opportunities
            avg_score = sum(o.opportunity_score for o in open_opps) / max(len(open_opps), 1)

            # Calibration accuracy
            cal_accuracy = self.calibrator.get_overall_accuracy()

            score = round(
                0.2 * action_ratio + 0.3 * completion_rate + 0.2 * avg_score + 0.3 * cal_accuracy, 4
            )

            return {
                "score": score,
                "total": total,
                "open": len(open_opps),
                "in_progress": len(in_progress),
                "completed": len(completed),
                "rejected": len(rejected),
                "completion_rate": round(completion_rate, 4),
                "avg_score": round(avg_score, 4),
                "calibration_accuracy": round(cal_accuracy, 4),
            }
        except Exception as e:
            logger.warning(f"opportunity_health failed: {e}")
            return {"score": 0.0, "error": str(e)}

    def _experiment_health(self) -> dict[str, Any]:
        """Dimension 5: Experiment lifecycle health."""
        try:
            exps = self.exp_mgr.list_all()
            if not exps:
                return {"score": 0.5, "total": 0, "message": "No experiments yet"}

            total = len(exps)
            promoted = sum(1 for e in exps if e["status"] == "promoted")
            rolled_back = sum(1 for e in exps if e["status"] == "rolled_back")
            running = sum(1 for e in exps if e["status"] == "running")

            # Promotion rate: promoted / (promoted + rolled_back)
            resolved = promoted + rolled_back
            promotion_rate = promoted / max(resolved, 1) if resolved > 0 else 0.0

            # Running ratio: healthy to have some active experiments
            running_ratio = min(1.0, running / max(total, 1) * 2)

            score = round(0.6 * promotion_rate + 0.4 * running_ratio, 4)

            return {
                "score": score,
                "total": total,
                "promoted": promoted,
                "rolled_back": rolled_back,
                "running": running,
                "promotion_rate": round(promotion_rate, 4),
            }
        except Exception as e:
            logger.warning(f"experiment_health failed: {e}")
            return {"score": 0.0, "error": str(e)}

    def _negotiation_health(self) -> dict[str, Any]:
        """Dimension 6: Negotiation session health."""
        try:
            import sqlite3
            db = str(Path("data") / "workflow.db")
            conn = sqlite3.connect(db)
            conn.row_factory = sqlite3.Row
            try:
                rows = conn.execute(
                    "SELECT status, COUNT(*) as cnt FROM negotiations GROUP BY status"
                ).fetchall()
            except sqlite3.OperationalError:
                rows = []
            finally:
                conn.close()

            if not rows:
                return {"score": 0.5, "total": 0, "message": "No negotiations yet"}

            total = sum(r["cnt"] for r in rows)
            statuses = {r["status"]: r["cnt"] for r in rows}
            accepted = statuses.get("accepted", 0)
            rejected = statuses.get("rejected", 0)
            resolved = accepted + rejected

            consensus_rate = accepted / max(resolved, 1) if resolved > 0 else 0.0
            score = round(consensus_rate, 4)

            return {
                "score": score,
                "total": total,
                "accepted": accepted,
                "rejected": rejected,
                "open": statuses.get("open", 0),
                "consensus_rate": consensus_rate,
            }
        except Exception as e:
            logger.warning(f"negotiation_health failed: {e}")
            return {"score": 0.0, "error": str(e)}

    def _knowledge_health(self) -> dict[str, Any]:
        """Dimension 7: Long-term memory health."""
        try:
            import sqlite3
            db = str(Path("data") / "workflow.db")
            conn = sqlite3.connect(db)
            conn.row_factory = sqlite3.Row
            try:
                knowledge = conn.execute(
                    "SELECT COUNT(*) as cnt FROM knowledge_items"
                ).fetchone() or {"cnt": 0}
                experiences = conn.execute(
                    "SELECT COUNT(*) as cnt FROM experience_summaries"
                ).fetchone() or {"cnt": 0}
                principles = conn.execute(
                    "SELECT COUNT(*) as cnt FROM principles"
                ).fetchone() or {"cnt": 0}
            except sqlite3.OperationalError:
                knowledge = {"cnt": 0}
                experiences = {"cnt": 0}
                principles = {"cnt": 0}
            finally:
                conn.close()

            total = knowledge["cnt"] + experiences["cnt"] + principles["cnt"]
            # More knowledge is better, but diminishing returns
            k_score = min(1.0, total / 50.0)  # 50 items = full score
            # Diversity bonus: having all three types
            diversity = sum(1 for c in [knowledge["cnt"], experiences["cnt"], principles["cnt"]] if c > 0) / 3.0

            score = round(0.6 * k_score + 0.4 * diversity, 4)

            return {
                "score": score,
                "knowledge_items": knowledge["cnt"],
                "experience_summaries": experiences["cnt"],
                "principles": principles["cnt"],
                "total": total,
            }
        except Exception as e:
            logger.warning(f"knowledge_health failed: {e}")
            return {"score": 0.5, "total": 0, "error": str(e)}

    def _loop_health(self) -> dict[str, Any]:
        """Dimension 8: Autonomous loop health — cycles completed, throughput."""
        try:
            exps = self.exp_mgr.list_all()
            total_cycles = len(exps)

            # Throughput bonus: more completed cycles = better
            completed = sum(1 for e in exps if e["status"] in ("promoted", "rolled_back"))
            completion_rate = completed / max(total_cycles, 1) if total_cycles > 0 else 0.0

            # Score: log scale for cycles (10 cycles = 0.5, 100 = 1.0)
            cycle_score = min(1.0, total_cycles / 100.0)

            score = round(0.5 * cycle_score + 0.5 * completion_rate, 4)

            return {
                "score": score,
                "total_cycles": total_cycles,
                "completed": completed,
                "completion_rate": round(completion_rate, 4),
            }
        except Exception as e:
            logger.warning(f"loop_health failed: {e}")
            return {"score": 0.0, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
#  Runner
# ═══════════════════════════════════════════════════════════════════════════════

def run_benchmark(
    cycles: int = 10,
    report_name: str | None = None,
    seed_evidence: int = 0,
    checkpoint_interval: int = 50,
) -> dict[str, Any]:
    """Run the full benchmark: baseline → evidence → N cycles → post → deltas.

    Records checkpoints every `checkpoint_interval` cycles so the learning
    curve can be plotted as d(capability)/d(cycles).
    """
    benchmark = CapabilityBenchmark()

    print(f"\n Capability Benchmark -- {cycles} cycles (checkpoints every {checkpoint_interval})")
    print(f"{'-' * 60}")

    # 1. Baseline snapshot
    print("\n Taking baseline snapshot...")
    before = benchmark.snapshot()
    overall_before = benchmark.overall_score(before)
    print(f"   Baseline overall score: {overall_before:.4f}")

    # 1b. Generate evidence (if requested)
    if seed_evidence > 0:
        print(f"\n Seeding {seed_evidence} evidence batches...")
        ev_gen = EvidenceGenerator()
        ev_start = time.time()
        ev_result = ev_gen.run_cycles(cycles=seed_evidence, batch_size=5)
        ev_elapsed = time.time() - ev_start
        t = ev_result["totals"]
        print(f"   Generated {ev_result['grand_total']} evidence items in {ev_elapsed:.1f}s")
        print(f"     Plans: {t['plans']}  Research: {t['research']}  "
              f"Competitions: {t['competition']}  Negotiations: {t['negotiation']}")

    # 2. Run discovery to seed opportunities
    print("\n Seeding opportunities...")
    try:
        engine = OpportunityDiscoveryEngine()
        results = engine.discover_all()
        count = 0
        for opp in results:
            try:
                benchmark.store.save_opportunity(opp)
                count += 1
            except Exception:
                pass
        # Accept the top opportunity
        if results:
            benchmark.store.update_opportunity_status(results[0].id, "in_progress")
        print(f"   Discovered {count} opportunities (top accepted)")
    except Exception as e:
        logger.warning(f"Seed failed: {e}")

    # 3. Run autonomous cycles with checkpoints
    print(f"\n Running {cycles} autonomous loop cycles...")
    cycle_results = []
    checkpoints: list[dict[str, Any]] = []
    start = time.time()

    for i in range(cycles):
        try:
            result = benchmark.run_cycle()
            cycle_results.append(result)
            action = result.get("action", "unknown")
            if action == "idle":
                re_seed_count = _re_seed_opportunity(benchmark)
                if re_seed_count > 0:
                    result = benchmark.run_cycle()
                    cycle_results.append(result)
                    action = result.get("action", "unknown")

            # Print per-cycle (compact for 500+)
            if cycles <= 100 or i < 10 or (i + 1) % 50 == 0 or i >= cycles - 5:
                print(f"   Cycle {i+1:3d}/{cycles}: {action:20s} (opp={result.get('opp_id','')[:12]}...)")

            # Checkpoint every N cycles
            if (i + 1) % checkpoint_interval == 0 or i == 0:
                checkpoint = _build_checkpoint(benchmark, cycle_results, i + 1)
                checkpoints.append(checkpoint)
                _print_checkpoint(checkpoint, i + 1, cycles)
        except Exception as e:
            logger.warning(f"Cycle {i} failed: {e}")
            cycle_results.append({"action": "error", "error": str(e)})

    elapsed = time.time() - start
    print(f"\n   {cycles} cycles in {elapsed:.1f}s ({cycles/max(elapsed,0.1):.1f} cycles/s)")

    # 4. Post snapshot
    print("\n Taking post snapshot...")
    after = benchmark.snapshot()
    overall_after = benchmark.overall_score(after)

    # 5. Compute deltas
    deltas = benchmark.compute_deltas(before, after)

    # 6. Build report
    report = {
        "benchmark_type": "capability",
        "cycles": cycles,
        "duration_seconds": round(elapsed, 1),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "baseline": before,
        "post": after,
        "deltas": deltas,
        "cycle_results": cycle_results,
        "checkpoints": checkpoints,
    }

    report_name = report_name or f"capability_{cycles}c_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    report_path = REPORT_DIR / f"{report_name}.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)

    # 7. Print summary
    print(f"\n{'=' * 60}")
    print(f" Capability Benchmark Results")
    print(f"{'=' * 60}")
    print(f" Overall:  {overall_before:.4f} -> {overall_after:.4f}  ({deltas['overall_delta']:+.4f})")
    print(f"{'-' * 60}")
    for dim, d in sorted(deltas["dimensions"].items()):
        arrow = " UP" if d["improved"] else " DOWN" if d["regressed"] else "  --"
        print(f" {dim:25s}: {d['before']:.4f} -> {d['after']:.4f} ({d['delta']:+.4f}){arrow}")
    print(f"{'-' * 60}")
    s = deltas["summary"]
    print(f" Improved: {s['dimensions_improved']}  Regressed: {s['dimensions_regressed']}  Unchanged: {s['dimensions_unchanged']}")
    print(f" Report: {report_path}")

    # 8. Print learning curve
    if len(checkpoints) > 1:
        print(f"\n Learning Curve (checkpoints every {checkpoint_interval} cycles):")
        print(f"{'Cycle':>6}  {'Overall':>8}  {'Planner':>8}  {'Experim':>8}  {'Promote':>8}  {'Rollbk':>8}")
        print(f"{'-' * 60}")
        for cp in checkpoints:
            print(f"{cp['cycle']:6d}  {cp['overall']:8.4f}  {cp['planner_health']:8.4f}  "
                  f"{cp['experiment_health']:8.4f}  {cp['promotion_rate']:8.4f}  {cp['rollback_rate']:8.4f}")
        # Trend direction
        first = checkpoints[0]
        last = checkpoints[-1]
        trend = last["overall"] - first["overall"]
        trend_str = f"+{trend:.4f}" if trend >= 0 else f"{trend:.4f}"
        print(f"{'-' * 60}")
        print(f" Trend: {trend_str} over {last['cycle'] - first['cycle']} cycles " +
              ("" if abs(trend) < 0.001 else
               f"({'RISING' if trend > 0 else 'FALLING'})"))
        print()

    # 9. Print promotion diagnostics
    _print_promotion_diagnostics(cycle_results)
    print()

    return report


def _print_promotion_diagnostics(cycle_results: list[dict[str, Any]]) -> None:
    """Extract and print per-experiment delta diagnostics."""
    deltas_acc = []
    deltas_sr = []
    promoted_count = 0
    rolled_back_count = 0
    completed_count = 0

    # Collect all "completed" results with changes
    for r in cycle_results:
        if r.get("action") == "completed":
            completed_count += 1
            result = r.get("result", {})
            if not isinstance(result, dict):
                continue
            changes = result.get("changes", {})
            if not changes:
                continue
            acc = changes.get("accuracy_change")
            sr = changes.get("success_rate_change")
            if isinstance(acc, (int, float)):
                deltas_acc.append(acc)
            if isinstance(sr, (int, float)):
                deltas_sr.append(sr)
        elif r.get("action") == "promoted":
            promoted_count += 1
        elif r.get("action") == "rolled_back":
            rolled_back_count += 1

    # Print promotion summary
    total_decided = promoted_count + rolled_back_count
    if total_decided == 0:
        return

    pr = promoted_count / max(total_decided, 1) * 100
    rr = rolled_back_count / max(total_decided, 1) * 100
    print(f"\n Promotion Diagnostics")
    print(f"{'-' * 60}")
    print(f" Completed: {completed_count}  |  Promoted: {promoted_count} ({pr:.0f}%)  "
          f"Rolled back: {rolled_back_count} ({rr:.0f}%)")

    # Accuracy change histogram
    if deltas_acc:
        _print_delta_histogram("accuracy_change", deltas_acc, 5)
    if deltas_sr:
        _print_delta_histogram("success_rate_change", deltas_sr, 5)

    # Summary stats
    all_deltas = deltas_acc + deltas_sr
    if all_deltas:
        avg = sum(all_deltas) / len(all_deltas)
        _min = min(all_deltas)
        _max = max(all_deltas)
        positive = sum(1 for d in all_deltas if d > 0)
        negative = sum(1 for d in all_deltas if d < 0)
        zero = sum(1 for d in all_deltas if d == 0)
        print(f" Combined: n={len(all_deltas)}  avg={avg:+.4f}  "
              f"range=[{_min:+.4f}, {_max:+.4f}]")
        print(f" Positive: {positive}  Negative: {negative}  Zero: {zero}")


def _print_delta_histogram(label: str, values: list[float], bins: int = 5) -> None:
    """Print a simple ASCII histogram of delta values."""
    if not values:
        return
    _min = min(values)
    _max = max(values)
    if _min == _max:
        print(f" {label}: all = {_min:+.4f} (no variance)")
        return
    bin_w = (_max - _min) / bins
    hist = [0] * bins
    for v in values:
        idx = min(bins - 1, int((v - _min) / bin_w)) if bin_w > 0 else 0
        hist[idx] += 1
    print(f" {label}: n={len(values)}  [{_min:+.4f}, {_max:+.4f}]")
    for i in range(bins):
        lo = _min + i * bin_w
        hi = lo + bin_w
        bar = "#" * hist[i]
        pct = hist[i] / len(values) * 100
        print(f"   [{lo:+.4f}, {hi:+.4f}): {bar} ({pct:.0f}%)")


def _re_seed_opportunity(benchmark: CapabilityBenchmark) -> int:
    """Find or discover the next opportunity, accept it. Returns count accepted."""
    all_opps = benchmark.store.list_opportunities(status="open")
    if all_opps:
        benchmark.store.update_opportunity_status(all_opps[0].id, "in_progress")
        return 1
    engine = OpportunityDiscoveryEngine()
    results = engine.discover_all()
    count = 0
    for opp in results:
        try:
            benchmark.store.save_opportunity(opp)
            count += 1
        except Exception:
            pass
    if results:
        benchmark.store.update_opportunity_status(results[0].id, "in_progress")
    return count


def _build_checkpoint(
    benchmark: CapabilityBenchmark,
    cycle_results: list[dict[str, Any]],
    cycle_num: int,
) -> dict[str, Any]:
    """Snapshot metrics at a checkpoint for learning curve plotting."""
    snapshot = benchmark.snapshot()
    overall = benchmark.overall_score(snapshot)
    dims = snapshot.get("dimensions", {})

    # Compute experiment stats from cycle results
    actions = [r.get("action", "") for r in cycle_results]
    completed = actions.count("completed")
    promoted = actions.count("promoted")
    rolled_back = actions.count("rolled_back")
    created = actions.count("created")

    return {
        "cycle": cycle_num,
        "overall": overall,
        "planner_health": dims.get("planner_health", {}).get("score", 0),
        "experiment_health": dims.get("experiment_health", {}).get("score", 0),
        "strategy_diversity": dims.get("strategy_diversity", {}).get("score", 0),
        "system_scores": dims.get("system_scores", {}).get("score", 0),
        "loop_health": dims.get("loop_health", {}).get("score", 0),
        "knowledge_health": dims.get("knowledge_health", {}).get("score", 0),
        "negotiation_health": dims.get("negotiation_health", {}).get("score", 0),
        "opportunity_health": dims.get("opportunity_health", {}).get("score", 0),
        "promotion_rate": promoted / max(completed, 1),
        "rollback_rate": rolled_back / max(completed, 1),
        "experiments_created": created,
        "experiments_completed": completed,
        "experiments_promoted": promoted,
        "experiments_rolled_back": rolled_back,
    }


def _print_checkpoint(checkpoint: dict[str, Any], cycle: int, total: int) -> None:
    """Print a compact checkpoint line."""
    pct = cycle / total * 100
    print(f"   [{pct:5.1f}%] CHECKPOINT @ cycle {cycle:4d}: "
          f"overall={checkpoint['overall']:.4f}  "
          f"planner={checkpoint['planner_health']:.4f}  "
          f"promote={checkpoint['promotion_rate']:.4f}  "
          f"rollback={checkpoint['rollback_rate']:.4f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Capability Benchmark")
    parser.add_argument("--cycles", type=int, default=10, help="Number of autonomous loop cycles")
    parser.add_argument("--name", type=str, default=None, help="Report name")
    parser.add_argument("--seed-evidence", type=int, default=0,
                        help="Number of evidence generation cycles to run before the loop")
    parser.add_argument("--checkpoint-interval", type=int, default=100,
                        help="Number of cycles between checkpoints (default 100)")
    args = parser.parse_args()

    report = run_benchmark(cycles=args.cycles, report_name=args.name,
                           seed_evidence=args.seed_evidence,
                           checkpoint_interval=args.checkpoint_interval)

    # Exit code: positive if overall improved
    delta = report["deltas"]["overall_delta"]
    sys.exit(0 if delta >= 0 else 1)
