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
# backend/api/hybrid_integration.py
"""
HYBRID AUTOMATION SYSTEM INTEGRATION
Research-grade implementation combining Claude + AutoGPT + OpenClaw + Perplexity routing
"""

import time

from models.hybrid_models import TaskType, hybrid_manager
from orchestrator.hybrid_orchestrator import ExecutionContext, hybrid_orchestrator
from tools.executor import open_claw_executor


def setup_hybrid_routes(app):
    """Add hybrid automation routes to FastAPI app"""

    @app.post("/api/hybrid/execute")
    async def execute_hybrid_goal(body: dict):
        """
        Execute a goal using the full hybrid automation system
        Combines: Claude planning + AutoGPT decomposition + OpenClaw execution
        """
        goal = body.get("goal", "")
        user_id = body.get("user_id", "user")
        session_id = body.get("session_id", f"session_{int(time.time())}")
        platform = body.get("platform", "api")
        max_depth = body.get("max_depth", 5)
        timeout_minutes = body.get("timeout_minutes", 30)

        if not goal:
            return {"error": "Goal is required"}

        context = ExecutionContext(
            user_id=user_id,
            session_id=session_id,
            platform=platform,
            memory_context=body.get("memory_context", {}),
            variables=body.get("variables", {}),
            permissions=body.get("permissions", ["read", "execute"])
        )

        try:
            result = await hybrid_orchestrator.execute_goal(
                goal=goal,
                context=context,
                max_depth=max_depth,
                timeout_minutes=timeout_minutes
            )

            return {
                "status": "completed",
                "result": result
            }

        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "goal": goal
            }

    @app.post("/api/hybrid/chat")
    async def hybrid_chat(body: dict):
        """
        Enhanced chat with hybrid model fallback and automation capabilities
        """
        message = body.get("message", "")
        user_id = body.get("user_id", "user")
        context_vars = body.get("context", {})

        if not message:
            return {"error": "Message is required"}

        # Determine task type from message
        task_type = TaskType.CHAT
        if any(keyword in message.lower() for keyword in ["analyze", "review", "examine"]):
            task_type = TaskType.ANALYSIS
        elif any(keyword in message.lower() for keyword in ["code", "program", "script", "function"]):
            task_type = TaskType.CODING
        elif any(keyword in message.lower() for keyword in ["plan", "strategy", "approach"]):
            task_type = TaskType.PLANNING
        elif any(keyword in message.lower() for keyword in ["execute", "run", "do", "perform"]):
            task_type = TaskType.EXECUTION

        # Check if this is an automation request
        automation_triggers = [
            "automate", "execute task", "run workflow", "perform action",
            "open app", "launch program", "send message", "make call"
        ]

        if any(trigger in message.lower() for trigger in automation_triggers):
            # Use full hybrid execution
            context = ExecutionContext(
                user_id=user_id,
                session_id=f"chat_{int(time.time())}",
                platform="chat",
                variables=context_vars
            )

            result = await hybrid_orchestrator.execute_goal(
                goal=message,
                context=context,
                max_depth=3,
                timeout_minutes=10
            )

            return {
                "response": result.get("result", {}).get("summary", "Task completed"),
                "automation_result": result,
                "model": "hybrid_system"
            }

        else:
            # Regular chat with fallback
            result = await hybrid_manager.generate_with_fallback(
                prompt=message,
                task_type=task_type,
                temperature=0.7,
                max_tokens=1024
            )

            return {
                "response": result.response,
                "model": result.model,
                "confidence": result.confidence,
                "latency_ms": result.latency_ms,
                "fallback_used": result.fallback_reason is not None,
                "fallback_reason": result.fallback_reason
            }

    @app.get("/api/hybrid/status")
    async def get_hybrid_status():
        """Get comprehensive system status"""
        return {
            "hybrid_orchestrator": hybrid_orchestrator.get_system_status(),
            "model_manager": hybrid_manager.get_performance_report(),
            "executor": open_claw_executor.get_status(),
            "timestamp": time.time()
        }

    @app.post("/api/hybrid/models/test")
    async def test_model_fallback(body: dict):
        """Test model fallback chain"""
        prompt = body.get("prompt", "Hello, test message")
        task_type_str = body.get("task_type", "chat")

        try:
            task_type = TaskType[task_type_str.upper()]
        except KeyError:
            return {"error": f"Invalid task type: {task_type_str}"}

        result = await hybrid_manager.generate_with_fallback(
            prompt=prompt,
            task_type=task_type,
            temperature=0.7,
            max_tokens=512
        )

        return {
            "prompt": prompt,
            "task_type": task_type_str,
            "result": {
                "provider": result.provider.value,
                "model": result.model,
                "response": result.response,
                "confidence": result.confidence,
                "latency_ms": result.latency_ms,
                "tokens_used": result.tokens_used,
                "fallback_reason": result.fallback_reason,
                "error": result.error
            }
        }

    @app.post("/api/hybrid/executor/test")
    async def test_executor(body: dict):
        """Test OpenClaw executor"""
        command = body.get("command", "echo 'Hello from OpenClaw'")
        user_id = body.get("user_id", "test_user")

        context = ExecutionContext(
            user_id=user_id,
            session_id=f"test_{int(time.time())}",
            platform="test"
        )

        result = await open_claw_executor.execute_command(command, context)

        return {
            "command": command,
            "result": {
                "success": result.success,
                "output": result.output,
                "error": result.error,
                "exit_code": result.exit_code,
                "execution_time": result.execution_time,
                "metadata": result.metadata
            }
        }

    @app.post("/api/mobile/automation")
    async def mobile_automation(body: dict):
        """
        Mobile-triggered automation endpoint
        Links mobile app commands to hybrid automation system
        """
        command = body.get("command", "")
        device_id = body.get("device_id", "unknown")
        platform = body.get("platform", "android")  # android, ios
        context_data = body.get("context", {})

        if not command:
            return {"error": "Command is required"}

        # Create execution context for mobile
        context = ExecutionContext(
            user_id=f"mobile_{device_id}",
            session_id=f"mobile_{int(time.time())}",
            platform=platform,
            variables={
                "device_id": device_id,
                "mobile_platform": platform,
                **context_data
            },
            permissions=["read", "execute", "mobile"]  # Mobile-specific permissions
        )

        # Execute via hybrid orchestrator
        result = await hybrid_orchestrator.execute_goal(
            goal=f"Mobile command: {command}",
            context=context,
            max_depth=3,
            timeout_minutes=5
        )

        return {
            "command": command,
            "device_id": device_id,
            "result": result,
            "executed_at": time.time()
        }

    @app.post("/api/mobile/sync")
    async def mobile_sync(body: dict):
        """
        Sync mobile app data with automation system
        """
        device_id = body.get("device_id", "unknown")
        sync_data = body.get("data", {})

        # Store sync data in memory for context
        sync_key = f"mobile_sync_{device_id}"
        # In a real implementation, this would go to a database

        return {
            "status": "synced",
            "device_id": device_id,
            "data_points": len(sync_data),
            "timestamp": time.time()
        }


# Integration instructions for main.py
INTEGRATION_INSTRUCTIONS = """
# Add to main.py:

# 1. Import hybrid integration
from api.hybrid_integration import setup_hybrid_routes

# 2. Add to startup event
@app.on_event("startup")
async def on_startup():
    # ... existing startup code ...
    await hybrid_manager._init_clients()
    print("[Main] Hybrid Automation System ready [OK]")

# 3. Setup routes (after other app.include_router calls)
setup_hybrid_routes(app)

# 4. Environment variables needed:
# CLAUDE_API_KEY=your_claude_key
# COPILOT_API_KEY=your_copilot_key
# GITHUB_TOKEN=your_github_token
# CODEX_CLI_PATH=/path/to/codex/cli
"""
