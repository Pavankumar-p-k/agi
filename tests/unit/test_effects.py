"""Declared effects vs actual code (docs/09 §3).

Registration enforces the declaration (powers/effects/floors, test_kernel);
this file lints the *code* against it: a worker that imports subprocess or a
network library without declaring the effect fails the lint — the evasion the
word-matching power rule cannot see (a capability called "helper" that shells
out passes any name check). Plus the runtime floor: even a row that bypassed
registration cannot run sensitive effects outside the local terminal.
"""

from __future__ import annotations

from mj.core.effects import lint_module, scan_source
from mj.core.registry import Manifest
from mj.core.store import Store, canonical_json
from mj.brain.planner import Plan, Step
from mj.executor import capabilities as caps
from mj.executor import runner


# -- scanner ----------------------------------------------------------------


def test_scan_detects_process_imports():
    assert "process" in scan_source("import subprocess")
    assert "process" in scan_source("from subprocess import run")
    assert "process" in scan_source("import multiprocessing")


def test_scan_detects_network_imports():
    assert "network" in scan_source("import socket")
    assert "network" in scan_source("from urllib.request import urlopen")
    assert "network" in scan_source("import requests")
    assert "network" in scan_source("import httpx")


def test_scan_detects_os_process_calls():
    assert "process" in scan_source("import os\nos.system('dir')")
    assert "process" in scan_source("import os\nos.popen('dir')")
    assert "process" in scan_source("import os\nos.spawnl(os.P_WAIT, 'x', 'x')")


def test_scan_leaves_innocuous_code_alone():
    assert scan_source("import json\nfrom pathlib import Path\nx = 1") == set()
    # os.replace moves files — that is filesystem.write, not process execution
    assert "process" not in scan_source("import os\nos.replace('a', 'b')")


# -- lint rule ---------------------------------------------------------------


def test_undeclared_process_import_is_a_lint_violation():
    """The rule itself: found effects minus declared effects must be empty."""
    shelling = (
        "import subprocess\n"
        "def run(store, inputs):\n"
        "    subprocess.run(['format', 'c:'])\n"
    )
    assert scan_source(shelling) - set() == {"process"}  # manifest declares nothing
    assert scan_source(shelling) - {"process"} == set()  # declaring it silences the lint


def test_all_builtin_capabilities_declare_what_their_code_does():
    """The shipped tree is consistent: every builtin's implementation modules
    (from provenance) scan clean against the manifest's declared effects.
    os.facts must declare `process` precisely because mj.world.probes
    imports subprocess — honest declarations, checked by machine."""
    for capability_id, impl in sorted(caps.BUILTINS.items()):
        declared = set(impl.manifest.effects)
        for entry in impl.manifest.provenance.get("implementations", []):
            module = entry.split(":")[0]
            assert lint_module(module, declared) == [], capability_id


# -- runtime floor (defense in depth) -----------------------------------------


def test_sensitive_effect_is_local_only_even_if_a_row_bypasses_registration(tmp_path):
    """Registration enforces floors, but a legacy or compromised DB row might
    have skipped validation — the runner still refuses sensitive effects from
    any non-local trust. Here policy alone would ALLOW (R0 reads are allowed
    from any channel), so this isolates the effects rule itself."""
    s = Store.open(tmp_path)
    try:
        caps.ensure_registered(s)
        m = Manifest(
            id="sneaky.helper",
            type="os",
            version="1.0.0",
            source="generated",
            risk_class="R0",  # would be refused at registration (process floor R1)…
            description="definitely nothing",
            effects=["process"],  # …but the row is inserted directly, bypassing it
        )
        s.conn.execute(
            "INSERT INTO capabilities (id, manifest_json, status, registered_at, updated_at) "
            "VALUES (?, ?, 'healthy', 0, 0)",
            ("sneaky.helper", canonical_json(m.to_dict())),
        )
        plan = Plan(
            goal="help",
            trust_level="external",
            steps=[Step("s1", "help", "sneaky.helper")],
        )
        report = runner.run_plan(s, plan, trust_level="external", auto_approve=True)
        assert report["state"] == "blocked"
        assert report["denied_steps"] == ["s1"]
        assert "local-terminal only" in report["decisions"]["s1"]["reason"]
    finally:
        s.close()
