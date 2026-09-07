"""Tests for jarvis activity CLI commands."""

from __future__ import annotations

import types

import pytest

from cli_commands import _cmd_activity


def test_activity_help(capsys):
    ns = types.SimpleNamespace(action="help", args=[])
    rc = _cmd_activity(ns)
    assert rc == 0
    out = capsys.readouterr().out
    assert "Usage: jarvis activity" in out
    assert "Subcommands:" in out
    assert "list" in out
    assert "tree" in out
    assert "get" in out
    assert "summary" in out
    assert "watch" in out


class TestActivityList:
    def test_list_empty(self, capsys, isolated_fs):
        ns = types.SimpleNamespace(action="list", args=[])
        rc = _cmd_activity(ns)
        assert rc == 0
        out = capsys.readouterr().out
        assert "No active activities." in out

    def test_list_with_activities(self, capsys, activity_manager, isolated_fs):
        mgr = activity_manager
        mgr.create_activity("First goal")
        mgr.create_activity("Second goal")
        ns = types.SimpleNamespace(action="list", args=[])
        activity_store = mgr.store
        rc = _cmd_activity(ns, _store=activity_store)
        assert rc == 0
        out = capsys.readouterr().out
        assert "First goal" in out
        assert "Second goal" in out


class TestActivityTree:
    def test_tree_no_id(self, capsys, isolated_fs):
        ns = types.SimpleNamespace(action="tree", args=[])
        rc = _cmd_activity(ns)
        assert rc == 1
        out = capsys.readouterr().out
        assert "Usage:" in out

    def test_tree_not_found(self, capsys, isolated_fs):
        ns = types.SimpleNamespace(action="tree", args=["nonexistent"])
        rc = _cmd_activity(ns)
        assert rc == 1
        out = capsys.readouterr().out
        assert "not found" in out

    def test_tree_with_nodes(self, capsys, activity_manager, isolated_fs):
        mgr = activity_manager
        act = mgr.create_activity("Root goal")
        sub = mgr.create_subgoal(act, "Sub task")
        mgr.create_agent_task(act, "builder", "Build step", parent=sub)
        ns = types.SimpleNamespace(action="tree", args=[act.activity_id])
        activity_store = mgr.store
        rc = _cmd_activity(ns, _store=activity_store)
        assert rc == 0
        out = capsys.readouterr().out
        assert "Root goal" in out
        assert "Activity Tree:" in out


class TestActivityGet:
    def test_get_no_id(self, capsys, isolated_fs):
        ns = types.SimpleNamespace(action="get", args=[])
        rc = _cmd_activity(ns)
        assert rc == 1
        out = capsys.readouterr().out
        assert "Usage:" in out

    def test_get_not_found(self, capsys, isolated_fs):
        ns = types.SimpleNamespace(action="get", args=["nonexistent"])
        rc = _cmd_activity(ns)
        assert rc == 1
        out = capsys.readouterr().out
        assert "not found" in out

    def test_get_with_id(self, capsys, activity_manager, isolated_fs):
        mgr = activity_manager
        act = mgr.create_activity("Detail test")
        ns = types.SimpleNamespace(action="get", args=[act.activity_id])
        activity_store = mgr.store
        rc = _cmd_activity(ns, _store=activity_store)
        assert rc == 0
        out = capsys.readouterr().out
        assert "Detail test" in out
        assert "ID:" in out
        assert "Type:" in out
        assert "Status:" in out


class TestActivitySummary:
    def test_summary_no_activities(self, capsys, isolated_fs):
        ns = types.SimpleNamespace(action="summary", args=[])
        rc = _cmd_activity(ns)
        assert rc == 0
        out = capsys.readouterr().out
        assert "No activities to summarize." in out

    def test_summary_with_id(self, capsys, activity_manager, isolated_fs):
        mgr = activity_manager
        act = mgr.create_activity("Summary test")
        sub = mgr.create_subgoal(act, "Sub A")
        mgr.create_agent_task(act, "agent_1", "Task 1", parent=sub)
        mgr.create_agent_task(act, "agent_2", "Task 2", parent=sub)
        ns = types.SimpleNamespace(action="summary", args=[act.activity_id])
        activity_store = mgr.store
        rc = _cmd_activity(ns, _store=activity_store)
        assert rc == 0
        out = capsys.readouterr().out
        assert "Summary test" in out
        assert "agent_1" in out
        assert "agent_2" in out

    def test_summary_for_all(self, capsys, activity_manager, isolated_fs):
        mgr = activity_manager
        mgr.create_activity("Active A")
        mgr.create_activity("Active B")
        ns = types.SimpleNamespace(action="summary", args=[])
        activity_store = mgr.store
        rc = _cmd_activity(ns, _store=activity_store)
        assert rc == 0
        out = capsys.readouterr().out
        assert "Active A" in out
        assert "Active B" in out


class TestActivityWatch:
    def test_watch_stops_on_keyboard_interrupt(self, activity_manager, isolated_fs):
        import cli_commands
        original_sleep = cli_commands.time.sleep

        interrupt_after_first = True
        def _interrupting_sleep(secs):
            nonlocal interrupt_after_first
            if interrupt_after_first:
                interrupt_after_first = False
                original_sleep(0)
                raise KeyboardInterrupt()
            original_sleep(secs)

        cli_commands.time.sleep = _interrupting_sleep
        try:
            ns = types.SimpleNamespace(action="watch", args=[])
            rc = _cmd_activity(ns)
            assert rc == 0
        finally:
            cli_commands.time.sleep = original_sleep


class TestActivityUnknown:
    def test_unknown_subcommand(self, capsys, isolated_fs):
        ns = types.SimpleNamespace(action="unknown_cmd", args=[])
        rc = _cmd_activity(ns)
        assert rc == 1
        out = capsys.readouterr().out
        assert "Unknown activity subcommand" in out
