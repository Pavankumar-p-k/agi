# ADR-009: Intelligence Platform — Phase 7

**Status:** Draft (Sprint 0)  
**Date:** 2026-07-09  
**Phase:** 7

## Context

Phases 1–6F established a complete runtime platform. Every request flows through
a canonical pipeline (ADR-006, ADR-007) with frozen contracts, single-owner
artifacts, and an architecture audit enforcing ownership boundaries.

The runtime is now robust, secured, tenant-aware, and distributable. What it
lacks is **intelligence** — reasoning over evidence, comparing strategies,
learning from outcomes, and explaining decisions.

Phase 7 exists to add that layer. The key architectural invariant: **one
canonical intelligence path**, just as Phases 1–6 established one canonical
runtime path.

### Existing Assets

During Phases 1–6 a substantial intelligence subsystem was built under
`core/research/`. It includes:

- **Belief-driven reasoning engine** (`reasoning.py`) — `ReasoningEngine`,
  `Belief`, `BeliefRevision`, `EvidenceItem`, `CounterHypothesis`,
  `Conclusion` with confidence tracking and revision history. This is a
  full reasoning loop that operates outside the pipeline today.

- **Knowledge graph** (`knowledge_graph.py`, `graph_store.py`,
  `graph_models.py`) — entity-backed graph with fact nodes, relationship
  edges (SUPPORTS, CONTRADICTS, REFERENCES), BFS traversal, contradiction
  queries, and statistics.

- **Cross-source fact analysis** (`reasoner.py`) — `FactReasoner` detecting
  contradictions, agreements, gaps, and unique claims across sources.

- **Evidence tracking** (`evidence_tracker.py`) — `EvidenceTracker` mapping
  facts to goals and hypotheses with coverage assessment.

- **Research reflection** (`reflection.py`) — `ResearchReflection` with
  post-execution analysis, success ratings, pattern extraction, and
  persistent storage.

- **Synthesis** (`synthesizer.py`) — `FactSynthesizer` generating structured
  research reports with evidence breakdowns and recommendations.

- **Research planner** (`planner.py`) — `ResearchPlanner` with question
  decomposition, iterative refinement, and gap-driven follow-up (single-plan).

Additional intelligence-adjacent modules exist outside `core/research/`:
- `brain/learning_engine.py` — lesson-driven prompt modification
- `memory/decision_memory.py` — action→outcome store with derived rules
- `memory/fact_store.py` — SQLite triple store
- `core/improvement/` — knob-based A/B experimentation (Phase 10, unrelated)
- `core/generalization/` — principle extraction (Phase 14, unrelated)

### Problem

These assets are powerful but fragmented. They exist outside the canonical
pipeline, have no stage adapters, no frozen contracts, no ownership
boundaries, and no architecture audit coverage. They are used by the research
workflow but are invisible to the general request path.

Phase 7 must **promote**, not replace, these assets — wrapping them in
pipeline-stage adapters with the same design discipline as Runtime v1.

## Decision — Sprint 0

Sprint 0 is a consolidation sprint. No new business logic. Its output is this
ADR, establishing the architecture for Sprints 1–10.

---

## Deliverable 1 — Intelligence Inventory

Every intelligence-related module receives one of four dispositions:

### Integrated

These modules become the canonical implementation of their concern.
They are wrapped in pipeline-stage adapters (Deliverable 4) and retain
their existing file path as the upstream source of truth.

| Module | File | Canonical Owner |
|---|---|---|
| ReasoningEngine, Belief, BeliefRevision, EvidenceItem, Conclusion | `core/research/reasoning.py` | ReasoningStage |
| FactReasoner, FactComparison | `core/research/reasoner.py` | ReasoningStage |
| EvidenceTracker, ResearchCoverage | `core/research/evidence_tracker.py` | ReasoningStage |
| KnowledgeGraph | `core/research/knowledge_graph.py` | KnowledgeStage |
| GraphStore, GraphNode, GraphEdge | `core/research/graph_store.py`, `graph_models.py` | KnowledgeStage |
| ResearchReflection, ReflectionResult, LearnedPattern | `core/research/reflection.py` | ReflectionStage |

