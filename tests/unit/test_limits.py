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


def test_step_timeout_fails_fast_instead_of_hanging(store, override_run, monkeypatch):
    override_run(
        "os.facts",
        "import time\n"
        "def run(store, inputs):\n"
        "    time.sleep(1.5)\n"
        "    return {'facts': []}\n",
    )
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


def test_timeout_record_is_a_failure_not_a_success(store, override_run, monkeypatch):
    """A timed-out step must never be recorded as verified or reused as one."""
    override_run(
        "os.facts",
        "import time\n"
        "def run(store, inputs):\n"
        "    time.sleep(1.2)\n"
        "    return {'facts': [{'label': 'verified'}]}\n",
    )
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


def test_budget_exhausted_mid_plan_keeps_completed_results(store, tmp_path, override_run, monkeypatch):
    monkeypatch.setenv("MJ_TASK_BUDGET_S", "0.6")
    # step 1 consumes the whole budget before it produces anything
    override_run(
        "files.list",
        "import time\n"
        "from mj.executor.capabilities import BUILTINS\n"
        "def run(store, inputs):\n"
        "    time.sleep(1.0)\n"
        "    return BUILTINS['files.list'].run(store, inputs)\n",
    )
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


def test_timeouts_do_not_poison_undo_of_completed_tasks(store, tmp_path, override_run, monkeypatch):
    """Expiry semantics: limits bound *execution*, never recorded history.
    A later task dying to a timeout leaves a completed task's undo record
    fully usable — undo reads step_results, which expiry never mutates."""
    sandbox = _sandbox(tmp_path, "undoable")
    plan = planner.build_plan(store, "organize files", {"dir": str(sandbox), "commit": True})
    report = runner.run_plan(store, plan, auto_approve=True)
    assert report["state"] == "done"

    # a separate task dies to the step deadline
    monkeypatch.setenv("MJ_STEP_TIMEOUT_S", "0.2")
    override_run(
        "os.facts",
        "import time\n"
        "def run(store, inputs):\n"
        "    time.sleep(1.0)\n"
        "    return {'facts': []}\n",
    )
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


# -- zombie workers: the deadline kills a process, not a thread ---------------


def _pid_alive(pid: int) -> bool:
    try:
        import psutil

        p = psutil.Process(pid)
        return p.status() != psutil.STATUS_ZOMBIE
    except psutil.Error:
        return False


def test_timed_out_worker_process_is_killed_not_merely_abandoned(
    store, override_run, monkeypatch, tmp_path
):
    """Python threads cannot be killed, so each step runs in its own
    subprocess. The injected worker records its own pid, sleeps past the
    deadline, and the test asserts that exact process is *dead* afterwards —
    it cannot keep causing side effects after MJ recorded the step failed.
    psutil gives the same answer on Windows (gone) and Linux (gone/reaped)."""
    pid_file = tmp_path / "worker.pid"
    override_run(
        "os.facts",
        "import os, time\n"
        "def run(store, inputs):\n"
        f"    open({str(pid_file)!r}, 'w').write(str(os.getpid()))\n"
        "    time.sleep(30)\n"
        "    return {'facts': []}\n",
    )
    monkeypatch.setenv("MJ_STEP_TIMEOUT_S", "3")
    report = runner.run_plan(store, planner.build_plan(store, "disk"), auto_approve=True)
    assert report["state"] == "failed"
    assert "timed out" in report["failed_step"]["error"]
    pid = int(pid_file.read_text())
    assert not _pid_alive(pid)


# -- final state: a recorded result is write-once ------------------------------


def test_late_or_duplicate_result_write_is_discarded_not_overwritten(store):
    """A result row is the record of *the* execution of an exact step. A late
    or duplicate write loses against the recorded truth, and the discard is
    audited — the final state is final."""
    key = "k-idem-1"
    first = runner._record_step_result(
        store, key, "t1", "s1", json.dumps({"v": 1}), 1, None, 0.0, 1.0
    )
    second = runner._record_step_result(
        store, key, "t1", "s1", json.dumps({"v": 2}), 0, None, 0.0, 2.0
    )
    assert first is True
    assert second is False
    row = store.one(
        "SELECT output_json, verified FROM step_results WHERE idempotency_key = ?", (key,)
    )
    assert json.loads(row["output_json"]) == {"v": 1}
    assert row["verified"] == 1  # the first write stands, un-overwritten
    discarded = store.query(
        "SELECT payload_json FROM audit_entries WHERE payload_json LIKE '%discarded%'"
    )
    assert discarded and key in discarded[0]["payload_json"]


def test_settings_snapshot_reflects_environment(monkeypatch):
    monkeypatch.setenv("MJ_STEP_TIMEOUT_S", "1.5")
    monkeypatch.setenv("MJ_TASK_BUDGET_S", "9")
    monkeypatch.setenv("MJ_MAX_STEPS", "3")
    snap = settings.snapshot()
    assert snap == {"step_timeout_s": 1.5, "task_budget_s": 9.0, "max_steps": 3}
    # garbage falls back to the default instead of raising
    monkeypatch.setenv("MJ_TASK_BUDGET_S", "not-a-number")
    assert settings.task_budget_s() == 600.0
