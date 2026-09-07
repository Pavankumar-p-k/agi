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

"""benchmark.py — Quick performance benchmark for core JARVIS modules.

Measures import time, module load speed, and diagnostic throughput.
Results in milliseconds for comparison across runs.

Usage:
    python -m demo.benchmark
    python -m demo.benchmark --json
"""
from __future__ import annotations

import argparse
import json
import time
import sys


def _ms() -> float:
    return time.perf_counter() * 1000


def main() -> int:
    parser = argparse.ArgumentParser(description="JARVIS benchmark")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()
    results: dict[str, float] = {}
    output = {}

    # Module import benchmarks
    modules = [
        "core.config_schema",
        "core.diagnostics",
        "core.ssrf",
        "core.api_key_vault",
        "core.prompt_security",
        "core.tools.execution",
        "core.tools.persistent_shell",
        "core.skill_loader",
    ]

    for mod_name in modules:
        start = _ms()
        try:
            __import__(mod_name)
            elapsed = _ms() - start
            results[mod_name] = round(elapsed, 2)
        except Exception as e:
            elapsed = _ms() - start
            results[mod_name] = -1

    if not args.json:
        print(f"{'Module':<35} {'Time (ms)':<10}")
        print("-" * 45)
        for mod, t in sorted(results.items(), key=lambda x: x[1], reverse=True):
            label = f"{'FAIL' if t < 0 else 'OK'}"
            print(f"  {mod:<33} {t:<8.1f} {label}")

    # Skill library scan
    from pathlib import Path
    skills_dir = Path(__file__).resolve().parent.parent / "skills" / "library"
    start = _ms()
    skill_count = len(list(skills_dir.rglob("skill.json")))
    scan_time = _ms() - start
    results["skills.library_scan"] = round(scan_time, 2)

    if not args.json:
        print(f"\n  {'Skill library scan':<33} {scan_time:<8.1f} ms ({skill_count} skills)")

    # Totals
    total = sum(v for v in results.values() if v > 0)
    output = {
        "results": results,
        "total_ms": round(total, 2),
        "skill_count": skill_count,
    }

    if args.json:
        print(json.dumps(output, indent=2))
    else:
        print(f"\n  Total: {total:.1f} ms")

    return 0


if __name__ == "__main__":
    sys.exit(main())
