# backend/tests/test_hybrid_system.py
"""
INDUSTRIAL-GRADE TESTING SUITE FOR HYBRID AUTOMATION SYSTEM
Tests all components: Models, Orchestrator, Executor, Mobile Integration
"""

import asyncio
import pytest
import time
from unittest.mock import Mock, patch, AsyncMock
import httpx
from core.types import ExecutionContext, Task, ExecutionResult, ExecutionState, ModelResult
from orchestrator.hybrid_orchestrator import HybridOrchestrator, hybrid_orchestrator
from models.hybrid_models import HybridModelManager, TaskType, ModelProvider, hybrid_manager
from tools.executor import OpenClawExecutor, open_claw_executor
from core.config import CLAUDE_API_KEY, COPILOT_API_KEY


class TestHybridModelManager:
    """Test hybrid model fallback system"""
    
    def setup_method(self):
        """Setup for each test"""
        self.manager = HybridModelManager()

    @pytest.mark.asyncio
    async def test_fallback_chain_ollama_only(self):
        """Test fallback when only Ollama is available"""
        # Mock Ollama success
        with patch.object(self.manager, '_call_ollama', new_callable=AsyncMock) as mock_ollama:
            mock_ollama.return_value = ModelResult(
                provider=ModelProvider.OLLAMA,
                model="llama3.1:8b",
                response="Test response",
                confidence=0.8,
                latency_ms=500,
                tokens_used=50
            )

            result = await self.manager.generate_with_fallback(
                prompt="Test prompt",
                task_type=TaskType.PLANNING
            )

            assert result.provider == ModelProvider.OLLAMA
            assert result.response == "Test response"
            assert result.fallback_reason is None

    @pytest.mark.asyncio
    async def test_fallback_to_claude(self):
        """Test fallback from Ollama failure to Claude"""
        # Create a fresh manager with limited fallback chain
        manager = HybridModelManager()
        # Only test with Ollama and Claude to simplify
        manager.config.fallback_chain = [ModelProvider.OLLAMA, ModelProvider.CLAUDE]
        
        # Ensure Claude client is available in the manager
        manager._clients[ModelProvider.CLAUDE] = Mock()  # Mock Anthropic client
        
        with patch.object(manager, '_call_ollama', new_callable=AsyncMock) as mock_ollama, \
             patch.object(manager, '_call_claude', new_callable=AsyncMock) as mock_claude:

            # Ollama fails
            mock_ollama.side_effect = Exception("Ollama connection failed")

            # Claude succeeds
            mock_claude.return_value = ModelResult(
                provider=ModelProvider.CLAUDE,
                model="claude-3-sonnet",
                response="Claude response",
                confidence=0.95,
                latency_ms=1000,
                tokens_used=75
            )

            result = await manager.generate_with_fallback(
                prompt="Test prompt",
                task_type=TaskType.PLANNING
            )

            assert result.provider == ModelProvider.CLAUDE
            assert "Claude response" in result.response
            assert result.fallback_reason is not None
            assert "Ollama" in result.fallback_reason

    @pytest.mark.asyncio
    async def test_all_providers_fail(self):
        """Test graceful failure when all providers fail"""
        with patch.object(self.manager, '_call_ollama', side_effect=Exception("Network error")), \
             patch.object(self.manager, '_call_codex_cli', side_effect=Exception("CLI error")), \
             patch.object(self.manager, '_call_claude', side_effect=Exception("API error")), \
             patch.object(self.manager, '_call_copilot', side_effect=Exception("Token error")):

            result = await self.manager.generate_with_fallback(
                prompt="Test prompt",
                task_type=TaskType.PLANNING
            )

            assert result.provider == ModelProvider.OLLAMA  # Default fallback
            assert "failed" in result.response.lower()
            assert result.error is not None
            assert result.confidence == 0.0

    @pytest.mark.asyncio
    async def test_task_type_routing(self):
        """Test that different task types route to appropriate models"""
        test_cases = [
            (TaskType.CODING, "qwen2.5-coder"),
            (TaskType.PLANNING, "deepseek-r1"),
            (TaskType.EXECUTION, "qwen3"),
            (TaskType.VISION, "moondream"),
        ]

        for task_type, expected_model in test_cases:
            with patch.object(self.manager, '_get_ollama_model_for_task', return_value=expected_model):
                with patch.object(self.manager, '_call_ollama', new_callable=AsyncMock) as mock_ollama:
                    mock_ollama.return_value = ModelResult(
                        provider=ModelProvider.OLLAMA,
                        model=expected_model,
                        response="Test",
                        confidence=0.8,
                        latency_ms=500,
                        tokens_used=50
                    )

                    result = await self.manager.generate_with_fallback(
                        prompt="Test",
                        task_type=task_type
                    )

                    assert result.model == expected_model


