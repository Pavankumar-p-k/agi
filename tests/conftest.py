"""Shared pytest fixtures: MJ_WORKER_OVERRIDE_DEV injection points.

Workers now run in subprocesses (docs/09 §2), so tests that need to inject
worker behavior do it through the same override mechanism an operator would
use: a JSON file naming the capability and the code to run, handed to the
worker subprocess by the runner. The injected code executes in exactly the
place a real capability would run.
"""

from __future__ import annotations

import json

import pytest


@pytest.fixture()
def override_run(tmp_path, monkeypatch):
    """Inject worker code for one capability via MJ_WORKER_OVERRIDE_DEV.

    Usage: override_run("os.facts", "def run(store, inputs):\\n    return {}\\n")
    The code must define ``run(store, inputs)``. It runs in the worker
    subprocess; verifiers stay untouched (they run in the parent, as ever).
    """

    def _override(capability: str, code: str) -> None:
        f = tmp_path / f"worker-override-{capability.replace('.', '_')}.json"
        f.write_text(
            json.dumps({"capability": capability, "code": code}), encoding="utf-8"
        )
        monkeypatch.setenv("MJ_WORKER_OVERRIDE_DEV", str(f))

    return _override
