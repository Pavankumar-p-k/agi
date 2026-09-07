"""End-to-end CLI tests: jarvis provider {list,enable,disable,etc}."""

from __future__ import annotations

import types

import pytest

from cli_commands import cmd_provider


class TestProviderList:
    def test_list(self, capsys, isolated_fs):
        ns = types.SimpleNamespace(action="list", args=[])
        rc = cmd_provider(ns)
        assert rc == 0


class TestProviderUnknown:
    def test_unknown_action(self, capsys, isolated_fs):
        ns = types.SimpleNamespace(action="bogus", args=[])
        rc = cmd_provider(ns)
        assert rc != 0