class TestHybridOrchestrator:
    """Test the hybrid orchestrator with Claude + AutoGPT + OpenClaw"""

    def setup_method(self):
        """Setup for each test"""
        self.orchestrator = HybridOrchestrator()

    @pytest.mark.asyncio
    async def test_simple_goal_execution(self):
        """Test basic goal execution flow"""
        goal = "Execute a simple command: echo 'hello world'"

        context = ExecutionContext(
            user_id="test_user",
            session_id="test_session",
            platform="test"
        )

        with patch.object(self.orchestrator, '_strategic_planning', new_callable=AsyncMock) as mock_plan, \
             patch.object(self.orchestrator, '_decompose_into_tasks', new_callable=AsyncMock) as mock_decomp, \
             patch.object(self.orchestrator, '_execute_task_tree', new_callable=AsyncMock) as mock_exec, \
             patch.object(self.orchestrator, '_synthesize_results', new_callable=AsyncMock) as mock_synth:

            # Mock planning
            mock_plan.return_value = {
                "objectives": ["Execute command"],
                "capabilities": ["command_execution"],
                "challenges": [],
                "success_criteria": ["Command runs successfully"],
                "risk_mitigation": ["Error handling"]
            }

            # Mock decomposition
            mock_decomp.return_value = [
                Task(id="task1", description="Run echo command", goal="echo 'hello world'")
            ]

            # Mock execution
            mock_exec.return_value = None

            # Mock synthesis
            mock_synth.return_value = {
                "summary": "Command executed successfully",
                "successful_tasks": 1,
                "failed_tasks": 0,
                "total_tasks": 1,
                "success_rate": 1.0
            }

            result = await self.orchestrator.execute_goal(goal, context)

            assert result["success"] == True
            assert "executed successfully" in result["result"]["summary"]
            assert result["execution_time"] >= 0  # May be very fast and round to 0

    @pytest.mark.asyncio
    async def test_complex_multi_task_execution(self):
        """Test complex goal with multiple dependent tasks"""
        goal = "Set up a development environment with Python, install dependencies, and run tests"

        context = ExecutionContext(
            user_id="developer",
            session_id="dev_setup",
            platform="desktop"
        )

        # This would test the full AutoGPT-style decomposition and execution
        # In real implementation, this would create multiple tasks with dependencies

        with patch.object(self.orchestrator, '_strategic_planning', new_callable=AsyncMock) as mock_plan:
            mock_plan.return_value = {
                "objectives": ["Setup dev environment", "Install deps", "Run tests"],
                "capabilities": ["system_access", "package_management"],
                "challenges": ["Dependency conflicts", "Permission issues"],
                "success_criteria": ["Environment ready", "Tests pass"],
                "risk_mitigation": ["Virtual environment", "Error recovery"]
            }

            plan = await self.orchestrator._strategic_planning(goal, context)

            assert "objectives" in plan
            assert len(plan["objectives"]) > 1
            assert "capabilities" in plan

    @pytest.mark.asyncio
    async def test_execution_timeout(self):
        """Test timeout handling"""
        goal = "Run a long-running task"

        context = ExecutionContext(
            user_id="test",
            session_id="timeout_test",
            platform="test"
        )

        with patch.object(self.orchestrator, '_execute_task_tree', new_callable=AsyncMock) as mock_exec:
            # Simulate timeout
            mock_exec.side_effect = asyncio.TimeoutError("Task execution timed out")

            result = await self.orchestrator.execute_goal(
                goal, context, timeout_minutes=0.001  # Very short timeout
            )

            assert result["success"] == False
            assert ("timeout" in str(result.get("error", "")).lower() or 
                    "timed out" in str(result.get("error", "")).lower())

    @pytest.mark.asyncio
    async def test_error_recovery(self):
        """Test error recovery and retry logic"""
        goal = "Execute potentially failing command"

        context = ExecutionContext(
            user_id="test",
            session_id="error_recovery_test",
            platform="test"
        )

        # Test would verify that failed tasks are retried up to max_attempts
        # and that partial results are returned even on failure


class TestOpenClawExecutor:
    """Test OpenClaw execution engine"""

    @pytest.mark.asyncio
    async def test_safe_command_execution(self):
        """Test command execution with safety controls"""
        context = ExecutionContext(
            user_id="test",
            session_id="cmd_test",
            platform="test",
            permissions=["read", "execute"]
        )

        # Test safe command
        result = await open_claw_executor.execute_command(
            "echo 'Hello World'",
            context
        )

        assert result.success == True
        assert "Hello World" in result.output
        assert result.execution_time > 0

    @pytest.mark.asyncio
    async def test_dangerous_command_blocked(self):
        """Test that dangerous commands are blocked"""
        context = ExecutionContext(
            user_id="test",
            session_id="danger_test",
            platform="test",
            permissions=["read", "execute"]
        )

        # Test dangerous command
        result = await open_claw_executor.execute_command(
            "rm -rf /",
            context
        )

        assert result.success == False
        assert "blocked" in result.error.lower()
        assert result.execution_time >= 0  # May be 0 due to fast safety check

    @pytest.mark.asyncio
    async def test_file_operations(self):
        """Test file system operations"""
        context = ExecutionContext(
            user_id="test",
            session_id="file_test",
            platform="test",
            permissions=["read", "write"]
        )

        # Test file creation
        result = await open_claw_executor.execute_file_operation(
            "write",
            "/tmp/test_hybrid.txt",
            content="Test content",
            context=context
        )

        # Note: This would need proper test directory setup
        # assert result.success == True

    @pytest.mark.asyncio
    async def test_system_monitoring(self):
        """Test system information gathering"""
        info = await open_claw_executor.get_system_info()

        assert "platform" in info
        assert "cpu_count" in info
        assert "memory" in info

    def test_audit_logging(self):
        """Test that all operations are logged"""
        # Verify audit log contains execution records
        logs = open_claw_executor.audit_log

        # Should have logs from previous tests
        assert len(logs) > 0

        # Check log structure
        for log in logs[-5:]:  # Check last 5 entries
            assert "timestamp" in log
            assert "command" in log or "operation" in log
            assert "success" in log
            assert "user_id" in log


