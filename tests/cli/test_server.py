"""End-to-end CLI tests: jarvis server {--dry-run, etc}."""

from __future__ import annotations

import types

from cli_commands import cmd_server


class TestServerDryRun:
    def test_dry_run(self, capsys):
        ns = types.SimpleNamespace(
            host="127.0.0.1", port=8000,
            no_reload=False, multi_model=False, dry_run=True,
        )
        rc = cmd_server(ns)
        assert rc == 0
        out = capsys.readouterr().out
        assert "[DRY RUN]" in out


class TestServerDefault:
    def test_server_dry_only(self, capsys):
        """In test env, only dry-run is safe; real start would hang."""
        ns = types.SimpleNamespace(
            host="127.0.0.1", port=8000,
            no_reload=False, multi_model=False, dry_run=True,
        )
        rc = cmd_server(ns)
        assert rc == 0
        assert "[DRY RUN]" in capsys.readouterr().out
