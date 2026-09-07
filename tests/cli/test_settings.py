"""End-to-end CLI tests: jarvis settings {get,set,reset,export,import}."""

from __future__ import annotations

import types

from cli_commands import cmd_settings


class TestSettingsGet:
    def test_get_unknown_key(self, capsys):
        ns = types.SimpleNamespace(action="get", key="nonexistent_key_xyz", value="", args=[])
        rc = cmd_settings(ns)
        assert rc == 1


class TestSettingsSet:
    def test_set_no_key(self, capsys):
        ns = types.SimpleNamespace(action="set", key="", value="", args=[])
        rc = cmd_settings(ns)
        assert rc == 0


class TestSettingsReset:
    def test_reset(self, capsys):
        ns = types.SimpleNamespace(action="reset", key="", value="", args=[])
        rc = cmd_settings(ns)
        assert rc == 0


class TestSettingsExport:
    def test_export(self, capsys):
        ns = types.SimpleNamespace(action="export", key="", value="", args=[])
        rc = cmd_settings(ns)
        assert rc == 0


class TestSettingsUnknown:
    def test_unknown_action(self, capsys):
        ns = types.SimpleNamespace(action="bogus", key="", value="", args=[])
        rc = cmd_settings(ns)
        assert rc == 0
        out = capsys.readouterr().out
        assert "Unknown" in out or "settings" in out.lower()
