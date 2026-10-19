"""Planner: goals in, typed plan DAGs out — never free-text commands.

The v0 planner is deterministic and registry-bound: a goal normalizes to one
of a fixed set of intents, and every step must reference a registered,
healthy capability, validated against the registry before execution
(plan failure mode 4: hallucinated capability). No LLM is involved yet; the
planner explicitly refuses unknown goals instead of guessing (failure 16).
The planner never edits policy and never holds credentials (invariants 1–2).

Determinism (failure 18): identical goals and parameters produce identical
plan ids, so a resumed run generates the same idempotency keys and cannot
double-execute a side effect.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from mj.core import registry, settings
from mj.core.store import Store, canonical_json


class UnknownGoalError(ValueError):
    def __init__(self, goal: str, question: str):
        super().__init__(f"no plan known for goal {goal!r}")
        self.goal = goal
        self.question = question  # one targeted question, plan section 7.2


class PlanValidationError(ValueError):
    pass


@dataclass(frozen=True)
class Step:
    step_id: str
    name: str
    capability_id: str
    inputs: dict[str, Any] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "name": self.name,
            "capability_id": self.capability_id,
            "inputs": self.inputs,
            "depends_on": self.depends_on,
        }


def plan_id_for(goal: str, steps: list[Step]) -> str:
    blob = canonical_json({"goal": goal, "steps": [s.to_dict() for s in steps]})
    return "p-" + hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]


@dataclass(frozen=True)
class Plan:
    goal: str
    trust_level: str
    steps: list[Step]
    created_at: float = field(default_factory=time.time)
    plan_id: str = ""  # derived; set in __post_init__ below

    def __post_init__(self) -> None:
        if not self.plan_id:
            object.__setattr__(self, "plan_id", plan_id_for(self.goal, self.steps))

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "goal": self.goal,
            "trust_level": self.trust_level,
            "created_at": self.created_at,
            "steps": [s.to_dict() for s in self.steps],
        }

    def step(self, step_id: str) -> Step | None:
        return next((s for s in self.steps if s.step_id == step_id), None)


def topological_order(steps: list[Step]) -> list[Step]:
    """Kahn's algorithm; raises on missing or cyclic dependencies."""
    by_id = {s.step_id: s for s in steps}
    indeg = {sid: 0 for sid in by_id}
    dependents: dict[str, list[str]] = {sid: [] for sid in by_id}
    for s in steps:
        for dep in s.depends_on:
            if dep not in by_id:
                raise PlanValidationError(f"step {s.step_id!r} depends on unknown step {dep!r}")
            indeg[s.step_id] += 1
            dependents[dep].append(s.step_id)
    ready = [sid for sid, d in indeg.items() if d == 0]
    order: list[Step] = []
    while ready:
        sid = ready.pop()
        order.append(by_id[sid])
        for dep in dependents[sid]:
            indeg[dep] -= 1
            if indeg[dep] == 0:
                ready.append(dep)
    if len(order) != len(steps):
        cyclic = sorted(set(by_id) - {s.step_id for s in order})
        raise PlanValidationError(f"plan contains a dependency cycle involving {cyclic}")
    return order


def validate_plan(plan: Plan, store: Store) -> list[Step]:
    """Every step references a registered, healthy capability; deps form a DAG."""
    if not plan.steps:
        raise PlanValidationError("plan has no steps")
    order = topological_order(plan.steps)
    seen: set[str] = set()
    for s in plan.steps:
        if s.step_id in seen:
            raise PlanValidationError(f"duplicate step id {s.step_id!r}")
        seen.add(s.step_id)
        got = registry.get(store, s.capability_id)
        if got is None:
            raise PlanValidationError(
                f"step {s.step_id!r} references unregistered capability {s.capability_id!r} "
                "(the planner may only use registered capabilities)"
            )
        _, status = got
        if status != "healthy":
            raise PlanValidationError(
                f"capability {s.capability_id!r} is {status!r}, not healthy; planner refuses it"
            )
    cap = settings.max_steps()
    if cap > 0 and len(plan.steps) > cap:
        raise PlanValidationError(
            f"plan has {len(plan.steps)} steps, over the cap of {cap} (MJ_MAX_STEPS); "
            "split the goal or raise the cap deliberately"
        )
    return order