### Adapted (non-integrated)

These modules are consumed by an adapter but remain at their existing path.
They are not the canonical implementation — they are one of possibly
multiple generators consumed by the owning stage.

| Module | File | Adapter Owner | Reason |
|---|---|---|---|
| ResearchPlanner, ResearchPlan | `core/research/planner.py` | PlannerStage | One strategy generator among many (multi-strategy) |
| FactSynthesizer, ResearchReport | `core/research/synthesizer.py` | ExplainabilityStage | Input to explanation generation |

### Merged

These modules contain logic that must be absorbed into the canonical stage,
after which the original file is removed.

| Module | File | Target |
|---|---|---|
| DecisionMemory | `memory/decision_memory.py` | Merge into LearningStage experience store |
| learning_engine.py | `brain/learning_engine.py` | Merge into LearningStage, then delete |

### Adapter → Replace

The module's functionality is replaced by a canonical stage adapter that
delegates to a different engine.

| Module | File | Replacement |
|---|---|---|
| FactStore (SQLite triples) | `memory/fact_store.py` | Replace with KnowledgeStage → GraphStore adapter |

### Kept Separate

These modules address different concerns and are unaffected by Phase 7.

| Module | File | Reason |
|---|---|---|
| `core/improvement/` | Whole directory | Runtime knob tuning (Phase 10), not intelligence |
| `core/generalization/` | Whole directory | Long-term principle extraction (Phase 14) |
| `core/pipeline/stages/epistemic.py` | `core/pipeline/stages/epistemic.py` | Source-confidence provenance, not intelligence |

### Complete Disposition Map

```
core/research/
    reasoning.py          → Integrate → ReasoningStage
    reasoner.py           → Integrate → ReasoningStage
    evidence_tracker.py   → Integrate → ReasoningStage
    knowledge_graph.py    → Integrate → KnowledgeStage
    graph_store.py        → Integrate → KnowledgeStage
    graph_models.py       → Integrate → KnowledgeStage
    planner.py            → Adapter   → PlannerStage
    synthesizer.py        → Adapter   → ExplainabilityStage
    reflection.py         → Integrate → ReflectionStage
    hypothesis.py         → Inherited by reasoning.py
    linker.py             → Inherited by knowledge_graph.py
    extractor.py          → Inherited by knowledge_graph.py
    extraction_fsm.py     → Inherited by knowledge_graph.py
    retriever.py          → Inherited by knowledge_graph.py
    storage.py            → Inherited by knowledge_graph.py
    gap_detector.py       → Inherited by evidence_tracker.py
    models.py             → Inherited by all above
    benchmark.py          → Test utility (unaffected)
    graph_benchmark.py    → Test utility (unaffected)
    reasoning_benchmark.py → Test utility (unaffected)
    research_benchmark.py → Test utility (unaffected)

brain/
    learning_engine.py    → Merge → LearningStage → then delete

memory/
    decision_memory.py    → Merge → LearningStage
    fact_store.py         → Adapter → KnowledgeStage

core/
    improvement/          → Keep separate
    generalization/       → Keep separate
```

No module is "undecided."

---

## Deliverable 2 — Final Pipeline Layout

The Phase 7 canonical pipeline (stages 1–23):

```
 1  Receive
 2  LoadContext
 3  Authentication
 4  TenantResolution
 5  Authorization
 6  ResourceAccess
 7  RateLimit
 8  Intent
 9  ContextRetrieval
10  Knowledge              ← NEW (Sprint 2)
11  Reasoning              ← REPLACES ReasonerStage (Sprint 1)
12  Planner                ← ENHANCED with multi-strategy (Sprint 3)
13  PlanValidation
14  CapabilitySelection
15  Execution
16  Verification
17  Epistemic              ← UNCHANGED
18  Reflection             ← NEW (Sprint 4)
19  Learning               ← NEW (Sprint 5)
20  Memory
21  Metrics                ← ENHANCED with intelligence fields (Sprint 8)
22  Explainability         ← NEW (Sprint 7)
23  Formatter
```

