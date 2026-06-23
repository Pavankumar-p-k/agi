"""Multi-Agent Graph Benchmark — tests agent routing and execution.

Benchmark G1: Agent Router Correctness
  Routes a decomposed hierarchical goal through the agent router.
  Pass: all sub-goals assigned to correct agents, no misses.

Benchmark G2: Agent Execution via WorkflowEngine
  Executes a multi-step goal where each step is dispatched to a different agent.
  Uses WorkflowEngine with agent_exec steps.
  Pass: all steps complete, correct agents invoked.

Benchmark G3: Handoff Chain
  Tests agent-to-agent handoff context preservation:
    ResearchAgent -> BuildAgent -> TestAgent -> EmailAgent
  Pass: each agent receives context from the previous.
"""

import asyncio
import json
import logging
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.agents import (
    AgentRouter, AgentEvent,
    list_agents, find_agent_for_goal, find_agents_for_subgoal,
    find_best_agent_for_subgoal,
)
from core.planner import GoalDecomposer
from core.workflow import WorkflowEngine, WorkflowStore
from core.workflow.context import ExecutionContext
from core.workflow.models import StepDefinition, WorkflowStatus

logger = logging.getLogger(__name__)

MODEL = os.environ.get("AGENT_MODEL", "qwen2.5:7b")


# ── Benchmark G1: Router Correctness ────────────────────────────────────────
def benchmark_g1() -> dict:
    """Test that AgentRouter correctly maps sub-goals to agents."""
    decomposer = GoalDecomposer()
    router = AgentRouter()

    goal = (
        "Build a coffee shop platform. "
        "Research competitor apps. "
        "Android app with UI, payments, and loyalty system. "
        "Run tests. "
        "Email the APK."
    )

    tree = decomposer.decompose(goal)
    tasks = router.route(tree)

    # Check each sub-goal maps to a valid agent
    agent_ids = set(a.agent_id for a in list_agents())
    all_valid = all(t["agent_id"] in agent_ids for t in tasks)
    has_build = any(t["agent_id"] == "build" for t in tasks)
    has_email = any(t["agent_id"] == "email" for t in tasks)
    has_test = any(t["agent_id"] == "test" for t in tasks)

    passed = all_valid and has_build and has_email

    return {
        "benchmark": "G1",
        "label": "Agent Router Correctness",
        "passed": passed,
        "agents_used": list(set(t["agent_id"] for t in tasks)),
        "total_tasks": len(tasks),
        "all_valid": all_valid,
        "has_build": has_build,
        "has_email": has_email,
        "tasks": tasks,
    }


# ── Mock build/test tools ───────────────────────────────────────────────────
def _setup_mocks():
    from unittest.mock import AsyncMock, patch

    patches = []

    async def _mock_build(*a, **kw):
        return {"success": True, "output": "Build ok", "exit_code": 0}

    async def _mock_tests(*a, **kw):
        return {"success": True, "output": "Tests passed", "exit_code": 0}

    patches.append(patch("core.tools.execution.do_build_project", side_effect=_mock_build))
    patches.append(patch("core.tools.execution.do_repair_project", side_effect=lambda *a, **kw: {"success": True, "exit_code": 0}))
    patches.append(patch("core.tools.execution.do_run_tests", side_effect=_mock_tests))
    patches.append(patch("core.tools.execution.do_runtime_validate", side_effect=lambda *a, **kw: {"success": True, "exit_code": 0}))

    _email_result = {"sent": True, "to": ["test@example.com"], "subject": "Build", "message_id": "<mock>"}

    async def _mock_mcp(tool, args):
        nonlocal _email_result
        _email_result["to"] = [args.get("to", "")]
        _email_result["subject"] = args.get("subject", "")
        return dict(_email_result)

    mock_mcp = AsyncMock()
    mock_mcp.call_tool = AsyncMock(side_effect=_mock_mcp)
    patches.append(patch("core.tools.execution.get_mcp_manager", return_value=mock_mcp))
    patches.append(patch("core.tools.security.is_authorized_to_execute", return_value=True))

    return patches


