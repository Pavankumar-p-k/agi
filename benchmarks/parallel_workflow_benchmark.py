"""Parallel Workflow Benchmark — tests decomposition and execution of multi-feature goals.

Unlike the sequential benchmarks (A-D), this benchmark validates that the
GoalDecomposer can extract parallel features from a complex goal and that the
PlannerStateMachine can orchestrate a workflow with multiple parallel sub-goals.

Benchmark E: Parallel Feature Extraction + Execution
  Goal: Build a coffee shop Android app with loyalty system, payment
        integration, admin dashboard, customer app, and analytics
  Expected: 5 feature sub-goals + build + test + validate + email
  Pass: All 5 features extracted; email_sent artifact produced
"""

import asyncio
import json
import logging
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.planner import GoalDecomposer, PlannerExecutor, PlannerStateMachine
from core.tools._constants import ToolBlock
from core.tools.execution import execute_tool_block
from core.workflow import WorkflowEngine, WorkflowStore
from core.workflow.models import WorkflowStatus

logger = logging.getLogger(__name__)

RESULTS = []

# ── Config ──────────────────────────────────────────────────────────────────
MAX_TURNS = int(os.environ.get("MAX_TURNS", "12"))
TASK_TIMEOUT = int(os.environ.get("TASK_TIMEOUT", "240"))
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
MODEL = os.environ.get("AGENT_MODEL", "qwen2.5:7b")

VALID_TOOLS = {
    "browser_navigate", "browser_snapshot", "browser_search", "browser_click",
    "browser_fill", "browser_press", "browser_evaluate", "browser_screenshot",
    "web_fetch", "build_project", "repair_project", "run_tests",
    "runtime_validate", "send_email", "delete_email", "read_email", "list_emails",
}

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
    "5. Keep using tools until the task is complete.\n"
    "6. When multiple features are requested, build them incrementally.\n"
)

# ── Tool Schemas ────────────────────────────────────────────────────────────
def _build_tool_schemas():
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

# ── Mock Setup ──────────────────────────────────────────────────────────────
def _setup_mocks():
    from unittest.mock import AsyncMock, patch
    patches = []

    async def _mock_build(task, project_dir, progress_cb=None):
        apk_dir = os.path.join(project_dir, "app", "build", "outputs", "apk", "debug")
        os.makedirs(apk_dir, exist_ok=True)
        apk_path = os.path.join(apk_dir, "app-debug.apk")
        with open(apk_path, "wb") as f:
            f.write(b"fake apk")
        log_path = os.path.join(project_dir, "build.log")
        with open(log_path, "w") as f:
            f.write(f"Build completed for: {task}\n")
        return {"success": True, "output": f"Build completed: {task}", "exit_code": 0, "artifact_path": apk_path}

    async def _mock_repair(project_dir, build_output, progress_cb=None):
        return {"success": True, "output": "Repair completed", "exit_code": 0}

    async def _mock_tests(project_dir, progress_cb=None):
        return {"success": True, "output": "All tests passed", "exit_code": 0}

    async def _mock_validate(project_dir, progress_cb=None):
        return {"success": True, "output": "Validation passed", "exit_code": 0}

    patches.append(patch("core.tools.execution.do_build_project", side_effect=_mock_build))
    patches.append(patch("core.tools.execution.do_repair_project", side_effect=_mock_repair))
    patches.append(patch("core.tools.execution.do_run_tests", side_effect=_mock_tests))
    patches.append(patch("core.tools.execution.do_runtime_validate", side_effect=_mock_validate))

    _email_result = {"sent": True, "to": ["recipient@example.com"], "subject": "", "message_id": "<mock@benchmark>"}

    async def _mock_mcp_call(tool, args):
        nonlocal _email_result
        _email_result["subject"] = args.get("subject", "")
        _email_result["to"] = [args.get("to", "")]
        return dict(_email_result)

    mock_mcp = AsyncMock()
    mock_mcp.call_tool = AsyncMock(side_effect=_mock_mcp_call)
    patches.append(patch("core.tools.execution.get_mcp_manager", return_value=mock_mcp))
    patches.append(patch("core.tools.security.is_authorized_to_execute", return_value=True))

    return patches


# ── LLM Call ─────────────────────────────────────────────────────────────────
async def call_llm(messages, model=None, ollama_url=None):
    import httpx
    model = model or MODEL
    ollama_url = ollama_url or OLLAMA_URL
    payload = {"model": model, "messages": messages, "stream": True, "tools": TOOL_SCHEMAS}
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


