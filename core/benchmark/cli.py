"""Multi-Model Benchmark CLI — run the benchmark matrix from the command line.

Usage:
    python -m core.benchmark.cli --models qwen2.5:7b gemma4:9b
    python -m core.benchmark.cli --tasks A B --no-raw
    python -m core.benchmark.cli --report benchmark_results.md
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from core.benchmark import (
    DEFAULT_MODELS,
    DEFAULT_TASKS,
    BenchmarkMode,
    BenchmarkOrchestrator,
    BenchmarkReportGenerator,
    BenchmarkResultsStore,
    ModelConfiguration,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("benchmark_cli")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="JARVIS Multi-Model Benchmark Harness",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python -m core.benchmark.cli --models qwen2.5:7b gemma4:9b\n"
            "  python -m core.benchmark.cli --tasks A B --no-raw\n"
            "  python -m core.benchmark.cli --report benchmark_report.md\n"
        ),
    )
    parser.add_argument(
        "--models", "-m",
        nargs="+",
        default=[],
        help="Model IDs to benchmark (default: all DEFAULT_MODELS)",
    )
    parser.add_argument(
        "--tasks", "-t",
        nargs="+",
        default=[],
        help="Task IDs to run (default: all DEFAULT_TASKS)",
    )
    parser.add_argument(
        "--no-raw",
        action="store_true",
        help="Skip RAW mode (architecture only)",
    )
    parser.add_argument(
        "--no-arch",
        action="store_true",
        help="Skip WITH_ARCHITECTURE mode (raw only)",
    )
    parser.add_argument(
        "--concurrency", "-c",
        type=int,
        default=2,
        help="Max concurrent runs (default: 2)",
    )
    parser.add_argument(
        "--report", "-r",
        type=str,
        default="",
        help="Path to write markdown report file",
    )
    parser.add_argument(
        "--session",
        type=str,
        default="",
        help="Session tag for results storage",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose per-run logging",
    )
    return parser.parse_args(argv)


async def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    # Configure models
    if args.models:
        models = [
            ModelConfiguration(id=m, name=m, provider="ollama")
            for m in args.models
        ]
    else:
        models = DEFAULT_MODELS

    # Configure tasks
    if args.tasks:
        tasks = [t for t in DEFAULT_TASKS if t.id in args.tasks]
        if not tasks:
            logger.error("No matching tasks found for: %s", args.tasks)
            return 1
    else:
        tasks = DEFAULT_TASKS

    logger.info("Benchmark config:")
    logger.info("  Models: %s", [m.id for m in models])
    logger.info("  Tasks:  %s", [t.id for t in tasks])
    logger.info("  Modes:  %s",
                ["raw"] if args.no_arch else
                ["arch"] if args.no_raw else
                ["raw", "arch"])

    # Run benchmark
    orchestrator = BenchmarkOrchestrator(
        concurrency=args.concurrency,
        verbose=args.verbose,
    )
    report = await orchestrator.run_all(
        models=models,
        tasks=tasks,
        include_raw=not args.no_raw,
        include_arch=not args.no_arch,
    )

    # Print summary
    print()
    print(BenchmarkReportGenerator.to_text_summary(report))
    print()

    # Generate markdown report
    md = BenchmarkReportGenerator.to_markdown(report)
    if args.report:
        with open(args.report, "w") as f:
            f.write(md)
        logger.info("Report written to %s", args.report)
    else:
        print("=== Markdown Report ===")
        print(md)

    # Store results
    store = BenchmarkResultsStore()
    report_id = store.save_report(report, session_tag=args.session)
    for run in [r for mr in report.model_results for r in mr.raw_runs + mr.arch_runs]:
        store.save_run(run)
    for task in tasks:
        store.save_task(task)
    logger.info("Results saved to benchmark store (report #%d)", report_id)

    # Print overall gain as exit status hint
    overall = report.overall_avg_gain
    logger.info("Overall architecture gain: +%.1f%%", overall * 100)

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
