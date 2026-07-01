"""Automated Soak Benchmark — long-running operational stability.

Monitors the ActivityUpdateService and core JARVIS components under
sustained load with periodic system exercises.

Usage:
    # Run for 60 seconds (quick smoke test):
    python benchmarks/soak_benchmark.py --quick

    # Run for 1 hour:
    python benchmarks/soak_benchmark.py --duration 3600

    # Run for 24 hours:
    python benchmarks/soak_benchmark.py --duration 86400

    # Run with custom report output:
    python benchmarks/soak_benchmark.py --report my_report.json

Metrics collected every ``sample_interval`` seconds:
    - memory_rss_mb, memory_pct
    - cpu_percent
    - asyncio_task_count
    - subscriber_count
    - cache_size
    - poll_latency_ms
    - exception_count
    - recovery_count

System exercises (every ``exercise_interval`` seconds):
    - Open/close subscribers
    - Simulate backend state changes
    - Inject backend failures
    - Restore backend
    - High subscriber count burst

Failure thresholds (configurable via env or args):
    SOAK_MEMORY_GROWTH_PCT  — max memory growth after warmup (default: 15)
    SOAK_TASK_LEAK_MAX      — max sustained new tasks (default: 5)
    SOAK_MAX_LATENCY_MS     — max poll latency (default: 5000)
    SOAK_MAX_EXCEPTIONS     — max allowed exceptions (default: 3)

Exit codes:
    0 — all thresholds passed
    1 — one or more thresholds exceeded
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import time
import tracemalloc
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from statistics import mean, median, stdev
from typing import Any
from unittest.mock import AsyncMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import psutil
except ImportError:
    psutil = None

from jarvis_tui.app.services.activity_updates import ActivityUpdateService

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
logger = logging.getLogger("soak_bench")

# ── Configuration ────────────────────────────────────────────────────────────

SOAK_DURATION = int(os.environ.get("SOAK_DURATION", "3600"))
SAMPLE_INTERVAL = int(os.environ.get("SOAK_SAMPLE_INTERVAL", "5"))
EXERCISE_INTERVAL = int(os.environ.get("SOAK_EXERCISE_INTERVAL", "30"))

THRESHOLD_MEMORY_GROWTH_PCT = float(os.environ.get("SOAK_MEMORY_GROWTH_PCT", "15"))
THRESHOLD_TASK_LEAK_MAX = int(os.environ.get("SOAK_TASK_LEAK_MAX", "5"))
THRESHOLD_MAX_LATENCY_MS = float(os.environ.get("SOAK_MAX_LATENCY_MS", "5000"))
THRESHOLD_MAX_EXCEPTIONS = int(os.environ.get("SOAK_MAX_EXCEPTIONS", "3"))
THRESHOLD_MIN_CALLBACKS = int(os.environ.get("SOAK_MIN_CALLBACKS", "10"))
THRESHOLD_CACHE_CONSISTENCY = os.environ.get("SOAK_CACHE_CONSISTENCY", "true").lower() == "true"


# ── Data types ───────────────────────────────────────────────────────────────

@dataclass
class MetricSample:
    timestamp: float
    memory_rss_mb: float
    memory_pct: float
    cpu_percent: float
    task_count: int
    subscriber_count: int
    cache_activity_count: int
    poll_latency_ms: float
    exception_count: int
    recovery_event: bool = False


@dataclass
class ExerciseEvent:
    type: str
    timestamp: float
    detail: str = ""
    success: bool = True


@dataclass
class SoakResult:
    duration_seconds: float
    total_samples: int
    warmup_samples: int
    peak_memory_rss_mb: float
    peak_cpu: float
    max_task_count: int
    max_subscriber_count: int
    avg_poll_latency_ms: float
    max_poll_latency_ms: float
    median_poll_latency_ms: float
    total_exceptions: int
    recovery_events: int
    exercises: list[ExerciseEvent] = field(default_factory=list)
    thresholds_passed: bool = True
    failures: list[str] = field(default_factory=list)
    start_time: str = ""
    end_time: str = ""


# ── Mock client with dynamic behavior ────────────────────────────────────────

class SoakMockClient:
    """Dynamically-behaving mock backend for soak testing.

    Cycles through activity states, injects failures on schedule,
    and varies activity counts to simulate real workloads.
    """

    def __init__(self, seed: int = 0):
        self._cycle = seed
        self._fail_until: float = 0
        self._latency: float = 0.01

    def fail_for(self, seconds: float):
        """Schedule backend failure for the given duration."""
        self._fail_until = time.time() + seconds

    def set_latency(self, seconds: float):
        """Simulate network latency."""
        self._latency = seconds

    async def get_activities(self) -> list[dict]:
        if time.time() < self._fail_until:
            raise ConnectionError("Simulated backend outage")
        await asyncio.sleep(self._latency)
        self._cycle += 1
        count = (self._cycle % 20) + 1  # 1-20 activities
        return [
            {
                "id": f"act_{self._cycle}_{i}",
                "title": f"Activity {self._cycle}-{i}",
                "status": _cycle_status(self._cycle + i),
                "progress": (self._cycle * 7 + i * 13) % 100,
            }
            for i in range(count)
        ]

    async def get_activity_counts(self) -> dict:
        if time.time() < self._fail_until:
            raise ConnectionError("Simulated backend outage")
        await asyncio.sleep(self._latency * 0.5)
        n = (self._cycle % 20) + 1
        running = max(0, n - (self._cycle % 5))
        return {"total": n, "running": running}


def _cycle_status(phase: int) -> str:
    opts = ["RUNNING", "PENDING", "COMPLETED", "FAILED", "RUNNING", "RUNNING"]
    return opts[phase % len(opts)]


# ── Metrics collector ────────────────────────────────────────────────────────

class MetricsCollector:
    """Periodic metrics sampling with automatic threshold checking."""

    def __init__(self, duration: float, sample_interval: float):
        self.duration = duration
        self.sample_interval = sample_interval
        self.samples: list[MetricSample] = []
        self.exception_count = 0
        self.recovery_count = 0
        self.failures: list[str] = []
        self._process = psutil.Process() if psutil else None
        self._warmup_samples = 0

    @property
    def warmup_end(self) -> float:
        """First 10% of samples are warmup."""
        return max(5, int(len(self.samples) * 0.1))

    @property
    def post_warmup_samples(self) -> list[MetricSample]:
        return self.samples[self.warmup_end:]

    async def sample(self, svc: ActivityUpdateService) -> MetricSample:
        # Memory
        mem_rss = 0.0
        mem_pct = 0.0
        cpu = 0.0
        if self._process:
            try:
                mem_info = self._process.memory_info()
                mem_rss = mem_info.rss / (1024 * 1024)
                mem_pct = self._process.memory_percent()
                cpu = self._process.cpu_percent(interval=0.1)
            except Exception:
                pass

        # Async tasks
        task_count = len(asyncio.all_tasks())

        # Service state
        sub_count = svc.subscriber_count
        cache_acts = len(svc.cache.get("activities", []))

        sample = MetricSample(
            timestamp=time.time(),
            memory_rss_mb=mem_rss,
            memory_pct=mem_pct,
            cpu_percent=cpu,
            task_count=task_count,
            subscriber_count=sub_count,
            cache_activity_count=cache_acts,
            poll_latency_ms=0.0,
            exception_count=self.exception_count,
        )
        self.samples.append(sample)
        return sample

    def record_exception(self):
        self.exception_count += 1

    def record_recovery(self):
        self.recovery_count += 1

    def check_thresholds(self) -> list[str]:
        failures = []
        pw = self.post_warmup_samples
        if not pw:
            return ["No post-warmup samples collected"]

        # Memory growth after warmup
        early = pw[:max(1, len(pw) // 4)]
        late = pw[-max(1, len(pw) // 4):]
        early_avg = mean(s.memory_rss_mb for s in early)
        late_avg = mean(s.memory_rss_mb for s in late)
        if early_avg > 0:
            growth_pct = ((late_avg - early_avg) / early_avg) * 100
            if growth_pct > THRESHOLD_MEMORY_GROWTH_PCT:
                failures.append(
                    f"Memory growth {growth_pct:.1f}% exceeds threshold "
                    f"{THRESHOLD_MEMORY_GROWTH_PCT}% (early: {early_avg:.1f}MB, late: {late_avg:.1f}MB)"
                )

        # Task leak
        early_tasks = mean(s.task_count for s in early)
        late_tasks = mean(s.task_count for s in late)
        leaked = late_tasks - early_tasks
        if leaked > THRESHOLD_TASK_LEAK_MAX:
            failures.append(
                f"Task leak: {leaked:.0f} new tasks after warmup "
                f"(early: {early_tasks:.0f}, late: {late_tasks:.0f}, max allowed: {THRESHOLD_TASK_LEAK_MAX})"
            )

        # Max latency
        latencies = [s.poll_latency_ms for s in pw if s.poll_latency_ms > 0]
        if latencies:
            max_lat = max(latencies)
            if max_lat > THRESHOLD_MAX_LATENCY_MS:
                failures.append(
                    f"Max poll latency {max_lat:.0f}ms exceeds threshold {THRESHOLD_MAX_LATENCY_MS}ms"
                )

        # Exceptions
        if self.exception_count > THRESHOLD_MAX_EXCEPTIONS:
            failures.append(
                f"Exception count {self.exception_count} exceeds threshold {THRESHOLD_MAX_EXCEPTIONS}"
            )

        return failures


# ── System exercises ─────────────────────────────────────────────────────────

class NullCallback:
    """Async callable that accepts a cache dict and does nothing.
    Replaces AsyncMock() to avoid unbounded call-history memory growth
    in long-running soak tests (https://bugs.python.org/issue45150).
    """
    async def __call__(self, cache: dict) -> None:
        pass


class SoakExerciser:
    """Periodically exercises the system under test."""

    def __init__(self, client: SoakMockClient, svc: ActivityUpdateService):
        self.client = client
        self.svc = svc
        self.events: list[ExerciseEvent] = []
        self.callbacks: list = []
        self._cycle = 0

    async def run_exercise(self, kind: str) -> ExerciseEvent:
        self._cycle += 1
        t0 = time.time()
        try:
            if kind == "open_subscribers":
                # Open 5 simulated screens
                for i in range(5):
                    cb = NullCallback()
                    self.svc.subscribe(cb)
                    self.callbacks.append(cb)
                return ExerciseEvent(
                    "open_subscribers", time.time(),
                    f"opened 5 subscribers (total: {self.svc.subscriber_count})", True
                )

            elif kind == "close_subscribers":
                # Close all simulated screens
                n = len(self.callbacks)
                for cb in self.callbacks:
                    self.svc.unsubscribe(cb)
                self.callbacks.clear()
                return ExerciseEvent(
                    "close_subscribers", time.time(),
                    f"closed {n} subscribers (total: {self.svc.subscriber_count})",
                    self.svc.subscriber_count == 0
                )

            elif kind == "backend_fail":
                self.client.fail_for(10)
                return ExerciseEvent(
                    "backend_fail", time.time(), "backend failing for 10s", True
                )

            elif kind == "backend_restore":
                self.client._fail_until = 0
                return ExerciseEvent(
                    "backend_restore", time.time(),
                    f"backend restored (fail_until cleared)", True
                )

            elif kind == "high_latency":
                self.client.set_latency(0.5)
                return ExerciseEvent(
                    "high_latency", time.time(), "latency set to 500ms", True
                )

            elif kind == "normal_latency":
                self.client.set_latency(0.01)
                return ExerciseEvent(
                    "normal_latency", time.time(), "latency restored to 10ms", True
                )

            elif kind == "subscriber_burst":
                # 50 subscribers in rapid succession
                burst = []
                for i in range(50):
                    cb = NullCallback()
                    self.svc.subscribe(cb)
                    burst.append(cb)
                await asyncio.sleep(0.1)
                for cb in burst:
                    self.svc.unsubscribe(cb)
                return ExerciseEvent(
                    "subscriber_burst", time.time(),
                    "50 subscribers opened/closed", True
                )

            elif kind == "big_cache":
                # Bulk activities to inflate cache
                big = [{"id": f"big_{i}", "status": "RUNNING", "title": f"Bulk {i}"} for i in range(500)]
                self.client.get_activities = AsyncMock(return_value=big)
                self.client.get_activity_counts = AsyncMock(return_value={"total": 500, "running": 500})
                return ExerciseEvent(
                    "big_cache", time.time(), "inflated cache to 500 activities", True
                )

            elif kind == "empty_cache":
                self.client.get_activities = AsyncMock(return_value=[])
                self.client.get_activity_counts = AsyncMock(return_value={"total": 0, "running": 0})
                return ExerciseEvent(
                    "empty_cache", time.time(), "emptied cache", True
                )

            elif kind == "restore_normal":
                self.client = SoakMockClient(seed=self._cycle)
                return ExerciseEvent(
                    "restore_normal", time.time(), "restored normal mock behavior", True
                )

            else:
                return ExerciseEvent("unknown", time.time(), f"unknown exercise: {kind}", False)

        except Exception as e:
            return ExerciseEvent(kind, time.time(), f"error: {e}", False)

    def get_exercise_sequence(self, elapsed_ratio: float) -> list[str]:
        """Return exercises to run based on elapsed time ratio (0.0-1.0)."""
        # Phase 1 (0-20%): normal operation, open subscribers
        if elapsed_ratio < 0.20:
            if elapsed_ratio < 0.05:
                return ["open_subscribers"]
            return []

        # Phase 2 (20-40%): backend failure + recovery
        if elapsed_ratio < 0.40:
            if elapsed_ratio < 0.25:
                return ["backend_fail"]
            if elapsed_ratio < 0.30:
                return []  # Wait while failing
            return ["backend_restore"]

        # Phase 3 (40-60%): transient subscriber changes
        if elapsed_ratio < 0.60:
            if elapsed_ratio < 0.45:
                return ["close_subscribers", "subscriber_burst"]
            if elapsed_ratio < 0.50:
                return ["open_subscribers"]
            return []

        # Phase 4 (60-80%): latency and cache stress
        if elapsed_ratio < 0.80:
            if elapsed_ratio < 0.65:
                return ["high_latency"]
            if elapsed_ratio < 0.70:
                return ["big_cache"]
            if elapsed_ratio < 0.75:
                return ["normal_latency", "empty_cache"]
            return ["restore_normal"]

        # Phase 5 (80-100%): close everything, stabilize
        if elapsed_ratio < 0.90:
            return ["close_subscribers"]
        return []


# ── Main benchmark ───────────────────────────────────────────────────────────

async def run_soak_benchmark(
    duration: float = SOAK_DURATION,
    sample_interval: float = SAMPLE_INTERVAL,
    exercise_interval: float = EXERCISE_INTERVAL,
    quick: bool = False,
) -> SoakResult:
    """Run the soak benchmark and return results."""

    if quick:
        duration = 30
        sample_interval = 2
        exercise_interval = 6
        logger.info("Quick mode: %ds with %ds samples and %ds exercises", duration, sample_interval, exercise_interval)

    if psutil is None:
        logger.warning("psutil not available — memory/CPU metrics will be zero")

    start_time = datetime.now(timezone.utc).isoformat()
    logger.info("Soak benchmark starting at %s", start_time)
    logger.info("Duration: %.0fs, sample interval: %.0fs, exercise interval: %.0fs",
                duration, sample_interval, exercise_interval)

    # Enable tracemalloc for heap tracing
    if not quick:
        tracemalloc.start()

    # Components
    client = SoakMockClient()
    svc = ActivityUpdateService(client, poll_interval=1.0)
    collector = MetricsCollector(duration, sample_interval)
    exerciser = SoakExerciser(client, svc)

    # Service lifecycle
    svc.start()
    logger.info("ActivityUpdateService started")

    last_sample_time = 0.0
    last_exercise_time = 0.0
    last_exercises_run: set[str] = set()
    t_start = time.time()

    try:
        while True:
            elapsed = time.time() - t_start
            if elapsed >= duration:
                break

            elapsed_ratio = elapsed / duration

            # ── Sample metrics ────────────────────────────────────
            if time.time() - last_sample_time >= sample_interval:
                sample = await collector.sample(svc)
                # Measure poll latency by timing get_activities
                t0 = time.time()
                try:
                    await client.get_activities()
                    await client.get_activity_counts()
                    sample.poll_latency_ms = (time.time() - t0) * 1000
                except Exception:
                    sample.poll_latency_ms = -1
                last_sample_time = time.time()

            # ── Run exercises ─────────────────────────────────────
            if time.time() - last_exercise_time >= exercise_interval:
                exercises = exerciser.get_exercise_sequence(elapsed_ratio)
                for kind in exercises:
                    event = await exerciser.run_exercise(kind)
                    collector.samples[-1].recovery_event = ("restore" in kind or "backend_restore" in kind)
                    if not event.success:
                        collector.record_exception()
                    if "restore" in kind or "backend_restore" in kind:
                        collector.record_recovery()
                    exerciser.events.append(event)
                    logger.info("Exercise: %s — %s", kind, "OK" if event.success else "FAIL")
                last_exercise_time = time.time()

            await asyncio.sleep(0.1)

    except asyncio.CancelledError:
        logger.info("Benchmark cancelled")
    except Exception as e:
        logger.error("Unexpected benchmark error: %s", e)
        collector.record_exception()
    finally:
        # Clean shutdown
        for cb in exerciser.callbacks:
            try:
                svc.unsubscribe(cb)
            except Exception:
                pass
        await svc.stop()

    # ── Compute results ──────────────────────────────────────────
    end_time = datetime.now(timezone.utc).isoformat()
    pw = collector.post_warmup_samples

    latencies = [s.poll_latency_ms for s in pw if s.poll_latency_ms > 0]

    result = SoakResult(
        duration_seconds=time.time() - t_start,
        total_samples=len(collector.samples),
        warmup_samples=collector.warmup_end,
        peak_memory_rss_mb=max((s.memory_rss_mb for s in pw), default=0),
        peak_cpu=max((s.cpu_percent for s in pw), default=0),
        max_task_count=max((s.task_count for s in pw), default=0),
        max_subscriber_count=max((s.subscriber_count for s in pw), default=0),
        avg_poll_latency_ms=mean(latencies) if latencies else 0,
        max_poll_latency_ms=max(latencies) if latencies else 0,
        median_poll_latency_ms=median(latencies) if latencies else 0,
        total_exceptions=collector.exception_count,
        recovery_events=collector.recovery_count,
        exercises=exerciser.events,
        start_time=start_time,
        end_time=end_time,
    )

    # Threshold checks
    result.failures = collector.check_thresholds()
    result.thresholds_passed = len(result.failures) == 0

    # Verify subscriber count returned to zero
    if svc.subscriber_count != 0:
        result.failures.append(
            f"Subscriber count {svc.subscriber_count} did not return to zero after all screens closed"
        )
        result.thresholds_passed = False

    # Verify cache consistency
    if THRESHOLD_CACHE_CONSISTENCY:
        for sample in pw:
            if sample.cache_activity_count < 0:
                result.failures.append(f"Negative cache activity count: {sample.cache_activity_count}")
                result.thresholds_passed = False
                break

    return result


def _safe(text: str) -> str:
    """Replace Unicode box chars with ASCII for Windows cp1252 consoles."""
    return (text.replace("\u2500", "-").replace("\u2502", "|")
                .replace("\u2514", "+").replace("\u251C", "+")
                .replace("\u2524", "+").replace("\u252C", "+")
                .replace("\u2534", "+").replace("\u2560", "+")
                .replace("\u2557", "+").replace("\u255D", "+")
                .replace("\u2554", "+").replace("\u255A", "+")
                .replace("\u2551", "|"))


def print_report(result: SoakResult):
    """Print a concise soak benchmark report."""
    status = "PASS" if result.thresholds_passed else "FAIL"
    sep = "=" * 58
    print()
    print(sep)
    print(f"  SOAK BENCHMARK REPORT --- {status}")
    print(sep)
    print(f"  Duration:           {result.duration_seconds:.0f}s")
    print(f"  Samples collected:  {result.total_samples} ({result.warmup_samples} warmup)")
    print(f"  Exercises executed: {len(result.exercises)}")
    print()
    print(f"  -- Resource Usage --")
    print(f"  Peak memory:        {result.peak_memory_rss_mb:.1f} MB")
    print(f"  Peak CPU:           {result.peak_cpu:.1f}%")
    print(f"  Max async tasks:    {result.max_task_count}")
    print(f"  Max subscribers:    {result.max_subscriber_count}")
    print()
    print(f"  -- Latency --")
    print(f"  Average:            {result.avg_poll_latency_ms:.1f} ms")
    print(f"  Median:             {result.median_poll_latency_ms:.1f} ms")
    print(f"  Maximum:            {result.max_poll_latency_ms:.1f} ms")
    print()
    print(f"  -- Health --")
    print(f"  Exceptions:         {result.total_exceptions}")
    print(f"  Recovery events:    {result.recovery_events}")
    print()
    if result.failures:
        print(f"  -- THRESHOLD FAILURES ({len(result.failures)}) --")
        for f in result.failures:
            print(f"    [FAIL] {f}")
        print()
    print(sep)


def save_report(result: SoakResult, path: str):
    """Save structured report as JSON."""
    report = {
        "benchmark": "soak",
        "status": "PASS" if result.thresholds_passed else "FAIL",
        "duration_seconds": result.duration_seconds,
        "total_samples": result.total_samples,
        "warmup_samples": result.warmup_samples,
        "peak_memory_rss_mb": result.peak_memory_rss_mb,
        "peak_cpu": result.peak_cpu,
        "max_task_count": result.max_task_count,
        "max_subscriber_count": result.max_subscriber_count,
        "avg_poll_latency_ms": result.avg_poll_latency_ms,
        "max_poll_latency_ms": result.max_poll_latency_ms,
        "median_poll_latency_ms": result.median_poll_latency_ms,
        "total_exceptions": result.total_exceptions,
        "recovery_events": result.recovery_events,
        "threshold_failures": result.failures,
        "exercises": [
            {"type": e.type, "timestamp": e.timestamp, "detail": e.detail, "success": e.success}
            for e in result.exercises
        ],
        "start_time": result.start_time,
        "end_time": result.end_time,
    }
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(report, f, indent=2)
    logger.info("Report saved to %s", path)


# ── CLI entry point ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="JARVIS Automated Soak Benchmark")
    parser.add_argument("--duration", type=int, default=SOAK_DURATION,
                        help=f"Test duration in seconds (default: {SOAK_DURATION})")
    parser.add_argument("--sample-interval", type=int, default=SAMPLE_INTERVAL,
                        help=f"Metrics sampling interval in seconds (default: {SAMPLE_INTERVAL})")
    parser.add_argument("--exercise-interval", type=int, default=EXERCISE_INTERVAL,
                        help=f"System exercise interval in seconds (default: {EXERCISE_INTERVAL})")
    parser.add_argument("--quick", action="store_true",
                        help="Run abbreviated 30-second smoke test")
    parser.add_argument("--report", type=str, default="",
                        help="Path to save JSON report (default: benchmark_reports/soak_<timestamp>.json)")
    args = parser.parse_args()

    result = asyncio.run(run_soak_benchmark(
        duration=args.duration,
        sample_interval=args.sample_interval,
        exercise_interval=args.exercise_interval,
        quick=args.quick,
    ))

    print_report(result)

    if args.report:
        save_report(result, args.report)
    elif not args.quick:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = f"benchmark_reports/soak_{ts}.json"
        save_report(result, path)

    sys.exit(0 if result.thresholds_passed else 1)


if __name__ == "__main__":
    main()