### Key changes

| Change | Rationale |
|---|---|
| **Knowledge** inserted after ContextRetrieval | Gives reasoning access to entity relationships before forming beliefs |
| **Reasoning** replaces old ReasonerStage | Complexity classifier becomes first phase of new ReasoningStage |
| **Planner** enhanced in-place | Single-plan → multi-strategy with comparison/ranking |
| **Reflection** after Epistemic | Truth provenance available before outcome analysis |
| **Learning** after Reflection | Reflection feeds into learning records |
| **Explainability** as final stage | Wraps the entire decision chain into an explanation before formatter |

---

## Deliverable 3 — Reasoner Transition

The existing `ReasonerStage` (`core/pipeline/stages/reasoner.py`) is a
complexity classifier that sets `context.reasoning_assessment` — downstream
stages (planner, capability_selection) depend on this field.

The new `ReasoningStage` absorbs the classifier as its first sub-step:

```
ReasoningStage.process(context):

  1. ComplexityAssessment          ← existing ReasonerStage logic
  2. EvidenceCollection            ← EvidenceTracker
  3. BeliefConstruction            ← ReasoningEngine
  4. ContradictionDetection        ← FactReasoner
  5. CounterHypothesisGeneration   ← ReasoningEngine
  6. BeliefRevision                ← ReasoningEngine (BeliefRevision)
  7. Produce ReasoningResult       ← new frozen contract
```

`context.reasoning_assessment` is still written at step 1. Downstream stages
are unaffected.

---

## Deliverable 4 — Stage Adapter Pattern

Every integration follows a uniform wrapper pattern. The adapter's
sole responsibilities:

```
class XxxStage(PipelineStage):
    async def process(self, context: PipelineContext) -> StageOutcome:
        # 1. Read inputs from PipelineContext
        # 2. Invoke the engine
        # 3. Write typed artifacts back to PipelineContext
        # 4. Return StageOutcome
        ...
```

The adapter must contain almost zero business logic. All reasoning resides
in the wrapped engine, which remains independently testable.

### Concrete adapters

| Stage | Wraps | Context Fields (Read) | Context Fields (Write) |
|---|---|---|---|
| KnowledgeStage | KnowledgeGraph | context_retrieval results | context.knowledge_graph |
| ReasoningStage | ReasoningEngine, FactReasoner, EvidenceTracker | context.knowledge_graph, context.reasoning_assessment | context.reasoning_result, context.beliefs, context.evidence |
| PlannerStage | ResearchPlanner + new generators | context.reasoning_result | context.plan_candidates, context.plan_ranking, context.selected_plan |
| ReflectionStage | ResearchReflection | context.outcome, context.verdicts | context.reflection_result |
| LearningStage | new LearningEngine | context.reflection_result | context.learning_records |
| ExplainabilityStage | FactSynthesizer + new explanation generator | context (all prior) | context.explanation |

---

## Deliverable 5 — Canonical Artifact Ownership

Every intelligence artifact has exactly one owning stage. Non-owner stages may
read but must not write.

| Artifact | Sole Creator | Frozen |
|---|---|---|
| `KnowledgeGraph` | KnowledgeStage | Yes |
| `Belief` | ReasoningStage | Yes |
| `Evidence` | ReasoningStage | Yes |
| `ReasoningResult` | ReasoningStage | Yes |
| `PlanningStrategy` | PlannerStage | Yes |
| `StrategyComparison` | PlannerStage | Yes |
| `PlanRanking` | PlannerStage | Yes |
| `ReflectionResult` | ReflectionStage | Yes |
| `LearningRecord` | LearningStage | Yes |
| `Explanation` | ExplainabilityStage | Yes |

