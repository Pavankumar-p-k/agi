"""Timeouts and budgets (docs/08): per-step deadline, per-task wall-clock
budget, plan step cap, and their interaction with undo.

Enforcement points:
  * MJ_STEP_TIMEOUT_S — the runner stops waiting for a worker at the deadline;
    the step fails as timed out, never as success.
  * MJ_TASK_BUDGET_S  — checked before each step starts; expired budget skips
    the step and fails the task while completed steps keep their results.
  * MJ_MAX_STEPS      — plan validation refuses oversized plans before any
    execution happens at all.
"""

from __future__ import annotations

import json
import time

import pytest

from mj.brain import planner
from mj.core import settings, tasks
from mj.executor import capabilities as caps
from mj.executor import runner


@pytest.fixture()
def store(tmp_path):
    s = __import__("mj.core.store", fromlist=["Store"]).Store.open(tmp_path)
    caps.ensure_registered(s)
    yield s
    s.close()


def _sandbox(tmp_path, name="box"):
    d = tmp_path / name
    d.mkdir()
    (d / "a.txt").write_text("t", encoding="utf-8")
    return d


# -- per-step deadline -------------------------------------------------------


def test_step_timeout_fails_fast_instead_of_hanging(store, monkeypatch):
    impl = caps.BUILTINS["os.facts"]

    def sleepy_run(store, inputs):
        time.sleep(1.5)
        return {"facts": []}

    monkeypatch.setitem(caps.BUILTINS, "os.facts", caps.Impl(impl.manifest, sleepy_run, impl.verify))
    monkeypatch.setenv("MJ_STEP_TIMEOUT_S", "0.2")
    plan = planner.build_plan(store, "disk")
    started = time.time()
    report = runner.run_plan(store, plan, auto_approve=True)
    elapsed = time.time() - started
    assert elapsed < 1.0  # returned at the deadline, did not wait out the worker
    assert report["state"] == "failed"
    assert "timed out" in report["failed_step"]["error"]
    row = store.one(
        "SELECT status FROM plan_steps WHERE task_id = ? AND step_id = 's1'",
        (report["task_id"],),
    )
    assert row["status"] == "failed"
    assert tasks.get(store, report["task_id"])["state"] == "failed"


def test_timeout_record_is_a_failure_not_a_success(store, monkeypatch):
    """A timed-out step must never be recorded as verified or reused as one."""
    impl = caps.BUILTINS["os.facts"]

    def sleepy_run(store, inputs):
        time.sleep(1.2)
        return {"facts": [{"label": "verified"}]}

    monkeypatch.setitem(caps.BUILTINS, "os.facts", caps.Impl(impl.manifest, sleepy_run, impl.verify))
    monkeypatch.setenv("MJ_STEP_TIMEOUT_S", "0.1")
    report = runner.run_plan(store, planner.build_plan(store, "disk"), auto_approve=True)
    assert report["state"] == "failed"
    assert report["verified_steps"] == 0
    rows = store.query(
        "SELECT verified, output_json FROM step_results WHERE task_id = ?",
        (report["task_id"],),
    )
    assert rows and all(r["verified"] == 0 for r in rows)
    assert all("timed out" in json.loads(r["output_json"]).get("error", "") for r in rows)


# -- per-task budget ---------------------------------------------------------


def test_zero_task_budget_never_starts_a_step(store, tmp_path, monkeypatch):
    monkeypatch.setenv("MJ_TASK_BUDGET_S", "0")
    sandbox = _sandbox(tmp_path)
    plan = planner.build_plan(store, "organize files", {"dir": str(sandbox), "commit": True})
    report = runner.run_plan(store, plan, auto_approve=True)
    assert report["state"] == "failed"
    assert "budget" in report["failed_step"]["error"]
    assert report["steps"] == []  # nothing executed
    assert store.query(
        "SELECT idempotency_key FROM step_results WHERE task_id = ?", (report["task_id"],)
    ) == []
    assert (sandbox / "a.txt").is_file()  # the world was never touched


