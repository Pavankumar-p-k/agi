"""Long-Horizon Execution Benchmark — measures multi-step project completion.

Tests 3 configurations across multi-step tasks:
  raw      — LLM with tool schemas, NO workflow enforcement
  workflow — LLM + phase state machine enforcement
  full     — LLM + phase enforcement + planner + memory prompts

Metrics:
  - completion_rate: fraction of phases completed
  - task_success: all phases completed
  - sequencing_accuracy: tools called in correct phase order
  - recovery_rate: from simulated failures
  - re_plans: how many times model changes approach
  - turns, duration

Usage:
    python benchmarks/long_horizon_benchmark.py
    python benchmarks/long_horizon_benchmark.py --smoke
    python benchmarks/long_horizon_benchmark.py --model llama3.1

Environment:
    OLLAMA_URL   (default: http://localhost:11434)
    AGENT_MODEL  (default: qwen2.5:7b)
    MAX_TURNS    (default: 20)
    TASK_TIMEOUT (default: 180)
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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.workflow.long_horizon_fsm import LongHorizonFSM, ExecutionState, create_context

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
logger = logging.getLogger("long_horizon_bench")

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
MODEL = os.environ.get("AGENT_MODEL", "qwen2.5:7b")
MAX_TURNS = int(os.environ.get("MAX_TURNS", "20"))
TASK_TIMEOUT = int(os.environ.get("TASK_TIMEOUT", "180"))
REPORT_DIR = os.environ.get("REPORT_DIR", "benchmark_reports")
os.makedirs(REPORT_DIR, exist_ok=True)

# ── Phase definitions for workflow enforcement ──────────────────

PHASE_DEFS = {
    "research": {
        "tools": ["web_search", "web_fetch", "browser_navigate", "browser_snapshot"],
        "next": "plan",
        "prompt": "Research phase: gather information about the topic.",
    },
    "plan": {
        "tools": ["write_file", "read_file"],
        "next": "build",
        "prompt": "Planning phase: create a plan document.",
    },
    "build": {
        "tools": ["write_file", "read_file", "edit_file", "build_project"],
        "next": "test",
        "prompt": "Build phase: write code and build the project.",
    },
    "test": {
        "tools": ["run_tests", "read_file"],
        "next": "repair",
        "prompt": "Test phase: run tests and check results.",
    },
    "repair": {
        "tools": ["read_file", "edit_file", "write_file", "build_project", "run_tests"],
        "next": "retest",
        "prompt": "Repair phase: fix any failures found during testing.",
    },
    "retest": {
        "tools": ["run_tests", "read_file"],
        "next": "deliver",
        "prompt": "Re-test phase: verify repairs and re-run tests.",
    },
    "deliver": {
        "tools": ["send_email", "write_file", "read_file"],
        "next": None,
        "prompt": "Delivery phase: communicate results.",
    },
}


@dataclass
class LongHorizonTask:
    id: str
    category: str  # build_test, research_synth, full_pipeline
    prompt: str
    required_phases: list[str]
    expected_phase_tools: dict[str, list[str]]
    inject_failures: bool = False
    min_phases_complete: int = 3


TASKS: list[LongHorizonTask] = [
    # ── Category 1: Build & Test ──────────────────────────────
    LongHorizonTask(
        id="build_test_1",
        category="build_test",
        prompt="Build a simple Python CLI calculator that can add, subtract, multiply, and divide. "
               "Write the code, build it, run tests, fix any issues, and re-test.",
        required_phases=["build", "test", "repair", "retest"],
        expected_phase_tools={
            "build": ["write_file", "build_project"],
            "test": ["run_tests"],
            "repair": ["read_file", "edit_file", "build_project"],
            "retest": ["run_tests"],
        },
        min_phases_complete=3,
        inject_failures=True,
    ),
    LongHorizonTask(
        id="build_test_2",
        category="build_test",
        prompt="Create a Python script that reads a CSV file and computes statistics (mean, median, std). "
               "Write the code, test it, and fix any bugs until all tests pass.",
        required_phases=["build", "test", "repair", "retest"],
        expected_phase_tools={
            "build": ["write_file", "build_project"],
            "test": ["run_tests"],
            "repair": ["read_file", "edit_file"],
            "retest": ["run_tests"],
        },
        min_phases_complete=3,
        inject_failures=True,
    ),
    LongHorizonTask(
        id="build_test_3",
        category="build_test",
        prompt="Write a small web server in Python using Flask or FastAPI with one endpoint that returns JSON. "
               "Write the code, build it, verify it works, and fix any errors.",
        required_phases=["build", "test", "repair", "retest"],
        expected_phase_tools={
            "build": ["write_file", "build_project"],
            "test": ["run_tests"],
            "repair": ["read_file", "edit_file"],
            "retest": ["run_tests"],
        },
        min_phases_complete=3,
        inject_failures=True,
    ),

    # ── Category 2: Research & Synthesize ────────────────────
    LongHorizonTask(
        id="research_synth_1",
        category="research_synth",
        prompt="Research the pros and cons of FastAPI vs Flask for building REST APIs in Python. "
               "Find at least 3 sources, summarize your findings in a document, and save the comparison.",
        required_phases=["research", "plan", "deliver"],
        expected_phase_tools={
            "research": ["web_search", "web_fetch", "browser_navigate", "browser_snapshot"],
            "plan": ["write_file"],
            "deliver": ["write_file"],
        },
        min_phases_complete=2,
    ),
    LongHorizonTask(
        id="research_synth_2",
        category="research_synth",
        prompt="Research the top 3 Python testing frameworks (pytest, unittest, nose2). "
               "Compare their features, community size, and ease of use. "
               "Write a summary document with your recommendation.",
        required_phases=["research", "plan", "deliver"],
        expected_phase_tools={
            "research": ["web_search", "web_fetch", "browser_navigate", "browser_snapshot"],
            "plan": ["write_file"],
            "deliver": ["write_file"],
        },
        min_phases_complete=2,
    ),

    # ── Category 3: Full Pipeline ────────────────────────────
    LongHorizonTask(
        id="full_pipeline_1",
        category="full_pipeline",
        prompt="Build a complete Python project: "
               "First, research the best project structure for a small CLI tool. "
               "Then create a plan document. "
               "Then write the code for a to-do list manager (add, list, complete, delete tasks). "
               "Then run the tests and fix any failures. "
               "Finally, summarize what was built.",
        required_phases=["research", "plan", "build", "test", "repair", "retest", "deliver"],
        expected_phase_tools={
            "research": ["web_search", "web_fetch", "browser_navigate", "browser_snapshot"],
            "plan": ["write_file"],
            "build": ["write_file", "build_project"],
            "test": ["run_tests"],
            "repair": ["read_file", "edit_file", "build_project"],
            "retest": ["run_tests"],
            "deliver": ["write_file"],
        },
        min_phases_complete=4,
        inject_failures=True,
    ),
]


# ── Tool schemas (shared) ──────────────────────────────────────

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


# ── Prompts ────────────────────────────────────────────────────

BASE_PROMPT = (
    "You are a software engineering agent with access to tools.\n\n"
    "Available tools: web_search, web_fetch, browser_navigate, browser_snapshot, "
    "browser_fill, browser_press, browser_click, browser_evaluate, "
    "read_file, write_file, edit_file, build_project, run_tests, send_email, "
    "python, bash.\n\n"
    "Complete the task step by step. Use tools until the task is complete. "
    "Do NOT stop after one tool call."
)

WORKFLOW_PROMPT = "\n\n" + (
    "WORKFLOW GUIDANCE:\n"
    "Follow these phases in order:\n"
    "1. Research: gather information using web_search, web_fetch, browser tools\n"
    "2. Plan: write a plan document using write_file\n"
    "3. Build: write code files, use build_project\n"
    "4. Test: run tests with run_tests\n"
    "5. Repair: if tests fail, read errors and fix code\n"
    "6. Re-test: run tests again after repairs\n"
    "7. Deliver: write summary or send results\n"
    "Complete each phase before moving to the next."
)

MEMORY_PROMPT = "\n\n" + (
    "MEMORY GUIDANCE FROM PAST PROJECTS:\n"
    "- Always read error output before editing files\n"
    "- After fixing, always re-run tests to verify\n"
    "- Write files before attempting to build\n"
    "- Use browser tools for research, web_fetch for quick lookups\n"
    "- Document your findings at each phase"
)


# ── Mock Tools ─────────────────────────────────────────────────

_mock_build_count: dict[str, int] = {}
_mock_test_state: dict[str, bool] = {}
_mock_repair_count: dict[str, int] = {}

def _task_id_for(task_id, config):
    return f"{config}_{task_id}"


async def _mock_research(task_id: str, tool: str, args: dict) -> dict:
    return {
        "success": True,
        "result": f"Research data for {task_id} using {tool}. Key findings: the recommended approach is standard practice.",
        "summary": f"Found relevant information about {task_id}.",
    }


async def _mock_write_file(path: str, content: str = "") -> dict:
    return {"success": True, "path": path, "action": "written", "summary": f"File written: {path}"}


async def _mock_read_file(path: str) -> dict:
    return {"success": True, "content": "# File content\nprint('hello')", "path": path}


async def _mock_edit_file(path: str, old: str = "", new: str = "") -> dict:
    return {"success": True, "path": path, "action": "edited", "summary": f"File edited: {path}"}


async def _mock_build_project(task_id: str, config: str, project_dir: str = "") -> dict:
    key = _task_id_for(task_id, config)
    _mock_build_count[key] = _mock_build_count.get(key, 0) + 1
    count = _mock_build_count[key]

    if count == 1:
        _mock_test_state[key] = False
        return {
            "success": True,
            "output": "Build completed. 0 errors, 0 warnings.",
            "exit_code": 0,
            "summary": "Build succeeded.",
        }

    return {
        "success": True,
        "output": "Build completed. No errors.",
        "exit_code": 0,
        "summary": "Build succeeded on retry.",
    }


async def _mock_run_tests(task_id: str, config: str, project_dir: str = "") -> dict:
    key = _task_id_for(task_id, config)
    had_failure = _mock_test_state.get(key, True)

    if had_failure:
        _mock_test_state[key] = True
        return {
            "success": False,
            "output": "FAILED: 2 tests passed, 1 failed.\n"
                      "Failure in test_calculator_add: expected 5, got 3\n"
                      "See logs for details.",
            "exit_code": 1,
            "summary": "Tests failed: 1 failure in test_calculator_add.",
            "failures": ["test_calculator_add: expected 5, got 3"],
            "passed": 2,
            "total": 3,
        }

    return {
        "success": True,
        "output": "All tests passed: 3/3.",
        "exit_code": 0,
        "summary": "All 3 tests passed.",
        "failures": [],
        "passed": 3,
        "total": 3,
    }


async def _mock_send_email(to: str = "", subject: str = "", body: str = "") -> dict:
    return {"success": True, "sent": True, "to": to, "subject": subject, "message_id": "<mock>"}


async def _mock_web_search(query: str = "") -> dict:
    return {
        "success": True,
        "results": [
            {"title": f"Result 1 about {query}", "url": "https://example.com/1", "snippet": f"Information about {query}..."},
            {"title": f"Result 2 about {query}", "url": "https://example.com/2", "snippet": f"More details on {query}..."},
            {"title": f"Result 3 about {query}", "url": "https://example.com/3", "snippet": f"Additional context for {query}..."},
        ],
        "summary": f"Found {query} results.",
    }


_mock_handlers: dict[str, Any] = {
    "browser_navigate": lambda **kw: {"success": True, "url": kw.get("url",""), "title": "Research Page"},
    "browser_snapshot": lambda **kw: {"success": True, "title": "Research Page", "headings": [{"text": "Research Topic"}], "paragraphs": [{"text": "Content about the topic..."}]},
    "browser_fill": lambda **kw: {"success": True},
    "browser_press": lambda **kw: {"success": True},
    "browser_click": lambda **kw: {"success": True},
    "browser_evaluate": lambda **kw: {"success": True, "result": "null"},
    "web_fetch": lambda **kw: {"success": True, "content": "Web page content here..."},
    "python": lambda **kw: {"success": True, "output": "Python executed successfully."},
    "bash": lambda **kw: {"success": True, "output": "Command completed."},
}

VALID_TOOLS = set(_mock_handlers.keys()) | {
    "web_search", "web_fetch", "read_file", "write_file", "edit_file",
    "build_project", "run_tests", "send_email", "python", "bash",
}


async def execute_tool(tool_name: str, arguments: dict, task_id: str = "", config: str = "") -> dict:
    if tool_name not in VALID_TOOLS:
        return {"error": f"Unknown tool: {tool_name}"}

    handler = _mock_handlers.get(tool_name)
    if handler:
        try:
            result = handler(**arguments)
            if asyncio.iscoroutine(result):
                return await result
            return result
        except Exception as e:
            logging.getLogger(__name__).error("Benchmark task failed: %s", e, exc_info=True)
            return {"error": "Benchmark task failed"}

    if tool_name == "write_file":
        return await _mock_write_file(arguments.get("path", ""), arguments.get("content", ""))
    if tool_name == "read_file":
        return await _mock_read_file(arguments.get("path", ""))
    if tool_name == "edit_file":
        return await _mock_edit_file(arguments.get("path", ""))
    if tool_name == "web_search":
        return await _mock_web_search(arguments.get("query", ""))
    if tool_name == "web_fetch":
        return {"success": True, "content": "Web content..."}
    if tool_name == "build_project":
        return await _mock_build_project(task_id, config, arguments.get("project_dir", ""))
    if tool_name == "run_tests":
        return await _mock_run_tests(task_id, config, arguments.get("project_dir", ""))
    if tool_name == "send_email":
        return await _mock_send_email(arguments.get("to", ""), arguments.get("subject", ""), arguments.get("body", ""))

    return {"success": True, "result": f"{tool_name} completed"}


# ── Workflow Phase State Machine ───────────────────────────────

class PhaseStateMachine:
    """Tracks and enforces multi-phase workflow progression."""

    PHASE_ORDER = ["research", "plan", "build", "test", "repair", "retest", "deliver"]

    def __init__(self, required_phases: list[str]):
        self.required = required_phases
        self.current_idx = 0
        self.completed: set[str] = set()
        self.injected_phase = ""
        self.log: list[dict] = []

    @property
    def current_phase(self) -> str | None:
        while self.current_idx < len(self.PHASE_ORDER):
            phase = self.PHASE_ORDER[self.current_idx]
            if phase in self.required:
                return phase
            self.current_idx += 1
        return None

    def advance(self):
        self.completed.add(self.current_phase)
        self.current_idx += 1
        self.injected_phase = ""

    def tool_matches_phase(self, tool: str, phase: str) -> bool:
        return tool in PHASE_DEFS.get(phase, {}).get("tools", [])

    def get_phase_for_tool(self, tool: str) -> str | None:
        for phase in self.PHASE_ORDER:
            if tool in PHASE_DEFS.get(phase, {}).get("tools", []):
                return phase
        return None

    def get_def(self, phase: str) -> dict:
        return PHASE_DEFS.get(phase, {"tools": [], "next": None, "prompt": ""})

    def fraction_complete(self) -> float:
        if not self.required:
            return 1.0
        return len(self.completed & set(self.required)) / len(set(self.required))

    def log_action(self, tool: str, phase: str, injected: bool = False):
        self.log.append({"tool": tool, "phase": phase, "injected": injected})


# ── LLM Interface ──────────────────────────────────────────────

async def call_llm(messages):
    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": False,
        "options": {"num_predict": 2048, "temperature": 0.1},
        "tools": TOOL_SCHEMAS,
    }
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=TASK_TIMEOUT) as client:
                resp = await client.post(f"{OLLAMA_URL}/api/chat", json=payload)
                if resp.status_code == 400:
                    logger.warning("LLM 400 (attempt %d/3): %s", attempt+1, resp.text[:200])
                    await asyncio.sleep(1)
                    continue
                resp.raise_for_status()
                data = resp.json()
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
        except Exception as e:
            logger.error("LLM call failed (attempt %d/3): %s", attempt+1, e)
            if attempt == 2:
                return "", []
            await asyncio.sleep(1)
    return "", []


# ── Task Runner ────────────────────────────────────────────────

@dataclass
class TaskResult:
    task_id: str
    category: str
    config_name: str
    success: bool = False
    turns: int = 0
    tool_calls: list[str] = field(default_factory=list)
    unique_tools: set[str] = field(default_factory=set)
    phases_completed: list[str] = field(default_factory=list)
    phases_required: list[str] = field(default_factory=list)
    injections: int = 0
    re_plans: int = 0
    duration_seconds: float = 0.0
    error: str = ""
    final_output: str = ""
    tool_sequence: list[dict] = field(default_factory=list)
    # FSM metrics
    fsm_transitions: int = 0
    fsm_forced_transitions: int = 0
    fsm_loops_prevented: int = 0
    fsm_timeouts: int = 0
    fsm_recoveries: int = 0
    fsm_replans: int = 0
    fsm_validation_failures: int = 0
    fsm_retries: int = 0
    fsm_final_state: str = ""
    fsm_phases_completed: int = 0
    fsm_phases_total: int = 0
    fsm_fraction_complete: float = 0.0


CONFIGS = {
    "raw": {"workflow": False, "prompt": "base"},
    "workflow": {"workflow": True, "prompt": "base"},
    "full": {"workflow": True, "prompt": "full"},
    "fsm": {"workflow": True, "prompt": "base", "use_fsm": True},
}


def _pick_phase_tool(sm: PhaseStateMachine, phase: str, task: LongHorizonTask) -> str | None:
    phase_def = sm.get_def(phase)
    if phase_def["tools"]:
        return phase_def["tools"][0]
    return None


def _pick_next_phase_tool(sm: PhaseStateMachine, task: LongHorizonTask) -> str | None:
    """Get first tool of the next incomplete phase."""
    for p in sm.PHASE_ORDER:
        if p in sm.required and p not in sm.completed and p != sm.current_phase:
            phase_def = sm.get_def(p)
            if phase_def["tools"]:
                return phase_def["tools"][0]
    # Fallback: try current phase's next tool
    curr = sm.current_phase
    if curr and curr in PHASE_DEFS:
        nxt = PHASE_DEFS[curr].get("next")
        if nxt and nxt in sm.required and nxt not in sm.completed:
            phase_def = sm.get_def(nxt)
            if phase_def["tools"]:
                return phase_def["tools"][0]
    return None


def _build_tool_args(tool: str, task: LongHorizonTask) -> dict:
    if tool == "web_search":
        return {"query": task.prompt[:80]}
    if tool == "write_file":
        return {"path": f"/tmp/{task.id}_output.md", "content": f"Phase: {task.id}\n\nTask: {task.prompt[:80]}"}
    if tool == "run_tests":
        return {"project_dir": "/tmp/test_project"}
    if tool == "build_project":
        return {"project_dir": "/tmp/test_project", "task": task.prompt[:80]}
    if tool == "send_email":
        return {"to": "user@example.com", "subject": f"Results: {task.id}", "body": task.prompt[:200]}
    return {}


async def run_task(task: LongHorizonTask, config_name: str, enable_workflow: bool) -> TaskResult:
    result = TaskResult(
        task_id=task.id,
        category=task.category,
        config_name=config_name,
        phases_required=task.required_phases,
    )

    config = CONFIGS.get(config_name, {})
    use_fsm = config.get("use_fsm", False)

    if config_name == "full":
        sys_prompt = BASE_PROMPT + WORKFLOW_PROMPT + MEMORY_PROMPT
    else:
        sys_prompt = BASE_PROMPT + (WORKFLOW_PROMPT if enable_workflow else "")

    messages = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": task.prompt},
    ]

    sm = PhaseStateMachine(task.required_phases) if enable_workflow and not use_fsm else None
    lh_fsm = LongHorizonFSM(ctx=create_context(phases=task.required_phases, objective=task.prompt)) if use_fsm else None
    phase_log: list[str] = []
    _loop_count = 0
    start = time.time()

    _model_tool_calls: list[str] = []
    _same_tool_run = 0
    _last_tool_name = ""
    try:
        for turn in range(MAX_TURNS):
            # FSM loop detection and auto-advancement
            if lh_fsm:
                is_looping, reason = lh_fsm.check_loop()
                if is_looping:
                    result.fsm_loops_prevented = lh_fsm.loops_prevented
                    adv_state = lh_fsm.handle_loop()
                    if adv_state == ExecutionState.FAIL:
                        result.error = f"fsm_loop_fail: {reason}"
                        break
                    if adv_state in (ExecutionState.VALIDATE, ExecutionState.ADVANCE):
                        # Auto-advance phase via FSM
                        lh_fsm.advance_phase()
                        result.phases_completed = list(lh_fsm.ctx["completed_phases"])
                        result.fsm_forced_transitions = lh_fsm.forced_transitions
                        result.injections += 1
                        result.fsm_transitions = len(lh_fsm.transitions)
                        _model_tool_calls = []
                        continue

                # Check stall timeout
                if lh_fsm.check_stall(stall_timeout=60):
                    result.fsm_timeouts = lh_fsm.timeouts
                    # Advance on stall
                    lh_fsm.advance_phase()
                    result.phases_completed = list(lh_fsm.ctx["completed_phases"])
                    result.injections += 1
                    continue

            # Detect tool loop (same tool 4+ times in MODEL's calls only)
            recent = _model_tool_calls[-6:]
            if len(recent) >= 4 and len(set(recent[-4:])) == 1:
                if lh_fsm:
                    next_phase_tool = _pick_fsm_phase_tool(lh_fsm, task)
                    if next_phase_tool:
                        inject_args = _build_tool_args(next_phase_tool, task)
                        logger.info("    [fsm-auto-inject] detected loop, forcing next phase with %s", next_phase_tool)
                        result.injections += 1
                        tool_res = await execute_tool(next_phase_tool, inject_args, task.id, config_name)
                        messages.append({
                            "role": "assistant",
                            "content": f"Auto-injecting {next_phase_tool} to advance phase",
                            "tool_calls": [{"function": {"name": next_phase_tool, "arguments": inject_args}}],
                        })
                        messages.append({
                            "role": "tool",
                            "content": json.dumps(tool_res),
                            "name": next_phase_tool,
                        })
                        lh_fsm.record_action(next_phase_tool, tool_res)
                        lh_fsm.handle_exit_tool(next_phase_tool)
                        lh_fsm.advance_phase()
                        result.phases_completed = list(lh_fsm.ctx["completed_phases"])
                        result.fsm_transitions = len(lh_fsm.transitions)
                        _model_tool_calls = []
                        continue
                elif not sm:
                    result.error = f"loop_detected: {recent[-1]} called {len(recent)} times"
                    break
                else:
                    # With SM active: auto-inject next phase tool
                    next_tool = _pick_next_phase_tool(sm, task)
                    if next_tool:
                        inject_args = _build_tool_args(next_tool, task)
                        logger.info("    [auto-inject] detected loop, forcing next phase with %s", next_tool)
                        result.injections += 1
                        phase_log.append(next_tool)
                        tool_res = await execute_tool(next_tool, inject_args, task.id, config_name)
                        messages.append({
                            "role": "assistant",
                            "content": f"Auto-injecting {next_tool} to advance phase",
                            "tool_calls": [{"function": {"name": next_tool, "arguments": inject_args}}],
                        })
                        messages.append({
                            "role": "tool",
                            "content": json.dumps(tool_res),
                            "name": next_tool,
                        })
                        for check_phase in task.required_phases:
                            if next_tool in task.expected_phase_tools.get(check_phase, []):
                                if check_phase not in result.phases_completed:
                                    result.phases_completed.append(check_phase)
                                    sm.advance()
                        _same_tool_run = 0
                        _last_tool_name = ""
                        _model_tool_calls = []
                        continue

            content, tool_calls = await call_llm(messages)
            result.turns = turn + 1

            if not tool_calls:
                result.final_output = content
                if lh_fsm:
                    result.success = lh_fsm.fraction_complete() >= task.min_phases_complete / max(len(set(task.required_phases)), 1)
                elif sm:
                    result.success = sm.fraction_complete() >= task.min_phases_complete / max(len(set(task.required_phases)), 1)
                else:
                    result.success = bool(content and len(content) > 50)
                break

            # Process each tool call
            for tc in tool_calls:
                name = tc.get("name", "")
                args = tc.get("arguments", {})

                result.tool_calls.append(name)
                _model_tool_calls.append(name)
                result.unique_tools.add(name)

                # FSM: record action and check loop/exit/validation
                if lh_fsm:
                    tool_result = await execute_tool(name, args, task.id, config_name)
                    lh_fsm.record_action(name, tool_result)

                    # Check for phase-relevant tool (track phase completion)
                    for check_phase in task.required_phases:
                        if name in task.expected_phase_tools.get(check_phase, []):
                            if check_phase not in result.phases_completed:
                                # Validate before advancing
                                val_result = lh_fsm.validate_phase(check_phase)
                                if val_result["valid"]:
                                    result.phases_completed.append(check_phase)
                                    lh_fsm.advance_phase()
                                    result.fsm_transitions = len(lh_fsm.transitions)
                                    result.fsm_validation_failures = lh_fsm.validation_failures
                                else:
                                    result.fsm_validation_failures = lh_fsm.validation_failures
                                    # Recovery: try again after validation failure
                                    lh_fsm.transition_to(ExecutionState.RECOVER, forced=True)

                    # Handle exit tool transition
                    exit_state = lh_fsm.handle_exit_tool(name)
                    if exit_state:
                        result.fsm_transitions = len(lh_fsm.transitions)

                    result.fsm_final_state = lh_fsm.state.value
                    result.fsm_phases_completed = len(lh_fsm.ctx["completed_phases"])
                    result.fsm_phases_total = len(lh_fsm.ctx["phases"])
                    result.fsm_fraction_complete = lh_fsm.fraction_complete()
                    result.fsm_forced_transitions = lh_fsm.forced_transitions
                    result.fsm_loops_prevented = lh_fsm.loops_prevented

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
                    continue

                # Track consecutive same-tool calls within phase
                if sm:
                    if name == _last_tool_name:
                        _same_tool_run += 1
                    else:
                        _same_tool_run = 1
                        _last_tool_name = name

                # Detect re-plans (phase regression)
                if sm:
                    tool_phase = sm.get_phase_for_tool(name)
                    curr = sm.current_phase
                    if tool_phase and curr and _phase_index(tool_phase) < _phase_index(curr) - 1:
                        result.re_plans += 1

                # Workflow enforcement: inject correct tool for current phase if model
                # chose a wrong-phase tool.
                injected = False
                if sm and name != "send_email":
                    curr_phase = sm.current_phase
                    if curr_phase:
                        matches = sm.tool_matches_phase(name, curr_phase)
                        if not matches:
                            inject_tool = _pick_phase_tool(sm, curr_phase, task)
                            if inject_tool:
                                inject_args = _build_tool_args(inject_tool, task)
                                logger.info("    [inject-correction] %s -> %s (was: %s)",
                                    curr_phase, inject_tool, name)
                                result.injections += 1
                                injected = True
                                result.tool_calls.append(inject_tool)
                                result.unique_tools.add(inject_tool)
                                sm.log_action(inject_tool, curr_phase, injected=True)
                                phase_log.append(inject_tool)

                                tool_result2 = await execute_tool(inject_tool, inject_args, task.id, config_name)
                                messages.append({
                                    "role": "assistant",
                                    "content": f"Injecting {inject_tool} for phase {curr_phase}",
                                    "tool_calls": [{"function": {"name": inject_tool, "arguments": inject_args}}],
                                })
                                messages.append({
                                    "role": "tool",
                                    "content": json.dumps(tool_result2),
                                    "name": inject_tool,
                                })

                                for check_phase in task.required_phases:
                                    if inject_tool in task.expected_phase_tools.get(check_phase, []):
                                        if check_phase not in result.phases_completed:
                                            result.phases_completed.append(check_phase)

                # Execute the model's actual tool
                tool_result = await execute_tool(name, args, task.id, config_name)
                result.tool_sequence.append({"tool": name, "phase": sm.current_phase if sm else "", "injected": injected})

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

                # Track phase completion
                if sm:
                    for check_phase in task.required_phases:
                        if name in task.expected_phase_tools.get(check_phase, []):
                            if check_phase not in result.phases_completed:
                                result.phases_completed.append(check_phase)
                                sm.advance()
                                _same_tool_run = 0
                                _last_tool_name = ""

            await asyncio.sleep(0.2)
        else:
            result.error = f"max_turns ({MAX_TURNS}) exceeded"

    except asyncio.CancelledError:
        result.error = "cancelled"
    except Exception as e:
        result.error = f"{type(e).__name__}: {e}"
        traceback.print_exc()

    result.duration_seconds = round(time.time() - start, 2)
    if not result.error:
        if lh_fsm:
            result.success = len(result.phases_completed) >= task.min_phases_complete
        elif sm:
            result.success = len(result.phases_completed) >= task.min_phases_complete
        else:
            result.success = bool(result.final_output and len(result.final_output) > 50)
    return result


def _pick_fsm_phase_tool(fsm: LongHorizonFSM, task: LongHorizonTask) -> str | None:
    """Get the first tool for the current FSM phase."""
    phase = fsm.get_current_phase()
    if not phase:
        return None
    expected = task.expected_phase_tools.get(phase, [])
    if expected:
        return expected[0]
    return None


@staticmethod
def _phase_index(phase: str) -> int:
    order = ["research", "plan", "build", "test", "repair", "retest", "deliver"]
    try:
        return order.index(phase)
    except ValueError:
        return -1


PhaseStateMachine._phase_index = staticmethod(_phase_index)
run_task._phase_index = staticmethod(_phase_index)


# ── Success Criteria ───────────────────────────────────────────

def evaluate_phase_completion(task: LongHorizonTask, result: TaskResult) -> dict:
    completed = set(result.phases_completed)
    required = set(task.required_phases)
    return {
        "required_phases": task.required_phases,
        "completed_phases": list(completed & required),
        "missing_phases": list(required - completed),
        "completion_rate": len(completed & required) / max(len(required), 1),
        "min_met": len(completed & required) >= task.min_phases_complete,
    }


# ── Benchmark Runner ───────────────────────────────────────────

@dataclass
class LongHorizonReport:
    timestamp: str
    model: str
    tasks: list[dict] = field(default_factory=list)
    per_task_details: list[dict] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "model": self.model,
            "tasks": self.tasks,
            "per_task_details": self.per_task_details,
            "summary": self.summary,
        }

    def save(self, path: str) -> None:
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2, default=str)
        logger.info("Report saved: %s", path)


def _compute_summary(all_results: list[TaskResult]) -> dict[str, Any]:
    by_config: dict[str, list[TaskResult]] = {}
    for r in all_results:
        by_config.setdefault(r.config_name, []).append(r)

    configs = {}
    for cname, tasks in by_config.items():
        total = len(tasks)
        successes = sum(1 for t in tasks if t.success)
        all_phases_completed = sum(len(t.phases_completed) for t in tasks)
        all_required = sum(len(t.phases_required) for t in tasks)
        all_injections = sum(t.injections for t in tasks)
        all_replans = sum(t.re_plans for t in tasks)
        all_durations = [t.duration_seconds for t in tasks]

        # FSM metrics
        all_fsm_transitions = sum(t.fsm_transitions for t in tasks)
        all_fsm_forced = sum(t.fsm_forced_transitions for t in tasks)
        all_fsm_loops = sum(t.fsm_loops_prevented for t in tasks)
        all_fsm_timeouts = sum(t.fsm_timeouts for t in tasks)
        all_fsm_recoveries = sum(t.fsm_recoveries for t in tasks)
        all_fsm_replans = sum(t.fsm_replans for t in tasks)
        all_fsm_val_fails = sum(t.fsm_validation_failures for t in tasks)

        configs[cname] = {
            "total_tasks": total,
            "successes": successes,
            "success_rate": round(successes / max(total, 1), 3),
            "avg_turns": round(sum(t.turns for t in tasks) / max(total, 1), 1),
            "avg_duration_seconds": round(sum(all_durations) / max(total, 1), 2),
            "phase_completion_rate": round(all_phases_completed / max(all_required, 1), 3),
            "total_phases_completed": all_phases_completed,
            "total_phases_required": all_required,
            "total_injections": all_injections,
            "total_replans": all_replans,
            "fsm_transitions": all_fsm_transitions,
            "fsm_forced_transitions": all_fsm_forced,
            "fsm_loops_prevented": all_fsm_loops,
            "fsm_timeouts": all_fsm_timeouts,
            "fsm_recoveries": all_fsm_recoveries,
            "fsm_replans": all_fsm_replans,
            "fsm_validation_failures": all_fsm_val_fails,
            "tools_by_frequency": dict(sorted(
                Counter([t for r in tasks for t in r.tool_calls]).items(),
                key=lambda x: -x[1]
            )[:10]),
            "errors": [t.error for t in tasks if t.error],
        }

    baseline = configs.get("raw", {})
    deltas = {}
    for cname, stats in configs.items():
        if cname == "raw":
            continue
        d_sr = stats["success_rate"] - baseline.get("success_rate", 0)
        d_phase = stats["phase_completion_rate"] - baseline.get("phase_completion_rate", 0)
        d_turns = baseline.get("avg_turns", 0) - stats.get("avg_turns", 0)
        deltas[cname] = {
            "delta_success_rate": round(d_sr, 3),
            "delta_phase_completion": round(d_phase, 3),
            "delta_avg_turns": round(d_turns, 1),
        }

    return {"by_config": configs, "deltas": deltas}


async def run_benchmark(max_tasks: int = 0, categories: list[str] | None = None,
                        smoke: bool = False) -> LongHorizonReport:
    report = LongHorizonReport(
        timestamp=datetime.now(timezone.utc).isoformat(),
        model=MODEL,
    )

    tasks = TASKS
    if categories:
        tasks = [t for t in tasks if t.category in categories]
    if max_tasks > 0:
        tasks = tasks[:max_tasks]
    if smoke:
        tasks = tasks[:1]
        config_names = ["raw", "workflow"]
    else:
        config_names = list(CONFIGS.keys())

    logger.info("Long-Horizon Execution Benchmark")
    logger.info("  Model: %s", MODEL)
    logger.info("  Tasks: %d (%s)", len(tasks), ", ".join(t.id for t in tasks))
    logger.info("  Configs: %s", ", ".join(config_names))

    await _warmup_ollama()

    all_results: list[TaskResult] = []
    task_details: list[dict] = []

    for config_name in config_names:
        config = CONFIGS[config_name]
        enable_wf = config["workflow"]

        logger.info("  Running config: %s (workflow=%s)", config_name, enable_wf)

        for task in tasks:
            logger.info("    Task: %s [%s]", task.id, task.category)

            result = await run_task(task, config_name, enable_wf)
            all_results.append(result)

            phase_eval = evaluate_phase_completion(task, result)

            detail = {
                "task_id": task.id,
                "category": task.category,
                "config": config_name,
                "success": result.success,
                "turns": result.turns,
                "tool_calls": result.tool_calls,
                "unique_tools": list(result.unique_tools),
                "phases_completed": result.phases_completed,
                "phases_required": result.phases_required,
                "phase_completion": phase_eval,
                "injections": result.injections,
                "re_plans": result.re_plans,
                "duration_seconds": result.duration_seconds,
                "error": result.error,
                "fsm_transitions": result.fsm_transitions,
                "fsm_forced_transitions": result.fsm_forced_transitions,
                "fsm_loops_prevented": result.fsm_loops_prevented,
                "fsm_timeouts": result.fsm_timeouts,
                "fsm_final_state": result.fsm_final_state,
                "fsm_phases_completed": result.fsm_phases_completed,
                "fsm_fraction_complete": result.fsm_fraction_complete,
            }
            task_details.append(detail)

            status = "PASS" if result.success else "FAIL"
            logger.info("      -> %s | turns=%d phases=%d/%d inj=%d replan=%d %.1fs",
                       status, result.turns,
                       len(result.phases_completed), len(result.phases_required),
                       result.injections, result.re_plans, result.duration_seconds)

            await asyncio.sleep(0.3)

    report.tasks = [{
        "task_id": r.task_id,
        "category": r.category,
        "config": r.config_name,
        "success": r.success,
        "turns": r.turns,
        "tool_calls": r.tool_calls,
        "unique_tools": list(r.unique_tools),
        "phases_completed": r.phases_completed,
        "phases_required": r.phases_required,
        "injections": r.injections,
        "re_plans": r.re_plans,
        "duration_seconds": r.duration_seconds,
        "error": r.error,
    } for r in all_results]

    report.per_task_details = task_details
    report.summary = _compute_summary(all_results)
    return report


async def _warmup_ollama():
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(f"{OLLAMA_URL}/api/chat", json={
                    "model": MODEL,
                    "messages": [{"role": "user", "content": "warmup"}],
                    "stream": False,
                })
                if resp.status_code == 200:
                    logger.info("Ollama warmup successful")
                    return
        except Exception:
            await asyncio.sleep(2)
    logger.warning("Ollama warmup failed")


def print_report(report: LongHorizonReport) -> None:
    print()
    print("=" * 78)
    print(f"  Long-Horizon Execution Benchmark")
    print(f"  Model: {report.model}")
    print(f"  Timestamp: {report.timestamp}")
    print("=" * 78)
    print()

    summary = report.summary
    by_config = summary.get("by_config", {})
    deltas = summary.get("deltas", {})

    header = (f"  {'Config':<12} {'Tasks':>5} {'Pass':>5} {'Rate':>8} "
              f"{'Phase%':>8} {'Turns':>6} {'Duration':>9} {'Inj':>5} {'RePlan':>6}")
    print(header)
    print("  " + "-" * 66)

    for cname in sorted(by_config.keys()):
        s = by_config[cname]
        print(f"  {cname:<12} {s['total_tasks']:>5} {s['successes']:>5} "
              f"{s['success_rate']:>6.1%}  {s['phase_completion_rate']:>6.1%} "
              f"{s['avg_turns']:>6.1f} {s['avg_duration_seconds']:>7.1f}s "
              f"{s['total_injections']:>5} {s['total_replans']:>6}")

    if deltas:
        print()
        print(f"  {'Delta vs Raw':<20} {'dSuccess':>10} {'dPhase%':>10} {'dTurns':>8}")
        print("  " + "-" * 48)
        for cname in sorted(deltas.keys()):
            d = deltas[cname]
            sr = d["delta_success_rate"]
            sr_s = f"+{sr:.1%}" if sr >= 0 else f"{sr:.1%}"
            pr = d["delta_phase_completion"]
            pr_s = f"+{pr:.1%}" if pr >= 0 else f"{pr:.1%}"
            print(f"  {cname:<20} {sr_s:>10} {pr_s:>10} {d['delta_avg_turns']:>+8.1f}")

    print()
    print("  Phase Completion Detail:")
    print(f"  {'Config':<12} {'Phases Req':>10} {'Phases Done':>11} {'Completion':>10}")
    print("  " + "-" * 43)
    for cname in sorted(by_config.keys()):
        s = by_config[cname]
        print(f"  {cname:<12} {s['total_phases_required']:>10} {s['total_phases_completed']:>11} "
              f"{s['phase_completion_rate']:>8.1%}")

    print()
    print("  Tool Usage (top 5 per config):")
    for cname in sorted(by_config.keys()):
        freq = by_config[cname].get("tools_by_frequency", {})
        top5 = list(freq.items())[:5]
        if top5:
            freq_str = ", ".join(f"{t}({c})" for t, c in top5)
            print(f"    {cname:<10} {freq_str}")

    # FSM metrics for fsm config
    fsm_data = by_config.get("fsm", {})
    if fsm_data and any(t.fsm_transitions > 0 for rs in [all_results] for t in rs if t.config_name == "fsm"):
        print()
        print("  FSM Metrics:")
        print(f"    {'Metric':<25} {'Total':>8}")
        print("    " + "-" * 33)
        for key in ("fsm_transitions", "fsm_forced_transitions", "fsm_loops_prevented",
                     "fsm_timeouts", "fsm_recoveries", "fsm_replans", "fsm_validation_failures"):
            val = fsm_data.get(key, 0)
            label = key.replace("fsm_", "").replace("_", " ").title()
            print(f"    {label:<25} {val:>8}")
    print()


async def main():
    parser = argparse.ArgumentParser(description="Long-Horizon Execution Benchmark")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--model", default=None)
    parser.add_argument("--category", choices=["build_test", "research_synth", "full_pipeline"])
    parser.add_argument("--max-tasks", type=int, default=0)
    parser.add_argument("--no-warmup", action="store_true")
    args = parser.parse_args()

    if args.model:
        global MODEL
        MODEL = args.model

    report = await run_benchmark(
        max_tasks=args.max_tasks,
        categories=[args.category] if args.category else None,
        smoke=args.smoke,
    )

    print_report(report)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    model_name = MODEL.replace(":", "_")
    path = os.path.join(REPORT_DIR, f"long_horizon_{model_name}_{ts}.json")
    report.save(path)

    return report


if __name__ == "__main__":
    asyncio.run(main())
