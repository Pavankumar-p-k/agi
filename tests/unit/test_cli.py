# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for jarvis/ package extraction and Track 9 CLI features."""

from __future__ import annotations

import pytest


class TestJarvisPackage:
    def test_import_config(self):
        from cli_config import JarvisConfig, JARVIS_DIR, CONFIG_PATH
        assert JarvisConfig is not None
        assert JARVIS_DIR is not None
        assert CONFIG_PATH is not None

    def test_import_completer(self):
        from cli_completer import JarvisCompleter, Completion
        assert JarvisCompleter is not None
        assert Completion is not None

    def test_import_utils(self):
        from cli_utils import (
            style_theme, syntax_highlight, colorize,
            python_exe, common_env, run_command,
            spawn_background, prepare_command, IDE_PRESETS,
        )
        assert all(f is not None for f in [
            style_theme, syntax_highlight, colorize,
            python_exe, common_env, run_command,
            spawn_background, prepare_command,
        ])
        assert "vscode" in IDE_PRESETS

    def test_import_visuals(self, capsys):
        from cli_visuals import AGENT_CARDS, render_agents, render_design_plan
        assert len(AGENT_CARDS) == 9
        render_agents()
        render_design_plan()
        output = capsys.readouterr().out
        assert "MAESTRO" in output
        assert "CLI experience design" in output

    def test_jarvis_py_entry(self):
        from cli_utils import ROOT
        assert ROOT is not None


class TestPluginCliCommands:
    def test_register_cli_command(self):
        from core.plugins.api import CLI_COMMANDS, get_cli_commands
        CLI_COMMANDS.clear()
        assert get_cli_commands() == {}

        handler = lambda text: f"handled: {text}"
        CLI_COMMANDS["test-cmd"] = {
            "handler": handler,
            "help_text": "A test command",
            "category": "custom",
            "plugin_name": "test_plugin",
        }
        commands = get_cli_commands()
        assert "test-cmd" in commands
        assert commands["test-cmd"]["help_text"] == "A test command"
        assert commands["test-cmd"]["plugin_name"] == "test_plugin"
        CLI_COMMANDS.clear()

    def test_register_and_dispatch(self):
        from core.plugins.api import CLI_COMMANDS
        CLI_COMMANDS.clear()
        results = []

        def my_handler(text):
            results.append(text)
            return "done"

        CLI_COMMANDS["mycmd"] = {
            "handler": my_handler,
            "help_text": "My command",
            "category": "custom",
            "plugin_name": "test",
        }
        result = CLI_COMMANDS["mycmd"]["handler"]("/mycmd arg1")
        assert results == ["/mycmd arg1"]
        assert result == "done"
        CLI_COMMANDS.clear()


class TestProgressSpinner:
    def test_spinner_cycles(self):
        from cli_utils import ProgressSpinner
        s = ProgressSpinner("working")
        frames = {s.tick() for _ in range(20)}
        assert len(frames) > 1

    def test_done_message(self):
        from cli_utils import ProgressSpinner
        s = ProgressSpinner("done")
        result = s.done("✔")
        assert "✔" in result


class TestDebugger:
    def test_runtime_snapshot_structure(self):
        from core.debugger import runtime_snapshot
        snap = runtime_snapshot()
        assert isinstance(snap, dict)
        for key in ("sessions", "tools", "plugins", "config"):
            assert key in snap
