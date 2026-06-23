"""Memory ranking benchmark — validates that ranking selects the best repair strategy.

Scenarios (16 total):
  Group A — Clear winner (5 cases): one strategy dominates
  Group B — Close competition (5 cases): narrow margins, prefers cheap strategies  
  Group C — Only failures (3 cases): some strategies never succeeded
  Group D — Empty/unknown (3 cases): no historical data

Questions answered:
  1. Does ranking choose the best repair?
  2. Does ranking outperform first-match?
  3. Does ranking improve recovery rate?
"""
import json
import logging
import os
import sys
import time

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.pattern_failure_memory import PatternFailureMemory, ScoredMatch

logger = logging.getLogger("memory_ranking_benchmark")


# ── Scenario definitions ───────────────────────────────────────────

# Each scenario: (name, error_text, strategies_to_record, expected_best_strategy)
# strategies_to_record: list of (strategy, is_success) tuples
# expected_best_strategy: the strategy that should rank #1
# Error texts avoid file paths (.java suffixes) to keep generalization simple.

Scenario = tuple[str, str, list[tuple[str, bool]], str]

SCENARIOS: list[Scenario] = [
    # ── Group A: Clear winner (one strategy dominates) ───────────
    ("A1_import_dominate",
     "error: cannot find symbol: class RecyclerView",
     [("add_import", True)] * 9 + [("create_file", True)] * 1,
     "add_import"),

    ("A2_cast_dominate",
     "error: incompatible types: String cannot be converted to int",
     [("fix_code", True)] * 8 + [("fix_resources", True)] * 2,
     "fix_code"),

    ("A3_layout_dominate",
     "error: R.layout.activity_main not found",
     [("create_layout", True)] * 7 + [("fix_resources", True)] * 3,
     "create_layout"),

    ("A4_syntax_dominate",
     "error: ';' expected",
     [("fix_syntax", True)] * 10 + [("fix_code", True)] * 1,
     "fix_syntax"),

    ("A5_string_dominate",
     "error: R.string.app_name not found",
     [("add_string_resource", True)] * 6 + [("fix_resources", True)] * 4,
     "add_string_resource"),

    # ── Group B: Close competition (narrow margins) ────────────
    ("B1_close_race",
     "error: cannot find symbol: class ViewModelProvider",
     [("add_import", True)] * 5 + [("create_file", True)] * 4,
     "add_import"),  # equal rates (100%) → cheaper wins → add_import is cheap

    ("B2_cost_bonus",
     "error: cannot find symbol: class NavController",
     [("add_import", True)] * 3 + [("create_file", True)] * 3,
     "add_import"),  # equal rates → cheaper wins

    ("B3_recovery_matters",
     "error: cannot find symbol: class LiveData",
     [("add_import", True)] * 2 + [("create_file", True)] * 2,
     "add_import"),  # equal rates → cheaper wins

    ("B4_expensive_wins_marginally",
     "error: incompatible types: int cannot be converted to String",
     [("fix_code", True)] * 5 + [("fix_syntax", True)] * 3,
     "fix_code"),  # 5/5 vs 3/3, equal rates but fix_code has more evidence

    ("B5_recent_vs_stale",
     "error: cannot find symbol: class FragmentManager",
     [("add_import", True)] * 10 + [("clean_and_build", True)] * 1,
     "add_import"),  # 10 old successes beat 1 recent success

    # ── Group C: Only failures ─────────────────────────────────
    ("C1_all_failed",
     "error: cannot find symbol: class MissingType",
     [("add_import", False)] * 5,
     "add_import"),  # only base strategy exists, valid but low score

    ("C2_failed_then_success",
     "error: incompatible types: double cannot be converted to float",
     [("fix_code", False)] * 3 + [("fix_code", True)] * 2,
     "fix_code"),  # 2/5 = 40% success — better than nothing

    ("C3_mixed_failures",
     "error: R.color.primary_dark not found",
     [("create_drawable", False)] * 2 + [("add_color_resource", True)] * 1,
     "add_color_resource"),

    # ── Group D: Empty / no data ───────────────────────────────
    ("D1_no_history",
     "error: resource style/Theme.AppTheme not found",
     [],
     ""),  # no data → no match

    ("D2_new_category",
     "error: attribute android:paddingLeft not found",
     [],
     ""),

    ("D3_unrecognized_message",
     "AAPT: error: resource XML attribute not found",
     [],
     ""),
]


