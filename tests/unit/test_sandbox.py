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

"""Tests for plugin sandbox: allowed vs disallowed imports."""
import tempfile
import os

from core.plugins.sandbox import validate_manifest_imports, check_plugin_imports, STDLIB_ALLOWED


class TestValidateManifestImports:
    def test_all_project_modules_allowed(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("""from __future__ import annotations
import logging
from typing import Any
from core.plugins.base import Plugin, PluginManifest
from core.privacy_classifier import PrivacyTier
from assistant.wake_word import get_detector
from pc_agent.computer_agent import ComputerAgent
from governance.GovernanceValidator import GovernanceValidator
from memory.embedding_memory import EmbeddingMemory
from tools.search_tool import SearXNGSearch
import threading
""")
            path = f.name
        try:
            disallowed = validate_manifest_imports(path)
            assert disallowed == [], f"Expected no disallowed imports, got: {disallowed}"
        finally:
            os.unlink(path)

    def test_dangerous_imports_blocked(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("import os\nimport subprocess\nimport socket\nimport requests\nimport ctypes\n")
            path = f.name
        try:
            disallowed = validate_manifest_imports(path)
            assert "os" in disallowed
            assert "subprocess" in disallowed
            assert "socket" in disallowed
            assert "requests" in disallowed
        finally:
            os.unlink(path)

    def test_safe_stdlib_allowed(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("\n".join(f"import {m}" for m in sorted(STDLIB_ALLOWED)))
            path = f.name
        try:
            disallowed = validate_manifest_imports(path)
            assert disallowed == [], f"Expected safe stdlib to pass, got: {disallowed}"
        finally:
            os.unlink(path)

    def test_empty_file_allowed(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("# just a comment\n")
            path = f.name
        try:
            assert validate_manifest_imports(path) == []
        finally:
            os.unlink(path)

    def test_syntax_error_returns_empty(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("this is not valid python @@@\n")
            path = f.name
        try:
            assert validate_manifest_imports(path) == []
        finally:
            os.unlink(path)


class TestStrictSandboxFlag:
    def test_plugin_registry_created_with_strict(self):
        from core.plugins.base import plugin_registry
        assert plugin_registry.strict_sandbox is True

    def test_discover_rejects_dangerous(self):
        from core.plugins.base import PluginRegistry
        import tempfile, json, pathlib

        reg = PluginRegistry(strict_sandbox=True)
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = pathlib.Path(tmpdir)
            # Create a malicious plugin
            py_file = plugin_dir / "malicious.py"
            py_file.write_text("import os\nfrom core.plugins.base import Plugin, PluginManifest\nclass Plugin(Plugin): pass\n")
            json_file = plugin_dir / "malicious.json"
            json_file.write_text(json.dumps({
                "name": "test.malicious", "version": "1.0.0",
                "description": "bad", "entry_point": "malicious.py",
                "enabled": True, "hooks": ["on_load"],
            }))
            reg.discover_from_manifest(str(plugin_dir))
            assert reg.get("test.malicious") is None
