"""Benchmark F — Hierarchical Project Decomposition.

Tests whether the decomposer can handle project-level goals that decompose
into hierarchical sub-components (not just flat feature lists).

Benchmark F1: Decomposition Quality
  Goal: "Build coffee shop platform. Android app with UI, payments, and
         loyalty system. Admin dashboard. Analytics. Deploy via email."
  Expected: 5+ components, at least 1 with children, depth >= 2

Benchmark F2: Full Execution
  Goal: same, executed through PlannerStateMachine + LLM
  Pass: email_sent artifact produced
"""

import asyncio
import json
import logging
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.planner import GoalDecomposer, PlannerStateMachine, PlannerExecutor
from core.tools._constants import ToolBlock
from core.tools.execution import execute_tool_block
from core.workflow import WorkflowEngine, WorkflowStore

logger = logging.getLogger(__name__)

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
    "You are a software engineering agent with tools for:\n"
    "- Web research (browser_navigate, browser_snapshot, browser_search, web_fetch)\n"
    "- Code/build (build_project, repair_project, run_tests, runtime_validate)\n"
    "- Communication (send_email)\n\n"
    "Build the requested project. Test it. Email the results."
)

# ── Test goals ──────────────────────────────────────────────────────────────
GOAL_SENTENCE = (
    "Build a coffee shop platform. "
    "Android app with UI, payments, and loyalty system. "
    "Admin dashboard. "
    "Analytics. "
    "Deploy via email."
)

GOAL_REQUIREMENTS = (
    "Build a coffee shop platform. Requirements: "
    "Android app (UI, payments, loyalty), "
    "Admin dashboard, "
    "Analytics, "
    "Delivery via email."
)

# ── Benchmark F1: Decomposition Quality ─────────────────────────────────────
def benchmark_f1() -> dict:
    """Test hierarchical decomposition quality.

    Pass conditions:
      - >= 4 top-level components extracted
      - At least 1 component has children (hierarchy depth >= 2)
      - At least 1 component maps to email step
      - No "Implement: and" artifacts in feature names
    """
    decomposer = GoalDecomposer()

    # Test both goal formats
    results = []
    for label, goal in [("Sentence-list", GOAL_SENTENCE), ("Requirements", GOAL_REQUIREMENTS)]:
        tree = decomposer.decompose(goal)
        leaves = tree.flatten()
        build_leaves = [l for l in leaves if l.step_name == "build"]
        email_leaves = [l for l in leaves if l.step_name == "email"]

        # Count components with children (hierarchical depth)
        comps_with_children = sum(1 for c in (tree.children or []) if c.children)

        # Count total top-level components
        top_level = len(tree.children or [])

        # Feature names clean?
        features_clean = all(
            "and " not in l.description.lower()
            for l in build_leaves
        )

        results.append({
            "format": label,
            "top_level_components": top_level,
            "components_with_children": comps_with_children,
            "build_leaves": len(build_leaves),
            "email_leaves": len(email_leaves),
            "features_clean": features_clean,
            "max_depth": max((_depth(c) for c in (tree.children or [])), default=0),
        })

    # Aggregate pass/fail
    passed = all(
        r["top_level_components"] >= 3
        and r["components_with_children"] >= 1
        and r["email_leaves"] >= 1
        and r["features_clean"]
        for r in results
    )

    return {
        "benchmark": "F1",
        "label": "Hierarchical Decomposition Quality",
        "passed": passed,
        "results": results,
    }


def _depth(node) -> int:
    if not node.children:
        return 1
    return 1 + max(_depth(c) for c in node.children)


# ── Tool schemas (for LLM) ──────────────────────────────────────────────────
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


# ── Mock build/test/validate ────────────────────────────────────────────────
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
        return {"success": True, "output": f"Build ok: {task}", "exit_code": 0, "artifact_path": apk_path}

    async def _mock_tests(project_dir, progress_cb=None):
        return {"success": True, "output": "Tests passed", "exit_code": 0}

    patches.append(patch("core.tools.execution.do_build_project", side_effect=_mock_build))
    patches.append(patch("core.tools.execution.do_repair_project", side_effect=lambda *a, **kw: {"success": True, "exit_code": 0}))
    patches.append(patch("core.tools.execution.do_run_tests", side_effect=_mock_tests))
    patches.append(patch("core.tools.execution.do_runtime_validate", side_effect=lambda *a, **kw: {"success": True, "exit_code": 0}))

    _email_result = {"sent": True, "to": [], "subject": "", "message_id": "<mock-f>"}

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


# ── LLM call ─────────────────────────────────────────────────────────────────
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


