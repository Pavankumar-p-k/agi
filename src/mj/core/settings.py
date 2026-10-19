"""Runtime limits for workers and tasks (docs/08 — timeouts and budgets).

Read from the environment on every call so an operator (or a test) can tune
them without re-importing anything. Defaults are deliberately conservative:
a hung worker must never hang the kernel, and a looping planner must never
run unbounded. These limits exist *before* any LLM joins the loop, so the
reasoner inherits them rather than escaping them.
"""

from __future__ import annotations

import os


def _float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def step_timeout_s() -> float:
    """Per-step wall-clock deadline for a worker's run() call.

    On expiry the step fails as timed out and the worker thread is abandoned
    (daemon); side effects it made before expiry are not recorded and must be
    re-observed — a timeout is an unknown outcome, never a success.
    <= 0 disables the deadline (not recommended).
    """
    return _float("MJ_STEP_TIMEOUT_S", 60.0)


def task_budget_s() -> float:
    """Per-task wall-clock budget. Checked before each step starts; when
    exhausted the remaining steps are skipped and the task fails with a
    budget error. Steps already completed keep their recorded results (and
    stay undoable). <= 0 means exhausted immediately."""
    return _float("MJ_TASK_BUDGET_S", 600.0)


def max_steps() -> int:
    """Hard cap on steps in one plan, enforced at plan validation — a plan
    over the cap is refused before anything executes. <= 0 disables."""
    return _int("MJ_MAX_STEPS", 25)


def snapshot() -> dict[str, float | int]:
    return {
        "step_timeout_s": step_timeout_s(),
        "task_budget_s": task_budget_s(),
        "max_steps": max_steps(),
    }
