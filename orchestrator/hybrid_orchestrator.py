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
# backend/orchestrator/hybrid_orchestrator.py
"""
Hybrid Orchestrator - Research-Grade Automation System
Combines: Claude (Planner) + AutoGPT (Autonomous) + OpenClaw (Executor) + Perplexity-style routing
"""

import asyncio
import json
import logging
import time
from typing import Dict, List, Optional, Any, Callable, Awaitable
import re

logger = logging.getLogger(__name__)

try:
    from core.types import ExecutionState, Task, ExecutionContext
except Exception as e:
    logger.warning("[orchestrator.hybrid_orchestrator] core.types import failed: %s", e)
    ExecutionState = Task = ExecutionContext = None
try:
    from models.hybrid_models import hybrid_manager, TaskType, ModelResult
except Exception as e:
    logger.warning("[orchestrator.hybrid_orchestrator] hybrid_models import failed: %s", e)
    hybrid_manager = TaskType = ModelResult = None
try:
    from tools.executor import OpenClawExecutor
except Exception as e:
    logger.warning("[orchestrator.hybrid_orchestrator] tools.executor import failed: %s", e)
    OpenClawExecutor = None
try:
    from core.config import HYBRID_MAX_RETRIES
except Exception as e:
    logger.warning("[orchestrator.hybrid_orchestrator] core.config HYBRID_MAX_RETRIES failed: %s", e)
    HYBRID_MAX_RETRIES = 3


