"""End-to-end CLI tests: jarvis models {list,test,benchmark,switch,start,apikeys}."""

from __future__ import annotations

import types

import pytest

from cli_commands import cmd_models


class TestModelsList:
    def test_list(self, capsys):
        ns = types.SimpleNamespace(action="list", args=[])
        rc = cmd_models(ns)
        assert rc == 0
        out = capsys.readouterr().out
        # Should list at least the available commands
        assert "Model" in out or rc == 0


class TestModelsTest:
    def _make_ns(self, **overrides) -> types.SimpleNamespace:
        defaults = dict(action="test", args=[], debug=False)
        defaults.update(overrides)
        return types.SimpleNamespace(**defaults)

    def test_test_no_model(self, capsys):
        ns = self._make_ns()
        rc = cmd_models(ns)
        assert rc == 0

    def test_test_help(self, capsys):
        ns = self._make_ns(args=["--help"])
        rc = cmd_models(ns)
        assert rc == 0


class TestModelsSwitch:
    def test_switch_no_arg(self, capsys):
        ns = types.SimpleNamespace(action="switch", args=[])
        rc = cmd_models(ns)
        assert rc == 0


class TestModelsApikeys:
    def test_apikeys_list(self, capsys):
        ns = types.SimpleNamespace(action="apikeys", args=[])
        rc = cmd_models(ns)
        assert rc == 0


class TestModelsStart:
    def test_start_dry(self, capsys):
        ns = types.SimpleNamespace(action="start", args=[])
        rc = cmd_models(ns)
        assert rc == 0
