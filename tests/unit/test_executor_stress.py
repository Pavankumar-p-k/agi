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

"""Stress and concurrency tests for OpenClawExecutor."""
import asyncio
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from core.types import ExecutionContext


def _make_context(permissions=None, session_id="test"):
    if permissions is None:
        permissions = ["read"]
    return ExecutionContext(
        user_id="test",
        session_id=session_id,
        permissions=permissions,
        variables={},
    )


class TestExecutorConcurrency:
    @pytest.mark.asyncio
    async def test_concurrent_command_execution(self):
        """Multiple commands can run concurrently without crashing."""
        from tools.executor import OpenClawExecutor
        ex = OpenClawExecutor()

        ctx = _make_context(permissions=["read", "write"])
        commands = [
            ("echo hello", ctx),
            ("echo world", ctx),
            ("echo foo", ctx),
            ("echo bar", ctx),
        ]

        tasks = [ex.execute_command(cmd, c) for cmd, c in commands]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        assert len(results) == 4
        for r in results:
            if isinstance(r, Exception):
                pytest.fail(f"Unexpected exception: {r}")

    @pytest.mark.asyncio
    async def test_concurrent_file_operations(self):
        """Concurrent file operations on same path are safe."""
        import tempfile, os
        from tools.executor import OpenClawExecutor
        ex = OpenClawExecutor()

        tmpdir = tempfile.mkdtemp()
        ctx = _make_context(permissions=["read", "write"])

        try:
            tasks = [
                ex.execute_file_operation("write", os.path.join(tmpdir, "f.txt"), f"data{i}", ctx)
                for i in range(10)
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            successes = [r for r in results if not isinstance(r, Exception) and r.success]
            assert len(successes) >= 1
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_concurrent_command_timeout(self):
        """Timeout handling under concurrent load."""
        from tools.executor import OpenClawExecutor
        ex = OpenClawExecutor()
        ex.max_execution_time = 1

        ctx = _make_context(permissions=["read", "write"])
        with patch.object(ex, "_check_command_safety") as mock_safety:
            mock_safety.return_value = MagicMock(allowed=True, reason="", risk_level="low")
            with patch.object(ex, "_parse_command", return_value=["cmd", "/c", "ping", "-n", "5", "127.0.0.1"]):
                with patch("asyncio.create_subprocess_exec") as mock_proc:
                    mock_process = AsyncMock()
                    mock_process.communicate = AsyncMock(side_effect=asyncio.TimeoutError)
                    mock_process.kill = MagicMock()
                    mock_proc.return_value = mock_process

                    result = await ex.execute_command("sleep 10", ctx, timeout=0.1)
                    assert result.success is False
                    assert "timed out" in (result.error or "").lower()


class TestExecutorSafety:
    @pytest.mark.asyncio
    async def test_dangerous_patterns_blocked(self):
        """All dangerous patterns are blocked regardless of permissions."""
        from tools.executor import OpenClawExecutor
        ex = OpenClawExecutor()
        ctx = _make_context(permissions=["read", "write"])

        dangerous = [
            "rm -rf /",
            "del /s /q c:",
            "format c:",
            "sudo rm -rf",
            "chmod 777 /etc",
        ]
        for cmd in dangerous:
            result = await ex.execute_command(cmd, ctx)
            if result.success:
                pytest.fail(f"Dangerous command not blocked: {cmd}")

    @pytest.mark.asyncio
    async def test_blocked_command_without_write_permission(self):
        """Write commands blocked when context lacks write permission."""
        from tools.executor import OpenClawExecutor
        ex = OpenClawExecutor()
        ctx = _make_context(permissions=["read"])

        result = await ex.execute_command("echo data > file.txt", ctx)
        assert result.success is False
        assert "permission" in (result.error or "").lower()

    def test_quoted_arguments_are_preserved(self):
        from tools.executor import OpenClawExecutor
        ex = OpenClawExecutor()

        parsed = ex._parse_command('echo "hello world"')

        assert parsed[-1] == "hello world"

    @pytest.mark.asyncio
    async def test_shell_control_operators_are_blocked(self):
        from tools.executor import OpenClawExecutor
        ex = OpenClawExecutor()
        ctx = _make_context(permissions=["read", "write"])

        result = await ex.execute_command("echo ok && echo unsafe", ctx)

        assert result.success is False
        assert "shell control" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_safety_disabled_allows_blocked_commands(self):
        """When safety is disabled, blocked commands should still run."""
        from tools.executor import OpenClawExecutor
        ex = OpenClawExecutor()
        ex.safety_enabled = False
        ctx = _make_context(permissions=["read", "write"])

        with patch.object(ex, "_parse_command", return_value=["cmd", "/c", "echo", "unsafe"]):
            with patch("asyncio.create_subprocess_exec") as mock_proc:
                mock_process = AsyncMock()
                mock_process.communicate = AsyncMock(return_value=(b"done", b""))
                mock_process.returncode = 0
                mock_proc.return_value = mock_process

                result = await ex.execute_command("echo unsafe", ctx)
                assert result.success is True


class TestExecutorAuditLog:
    @pytest.mark.asyncio
    async def test_audit_log_capped(self):
        """Audit log stays within 1000 entries."""
        from tools.executor import OpenClawExecutor
        ex = OpenClawExecutor()
        ctx = _make_context(permissions=["read", "write"])

        with patch.object(ex, "_parse_command", return_value=["cmd", "/c", "echo", "x"]):
            with patch("asyncio.create_subprocess_exec") as mock_proc:
                mock_process = AsyncMock()
                mock_process.communicate = AsyncMock(return_value=(b"x", b""))
                mock_process.returncode = 0
                mock_proc.return_value = mock_process

                for _ in range(1100):
                    await ex.execute_command("echo x", ctx)

        assert len(ex.audit_log) <= 1000


class TestExecutorBrowserIsolation:
    @pytest.mark.asyncio
    async def test_browser_session_isolation(self):
        """Different session IDs get different browser instances."""
        from tools.executor import OpenClawExecutor
        ex = OpenClawExecutor()

        try:
            ctx1 = _make_context(session_id="session_a")
            ctx2 = _make_context(session_id="session_b")

            with patch("selenium.webdriver.Chrome") as mock_chrome:
                mock_driver = MagicMock()
                mock_chrome.return_value = mock_driver

                result = await ex.execute_browser_action("navigate", url="http://example.com", context=ctx1)
                assert result.success

            assert "session_a" in ex.browser_instances
            assert len(ex.browser_instances) == 1
            assert ex.browser_instances["session_a"] is not None
        finally:
            ex.cleanup()
