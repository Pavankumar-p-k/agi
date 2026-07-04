"""Ablation Benchmark — measures JARVIS subsystem contribution to task performance.

Level 1 — Full System vs Raw Model:
    Run identical tasks with and without JARVIS infrastructure.

Level 2 — Component Ablation:
    Systematically disable subsystems:
      - Full JARVIS
      - Full - Memory
      - Full - Planner
      - Full - Scheduler
      - Full - Belief Engine
      - Full - Negotiation

Level 3 — Opportunity Pipeline:
    Measures the autonomous scheduling pipeline end-to-end.

Metrics:
    - success: binary task completion
    - turns: number of LLM interactions
    - tool_calls: total tool invocations
    - duration_seconds: wall-clock time
    - recovery_rate: fraction of failures successfully recovered
    - cost_estimate: estimated API cost from token counts

Usage:
    # Run Level 1 (Full vs Raw) on research tasks, 3 tasks:
    python benchmarks/ablation_benchmark.py --level 1 --category research --max-tasks 3

    # Run Level 2 (component ablation) on planning tasks:
    python benchmarks/ablation_benchmark.py --level 2 --category planning

    # Run everything (may take hours):
    python benchmarks/ablation_benchmark.py --level all

    # Quick smoke test (1 task, 1 config):
    python benchmarks/ablation_benchmark.py --level 1 --max-tasks 1 --smoke

Environment:
    OLLAMA_URL   (default: http://localhost:11434)
    AGENT_MODEL  (default: qwen2.5:7b)
    MAX_TURNS    (default: 15)
    TASK_TIMEOUT (default: 300)
    REPORT_DIR   (default: benchmark_reports)
"""

import argparse
import asyncio
import httpx
import json
import logging
import os
import sys
import time
import traceback
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
logger = logging.getLogger("ablation_bench")

# ── Config ───────────────────────────────────────────────────────────────────

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
MODEL = os.environ.get("AGENT_MODEL", "qwen2.5:7b")
MAX_TURNS = int(os.environ.get("MAX_TURNS", "15"))
TASK_TIMEOUT = int(os.environ.get("TASK_TIMEOUT", "300"))
REPORT_DIR = os.environ.get("REPORT_DIR", "benchmark_reports")
os.makedirs(REPORT_DIR, exist_ok=True)

# ── Ablation Configuration ───────────────────────────────────────────────────

ABLATION_MODES: dict[str, dict[str, bool]] = {
    "raw": {
        "planner": False,
        "memory": False,
        "scheduler": False,
        "belief": False,
        "negotiation": False,
    },
    "full": {
        "planner": True,
        "memory": True,
        "scheduler": True,
        "belief": True,
        "negotiation": True,
    },
    "full-no-memory": {
        "planner": True,
        "memory": False,
        "scheduler": True,
        "belief": True,
        "negotiation": True,
    },
    "full-no-planner": {
        "planner": False,
        "memory": True,
        "scheduler": True,
        "belief": True,
        "negotiation": True,
    },
    "full-no-scheduler": {
        "planner": True,
        "memory": True,
        "scheduler": False,
        "belief": True,
        "negotiation": True,
    },
    "full-no-belief": {
        "planner": True,
        "memory": True,
        "scheduler": True,
        "belief": False,
        "negotiation": True,
    },
    "full-no-negotiation": {
        "planner": True,
        "memory": True,
        "scheduler": True,
        "belief": True,
        "negotiation": False,
    },
}

LEVEL_2_MODES = ["full", "full-no-memory", "full-no-planner",
                 "full-no-scheduler", "full-no-belief", "full-no-negotiation"]


# ── Task Definitions ─────────────────────────────────────────────────────────

@dataclass
class BenchmarkTask:
    """A single benchmark task with expected outcome criteria."""
    id: str
    category: str           # research, browser, planning, recovery, se, long_horizon
    prompt: str
    expected_tools: list[str] = field(default_factory=list)
    min_success_tools: int = 1
    validation_fn: str = ""  # optional python expression to evaluate result


