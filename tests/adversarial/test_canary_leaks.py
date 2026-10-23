"""Canary leak test: a secret value must never leave the worker boundary.

The review's scenario: a stored credential is handed to a capability, and the
capability misbehaves — it prints the value, raises an error containing it,
and returns it in its output. None of that may reach the model, the database,
the audit log, the task report, worker scratch files, or CLI output.

Each test stores ``CANARY-7f3a9`` under ``spreadsheet_column`` (the name
``data.spreadsheet.summary`` declares in ``requires_scopes``), runs the step
through the real subprocess path, then sweeps every persistence surface:

* every byte of the SQLite database and its WAL/SHM sidecars,
* every file under the MJ home (broker records included — they are encrypted),
* the report dict returned by the runner,
* the CLI's ``events``, ``audit`` and ``status`` output.

The scope test additionally proves a name outside ``requires_scopes`` is
refused before the worker starts.
"""

from __future__ import annotations

import json

import pytest

from mj.brain.planner import Plan, Step
from mj.core.store import Store
from mj.executor import broker
from mj.executor import capabilities as caps
from mj.executor import runner
from mj.gateway import cli

CANARY = "CANARY-7f3a9"
SECRET_NAME = "spreadsheet_column"


@pytest.fixture()
def store(tmp_path):
    s = Store.open(tmp_path)
    caps.ensure_registered(s)
    yield s
    s.close()


def _plan(csv_path, secret_names):
    return Plan(
        goal="summarize with a credential",
        trust_level="local-terminal",
        steps=[
            Step(
                "s1",
                "summarize",
                "data.spreadsheet.summary",
                {"path": str(csv_path), "secrets": list(secret_names)},
            )
        ],
    )


@pytest.fixture()
def sample_csv(tmp_path):
    path = tmp_path / "sample.csv"
    path.write_text("name,value\none,1\n", encoding="utf-8")
    return path


def _assert_absent_from_files(store: Store, needle: str = CANARY) -> None:
    """Nothing under the MJ home — database, WAL, broker records, scratch — has it."""
    for path in sorted(store.path.parent.rglob("*")):
        if not path.is_file():
            continue
        assert needle.encode() not in path.read_bytes(), f"secret leaked into {path.name}"


