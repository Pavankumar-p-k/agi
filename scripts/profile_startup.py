"""Profile JARVIS startup time by import stage.

Usage: python scripts/profile_startup.py
"""

from __future__ import annotations

import time
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

stages: list[tuple[str, float]] = []
t0 = time.perf_counter()


def mark(name: str) -> None:
    stages.append((name, time.perf_counter() - t0))


mark("python startup")

# Stage 1: core imports (non-heavy)
import cli_commands  # noqa: E402

mark("cli_commands")

import cli_helpers  # noqa: E402

mark("cli_helpers")

import cli_requests  # noqa: E402

mark("cli_requests")

import cli_server  # noqa: E402

mark("cli_server")

import cli_state  # noqa: E402

mark("cli_state")

# Stage 2: heavy core modules
import core.version  # noqa: E402

mark("core.version")

import core.main  # noqa: E402

mark("core.main")

# Stage 3: activity / workflow
from core.activity.storage import ActivityStore  # noqa: E402

mark("core.activity.storage")

from core.activity.manager import ActivityManager  # noqa: E402

mark("core.activity.manager")

# Stage 4: provider imports
from core.model_providers.ollama import OllamaProvider  # noqa: E402

mark("core.model_providers.ollama")

from core.tools.execution import execute_tool_block  # noqa: E402

mark("core.tools.execution")

# Stage 5: web / UI
import cli_visuals  # noqa: E402

mark("cli_visuals")

# Stage 6: setup engine (runs during first_run check)
from core.setup.engine import SetupEngine  # noqa: E402

mark("core.setup.engine")

# Stage 7: database init
store = ActivityStore(db_path=":memory:")

mark("activity store init (in-memory)")

t_total = time.perf_counter() - t0

print(f"\n{'='*55}")
print(f"{'Startup Profile':^55}")
print(f"{'='*55}")
print(f"{'Stage':<40} {'Delta':>8} {'Cumulative':>8}")
print(f"{'-'*55}")
prev = 0.0
for name, t in stages:
    delta = t - prev
    print(f"{name:<40} {delta*1000:>7.1f}ms {t*1000:>7.1f}ms")
    prev = t
print(f"{'-'*55}")
print(f"{'TOTAL':<40} {t_total*1000:>7.1f}ms {'':>8}")
print()

# Identify top 3 slowest stages
stage_deltas = [(stages[i][0], stages[i][1] - (stages[i-1][1] if i > 0 else 0)) for i in range(len(stages))]
stage_deltas.sort(key=lambda x: -x[1])
print("Top 3 slowest stages:")
for name, delta in stage_deltas[:3]:
    print(f"  {delta*1000:>7.1f}ms  {name}")
