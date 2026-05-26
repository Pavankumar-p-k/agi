"""core/agent_executor.py
Executes plan steps by running the appropriate CLI agent via subprocess.
Handles verification, timeouts, error reporting, and progress updates.
"""

import asyncio
import subprocess
import os
import json
import logging
from datetime import datetime
from typing import Optional, Callable, Any

from .agent_registry import AGENTS, get_agent, get_best_agent

logger = logging.getLogger("agent_executor")


class AgentChannel:
    """Structured communication between agent steps"""
    def __init__(self):
        self._store = {}

    def publish(self, step_id: int, key: str, value: Any):
        self._store[f"{step_id}:{key}"] = value

    def read(self, step_id: int, key: str) -> Any:
        return self._store.get(f"{step_id}:{key}")

    def pass_to_next(self, from_step: int, to_step: int):
        prefix = f"{from_step}:"
        for k, v in list(self._store.items()):
            if k.startswith(prefix):
                new_key = f"{to_step}:{k[len(prefix):]}"
                self._store[new_key] = v


async def execute_parallel(steps: list, progress_callback: Optional[Callable] = None) -> list:
    """
    Finds independent steps (no shared files / no depends_on).
    Runs them simultaneously with asyncio.gather().
    Returns all results.
    """
    independent = [s for s in steps if not s.get("depends_on")]
    dependent = [s for s in steps if s.get("depends_on")]

    executor = AgentExecutor(progress_callback=progress_callback)

    async def run_step(step):
        return await executor._execute_step(
            step["id"], step.get("agent", "shell"),
            step.get("command", ""), step.get("verify", ""),
        )

    parallel_tasks = [run_step(s) for s in independent]
    parallel_results = await asyncio.gather(*parallel_tasks, return_exceptions=True)

    sequential_results = []
    for step in dependent:
        result = await run_step(step)
        sequential_results.append(result)

    combined = []
    for r in parallel_results:
        if isinstance(r, Exception):
            combined.append(ExecutionResult(0, "error", "error", error=str(r)))
        else:
            combined.append(r)
    return combined + sequential_results


class ExecutionResult:
    def __init__(self, step_id: int, agent: str, status: str,
                 stdout: str = "", stderr: str = "",
                 verified: bool = False, error: Optional[str] = None):
        self.step_id = step_id
        self.agent = agent
        self.status = status
        self.stdout = stdout
        self.stderr = stderr
        self.verified = verified
        self.error = error
        self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return {
            "step_id": self.step_id,
            "agent": self.agent,
            "status": self.status,
            "stdout": self.stdout[-500:],
            "stderr": self.stderr[-500:],
            "verified": self.verified,
            "error": self.error,
            "timestamp": self.timestamp,
        }