---

## Deliverable 6 — Parallel Execution Plan

```
Sprint 0 (consolidation — this ADR)
    │
    ├──────────────────┬──────────────────┐
    │                  │                  │
Sprint 1           Sprint 2           Sprint 4
Reasoning          Knowledge           Reflection
(integrate)        (integrate)         (integrate)
    │                  │                  │
    └─────────┬────────┘                  │
              │                           │
         Sprint 3                     Sprint 5
    Multi-Strategy Planner            Learning
    (new build)                       (merge + new)
              │                           │
              └──────────────┬────────────┘
                             │
                        Sprint 6
                  Policy Optimization (new)
                             │
                        Sprint 7
                    Explainability (new)
                             │
                        Sprint 8
                  Intelligence Metrics (new)
                             │
                        Sprint 9
                   Architecture Rules 48-55
                             │
                        Sprint 10
                  Replay & Determinism (new)
```

Sprints 1, 2, and 4 are independent and can run in parallel.

Sprint 3 depends on Sprint 1 (planner consumes ReasoningResult).

Sprint 5 depends on Sprint 4 (learning consumes ReflectionResult).

Sprint 7 depends on Sprints 1+2+3 (explanation consumes reasoning + knowledge
+ planning).

---

## Deliverable 7 — Architecture Rules 48–55

Rules are enforced at `tests/architecture/test_architecture_audit.py`.

| Rule | Description | Enforced |
|---|---|---|
| 48 | Only `ReasoningStage` creates `ReasoningResult` | AST scan — `ReasoningResult(` calls outside `stages/reasoning/` |
| 49 | Only `KnowledgeStage` creates `KnowledgeGraph` | AST scan — `KnowledgeGraph(` calls outside `stages/knowledge/` |
| 50 | Only `PlannerStage` creates `PlanningStrategy`, `StrategyComparison`, `PlanRanking` | AST scan — constructors outside `stages/planner/` |
| 51 | Only `ReflectionStage` creates `ReflectionResult` | AST scan — `ReflectionResult(` calls outside `stages/reflection/` |
| 52 | Only `LearningStage` creates `LearningRecord` | AST scan — `LearningRecord(` calls outside `stages/learning/` |
| 53 | Only `ExplainabilityStage` creates `Explanation` | AST scan — `Explanation(` calls outside `stages/explainability/` |
| 54 | Research engines accessed only through stage adapters | Import check — `core.research` imported only by stage adapter modules |
| 55 | No stage bypasses the canonical intelligence pipeline | Import check — no `core.pipeline.pipeline.process_message` calls from intelligence modules |

---

## Consequences

### Positive

- Zero duplication of the existing `core/research/` intelligence assets.
- Every intelligence artifact has a single canonical owner and stage.
- The adapter pattern keeps engines independently testable.
- Pipeline stages and research engines can evolve at different speeds.
- The existing research workflow continues to work during migration.
- Architecture audit prevents ownership drift.

### Negative

- Sprint 0 produces only documentation — no runnable code.
- Adapter wrapping adds one indirection layer per engine.
- Merging `brain/learning_engine.py` and `memory/decision_memory.py` requires
  careful regression testing.

### Risks

- Sprint 0 scope creep: the inventory disposition table is the gating
  deliverable — once agreed, Sprints 1–10 become well-scoped.
- The `memory/fact_store.py` → `KnowledgeStage` transition could lose
  SQLite-persisted triples if the adapter is lossy. Mitigation: run both in
  parallel during Sprint 2, validate equivalence, then remove the old path.

## Status

This ADR is **Draft** during Sprint 0. It becomes **Accepted** at the end of
Sprint 0, at which point Sprints 1–10 proceed under this architecture and no
further architectural changes are permitted without a new ADR.
