"""End-to-end CLI tests: jarvis activity {list,tree,get,summary,watch,cleanup}."""

from __future__ import annotations

import types

import pytest

from cli_commands import _cmd_activity


class TestActivityHelp:
    def test_help(self, capsys):
        ns = types.SimpleNamespace(action="help", args=[])
        rc = _cmd_activity(ns)
        assert rc == 0
        out = capsys.readouterr().out
        assert "Usage: jarvis activity" in out
        assert "cleanup" in out


class TestActivityList:
    def test_list_empty(self, capsys, isolated_fs):
        ns = types.SimpleNamespace(action="list", args=[])
        rc = _cmd_activity(ns)
        assert rc == 0
        out = capsys.readouterr().out
        assert "No active activities." in out


class TestActivityCleanup:
    def test_cleanup_no_args(self, capsys, isolated_fs):
        ns = types.SimpleNamespace(action="cleanup", args=[])
        rc = _cmd_activity(ns)
        assert rc == 0
        out = capsys.readouterr().out
        assert "stale" in out.lower() or "No" in out


class TestActivityUnknown:
    def test_unknown_subcommand(self, capsys, isolated_fs):
        ns = types.SimpleNamespace(action="nonexistent", args=[])
        rc = _cmd_activity(ns)
        assert rc == 1
        out = capsys.readouterr().out
        assert "Unknown activity subcommand" in out


class TestActivityTree:
    def test_tree_no_id(self, capsys, isolated_fs):
        ns = types.SimpleNamespace(action="tree", args=[])
        rc = _cmd_activity(ns)
        assert rc == 1
        out = capsys.readouterr().out
        assert "Usage:" in out


class TestActivityGet:
    def test_get_no_id(self, capsys, isolated_fs):
        ns = types.SimpleNamespace(action="get", args=[])
        rc = _cmd_activity(ns)
        assert rc == 1
        out = capsys.readouterr().out
        assert "Usage:" in out
