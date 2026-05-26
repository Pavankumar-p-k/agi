"""core/plan_manager.py
Manages plan lifecycle — create, store, approve, execute, track status.
In-memory store (ephemeral). Plans tracked by ID.
"""

import asyncio
import json
import logging
import re
from datetime import datetime
from typing import Optional

from .goal_processor import GoalProcessor
from .agent_executor import AgentExecutor, ExecutionResult
from .llm_router import complete as llm_complete

logger = logging.getLogger("plan_manager")


def _try_parse_json(content: str) -> dict | None:
    """Try to parse JSON, repairing truncation if needed."""
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    match = re.search(r'\{.*\}', content, re.DOTALL)
    if match:
        candidate = match.group()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    # Repair truncated JSON: add missing closing brackets
    for candidate in _repair_json(content):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue

    return None


def _repair_json(s: str) -> list[str]:
    """Generate fixed versions of truncated JSON by adding missing closing brackets."""
    results = []
    match = re.search(r'\{.*', s, re.DOTALL)
    if not match:
        return results
    obj = match.group()
    stack = []
    in_str = False
    escape = False
    for ch in obj:
        if escape:
            escape = False
            continue
        if ch == '\\' and in_str:
            escape = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch in '{[':
            stack.append(ch)
        elif ch == '}':
            if stack and stack[-1] == '{':
                stack.pop()
        elif ch == ']':
            if stack and stack[-1] == '[':
                stack.pop()
    closers = {'{': '}', '[': ']'}
    fixed = obj + ''.join(closers[c] for c in reversed(stack))
    if fixed != obj:
        results.append(fixed)
    # Also try with just the innermost object closed first
    if len(stack) > 1:
        fixed2 = obj
        for c in reversed(stack):
            fixed2 += closers[c]
        results.append(fixed2)
    return results
    obj = match.group()
    depth_braces = 0
    depth_brackets = 0
    in_str = False
    escape = False
    for ch in obj:
        if escape:
            escape = False
            continue
        if ch == '\\' and in_str:
            escape = True
            continue
        if ch == '"' and not escape:
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == '{':
            depth_braces += 1
        elif ch == '}':
            depth_braces -= 1
        elif ch == '[':
            depth_brackets += 1
        elif ch == ']':
            depth_brackets -= 1
    fixed = obj
    fixed += ']' * max(0, depth_brackets)
    fixed += '}' * max(0, depth_braces)
    if fixed != obj:
        results.append(fixed)
    # If arrays are unclosed, try wrapping in array too
    if depth_brackets > 0:
        results.append(fixed + ']' * depth_brackets + '}' * depth_braces)
    return results


def generate_autodream_plan(goal: str) -> dict:
    """
    Takes natural language goal.
    Uses local LLM to generate structured JSON execution plan.
    Returns plan with steps, agents, verification.
    """
    prompt = f"""Goal: {goal}

Return JSON plan ONLY. Format:
{{"goal":"...","steps":[{{"id":1,"description":"...","agent":"AGENT","command":"...","verify":"...","on_failure":"SKIP"}}],"github":{{"create_repo":false,"repo_name":"","visibility":"public"}},"estimated_time":"X min"}}

AGENT must be EXACTLY one word: shell, codex, aider, gemini, opencode, or jarvis. NOT a list.
command must be a real executable command. verify must be a shell test command. max 6 steps.
on_failure choices: retry, skip, abort.

Return ONLY the JSON. No markdown. No explanation."""

    try:
        result = asyncio.run(llm_complete("automation", [{"role": "user", "content": prompt}]))
    except RuntimeError:
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(llm_complete("automation", [{"role": "user", "content": prompt}]))
        loop.close()

    content = result.strip()
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0].strip()
    elif "```" in content:
        content = content.split("```")[1].split("```")[0].strip()

    plan = _try_parse_json(content)
    if plan is None:
        plan = {"goal": goal, "steps": [], "error": f"No JSON found in response: {content[:300]}"}

    if "steps" not in plan:
        plan["steps"] = []
    plan["_autodream"] = True
    plan["created_at"] = datetime.now().isoformat()
    return plan


