from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(name)s: %(message)s",
    stream=sys.stderr,
)

logger = logging.getLogger("eval.cli")


def main():
    parser = argparse.ArgumentParser(prog="python -m eval.cli", description="JARVIS evaluation framework")
    sub = parser.add_subparsers(dest="command")

    run_parser = sub.add_parser("run", help="Run eval scenarios")
    run_parser.add_argument("scenarios", type=str, help="Path to scenario file or directory")
    run_parser.add_argument("--endpoint", type=str, default="", help="LLM endpoint URL")
    run_parser.add_argument("--model", type=str, default="", help="Model name")
    run_parser.add_argument("--output", type=str, default="results.jsonl", help="Output results file")
    run_parser.add_argument("--concurrency", type=int, default=1, help="Parallel scenarios")

    compare_parser = sub.add_parser("compare", help="Compare two result files")
    compare_parser.add_argument("baseline", type=str, help="Baseline results file")
    compare_parser.add_argument("current", type=str, help="Current results file")

    args = parser.parse_args()

    if args.command == "run":
        asyncio.run(_do_run(args))
    elif args.command == "compare":
        _do_compare(args)
    else:
        parser.print_help()


async def _do_run(args):
    from eval.runner import RunConfig, run_scenarios
    from eval.scenario import load_scenarios, save_results

    scenarios = load_scenarios(args.scenarios)
    if not scenarios:
        logger.error("No scenarios found at %s", args.scenarios)
        sys.exit(1)

    config = RunConfig(
        endpoint_url=args.endpoint,
        model=args.model,
    )

    logger.info("Running %d scenarios (concurrency=%d)...", len(scenarios), args.concurrency)
    results = await run_scenarios(scenarios, config, concurrency=args.concurrency)

    path = save_results(results, args.output)

    from eval.scorer import score_all
    scores = score_all(results, scenarios)

    from eval.report import EvalReport, print_report
    report = EvalReport(run_timestamp=path.stat().st_mtime if path.exists() else "", scenarios=scores)
    print_report(report)

    report_path = Path(args.output).with_suffix(".report.json")
    report_path.write_text(json.dumps({
        "timestamp": report.run_timestamp,
        "aggregate": report.aggregate,
        "passed": report.passed,
        "failed": report.failed,
        "scenarios": [
            {"id": s.scenario_id, "aggregate": s.aggregate, "passed": s.passed, "error": s.error}
            for s in scores
        ],
    }, indent=2), encoding="utf-8")
    logger.info("Report written to %s", report_path)


def _do_compare(args):
    from eval.report import compare_runs
    from eval.scenario import load_results
    from eval.scorer import ScenarioScore

    baseline_data = load_results(args.baseline)
    current_data = load_results(args.current)

    def _to_scores(data: list[dict]) -> list[ScenarioScore]:
        scores = []
        for d in data:
            s = ScenarioScore(
                scenario_id=d.get("scenario_id", "?"),
                prompt=d.get("prompt", ""),
                error=d.get("error"),
                round_count=d.get("round_count", 0),
                total_duration=d.get("total_duration", 0.0),
            )
            s.tool_call_accuracy = d.get("scores", {}).get("tool_call_accuracy", 0)
            s.pattern_match = d.get("scores", {}).get("pattern_match", 0)
            s.quality_score = d.get("scores", {}).get("quality_score", 0)
            s.efficiency_score = d.get("scores", {}).get("efficiency_score", 0)
            s.aggregate = d.get("scores", {}).get("aggregate", 0)
            scores.append(s)
        return scores

    baseline_scores = _to_scores(baseline_data)
    current_scores = _to_scores(current_data)

    comparison = compare_runs(baseline_scores, current_scores)
    print(json.dumps(comparison, indent=2))


if __name__ == "__main__":
    main()