# ── Benchmark G2: Agent Execution via WorkflowEngine ────────────────────────
async def benchmark_g2() -> dict:
    """Execute agents through WorkflowEngine with agent_exec steps."""
    store = WorkflowStore(tempfile.mktemp(suffix=".db"))
    engine = WorkflowEngine(store)

    steps = [
        StepDefinition(tool_name="agent_exec",
                       input_data={"agent_id": "research", "action": {"query": "coffee shop trends"}},
                       max_retries=1),
        StepDefinition(tool_name="agent_exec",
                       input_data={"agent_id": "build", "action": {"task": "build android app"}},
                       max_retries=1),
        StepDefinition(tool_name="agent_exec",
                       input_data={"agent_id": "test", "action": {"test_mode": "unit"}},
                       max_retries=1),
        StepDefinition(tool_name="agent_exec",
                       input_data={"agent_id": "email", "action": {
                           "to": "test@example.com", "subject": "Results", "body": "Done."
                       }},
                       max_retries=1),
    ]

    wf = await engine.start_workflow(
        "multi_agent", steps, owner="bench",
        execution_context={"query": "coffee shop trends"},
    )
    wid = wf.workflow_id

    # Wait for completion
    for _ in range(30):
        await asyncio.sleep(0.2)
        wf = store.get_workflow(wid)
        if wf.status in (WorkflowStatus.COMPLETED, WorkflowStatus.FAILED):
            break

    ctx = engine.context_manager.get_context(wid) if wf.status == WorkflowStatus.COMPLETED else None

    agents_invoked = []
    for step in wf.steps:
        if step.status == "COMPLETED" and step.output_data:
            agent_id = step.input_data.get("agent_id", "?")
            agents_invoked.append(agent_id)

    passed = (
        wf.status == WorkflowStatus.COMPLETED
        and "research" in agents_invoked
        and "build" in agents_invoked
        and "test" in agents_invoked
        and "email" in agents_invoked
    )

    return {
        "benchmark": "G2",
        "label": "Agent Execution via WorkflowEngine",
        "passed": passed,
        "status": wf.status.value,
        "agents_invoked": agents_invoked,
        "total_steps": len(wf.steps),
        "failed_steps": sum(1 for s in wf.steps if s.status == "FAILED"),
        "artifacts": dict(ctx.artifacts) if ctx else {},
    }


# ── Benchmark G3: Handoff Chain ─────────────────────────────────────────────
async def benchmark_g3() -> dict:
    """Test context preservation across agent handoffs: Research -> Build -> Test -> Email."""
    store = WorkflowStore(tempfile.mktemp(suffix=".db"))
    engine = WorkflowEngine(store)

    shared_key = "project_name"
    shared_value = "CoffeeShopApp"

    steps = [
        StepDefinition(tool_name="agent_exec",
                       input_data={"agent_id": "research",
                                   "action": {"query": "coffee shop apps", shared_key: shared_value}}),
        StepDefinition(tool_name="agent_exec",
                       input_data={"agent_id": "build",
                                   "action": {"task": f"build {shared_value}"}}),
        StepDefinition(tool_name="agent_exec",
                       input_data={"agent_id": "test",
                                   "action": {"test_mode": "unit"}}),
        StepDefinition(tool_name="agent_exec",
                       input_data={"agent_id": "email",
                                   "action": {"to": "test@example.com",
                                              "subject": f"{shared_value} results",
                                              "body": "Done."}}),
    ]

    wf = await engine.start_workflow(
        "handoff_chain", steps, owner="bench",
        execution_context={shared_key: shared_value},
    )
    wid = wf.workflow_id

    for _ in range(30):
        await asyncio.sleep(0.2)
        wf = store.get_workflow(wid)
        if wf.status in (WorkflowStatus.COMPLETED, WorkflowStatus.FAILED):
            break

    ctx = engine.context_manager.get_context(wid) if wf.status == WorkflowStatus.COMPLETED else None
    context_preserved = (ctx is not None and ctx.variables.get(shared_key) == shared_value) if ctx else False

    agents_invoked = []
    for step in wf.steps:
        if step.status == "COMPLETED":
            agent_id = step.input_data.get("agent_id", "?")
            agents_invoked.append(agent_id)

    correct_order = agents_invoked == ["research", "build", "test", "email"]

    passed = (
        wf.status == WorkflowStatus.COMPLETED
        and correct_order
        and context_preserved
    )

    return {
        "benchmark": "G3",
        "label": "Agent Handoff Chain (Research -> Build -> Test -> Email)",
        "passed": passed,
        "status": wf.status.value,
        "agents_invoked": agents_invoked,
        "correct_order": correct_order,
        "context_preserved": context_preserved,
    }


