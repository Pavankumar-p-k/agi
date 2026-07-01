"""Profile import of core.main by tracing every sub-module import."""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

t0 = time.perf_counter()

# 1. Approximate stage markers
stages = {}


def mark(name: str) -> None:
    stages[name] = (time.perf_counter() - t0) * 1000


# Trace imports by hooking __import__
_original_import = __builtins__.__import__
_import_times: dict[str, float] = {}
_import_order: list[str] = []


def _hooked_import(name, *args, **kwargs):
    t = time.perf_counter()
    result = _original_import(name, *args, **kwargs)
    elapsed = (time.perf_counter() - t) * 1000
    if elapsed > 50:  # only log slow imports (>50ms)
        _import_times[name] = elapsed
        _import_order.append(name)
    return result


__builtins__.__import__ = _hooked_import

# Now import core.main
from core import main  # noqa: E402

total = (time.perf_counter() - t0) * 1000

__builtins__.__import__ = _original_import

print(f"\n{'='*60}")
print(f"{'core.main Import Profile':^60}")
print(f"{'='*60}")
print(f"{'Module':<50} {'Time (ms)':>10}")
print(f"{'-'*60}")
for mod in _import_order:
    t = _import_times[mod]
    bar = "█" * max(1, int(t / 50))
    print(f"{mod:<50} {t:>8.1f}ms  {bar}")
print(f"{'-'*60}")
print(f"{'TOTAL (core.main)':<50} {total:>8.0f}ms")
print()

if _import_order:
    print(f"\nTop 5 slowest imports:")
    for mod, t in sorted(_import_times.items(), key=lambda x: -x[1])[:5]:
        print(f"  {t:>8.1f}ms  {mod}")