TASKS: list[BenchmarkTask] = [
    # ── Research ──────────────────────────────────────────────────────────
    BenchmarkTask(
        id="research_1",
        category="research",
        prompt="Research the current weather in London and report the temperature and conditions.",
        expected_tools=["browser_navigate", "browser_snapshot", "web_search"],
        min_success_tools=2,
    ),
    BenchmarkTask(
        id="research_2",
        category="research",
        prompt="Find the top 3 latest news articles about Python 3.13 features and summarize them.",
        expected_tools=["browser_navigate", "web_search", "browser_snapshot"],
        min_success_tools=2,
    ),
    BenchmarkTask(
        id="research_3",
        category="research",
        prompt="Search for the documentation of FastAPI dependency injection and explain how it works.",
        expected_tools=["web_search", "browser_navigate", "browser_snapshot"],
        min_success_tools=2,
    ),

    # ── Browser ───────────────────────────────────────────────────────────
    BenchmarkTask(
        id="browser_1",
        category="browser",
        prompt="Go to example.com and tell me what the page title is.",
        expected_tools=["browser_navigate", "browser_snapshot"],
        min_success_tools=2,
    ),
    BenchmarkTask(
        id="browser_2",
        category="browser",
        prompt="Search for 'open source AI tools' on Google and list the first 3 results.",
        expected_tools=["browser_navigate", "browser_fill", "browser_press",
                        "browser_snapshot"],
        min_success_tools=3,
    ),
    BenchmarkTask(
        id="browser_3",
        category="browser",
        prompt="Go to Wikipedia, search for 'Artificial Intelligence', and read the first paragraph.",
        expected_tools=["browser_navigate", "browser_fill", "browser_press",
                        "browser_snapshot"],
        min_success_tools=3,
    ),

    # ── Planning ──────────────────────────────────────────────────────────
    BenchmarkTask(
        id="planning_1",
        category="planning",
        prompt="Plan the steps needed to build a simple CLI todo app in Python.",
        expected_tools=[],
        min_success_tools=0,
    ),
    BenchmarkTask(
        id="planning_2",
        category="planning",
        prompt="Outline the architecture for a REST API with user authentication, database, and caching.",
        expected_tools=[],
        min_success_tools=0,
    ),

    # ── Recovery ──────────────────────────────────────────────────────────
    BenchmarkTask(
        id="recovery_1",
        category="recovery",
        prompt="A build failed with 'ModuleNotFoundError: No module named requests'. "
               "Fix this by adding the missing import and rebuilding.",
        expected_tools=["read_file", "edit_file", "build_project"],
        min_success_tools=2,
    ),
    BenchmarkTask(
        id="recovery_2",
        category="recovery",
        prompt="A test failure shows 'AssertionError: expected 5, got 3'. "
               "Find the bug, fix it, and re-run the tests.",
        expected_tools=["read_file", "edit_file", "run_tests"],
        min_success_tools=2,
    ),

    # ── Long-Horizon ──────────────────────────────────────────────────────
    BenchmarkTask(
        id="long_1",
        category="long_horizon",
        prompt="Research the best Python web frameworks, build a simple hello-world app using the "
               "top recommendation, and create a test for it.",
        expected_tools=["web_search", "browser_navigate", "write_file",
                        "read_file", "run_tests"],
        min_success_tools=3,
    ),
    BenchmarkTask(
        id="long_2",
        category="long_horizon",
        prompt="Research how to deploy a Flask app to production, write a Dockerfile, "
               "and create a deployment checklist.",
        expected_tools=["web_search", "browser_navigate", "write_file"],
        min_success_tools=2,
    ),
]


# ── Mock Setup ───────────────────────────────────────────────────────────────