# ── Benchmark E ──────────────────────────────────────────────────────────────
async def benchmark_e(executor, model=None, ollama_url=None) -> dict:
    """Parallel feature extraction + execution benchmark."""
    goal = (
        "Build a coffee shop Android app with loyalty system, payment "
        "integration, admin dashboard, customer app, and analytics. "
        "Research trends first, then run tests, and email the APK."
    )

    # ── Phase 1: Decomposition Quality ─────────────────────────────────────
    decomposer = GoalDecomposer()
    tree = decomposer.decompose(goal)
    leaves = tree.flatten()
    feature_leaves = [l for l in leaves if "Implement:" in l.description]
    step_names = set(l.step_name for l in leaves)

    decomposition_ok = len(feature_leaves) >= 5
    has_build = "build" in step_names
    has_email = "email" in step_names
    features_clean = all(
        not l.description.lower().startswith("implement: and")
        for l in feature_leaves
    )

    decomposition = {
        "num_features": len(feature_leaves),
        "feature_names": [l.description.replace("Implement: ", "") for l in feature_leaves],
        "total_leaves": len(leaves),
        "has_build": has_build,
        "has_email": has_email,
        "features_clean": features_clean,
        "decomposition_ok": decomposition_ok and has_build and has_email and features_clean,
    }

    # ── Phase 2: Execution ─────────────────────────────────────────────────
    store = WorkflowStore(tempfile.mktemp(suffix=".db"))
    engine = WorkflowEngine(store)
    wf = await engine.start_workflow("bench_e", [], owner="dev", execution_context={"goal": goal})
    wid = wf.workflow_id
    context = engine.context_manager.get_context(wid)

    planner = PlannerExecutor()
    sm = PlannerStateMachine(planner)

    async def execute_fn(_goal, _executor):
        plan = _executor.create_plan(_goal)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _goal},
        ]
        all_tool_calls = []
        hallucinated = []
        loop_count = 0
        start = time.monotonic()

        for turn in range(MAX_TURNS):
            content, tool_calls = await call_llm(messages, model=model, ollama_url=ollama_url)

            if not tool_calls and plan is not None:
                tool_names = [tc["tool"] for tc in all_tool_calls]
                if not tool_names:
                    messages.append({"role": "user", "content": "Start working. Make your first tool call."})
                    continue
                missing = _executor.check_early_termination(plan.template_id, tool_names)
                if missing:
                    for step_name in missing:
                        async def enforce_step(tname, dargs):
                            args = dict(dargs)
                            if tname == "send_email":
                                _, forced_tc = await call_llm(
                                    messages + [{"role": "user", "content": "Provide params for send_email. Reply with ONLY a tool call containing to, subject, body."}],
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
                                    messages + [{"role": "user", "content": "Provide URL for browser_navigate. Reply with ONLY a tool call containing url."}],
                                    model=model, ollama_url=ollama_url,
                                )
                                if forced_tc:
                                    fa = forced_tc[0].get("arguments", {})
                                    if "url" in fa: args["url"] = fa["url"]
                            tb = ToolBlock(tool_type=tname, content=json.dumps(args))
                            desc, result = await execute_tool_block(block=tb, session_id=wid, owner="dev", context=context)
                            return result

                        task_info = _executor.get_task_for_step(plan.template_id, step_name)
                        if task_info:
                            result = await enforce_step(task_info["tool"], task_info.get("default_args", {}))
                        else:
                            result = {"exit_code": 1, "error": f"Unknown step: {step_name}"}
                        tn = task_info["tool"] if task_info else step_name
                        all_tool_calls.append({"tool": tn, "args": {}, "result": result, "enforced": True})
                        msg = str(result.get("output", result.get("result", json.dumps(result))))[:500]
                        messages.append({"role": "assistant", "content": None, "tool_calls": [{"function": {"name": tn, "arguments": "{}"}, "type": "function"}]})
                        messages.append({"role": "tool", "content": f"[Enforced] {msg}"})
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
                    hallucinated.append(name)
                result = await _dispatch_tool(tc, wid, context)
                all_tool_calls.append({"tool": name, "args": tc["arguments"], "result": result})
                if plan:
                    ok = (result.get("exit_code", -1) == 0 or result.get("sent") or result.get("success") or (result.get("error") is None and result.get("output")))
                    _executor.record_step(plan.template_id, name, ok)
                msg = str(result.get("output", result.get("result", json.dumps(result))))[:500]
                messages.append({"role": "assistant", "content": None, "tool_calls": [{"function": {"name": name, "arguments": json.dumps(tc["arguments"])}, "type": "function"}]})
                messages.append({"role": "tool", "content": msg})

            if time.monotonic() - start > TASK_TIMEOUT:
                break

        ctx = engine.context_manager.get_context(wid)
        return {
            "artifacts": dict(ctx.artifacts) if ctx else {},
            "tool_calls": all_tool_calls,
            "tool_names": [tc["tool"] for tc in all_tool_calls],
            "hallucinated_tools": hallucinated,
            "loop_count": loop_count,
            "completed_naturally": False,
            "planner_metrics": {},
        }

    sm_result = await sm.run(goal, execute_fn)
    artifacts = sm_result.get("artifacts", {})

    # ── Scoring ────────────────────────────────────────────────────────────
    has_email_artifact = "email_sent" in artifacts
    has_snapshot = "snapshot" in artifacts
    tool_names_list = sm_result.get("tool_names", [])
    has_build_tool = "build_project" in tool_names_list

    passed = (
        decomposition["decomposition_ok"]
        and has_email_artifact
        and has_build_tool
    )

    result = {
        "benchmark": "E",
        "label": "Parallel Feature Extraction + Execution",
        "goal": goal[:80],
        "passed": passed,
        "elapsed": sm_result.get("elapsed", 0),
        "status": sm.state.value if sm else "UNKNOWN",
        "artifacts": artifacts,
        "tool_names": tool_names_list,
        "num_features": decomposition["num_features"],
        "features_clean": decomposition["features_clean"],
        "features": decomposition["feature_names"],
        "has_email_artifact": has_email_artifact,
        "has_build_tool": has_build_tool,
        "decomposition": decomposition,
        "hallucinated_tools": sm_result.get("hallucinated_tools", []),
        "loop_count": sm_result.get("loop_count", 0),
        "state": sm.state.value if sm else "UNKNOWN",
    }
    return result


