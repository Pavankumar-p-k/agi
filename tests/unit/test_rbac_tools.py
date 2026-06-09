import pytest


class TestNonAdminBlockedTools:
    def test_blocklist_contains_critical_tools(self):
        from core.tools.security import NON_ADMIN_BLOCKED_TOOLS
        assert "bash" in NON_ADMIN_BLOCKED_TOOLS
        assert "shell" in NON_ADMIN_BLOCKED_TOOLS
        assert "shell_command" in NON_ADMIN_BLOCKED_TOOLS
        assert "python" in NON_ADMIN_BLOCKED_TOOLS
        assert "read_file" in NON_ADMIN_BLOCKED_TOOLS
        assert "write_file" in NON_ADMIN_BLOCKED_TOOLS

    def test_blocklist_excludes_safe_tools(self):
        from core.tools.security import NON_ADMIN_BLOCKED_TOOLS
        assert "search" not in NON_ADMIN_BLOCKED_TOOLS
        assert "read" not in NON_ADMIN_BLOCKED_TOOLS
        assert "suggest" not in NON_ADMIN_BLOCKED_TOOLS

    def test_is_public_blocked_tool_true_for_blocked(self):
        from core.tools.security import is_public_blocked_tool
        assert is_public_blocked_tool("bash") is True
        assert is_public_blocked_tool("shell_command") is True

    def test_is_public_blocked_tool_false_for_safe(self):
        from core.tools.security import is_public_blocked_tool
        assert is_public_blocked_tool("search") is False
        assert is_public_blocked_tool("read") is False

    def test_is_public_blocked_tool_none(self):
        from core.tools.security import is_public_blocked_tool
        assert is_public_blocked_tool(None) is False
        assert is_public_blocked_tool("") is False

    def test_blocked_tools_for_owner_non_admin(self):
        from core.tools.security import blocked_tools_for_owner
        with pytest.MonkeyPatch().context() as mp:
            mp.setattr("core.tools.security.owner_is_admin_or_single_user", lambda o: False)
            blocked = blocked_tools_for_owner("non_admin")
            assert "bash" in blocked
            assert "shell_command" in blocked

    def test_blocked_tools_for_admin(self):
        from core.tools.security import blocked_tools_for_owner
        with pytest.MonkeyPatch().context() as mp:
            mp.setattr("core.tools.security.owner_is_admin_or_single_user", lambda o: True)
            blocked = blocked_tools_for_owner("admin_user")
            assert blocked == set()