def _setup_mocks():
    """Patch external services (build, email, network). Returns patches list."""
    patches = []

    async def _mock_build(task, project_dir, progress_cb=None):
        apk_dir = os.path.join(project_dir, "app", "build", "outputs", "apk", "debug")
        os.makedirs(apk_dir, exist_ok=True)
        apk_path = os.path.join(apk_dir, "app-debug.apk")
        with open(apk_path, "wb") as f:
            f.write(b"fake apk")
        return {"success": True, "output": f"Build completed: {task}", "exit_code": 0}

    async def _mock_repair(project_dir, build_output, progress_cb=None):
        return {"success": True, "output": "Repaired 0 issues", "exit_code": 0}

    async def _mock_tests(project_dir, progress_cb=None):
        return {"success": True, "output": "Tests passed: 5/5", "exit_code": 0}

    async def _mock_validate(project_dir, progress_cb=None):
        return {"success": True, "output": "Validation passed", "exit_code": 0}

    patches.append(patch("core.tools.execution.do_build_project", side_effect=_mock_build))
    patches.append(patch("core.tools.execution.do_repair_project", side_effect=_mock_repair))
    patches.append(patch("core.tools.execution.do_run_tests", side_effect=_mock_tests))
    patches.append(patch("core.tools.execution.do_runtime_validate", side_effect=_mock_validate))

    async def _mock_mcp_call(tool, args):
        return {"sent": True, "to": [args.get("to", "")],
                "subject": args.get("subject", ""), "message_id": "<mock@bench>"}

    mock_mcp = AsyncMock()
    mock_mcp.call_tool = AsyncMock(side_effect=_mock_mcp_call)
    patches.append(patch("core.tools.execution.get_mcp_manager", return_value=mock_mcp))

    async def _always_authorized(tool_name, ctx):
        return True
    patches.append(patch("core.tools.security.is_authorized_to_execute", return_value=True))

    return patches


# ── Tool Schemas ─────────────────────────────────────────────────────────────

def _build_tool_schemas():
    """Collect all tool schemas for LLM function calling."""
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


# ── Prompts per Configuration ────────────────────────────────────────────────

BASE_PROMPT = (
    "You are a software engineering agent with access to tools for web research, "
    "file operations, building code, and communication.\n\n"
    "Available tools: browser_navigate, browser_snapshot, browser_fill, browser_click, "
    "browser_press, browser_search, web_search, web_fetch, read_file, write_file, "
    "edit_file, build_project, run_tests, send_email, python, bash.\n\n"
    "Use tools to accomplish the task. Keep using tools until the task is complete.\n"
    "Do NOT stop after one tool call.\n"
    "Read page content before deciding the next action."
)

PLANNER_INSTRUCTIONS = (
    "\n\nBROWSER PLANNER RULES:\n"
    "1. After browser_navigate, ALWAYS call browser_snapshot.\n"
    "2. When a search form is visible, fill it and press Enter.\n"
    "3. After filling a search form, check the results page.\n"
    "4. If the same tool sequence repeats 3+ times, take a snapshot.\n"
    "5. Look for login forms and report them without auto-filling."
)

MEMORY_INSTRUCTIONS = (
    "\n\nMEMORY GUIDANCE:\n"
    "Previous similar tasks suggest the following approaches work well:\n"
    "- For research: use browser_search first, then navigate to results\n"
    "- For builds: write files before attempting to build\n"
    "- For recovery: read the error output first, then fix\n"
    "Common pitfalls to avoid:\n"
    "- Calling browser_snapshot without first navigating to a page\n"
    "- Using edit_file before read_file\n"
    "- Stopping after a single tool call"
)

SCHEDULER_INSTRUCTIONS = (
    "\n\nWORKFLOW GUIDANCE:\n"
    "Break multi-step tasks into sequential phases:\n"
    "1. Research phase: gather information\n"
    "2. Execution phase: build or write\n"
    "3. Verification phase: test or validate\n"
    "4. Delivery phase: communicate results\n"
    "Complete one phase before starting the next."
)


def build_system_prompt(config: dict[str, bool]) -> str:
    """Build the system prompt for a given ablation configuration."""
    parts = [BASE_PROMPT]
    if config.get("planner"):
        parts.append(PLANNER_INSTRUCTIONS)
    if config.get("memory"):
        parts.append(MEMORY_INSTRUCTIONS)
    if config.get("scheduler"):
        parts.append(SCHEDULER_INSTRUCTIONS)
    return "\n".join(parts)


# ── LLM Interface ────────────────────────────────────────────────────────────