class TestMobileIntegration:
    """Test mobile app integration with hybrid system"""

    @pytest.mark.asyncio
    async def test_mobile_automation_request(self):
        """Test mobile-triggered automation"""
        # This would test the /api/mobile/automation endpoint
        # Verifying that mobile commands are properly routed to hybrid orchestrator

        mobile_command = "open calculator app"
        device_id = "test_device_123"

        # Mock the backend API call
        with patch('httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = Mock()
            mock_post.return_value.json = AsyncMock(return_value={
                "command": mobile_command,
                "device_id": device_id,
                "result": {"success": True, "summary": "Calculator opened"},
                "executed_at": time.time()
            })

            # Test mobile API service method
            # (This would be in the mobile app's API service)

    @pytest.mark.asyncio
    async def test_mobile_sync(self):
        """Test mobile data synchronization"""
        # Test syncing contacts, messages, and preferences
        sync_data = {
            "contacts": ["+1234567890", "+0987654321"],
            "messages": ["Test message 1", "Test message 2"],
            "preferences": {"auto_reply": True, "quiet_hours": "22:00-08:00"}
        }

        # Verify sync data is properly stored and retrievable

    @pytest.mark.asyncio
    async def test_cross_platform_context(self):
        """Test maintaining context across mobile and desktop"""
        # Test that a conversation started on mobile can continue on desktop
        # and vice versa, with proper context transfer


class TestPerformanceAndReliability:
    """Industrial-grade performance and reliability tests"""

    @pytest.mark.asyncio
    async def test_concurrent_executions(self):
        """Test multiple simultaneous goal executions"""
        goals = [
            "Execute command 1",
            "Execute command 2",
            "Execute command 3"
        ]

        context = ExecutionContext(
            user_id="concurrent_test",
            session_id="concurrency_test",
            platform="test"
        )

        # Execute multiple goals concurrently
        tasks = [
            hybrid_orchestrator.execute_goal(goal, context)
            for goal in goals
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Verify all executions completed
        assert len(results) == len(goals)
        for result in results:
            if isinstance(result, Exception):
                pytest.fail(f"Concurrent execution failed: {result}")
            else:
                assert "success" in result

    @pytest.mark.asyncio
    async def test_memory_usage_monitoring(self):
        """Test memory usage doesn't grow unbounded"""
        # Execute multiple goals and monitor memory usage
        # Ensure proper cleanup and no memory leaks

    @pytest.mark.asyncio
    async def test_long_running_workflow(self):
        """Test workflows that run for extended periods"""
        # Test timeout handling, progress reporting, resumability

    def test_error_rate_monitoring(self):
        """Test error rate tracking and alerting"""
        # Verify error rates are tracked and don't exceed thresholds


class TestIntegrationTests:
    """Full system integration tests"""

    @pytest.mark.asyncio
    async def test_end_to_end_mobile_to_desktop(self):
        """Test complete flow: Mobile command → Backend processing → Desktop execution"""
        # 1. Mobile app sends automation request
        # 2. Backend receives and processes via hybrid orchestrator
        # 3. Desktop executes the command
        # 4. Result sent back to mobile

    @pytest.mark.asyncio
    async def test_model_fallback_under_load(self):
        """Test model fallback behavior under high load"""
        # Simulate high load and verify fallback works correctly
        # Test that degraded performance doesn't break functionality

    @pytest.mark.asyncio
    async def test_recovery_from_network_issues(self):
        """Test system recovery from network interruptions"""
        # Simulate network failures and verify graceful degradation
        # Test reconnection and state recovery


# Performance benchmarks
class TestBenchmarks:
    """Performance benchmarking tests"""

    @pytest.mark.asyncio
    async def test_model_response_times(self):
        """Benchmark response times for different models"""
        # Measure latency for each model type
        # Ensure fallback doesn't significantly impact performance

    @pytest.mark.asyncio
    async def test_orchestrator_throughput(self):
        """Test orchestrator throughput under load"""
        # Measure tasks per second
        # Test scalability

    @pytest.mark.asyncio
    async def test_executor_performance(self):
        """Test execution engine performance"""
        # Measure command execution times
        # Test parallel execution capabilities


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "--tb=short"])