"""tests/test_computer_agent.py — Tests for pc_agent/computer_agent.py."""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock


class TestComputerAgentInit:
    def test_init_creates_dirs(self):
        with patch("os.makedirs") as mock_mkdir:
            from pc_agent.computer_agent import ComputerAgent
            agent = ComputerAgent(db_path="/tmp/test.db")
            assert agent.db_path == "/tmp/test.db"

    def test_init_with_governance_and_sandbox(self):
        with patch("pc_agent.computer_agent.GovernanceValidator") as mock_gov:
            with patch("pc_agent.computer_agent.SandboxedExecutor") as mock_sb:
                from pc_agent.computer_agent import ComputerAgent
                agent = ComputerAgent()
                assert agent.governance is not None
                assert agent.sandbox is not None


class TestComputerAgent:
    @pytest.fixture
    def agent(self):
        with patch("pc_agent.computer_agent.GovernanceValidator") as mock_gov:
            with patch("pc_agent.computer_agent.SandboxedExecutor") as mock_sb:
                from pc_agent.computer_agent import ComputerAgent
                agent = ComputerAgent(db_path="/tmp/test.db")
                agent._interpreter = MagicMock()
                agent._interpreter.chat.return_value = "done"
                yield agent

    def test_get_interpreter_lazy(self):
        with patch("pc_agent.computer_agent.GovernanceValidator"):
            with patch("pc_agent.computer_agent.SandboxedExecutor"):
                from pc_agent.computer_agent import ComputerAgent
                agent = ComputerAgent()
                assert agent._interpreter is None
                with patch("interpreter.interpreter") as mock_interp:
                    interp = agent._get_interpreter()
                    assert interp is not None
                    assert agent._interpreter is not None

    @pytest.mark.asyncio
    async def test_get_screen_context_fallback(self, agent):
        import PIL
        PIL.ImageGrab = MagicMock()
        PIL.ImageGrab.grab.return_value = MagicMock()
        result = await agent.get_screen_context()
        assert "Screen capture" in result or "screen" in result.lower()

    @pytest.mark.asyncio
    async def test_execute_natural_language_sandbox_blocked(self, agent):
        agent.sandbox.execute.return_value = {"success": False, "sandbox_blocked": True, "error": "Blocked"}
        result = await agent.execute_natural_language("do something")
        assert result["status"] == "blocked"

    @pytest.mark.asyncio
    async def test_execute_natural_language_success(self, agent):
        agent.sandbox.execute.return_value = {"success": True}
        with patch.object(agent, "get_screen_context", return_value="screen ok"):
            with patch.object(agent, "_log_action"):
                result = await agent.execute_natural_language("do something")
                assert result["status"] == "success"
                assert result["result"] == "done"

    @pytest.mark.asyncio
    async def test_execute_natural_language_governance_violation(self, agent):
        from governance.exceptions import GovernanceViolation
        agent.governance.validate_execution.side_effect = GovernanceViolation("test")
        result = await agent.execute_natural_language("bad command")
        assert result["status"] == "blocked"
        assert "Governance violation" in result["reason"]

    def test_log_action(self, agent):
        with patch("sqlite3.connect") as mock_conn:
            agent._log_action("test instruction", "test result")
            assert mock_conn.called
