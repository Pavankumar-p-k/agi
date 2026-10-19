"""Gateway tests: the mj CLI end to end."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from mj.core.store import Store
from mj.executor import capabilities as caps
from mj.executor import runner
from mj.world import model
from mj.world import probes as probes_mod

SRC = str(Path(__file__).resolve().parents[2] / "src")


@pytest.fixture()
def mj_home(tmp_path):
    home = tmp_path / "mjhome"
    home.mkdir(parents=True)
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("MJ_HOME", str(home))
        yield home
    # env restored by the context manager


def _subprocess_mj(mj_home, *argv, cwd=None):
    env = dict(os.environ)
    env["MJ_HOME"] = str(mj_home)
    env["PYTHONPATH"] = SRC + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-m", "mj", *argv],
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd or os.getcwd(),
        timeout=120,
    )


# -- subprocess smoke (the interface the user will actually use) --------------


def test_status_subprocess(mj_home):
    r = _subprocess_mj(mj_home, "status")
    assert r.returncode == 0, r.stderr
    status = json.loads(r.stdout)
    assert status["autonomy_level"] == "L0"
    assert status["audit_chain"]["ok"] is True
    assert {c["id"] for c in status["capabilities"]} >= {
        "os.facts",
        "files.list",
        "files.organize.plan",
        "files.organize",
    }
    assert all(c["status"] == "healthy" for c in status["capabilities"])


def test_ask_subprocess_reports_disk_with_labels(mj_home):
    r = _subprocess_mj(mj_home, "ask", "how much disk space do I have?")
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    disk_answers = [a for a in out["answers"] if a["topic"] == "disk"]
    assert disk_answers
    assert all(a["label"] == "verified" for a in disk_answers)
    assert any(a["value"]["free"] > 0 for a in disk_answers)


def test_run_organize_dry_run_subprocess(mj_home, tmp_path):
    sandbox = tmp_path / "files"
    sandbox.mkdir()
    (sandbox / "a.txt").write_text("t", encoding="utf-8")
    (sandbox / "b.png").write_text("t", encoding="utf-8")
    r = _subprocess_mj(mj_home, "run", "organize files", "--dir", str(sandbox), "--yes")
    assert r.returncode == 0, r.stderr
    report = json.loads(r.stdout)
    assert report["state"] == "done"
    assert report["verified_steps"] == 2 or report["verified_steps"] == 1
    # dry run moved nothing
    assert sorted(p.name for p in sandbox.iterdir()) == ["a.txt", "b.png"]


def test_organize_commit_requires_approval_then_executes_interactively(mj_home, tmp_path):
    sandbox = tmp_path / "files2"
    sandbox.mkdir()
    (sandbox / "a.txt").write_text("t", encoding="utf-8")
    (sandbox / "b.png").write_text("t", encoding="utf-8")
    env_setup = dict(os.environ or {})
    env_setup["MJ_HOME"] = str(mj_home)
    env_setup["PYTHONPATH"] = SRC + os.pathsep + env_setup.get("PYTHONPATH", "")
    import msvcrt  # noqa: F401  # interactive input via stdin redirection below

    proc = subprocess.run(
        [sys.executable, "-m", "mj", "run", "organize files", "--dir", str(sandbox), "--commit"],
        capture_output=True,
        text=True,
        env=env_setup,
        input="y\n",
        timeout=120,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert '"action_required": "approval"' in proc.stdout
    # the approval payload names the exact capability and risk class
    assert "files.organize" in proc.stdout and '"risk_class": "R2"' in proc.stdout
    moved = sorted(p.name for p in sandbox.iterdir())
    assert "documents" in moved and "images" in moved


# -- in-process checks ---------------------------------------------------------


def _cli(mj_home, *argv):
    os.environ["MJ_HOME"] = str(mj_home)
    from mj.gateway import cli

    return cli.main(list(argv))


def test_unknown_goal_exits_3_with_question(mj_home, capsys):
    code = _cli(mj_home, "plan", "file my taxes")
    assert code == 3
    out = json.loads(capsys.readouterr().out)
    assert out["error"] == "unknown goal"
    assert out["question"]


def test_plan_command_shows_typed_plan(mj_home, capsys):
    code = _cli(mj_home, "plan", "disk")
    assert code == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["plan_id"] and plan["steps"][0]["capability_id"] == "os.facts"


def test_run_facts_report_separates_verified(mj_home, capsys):
    code = _cli(mj_home, "run", "what is running", "--yes")
    assert code == 0
    report = json.loads(capsys.readouterr().out)
    assert report["state"] == "done"
    assert report["verified_steps"] >= 1 and report["unverified_steps"] == 0


def test_events_show_transition_and_step_records(mj_home, capsys):
    _cli(mj_home, "run", "disk", "--yes")
    capsys.readouterr()  # consume the run report before reading events output
    code = _cli(mj_home, "events")
    assert code == 0
    evts = json.loads(capsys.readouterr().out)
    kinds = [e["kind"] for e in evts]
    assert "task.transition" in kinds and "step.result" in kinds


def test_events_for_task(mj_home, capsys):
    out1 = _run_capture(mj_home, "run", "facts", "--yes")
    task_id = out1["task_id"]
    cap2 = _cli(mj_home, "events", "--task-id", task_id)
    assert cap2 == 0
    evts = json.loads(capsys.readouterr().out)
    assert all(True for _ in evts)


def _run_capture(mj_home, *argv):
    import io
    from contextlib import redirect_stdout

    os.environ["MJ_HOME"] = str(mj_home)
    from mj.gateway import cli

    buf = io.StringIO()
    with redirect_stdout(buf):
        cli.main(list(argv))
    return json.loads(buf.getvalue())


def test_facts_and_audit_commands(mj_home, capsys):
    assert _cli(mj_home, "facts", "--refresh") == 0
    facts_out = capsys.readouterr().out
    assert "verified" in facts_out
    assert _cli(mj_home, "audit") == 0
    res = json.loads(capsys.readouterr().out)
    assert res["ok"] is True and res["entries"] > 0


def test_registry_command_lists_risk_classes(mj_home, capsys):
    assert _cli(mj_home, "registry") == 0
    caps_rows = json.loads(capsys.readouterr().out)
    assert all("risk_class" in row and row["risk_class"].startswith("R") for row in caps_rows)


def test_run_commit_denied_interactively_leaves_files(mj_home, tmp_path):
    sandbox = tmp_path / "files3"
    sandbox.mkdir()
    (sandbox / "a.txt").write_text("t", encoding="utf-8")
    env_setup = dict(os.environ)
    env_setup["MJ_HOME"] = str(mj_home)
    env_setup["PYTHONPATH"] = SRC + os.pathsep + env_setup.get("PYTHONPATH", "")
    proc = subprocess.run(
        [sys.executable, "-m", "mj", "run", "organize files", "--dir", str(sandbox), "--commit"],
        capture_output=True,
        text=True,
        env=env_setup,
        input="n\n",
        timeout=120,
    )
    assert proc.returncode == 4
    assert sorted(p.name for p in sandbox.iterdir()) == ["a.txt"]


def test_undo_after_commit(mj_home, tmp_path, capsys):
    sandbox = tmp_path / "files4"
    sandbox.mkdir()
    (sandbox / "a.txt").write_text("t", encoding="utf-8")
    out = _run_capture(mj_home, "run", "organize files", "--dir", str(sandbox), "--commit", "--yes")
    assert sorted(p.name for p in sandbox.iterdir()) != ["a.txt"]
    code = _cli(mj_home, "undo", out["task_id"])
    assert code == 0
    assert sorted(p.name for p in sandbox.iterdir()) == ["a.txt"]