def _assert_absent_from_cli(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("MJ_HOME", str(tmp_path))
    for argv in (["events"], ["audit"], ["status"]):
        assert cli.main(argv) in (0, 6)  # audit may legitimately fail on empty chain
        out, err = capsys.readouterr()
        assert CANARY not in out and CANARY not in err, f"secret leaked into CLI {argv}"


def _assert_no_leak(store, report, tmp_path, monkeypatch, capsys) -> None:
    assert CANARY not in json.dumps(report, default=str)
    _assert_absent_from_files(store)
    _assert_absent_from_cli(tmp_path, monkeypatch, capsys)


# -- 1: value in the worker's returned output --------------------------------


def test_canary_in_worker_output_is_redacted(
    store, sample_csv, override_run, tmp_path, monkeypatch, capsys
):
    broker.set_secret(store, SECRET_NAME, CANARY)
    override_run(
        "data.spreadsheet.summary",
        "def run(store, inputs):\n"
        "    value = inputs['secrets']['spreadsheet_column']\n"
        "    return {'total_rows': 1, 'matching_rows': 1, 'summary': 'carried ' + value}\n",
    )

    report = runner.run_plan(store, _plan(sample_csv, [SECRET_NAME]), auto_approve=True)

    assert report["state"] == "done"
    row = store.one(
        "SELECT output_json FROM step_results WHERE task_id = ? AND step_id = 's1'",
        (report["task_id"],),
    )
    assert CANARY not in row["output_json"]
    assert "[REDACTED:spreadsheet_column]" in row["output_json"]
    _assert_no_leak(store, report, tmp_path, monkeypatch, capsys)


# -- 2: value in a worker exception message ----------------------------------


def test_canary_in_worker_exception_is_redacted(
    store, sample_csv, override_run, tmp_path, monkeypatch, capsys
):
    broker.set_secret(store, SECRET_NAME, CANARY)
    override_run(
        "data.spreadsheet.summary",
        "def run(store, inputs):\n"
        "    raise ValueError('bad credential: ' + inputs['secrets']['spreadsheet_column'])\n",
    )

    report = runner.run_plan(store, _plan(sample_csv, [SECRET_NAME]), auto_approve=True)

    assert report["state"] == "failed"
    assert CANARY not in report["failed_step"]["error"]
    assert "[REDACTED:spreadsheet_column]" in report["failed_step"]["error"]
    row = store.one(
        "SELECT output_json FROM step_results WHERE task_id = ? AND step_id = 's1'",
        (report["task_id"],),
    )
    assert CANARY not in row["output_json"]
    _assert_no_leak(store, report, tmp_path, monkeypatch, capsys)


# -- 3: value in printed output / a dead worker's stderr ---------------------


def test_canary_printed_or_left_in_stderr_survives_nowhere(
    store, sample_csv, override_run, tmp_path, monkeypatch, capsys
):
    broker.set_secret(store, SECRET_NAME, CANARY)
    # The worker prints the value on both streams, then dies without a result:
    # the parent's "no result" error embeds the stderr tail, the strongest
    # form of the print leak.
    override_run(
        "data.spreadsheet.summary",
        "def run(store, inputs):\n"
        "    import os, sys\n"
        "    value = inputs['secrets']['spreadsheet_column']\n"
        "    print('stdout leak: ' + value)\n"
        "    print('stderr leak: ' + value, file=sys.stderr)\n"
        "    sys.stdout.flush()\n"
        "    sys.stderr.flush()\n"
        "    os._exit(1)\n",
    )

    report = runner.run_plan(store, _plan(sample_csv, [SECRET_NAME]), auto_approve=True)

    assert report["state"] == "failed"
    assert "worker produced no result" in report["failed_step"]["error"]
    # the scratch stdout/stderr files carried the value; cleanup must have
    # removed them, and the recorded error must not repeat it
    assert CANARY not in report["failed_step"]["error"]
    _assert_no_leak(store, report, tmp_path, monkeypatch, capsys)


# -- 4: a name outside requires_scopes is refused before the worker starts ---


def test_out_of_scope_secret_is_refused(store, sample_csv, override_run, tmp_path, monkeypatch, capsys):
    broker.set_secret(store, SECRET_NAME, CANARY)
    broker.set_secret(store, "other_token", "CANARY-OTHER-9c2")
    # If the refusal were skipped, this worker would happily echo it.
    override_run(
        "data.spreadsheet.summary",
        "def run(store, inputs):\n"
        "    return {'total_rows': 1, 'matching_rows': 1, "
        "'summary': str(sorted(inputs.get('secrets', {})))}\n",
    )

    report = runner.run_plan(store, _plan(sample_csv, ["other_token"]), auto_approve=True)

    assert report["state"] == "failed"
    assert "requires_scopes" in report["failed_step"]["error"]
    assert "CANARY-OTHER-9c2" not in json.dumps(report, default=str)
    _assert_absent_from_files(store)
    _assert_absent_from_files(store, "CANARY-OTHER-9c2")
    _assert_absent_from_cli(tmp_path, monkeypatch, capsys)


# -- 5: the master key never reaches a worker process ------------------------


def test_master_key_env_is_not_inherited_by_workers(
    store, sample_csv, override_run, tmp_path, monkeypatch, capsys
):
    broker.set_secret(store, SECRET_NAME, CANARY)
    override_run(
        "data.spreadsheet.summary",
        "def run(store, inputs):\n"
        "    import os\n"
        "    return {'total_rows': 1, 'matching_rows': 1, "
        "'key_in_env': 'MJ_BROKER_KEY' in os.environ}\n",
    )

    report = runner.run_plan(store, _plan(sample_csv, [SECRET_NAME]), auto_approve=True)

    assert report["state"] == "done"
    row = store.one(
        "SELECT output_json FROM step_results WHERE task_id = ? AND step_id = 's1'",
        (report["task_id"],),
    )
    assert json.loads(row["output_json"])["key_in_env"] is False