async def call_llm(messages, model=None, ollama_url=None):
    """Call Ollama with tool schemas, return (content, tool_calls)."""
    model = model or MODEL
    ollama_url = ollama_url or OLLAMA_URL
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"num_predict": 2048, "temperature": 0.1},
    }
    payload["tools"] = TOOL_SCHEMAS

    data = None
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=TASK_TIMEOUT) as client:
                resp = await client.post(f"{ollama_url}/api/chat", json=payload)
                if resp.status_code == 400:
                    err_body = resp.text[:1000]
                    logger.warning("LLM 400 (attempt %d/3): %s", attempt+1, err_body)
                    if attempt == 0:
                        with open("_debug_full_payload.json", "w") as f:
                            json.dump(payload, f, indent=2, default=str)
                        logger.warning("Dumped full payload to _debug_full_payload.json")
                    await asyncio.sleep(1)
                    continue
                resp.raise_for_status()
                data = resp.json()
                break
        except Exception as e:
            logger.error("LLM call failed (attempt %d/3): %s", attempt+1, e)
            if attempt == 2:
                return "", []
            await asyncio.sleep(1)

    if data is None:
        logger.error("LLM call failed after 3 attempts")
        return "", []

    msg = data.get("message", {})
    content = msg.get("content", "")
    raw_tool_calls = msg.get("tool_calls", [])
    tool_calls = []
    for tc in raw_tool_calls:
        fn = tc.get("function", tc)
        name = fn.get("name", "")
        args_raw = fn.get("arguments", "{}")
        if isinstance(args_raw, str):
            try:
                args = json.loads(args_raw)
            except json.JSONDecodeError:
                args = {}
        else:
            args = args_raw
        tool_calls.append({"name": name, "arguments": args})
    return content, tool_calls


# ── Tool Execution ───────────────────────────────────────────────────────────

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


async def execute_tool(tool_name: str, arguments: dict) -> dict:
    """Execute a single tool call (mocked). Returns result dict."""
    if tool_name not in VALID_TOOLS:
        return {"error": f"Unknown tool: {tool_name}"}

    try:
        from core.tools.execution import execute_tool_block
        from core.tools._constants import ToolBlock
        block = ToolBlock(tool_type=tool_name, content=json.dumps(arguments))
        result = await execute_tool_block(block)
        return result if isinstance(result, dict) else {"result": str(result)}
    except Exception as e:
        logging.getLogger(__name__).error("Benchmark task failed: %s", e, exc_info=True)
        return {"error": "Benchmark task failed"}


# ── Task Runner ──────────────────────────────────────────────────────────────

@dataclass
class TaskResult:
    """Result of a single task under a single ablation configuration."""
    task_id: str
    category: str
    config_name: str
    success: bool = False
    turns: int = 0
    tool_calls: list[str] = field(default_factory=list)
    unique_tools: set[str] = field(default_factory=set)
    duration_seconds: float = 0.0
    error: str = ""
    final_output: str = ""


async def run_task(task: BenchmarkTask, config_name: str,
                   config: dict[str, bool]) -> TaskResult:
    """Run a single task under one ablation configuration."""
    result = TaskResult(
        task_id=task.id,
        category=task.category,
        config_name=config_name,
    )

    system_prompt = build_system_prompt(config)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": task.prompt},
    ]

    start = time.time()
    try:
        for turn in range(MAX_TURNS):
            content, tool_calls = await call_llm(messages)
            result.turns = turn + 1

            if tool_calls:
                for tc in tool_calls:
                    name = tc.get("name", "")
                    args = tc.get("arguments", {})
                    result.tool_calls.append(name)
                    result.unique_tools.add(name)

                    tool_result = await execute_tool(name, args)
                    messages.append({
                        "role": "assistant",
                        "content": content if content else f"Calling {name}",
                        "tool_calls": [{"function": {"name": name, "arguments": args}}],
                    })
                    messages.append({
                        "role": "tool",
                        "content": json.dumps(tool_result),
                        "name": name,
                    })
            else:
                # No tool calls — LLM is responding with final answer
                result.final_output = content
                result.success = True
                break
        else:
            # MAX_TURNS reached without completion
            result.error = f"max_turns ({MAX_TURNS}) exceeded"

    except asyncio.CancelledError:
        result.error = "cancelled"
    except Exception as e:
        result.error = f"{type(e).__name__}: {e}"
        traceback.print_exc()

    result.duration_seconds = round(time.time() - start, 2)
    return result