async def _dispatch_tool(tc, session_id, context):
    name = tc["name"]
    args = tc.get("arguments", {})
    block = ToolBlock(tool_type=name, content=json.dumps(args) if args else "")
    try:
        desc, result = await execute_tool_block(block=block, session_id=session_id, owner="dev", context=context)
        return result
    except Exception as e:
        return {"error": str(e), "exit_code": 1}


# ── Reporting ────────────────────────────────────────────────────────────────
def _print_results(results):
    passed = sum(1 for r in results if r.get("passed"))
    total = len(results)
    print(f"\n{'=' * 70}")
    print(f"  Parallel Workflow Benchmark")
    print(f"  Model: {MODEL}")
    print(f"  Result: {passed}/{total} passed ({passed * 100 // total}%)")
    print(f"{'=' * 70}")

    for r in results:
        status = "PASS" if r.get("passed") else "FAIL"
        label = r.get("label", "")
        elapsed = r.get("elapsed", 0)
        feats = r.get("num_features", 0)
        email = "email_sent" if r.get("has_email_artifact") else "no email"
        print(f"\n  {status}  {label}")
        print(f"         elapsed={elapsed:.1f}s  features={feats}  {email}")
        feats_list = r.get("features", [])
        if feats_list:
            print(f"         features: {', '.join(feats_list)}")
        tools = r.get("tool_names", [])
        if tools:
            print(f"         tools: {' -> '.join(tools[-8:])}")


# ── Main ─────────────────────────────────────────────────────────────────────
async def main():
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    patches = _setup_mocks()
    for p in patches:
        p.start()

    try:
        results = []
        print("=" * 70)
        print("  Parallel Workflow Benchmark")
        print(f"  Model: {MODEL}")
        print(f"  Max turns: {MAX_TURNS}, Timeout: {TASK_TIMEOUT}s")
        print("=" * 70)

        print("\n[Benchmark E]")
        print("  Running...")
        sys.stdout.flush()
        data = await benchmark_e(None, model=MODEL, ollama_url=OLLAMA_URL)
        results.append(data)
        _print_results(results)

        report_dir = os.environ.get("REPORT_DIR", "benchmark_reports")
        os.makedirs(report_dir, exist_ok=True)
        report_path = os.path.join(report_dir, f"parallel_{MODEL.replace(':', '_')}.json")
        with open(report_path, "w") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\n  Report saved to: {report_path}")

    finally:
        for p in patches:
            p.stop()


if __name__ == "__main__":
    asyncio.run(main())