def test_budget_exhausted_mid_plan_keeps_completed_results(store, tmp_path, monkeypatch):
    monkeypatch.setenv("MJ_TASK_BUDGET_S", "0.6")
    impl = caps.BUILTINS["files.list"]

    def slow_list(store, inputs):
        time.sleep(1.0)  # consumes the whole budget on step 1
        return impl.run(store, inputs)

    monkeypatch.setitem(caps.BUILTINS, "files.list", caps.Impl(impl.manifest, slow_list, impl.verify))
    sandbox = _sandbox(tmp_path, "midbudget")
    plan = planner.build_plan(store, "organize files", {"dir": str(sandbox), "commit": True})
    report = runner.run_plan(store, plan, auto_approve=True)
    assert report["state"] == "failed"
    assert "budget" in report["failed_step"]["error"]
    assert report["failed_step"]["step_id"] == "s2"  # refused before it started
    s1 = [r for r in report["steps"] if r["step_id"] == "s1"]
    assert s1 and s1[0]["verified"] is True  # completed work is kept and verified
    # the R2 move never happened because the budget expired first
    assert (sandbox / "a.txt").is_file()
    assert "documents" not in {p.name for p in sandbox.iterdir()}


# -- plan step cap -----------------------------------------------------------


def test_plan_over_step_cap_is_refused(store, monkeypatch):
    monkeypatch.setenv("MJ_MAX_STEPS", "1")
    with pytest.raises(planner.PlanValidationError, match="cap"):
        planner.build_plan(store, "organize files", {"dir": "."})
    # cap disabled with <= 0 still validates (documented in settings)
    monkeypatch.setenv("MJ_MAX_STEPS", "0")
    planner.build_plan(store, "organize files", {"dir": "."})


# -- interaction with undo ---------------------------------------------------


def test_timeouts_do_not_poison_undo_of_completed_tasks(store, tmp_path, monkeypatch):
    """Expiry semantics: limits bound *execution*, never recorded history.
    A later task dying to a timeout leaves a completed task's undo record
    fully usable — undo reads step_results, which expiry never mutates."""
    sandbox = _sandbox(tmp_path, "undoable")
    plan = planner.build_plan(store, "organize files", {"dir": str(sandbox), "commit": True})
    report = runner.run_plan(store, plan, auto_approve=True)
    assert report["state"] == "done"

    # a separate task dies to the step deadline
    monkeypatch.setenv("MJ_STEP_TIMEOUT_S", "0.2")
    facts_impl = caps.BUILTINS["os.facts"]

    def sleepy_run(store, inputs):
        time.sleep(1.0)
        return {"facts": []}

    monkeypatch.setitem(caps.BUILTINS, "os.facts", caps.Impl(facts_impl.manifest, sleepy_run, facts_impl.verify))
    dead = runner.run_plan(store, planner.build_plan(store, "disk"), auto_approve=True)
    assert dead["state"] == "failed"
    assert "timed out" in dead["failed_step"]["error"]

    # undo of the first task still restores its files from the recorded output
    row = store.one(
        "SELECT output_json FROM step_results WHERE task_id = ? AND step_id = 's2'",
        (report["task_id"],),
    )
    output = json.loads(row["output_json"])
    out = caps.undo_organize(store, {"path": str(sandbox)}, output)
    assert sorted(out["undone"]) == ["a.txt"]
    assert (sandbox / "a.txt").is_file()
    assert "documents" not in {p.name for p in sandbox.iterdir()}


def test_settings_snapshot_reflects_environment(monkeypatch):
    monkeypatch.setenv("MJ_STEP_TIMEOUT_S", "1.5")
    monkeypatch.setenv("MJ_TASK_BUDGET_S", "9")
    monkeypatch.setenv("MJ_MAX_STEPS", "3")
    snap = settings.snapshot()
    assert snap == {"step_timeout_s": 1.5, "task_budget_s": 9.0, "max_steps": 3}
    # garbage falls back to the default instead of raising
    monkeypatch.setenv("MJ_TASK_BUDGET_S", "not-a-number")
    assert settings.task_budget_s() == 600.0