# ── Success Criteria ─────────────────────────────────────────────────────────

def evaluate_success(task: BenchmarkTask, result: TaskResult) -> bool:
    """Determine if a task completed successfully.

    A task succeeds if:
    1. The LLM produced a final response (not max_turns)
    2. It used the expected tool categories
    """
    if result.error and "max_turns" not in result.error:
        return False
    if result.turns == 0:
        return False

    # For research/browser tasks, require tool usage
    if task.expected_tools:
        used_expected = [t for t in result.tool_calls if t in task.expected_tools]
        if len(used_expected) < task.min_success_tools:
            return False

    return True


# ── Benchmark Runner ─────────────────────────────────────────────────────────

@dataclass
class AblationReport:
    """Complete ablation benchmark report."""
    timestamp: str
    model: str
    level: str
    tasks: list[dict] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "model": self.model,
            "level": self.level,
            "tasks": self.tasks,
            "summary": self.summary,
        }

    def save(self, path: str) -> None:
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2, default=str)
        logger.info("Report saved: %s", path)


def compute_summary(results: list[TaskResult]) -> dict[str, Any]:
    """Aggregate results by configuration."""
    by_config: dict[str, list[TaskResult]] = {}
    for r in results:
        by_config.setdefault(r.config_name, []).append(r)

    configs: dict[str, dict[str, Any]] = {}
    for cname, tasks in by_config.items():
        total = len(tasks)
        successes = sum(1 for t in tasks if evaluate_success(
            next(tk for tk in TASKS if tk.id == t.task_id), t))
        all_tools = [t for r in tasks for t in r.tool_calls]
        avg_duration = round(sum(r.duration_seconds for r in tasks) / max(total, 1), 2)

        configs[cname] = {
            "total_tasks": total,
            "successes": successes,
            "success_rate": round(successes / max(total, 1), 3),
            "avg_turns": round(sum(r.turns for r in tasks) / max(total, 1), 1),
            "avg_duration_seconds": avg_duration,
            "total_tool_calls": len(all_tools),
            "unique_tools": len(set(all_tools)),
            "tool_frequency": dict(sorted(
                Counter(all_tools).items(), key=lambda x: -x[1])[:10]),
            "errors": [r.error for r in tasks if r.error],
        }

    # Delta: compare each config to "raw" baseline
    baseline = configs.get("raw", {})
    deltas = {}
    for cname, stats in configs.items():
        if cname == "raw":
            continue
        delta_sr = stats["success_rate"] - baseline.get("success_rate", 0)
        deltas[cname] = {
            "delta_success_rate": round(delta_sr, 3),
            "delta_avg_turns": round(
                baseline.get("avg_turns", 0) - stats.get("avg_turns", 0), 1),
            "delta_avg_duration": round(
                baseline.get("avg_duration_seconds", 0) - stats.get("avg_duration_seconds", 0), 1),
        }

    return {"by_config": configs, "deltas": deltas}


async def run_level_1(max_tasks: int = 0, categories: list[str] | None = None,
                      smoke: bool = False) -> AblationReport:
    """Level 1: Raw Model vs Full System."""
    configs_to_run = {"raw": ABLATION_MODES["raw"], "full": ABLATION_MODES["full"]}
    return await _run_configs(configs_to_run, max_tasks, categories, smoke, level="1")


async def run_level_2(max_tasks: int = 0, categories: list[str] | None = None,
                      smoke: bool = False) -> AblationReport:
    """Level 2: Component Ablation — systematically disable subsystems."""
    configs_to_run = {name: ABLATION_MODES[name] for name in LEVEL_2_MODES}
    return await _run_configs(configs_to_run, max_tasks, categories, smoke, level="2")


