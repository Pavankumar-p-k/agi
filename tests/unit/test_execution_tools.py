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

import pytest
import os
import tempfile


@pytest.fixture(autouse=True)
def patch_logger():
    import logging
    logging.getLogger("core.tools.execution").disabled = True


def _p(path: str) -> str:
    """Normalize to platform path separator."""
    return path.replace("/", os.sep)


class TestIsSensitivePath:
    def test_blocked_ssh_dir(self):
        from core.tools.execution import _is_sensitive_path
        assert _is_sensitive_path(_p("/home/user/.ssh/authorized_keys")) is True
        assert _is_sensitive_path(_p("/home/user/.ssh")) is True

    def test_blocked_gnupg_dir(self):
        from core.tools.execution import _is_sensitive_path
        assert _is_sensitive_path(_p("/home/user/.gnupg/pubring.kbx")) is True

    def test_blocked_dotfiles(self):
        from core.tools.execution import _is_sensitive_path
        assert _is_sensitive_path(_p("/home/user/.bashrc")) is True
        assert _is_sensitive_path(_p("/home/user/.zshrc")) is True
        assert _is_sensitive_path(_p("/home/user/.env")) is True
        assert _is_sensitive_path(_p("/home/user/.netrc")) is True

    def test_blocked_key_files(self):
        from core.tools.execution import _is_sensitive_path
        assert _is_sensitive_path(_p("/any/dir/id_rsa")) is True
        assert _is_sensitive_path(_p("/any/dir/id_ed25519")) is True
        assert _is_sensitive_path(_p("/any/dir/authorized_keys")) is True

    def test_safe_path(self):
        from core.tools.execution import _is_sensitive_path
        assert _is_sensitive_path(_p("/home/user/projects/main.py")) is False
        assert _is_sensitive_path(_p("/tmp/build/output.log")) is False

    def test_safe_data_dir(self):
        from core.tools.execution import _is_sensitive_path
        assert _is_sensitive_path(_p("/data/documents/notes.md")) is False


class TestResolveToolPath:
    def test_empty_path_raises(self):
        from core.tools.execution import _resolve_tool_path
        with pytest.raises(ValueError, match="path is required"):
            _resolve_tool_path("")
        with pytest.raises(ValueError, match="path is required"):
            _resolve_tool_path(None)

    def test_sensitive_path_blocked(self):
        from core.tools.execution import _resolve_tool_path
        with pytest.raises(ValueError, match="sensitive directory"):
            _resolve_tool_path(_p("/home/user/.ssh/authorized_keys"))

    def test_tool_path_roots_contains_data_dir(self):
        from core.tools.execution import _tool_path_roots
        from core.constants import DATA_DIR
        roots = _tool_path_roots()
        assert any(os.path.samefile(r, DATA_DIR) if os.path.exists(r) else DATA_DIR in r for r in roots)
        assert any("tmp" in r for r in roots)


class TestToolPathRoots:
    def test_returns_list(self):
        from core.tools.execution import _tool_path_roots
        roots = _tool_path_roots()
        assert isinstance(roots, list)
        assert len(roots) >= 1

    def test_includes_temp(self):
        from core.tools.execution import _tool_path_roots
        roots = _tool_path_roots()
        assert any("tmp" in r for r in roots)
