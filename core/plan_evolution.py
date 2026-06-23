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
"""core/plan_evolution.py
Phase 4 (D2): Plan Evolution.
Dynamic DAG mutation mid-run: switch templates, insert/remove steps, change tools.
Now includes FailureAnalysis step: Plan → Generate → Verify → Failure Analysis → Update Plan → Regenerate.
"""
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class FailureAnalysis:
    root_cause: str
    category: str
    affected_requirements: list[str] = field(default_factory=list)
    suggested_mutation: str = ""
    fix_priority: int = 5
    generalized_pattern: str = ""


@dataclass
class PlanMutation:
    mutation_type: str  # "insert", "remove", "replace", "reorder", "switch_template"
    target_task_id: str = ""
    new_task: dict | None = None
    reason: str = ""
    applied_at_retry: int = 0
    analysis: FailureAnalysis | None = None


class PlanEvolutionEngine:
    def __init__(self):
        self.mutations: dict[str, list[PlanMutation]] = {}

    def insert_task(self, project: str, plan: list, after_id: str,
                    task_type: str, description: str, retry: int = 0) -> list:
        """Insert a new task after the given task ID."""
        new_id = f"evo_{len(plan) + 1}"
        new_task = {
            "id": new_id, "type": task_type,
            "description": description,
            "depends_on": [after_id] if after_id else [],
        }
        idx = next((i for i, t in enumerate(plan) if t["id"] == after_id), -1)
        if idx >= 0:
            plan.insert(idx + 1, new_task)
        else:
            plan.append(new_task)
        self.mutations.setdefault(project, []).append(PlanMutation(
            mutation_type="insert", target_task_id=after_id,
            new_task=new_task, reason=f"Insert {task_type}: {description[:40]}",
            applied_at_retry=retry
        ))
        logger.info(f"[PLANEVO] Inserted {new_id} ({task_type}) after {after_id}")
        return plan

    def remove_task(self, project: str, plan: list, task_id: str, retry: int = 0) -> list:
        plan = [t for t in plan if t["id"] != task_id]
        self.mutations.setdefault(project, []).append(PlanMutation(
            mutation_type="remove", target_task_id=task_id,
            reason=f"Remove {task_id}", applied_at_retry=retry
        ))
        logger.info(f"[PLANEVO] Removed {task_id}")
        return plan

    def replace_task(self, project: str, plan: list, task_id: str,
                     new_type: str, new_description: str, retry: int = 0) -> list:
        for t in plan:
            if t["id"] == task_id:
                old_desc = t.get("description", "")[:40]
                t["type"] = new_type
                t["description"] = new_description
                self.mutations.setdefault(project, []).append(PlanMutation(
                    mutation_type="replace", target_task_id=task_id,
                    new_task=t, reason=f"Replace '{old_desc}' with {new_type}",
                    applied_at_retry=retry
                ))
                logger.info(f"[PLANEVO] Replaced {task_id}: {new_type}")
                break
        return plan

    def switch_template(self, project: str, plan: list, new_template: str,
                        retry: int = 0, state=None) -> list:
        if state:
            state.template_name = new_template
            state.save()
        self.mutations.setdefault(project, []).append(PlanMutation(
            mutation_type="switch_template", reason=f"Switch to {new_template}",
            applied_at_retry=retry
        ))
        logger.info(f"[PLANEVO] Switching template to {new_template}")
        if plan:
            plan[0]["description"] = f"Apply template: {new_template}. " + plan[0].get("description", "")
        return plan

    def get_mutations(self, project: str) -> list[PlanMutation]:
        return self.mutations.get(project, [])

    def analyze_failures(self, failures: list[str], plan: list,
                          retry: int, completion_score: float = 0.0) -> list[FailureAnalysis]:
        """Failure Analysis step: categorize failures by root cause, not symptom.
        Returns structured FailureAnalysis list for plan regeneration."""
        analyses = []
        seen_causes = set()

        for f in failures:
            f_lower = f.lower()

            if "missing" in f_lower and "page" in f_lower:
                page_name = f.split(":")[-1].strip() if ":" in f else "unknown"
                cause = f"page_missing:{page_name}"
                if cause not in seen_causes:
                    seen_causes.add(cause)
                    analyses.append(FailureAnalysis(
                        root_cause=f"Required page '{page_name}' was not generated",
                        category="missing_page",
                        suggested_mutation="insert_generation_task",
                        fix_priority=1,
                        generalized_pattern="missing page: *",
                    ))

            elif "broken" in f_lower and "link" in f_lower:
                cause = "broken_links"
                if cause not in seen_causes:
                    seen_causes.add(cause)
                    analyses.append(FailureAnalysis(
                        root_cause="Generated pages reference non-existent files (images, CSS, JS)",
                        category="resource_reference",
                        suggested_mutation="fix_resource_paths",
                        fix_priority=3,
                        generalized_pattern="broken link or reference to *",
                    ))

            elif "placeholder" in f_lower or "lorem" in f_lower or "todo" in f_lower:
                cause = "placeholders"
                if cause not in seen_causes:
                    seen_causes.add(cause)
                    analyses.append(FailureAnalysis(
                        root_cause="Template placeholders or filler text left in generated output",
                        category="incomplete_content",
                        suggested_mutation="replace_placeholders",
                        fix_priority=2,
                        generalized_pattern="placeholder or filler text (*)",
                    ))

            elif "nav" in f_lower and "differ" in f_lower:
                cause = "nav_inconsistency"
                if cause not in seen_causes:
                    seen_causes.add(cause)
                    analyses.append(FailureAnalysis(
                        root_cause="Navigation differs across pages — pages were generated independently",
                        category="structural_inconsistency",
                        suggested_mutation="unify_navigation",
                        fix_priority=4,
                        generalized_pattern="navigation differs on page *",
                    ))

            elif "html" in f_lower and ("valid" in f_lower or "parse" in f_lower or "syntax" in f_lower):
                cause = "html_syntax"
                if cause not in seen_causes:
                    seen_causes.add(cause)
                    analyses.append(FailureAnalysis(
                        root_cause="Generated HTML contains syntax errors",
                        category="syntax_error",
                        suggested_mutation="fix_html_syntax",
                        fix_priority=3,
                        generalized_pattern="HTML syntax error in *",
                    ))

            elif "visual" in f_lower or "score" in f_lower:
                cause = "visual_quality"
                if cause not in seen_causes:
                    seen_causes.add(cause)
                    analyses.append(FailureAnalysis(
                        root_cause="Visual appearance does not meet quality threshold",
                        category="visual_quality",
                        suggested_mutation="improve_visual_design",
                        fix_priority=5,
                        generalized_pattern="visual score below threshold",
                    ))

            elif "reasoning" in f_lower or "content" in f_lower:
                cause = "content_quality"
                if cause not in seen_causes:
                    seen_causes.add(cause)
                    analyses.append(FailureAnalysis(
                        root_cause="Generated content lacks relevance, structure, or completeness",
                        category="content_quality",
                        suggested_mutation="regenerate_content",
                        fix_priority=4,
                        generalized_pattern="content quality below threshold",
                    ))

            else:
                cause = f"uncategorized:{f[:60]}"
                if cause not in seen_causes:
                    seen_causes.add(cause)
                    analyses.append(FailureAnalysis(
                        root_cause=f"Unknown failure: {f[:120]}",
                        category="uncategorized",
                        suggested_mutation="general_repair",
                        fix_priority=6,
                    ))

        if completion_score < 100.0:
            logger.info(f"[ANALYSIS] Requirements at {completion_score:.0f}% — "
                         f"continuing loop to reach 100%")

        logger.info(f"[ANALYSIS] {len(analyses)} root cause(s) identified: "
                     f"{[a.category for a in analyses]}")
        return analyses

    def suggest_fixes(self, project: str, failures: list[str],
                      plan: list, retry: int) -> list[PlanMutation]:
        suggestions = []
        for f in failures:
            f_lower = f.lower()
            if "missing" in f_lower and "page" in f_lower:
                page_name = f.split(":")[-1].strip() if ":" in f else "missing"
                existing_ids = [t["id"] for t in plan]
                new_id = f"evo_fix_{len(existing_ids) + 1}"
                suggestions.append(PlanMutation(
                    mutation_type="insert", reason=f"Add missing page: {page_name}",
                    new_task={"id": new_id, "type": "fix",
                              "description": f"Add missing page: {page_name}",
                              "depends_on": [plan[-1]["id"]] if plan else []}
                ))
        return suggestions


plan_evolution = PlanEvolutionEngine()
