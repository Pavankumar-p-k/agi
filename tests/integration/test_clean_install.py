"""Clean-install test: a fresh virtualenv, a non-editable install, and the
`mj` console script exercised from it.

This exists because "installed package or PYTHONPATH=src" was a packaging gap;
this test proves a plain `pip install .` then `mj status` works for a new
session with no PYTHONPATH tricks. It creates a real venv, so it is slower
than the unit tests — that is the honest cost of proving the claim.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


def _venv_paths(venv_dir: Path) -> tuple[Path, Path]:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe", venv_dir / "Scripts" / "mj.exe"
    return venv_dir / "bin" / "python", venv_dir / "bin" / "mj"


@pytest.mark.integration
def test_clean_install_runs_mj_status_and_audit_in_fresh_venv(tmp_path):
    venv_dir = tmp_path / "clean-env"
    venv_python, mj_script = _venv_paths(venv_dir)

    created = subprocess.run(
        [sys.executable, "-m", "venv", str(venv_dir)],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert created.returncode == 0, created.stderr

    project_root = Path(__file__).resolve().parents[2]
    installed = subprocess.run(
        [
            str(venv_python),
            "-m",
            "pip",
            "install",
            "--quiet",
            "--disable-pip-version-check",
            str(project_root),
        ],
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert installed.returncode == 0, installed.stdout + installed.stderr
    assert mj_script.exists(), "console script `mj` should exist after a clean install"

    env = dict(os.environ, MJ_HOME=str(tmp_path / "mjhome"))
    status = subprocess.run(
        [str(mj_script), "status"],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    assert status.returncode == 0, status.stderr
    status_json = json.loads(status.stdout)
    assert status_json["autonomy_level"] == "L0"
    assert status_json["audit_chain"]["ok"] is True
    assert {"os.facts", "files.list", "files.organize.plan", "files.organize"} <= {
        c["id"] for c in status_json["capabilities"]
    }
    assert all(c["status"] == "healthy" for c in status_json["capabilities"])
    # the store lives where MJ_HOME pointed — not in some undefined location
    assert status_json["store"].replace("/", "\\").endswith(
        str((tmp_path / "mjhome" / "mj.sqlite3")).replace("/", "\\")
    )

    audit_run = subprocess.run(
        [str(mj_script), "audit"],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    assert audit_run.returncode == 0, audit_run.stderr
    assert json.loads(audit_run.stdout)["ok"] is True
