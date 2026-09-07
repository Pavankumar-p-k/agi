"""End-to-end CLI tests: top-level commands: version, doctor, setup, benchmark."""

from __future__ import annotations

import types
from unittest.mock import MagicMock, patch

from cli_commands import cmd_version, cmd_doctor, cmd_setup, cmd_benchmark


class TestVersion:
    def test_version_output(self, capsys):
        ns = types.SimpleNamespace()
        rc = cmd_version(ns)
        assert rc == 0
        out = capsys.readouterr().out
        assert out.strip()


class TestDoctor:
    def test_doctor_ok(self, capsys):
        ns = types.SimpleNamespace(json=False)
        with patch("cli_visuals_new.print_system_msg"), \
             patch("core.setup.engine.SetupEngine.status", return_value={
                 "phase": "complete", "recommended_model": {"name": "test"},
                 "hardware": {"ram_gb": 16, "gpu_name": None, "os": "win32"},
                 "checks": {},
             }), \
             patch("core.feature_registry.get_feature_report", return_value={
                 "features": [], "enabled": 0, "disabled": 0,
                 "stable": 0, "beta": 0, "broken": 0, "planned": 0,
             }), \
             patch("core.diagnostics.build_diagnostic_report", return_value=MagicMock(
                 status="ok", issues=[], capability_gaps=[]
             )):
            rc = cmd_doctor(ns)
        assert rc == 0
        out = capsys.readouterr().out
        assert out.strip()


class TestSetup:
    def test_setup_no_crash(self, capsys):
        ns = types.SimpleNamespace()
        rc = cmd_setup(ns)
        assert rc == 0


class TestBenchmark:
    def test_benchmark_default(self, capsys):
        ns = types.SimpleNamespace(json=False)
        with patch("core.benchmark.perf_baseline.main", return_value=0):
            rc = cmd_benchmark(ns)
        assert rc == 0

    def test_benchmark_json(self, capsys):
        ns = types.SimpleNamespace(json=True)
        with patch("core.benchmark.perf_baseline.main", return_value=0):
            rc = cmd_benchmark(ns)
        assert rc == 0
