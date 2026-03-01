# problem_solver/solver.py
#
# PROBLEM SOLVER ENGINE
# ──────────────────────────────────────────────────────────────
# Breaks complex problems into executable steps using LLM reasoning.
# Executes each step and adapts based on results.
#
# Examples:
#  Input:  "I need to prepare for my exam on Monday"
#  Output:
#    Step 1: List all topics that need review → tool: notes
#    Step 2: Create study schedule → tool: brain (llama3)
#    Step 3: Set daily reminder for each topic → tool: reminders
#    Step 4: Check back on Sunday evening → tool: reminder
#
#  Input:  "Organize all my notes from this week"
#  Output:
#    Step 1: Fetch all notes from last 7 days → tool: notes
#    Step 2: Group by topic using AI → tool: brain
#    Step 3: Create tagged summary → tool: notes
#    Step 4: Notify user with summary → tool: speak
#
# Self-Correction:
#  If a step fails → LLM reflects → tries alternative approach

import asyncio
import json
import re
import time
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import httpx


DECOMPOSE_SYSTEM = """You are JARVIS's problem-solving engine.
Break the given problem into 2-6 concrete, executable steps.

Available tools: speak, notes, reminders, brain, media, web, task_list, daily_summary

Return ONLY valid JSON array:
[
  {
    "step_num": 1,
    "description": "what this step does",
    "action": "action_name",
    "tool": "tool_name",
    "params": {"key": "value"},
    "depends_on": []
  }
]

No explanation. Only the JSON array."""


REFLECT_SYSTEM = """You are JARVIS's self-correction engine.
A step in the problem-solving plan failed.
Suggest an alternative approach.

Return ONLY valid JSON:
{
  "analysis": "why it failed",
  "alternative_action": "action_name",
  "alternative_tool": "tool_name",
  "alternative_params": {},
  "should_retry": true
}"""


@dataclass
class SolverResult:
    problem:     str
    steps_total: int
    steps_done:  int
    steps_failed: int
    output:      str
    success:     bool
    duration_s:  float