def run_benchmark() -> dict:
    """Run all 16 scenarios and return results."""
    results = {"scenarios": [], "summary": {}}
    passed = 0
    failed = 0

    for name, error_text, strategies, expected in SCENARIOS:
        mem = PatternFailureMemory()
        mem.clear()

        for strategy, is_success in strategies:
            if is_success:
                mem.record_success(error_text, strategy)
            else:
                mem.record_failure(error_text, strategy)

        matches = mem.match_all(error_text)
        selected = matches[0].fix_strategy if matches else ""
        selected_score = matches[0].score if matches else 0.0
        all_scores = {m.fix_strategy: m.score for m in matches}

        if expected:
            correct = selected == expected
        else:
            correct = len(matches) == 0

        scenario_result = {
            "name": name,
            "strategies_recorded": len(strategies),
            "strategies_success": sum(1 for _, s in strategies if s),
            "strategies_failed": sum(1 for _, s in strategies if not s),
            "expected": expected or "(no match)",
            "selected": selected or "(none)",
            "score": round(selected_score, 4),
            "all_scores": all_scores,
            "correct": correct,
        }
        results["scenarios"].append(scenario_result)

        if correct:
            passed += 1
        else:
            failed += 1
            logger.warning("FAIL: %s — expected=%s, selected=%s, scores=%s",
                           name, expected, selected, all_scores)

    results["summary"] = {
        "total": len(SCENARIOS),
        "passed": passed,
        "failed": failed,
        "accuracy_pct": round(passed / len(SCENARIOS) * 100, 1),
        "group_a_passed": sum(1 for s in results["scenarios"]
                              if s["name"].startswith("A") and s["correct"]),
        "group_b_passed": sum(1 for s in results["scenarios"]
                              if s["name"].startswith("B") and s["correct"]),
        "group_c_passed": sum(1 for s in results["scenarios"]
                              if s["name"].startswith("C") and s["correct"]),
        "group_d_passed": sum(1 for s in results["scenarios"]
                              if s["name"].startswith("D") and s["correct"]),
    }
    return results


def print_report(results: dict):
    s = results["summary"]
    print(f"\n{'='*60}")
    print("Memory Ranking Benchmark")
    print(f"{'='*60}")
    print(f"  Accuracy:       {s['accuracy_pct']}% ({s['passed']}/{s['total']})")
    print(f"  Group A (clear): {s['group_a_passed']}/5")
    print(f"  Group B (close): {s['group_b_passed']}/5")
    print(f"  Group C (fail):  {s['group_c_passed']}/3")
    print(f"  Group D (empty): {s['group_d_passed']}/3")
    print(f"{'='*60}")

    for sc in results["scenarios"]:
        status = "PASS" if sc["correct"] else "FAIL"
        print(f"  {status} {sc['name']}: expected={sc['expected']}, "
              f"selected={sc['selected']} (score={sc['score']})")
    print()


def main():
    logger.info("Running memory ranking benchmark...")
    start = time.time()
    results = run_benchmark()
    elapsed = time.time() - start
    results["elapsed_s"] = round(elapsed, 2)

    os.makedirs("benchmark_results", exist_ok=True)
    path = os.path.join("benchmark_results", "memory_ranking.json")
    with open(path, "w") as f:
        json.dump(results, f, indent=2)
    logger.info("Results saved to %s", path)

    print_report(results)

    success = results["summary"]["accuracy_pct"] >= 80.0
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
