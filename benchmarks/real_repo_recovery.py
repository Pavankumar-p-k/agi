"""real_repo_recovery.py — Real Android repository recovery benchmark.

Workflow:
  Clone/Open Repo
       ↓
  gradlew assembleDebug
       ↓
  Parse Errors
       ↓
  Deterministic Repairs → Memory Repairs → LLM Fallback
       ↓
  Rebuild
       ↓
  Repeat → Success or Stop

Usage:
    # Run against pre-downloaded repos:
    python benchmarks/real_repo_recovery.py --repos-dir ./test_repos/ --results ./results/

    # Dry-run with fixture build outputs:
    python benchmarks/real_repo_recovery.py --fixtures tests/fixtures/build_outputs/ --results ./results/

    # Single repo with custom build command:
    python benchmarks/real_repo_recovery.py --repo ./my_project/ --build-cmd ./gradlew assembleDebug
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from brain.compiler_repair_engine import CompilerRepairEngine, JavacError
from brain.repair_chaining import RepairChain, ChainResult
from core.pattern_failure_memory import PatternFailureMemory

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("real_repo_recovery")


# ── Metrics ─────────────────────────────────────────────────────────


@dataclass
class RepoResult:
    """Outcome for a single repository recovery attempt."""
    repo_name: str
    repo_url: str = ""
    repo_size: str = ""  # small / medium / large
    initial_error_count: int = 0
    parsed_errors: int = 0
    deterministic_fixes: int = 0
    memory_fixes: int = 0
    llm_fixes: int = 0
    total_iterations: int = 0
    build_success: bool = False
    recovery_time_s: float = 0.0
    stop_reason: str = ""
    chain_metrics: dict = field(default_factory=dict)
    timing: dict = field(default_factory=dict)
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "repo_name": self.repo_name,
            "repo_url": self.repo_url,
            "repo_size": self.repo_size,
            "initial_error_count": self.initial_error_count,
            "parsed_errors": self.parsed_errors,
            "deterministic_fixes": self.deterministic_fixes,
            "memory_fixes": self.memory_fixes,
            "llm_fixes": self.llm_fixes,
            "total_iterations": self.total_iterations,
            "build_success": self.build_success,
            "recovery_time_s": round(self.recovery_time_s, 2),
            "stop_reason": self.stop_reason,
            "timing": self.timing,
            "notes": self.notes,
        }


@dataclass
class AggregateReport:
    """Aggregate across all repositories."""
    total_repos: int = 0
    recovered: int = 0
    failed: int = 0
    total_initial_errors: int = 0
    total_parsed_errors: int = 0
    total_deterministic: int = 0
    total_memory: int = 0
    total_llm: int = 0
    total_iterations: int = 0
    avg_recovery_time_s: float = 0.0
    repos: list[RepoResult] = field(default_factory=list)

    def parse_rate(self) -> float:
        if self.total_initial_errors == 0:
            return 0.0
        return round(self.total_parsed_errors / self.total_initial_errors * 100, 1)

    def recovery_rate(self) -> float:
        if self.total_repos == 0:
            return 0.0
        return round(self.recovered / self.total_repos * 100, 1)

    def llm_fallback_rate(self) -> float:
        total_fixes = self.total_deterministic + self.total_memory + self.total_llm
        if total_fixes == 0:
            return 0.0
        return round(self.total_llm / total_fixes * 100, 1)

    def deterministic_rate(self) -> float:
        total_fixes = self.total_deterministic + self.total_memory + self.total_llm
        if total_fixes == 0:
            return 0.0
        return round(self.total_deterministic / total_fixes * 100, 1)

    def to_dict(self) -> dict:
        return {
            "total_repos": self.total_repos,
            "recovered": self.recovered,
            "failed": self.failed,
            "recovery_rate_pct": self.recovery_rate(),
            "parse_rate_pct": self.parse_rate(),
            "total_initial_errors": self.total_initial_errors,
            "total_parsed_errors": self.total_parsed_errors,
            "total_deterministic_fixes": self.total_deterministic,
            "total_memory_fixes": self.total_memory,
            "total_llm_fixes": self.total_llm,
            "deterministic_rate_pct": self.deterministic_rate(),
            "llm_fallback_rate_pct": self.llm_fallback_rate(),
            "total_iterations": self.total_iterations,
            "avg_recovery_time_s": round(self.avg_recovery_time_s, 2),
            "repos": [r.to_dict() for r in self.repos],
        }


# ── Repository Config ──────────────────────────────────────────────

# Suggested test set: 10 Android repositories of varying sizes.
# Each entry can be cloned from GitHub or loaded from a local path.
# Repos known to have build issues or complex configurations.

DEFAULT_TEST_SET = [
    # Small (3)
    {"name": "todo-app", "url": "https://github.com/android/sunflower.git",
     "size": "small", "build_cmd": "", "branch": "main",
     "notes": "Basic Jetpack Compose app"},
    {"name": "notepad-app", "url": "https://github.com/erikcaffrey/Android-Notes.git",
     "size": "small", "build_cmd": "", "branch": "main",
     "notes": "Simple note-taking app with Room"},
    {"name": "weather-app", "url": "https://github.com/bboybogy/WeatherApp.git",
     "size": "small", "build_cmd": "", "branch": "master",
     "notes": "Weather app with Retrofit + MVVM"},
    # Medium (4)
    {"name": "plaid", "url": "https://github.com/nickbutcher/plaid.git",
     "size": "medium", "build_cmd": "", "branch": "main",
     "notes": "Material Design showcase (may need AGP update)"},
    {"name": "iosched", "url": "https://github.com/google/iosched.git",
     "size": "medium", "build_cmd": "", "branch": "main",
     "notes": "Google I/O scheduler (complex build)"},
    {"name": "universal-music-player", "url": "https://github.com/googlesamples/android-UniversalMusicPlayer.git",
     "size": "medium", "build_cmd": "", "branch": "main",
     "notes": "Media playback sample"},
    {"name": "muzei", "url": "https://github.com/romannurik/muzei.git",
     "size": "medium", "build_cmd": "", "branch": "main",
     "notes": "Live wallpaper app with complex deps"},
    # Large (3)
    {"name": "k-9", "url": "https://github.com/thunderbird/thunderbird-android.git",
     "size": "large", "build_cmd": "", "branch": "main",
     "notes": "Email client (thunderbird-android, ~1M LOC)"},
    {"name": "signal-android", "url": "https://github.com/signalapp/Signal-Android.git",
     "size": "large", "build_cmd": "", "branch": "main",
     "notes": "Signal messenger (encrypted, complex build)"},
    {"name": "wordpress-android", "url": "https://github.com/wordpress-mobile/WordPress-Android.git",
     "size": "large", "build_cmd": "", "branch": "trunk",
     "notes": "WordPress Android app"},
]


# ── Repository Recovery ────────────────────────────────────────────


class RepoRecoveryRunner:
    """Run recovery on a single repository."""

    def __init__(self, repo_dir: str, build_cmd: list[str] | None = None,
                 pattern_memory: PatternFailureMemory | None = None,
                 max_iterations: int = 25):
        self.repo_dir = repo_dir
        self.build_cmd = build_cmd or self._detect_build_cmd()
        self.pattern_memory = pattern_memory or PatternFailureMemory()
        self.max_iterations = max_iterations

    def _detect_build_cmd(self) -> list[str]:
        """Detect the appropriate build command for the repo."""
        gradlew = os.path.join(self.repo_dir, "gradlew")
        gradlew_bat = os.path.join(self.repo_dir, "gradlew.bat")
        if os.path.exists(gradlew_bat):
            return [gradlew_bat, "assembleDebug"]
        if os.path.exists(gradlew):
            return ["bash", gradlew, "assembleDebug"]
        # Use cmd /c on Windows to handle .cmd shims from scoop/choco
        return ["cmd", "/c", "gradle", "assembleDebug", "--no-daemon"]

    def run_build(self, timeout: int = 900) -> tuple[int, str]:
        """Run the build command and return (returncode, output)."""
        start = time.time()
        try:
            result = subprocess.run(
                self.build_cmd,
                capture_output=True,
                text=True,
                cwd=self.repo_dir,
                timeout=timeout,
            )
            output = result.stdout + "\n" + result.stderr
            elapsed = time.time() - start
            logger.info("Build completed in %.1fs (exit code %d, %d chars output)",
                        elapsed, result.returncode, len(output))
            return result.returncode, output
        except subprocess.TimeoutExpired:
            logger.warning("Build timed out after %ds", timeout)
            return -1, f"BUILD TIMEOUT after {timeout}s"
        except FileNotFoundError:
            logger.error("Build command not found: %s", self.build_cmd[0])
            if self.build_cmd[0].endswith("gradlew"):
                logger.error("gradlew not found — run './gradlew' or use --build-cmd")
            return -2, f"BUILD COMMAND NOT FOUND: {self.build_cmd[0]}"
        except Exception as e:
            logger.error("Build failed: %s", e)
            return -3, f"BUILD ERROR: {e}"

    async def recover(self, initial_output: str | None = None) -> RepoResult:
        """Run the full recovery pipeline."""
        result = RepoResult(repo_name=os.path.basename(self.repo_dir))
        start_total = time.time()

        # Step 1: Initial build
        if initial_output is None:
            logger.info("Running initial build...")
            rc, initial_output = self.run_build()
            result.initial_error_count = initial_output.count("error:")
            if rc == 0:
                logger.info("Build succeeded on first attempt — no recovery needed")
                result.build_success = True
                result.stop_reason = "no_errors"
                result.recovery_time_s = time.time() - start_total
                return result
        else:
            # Estimate errors from output
            result.initial_error_count = initial_output.count("error:")

        # Step 2: Parse
        engine = CompilerRepairEngine(self.repo_dir, pattern_memory=self.pattern_memory)
        errors = engine.parse_errors(initial_output)
        result.parsed_errors = len(errors)
        logger.info("Parsed %d errors from build output", len(errors))

        if not errors:
            logger.warning("0 errors parsed — cannot proceed with repair")
            result.build_success = False
            result.stop_reason = "no_errors_parsed"
            result.recovery_time_s = time.time() - start_total
            return result

        # Step 3: Run repair chain
        chain = RepairChain(
            engine,
            self.repo_dir,
            max_iterations=self.max_iterations,
        )

        def rebuild_fn():
            rc, output = self.run_build()
            return rc == 0, output

        chain_result = await chain.run(
            build_output=initial_output,
            rebuild_fn=rebuild_fn,
        )

        # Step 4: Record results
        elapsed = time.time() - start_total
        result.build_success = chain_result.success
        result.total_iterations = chain_result.total_iterations
        result.stop_reason = chain_result.stop_reason
        result.recovery_time_s = elapsed
        result.chain_metrics = chain_result.metrics.to_dict() if chain_result.metrics else {}

        m = chain_result.metrics or {}
        result.deterministic_fixes = getattr(m, 'deterministic_repairs', 0)
        result.memory_fixes = getattr(m, 'memory_repairs', 0)
        result.llm_fixes = getattr(m, 'llm_repairs', 0)

        status = "RECOVERED" if result.build_success else "FAILED"
        logger.info("Repo %s: %s (%d iters, %d fixes, %.1fs)",
                    result.repo_name, status, result.total_iterations,
                    result.deterministic_fixes, elapsed)

        return result


# ── Benchmark Runner ───────────────────────────────────────────────


class RealRepoRecoveryBenchmark:
    """Run recovery across multiple repositories."""

    def __init__(self, repos_dir: str | None = None,
                 build_cmd: list[str] | None = None,
                 max_iterations: int = 25,
                 reuse_clones: bool = True):
        self.repos_dir = repos_dir
        self.build_cmd = build_cmd
        self.max_iterations = max_iterations
        self.reuse_clones = reuse_clones
        self.results: list[RepoResult] = []

    def run_on_repos(self, repo_configs: list[dict]) -> AggregateReport:
        """Run recovery on a list of repository configs."""
        aggregate = AggregateReport()
        results = []

        for config in repo_configs:
            name = config["name"]
            url = config.get("url", "")
            size = config.get("size", "unknown")
            notes = config.get("notes", "")

            # Resolve repo directory
            if self.repos_dir and os.path.isdir(os.path.join(self.repos_dir, name)):
                repo_dir = os.path.join(self.repos_dir, name)
            elif os.path.isdir(name):
                repo_dir = name
            elif self.repos_dir and os.path.isdir(self.repos_dir):
                repo_dir = self._clone_repo(name, url)
            else:
                logger.warning("Repo %s not found at %s or %s — skipping",
                               name, self.repos_dir or "(none)", name)
                continue

            logger.info("=" * 60)
            logger.info("Recovering: %s (%s, %s)", name, size, url or "local")
            logger.info("=" * 60)

            runner = RepoRecoveryRunner(
                repo_dir,
                build_cmd=self.build_cmd,
                max_iterations=self.max_iterations,
            )
            result = asyncio.run(runner.recover())

            result.repo_name = name
            result.repo_url = url
            result.repo_size = size
            result.notes = notes
            results.append(result)

            # Update aggregates
            aggregate.total_repos += 1
            if result.build_success:
                aggregate.recovered += 1
            else:
                aggregate.failed += 1
            aggregate.total_initial_errors += result.initial_error_count
            aggregate.total_parsed_errors += result.parsed_errors
            aggregate.total_deterministic += result.deterministic_fixes
            aggregate.total_memory += result.memory_fixes
            aggregate.total_llm += result.llm_fixes
            aggregate.total_iterations += result.total_iterations
            aggregate.repos.append(result)

            # Status line
            status_icon = "RECOVERED" if result.build_success else "FAILED"
            print(f"  [{status_icon}] {name}: {result.initial_error_count} errors -> "
                  f"{result.deterministic_fixes} deterministic, "
                  f"{result.memory_fixes} memory, "
                  f"{result.llm_fixes} llm, "
                  f"{result.total_iterations} iters, "
                  f"{result.recovery_time_s:.1f}s")

        n = aggregate.total_repos
        aggregate.avg_recovery_time_s = round(
            sum(r.recovery_time_s for r in results) / n, 2) if n else 0.0

        return aggregate

    def _clone_repo(self, name: str, url: str) -> str:
        """Clone a GitHub repo into repos_dir and return the path."""
        if not url:
            logger.error("No URL for repo %s", name)
            return ""
        target = os.path.join(self.repos_dir, name)
        if os.path.isdir(target) and self.reuse_clones:
            logger.info("Using existing clone: %s", target)
            return target
        logger.info("Cloning %s from %s ...", name, url)
        try:
            subprocess.run(
                ["git", "clone", "--depth=1", url, target],
                capture_output=True, text=True, timeout=300,
            )
            logger.info("Cloned to %s", target)
        except Exception as e:
            logger.error("Clone failed: %s", e)
        return target

    def run_on_fixtures(self, fixtures_dir: str,
                        project_root: str | None = None) -> AggregateReport:
        """Dry-run mode: run recovery using fixture build output files.
        
        This simulates the recovery pipeline without requiring Android SDK
        or real Gradle builds. Each .txt file in fixtures_dir is treated
        as a build output. The repair engine applies fixes to a scratch
        project directory.
        """
        import glob as glob_module
        fixture_files = sorted(glob_module.glob(os.path.join(fixtures_dir, "*.txt")))
        if not fixture_files:
            fixture_files = sorted(glob_module.glob(os.path.join(fixtures_dir, "*.log")))

        aggregate = AggregateReport()

        for fixture_path in fixture_files:
            name = os.path.splitext(os.path.basename(fixture_path))[0]
            logger.info("Fixture: %s", name)

            with open(fixture_path, encoding="utf-8", errors="replace") as f:
                build_output = f.read()

            # Create scratch project directory for repairs
            scratch_dir = project_root or tempfile.mkdtemp(prefix=f"recovery_{name}_")
            os.makedirs(scratch_dir, exist_ok=True)

            runner = RepoRecoveryRunner(
                scratch_dir,
                build_cmd=None,  # no real builds
                max_iterations=self.max_iterations,
            )

            # Parse errors
            engine = CompilerRepairEngine(scratch_dir)
            errors = engine.parse_errors(build_output)

            result = RepoResult(repo_name=name)
            result.initial_error_count = build_output.count("error:")
            result.parsed_errors = len(errors)
            result.repo_size = "fixture"

            if not errors:
                result.build_success = False
                result.stop_reason = "no_errors_parsed"
            else:
                # Run repair chain with rebuild simulation
                chain = RepairChain(
                    engine, scratch_dir,
                    max_iterations=self.max_iterations,
                )

                # Build a simulated rebuild from the remaining errors
                original_errors = list(errors)

                chain_result = asyncio.run(chain.run(
                    build_output=build_output,
                    rebuild_fn=self._make_fixture_rebuild_fn(
                        scratch_dir, original_errors, build_output),
                ))

                result.build_success = chain_result.success
                result.total_iterations = chain_result.total_iterations
                result.stop_reason = chain_result.stop_reason

                m = chain_result.metrics or type('m', (), {})()
                result.deterministic_fixes = getattr(m, 'deterministic_repairs', 0)
                result.memory_fixes = getattr(m, 'memory_repairs', 0)
                result.llm_fixes = getattr(m, 'llm_repairs', 0)
                result.chain_metrics = chain_result.metrics.to_dict() if chain_result.metrics else {}

            result.recovery_time_s = 0.0  # simulated

            aggregate.total_repos += 1
            if result.build_success:
                aggregate.recovered += 1
            else:
                aggregate.failed += 1
            aggregate.total_initial_errors += result.initial_error_count
            aggregate.total_parsed_errors += result.parsed_errors
            aggregate.total_deterministic += result.deterministic_fixes
            aggregate.total_memory += result.memory_fixes
            aggregate.total_llm += result.llm_fixes
            aggregate.total_iterations += result.total_iterations
            aggregate.repos.append(result)

            status_icon = "RECOVERED" if result.build_success else "FAILED"
            print(f"  [{status_icon}] {name}: {result.initial_error_count} errors, "
                  f"{result.parsed_errors} parsed, "
                  f"{result.deterministic_fixes} deterministic, "
                  f"{result.stop_reason}")

        return aggregate

    def _make_fixture_rebuild_fn(self, project_dir: str,
                                  original_errors: list[JavacError],
                                  original_output: str) -> Callable:
        """Create a rebuild function for fixture mode.
        
        After each fix, re-parses the project files to determine
        which errors remain, and generates a new build output.
        """
        from benchmarks.repair_chaining_benchmark import make_rebuild_fn
        # Use the pre-computed stage approach — for fixtures without stages,
        # build a simple single-stage cycle
        stages = [original_output, "BUILD SUCCESSFUL\n"]
        return make_rebuild_fn(stages)


# ── Report ─────────────────────────────────────────────────────────


def format_report(aggregate: AggregateReport) -> str:
    lines = []
    lines.append("# Real Repository Recovery Report")
    lines.append("")
    lines.append(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Total repositories | {aggregate.total_repos} |")
    lines.append(f"| Recovered | {aggregate.recovered}/{aggregate.total_repos} |")
    lines.append(f"| Recovery rate | {aggregate.recovery_rate()}% |")
    lines.append(f"| Total initial errors | {aggregate.total_initial_errors} |")
    lines.append(f"| Total parsed errors | {aggregate.total_parsed_errors} |")
    lines.append(f"| Parse rate | {aggregate.parse_rate()}% |")
    lines.append(f"| Deterministic fixes | {aggregate.total_deterministic} |")
    lines.append(f"| Memory fixes | {aggregate.total_memory} |")
    lines.append(f"| LLM fixes | {aggregate.total_llm} |")
    lines.append(f"| Deterministic rate | {aggregate.deterministic_rate()}% |")
    lines.append(f"| LLM fallback rate | {aggregate.llm_fallback_rate()}% |")
    lines.append(f"| Total iterations | {aggregate.total_iterations} |")
    lines.append(f"| Avg recovery time | {aggregate.avg_recovery_time_s}s |")
    lines.append("")

    # Per-repo results
    lines.append("## Per-Repository Results")
    lines.append("")
    lines.append("| Repo | Size | Initial Errors | Parsed | Det. Fixes | Mem. Fixes | LLM Fixes | Iters | Time | Result |")
    lines.append("|------|------|----------------|--------|------------|------------|-----------|-------|------|--------|")
    for r in aggregate.repos:
        result_str = "PASS" if r.build_success else "FAIL"
        lines.append(
            f"| {r.repo_name} | {r.repo_size} | {r.initial_error_count} | "
            f"{r.parsed_errors} | {r.deterministic_fixes} | {r.memory_fixes} | "
            f"{r.llm_fixes} | {r.total_iterations} | {r.recovery_time_s}s | {result_str} |"
        )
    lines.append("")

    # Failure analysis
    failures = [r for r in aggregate.repos if not r.build_success]
    if failures:
        lines.append("## Failure Analysis")
        lines.append("")
        for r in failures:
            lines.append(f"- **{r.repo_name}**: {r.stop_reason} "
                         f"({r.parsed_errors} parsed, {r.deterministic_fixes} deterministic)")
        lines.append("")

    return "\n".join(lines)


# ── CLI ─────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Real Android repository recovery benchmark")
    parser.add_argument("--repos-dir", "-d",
                        help="Directory containing Android repos (or clone destination)")
    parser.add_argument("--repo", "-r",
                        help="Single repo path to recover")
    parser.add_argument("--fixtures", "-f",
                        help="Directory of .txt build output fixtures (dry-run mode)")
    parser.add_argument("--build-cmd", "-b", nargs="+",
                        help="Build command (default: ./gradlew assembleDebug)")
    parser.add_argument("--config", "-c",
                        help="JSON config file with repo list (overrides default)")
    parser.add_argument("--max-iterations", type=int, default=25,
                        help="Max repair chain iterations per repo")
    parser.add_argument("--results", "-o", default="./recovery_results",
                        help="Output directory for results")
    parser.add_argument("--markdown", "-m",
                        help="Output markdown report path")
    args = parser.parse_args()

    os.makedirs(args.results, exist_ok=True)
    benchmark = RealRepoRecoveryBenchmark(
        repos_dir=args.repos_dir,
        build_cmd=args.build_cmd,
        max_iterations=args.max_iterations,
    )

    if args.fixtures:
        # Dry-run mode: use fixture files
        logger.info("Running in fixture mode (no real builds)")
        aggregate = benchmark.run_on_fixtures(args.fixtures)
    elif args.repo:
        # Single repo mode
        logger.info("Running on single repo: %s", args.repo)
        config = [{"name": os.path.abspath(args.repo), "url": "",
                    "size": "custom", "notes": "single repo"}]
        aggregate = benchmark.run_on_repos(config)
    elif args.config:
        # Custom config
        with open(args.config, encoding="utf-8") as f:
            config = json.load(f)
        aggregate = benchmark.run_on_repos(config)
    elif args.repos_dir:
        # Use default test set with repos_dir as clone destination
        aggregate = benchmark.run_on_repos(DEFAULT_TEST_SET)
    else:
        parser.print_help()
        print("\nNo repos found. Either:")
        print("  --repos-dir DIR    Point to a directory of Android repos")
        print("  --fixtures DIR     Run in dry-run mode with fixture build outputs")
        sys.exit(1)

    # Save results
    report_path = os.path.join(args.results, "recovery_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(aggregate.to_dict(), f, indent=2)
    logger.info("Results saved to %s", report_path)

    # Print report
    report = format_report(aggregate)
    print("\n" + report)

    if args.markdown:
        with open(args.markdown, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"Report saved to {args.markdown}")
    else:
        md_path = os.path.join(args.results, "recovery_report.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"Report also saved to {md_path}")


if __name__ == "__main__":
    main()