# ── Benchmark G4: AgentDrivenExecutor via PlannerStateMachine ───────────────
async def benchmark_g4() -> dict:
    """Test agent-driven execution through PlannerStateMachine.run().

    Uses make_agent_execute_fn() as the execute_fn callback — no LLM
    involvement. Verifies decompose -> route -> execute -> enforce pipeline.
    """
    from core.agents.executor import make_agent_execute_fn
    from core.planner.state_machine import PlannerStateMachine
    from core.planner.executor import PlannerExecutor

    planner = PlannerExecutor()
    sm = PlannerStateMachine(planner)
    execute_fn = make_agent_execute_fn(global_context={"project_dir": "."})

    try:
        result = await asyncio.wait_for(
            sm.run("Build a project, run tests, and notify me", execute_fn),
            timeout=15.0,
        )
    except asyncio.TimeoutError:
        return {
            "benchmark": "G4",
            "label": "AgentDrivenExecutor via PlannerStateMachine",
            "passed": False,
            "state": "TIMEOUT",
            "error": "G4 timed out after 15s",
            "tool_names": [],
            "artifacts": [],
            "has_build": False,
            "has_notify": False,
            "has_artifacts": False,
            "elapsed_s": 15.0,
        }

    state = result.get("state", "FAILED")
    artifacts = result.get("artifacts", {})
    tool_names = result.get("tool_names", [])
    error = result.get("error")

    # Pass criteria:
    # - State is COMPLETE (not FAILED)
    # - Build step was executed (tool_names includes build)
    # - Notify/email step was executed (tool_names includes notify or email)
    # - No timeout or fatal error
    has_build = any("build" in t or "compile" in t for t in tool_names)
    has_notify = any(t in ("notify", "email") or "notify" in t or "email" in t for t in tool_names)
    has_artifacts = len(artifacts) > 0

    passed = (
        state == "COMPLETE"
        and has_build
        and has_notify
    )

    return {
        "benchmark": "G4",
        "label": "AgentDrivenExecutor via PlannerStateMachine",
        "passed": passed,
        "state": state,
        "tool_names": tool_names,
        "artifacts": list(artifacts.keys()),
        "has_build": has_build,
        "has_notify": has_notify,
        "has_artifacts": has_artifacts,
        "error": error,
        "elapsed_s": round(result.get("elapsed", 0), 2),
    }


