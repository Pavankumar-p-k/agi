# ADR-010: CorePlanner as Single Planner Protocol

**Status:** Proposed  
**Date:** 2026-07-09  
**Phase:** 3  

## Context

The system has three planner systems with incompatible output formats:

- **CorePlanner** (`core/planner/`): reference implementation, 15 files, produces SubGoal trees → StepDefinition lists
- **Brain Planner** (`brain/planner/`): fixed 3-node DAG, produces different plan format, used by UnifiedBrain
- **Pipeline Planner** (Stage 11): inline, keyword-heuristic decomposition, no LLM fallback
- 4 goal stores with different schemas and status enums (GoalManager, PlanStore, brain goals, task store)

No planner supports LLM-based decomposition as a fallback. The pipeline planner's keyword heuristics fail for novel tasks.

## Decision

**`core/planner/` becomes the single `Planner` protocol that all planners implement.**

1. Define a `Planner` ABC/protocol in `core/planner/` with `create_plan(goal: str) → SubGoalTree`.
2. Replace brain planner's internal planner with CorePlanner.
3. Pipeline Stage 11 delegates to CorePlanner.
4. Merge GoalManager + PlanStore into a UnifiedStore with a single `goals_plans` table and unified status enum.
5. Add LLM-based decomposition as a fallback when keyword heuristics produce < 2 sub-goals.
6. `brain/planner/` and `brain/goals/` are deprecated.

## Consequences

**Positive:**
- Single planner interface — pipeline, brain, and specialized planners all speak the same protocol
- LLM fallback handles novel tasks that keyword heuristics miss
- UnifiedStore eliminates 4 incompatible goal schemas
- Plan health and automatic replanning work across all planners

**Negative:**
- Brain planner's 3-node DAG logic must be reimplemented in CorePlanner terms
- GoalManager data migration (brain.db → data/planner.db) requires schema translation
- Pipeline Stage 11 currently produces plans inline — refactoring to delegate to CorePlanner may change stage boundaries