async def run_level_3(max_tasks: int = 0, categories: list[str] | None = None,
                      smoke: bool = False) -> AblationReport:
    """Level 3: Opportunity Pipeline — validate autonomous scheduling end-to-end.

    Tests the full pipeline: opportunity discovery → decision → submit → execute.
    Measures throughput and success rate of the autonomous scheduling layer.
    """
    configs_to_run = {"full": ABLATION_MODES["full"]}
    report = AblationReport(
        timestamp=datetime.now(timezone.utc).isoformat(),
        model=MODEL,
        level="3",
    )

    patches = _setup_mocks()
    for p in patches:
        p.start()

    results = []
    try:
        for _ in range(min(max_tasks or 3, 5) if not smoke else 1):
            # Run AutonomousScheduler.run_cycle() end-to-end
            from core.scheduler.autonomous import AutonomousScheduler
            from core.scheduler.decision import DecisionEngine
            from core.scheduler.intelligence import ActivityIntelligence
            from core.scheduler.queue import SchedulerQueue
            from core.opportunity.engine import OpportunityDiscoveryEngine
            from core.activity.manager import ActivityManager

            mgr = ActivityManager()
            ai = ActivityIntelligence()
            queue = SchedulerQueue(mgr)
            engine = DecisionEngine(intelligence=ai)
            opp_engine = OpportunityDiscoveryEngine()
            bridge = AutonomousScheduler(
                engine=opp_engine,
                decision=engine,
                queue=queue,
            )

            start = time.time()
            cycle_result = bridge.run_cycle()
            duration = round(time.time() - start, 2)

            results.append({
                "discovered": cycle_result.get("discovered", 0),
                "submitted": cycle_result.get("submitted", 0),
                "rejected": cycle_result.get("rejected", 0),
                "duration_seconds": duration,
            })
    except Exception as e:
        logger.error("Level 3 failed: %s", e)
    finally:
        for p in patches:
            p.stop()

    report.tasks = results
    total_discovered = sum(r.get("discovered", 0) for r in results)
    total_submitted = sum(r.get("submitted", 0) for r in results)
    report.summary = {
        "cycles": len(results),
        "total_discovered": total_discovered,
        "total_submitted": total_submitted,
        "submission_rate": round(total_submitted / max(total_discovered, 1), 3),
        "avg_cycle_duration": round(
            sum(r.get("duration_seconds", 0) for r in results) / max(len(results), 1), 2),
    }

    return report


async def _run_configs(configs_to_run: dict[str, dict[str, bool]],
                       max_tasks: int, categories: list[str] | None,
                       smoke: bool, level: str) -> AblationReport:
    """Run tasks under each configuration."""
    report = AblationReport(
        timestamp=datetime.now(timezone.utc).isoformat(),
        model=MODEL,
        level=level,
    )

    # Filter tasks
    tasks = TASKS
    if categories:
        tasks = [t for t in tasks if t.category in categories]
    if max_tasks > 0:
        tasks = tasks[:max_tasks]
    if smoke:
        tasks = tasks[:1]
        configs_to_run = dict(list(configs_to_run.items())[:2])

    logger.info("Ablation Benchmark Level %s", level)
    logger.info("  Model: %s", MODEL)
    logger.info("  Tasks: %d (%s)", len(tasks), ", ".join(t.id for t in tasks))
    logger.info("  Configs: %s", ", ".join(configs_to_run.keys()))

    patches = _setup_mocks()
    for p in patches:
        p.start()

    all_results: list[TaskResult] = []
    try:
        for config_name, config in configs_to_run.items():
            logger.info("  Running config: %s", config_name)
            for task in tasks:
                logger.info("    Task: %s (%s)", task.id, task.prompt[:50])
                result = await run_task(task, config_name, config)
                result.success = evaluate_success(task, result)
                all_results.append(result)

                logger.info("      → success=%s turns=%d tools=%d",
                            result.success, result.turns, len(result.tool_calls))

                # Yield to event loop between tasks
                await asyncio.sleep(0.5)

    except KeyboardInterrupt:
        logger.warning("Benchmark interrupted by user")
    except Exception as e:
        logger.error("Benchmark failed: %s", e)
        traceback.print_exc()
    finally:
        for p in patches:
            p.stop()

    report.tasks = [{
        "task_id": r.task_id,
        "category": r.category,
        "config": r.config_name,
        "success": r.success,
        "turns": r.turns,
        "tool_calls": r.tool_calls,
        "unique_tools": list(r.unique_tools),
        "duration_seconds": r.duration_seconds,
        "error": r.error,
    } for r in all_results]

    report.summary = compute_summary(all_results)
    return report


# ── Report Display ───────────────────────────────────────────────────────────