async def supabase_notify(event: str, data: dict):
    """Push event to Supabase for mobile notifications."""
    if not os.environ.get("SUPABASE_URL") or not os.environ.get("SUPABASE_SERVICE_KEY"):
        return
    try:
        import httpx
        async with httpx.AsyncClient() as http:
            await http.post(
                f"{os.environ['SUPABASE_URL']}/rest/v1/notifications",
                headers={
                    "Authorization": f"Bearer {os.environ['SUPABASE_SERVICE_KEY']}",
                    "Content-Type": "application/json",
                },
                json={
                    "user_id": "default",
                    "type": event,
                    "title": data.get("goal", event),
                    "body": json.dumps(data, default=str)[:500],
                    "data": json.dumps(data, default=str),
                    "created_at": datetime.now().isoformat(),
                },
                timeout=10,
            )
    except Exception:
        pass


class PlanManager:
    def __init__(self):
        self._plans: dict[str, dict] = {}
        self._goal_processor = GoalProcessor()
        self._executor: Optional[AgentExecutor] = None

    async def create_plan(self, goal: str, preferences: Optional[dict] = None) -> dict:
        research = await self._goal_processor.research_goal(goal)
        plan = await self._goal_processor.generate_plan(goal, research, preferences)
        self._plans[plan["id"]] = plan
        return plan

    def get_plan(self, plan_id: str) -> Optional[dict]:
        return self._plans.get(plan_id)

    def approve_plan(self, plan_id: str) -> Optional[dict]:
        plan = self._plans.get(plan_id)
        if plan:
            plan["status"] = "approved"
            plan["approved_at"] = datetime.now().isoformat()
        return plan

    def reject_plan(self, plan_id: str) -> Optional[dict]:
        plan = self._plans.get(plan_id)
        if plan:
            plan["status"] = "rejected"
        return plan

    def update_plan(self, plan_id: str, updates: dict) -> Optional[dict]:
        plan = self._plans.get(plan_id)
        if plan:
            plan.update(updates)
        return plan

    async def execute_plan(self, plan_id: str,
                           progress_callback=None,
                           notify_fn=None,
                           auto_mode: bool = False) -> list[ExecutionResult]:
        plan = self._plans.get(plan_id)
        if not plan:
            raise ValueError(f"Plan {plan_id} not found")

        plan["status"] = "executing"
        plan["started_at"] = datetime.now().isoformat()

        github_result = await self._goal_processor.execute_github_setup(plan)
        plan["github_result"] = github_result

        self._executor = AgentExecutor(progress_callback=progress_callback, auto_mode=auto_mode)
        results = await self._executor.execute_plan(plan, notify_fn)

        plan["status"] = "completed" if all(r.status == "completed" for r in results) else "failed"
        plan["results"] = [r.to_dict() for r in results]
        plan["completed_at"] = datetime.now().isoformat()

        if plan.get("github") in ("new", "existing"):
            push_result = await self._goal_processor.push_to_github(plan)
            plan["push_result"] = push_result

        return results

    def get_status(self, plan_id: str) -> Optional[dict]:
        plan = self._plans.get(plan_id)
        if not plan:
            return None

        base = {
            "id": plan["id"],
            "goal": plan["goal"],
            "status": plan["status"],
            "steps": len(plan.get("steps", [])),
            "created_at": plan.get("created_at"),
        }

        if plan["status"] in ("approved", "executing", "completed", "failed"):
            base["started_at"] = plan.get("started_at")
            base["completed_at"] = plan.get("completed_at")
            base["github"] = plan.get("github")
            base["directory"] = plan.get("directory")

        if self._executor and self._executor._running:
            base["execution"] = self._executor.get_status()

        if "results" in plan:
            base["results"] = plan["results"]
            summary_lines = []
            for r in plan["results"]:
                icon = "✅" if r["status"] == "completed" and r["verified"] else "⚠️" if r["status"] == "completed" else "❌"
                summary_lines.append(f"{icon} Step {r['step_id']} ({r['agent']}): {r['status']}")
            base["summary"] = "\n".join(summary_lines)

        return base

    def list_plans(self) -> list[dict]:
        return [
            {"id": p["id"], "goal": p["goal"], "status": p["status"],
             "created_at": p.get("created_at"), "steps": len(p.get("steps", []))}
            for p in self._plans.values()
        ]