class HybridOrchestrator:
    """
    Research-grade hybrid orchestrator implementing:
    - Claude-based planning (strategic decomposition)
    - AutoGPT-style autonomous execution (recursive task breakdown)
    - OpenClaw-style real-world execution (system access)
    - Perplexity-style multi-model routing (optimal model selection)
    """

    def __init__(self):
        from core.config import HYBRID_MAX_RETRIES
        try:
            from jarvis_os.memory.memory_manager import MemoryManager
        except ImportError:
            MemoryManager = None
        try:
            from tools.executor import OpenClawExecutor
        except Exception as e:
            logger.warning("[orchestrator.hybrid_orchestrator] OpenClawExecutor init import failed: %s", e)
            OpenClawExecutor = None

        from dataclasses import dataclass
        
        @dataclass
        class MemoryConfig:
            short_term_limit: int = 100
            data_dir: str = "data/memory"
        
        self.memory = MemoryManager(MemoryConfig()) if MemoryManager else None
        self.executor = OpenClawExecutor() if OpenClawExecutor else None
        self.active_tasks: Dict[str, Task] = {}
        self.task_history: List[Task] = []
        self.performance_metrics = {
            "total_tasks": 0,
            "successful_tasks": 0,
            "failed_tasks": 0,
            "average_execution_time": 0.0,
            "model_usage": {}
        }

    async def execute_goal(
        self,
        goal: str,
        context: ExecutionContext,
        max_depth: int = 5,
        timeout_minutes: int = 30
    ) -> Dict[str, Any]:
        """
        Execute a high-level goal using hybrid automation approach
        Returns comprehensive execution report
        """

        start_time = time.time()
        root_task = Task(
            id=f"goal_{int(start_time)}",
            description=goal,
            goal=goal
        )

        self.active_tasks[root_task.id] = root_task

        try:
            # Phase 1: Strategic Planning (Claude)
            plan = await self._strategic_planning(goal, context)

            # Phase 2: Task Decomposition (AutoGPT-style)
            root_task.subtasks = await self._decompose_into_tasks(plan, context, max_depth)

            # Phase 3: Parallel Execution with Dependencies
            await self._execute_task_tree(root_task, context, timeout_minutes * 60)

            # Phase 4: Result Synthesis
            result = await self._synthesize_results(root_task, context)

            execution_time = time.time() - start_time
            root_task.execution_time = execution_time
            root_task.completed_at = time.time()
            root_task.state = ExecutionState.COMPLETED

            # Update metrics
            self._update_metrics(root_task, True)

            return {
                "success": True,
                "goal": goal,
                "result": result,
                "execution_time": execution_time,
                "tasks_executed": len(root_task.subtasks),
                "model_usage": self._get_model_usage_report(root_task),
                "performance": self.performance_metrics.copy()
            }

        except Exception as e:
            root_task.state = ExecutionState.FAILED
            root_task.error = str(e)
            root_task.completed_at = time.time()
            self._update_metrics(root_task, False)

            return {
                "success": False,
                "goal": goal,
                "error": str(e),
                "execution_time": time.time() - start_time,
                "partial_results": self._get_partial_results(root_task)
            }

        finally:
            # Cleanup
            if root_task.id in self.active_tasks:
                del self.active_tasks[root_task.id]
            self.task_history.append(root_task)

    async def _strategic_planning(self, goal: str, context: ExecutionContext) -> Dict[str, Any]:
        """Phase 1: Use Claude for high-level strategic planning"""

        planning_prompt = f"""
You are JARVIS, a strategic AI planner. Break down this goal into a detailed execution plan:

GOAL: {goal}

CONTEXT:
- User: {context.user_id}
- Platform: {context.platform}
- Available Permissions: {', '.join(context.permissions)}
- Memory Context: {json.dumps(context.memory_context, indent=2)}

Create a structured plan with:
1. Main objectives
2. Required capabilities
3. Potential challenges
4. Success criteria
5. Risk mitigation strategies

Format as JSON with these keys: objectives, capabilities, challenges, success_criteria, risk_mitigation
"""

        result = await hybrid_manager.generate_with_fallback(
            prompt=planning_prompt,
            task_type=TaskType.PLANNING,
            system_prompt="You are a strategic planner. Always respond with valid JSON.",
            temperature=0.3,
            max_tokens=2048
        )

        try:
            plan = json.loads(result.response)
            return plan
        except json.JSONDecodeError:
            # Fallback to basic plan
            return {
                "objectives": [goal],
                "capabilities": ["execution"],
                "challenges": [],
                "success_criteria": ["Goal completion"],
                "risk_mitigation": ["Retry on failure"]
            }

    async def _decompose_into_tasks(
        self,
        plan: Dict[str, Any],
        context: ExecutionContext,
        max_depth: int
    ) -> List[Task]:
        """Phase 2: AutoGPT-style recursive task decomposition"""

        decomposition_prompt = f"""
You are JARVIS, an autonomous task decomposer. Break down this plan into executable tasks:

PLAN: {json.dumps(plan, indent=2)}

Create a hierarchical task list where each task is:
- Specific and actionable
- Has clear success criteria
- Can be executed independently
- Includes dependencies where needed

Format as JSON array of tasks with: id, description, dependencies, success_criteria
"""

        result = await hybrid_manager.generate_with_fallback(
            prompt=decomposition_prompt,
            task_type=TaskType.REASONING,
            system_prompt="You are a task decomposition expert. Always respond with valid JSON.",
            temperature=0.2,
            max_tokens=1536
        )

        try:
            task_data = json.loads(result.response)
            tasks = []

            for item in task_data:
                task = Task(
                    id=item.get("id", f"task_{len(tasks)}"),
                    description=item.get("description", ""),
                    goal=item.get("description", ""),
                    dependencies=item.get("dependencies", []),
                    max_attempts=3
                )
                tasks.append(task)

            return tasks

        except json.JSONDecodeError:
            # Fallback to single task
            return [Task(
                id="fallback_task",
                description=plan.get("objectives", ["Execute goal"])[0],
                goal=str(plan)
            )]

    async def _execute_task_tree(
        self,
        root_task: Task,
        context: ExecutionContext,
        timeout_seconds: float
    ):
        """Phase 3: Execute task tree with dependency management"""

        start_time = time.time()
        completed_tasks = set()
        pending_tasks = {task.id: task for task in root_task.subtasks}

        while pending_tasks and (time.time() - start_time) < timeout_seconds:
            # Find tasks with satisfied dependencies
            executable_tasks = [
                task for task in pending_tasks.values()
                if all(dep in completed_tasks for dep in task.dependencies)
            ]

            if not executable_tasks:
                # Circular dependency or stuck - break
                break

            # Execute tasks in parallel (limit concurrency)
            execution_tasks = []
            for task in executable_tasks[:5]:  # Max 5 concurrent
                execution_tasks.append(self._execute_single_task(task, context))

            if execution_tasks:
                results = await asyncio.gather(*execution_tasks, return_exceptions=True)

                for task, result in zip(executable_tasks, results):
                    if isinstance(result, Exception):
                        task.error = str(result)
                        task.state = ExecutionState.FAILED
                    else:
                        task.result = result
                        task.state = ExecutionState.COMPLETED
                        completed_tasks.add(task.id)

                    del pending_tasks[task.id]

        # Mark remaining tasks as failed due to timeout
        for task in pending_tasks.values():
            task.state = ExecutionState.FAILED
            task.error = "Timeout or dependency failure"

    async def _execute_single_task(self, task: Task, context: ExecutionContext) -> Any:
        """Execute a single task using OpenClaw executor"""

        task.state = ExecutionState.EXECUTING
        task.attempts += 1

        try:
            # Determine execution approach based on task type
            execution_prompt = f"""
Execute this task: {task.description}

Context: {json.dumps(context.variables, indent=2)}
Goal: {task.goal}

Determine the best execution approach:
1. If this requires system actions (file operations, commands, etc.), use EXECUTE
2. If this requires analysis or reasoning, use ANALYZE
3. If this requires code generation, use CODE
4. If this requires external API calls, use API

Respond with JSON: {{"approach": "EXECUTE|ANALYZE|CODE|API", "command": "specific command or analysis needed"}}
"""

            # Get execution plan from AI
            plan_result = await hybrid_manager.generate_with_fallback(
                prompt=execution_prompt,
                task_type=TaskType.EXECUTION,
                temperature=0.1,
                max_tokens=512
            )

            try:
                plan = json.loads(plan_result.response)
                approach = plan.get("approach", "EXECUTE")
                command = plan.get("command", task.description)

                # Execute based on approach
                if approach == "EXECUTE":
                    result = await self.executor.execute_command(command, context)
                elif approach == "ANALYZE":
                    result = await self._analyze_task(command, context)
                elif approach == "CODE":
                    result = await self._generate_code(command, context)
                elif approach == "API":
                    result = await self._call_external_api(command, context)
                else:
                    result = await self.executor.execute_command(command, context)

                task.model_used = plan_result.model
                task.confidence = plan_result.confidence
                return result

            except json.JSONDecodeError:
                # Fallback to direct execution
                return await self.executor.execute_command(task.description, context)

        except Exception as e:
            if task.attempts < task.max_attempts:
                task.state = ExecutionState.RETRYING
                await asyncio.sleep(1 * task.attempts)  # Exponential backoff
                return await self._execute_single_task(task, context)
            else:
                raise e

    async def _analyze_task(self, query: str, context: ExecutionContext) -> Dict[str, Any]:
        """Analyze task using appropriate model"""
        result = await hybrid_manager.generate_with_fallback(
            prompt=query,
            task_type=TaskType.ANALYSIS,
            temperature=0.3,
            max_tokens=1024
        )
        return {
            "analysis": result.response,
            "model": result.model,
            "confidence": result.confidence
        }

    async def _generate_code(self, requirement: str, context: ExecutionContext) -> Dict[str, Any]:
        """Generate code using coding-specialized model"""
        result = await hybrid_manager.generate_with_fallback(
            prompt=f"Generate code for: {requirement}",
            task_type=TaskType.CODING,
            temperature=0.2,
            max_tokens=2048
        )
        return {
            "code": result.response,
            "model": result.model,
            "language": self._detect_language(result.response)
        }

    async def _call_external_api(self, api_request: str, context: ExecutionContext) -> Dict[str, Any]:
        """Handle external API calls"""
        # This would integrate with various APIs based on the request
        return {
            "api_call": api_request,
            "result": "API integration placeholder",
            "status": "not_implemented"
        }

    async def _synthesize_results(self, root_task: Task, context: ExecutionContext) -> Dict[str, Any]:
        """Phase 4: Synthesize results from all subtasks"""

        successful_tasks = [t for t in root_task.subtasks if t.state == ExecutionState.COMPLETED]
        failed_tasks = [t for t in root_task.subtasks if t.state == ExecutionState.FAILED]

        synthesis_prompt = f"""
Synthesize the results of this multi-task execution:

GOAL: {root_task.goal}

SUCCESSFUL TASKS ({len(successful_tasks)}):
{chr(10).join(f"- {t.description}: {str(t.result)[:200]}..." for t in successful_tasks)}

FAILED TASKS ({len(failed_tasks)}):
{chr(10).join(f"- {t.description}: {t.error}" for t in failed_tasks)}

Provide a comprehensive summary of what was accomplished, what failed, and overall success assessment.
"""

        result = await hybrid_manager.generate_with_fallback(
            prompt=synthesis_prompt,
            task_type=TaskType.ANALYSIS,
            temperature=0.2,
            max_tokens=1024
        )

        return {
            "summary": result.response,
            "successful_tasks": len(successful_tasks),
            "failed_tasks": len(failed_tasks),
            "total_tasks": len(root_task.subtasks),
            "success_rate": len(successful_tasks) / len(root_task.subtasks) if root_task.subtasks else 0
        }

    def _detect_language(self, code: str) -> str:
        """Detect programming language from code"""
        if "def " in code or "import " in code:
            return "python"
        elif "function" in code or "const " in code:
            return "javascript"
        elif "public class" in code or "import java" in code:
            return "java"
        elif "fn " in code or "let " in code:
            return "rust"
        else:
            return "unknown"

    def _update_metrics(self, task: Task, success: bool):
        """Update performance metrics"""
        self.performance_metrics["total_tasks"] += 1
        if success:
            self.performance_metrics["successful_tasks"] += 1
        else:
            self.performance_metrics["failed_tasks"] += 1

        # Update average execution time
        total_time = self.performance_metrics["average_execution_time"] * (self.performance_metrics["total_tasks"] - 1)
        total_time += task.execution_time
        self.performance_metrics["average_execution_time"] = total_time / self.performance_metrics["total_tasks"]

        # Update model usage
        if task.model_used:
            model_usage = self.performance_metrics["model_usage"]
            model_usage[task.model_used] = model_usage.get(task.model_used, 0) + 1

    def _get_model_usage_report(self, root_task: Task) -> Dict[str, int]:
        """Get model usage statistics for a task tree"""
        usage = {}
        def count_usage(task):
            if task.model_used:
                usage[task.model_used] = usage.get(task.model_used, 0) + 1
            for subtask in task.subtasks:
                count_usage(subtask)
        count_usage(root_task)
        return usage

    def _get_partial_results(self, root_task: Task) -> Dict[str, Any]:
        """Get partial results when execution fails"""
        return {
            "completed_tasks": [
                {"description": t.description, "result": t.result}
                for t in root_task.subtasks
                if t.state == ExecutionState.COMPLETED
            ],
            "failed_tasks": [
                {"description": t.description, "error": t.error}
                for t in root_task.subtasks
                if t.state == ExecutionState.FAILED
            ]
        }

    def get_system_status(self) -> Dict[str, Any]:
        """Get comprehensive system status"""
        return {
            "active_tasks": len(self.active_tasks),
            "completed_tasks_history": len(self.task_history),
            "performance_metrics": self.performance_metrics,
            "model_performance": hybrid_manager.get_performance_report(),
            "executor_status": self.executor.get_status()
        }


# Global orchestrator instance
hybrid_orchestrator = HybridOrchestrator()