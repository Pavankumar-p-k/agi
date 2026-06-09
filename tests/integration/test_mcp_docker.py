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

"""tests/test_mcp_docker.py — Tests for mcp/server.py MCPServer + ai_os/docker_sandbox.py."""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock


class TestMCPServer:
    @pytest.fixture
    def server(self):
        from mcp.server import MCPServer
        s = MCPServer()
        return s

    def test_init(self, server):
        assert server.is_running is False
        assert server._tools == {}
        assert server._resources == {}

    def test_register_tool(self, server):
        handler = MagicMock()
        server.register_tool("test_tool", "A test tool", {"type": "object"}, handler)
        assert "test_tool" in server._tools
        assert server._tools["test_tool"]["handler"] is handler

    def test_register_resource(self, server):
        handler = MagicMock()
        server.register_resource("memory://recent", "Recent Memory", "Recent items", handler)
        assert "memory://recent" in server._resources

    def test_get_tool_definitions(self, server):
        server.register_tool("t1", "desc", {"type": "object"}, MagicMock())
        defs = server.get_tool_definitions()
        assert len(defs) == 1
        assert defs[0]["name"] == "t1"

    def test_get_resource_definitions(self, server):
        server.register_resource("r1", "R1", "desc", MagicMock())
        defs = server.get_resource_definitions()
        assert len(defs) == 1
        assert defs[0]["uri"] == "r1"

    @pytest.mark.asyncio
    async def test_call_tool(self, server):
        handler = AsyncMock(return_value="result")
        server.register_tool("t1", "desc", {"type": "object"}, handler)
        result = await server.call_tool("t1", {"arg": "val"})
        assert result == "result"
        handler.assert_called_once_with(arg="val")

    @pytest.mark.asyncio
    async def test_call_tool_unknown(self, server):
        with pytest.raises(ValueError, match="Unknown MCP tool"):
            await server.call_tool("nonexistent", {})

    @pytest.mark.asyncio
    async def test_read_resource(self, server):
        handler = AsyncMock(return_value={"data": "test"})
        server.register_resource("mem://data", "Data", "desc", handler)
        result = await server.read_resource("mem://data")
        assert result == {"data": "test"}

    @pytest.mark.asyncio
    async def test_read_resource_unknown(self, server):
        with pytest.raises(ValueError, match="Unknown MCP resource"):
            await server.read_resource("mem://unknown")

    @pytest.mark.asyncio
    async def test_start_stop(self, server):
        await server.start()
        assert server.is_running is True
        assert len(server._tools) == 6
        await server.stop()
        assert server.is_running is False

    def test_get_fastapi_router(self, server):
        router = server.get_fastapi_router()
        assert router is not None
        assert router.prefix == "/mcp"


class TestDockerSandbox:
    @pytest.fixture
    def sandbox(self):
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        with patch("docker.from_env", return_value=mock_client):
            from ai_os.docker_sandbox import DockerSandbox
            yield DockerSandbox()

    def test_init_available(self, sandbox):
        assert sandbox.available is True

    def test_init_not_available(self):
        with patch("docker.from_env", side_effect=Exception("No docker")):
            from ai_os.docker_sandbox import DockerSandbox
            s = DockerSandbox()
            assert s.available is False

    @pytest.mark.asyncio
    async def test_exec_python_not_available(self):
        from ai_os.docker_sandbox import DockerSandbox
        s = DockerSandbox()
        s._available = False
        result = await s.exec_python("print('hello')")
        assert result["success"] is False
        assert "Docker not available" in result["error"]

    @pytest.mark.asyncio
    async def test_exec_python_success(self, sandbox):
        mock_container = MagicMock()
        sandbox._client.containers.create.return_value = mock_container
        mock_container.wait.return_value = 0
        mock_container.logs.return_value = b"hello world\n"
        result = await sandbox.exec_python("print('hello')")
        assert result["success"] is True
        assert "hello" in result["stdout"]

    @pytest.mark.asyncio
    async def test_exec_command_with_files(self, sandbox):
        mock_container = MagicMock()
        sandbox._client.containers.create.return_value = mock_container
        mock_container.wait.return_value = 0
        mock_container.logs.return_value = b"output\n"
        mock_container.get_archive.return_value = ([b"data"], {})
        result = await sandbox.exec_command(["ls"], files={"test.txt": b"hello"})
        assert result["success"] is True
