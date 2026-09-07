# ADR-008: Runtime v1 Freeze

**Status:** Accepted  
**Date:** 2026-07-07  
**Phase:** 5

## Context

Phases 1 through 4 established a complete runtime architecture for JARVIS.
Every request flows through a canonical pipeline (ADR-006, ADR-007) with
well-defined stages, ownership, and typed contracts for each stage's output.

The runtime object model is now complete:

- **Decision** — output of Reasoner / Planner
- **Observation** — raw event during execution
- **Outcome** — structured result of Execution (immutable)
- **Verdict** — output of a single Verifier check
- **StoreDecision** — output of the Memory stage

Phase 5 (autonomy) and later phases (Marketplace, Enterprise, Universal Graph)
will add new capabilities but must not reshape the core runtime.  Freezing the
interfaces prevents architectural drift while legacy subsystems are migrated.

## Decision

The following contracts, ownership rules, and stage ordering are frozen as
**Runtime v1**.  Breaking changes require a new ADR.

### Frozen Contracts

| Contract | File | Notes |
|---|---|---|
| `Pipeline` | `core/pipeline/pipeline.py` | Stage registration, `execute()`, `process_message()` |
| `PipelineContext` | `core/pipeline/context.py` | All fields, `set_stage_field()` ownership enforcement |
| `Observation` | `core/pipeline/observation.py` | Immutable frozen dataclass |
| `Outcome` | `core/pipeline/outcome.py` | Immutable frozen dataclass |
| `Decision` | `core/pipeline/decision.py` | Frozen dataclass |
| `Verdict` | `core/pipeline/stages/verification/__init__.py` | `verifier_name`, `outcome`, `blocking`, `confidence` |
| `StoreDecision` | `core/pipeline/store_decision.py` | `StoreAction` enum, `StoreDecision` dataclass |
| `StageResult` | `core/pipeline/base.py` | `outcome`, `context`, `error`, `metrics` |
| `StageOutcome` | `core/pipeline/base.py` | Enum: CONTINUE, SHORT_CIRCUIT, RETRY, FAIL, DEFER, CANCELLED |
| `HookRegistry` | `core/pipeline/base.py` | `on_before` / `on_after` lifecycle hooks |

### Frozen Ownership

Every context field or runtime artifact has a single owning stage:

| Artifact | Sole Owner | Immutable |
|---|---|---|
| `Observation` | Execution | Yes |
| `Outcome` | Execution | Yes |
| `Decision` | Reasoner / Planner | Yes |
| `StoreDecision` | Memory | No (built once) |
| `Verdict` | Verification | Yes |
| `Activity` (ActivityGraph) | ActivityManager | — |
| `PipelineContext` | Pipeline (coordinator) | No |

Non-owner stages may **read** these artifacts but must not **write** them.
Cross-stage writes produce a runtime warning via `PipelineContext.set_stage_field()`.

### Frozen Stage Order

The canonical pipeline order (ADR-007) is frozen:

```
 1. Receive
 2. LoadContext
 3. Authentication
 4. RateLimit
 5. Intent
 6. ContextRetrieval
 7. Reasoner
 8. Planner
 9. PlanValidator
10. CapabilitySelection
11. Execution
12. Verification
13. Epistemic
14. Memory
15. Metrics
16. Formatter
```

No stage may be removed, reordered, or skipped by default.  The pipeline
may be extended by inserting new stages at the end or between existing
stages via `Pipeline.insert_stage()`.

### Frozen Canonical Lifecycle

The universal runtime lifecycle for both user requests and autonomous tasks:

```
Signal
  │
  ▼
Observation
  │
  ▼
Opportunity
  │
  ▼
Decision
  │
  ▼
Plan
  │
  ▼
Capability Binding
  │
  ▼
Execution
  │
  ▼
Outcome
  │
  ▼
Verification
  │
  ▼
Memory
```

Every artifact in this lifecycle must be traceable to the same root
`Activity` (via `activity_id`).

## Consequences

### Positive

- Teams can build Phase 5+ features against stable interfaces.
- The architecture audit can enforce ownership boundaries.
- Legacy migration can proceed incrementally without runtime churn.
- Adding new verifier categories, capability types, or memory backends
  requires no contract changes.

### Negative

- Bug fixes or performance optimisations that require contract changes
  must go through the ADR process.
- Some legacy subsystems (scheduler executors, agent runtime) will
  temporarily sit outside the frozen contracts until migrated.

### Migration

The `docs/architecture/MIGRATION_BACKLOG.md` catalogues all 43 pre-existing
violations found by the architecture audit.  Each violation has an assigned
phase and owner.  Until migrated, legacy code is exempt from the freeze but
new code must comply.

## Policy

- **Breaking changes** (removing/renaming a field, changing stage order,
  altering ownership) require a new ADR and consensus review.
- **Additive changes** (new fields with defaults, new stage types, new
  verifier categories) are allowed freely without an ADR as long as they
  are backward-compatible.
- **Architecture audit** (`tests/architecture/test_architecture_audit.py`)
  must pass for every PR.  If the audit fails, the change must not merge
  unless it is explicitly part of a migration plan.