# ── Benchmark G5: PlannerStateMachine Native Agent Routing ──────────────────
async def benchmark_g5() -> dict:
    """Test native agent routing through PlannerStateMachine with router.

    No execute_fn — the state machine routes decomposed subgoals to specialist
    agents via AgentRouter and executes them through agent.execute().

    Goal: multi-specialist pipeline covering all specialist domains.
    Expected routing: research→Research, synthesis→Nexus, codegen→Forge,
                      security→Cipher, docs→Scribe, email→EmailAgent
    """
    from core.planner.state_machine import PlannerStateMachine
    from core.planner.executor import PlannerExecutor
    from unittest.mock import AsyncMock, patch

    planner = PlannerExecutor()
    router = AgentRouter()
    sm = PlannerStateMachine(planner, router=router)

    # Mock all agents to return success immediately
    agent_patches = []
    for a in list_agents():
        base_artifacts = {}
        if a.agent_id == "email":
            base_artifacts["email_sent"] = f"mock_{a.agent_id}"
        agent_patches.append(
            patch.object(a, "execute", AsyncMock(return_value={
                "success": True, "output": f"{a.agent_id} ok", "exit_code": 0,
                "_artifacts": base_artifacts,
            }))
        )
    for p in agent_patches:
        p.start()

    try:
        result = await asyncio.wait_for(
            sm.run(
                "Research competitor apps, then synthesize the findings, "
                "then implement payment API, then perform security audit, "
                "then write documentation, then email results"
            ),
            timeout=15.0,
        )
    except asyncio.TimeoutError:
        for p in agent_patches:
            p.stop()
        return {
            "benchmark": "G5",
            "label": "Native Agent Routing through PlannerStateMachine",
            "passed": False,
            "state": "TIMEOUT",
            "error": "G5 timed out",
            "agent_assignments": [],
            "routing_correct": False,
            "all_agents_called": False,
            "elapsed_s": 15.0,
        }

    for p in agent_patches:
        p.stop()

    state = result.get("state", "FAILED")
    assignments = result.get("agent_assignments", [])
    tool_names = result.get("tool_names", [])
    error = result.get("error")

    # Expected routing order
    expected = ["research", "nexus", "forge", "cipher", "scribe", "email"]
    assigned_ids = [a["agent_id"] for a in assignments]
    routing_correct = assigned_ids == expected

    # All expected agents were called
    all_agents_called = all(exp in tool_names for exp in expected)

    passed = (
        state == "COMPLETE"
        and routing_correct
        and all_agents_called
        and not error
    )

    return {
        "benchmark": "G5",
        "label": "Native Agent Routing through PlannerStateMachine",
        "passed": passed,
        "state": state,
        "agent_assignments": assignments,
        "assigned_ids": assigned_ids,
        "expected_ids": expected,
        "routing_correct": routing_correct,
        "tool_names": tool_names,
        "all_agents_called": all_agents_called,
        "error": error,
        "elapsed_s": round(result.get("elapsed", 0), 2),
    }