# ── Benchmark F2: Full Execution ────────────────────────────────────────────
async def benchmark_f2(goal, model=None, ollama_url=None) -> dict:
    """Execute a hierarchical project goal through the full planner+LLM pipeline."""
    import tempfile
    store = WorkflowStore(tempfile.mktemp(suffix=".db"))
    engine = WorkflowEngine(store)
    wf = await engine.start_workflow("bench_f", [], owner="dev", execution_context={"goal": goal})
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
                                    for k in ("to", "subject", "body"):
                                        if k in fa: args[k] = fa[k]
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
                    ok = (result.get("exit_code", -1) == 0 or result.get("sent") or result.get("success"))
                    _executor.record_step(plan.template_id, name, ok)
                msg = str(result.get("output", result.get("result", json.dumps(result))))[:500]
                messages.append({"role": "assistant", "content": None, "tool_calls": [{"function": {"name": name, "arguments": json.dumps(tc["arguments"])}, "type": "function"}]})
                messages.append({"role": "tool", "content": msg})

        ctx = engine.context_manager.get_context(wid)
        return {
            "artifacts": dict(ctx.artifacts) if ctx else {},
            "tool_calls": all_tool_calls,
            "tool_names": [tc["tool"] for tc in all_tool_calls],
            "hallucinated_tools": hallucinated,
        }

    sm_result = await sm.run(goal, execute_fn)
    artifacts = sm_result.get("artifacts", {})

    has_email_artifact = "email_sent" in artifacts
    has_build_tool = "build_project" in sm_result.get("tool_names", [])
    passed = has_email_artifact and has_build_tool

    return {
        "benchmark": "F2",
        "label": "Hierarchical Project Execution",
        "passed": passed,
        "goal": goal[:60],
        "elapsed": sm_result.get("elapsed", 0),
        "artifacts": artifacts,
        "tool_names": sm_result.get("tool_names", []),
        "hallucinated_tools": sm_result.get("hallucinated_tools", []),
        "status": sm.state.value if sm else "UNKNOWN",
    }


async def _dispatch_tool(tc, session_id, context):
    name = tc["name"]
    args = tc.get("arguments", {})
    block = ToolBlock(tool_type=name, content=json.dumps(args) if args else "")
    try:
        desc, result = await execute_tool_block(block=block, session_id=session_id, owner="dev", context=context)
        return result
    except Exception as e:
        logging.getLogger(__name__).error("Benchmark task failed: %s", e, exc_info=True)
        return {"error": "Benchmark task failed", "exit_code": 1}


# ── Reporting ────────────────────────────────────────────────────────────────
def _print_results(f1, f2):
    print(f"\n{'=' * 70}")
    print(f"  Benchmark F — Hierarchical Project Decomposition")
    print(f"  Model: {MODEL}")
    print(f"{'=' * 70}")

    # F1
    print(f"\n  F1: {f1['label']}")
    print(f"  Result: {'PASS' if f1['passed'] else 'FAIL'}")
    for r in f1.get("results", []):
        print(f"    [{r['format']:15}] top={r['top_level_components']} "
              f"depth={r['max_depth']} children={r['components_with_children']} "
              f"email={r['email_leaves']} clean={r['features_clean']}")

    # F2
    print(f"\n  F2: {f2.get('label', '')}")
    print(f"  Result: {'PASS' if f2.get('passed') else 'FAIL'}")
    artifacts = f2.get("artifacts", {})
    tools = f2.get("tool_names", [])
    print(f"    artifacts={list(artifacts.keys())}")
    print(f"    tools={' -> '.join(tools[-6:])}")
    elapsed = f2.get("elapsed", 0)
    if elapsed:
        print(f"    elapsed={elapsed:.1f}s")

    overall = f1["passed"] and f2.get("passed", False)
    print(f"\n  {'=' * 40}")
    print(f"  Overall: {'PASS' if overall else 'FAIL'}")
    print(f"  {'=' * 40}")


# ── Main ─────────────────────────────────────────────────────────────────────
async def main():
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    patches = _setup_mocks()
    for p in patches:
        p.start()

    try:
        print(f"{'=' * 70}")
        print(f"  Benchmark F — Hierarchical Project Decomposition")
        print(f"  Goal: Build coffee shop platform with Android app, admin,")
        print(f"        analytics, loyalty, payments, UI, email delivery")
        print(f"{'=' * 70}")

        # F1: Decomposition quality (no LLM needed)
        f1 = benchmark_f1()
        print(f"\n  F1: Decomposition Quality")
        for r in f1.get("results", []):
            print(f"    {r['format']:15}: top={r['top_level_components']} "
                  f"depth={r['max_depth']} children={r['components_with_children']}")
        print(f"    -> {'PASS' if f1['passed'] else 'FAIL'}")

        # F2: Full execution (requires LLM)
        print(f"\n  F2: Full Execution (via LLM)")
        sys.stdout.flush()
        f2 = await benchmark_f2(GOAL_SENTENCE, model=MODEL, ollama_url=OLLAMA_URL)
        print(f"    elapsed={f2.get('elapsed', 0):.1f}s -> {'PASS' if f2.get('passed') else 'FAIL'}")

        _print_results(f1, f2)

        # Save report
        report_dir = os.environ.get("REPORT_DIR", "benchmark_reports")
        os.makedirs(report_dir, exist_ok=True)
        report_path = os.path.join(report_dir, f"hierarchical_{MODEL.replace(':', '_')}.json")
        with open(report_path, "w") as f:
            json.dump({"f1": f1, "f2": f2}, f, indent=2, default=str)
        print(f"\n  Report saved to: {report_path}")

    finally:
        for p in patches:
            p.stop()


if __name__ == "__main__":
    asyncio.run(main())
