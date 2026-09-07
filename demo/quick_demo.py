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

"""quick_demo.py — Self-contained demo of JARVIS core features.

Usage:
    python -m demo.quick_demo

Runs a series of module-level smoke tests:
- Imports core modules
- Checks config loads
- Tests tool system
- Verifies diagnostics
- Shows skill index
"""
from __future__ import annotations

import os
import sys
import time


def _header(text: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {text}")
    print(f"{'=' * 60}")


def _check(ok: bool, label: str) -> int:
    status = "PASS" if ok else "FAIL"
    color = "\x1b[32m" if ok else "\x1b[31m"
    reset = "\x1b[0m"
    print(f"  [{color}{status}{reset}] {label}")
    return 0 if ok else 1


def main() -> int:
    failures = 0
    print(f"JARVIS Demo — Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")

    # 1. Config loading
    _header("1. Config")
    try:
        from core.config_schema import JarvisConfig
        cfg = JarvisConfig.load()
        failures += _check(True, f"Config loaded: {cfg.__class__.__name__}")
    except Exception as e:
        failures += _check(False, f"Config failed: {e}")

    # 2. Core imports
    _header("2. Core Modules")
    for mod in ["core.agent_loop", "core.tools.execution", "core.diagnostics",
                "core.ssrf", "core.api_key_vault", "core.prompt_security",
                "core.skill_loader", "core.tools.persistent_shell"]:
        try:
            __import__(mod)
            failures += _check(True, mod)
        except Exception as e:
            failures += _check(False, f"{mod}: {e}")

    # 3. Diagnostics
    _header("3. Diagnostics")
    try:
        from core.diagnostics import build_diagnostic_report
        report = build_diagnostic_report()
        status = report.status
        total = report.counts.get("python_files", 0)
        tests = report.counts.get("tests", 0)
        deps = sum(1 for v in report.optional_dependencies.values() if v)
        failures += _check(True, f"Status: {status} — {total} py files, {tests} tests, {deps} deps found")
        for issue in report.issues[:3]:
            icon = "!" if os.name == "nt" else "\u26a0"
            print(f"    {icon}  [{issue.severity}] {issue.path}: {issue.message}")
        if len(report.issues) > 3:
            print(f"    ... and {len(report.issues) - 3} more issues")
    except Exception as e:
        failures += _check(False, f"Diagnostics failed: {e}")

    # 4. Tool system
    _header("4. Tools Available")
    try:
        from core.tools.index import BUILTIN_TOOL_DESCRIPTIONS
        count = len(BUILTIN_TOOL_DESCRIPTIONS)
        failures += _check(True, f"{count} tools registered")
        for name, desc in sorted(BUILTIN_TOOL_DESCRIPTIONS.items())[:6]:
            print(f"    - {name}: {desc[:60]}...")
        print(f"    ... and {count - 6} more")
    except Exception as e:
        failures += _check(False, f"Tool index failed: {e}")

    # 5. Skill library
    _header("5. Skills Library")
    try:
        import json
        from pathlib import Path
        skills_dir = Path(__file__).resolve().parent.parent / "skills" / "library"
        count = len(list(skills_dir.rglob("skill.json")))
        catalog = set()
        for f in skills_dir.rglob("skill.json"):
            cat = f.parent.parent.name
            catalog.add(cat)
        failures += _check(True, f"{count} skills in {len(catalog)} categories: {', '.join(sorted(catalog))}")
    except Exception as e:
        failures += _check(False, f"Skills scan failed: {e}")

    # Summary
    _header("Result")
    if failures == 0:
        print("  All checks passed — JARVIS is ready.")
    else:
        print(f"  {failures} check(s) failed. Run 'python jarvis.py doctor' for details.")
    return failures


if __name__ == "__main__":
    sys.exit(main())