class ProblemSolver:

    def __init__(self):
        self._ollama_url = "http://localhost:11434"
        self._solve_history: List[dict] = []

    # ─────────────────────────────────────────────────────
    #  DECOMPOSE — break problem into steps
    # ─────────────────────────────────────────────────────

    async def decompose(self, problem: str, context: dict = None) -> List[dict]:
        """
        Use LLM to break a problem into executable steps.
        Returns list of step dicts.
        """
        print(f"[Solver] Decomposing: {problem}")

        ctx_str = ""
        if context:
            ctx_str = f"\nContext: {json.dumps(context)}"

        prompt = f"Break this problem into steps: \"{problem}\"{ctx_str}"

        try:
            raw = await self._llm(DECOMPOSE_SYSTEM, prompt, model="llama3:8b", max_tokens=500)
            m = re.search(r'\[.*?\]', raw, re.DOTALL)
            if m:
                steps = json.loads(m.group())
                print(f"[Solver] Decomposed into {len(steps)} steps")
                return steps
        except Exception as e:
            print(f"[Solver] Decompose error: {e}")

        # Fallback: simple 3-step plan
        return [
            {"step_num":1,"description":"Gather info","action":"search","tool":"brain","params":{"query":problem},"depends_on":[]},
            {"step_num":2,"description":"Process","action":"analyze","tool":"brain","params":{},"depends_on":[1]},
            {"step_num":3,"description":"Report","action":"speak_result","tool":"speak","params":{},"depends_on":[2]},
        ]

    # ─────────────────────────────────────────────────────
    #  SOLVE — full execution loop
    # ─────────────────────────────────────────────────────

    async def solve(self, problem: str, context: dict,
                    tools, memory) -> SolverResult:
        """
        Full problem-solving pipeline:
        1. Decompose into steps
        2. Execute each step in order
        3. Handle failures with self-correction
        4. Return aggregated result
        """
        t_start = time.time()
        print(f"\n[Solver] ══ Solving: '{problem}' ══")

        steps = await self.decompose(problem, context)
        results = {}
        steps_done = 0
        steps_failed = 0
        output_parts = []

        for step in steps:
            step_num = step.get("step_num", steps.index(step) + 1)
            desc = step.get("description","")
            tool_name = step.get("tool","")
            params    = step.get("params",{})

            # Check if dependencies are met
            deps = step.get("depends_on", [])
            if deps and any(results.get(d, {}).get("success") == False for d in deps):
                print(f"[Solver] Step {step_num} skipped — dependency failed")
                continue

            print(f"[Solver] Step {step_num}: {desc}")

            # Execute step
            success = False
            result_data = {}
            for attempt in range(2):   # max 2 attempts per step
                try:
                    result_data = await self._execute_step(step, tools, memory, results)
                    success = result_data.get("success", False)
                    if success: break

                    if attempt == 0:
                        # Self-correct and retry
                        alt = await self._self_correct(step, result_data.get("error",""))
                        if alt and alt.get("should_retry"):
                            step["tool"]   = alt["alternative_tool"]
                            step["params"] = alt["alternative_params"]
                            print(f"[Solver] Retrying step {step_num} with: {alt['alternative_tool']}")

                except Exception as e:
                    result_data = {"success": False, "error": str(e)}

            results[step_num] = {**result_data, "success": success, "step": step}

            if success:
                steps_done += 1
                out = result_data.get("output","")
                if out:
                    output_parts.append(out)
            else:
                steps_failed += 1
                print(f"[Solver] Step {step_num} failed after retries")

        # Build final output
        final_output = self._build_output(problem, output_parts, steps_done, steps_failed)
        duration_s   = round(time.time() - t_start, 2)

        result = SolverResult(
            problem=problem,
            steps_total=len(steps),
            steps_done=steps_done,
            steps_failed=steps_failed,
            output=final_output,
            success=steps_failed == 0,
            duration_s=duration_s,
        )

        await memory.save_solve_result({
            "problem":      problem,
            "steps_total":  len(steps),
            "steps_done":   steps_done,
            "success":      result.success,
            "duration_s":   duration_s,
            "timestamp":    time.time(),
        })

        print(f"[Solver] Done: {steps_done}/{len(steps)} steps ok in {duration_s}s")
        return result

    async def _execute_step(self, step: dict, tools, memory, prev_results: dict) -> dict:
        """Execute one step using appropriate tool."""
        tool_name = step.get("tool","")
        params    = step.get("params",{}).copy()

        # Inject previous results if needed
        for key, val in params.items():
            if isinstance(val, str) and val.startswith("$result_"):
                step_ref = int(val.replace("$result_",""))
                params[key] = prev_results.get(step_ref, {}).get("output","")

        if tool_name == "speak":
            text = params.get("text","")
            if not text and prev_results:
                last = list(prev_results.values())[-1]
                text = last.get("output","")
            await tools.speak(text)
            return {"success": True, "output": text}

        elif tool_name == "brain":
            query = params.get("query", step.get("description",""))
            # Use multi-agent brain for reasoning
            result = await tools.ask_brain(query)
            return {"success": bool(result), "output": result}

        elif tool_name == "notes":
            result = await tools.list_recent_notes()
            return {"success": True, "output": json.dumps(result)}

        elif tool_name == "reminders":
            title = params.get("title","")
            time_str = params.get("time","")
            result = await tools.create_reminder(title, time_str)
            return {"success": result, "output": f"Reminder set: {title}"}

        elif tool_name == "web":
            query = params.get("query","")
            url   = params.get("url","")
            if url:
                await tools.open_url(url)
                return {"success": True, "output": f"Opened: {url}"}
            return {"success": False, "output": "No URL provided"}

        elif tool_name == "task_list":
            tasks = await tools.get_task_list()
            return {"success": True, "output": json.dumps(tasks)}

        elif tool_name == "daily_summary":
            summary = await tools.get_daily_summary()
            return {"success": True, "output": summary}

        else:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}

    async def _self_correct(self, step: dict, error: str) -> dict:
        """Use LLM to figure out a better approach when a step fails."""
        prompt = (
            f"Step '{step.get('description','')}' using tool '{step.get('tool','')}' "
            f"failed with error: '{error}'. Suggest alternative."
        )
        try:
            raw = await self._llm(REFLECT_SYSTEM, prompt, model="phi3:mini", max_tokens=150)
            m = re.search(r'\{.*?\}', raw, re.DOTALL)
            if m:
                return json.loads(m.group())
        except:
            pass
        return {"should_retry": False}

    def _build_output(self, problem: str, parts: list, done: int, failed: int) -> str:
        if not parts:
            return f"Worked on '{problem}': {done} steps completed"
        return " | ".join(p for p in parts if p)[:500]

    async def _llm(self, system: str, prompt: str, model: str = "llama3:8b", max_tokens: int = 300) -> str:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                f"{self._ollama_url}/api/generate",
                json={"model":model,"system":system,"prompt":prompt,
                      "stream":False,"options":{"num_predict":max_tokens,"num_gpu":99,"temperature":0.3}},
            )
            return r.json().get("response","").strip()