def goal_fact_probe(goal: str, params: dict[str, Any]) -> Plan:
    """Awareness goal: refresh facts for the requested scopes."""
    scopes = params.get("probes") or ["disk", "processes", "apps", "tools"]
    return Plan(
        goal=goal,
        trust_level=params["_trust_level"],
        steps=[
            Step(
                step_id="s1",
                name="refresh machine facts",
                capability_id="os.facts",
                inputs={"probes": sorted(scopes)},
            )
        ],
    )


def goal_organize(goal: str, params: dict[str, Any]) -> Plan:
    """Organize files in a directory: list first, then organize by extension."""
    directory = params.get("dir")
    if not directory:
        raise UnknownGoalError(
            goal, "Which directory should be organized? (--dir PATH)"
        )
    steps = [
        Step("s1", "list directory", "files.list", inputs={"path": directory}),
        (
            Step(
                "s2",
                "organize files into category subfolders (real moves, undo recorded)",
                "files.organize",
                inputs={"path": directory},
                depends_on=["s1"],
            )
            if params.get("commit")
            else Step(
                "s2",
                "dry run: propose organization, move nothing",
                "files.organize.plan",
                inputs={"path": directory},
                depends_on=["s1"],
            )
        ),
    ]
    return Plan(goal=goal, trust_level=params["_trust_level"], steps=steps)


# intent matchers, evaluated in order; first substring hit wins
INTENTS: list[tuple[str, Callable[[str, dict[str, Any]], Plan]]] = [
    ("organize", goal_organize),
    ("tidy", goal_organize),
    ("disk space", goal_fact_probe),
    ("free space", goal_fact_probe),
    ("storage", goal_fact_probe),
    ("disk", goal_fact_probe),
    ("what is running", goal_fact_probe),
    ("processes", goal_fact_probe),
    ("installed", goal_fact_probe),
    ("apps", goal_fact_probe),
    ("system status", goal_fact_probe),
    ("facts", goal_fact_probe),
]


def build_plan(store: Store, goal: str, params: dict[str, Any] | None = None) -> Plan:
    """Normalize the goal and emit a typed plan. Refuses to guess."""
    params = dict(params or {})
    params.setdefault("_trust_level", "local-terminal")
    lowered = goal.lower().strip()
    for needle, builder in INTENTS:
        if needle not in lowered:
            continue
        plan = builder(goal, params)
        validate_plan(plan, store)
        return plan
    raise UnknownGoalError(
        goal,
        "I can answer questions about disk space, running processes, installed "
        "apps and tool versions, or organize a directory (need --dir PATH). "
        "What exactly do you want?",
    )


def persist_plan(store: Store, plan: Plan, task_id: str) -> None:
    """Store each step with its risk class and idempotency key."""
    for s in plan.steps:
        got = registry.get(store, s.capability_id)
        risk = got[0].risk_class if got else "R4"
        store.conn.execute(
            "INSERT INTO plan_steps (task_id, step_id, name, capability_id, risk_class, "
            "inputs_json, depends_on_json, status) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')",
            (
                task_id,
                s.step_id,
                s.name,
                s.capability_id,
                risk,
                canonical_json(s.inputs),
                canonical_json(s.depends_on),
            ),
        )


def set_step_key(store: Store, task_id: str, step_id: str, key: str) -> None:
    store.conn.execute(
        "UPDATE plan_steps SET idempotency_key = ? WHERE task_id = ? AND step_id = ?",
        (key, task_id, step_id),
    )


def key_for(plan: Plan, step: Step) -> str:
    blob = canonical_json({"plan": plan.plan_id, "step": step.step_id, "inputs": step.inputs})
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
