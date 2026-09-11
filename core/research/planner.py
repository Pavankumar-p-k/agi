# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from __future__ import annotations

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from core.research.models import ResearchTask, ResearchPlan, ResearchStep, ResearchResult, Source, Claim, Hypothesis
from core.research.evidence_tracker import EvidenceTracker

logger = logging.getLogger("jarvis.research.planner")


class ResearchPlanner:
    """Plans and structures research activities broken down from user goals."""
    
    def __init__(self, evidence_tracker: EvidenceTracker = None):
        self.evidence_tracker = evidence_tracker or EvidenceTracker()
        self.plan_history: List[ResearchPlan] = []
    
    def create_plan(self, task: ResearchTask) -> ResearchPlan:
        """Create a research plan broken down from a research task."""
        plan_id = task.id if task.id else str(uuid4())
        
        # Decompose the query into structured sub-goals
        sub_goals = self._decompose_query(task.query)
        
        plan = ResearchPlan(
            id=plan_id,
            task_id=task.id or "",
            goal=task.query,
            status="pending",
            created_at=datetime.now(),
        )
        
        # Build structured steps from sub-goals
        steps = []
        for i, sub_goal in enumerate(sub_goals):
            step = ResearchStep(
                step_number=i + 1,
                action=self._determine_action(sub_goal),
                description=sub_goal,
                input={"original_query": task.query, "sub_goal": sub_goal},
                status="pending",
            )
            steps.append(step)
        
        plan.steps = steps
        plan.status = "in_progress" if steps else "pending"
        
        self.plan_history.append(plan)
        return plan
    
    def _decompose_query(self, query: str) -> List[str]:
        """Decompose a research query into sub-goals."""
        import re
        
        # Check if query already has structured sub-questions
        sub_questions = []
        
        # Heuristic decomposition based on query type
        query_lower = query.lower().strip()
        
        if "deploy" in query_lower or "install" in query_lower:
            sub_questions = [
                "Identify the project/framework",
                "Find official documentation",
                "Determine dependencies and requirements",
                "Identify deployment targets/options",
                "Find configuration requirements",
                "Identify failure conditions",
            ]
        elif "how to" in query_lower:
            sub_questions = [
                "Understand the core concept",
                "Find step-by-step procedures",
                "Identify prerequisites",
                "Find common pitfalls/solutions",
                "Locate tutorials or guides",
            ]
        elif "compare" in query_lower or "vs" in query_lower:
            sub_questions = [
                "Identify option A characteristics",
                "Identify option B characteristics",
                "Find comparison criteria",
                "Gather benchmark data",
                "Synthesize differences",
            ]
        elif "why" in query_lower:
            sub_questions = [
                "Identify root causes",
                "Find supporting evidence",
                "Review expert opinions",
                "Examine historical context",
                "Synthesize conclusions",
            ]
        else:
            # General decomposition
            sub_questions = [
                "Gather background information",
                "Find primary sources",
                "Identify key stakeholders or components",
                "Review known solutions or approaches",
                "Synthesize findings",
            ]
        
        # Filter to only what's relevant to the actual query
        filtered = self._filter_sub_questions(sub_questions, query)
        
        # Ensure we always have at least one sub-question
        if not filtered:
            filtered = [query]
        
        return filtered
    
    def _filter_sub_questions(self, sub_questions: List[str], query: str) -> List[str]:
        """Filter sub-questions to match the actual query."""
        query_words = set(query.lower().split())
        filtered = []
        
        for sq in sub_questions:
            sq_words = set(sq.lower().split())
            # Keep if there's word overlap with the query
            if query_words and sq_words:
                overlap = len(query_words & sq_words) / max(len(query_words), len(sq_words))
                if overlap > 0.2:  # Minimum 20% overlap
                    filtered.append(sq)
        
        return filtered if filtered else [query]
    
    def _determine_action(self, sub_goal: str) -> str:
        """Determine the primary action for a sub-goal."""
        goal_lower = sub_goal.lower()
        
        if any(kw in goal_lower for kw in ["documentation", "guide", "tutorial"]):
            return "search"
        elif any(kw in goal_lower for kw in ["deploy", "install", "configure"]):
            return "research"
        elif any(kw in goal_lower for kw in ["compare", "vs", "difference"]):
            return "compare"
        elif any(kw in goal_lower for kw in ["why", "cause", "reason"]):
            return "investigate"
        else:
            return "search"
    
    def update_step_status(self, plan_id: str, step_id: str, status: str, 
                           output: Any = None, error: str = "") -> Optional[ResearchStep]:
        """Update a step's status in a plan."""
        # Find the plan
        plan = self._find_plan(plan_id)
        if not plan:
            logger.error(f"Plan {plan_id} not found")
            return None
        
        # Find and update the step
        for step in plan.steps:
            if step.id == step_id:
                step.status = status
                if output is not None:
                    step.output = output
                if error:
                    step.error = error
                    step.status = "failed"
                return step
        
        logger.error(f"Step {step_id} not found in plan {plan_id}")
        return None
    
    def _find_plan(self, plan_id: str) -> Optional[ResearchPlan]:
        """Find a plan by ID."""
        for plan in self.plan_history:
            if plan.id == plan_id:
                return plan
        return None
    
    def get_next_step(self, plan_id: str) -> Optional[ResearchStep]:
        """Get the next pending step from a plan."""
        plan = self._find_plan(plan_id)
        if not plan:
            return None
        
        for step in plan.steps:
            if step.status == "pending":
                return step
        
        # All steps done or failed
        return None
    
    def mark_step_complete(self, plan_id: str, step_id: str, output: Any = None) -> None:
        """Mark a step as complete."""
        step = self.update_step_status(plan_id, step_id, "completed", output=output)
        if step and step.status == "completed":
            # Check if all steps are complete
            all_complete = all(s.status == "completed" for s in plan.steps)
            if all_complete:
                plan = self._find_plan(plan_id)
                if plan:
                    plan.status = "completed"
    
    def mark_step_failed(self, plan_id: str, step_id: str, error: str) -> None:
        """Mark a step as failed."""
        step = self.update_step_status(plan_id, step_id, "failed", error=error)
        if step:
            # Check if we should stop or continue
            plan = self._find_plan(plan_id)
            if plan:
                failed_steps = [s for s in plan.steps if s.status == "failed"]
                # If more than half the steps failed, mark plan as failed
                if len(failed_steps) > len(plan.steps) / 2:
                    plan.status = "failed"


def uuid4():
    import uuid
    return uuid.uuid4()