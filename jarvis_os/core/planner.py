from __future__ import annotations

import json
from typing import Any

from ..contracts import Plan, PlanStep


class PlanningEngine:
    def __init__(self, registry: Any, models: Any, skill_registry: Any | None = None) -> None:
        self.registry = registry
        self.models = models
        self.skill_registry = skill_registry

    def build_plan(self, prompt: str, intent: Any, analysis: dict[str, Any]) -> Plan:
        # LLM-based DAG planner
        tools_list = [tool['name'] for tool in analysis.get('recommended_tools', [])]
        plan_prompt = f"""
Generate a DAG plan for the goal: {prompt}

Available tools: {', '.join(tools_list)}

Output STRICT JSON only:
{{
  "tasks": [
    {{
      "id": "t1",
      "tool": "tool_name",
      "args": {{}},
      "deps": [],
      "success": ""
    }}
  ]
}}
"""
        try:
            response = self.models.generate(plan_prompt, task="planner")
        except RuntimeError as exc:
            import logging
            logging.getLogger(__name__).error(f"Planner failed to generate initial plan: {exc}")
            raise
        
        try:
            # Extract response text from dict, handling both string and dict returns
            if isinstance(response, dict):
                response_text = response.get("response", "")
            else:
                response_text = response
            plan_data = json.loads(response_text.strip())
        except (json.JSONDecodeError, AttributeError):
            # Retry with corrected prompt
            retry_prompt = plan_prompt + "\n\nEnsure the output is valid JSON."
            try:
                response = self.models.generate(retry_prompt, task="planner")
            except RuntimeError as exc:
                import logging
                logging.getLogger(__name__).error(f"Planner failed to generate retry plan: {exc}")
                raise

            try:
                if isinstance(response, dict):
                    response_text = response.get("response", "")
                else:
                    response_text = response
                plan_data = json.loads(response_text.strip())
            except (json.JSONDecodeError, AttributeError):
                # Fallback - last resort if model is being weird but reachable
                plan_data = {"tasks": [{"id": "t1", "tool": "assistant_chat", "args": {"prompt": prompt}, "deps": [], "success": ""}]}

        steps = []
        for task in plan_data.get("tasks", []):
            steps.append(PlanStep(
                tool=task["tool"],
                action=f"Execute {task['tool']}",
                arguments=task.get("args", {}),
                reason=f"Task {task['id']}",
            ))

        return Plan(
            goal=prompt,
            intent=intent.get("type", "auto"),
            strategy="llm_dag",
            steps=steps,
            notes=["LLM-generated DAG plan"],
        )
