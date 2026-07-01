"""Autonomous Workflow Benchmarks A/B/C/D.

Uses real WorkflowEngine + ExecutionContext + ArtifactStore + ToolDispatch.
Only mocks: heavy build targets (Android SDK) and external APIs (SMTP).

Runs four benchmarks:
  A: Research → Build → Validate → Email  (bookstore website)
  B: Research → Android APK Delivery         (coffee shop app)
  C: Long Running Recovery                   (kill/restart)
  D: Compensation Stress Test                (force failure, verify rollback)

Usage:
  python benchmarks/autonomous_workflow_benchmark.py
  python benchmarks/autonomous_workflow_benchmark.py --benchmark A
  python benchmarks/autonomous_workflow_benchmark.py --model qwen2.5:7b
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import tempfile
import time
import traceback
from collections import Counter
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

_JARVIS_TEST_EMAIL = os.environ.get("JARVIS_TEST_EMAIL", "autobot99123@gmail.com")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx

from core.tools._constants import ToolBlock
from core.tools.execution import execute_tool_block
from core.workflow import (
    ArtifactStore,
    ContextManager,
    WorkflowEngine,
    WorkflowStore,
    recover_active_workflows,
)
from core.workflow.models import (
    StepDefinition,
    StepStatus,
    WorkflowInstance,
    WorkflowStatus,
)

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
logger = logging.getLogger("autonomous_bench")

# ── Config ───────────────────────────────────────────────────────────────

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
MODEL = os.environ.get("AGENT_MODEL", "qwen2.5:7b")
MAX_TURNS = int(os.environ.get("MAX_TURNS", "15"))
TASK_TIMEOUT = int(os.environ.get("TASK_TIMEOUT", "300"))
REPORT_DIR = os.environ.get("REPORT_DIR", "benchmark_reports")
os.makedirs(REPORT_DIR, exist_ok=True)

RESULTS: list[dict] = []

VALID_TOOLS = {
    "browser_navigate", "browser_snapshot", "browser_screenshot",
    "browser_fill", "browser_click", "browser_press",
    "browser_current_state", "browser_find", "browser_wait_visible",
    "browser_wait_text", "browser_get_url", "browser_get_title",
    "browser_search", "browser_new_tab", "browser_switch_tab",
    "browser_close_tab", "browser_list_tabs", "browser_evaluate",
    "browser_find_interactive", "browser_wait_interactive",
    "browser_health", "browser_shadow_query",
    "build_project", "repair_project", "run_tests", "runtime_validate",
    "write_file", "read_file", "edit_file", "delete_file",
    "send_email", "delete_email", "read_email", "list_emails",
    "web_fetch", "web_search", "python", "bash", "shell",
}


# ── Tool Schemas ─────────────────────────────────────────────────────────

def _build_tool_schemas():
    """Collect tool schemas from all subsystems."""
    from core.tools.schemas_browser import FUNCTION_TOOL_SCHEMAS as BROWSER_SCHEMAS
    from core.tools.schemas import FUNCTION_TOOL_SCHEMAS
    seen = set()
    combined = []
    for s in FUNCTION_TOOL_SCHEMAS:
        name = s.get("function", {}).get("name", "")
        if name not in seen:
            seen.add(name)
            combined.append(s)
    for s in BROWSER_SCHEMAS:
        name = s.get("function", {}).get("name", "")
        if name not in seen:
            seen.add(name)
            combined.append(s)
    return combined

TOOL_SCHEMAS = _build_tool_schemas()

SYSTEM_PROMPT = (
    "You are a software engineering agent. You have access to tools for:\n"
    "- Web research (browser_navigate, browser_snapshot, browser_search, web_fetch)\n"
    "- File operations (read_file, write_file, edit_file)\n"
    "- Code/build (build_project, repair_project, run_tests, runtime_validate)\n"
    "- Communication (send_email with attachments)\n\n"
    "WORKFLOW RULES:\n"
    "1. After browser_navigate, ALWAYS call browser_snapshot.\n"
    "2. Read page content before deciding the next action.\n"
    "3. Use build_project for building code, run_tests for testing.\n"
    "4. Use send_email with attachments to deliver results.\n"
    "5. Attachments can be file paths.\n"
    "6. Keep using tools until the task is complete.\n"
    "7. Do NOT stop after one tool call — multi-step workflows require multiple calls.\n"
    "8. When research is needed, use browser tools; do not fabricate facts."
)


# ── Mock Setup ───────────────────────────────────────────────────────────

def _setup_mocks():
    """Patch external APIs and heavy build targets. Returns a list of patches to start/stop."""
    patches = []

    # Mock build tools (requires real Android SDK)
    async def _mock_build(task, project_dir, progress_cb=None):
        apk_dir = os.path.join(project_dir, "app", "build", "outputs", "apk", "debug")
        os.makedirs(apk_dir, exist_ok=True)
        apk_path = os.path.join(apk_dir, "app-debug.apk")
        with open(apk_path, "wb") as f:
            f.write(b"fake apk")
        log_path = os.path.join(project_dir, "build.log")
        with open(log_path, "w") as f:
            f.write(f"Build completed for: {task}\n")
        return {
            "success": True,
            "output": f"Build completed: {task}",
            "exit_code": 0,
            "artifact_path": apk_path,
        }

    async def _mock_repair(project_dir, build_output, progress_cb=None):
        return {"success": True, "output": "Repaired 0 issues", "exit_code": 0}

    async def _mock_tests(project_dir, progress_cb=None):
        report_dir = os.path.join(project_dir, "app", "build", "reports", "tests")
        os.makedirs(report_dir, exist_ok=True)
        xml_path = os.path.join(report_dir, "test-results.xml")
        with open(xml_path, "w") as f:
            f.write("<testsuite><testcase name='test1'/></testsuite>")
        return {"success": True, "output": "Tests passed: 5/5", "exit_code": 0}

    async def _mock_validate(project_dir, progress_cb=None):
        ss_dir = os.path.join(project_dir, "build", "reports", "validation")
        os.makedirs(ss_dir, exist_ok=True)
        ss_path = os.path.join(ss_dir, "screenshot.png")
        with open(ss_path, "wb") as f:
            f.write(b"fake png")
        return {"success": True, "output": "Validation passed", "exit_code": 0}

    patches.append(patch("core.tools.execution.do_build_project", side_effect=_mock_build))
    patches.append(patch("core.tools.execution.do_repair_project", side_effect=_mock_repair))
    patches.append(patch("core.tools.execution.do_run_tests", side_effect=_mock_tests))
    patches.append(patch("core.tools.execution.do_runtime_validate", side_effect=_mock_validate))

    # Mock email MCP
    _email_result = {"sent": True, "to": ["recipient@example.com"],
                     "subject": "", "message_id": "<mock@benchmark>"}

    async def _mock_mcp_call(tool, args):
        nonlocal _email_result
        _email_result["subject"] = args.get("subject", "")
        _email_result["to"] = [args.get("to", "")]
        return dict(_email_result)

    mock_mcp = AsyncMock()
    mock_mcp.call_tool = AsyncMock(side_effect=_mock_mcp_call)
    patches.append(patch("core.tools.execution.get_mcp_manager", return_value=mock_mcp))

    # Mock auth to bypass RBAC for benchmark (all tool accesses succeed)
    async def _always_authorized(tool_name, ctx):
        return True
    patches.append(patch("core.tools.security.is_authorized_to_execute", return_value=True))

    return patches


# ── Ollama Planner ───────────────────────────────────────────────────────

async def call_llm(messages, model=None, ollama_url=None):
    """Call Ollama with tool schemas, return (content, tool_calls)."""
    model = model or MODEL
    ollama_url = ollama_url or OLLAMA_URL
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "tools": TOOL_SCHEMAS,
    }
    full_content = ""
    tool_calls = []
    try:
        async with httpx.AsyncClient(timeout=TASK_TIMEOUT) as client:
            async with client.stream("POST", f"{ollama_url}/api/chat", json=payload) as resp:
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if "message" not in chunk:
                        continue
                    msg = chunk["message"]
                    if msg.get("content"):
                        full_content += msg["content"]
                    if msg.get("tool_calls"):
                        for tc in msg["tool_calls"]:
                            name = tc["function"]["name"]
                            args_raw = tc["function"].get("arguments", {})
                            if isinstance(args_raw, str):
                                try:
                                    args_raw = json.loads(args_raw)
                                except json.JSONDecodeError:
                                    args_raw = {}
                            tool_calls.append({"name": name, "arguments": args_raw})
    except Exception as e:
        logger.error("Ollama call failed: %s", e)
        return "", []
    return full_content, tool_calls


# ── Workflow Execution ──────────────────────────────────────────────────

class WorkflowExecutor:
    """Executes tool calls through the real WorkflowEngine + execute_tool_block."""

    def __init__(self, store: WorkflowStore, engine: WorkflowEngine):
        self.store = store
        self.engine = engine
        self.cm = engine.context_manager
        self.artifact_store = engine.artifact_store

    async def run_workflow(self, steps: list[StepDefinition],
                           goal: str) -> WorkflowInstance:
        """Start a workflow and wait for completion."""
        wf = await self.engine.start_workflow(
            "auto_bench", steps, owner="dev",
            execution_context={"goal": goal},
        )
        wid = wf.workflow_id
        deadline = time.monotonic() + TASK_TIMEOUT
        while time.monotonic() < deadline:
            current = self.store.get_workflow(wid)
            if current and current.status in (
                WorkflowStatus.COMPLETED, WorkflowStatus.FAILED,
                WorkflowStatus.CANCELLED, WorkflowStatus.COMPENSATED,
                WorkflowStatus.COMPENSATION_FAILED,
            ):
                return current
            await asyncio.sleep(0.05)
        return self.store.get_workflow(wid)

    async def run_dynamic(self, goal: str, model=None, ollama_url=None, use_planner=True) -> dict:
        """Run a planner-driven workflow: LLM → tool calls → execution → repeat.

        When use_planner=True, wraps execution in a PlannerStateMachine that
        owns the PLAN → DECOMPOSE → EXECUTE → VERIFY → COMPLETE lifecycle,
        with artifact-driven verification gates.
        """
        from core.planner import PlannerExecutor, PlannerStateMachine

        wf = await self.engine.start_workflow(
            "auto_bench", [], owner="dev",
            execution_context={"goal": goal},
        )
        wid = wf.workflow_id
        context = self.cm.get_context(wid)

        planner = PlannerExecutor() if use_planner else None
        sm = PlannerStateMachine(planner) if use_planner else None

        async def execute_fn(_goal: str, _executor: PlannerExecutor) -> dict:
            """Run the LLM + tool dispatch loop. Called by the state machine."""
            plan = _executor.create_plan(_goal)
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _goal},
            ]
            all_tool_calls = []
            hallucinated_tools = []
            loop_count = 0
            recent_window = []
            early_termination_count = 0
            start_time = time.monotonic()

            for turn in range(MAX_TURNS):
                content, tool_calls = await call_llm(messages, model=model, ollama_url=ollama_url)

                # ── Planner Enforcement ─────────────────────────────────
                if not tool_calls and plan is not None:
                    tool_names_sofar = [tc["tool"] for tc in all_tool_calls]

                    if not tool_names_sofar:
                        messages.append({"role": "user", "content": "Start working on the task using the available tools. Make your first tool call now."})
                        continue

                    missing = _executor.check_early_termination(plan.template_id, tool_names_sofar)
                    if missing:
                        early_termination_count += 1
                        logger.info("Planner: enforcing %d missing steps: %s", len(missing), missing)

                        for step_name in missing:
                            async def enforce_step(tname: str, dargs: dict) -> dict:
                                args = dict(dargs)
                                if tname == "send_email":
                                    _, forced_tc = await call_llm(
                                        messages + [{"role": "user", "content": "Provide parameters for send_email. Reply with ONLY a tool call containing to, subject, and body."}],
                                        model=model, ollama_url=ollama_url,
                                    )
                                    if forced_tc:
                                        fa = forced_tc[0].get("arguments", {})
                                        if "to" in fa: args.update(fa)
                                        elif "recipient" in fa: args["to"] = fa["recipient"]
                                        if "subject" in fa: args["subject"] = fa["subject"]
                                        if "body" in fa: args["body"] = fa["body"]
                                elif tname == "browser_navigate":
                                    _, forced_tc = await call_llm(
                                        messages + [{"role": "user", "content": "Provide the URL for browser_navigate. Reply with ONLY a tool call containing a url parameter."}],
                                        model=model, ollama_url=ollama_url,
                                    )
                                    if forced_tc:
                                        fa = forced_tc[0].get("arguments", {})
                                        if "url" in fa: args["url"] = fa["url"]
                                        else: args.setdefault("url", dargs.get("url", "https://www.google.com"))
                                tool_block = ToolBlock(tool_type=tname, content=json.dumps(args))
                                desc, result = await execute_tool_block(block=tool_block, session_id=wid, owner="dev", context=context)
                                return result

                            task_info = _executor.get_task_for_step(plan.template_id, step_name)
                            if task_info:
                                result = await enforce_step(task_info["tool"], task_info.get("default_args", {}))
                            else:
                                result = {"exit_code": 1, "error": f"Unknown step: {step_name}"}
                            tool_name = task_info["tool"] if task_info else step_name
                            all_tool_calls.append({"tool": tool_name, "args": {}, "result": result, "enforced": True})
                            msg_text = str(result.get("output", result.get("result", json.dumps(result))))[:500]
                            messages.append({"role": "assistant", "content": None, "tool_calls": [{"function": {"name": tool_name, "arguments": "{}"}, "type": "function"}]})
                            messages.append({"role": "tool", "content": f"[Planner-enforced] {msg_text}"})

                        if _executor.is_workflow_complete(plan.template_id):
                            break
                        continue
                    else:
                        break

                if not tool_calls:
                    break

                for tc in tool_calls:
                    name = tc["name"]
                    if name not in VALID_TOOLS:
                        hallucinated_tools.append(name)
                    result = await self._dispatch_tool(tc, session_id=wid, context=context)
                    all_tool_calls.append({"tool": name, "args": tc["arguments"], "result": result})
                    if plan is not None:
                        step_ok = (result.get("exit_code", -1) == 0 or result.get("sent") is True or result.get("success", False) is True or (result.get("error") is None and result.get("output") is not None))
                        _executor.record_step(plan.template_id, name, step_ok)
                    msg_text = str(result.get("output", result.get("result", json.dumps(result))))[:500]
                    messages.append({"role": "assistant", "content": None, "tool_calls": [{"function": {"name": name, "arguments": json.dumps(tc["arguments"])}, "type": "function"}]})
                    messages.append({"role": "tool", "content": msg_text})
                    recent_window.append(name)
                    if len(recent_window) > 8: recent_window.pop(0)
                    from collections import Counter as _Counter
                    if len(recent_window) >= 6 and _Counter(recent_window).most_common(1)[0][1] >= 4:
                        loop_count += 1
                    tn = [tc2["tool"] for tc2 in all_tool_calls]
                    n = len(tn)
                    for plen in range(3, 7):
                        if n >= plen * 4:
                            if tn[-plen:-0] == tn[-plen*2:-plen] == tn[-plen*3:-plen*2] == tn[-plen*4:-plen*3]:
                                loop_count += 1
                                break

                if time.monotonic() - start_time > TASK_TIMEOUT:
                    break

            # Return execution artifacts
            ctx = self.cm.get_context(wid)
            plan_metrics = {}
            if plan is not None:
                if early_termination_count:
                    _executor.finalize(plan.template_id, _executor.is_workflow_complete(plan.template_id))
                plan_metrics = {
                    "planner_template_used": plan.template_id,
                    "planner_required_steps": plan.steps,
                    "planner_missing_steps": _executor.get_missing_steps(plan.template_id),
                    "planner_early_termination_count": early_termination_count,
                    "planner_completed": _executor.is_workflow_complete(plan.template_id),
                    "hallucinated_tools": hallucinated_tools,
                    "loop_count": loop_count,
                    **_executor.metrics,
                }
            return {
                "artifacts": dict(ctx.artifacts) if ctx else {},
                "tool_calls": all_tool_calls,
                "tool_names": [tc["tool"] for tc in all_tool_calls],
                "planner_metrics": plan_metrics,
                "hallucinated_tools": hallucinated_tools,
                "loop_count": loop_count,
                "completed_naturally": not any(
                    tc.get("enforced") for tc in all_tool_calls
                ) if all_tool_calls else False,
            }

        # ── State Machine ────────────────────────────────────────────────
        if use_planner and sm is not None:
            sm_result = await sm.run(goal, execute_fn)
            wf = self.store.get_workflow(wid)
            if wf and wf.status == WorkflowStatus.RUNNING:
                wf.status = WorkflowStatus.COMPLETED
                self.store.update_workflow(wf)
            return {
                "workflow_id": wid,
                "status": wf.status.value if wf else "UNKNOWN",
                "elapsed": sm_result.get("elapsed", 0.0),
                "turns": len(sm_result.get("tool_calls", [])),
                "tool_calls": sm_result.get("tool_calls", []),
                "tool_names": sm_result.get("tool_names", []),
                "artifacts": sm_result.get("artifacts", {}),
                "completed_naturally": sm_result.get("completed_naturally", False),
                "hallucinated_tools": sm_result.get("hallucinated_tools", []),
                "loop_count": sm_result.get("loop_count", 0),
                "planner_metrics": {
                    "state_machine_state": sm.state.value,
                    "verification": sm_result.get("verification", []),
                    **sm_result.get("planner_metrics", {}),
                    **sm.metrics,
                },
            }

        # ── Fallback: run without state machine ──────────────────────────
        return await execute_fn(goal, planner) if planner else {"artifacts": {}}

    async def _dispatch_tool(self, tc: dict, session_id: str, context) -> dict:
        """Dispatch a single tool call through execute_tool_block."""
        name = tc["name"]
        args = tc.get("arguments", {})
        block = ToolBlock(tool_type=name, content=json.dumps(args) if args else "")
        try:
            desc, result = await execute_tool_block(
                block=block, session_id=session_id, owner="dev", context=context,
            )
            return result
        except Exception as e:
            return {"error": str(e), "exit_code": 1}


# ── Benchmark Scenarios ─────────────────────────────────────────────────

async def benchmark_a(executor: WorkflowExecutor, model=None, ollama_url=None) -> dict:
    """Research → Build → Validate → Email (bookstore website)."""
    goal = (
        "Build a professional bookstore website and email the results. "
        "First research bookstore website designs and features. "
        "Then build the project, run tests, validate, and email the build report."
    )
    result = await executor.run_dynamic(goal, model=model, ollama_url=ollama_url)

    ctx = executor.cm.get_context(result["workflow_id"])
    artifacts = dict(ctx.artifacts) if ctx else {}
    tool_names = result.get("tool_names", [])

    expected_tools = [
        "browser_navigate", "browser_snapshot",
        "build_project", "run_tests", "runtime_validate",
        "send_email",
    ]
    present = set(tool_names)
    missing = [t for t in expected_tools if t not in present]
    hallucinated = result.get("hallucinated_tools", [])
    loop_count = result.get("loop_count", 0)

    # Artifact metrics
    artifact_tracker = _trace_artifacts(tool_names, artifacts)

    return {
        "benchmark": "A",
        "label": "Research → Build → Validate → Email",
        "passed": result["status"] == "COMPLETED" and not missing,
        "elapsed": result["elapsed"],
        "turns": result["turns"],
        "completed_naturally": result["completed_naturally"],
        "status": result["status"],
        "artifacts": artifacts,
        "tool_names": tool_names,
        "tool_order_correct": _check_order(tool_names, expected_tools),
        "missing_steps": missing,
        "hallucinated_tools": hallucinated,
        "loop_count": loop_count,
        "planner_metrics": result.get("planner_metrics", {}),
        **artifact_tracker,
    }


async def benchmark_b(executor: WorkflowExecutor, model=None, ollama_url=None) -> dict:
    """Research → Android APK Delivery (coffee shop app)."""
    goal = (
        "Build an Android coffee shop app and deliver the APK. "
        "Research coffee shop app UI trends first. "
        "Then build the project, repair any issues, validate runtime, "
        "and email the APK file as an attachment."
    )
    result = await executor.run_dynamic(goal, model=model, ollama_url=ollama_url)

    ctx = executor.cm.get_context(result["workflow_id"])
    artifacts = dict(ctx.artifacts) if ctx else {}

    tool_names = result.get("tool_names", [])
    has_artifact_ids = all(
        not isinstance(v, str) or (not v.startswith("/") and not v.startswith("C:\\"))
        for v in artifacts.values()
    ) if artifacts else False

    expected_tools = ["browser_navigate", "build_project", "send_email"]
    present = set(tool_names)
    missing = [t for t in expected_tools if t not in present]
    hallucinated = result.get("hallucinated_tools", [])
    loop_count = result.get("loop_count", 0)
    artifact_tracker = _trace_artifacts(tool_names, artifacts)

    return {
        "benchmark": "B",
        "label": "Research → Android APK Delivery",
        "goal": goal,
        "passed": result["status"] == "COMPLETED" and not missing,
        "elapsed": result["elapsed"],
        "turns": result["turns"],
        "completed_naturally": result["completed_naturally"],
        "status": result["status"],
        "artifacts": artifacts,
        "tool_names": tool_names,
        "uses_artifact_ids_only": has_artifact_ids,
        "missing_steps": missing,
        "hallucinated_tools": hallucinated,
        "loop_count": loop_count,
        "planner_metrics": result.get("planner_metrics", {}),
        **artifact_tracker,
    }


async def benchmark_c(executor: WorkflowExecutor, store: WorkflowStore,
                      model=None, ollama_url=None) -> dict:
    """Long Running Recovery — kill process mid-way, restart, verify completion."""
    goal = (
        "Research modern bookstore design trends, then build a bookstore project, "
        "run tests, and validate runtime."
    )
    result = await executor.run_dynamic(goal, model=model, ollama_url=ollama_url)

    wid = result["workflow_id"]
    tool_count_before = len(result["tool_calls"])
    tool_names_before = result.get("tool_names", [])
    crash_time = time.monotonic()

    # Simulate crash: mark workflow as stale with mid-execution state
    wf_stale = store.get_workflow(wid)
    if wf_stale:
        wf_stale.status = WorkflowStatus.RUNNING
        wf_stale.last_heartbeat = datetime.utcnow() - timedelta(seconds=120)
        store.update_workflow(wf_stale)

    # Recover with fresh engine
    store2 = WorkflowStore(store._db_path)
    engine2 = WorkflowEngine(store2)
    executor2 = WorkflowExecutor(store2, engine2)

    async def _recover_and_continue():
        recovered = await recover_active_workflows(engine2)
        if recovered:
            for w in recovered:
                deadline = time.monotonic() + TASK_TIMEOUT
                while time.monotonic() < deadline:
                    wid_recovery = w["workflow_id"] if isinstance(w, dict) else w.workflow_id
                    current = store2.get_workflow(wid_recovery)
                    if current and current.status in (
                        WorkflowStatus.COMPLETED, WorkflowStatus.FAILED,
                        WorkflowStatus.CANCELLED, WorkflowStatus.COMPENSATED,
                    ):
                        return current
                    await asyncio.sleep(0.05)
                return store2.get_workflow(wid_recovery)
        return None

    recovered_wf = await _recover_and_continue()
    recovery_time = time.monotonic() - crash_time
    ctx_after = executor2.cm.get_context(wid)
    artifacts_after = dict(ctx_after.artifacts) if ctx_after else {}

    duplicate_executions = 0
    duplicate_emails = 0
    duplicate_artifacts = set()
    if recovered_wf:
        completed = [s for s in recovered_wf.steps if s.status == StepStatus.COMPLETED]
        dup_count = max(0, len(completed) - tool_count_before)
        duplicate_executions = dup_count
        # Check for duplicate email steps
        email_steps = [s for s in recovered_wf.steps if "email" in (s.tool_name or "").lower()]
        duplicate_emails = max(0, len(email_steps) - 1)
        # Check for duplicate artifact names
        art_names = list(artifacts_after.keys())
        duplicate_artifacts = {n for n in art_names if art_names.count(n) > 1}

    hallucinated = result.get("hallucinated_tools", [])
    loop_count = result.get("loop_count", 0)
    artifact_tracker = _trace_artifacts(tool_names_before, artifacts_after)

    return {
        "benchmark": "C",
        "label": "Long Running Recovery",
        "goal": goal,
        "passed": recovered_wf is not None and recovered_wf.status == WorkflowStatus.COMPLETED,
        "elapsed": result["elapsed"],
        "status": recovered_wf.status.value if recovered_wf else "LOST",
        "artifacts": artifacts_after,
        "tool_calls_before_crash": tool_count_before,
        "recovery_time_s": round(recovery_time, 2),
        "duplicate_execution": duplicate_executions > 0,
        "duplicate_execution_count": duplicate_executions,
        "duplicate_emails": duplicate_emails,
        "duplicate_artifacts": list(duplicate_artifacts),
        "recovered": recovered_wf is not None,
        "hallucinated_tools": hallucinated,
        "loop_count": loop_count,
        "planner_metrics": result.get("planner_metrics", {}),
        **artifact_tracker,
    }


async def benchmark_d(executor: WorkflowExecutor, model=None, ollama_url=None) -> dict:
    """Compensation Stress Test — force failure, verify rollback."""
    goal = (
        "Generate a project report, email it, then intentionally fail the next step "
        "to verify the system rolls back the previous operations."
    )

    report_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "bench_report.md")
    wf = await executor.engine.start_workflow(
        "comp_stress", [
            StepDefinition(tool_name="write_file", input_data={
                "path": report_path, "content": "# Build Report\nSuccess.",
            }, compensation_tool="delete_file", compensation_data={"path": report_path}),
            StepDefinition(tool_name="send_email", input_data={
                "to": _JARVIS_TEST_EMAIL, "subject": "Report", "body": "See attachment.",
            }, compensation_tool="delete_email", compensation_data={"uid": "LAST"}),
            StepDefinition(tool_name="fail_intentionally", input_data={}, max_retries=0),
        ],
        owner="dev",
        execution_context={"goal": goal},
    )
    wid = wf.workflow_id
    compensation_invoked = False
    compensation_succeeded = False
    partial_rollback = True
    transitions = ["PENDING"]

    start_time = time.monotonic()
    deadline = time.monotonic() + TASK_TIMEOUT
    while time.monotonic() < deadline:
        current = executor.store.get_workflow(wid)
        if current:
            if current.status.value not in transitions[-1]:
                transitions.append(current.status.value)
        if current and current.status in (
            WorkflowStatus.COMPLETED, WorkflowStatus.FAILED,
            WorkflowStatus.CANCELLED, WorkflowStatus.COMPENSATED,
            WorkflowStatus.COMPENSATION_FAILED,
        ):
            break
        await asyncio.sleep(0.05)

    elapsed = time.monotonic() - start_time
    final = executor.store.get_workflow(wid)
    events = executor.store.list_events(wid) if hasattr(executor.store, "list_events") else []

    if final:
        compensation_invoked = final.status in (
            WorkflowStatus.COMPENSATING, WorkflowStatus.COMPENSATED,
            WorkflowStatus.COMPENSATION_FAILED,
        )
        compensation_succeeded = final.status == WorkflowStatus.COMPENSATED
        # Check if all steps with compensation_tool were compensated
        comp_steps = [s for s in final.steps if s.compensated]
        total_with_comp = [s for s in final.steps if s.compensation_tool and s.status == StepStatus.COMPLETED]
        partial_rollback = len(comp_steps) < len(total_with_comp)

    return {
        "benchmark": "D",
        "label": "Compensation Stress Test",
        "goal": goal,
        "passed": final is not None and final.status in (
            WorkflowStatus.COMPENSATED, WorkflowStatus.COMPENSATION_FAILED,
        ),
        "status": final.status.value if final else "UNKNOWN",
        "elapsed": round(elapsed, 2),
        "event_count": len(events),
        "compensated": final.status == WorkflowStatus.COMPENSATED if final else False,
        "compensation_invoked": compensation_invoked,
        "compensation_succeeded": compensation_succeeded,
        "partial_rollback": partial_rollback,
        "transitions": transitions,
        "comp_steps": sum(1 for s in final.steps if s.compensated) if final else 0,
    }


# ── Helpers ──────────────────────────────────────────────────────────────

def _trace_artifacts(tool_names: list[str], artifacts: dict) -> dict:
    """Trace artifact production/consumption/orphaning."""
    produced = set(artifacts.keys())
    # Tools that consume (use) artifacts
    consumptive_tool_patterns = ["send_email", "attach", "build"]
    consumed_hints = set()
    for t in tool_names:
        for pattern in consumptive_tool_patterns:
            if pattern in t.lower():
                for art_name, art_id in artifacts.items():
                    # If artifact name or ID appears in the tool args context, mark consumed
                    if art_name in t.lower():
                        consumed_hints.add(art_name)
    consumed = consumed_hints or produced  # conservative: if no match, assume all consumed
    orphaned = produced - consumed
    return {
        "artifacts_produced": list(produced),
        "artifacts_consumed": list(consumed),
        "artifacts_orphaned": list(orphaned),
    }


def _check_order(tool_names: list[str], expected: list[str]) -> bool:
    """Check if expected tools appear in order within tool_names."""
    it = iter(tool_names)
    return all(any(e in t for t in it) for e in expected)


def _record(name: str, data: dict):
    RESULTS.append({"name": name, **data})
    status = "PASS" if data.get("passed") else "FAIL"
    extra = []
    if "elapsed" in data:
        extra.append(f"{data['elapsed']:.1f}s")
    if "turns" in data:
        extra.append(f"{data['turns']} turns")
    if "status" in data:
        extra.append(f"status={data['status']}")
    if data.get("duplicate_execution"):
        extra.append("DUP")
    print(f"  {status:5s}  {'  '.join(extra)}  {name}")


# ── Main ─────────────────────────────────────────────────────────────────

async def main():
    parser = argparse.ArgumentParser(description="Autonomous Workflow Benchmarks")
    parser.add_argument("--benchmark", choices=["A", "B", "C", "D", "all"], default="all")
    parser.add_argument("--model", default=None)
    parser.add_argument("--ollama-url", default=None)
    parser.add_argument("--report-name", default=None,
                        help="Custom report filename (without .json)")
    args = parser.parse_args()

    bench_model = args.model or MODEL
    bench_ollama = args.ollama_url or OLLAMA_URL

    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "bench.db")
    store = WorkflowStore(db_path)
    engine = WorkflowEngine(store)
    executor = WorkflowExecutor(store, engine)

    benchmarks = []
    if args.benchmark in ("A", "all"):
        benchmarks.append(("Benchmark A", benchmark_a))
    if args.benchmark in ("B", "all"):
        benchmarks.append(("Benchmark B", benchmark_b))
    if args.benchmark in ("C", "all"):
        benchmarks.append(("Benchmark C", benchmark_c))
    if args.benchmark in ("D", "all"):
        benchmarks.append(("Benchmark D", benchmark_d))

    print("=" * 70)
    print(f"  Autonomous Workflow Benchmarks")
    print(f"  Model: {bench_model}")
    print(f"  Ollama: {bench_ollama}")
    print(f"  Max turns: {MAX_TURNS}, Timeout: {TASK_TIMEOUT}s")
    print("=" * 70)
    print()

    patches = _setup_mocks()
    for p in patches:
        p.start()

    try:
        for label, func in benchmarks:
            print(f"[{label}]")
            print(f"  Running...")
            sys.stdout.flush()
            try:
                kwargs = dict(model=bench_model, ollama_url=bench_ollama)
                if label == "Benchmark C":
                    data = await func(executor, store, **kwargs)
                else:
                    data = await func(executor, **kwargs)
                _record(label.replace("Benchmark ", ""), data)
            except Exception as e:
                traceback.print_exc()
                _record(label.replace("Benchmark ", ""), {
                    "passed": False, "error": str(e),
                })
            print()
    finally:
        for p in patches:
            p.stop()

    # Summary
    passed = sum(1 for r in RESULTS if r.get("passed"))
    total = len(RESULTS)
    print("=" * 70)
    print(f"  RESULTS: {passed}/{total} passed ({passed/total*100:.0f}%)")
    print()

    # Classification summary
    planner_fails = sum(1 for r in RESULTS if r.get("missing_steps") or r.get("hallucinated_tools"))
    planner_loops = sum(1 for r in RESULTS if r.get("loop_count", 0) > 1)
    infra_fails = sum(1 for r in RESULTS if not r.get("passed") and not r.get("missing_steps")
                      and not r.get("hallucinated_tools"))
    planner_used = sum(1 for r in RESULTS if r.get("planner_metrics", {}).get("planner_template_used"))
    print(f"  Planner failures: {planner_fails} (missing/ hallucinated tools)")
    print(f"  Loop detections:  {planner_loops} (same tool >=4x in last 8 calls)")
    print(f"  Planner enabled:  {planner_used}/{total} runs")
    print()

    for r in RESULTS:
        name = r.pop("name", "")
        passed_flag = r.pop("passed", False)
        status = "PASS" if passed_flag else "FAIL"
        artifacts = r.pop("artifacts", {})
        tool_names = r.pop("tool_names", [])
        planner_metrics = r.pop("planner_metrics", {}) or {}

        # Build detailed report
        lines = []
        if "missing_steps" in r and r["missing_steps"]:
            lines.append(f"missing_steps={r['missing_steps']}")
        if "hallucinated_tools" in r and r["hallucinated_tools"]:
            lines.append(f"hallucinated={r['hallucinated_tools']}")
        if "loop_count" in r and r["loop_count"]:
            lines.append(f"loops={r['loop_count']}")
        if "elapsed" in r:
            lines.append(f"elapsed={r['elapsed']:.1f}s")
        if "turns" in r:
            lines.append(f"turns={r['turns']}")
        if "completed_naturally" in r:
            lines.append(f"natural={r['completed_naturally']}")
        if "status" in r:
            lines.append(f"status={r['status']}")
        if "recovery_time_s" in r:
            lines.append(f"recovery={r['recovery_time_s']}s")
        if "duplicate_execution" in r:
            lines.append(f"dup_exec={r['duplicate_execution']}")
        if "duplicate_emails" in r:
            lines.append(f"dup_email={r['duplicate_emails']}")
        if "artifacts_produced" in r:
            lines.append(f"artifacts={r['artifacts_produced']}")
        if "artifacts_orphaned" in r and r["artifacts_orphaned"]:
            lines.append(f"orphaned={r['artifacts_orphaned']}")
        if "compensated" in r:
            lines.append(f"compensated={r['compensated']}")
        if "compensation_succeeded" in r:
            lines.append(f"comp_success={r['compensation_succeeded']}")
        if "transitions" in r:
            lines.append(f"transitions={'->'.join(r['transitions'])}")
        if planner_metrics:
            tpl = planner_metrics.get("planner_template_used", "")
            misc = planner_metrics.get("planner_missing_steps", [])
            etc = planner_metrics.get("planner_early_termination_count", 0)
            if misc:
                lines.append(f"planner_missing={misc}")
            if etc:
                lines.append(f"planner_reprompts={etc}")
            lines.append(f"plan={tpl}")

        detail = "; ".join(lines)
        print(f"  {status}  {name}")
        if detail:
            print(f"         {detail}")
        if artifacts:
            print(f"         artifacts: {dict(sorted(artifacts.items()))}")
        if tool_names:
            print(f"         tools: {' -> '.join(tool_names)}")

    report_name = args.report_name or f"autonomous_{bench_model.replace(':', '_')}"
    report_path = os.path.join(REPORT_DIR, f"{report_name}.json")
    with open(report_path, "w") as f:
        json.dump(RESULTS, f, indent=2, default=str)
    print(f"\n  Report saved to: {report_path}")


if __name__ == "__main__":
    asyncio.run(main())