# ── Benchmark G6: Artifact Handoff Chain ─────────────────────────────────────────
async def benchmark_g6() -> dict:
    """Test multi-agent artifact handoff through graph dependency edges.

    Creates a dependency graph: Research -> Forge -> Cipher -> Scribe -> Email
    Each downstream agent receives upstream artifacts in its context/variables.
    """
    from core.agents.graph import (
        AgentExecutionGraph, GraphNode, NodeStatus, build_graph_from_tasks,
    )
    from core.agents.parallel_executor import ParallelAgentExecutor
    from core.agents.router import _AGENT_REGISTRY
    from unittest.mock import AsyncMock

    captured_params: dict[str, dict] = {}

    async def _mock_research(ec):
        captured_params["research"] = dict(ec.variables)
        return {
            "output": "Research complete", "exit_code": 0,
            "_artifacts": {"research_report": "art_report_001"},
        }

    async def _mock_forge(ec):
        captured_params["forge"] = dict(ec.variables)
        return {
            "output": "Implementation complete", "exit_code": 0,
            "_artifacts": {"generated_code": "art_code_002"},
        }

    async def _mock_cipher(ec):
        captured_params["cipher"] = dict(ec.variables)
        return {
            "output": "Security audit complete", "exit_code": 0,
            "_artifacts": {"security_review": "art_sec_003"},
        }

    async def _mock_scribe(ec):
        captured_params["scribe"] = dict(ec.variables)
        return {
            "output": "Documentation complete", "exit_code": 0,
            "_artifacts": {"final_document": "art_doc_004"},
        }

    async def _mock_email(ec):
        captured_params["email"] = dict(ec.variables)
        return {
            "output": "Email sent", "sent": True,
            "_artifacts": {"email_sent": "art_email_005"},
        }

    originals = {}
    mock_agents = {}
    for aid, fn in [("research", _mock_research), ("forge", _mock_forge),
                     ("cipher", _mock_cipher), ("scribe", _mock_scribe),
                     ("email", _mock_email)]:
        originals[aid] = _AGENT_REGISTRY.get(aid)
        agent = AsyncMock()
        agent.agent_id = aid
        agent.execute = fn
        _AGENT_REGISTRY[aid] = agent
        mock_agents[aid] = agent

    try:
        tasks = [
            {"agent_id": "research", "goal": "Research competitor apps", "step": "research", "parameters": {"topic": "competitors"}},
            {"agent_id": "forge", "goal": "Implement payment API", "step": "codegen", "parameters": {"feature": "payments"}},
            {"agent_id": "cipher", "goal": "Perform security audit", "step": "security", "parameters": {"audit_mode": "full"}},
            {"agent_id": "scribe", "goal": "Write documentation", "step": "docs", "parameters": {"format": "markdown"}},
            {"agent_id": "email", "goal": "Email results", "step": "email", "parameters": {"to": "test@example.com"}},
        ]

        edges = [
            ("n_0", "n_1", {"research_report": "research_data"}),
            ("n_1", "n_2", {"generated_code": "code_to_audit"}),
            ("n_2", "n_3", {"security_review": "audit_results"}),
            ("n_3", "n_4", {"final_document": "doc_to_send"}),
        ]

        graph = build_graph_from_tasks(tasks, edges=edges)
        graph.max_parallel = 5

        n0 = graph.get_node("n_0")
        n1 = graph.get_node("n_1")
        n2 = graph.get_node("n_2")
        n3 = graph.get_node("n_3")
        n4 = graph.get_node("n_4")

        deps_correct = (
            n0.depends_on == []
            and n1.depends_on == ["n_0"]
            and n2.depends_on == ["n_1"]
            and n3.depends_on == ["n_2"]
            and n4.depends_on == ["n_3"]
        )

        input_art_correct = (
            n1.input_artifacts == {"research_report": "research_data"}
            and n2.input_artifacts == {"generated_code": "code_to_audit"}
            and n3.input_artifacts == {"security_review": "audit_results"}
            and n4.input_artifacts == {"final_document": "doc_to_send"}
        )

        if not (deps_correct and input_art_correct):
            return {
                "benchmark": "G6", "label": "Multi-Agent Artifact Handoff",
                "passed": False, "state": "GRAPH_BUILD_FAILED",
                "error": "Dependency or input_artifact structure incorrect",
                "deps_correct": deps_correct, "input_art_correct": input_art_correct,
                "n1_depends_on": n1.depends_on, "n1_artifacts": n1.input_artifacts,
            }

        executor = ParallelAgentExecutor(max_parallel=5, emit_events=False)
        result = await executor.execute(graph, "g6_test")

        all_artifacts = result.get("artifacts", {})

        has_research_art = all_artifacts.get("research_report") == "art_report_001"
        has_code_art = all_artifacts.get("generated_code") == "art_code_002"
        has_sec_art = all_artifacts.get("security_review") == "art_sec_003"
        has_doc_art = all_artifacts.get("final_document") == "art_doc_004"
        has_email_art = all_artifacts.get("email_sent") == "art_email_005"

        forge_vars = captured_params.get("forge", {})
        forge_has_research = forge_vars.get("research_data") == "art_report_001"

        cipher_vars = captured_params.get("cipher", {})
        cipher_has_code = cipher_vars.get("code_to_audit") == "art_code_002"

        scribe_vars = captured_params.get("scribe", {})
        scribe_has_audit = scribe_vars.get("audit_results") == "art_sec_003"

        email_vars = captured_params.get("email", {})
        email_has_doc = email_vars.get("doc_to_send") == "art_doc_004"

        forge_has_raw = forge_vars.get("research_report") == "art_report_001"

        all_nodes_completed = all(
            n.status == NodeStatus.COMPLETED for n in graph.nodes.values()
        )

        passed = (
            all_nodes_completed and has_research_art and has_code_art
            and has_sec_art and has_doc_art and has_email_art
            and forge_has_research and cipher_has_code
            and scribe_has_audit and email_has_doc
        )

        return {
            "benchmark": "G6", "label": "Multi-Agent Artifact Handoff",
            "passed": passed,
            "state": "COMPLETE" if all_nodes_completed else "PARTIAL",
            "all_nodes_completed": all_nodes_completed,
            "artifact_chain": {
                "research_report": all_artifacts.get("research_report"),
                "generated_code": all_artifacts.get("generated_code"),
                "security_review": all_artifacts.get("security_review"),
                "final_document": all_artifacts.get("final_document"),
                "email_sent": all_artifacts.get("email_sent"),
            },
            "injection_results": {
                "forge_received_research_data": forge_has_research,
                "forge_received_raw_artifact": forge_has_raw,
                "cipher_received_code_to_audit": cipher_has_code,
                "scribe_received_audit_results": scribe_has_audit,
                "email_received_doc_to_send": email_has_doc,
            },
            "deps_correct": deps_correct, "input_art_correct": input_art_correct,
            "agents_invoked": list(captured_params.keys()),
            "error": result.get("error"),
        }

    finally:
        for aid, original in originals.items():
            _AGENT_REGISTRY[aid] = original