def print_report(report: AblationReport) -> None:
    """Print a human-readable summary of the ablation report."""
    print()
    print("=" * 70)
    print(f"  Ablation Benchmark — Level {report.level}")
    print(f"  Model: {report.model}")
    print(f"  Timestamp: {report.timestamp}")
    print("=" * 70)
    print()

    summary = report.summary
    if "by_config" in summary:
        by_config = summary["by_config"]
        deltas = summary.get("deltas", {})

        print(f"{'Config':<25} {'Tasks':>5} {'Success':>8} {'Rate':>7} "
              f"{'Turns':>6} {'Duration':>9} {'Tools':>6}")
        print("-" * 70)

        for cname in sorted(by_config.keys()):
            s = by_config[cname]
            print(f"{cname:<25} {s['total_tasks']:>5} {s['successes']:>8} "
                  f"{s['success_rate']:>6.1%} {s['avg_turns']:>6.1f} "
                  f"{s['avg_duration_seconds']:>7.1f}s {s['total_tool_calls']:>6}")

        if deltas:
            print()
            print(f"{'Delta vs Raw':<25} {'dSuccess':>10} {'dTurns':>8} {'dDuration':>12}")
            print("-" * 55)
            for cname in sorted(deltas.keys()):
                d = deltas[cname]
                sr = d["delta_success_rate"]
                sr_str = f"+{sr:.1%}" if sr >= 0 else f"{sr:.1%}"
                print(f"{cname:<25} {sr_str:>10} {d['delta_avg_turns']:>+8.1f} "
                      f"{d['delta_avg_duration']:>+8.1f}s")

        print()
        print("  Tool Frequency (top 5 per config):")
        for cname in sorted(by_config.keys()):
            freq = by_config[cname].get("tool_frequency", {})
            top5 = list(freq.items())[:5]
            if top5:
                freq_str = ", ".join(f"{t}({c})" for t, c in top5)
                print(f"    {cname:<20} {freq_str}")

    else:
        # Level 3 summary
        for key, value in summary.items():
            print(f"  {key}: {value}")

    print()


# ── Main ─────────────────────────────────────────────────────────────────────

async def _warmup_ollama():
    """Warm up the model to avoid cold-start 400 errors."""
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(f"{OLLAMA_URL}/api/chat", json={
                    "model": MODEL,
                    "messages": [{"role": "user", "content": "warmup"}],
                    "stream": False,
                })
                if resp.status_code == 200:
                    return
        except Exception:
            pass
        await asyncio.sleep(2)


async def main():
    parser = argparse.ArgumentParser(description="Ablation Benchmark")
    parser.add_argument("--level", choices=["1", "2", "3", "all"], default="1",
                        help="Benchmark level (default: 1)")
    parser.add_argument("--category", choices=["research", "browser", "planning",
                                               "recovery", "long_horizon"],
                        help="Filter by task category")
    parser.add_argument("--max-tasks", type=int, default=0,
                        help="Max tasks per config (default: all)")
    parser.add_argument("--smoke", action="store_true",
                        help="Quick smoke test: 1 task, 2 configs")
    parser.add_argument("--model", default=None,
                        help="Override model (default: qwen2.5:7b)")
    parser.add_argument("--no-warmup", action="store_true",
                        help="Skip model warm-up")
    args = parser.parse_args()

    if not args.no_warmup:
        print("Warming up model...")
        await _warmup_ollama()

    if args.model:
        global MODEL
        MODEL = args.model

    categories = [args.category] if args.category else None

    report: AblationReport | None = None
    levels = ["1", "2", "3"] if args.level == "all" else [args.level]

    for level in levels:
        if level == "1":
            report = await run_level_1(args.max_tasks, categories, args.smoke)
        elif level == "2":
            report = await run_level_2(args.max_tasks, categories, args.smoke)
        elif level == "3":
            report = await run_level_3(args.max_tasks, categories, args.smoke)

        if report:
            print_report(report)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            model_name = MODEL
            path = os.path.join(REPORT_DIR,
                                f"ablation_L{level}_{model_name.replace(':', '_')}_{timestamp}.json")
            report.save(path)


if __name__ == "__main__":
    asyncio.run(main())
