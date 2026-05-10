from __future__ import annotations

import json
from typing import Any

from ..contracts import ExecutionReport


class CriticEngine:
    def __init__(self, models: Any) -> None:
        self.models = models

    def evaluate(self, goal: str, plan: Any, execution: ExecutionReport) -> dict[str, Any]:
        # Structured evaluation
        eval_prompt = f"""
Evaluate the execution of goal: {goal}

Plan: {plan.to_dict() if hasattr(plan, 'to_dict') else str(plan)}
Execution results: {[r.to_dict() for r in execution.results]}

Output STRICT JSON only:
{{
  "score": 0.0,
  "failure_type": "",
  "issues": [],
  "fix_strategy": "",
  "replan": true
}}
"""
        response = self.models.generate(eval_prompt, task="critic")
        try:
            # Extract response text from dict, handling both string and dict returns
            if isinstance(response, dict):
                response_text = response.get("response", "")
            else:
                response_text = response
            result = json.loads(response_text.strip())
        except json.JSONDecodeError:
            result = {"score": 0.5, "failure_type": "parse_error", "issues": ["Failed to parse evaluation"], "fix_strategy": "Retry", "replan": True}

        return result