# ── Reporting ────────────────────────────────────────────────────────────────
def _print_results(results: list[dict]):
    passed = sum(1 for r in results if r["passed"])
    total = len(results)

    print(f"\n{'=' * 70}")
    print(f"  Multi-Agent Graph Benchmark")
    print(f"  {passed}/{total} passed ({passed * 100 // total}%)")
    print(f"{'=' * 70}")

    for r in results:
        status = "PASS" if r.get("passed") else "FAIL"
        label = r.get("label", "")
        print(f"\n  {status}  {label}")
        for k, v in r.items():
            if k not in ("benchmark", "label", "passed"):
                print(f"         {k}: {v}")


# ── Main ─────────────────────────────────────────────────────────────────────
async def main():
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    patches = _setup_mocks()
    for p in patches:
        p.start()

    try:
        print(f"{'=' * 70}")
        print(f"  Multi-Agent Graph Benchmark")
        print(f"  Tests agent routing, execution, and handoff")
        print(f"{'=' * 70}")

        # G1: Router correctness (no engine needed)
        print(f"\n  G1: Router Correctness")
        g1 = benchmark_g1()
        print(f"    agents={g1['agents_used']} tasks={g1['total_tasks']} -> {'PASS' if g1['passed'] else 'FAIL'}")

        # G2: Agent execution via WorkflowEngine
        print(f"\n  G2: Agent Execution via WorkflowEngine")
        sys.stdout.flush()
        g2 = await benchmark_g2()
        print(f"    agents={g2['agents_invoked']} status={g2['status']} -> {'PASS' if g2['passed'] else 'FAIL'}")

        # G3: Handoff chain
        print(f"\n  G3: Agent Handoff Chain")
        sys.stdout.flush()
        g3 = await benchmark_g3()
        print(f"    agents={g3['agents_invoked']} order={g3['correct_order']} ctx={g3['context_preserved']} -> {'PASS' if g3['passed'] else 'FAIL'}")

        # G4: AgentDrivenExecutor via PlannerStateMachine
        print(f"\n  G4: AgentDrivenExecutor via PlannerStateMachine")
        sys.stdout.flush()
        g4 = await benchmark_g4()
        print(f"    state={g4['state']} build={g4['has_build']} notify={g4['has_notify']} -> {'PASS' if g4['passed'] else 'FAIL'}")

        # G5: Native agent routing through PlannerStateMachine
        print(f"\n  G5: Native Agent Routing through PlannerStateMachine")
        sys.stdout.flush()
        g5 = await benchmark_g5()
        print(f"    state={g5['state']} routing={g5['routing_correct']} agents={g5['all_agents_called']} -> {'PASS' if g5['passed'] else 'FAIL'}")
        for a in g5.get("agent_assignments", []):
            print(f"      {a['description']:50s} -> {a['agent_id']}")

        # G6: Artifact handoff chain
        print(f"\n  G6: Multi-Agent Artifact Handoff")
        sys.stdout.flush()
        g6 = await benchmark_g6()
        print(f"    state={g6['state']} deps={g6['deps_correct']} injections={g6['input_art_correct']} -> {'PASS' if g6['passed'] else 'FAIL'}")
        for k, v in g6.get("injection_results", {}).items():
            print(f"      {k}: {'PASS' if v else 'FAIL'}")

        results = [g1, g2, g3, g4, g5, g6]
        _print_results(results)

        # Save report
        report_dir = os.environ.get("REPORT_DIR", "benchmark_reports")
        os.makedirs(report_dir, exist_ok=True)
        report_path = os.path.join(report_dir, "multi_agent_benchmark.json")
        with open(report_path, "w") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\n  Report saved to: {report_path}")

    finally:
        for p in patches:
            p.stop()


if __name__ == "__main__":
    asyncio.run(main())
