"""ResearchPlanner — question-driven research planning with iterative refinement.

Takes a user question and produces a structured research plan with goals,
search queries, evidence collection, and gap-driven follow-up.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class GoalStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    ANSWERED = "answered"
    GAP = "gap"
    CONTRADICTED = "contradicted"


class PlanStatus(Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    COMPLETED = "completed"
    STOPPED = "stopped"


@dataclass
class SearchQuery:
    """A search query generated from a research goal."""
    query: str
    engine: str = "web"  # web, browser, academic
    executed: bool = False
    facts_found: int = 0

    def summary(self) -> str:
        return f"[{'x' if self.executed else ' '}] {self.engine}: {self.query} ({self.facts_found} facts)"


@dataclass
class ResearchGoal:
    """A single research sub-goal derived from the main question."""
    goal_id: str
    question: str
    search_queries: list[SearchQuery] = field(default_factory=list)
    status: GoalStatus = GoalStatus.PENDING
    fact_ids: list[str] = field(default_factory=list)
    confidence: float = 0.0
    note: str = ""

    def is_answered(self) -> bool:
        return self.status in (GoalStatus.ANSWERED, GoalStatus.CONTRADICTED)

    def summary(self) -> str:
        return (f"[{self.status.value}] {self.question[:80]} "
                f"({len(self.fact_ids)} facts, conf={self.confidence:.2f})")


@dataclass
class ResearchPlan:
    """Complete research plan with goals, evidence, and status."""
    plan_id: str
    question: str
    goals: list[ResearchGoal] = field(default_factory=list)
    status: PlanStatus = PlanStatus.DRAFT
    iteration: int = 0
    max_iterations: int = 5
    total_facts_collected: int = 0

    def answered_goals(self) -> list[ResearchGoal]:
        return [g for g in self.goals if g.is_answered()]

    def gap_goals(self) -> list[ResearchGoal]:
        return [g for g in self.goals if g.status == GoalStatus.GAP]

    def pending_goals(self) -> list[ResearchGoal]:
        return [g for g in self.goals if g.status == GoalStatus.PENDING]

    def active_goals(self) -> list[ResearchGoal]:
        return [g for g in self.goals if g.status == GoalStatus.IN_PROGRESS]

    def completion_ratio(self) -> float:
        if not self.goals:
            return 0.0
        return len(self.answered_goals()) / len(self.goals)

    def summary(self) -> str:
        return (f"Plan {self.plan_id[:8]} | "
                f"{self.status.value} | "
                f"Iter {self.iteration}/{self.max_iterations} | "
                f"{len(self.answered_goals())}/{len(self.goals)} goals | "
                f"{self.total_facts_collected} facts")


class ResearchPlanner:
    """Generates and manages research plans from user questions.

    Deterministic planning — breaks questions into sub-goals, generates
    search queries, and tracks evidence collection across iterations.

    Usage:
        planner = ResearchPlanner()
        plan = planner.plan("What are the pricing options for Company Product?")
        # ... execute research ...
        plan = planner.refine(plan, collected_facts)
        if plan.status == PlanStatus.COMPLETED:
            report = synthesizer.synthesize(plan.question, collected_facts)
    """

    # Question patterns that indicate multiple sub-topics
    _JOIN_PATTERNS = [
        (re.compile(r'\band\b', re.IGNORECASE), "and"),
        (re.compile(r'\bvs\b', re.IGNORECASE), "vs"),
        (re.compile(r'\bversus\b', re.IGNORECASE), "vs"),
        (re.compile(r'\bcompared to\b', re.IGNORECASE), "vs"),
        (re.compile(r'\bcompare\b', re.IGNORECASE), "compare"),
    ]

    # Common research question prefixes for goal extraction
    _QUESTION_TEMPLATES: dict[str, list[str]] = {
        "pricing": [
            "What is the pricing for {entity}?",
            "How much does {entity} cost?",
            "Is there a free tier for {entity}?",
        ],
        "features": [
            "What features does {entity} offer?",
            "What does {entity} support?",
            "What are the key capabilities of {entity}?",
        ],
        "comparison": [
            "How does {entity} compare to alternatives?",
            "What are the pros and cons of {entity}?",
        ],
        "background": [
            "When was {entity} released?",
            "Who created {entity}?",
            "What is {entity}?",
        ],
        "technical": [
            "What technology does {entity} use?",
            "What are the technical requirements for {entity}?",
        ],
        "news": [
            "What are the latest updates about {entity}?",
            "What was recently announced about {entity}?",
        ],
    }

    def __init__(self):
        self._known_entities: list[str] = []

    def plan(self, question: str, max_iterations: int = 5) -> ResearchPlan:
        """Create a research plan from a question."""
        plan_id = f"plan_{uuid.uuid4().hex[:12]}"
        goals = self._decompose_question(question)

        return ResearchPlan(
            plan_id=plan_id,
            question=question,
            goals=goals,
            status=PlanStatus.ACTIVE,
            max_iterations=max_iterations,
        )

    def refine(self, plan: ResearchPlan,
               collected_facts: list[dict]) -> ResearchPlan:
        """Update plan with collected facts and identify gaps for next iteration."""
        plan.iteration += 1

        # Map facts to goals
        for goal in plan.goals:
            if goal.status in (GoalStatus.ANSWERED, GoalStatus.CONTRADICTED):
                continue

            goal_facts = [f for f in collected_facts
                          if self._fact_matches_goal(f, goal)]
            goal.fact_ids = list(set(
                goal.fact_ids + [f.get("fact_id", "") for f in goal_facts
                                 if f.get("fact_id")]
            ))

            # Evaluate goal status
            new_status, confidence = self._evaluate_goal(goal, goal_facts)
            goal.status = new_status
            goal.confidence = confidence

        plan.total_facts_collected = len(collected_facts)

        # Check termination
        if plan.iteration >= plan.max_iterations:
            plan.status = PlanStatus.STOPPED
            plan.note = f"Reached max iterations ({plan.max_iterations})"
        elif plan.completion_ratio() >= 0.8:
            plan.status = PlanStatus.COMPLETED
            plan.note = "Sufficient evidence collected"
        else:
            plan.status = PlanStatus.ACTIVE
            # Generate follow-up queries for gap goals
            self._generate_follow_up_queries(plan)

        return plan

    def generate_queries(self, plan: ResearchPlan) -> list[SearchQuery]:
        """Get all unexecuted search queries from the plan."""
        queries: list[SearchQuery] = []
        for goal in plan.pending_goals() + plan.active_goals():
            for sq in goal.search_queries:
                if not sq.executed:
                    queries.append(sq)
        return queries

    def get_research_summary(self, plan: ResearchPlan) -> dict[str, Any]:
        """Return a structured summary of the research plan state."""
        return {
            "plan_id": plan.plan_id,
            "question": plan.question,
            "status": plan.status.value,
            "iteration": plan.iteration,
            "max_iterations": plan.max_iterations,
            "total_goals": len(plan.goals),
            "answered_goals": len(plan.answered_goals()),
            "gap_goals": len(plan.gap_goals()),
            "total_facts": plan.total_facts_collected,
            "completion_ratio": round(plan.completion_ratio(), 2),
            "goals": [{
                "id": g.goal_id[:8],
                "question": g.question[:80],
                "status": g.status.value,
                "facts": len(g.fact_ids),
                "confidence": round(g.confidence, 2),
            } for g in plan.goals],
        }

    # ── Internal decomposition ───────────────────────────────────────

    def _decompose_question(self, question: str) -> list[ResearchGoal]:
        """Break a question into research goals."""
        goals: list[ResearchGoal] = []
        seen_questions: set[str] = set()

        # Extract entities from the question
        entities = self._extract_entities_from_text(question)
        self._known_entities = entities

        if not entities:
            # No clear entity — use the question itself as one goal
            goal = self._make_goal(question, [question])
            goals.append(goal)
            return goals

        # Determine question type and build goals
        qtype = self._classify_question(question)
        templates = self._QUESTION_TEMPLATES.get(qtype, self._QUESTION_TEMPLATES["background"])

        for entity in entities:
            for template in templates:
                goal_question = template.format(entity=entity)
                if goal_question not in seen_questions:
                    seen_questions.add(goal_question)
                    queries = self._generate_initial_queries(goal_question, entity)
                    goal = ResearchGoal(
                        goal_id=f"g_{uuid.uuid4().hex[:8]}",
                        question=goal_question,
                        search_queries=queries,
                    )
                    goals.append(goal)

        # If the question is comparative, add comparison goal
        if qtype == "comparison" and len(entities) >= 2:
            comp_question = f"How does {entities[0]} compare to {entities[1]}?"
            if comp_question not in seen_questions:
                seen_questions.add(comp_question)
                queries = [
                    SearchQuery(query=comp_question),
                    SearchQuery(query=f"{entities[0]} vs {entities[1]} comparison"),
                ]
                goals.append(ResearchGoal(
                    goal_id=f"g_{uuid.uuid4().hex[:8]}",
                    question=comp_question,
                    search_queries=queries,
                ))

        return goals

    def _classify_question(self, question: str) -> str:
        """Determine the type of research question."""
        lower = question.lower()
        if any(w in lower for w in ["price", "cost", "pricing", "paid",
                                     "subscription", "tier", "free"]):
            return "pricing"
        if any(w in lower for w in ["vs", "versus", "compare", "better",
                                     "alternative", "difference"]):
            return "comparison"
        if any(w in lower for w in ["feature", "capability", "support",
                                     "does", "can"]):
            return "features"
        if any(w in lower for w in ["technology", "tech", "built with",
                                     "stack", "architecture"]):
            return "technical"
        if any(w in lower for w in ["announced", "new", "latest", "update",
                                     "released"]):
            return "news"
        return "background"

    def _extract_entities_from_text(self, text: str) -> list[str]:
        """Extract key entities from the question text."""
        from core.research.linker import Linker
        # Use the linker's entity extraction via a dummy Fact
        from core.research.models import Fact
        linker = Linker()
        dummy_fact = Fact(
            fact_id="dummy",
            source_url="",
            claim=text,
        )
        return linker.extract_entities(dummy_fact)

    def _generate_initial_queries(self, question: str,
                                   entity: str) -> list[SearchQuery]:
        """Generate initial search queries for a goal."""
        return [
            SearchQuery(query=question),
            SearchQuery(query=entity),
            SearchQuery(query=f"{entity} review analysis"),
        ]

    def _make_goal(self, question: str,
                   queries: list[str]) -> ResearchGoal:
        return ResearchGoal(
            goal_id=f"g_{uuid.uuid4().hex[:8]}",
            question=question,
            search_queries=[SearchQuery(query=q) for q in queries],
        )

    def _fact_matches_goal(self, fact: dict, goal: ResearchGoal) -> bool:
        """Check if a fact is relevant to a research goal."""
        claim = (fact.get("claim", "") or "").lower()
        goal_lower = goal.question.lower()

        # Check keyword overlap
        goal_words = set(w for w in re.split(r'\W+', goal_lower) if len(w) > 3)
        claim_words = set(w for w in re.split(r'\W+', claim) if len(w) > 3)

        if not goal_words:
            return True

        overlap = goal_words & claim_words
        return len(overlap) / len(goal_words) > 0.2

    def _evaluate_goal(self, goal: ResearchGoal,
                       facts: list[dict]) -> tuple[GoalStatus, float]:
        """Evaluate whether a goal has sufficient evidence."""
        if not facts:
            return GoalStatus.PENDING, 0.0

        # Average confidence
        confidences = [f.get("confidence", 0.5) for f in facts
                       if isinstance(f.get("confidence"), (int, float))]
        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0

        # Check for contradictions
        from core.research.linker import Linker
        linker = Linker()
        from core.research.models import Fact
        fact_objects = []
        for f in facts[:20]:
            try:
                fact_objects.append(Fact(
                    fact_id=f.get("fact_id", ""),
                    source_url=f.get("source_url", ""),
                    claim=f.get("claim", ""),
                    confidence=f.get("confidence", 0.5),
                    category=f.get("category", "general"),
                ))
            except Exception:
                continue

        contradictions = 0
        for i in range(len(fact_objects)):
            for j in range(i + 1, len(fact_objects)):
                rel = linker.classify_relationship(fact_objects[i], fact_objects[j])
                if rel == "CONTRADICTS":
                    contradictions += 1

        has_contradictions = contradictions > 0

        # Multi-source check
        sources = set(f.get("source_url", "") for f in facts if f.get("source_url"))
        multi_source = len(sources) >= 2

        # Determine status
        if has_contradictions:
            return GoalStatus.CONTRADICTED, max(0.1, avg_conf - 0.3)

        if len(facts) >= 3 and avg_conf >= 0.5 and multi_source:
            return GoalStatus.ANSWERED, min(1.0, avg_conf + 0.15)

        if len(facts) >= 1:
            return GoalStatus.IN_PROGRESS, avg_conf

        return GoalStatus.GAP, 0.0

    def _generate_follow_up_queries(self, plan: ResearchPlan) -> None:
        """Generate follow-up queries for unanswered goals."""
        for goal in plan.gap_goals():
            if len(goal.search_queries) >= 6:
                continue
            # Broader query
            goal.search_queries.append(SearchQuery(
                query=f"more about {goal.question[:60]}",
            ))
            # Source-specific query if entities known
            if self._known_entities:
                goal.search_queries.append(SearchQuery(
                    query=f"{self._known_entities[0]} {goal.question[:50]}",
                ))