class AgentExecutor:
    def __init__(self, progress_callback: Optional[Callable] = None,
                 channel: Optional[AgentChannel] = None,
                 auto_mode: bool = False):
        self._progress_callback = progress_callback
        self._channel = channel
        self._auto_mode = auto_mode
        self._running = False
        self._current_step = None
        self._results: list[ExecutionResult] = []
        self._cancelled = False

    async def execute_plan(self, plan: dict, notify_fn: Optional[Callable] = None) -> list[ExecutionResult]:
        self._running = True
        self._cancelled = False
        self._results = []
        steps = plan.get("steps", [])
        total = len(steps)

        for step in steps:
            if self._cancelled:
                break

            step_id = step["id"]
            agent_name = step.get("agent", "shell")
            prompt = step.get("prompt", "")
            command = step.get("command", "")
            verify_cmd = step.get("verify", "")
            on_failure = step.get("on_failure", "abort")

            actual_cmd = command or prompt

            self._current_step = step
            result = await self._execute_step(step_id, agent_name, actual_cmd, verify_cmd)

            if self._channel:
                self._channel.publish(step_id, "stdout", result.stdout)
                self._channel.publish(step_id, "stderr", result.stderr)
                self._channel.publish(step_id, "status", result.status)
                if step_id > 1:
                    self._channel.pass_to_next(step_id - 1, step_id)

            self._results.append(result)

            if notify_fn:
                await notify_fn({
                    "type": "step_complete",
                    "plan_id": plan.get("id"),
                    "step": step_id,
                    "total": total,
                    "status": result.status,
                    "result": result.to_dict(),
                })

            if result.status == "error":
                if self._auto_mode:
                    if on_failure == "retry":
                        result = await self._execute_step(step_id, agent_name, actual_cmd, verify_cmd)
                        self._results[-1] = result
                        if result.status == "error":
                            if on_failure == "skip":
                                continue
                            break
                    elif on_failure == "skip":
                        continue
                    else:
                        break
                elif self._progress_callback:
                    should_continue = await self._progress_callback(
                        f"Step {step_id}/{total} failed ({agent_name}). Continue? (retry/skip/abort)",
                        "step_error",
                        step,
                    )
                    if should_continue == "abort":
                        break
                    elif should_continue == "retry":
                        result = await self._execute_step(step_id, agent_name, actual_cmd, verify_cmd)
                        self._results[-1] = result
                        if result.status == "error":
                            break
                    elif should_continue == "skip":
                        continue

        self._running = False
        return self._results

    async def _execute_step(self, step_id: int, agent_name: str,
                            prompt: str, verify_cmd: str) -> ExecutionResult:
        agent = get_agent(agent_name)
        if not agent:
            return ExecutionResult(step_id, agent_name, "error", error=f"Unknown agent: {agent_name}")

        if agent.cmd:
            cmd = self._build_command(agent, prompt)
        else:
            cmd = prompt

        logger.info(f"[EXECUTOR] Step {step_id}: {agent_name} → {cmd[:100]}")

        try:
            import shlex
            cmd_args = shlex.split(cmd)
            proc = await asyncio.create_subprocess_exec(
                *cmd_args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=os.getcwd(),
            )

            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
            except asyncio.TimeoutError:
                proc.kill()
                return ExecutionResult(
                    step_id, agent_name, "error",
                    error="Timed out after 300s",
                )

            stdout_str = stdout.decode("utf-8", errors="replace") if stdout else ""
            stderr_str = stderr.decode("utf-8", errors="replace") if stderr else ""

            if proc.returncode != 0:
                return ExecutionResult(
                    step_id, agent_name, "error",
                    stdout=stdout_str, stderr=stderr_str,
                    error=f"Exit code {proc.returncode}",
                )

            verified = False
            if verify_cmd:
                verified = await self._run_verification(verify_cmd)

            return ExecutionResult(
                step_id, agent_name, "completed",
                stdout=stdout_str, stderr=stderr_str,
                verified=verified,
            )

        except Exception as e:
            return ExecutionResult(
                step_id, agent_name, "error",
                error=str(e),
            )

    def _build_command(self, agent, prompt: str) -> str:
        escapes = prompt.replace('"', '\\"')
        return f'{agent.cmd} "{escapes}"'

    async def _run_verification(self, verify_cmd: str) -> bool:
        try:
            import shlex
            cmd_args = shlex.split(verify_cmd)
            proc = await asyncio.create_subprocess_exec(
                *cmd_args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
            return proc.returncode == 0
        except Exception:
            return False

    def cancel(self):
        self._cancelled = True

    def get_status(self) -> dict:
        return {
            "running": self._running,
            "current_step": self._current_step,
            "results": [r.to_dict() for r in self._results],
        }

    def get_summary(self) -> str:
        total = len(self._results)
        passed = sum(1 for r in self._results if r.status == "completed" and r.verified)
        failed = sum(1 for r in self._results if r.status == "error")
        skipped = sum(1 for r in self._results if r.verified is False and r.status == "completed")
        lines = [f"Execution complete: {total} steps"]
        lines.append(f"  ✅ Passed: {passed}  ⚠️  Skipped verify: {skipped - (total - len(self._results))}")
        lines.append(f"  ❌ Failed: {failed}")
        for r in self._results:
            status_icon = "✅" if r.status == "completed" and r.verified else "⚠️" if r.status == "completed" else "❌"
            lines.append(f"  {status_icon} Step {r.step_id} ({r.agent}): {r.status}")
        return "\n".join(lines)


async def execute_step(step: dict) -> dict:
    """Execute a single plan step and return result dict."""
    executor = AgentExecutor()
    result = await executor._execute_step(
        step.get("id", 0),
        step.get("agent", "shell"),
        step.get("command", ""),
        step.get("verify", ""),
    )
    return {
        "success": result.status == "completed",
        "status": result.status,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "verified": result.verified,
        "error": result.error,
    }


async def run_overnight_build(goal: str, output_dir: str) -> dict:
    """
    Like Cowork's overnight autonomous builder.
    Takes a goal, works through the night, delivers result.
    Sends progress to Supabase for mobile notification.
    """
    from .plan_manager import generate_autodream_plan, supabase_notify

    plan = generate_autodream_plan(goal)
    steps = plan.get("steps", [])
    os.makedirs(output_dir, exist_ok=True)

    await supabase_notify("build_started", {
        "goal": goal,
        "steps": len(steps),
        "estimated_time": plan.get("estimated_time", "unknown"),
        "output_dir": output_dir,
    })

    results = []
    for i, step in enumerate(steps):
        step_id = step.get("id", i + 1)
        result = await execute_step(step)
        results.append(result)

        await supabase_notify("build_progress", {
            "step": step_id,
            "total": len(steps),
            "description": step.get("description", ""),
            "status": "success" if result["success"] else "failed",
            "output_dir": output_dir,
        })

        if not result["success"] and step.get("on_failure") == "abort":
            break

    await supabase_notify("build_complete", {
        "goal": goal,
        "output_dir": output_dir,
        "steps_completed": sum(1 for r in results if r["success"]),
        "steps_total": len(steps),
        "success": any(r["success"] for r in results),
    })

    return {
        "goal": goal,
        "output_dir": output_dir,
        "steps_completed": sum(1 for r in results if r["success"]),
        "steps_total": len(steps),
        "results": results,
    }
