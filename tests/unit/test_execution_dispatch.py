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
from unittest.mock import patch, MagicMock, AsyncMock


def _p(path: str) -> str:
    return path.replace("/", os.sep)


class TestMisformattedToolCall:
    @pytest.mark.asyncio
    async def test_misformatted_json_in_python_block(self):
        block = MagicMock()
        block.content = '{"key": "value"}'
        block.tool_type = "python"
        from core.tools.execution import execute_tool_block
        desc, result = await execute_tool_block(block)
        assert "misformatted" in desc
        assert result["exit_code"] == 1

    @pytest.mark.asyncio
    async def test_misformatted_valid_json_not_blocked(self):
        block = MagicMock()
        block.content = '{"key": "value"}'
        block.tool_type = "bash"
        from core.tools.execution import execute_tool_block
        desc, result = await execute_tool_block(block)
        assert "misformatted" not in desc


class TestDisabledTools:
    @pytest.mark.asyncio
    async def test_disabled_tool_blocked(self):
        block = MagicMock()
        block.content = "echo hello"
        block.tool_type = "bash"
        from core.tools.execution import execute_tool_block
        desc, result = await execute_tool_block(block, disabled_tools={"bash"})
        assert "BLOCKED" in desc
        assert "disabled" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_non_disabled_tool_passes(self):
        block = MagicMock()
        block.content = "query"
        block.tool_type = "search_chats"
        from core.tools.execution import execute_tool_block
        from core.tools.implementations import do_search_chats
        with patch("core.tools.implementations.do_search_chats", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = {"results": []}
            desc, result = await execute_tool_block(block, disabled_tools={"bash"})
            assert "BLOCKED" not in desc


class TestUnknownAndMcpTool:
    @pytest.mark.asyncio
    async def test_unknown_tool_blocked_by_rbac(self):
        block = MagicMock()
        block.content = "something"
        block.tool_type = "non_existent_tool_xyz"
        from core.tools.execution import execute_tool_block
        from core.authz import Role
        with patch("core.authz.engine.authz_engine.evaluate", return_value=True):
            desc, result = await execute_tool_block(block)
            assert "unknown" in desc
            assert result["exit_code"] == 1

    @pytest.mark.asyncio
    async def test_mcp_tool_falls_through_when_no_manager(self):
        block = MagicMock()
        block.content = "{}"
        block.tool_type = "mcp__custom_tool"
        from core.tools.execution import execute_tool_block
        with patch("core.tools.execution.get_mcp_manager", return_value=None):
            desc, result = await execute_tool_block(block)
            assert "mcp" in desc
            assert result["exit_code"] == 1


class TestToolDispatch:
    @pytest.mark.asyncio
    async def test_handler_called_for_registered_tool(self):
        block = MagicMock()
        block.content = "hello"
        block.tool_type = "bash"
        from core.tools.execution import execute_tool_block
        desc, result = await execute_tool_block(block)
        assert isinstance(desc, str)
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_handler_receives_owner(self):
        block = MagicMock()
        block.content = "GET /test"
        block.tool_type = "api_call"
        from core.tools.execution import execute_tool_block
        from core.tools.implementations import do_api_call
        with patch("core.tools.implementations.do_api_call", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = {"result": "ok"}
            with patch("core.authz.engine.authz_engine.evaluate", return_value=True):
                desc, result = await execute_tool_block(block, owner="test_admin")
                _, kwargs = mock_call.call_args
                assert kwargs.get("owner") == "test_admin"


class TestSensitivePath:
    def test_sensitive_paths_blocklist(self):
        from core.tools.execution import _is_sensitive_path
        assert _is_sensitive_path(_p("/home/user/.ssh/id_rsa")) is True
        assert _is_sensitive_path(_p("/home/user/.bashrc")) is True
        assert _is_sensitive_path(_p("/tmp/workspace/file.py")) is False

    def test_resolve_tool_path_rejects_sensitive(self):
        from core.tools.execution import _resolve_tool_path
        with pytest.raises(ValueError, match="sensitive directory"):
            _resolve_tool_path(_p("/home/user/.ssh/authorized_keys"))

    def test_resolve_tool_path_rejects_empty(self):
        from core.tools.execution import _resolve_tool_path
        with pytest.raises(ValueError, match="path is required"):
            _resolve_tool_path("")

    def test_tool_path_roots_includes_data(self):
        from core.tools.execution import _tool_path_roots
        from core.constants import DATA_DIR
        roots = _tool_path_roots()
        assert any(os.path.normpath(DATA_DIR) in r.replace(os.sep * 2, os.sep) for r in roots)
