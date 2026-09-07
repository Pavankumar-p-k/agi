# ADR-007: Reasoning Engine

**Status:** Accepted  
**Date:** 2026-07-06  
**Phase:** 3a  

## Context

Phase 2 established a canonical pipeline for every request (ADR-006). All
requests flow through 13 ordered stages, with the LLM confined to the
Execution stage.

Phase 2's pipeline is **execution-oriented**: it receives input, classifies
intent, selects a capability, and executes. There is no reasoning layer
between intent classification and execution:

```
Intent → CapabilitySelection → Planner (stub) → Execution
```

This means:
- The planner cannot decompose complex goals because it has no reasoning
  input
- Capability selection works from raw intent, not from a structured plan
- There is no way to determine *how* a request should be processed before
  deciding *who* should process it
- Every request goes straight to execution regardless of complexity

Phase 3 introduces a **Reasoning Engine** that sits between intent
classification and execution, transforming the pipeline from:

```
Intent → Execution
```

to:

```
Intent → Context Retrieval → Reasoner → Planner → Plan Validator →
Capability Selection → Execution
```

## Decision

### 1. New Stage Order

The canonical pipeline gains four new stages and one replacement, resulting
in 17 stages (ADR-006 is amended):

```
Order  Stage                  Classification   Responsibility
─────  ─────────────────────  ───────────────  ───────────────────────────
  1    Receive                Pure             Accept raw input, parse
  2    LoadContext            Pure             Resolve user/session data
  3    Authentication         Pure             Validate identity
  4    RateLimit              Pure             Enforce rate limits
  5    IntentClassification   Pure             Classify request mode
  6    ContextRetrieval       Read-only        Retrieve memory context
  7    Reasoner               Pure             Assess complexity, constraints
  8    Planner                Pure             Decompose into logical steps
  9    PlanValidator          Pure             Validate plan structure
 10    CapabilitySelection    Pure             Bind steps → capability descriptors
 11    Execution              Impure           Execute plan (LLM + tools)
 12    Verification           Pure             Validate output
 13    EpistemicTagging       Pure             Tag confidence/provenance
 14    Memory                 Impure           Persist to memory facade
 15    Metrics                Impure           Emit observability data
 16    Formatter              Pure             Build final response
```

Stages 6–10 are new in Phase 3.

### 2. Stage Purity Classification

Every stage is classified into one of three categories:

| Category    | Deterministic | External I/O | Examples |
|-------------|:---:|:---:|----------|
| **Pure**    | Yes | No  | Reasoner, Planner, CapSel, Verifier, Formatter |
| **Read-only** | No  | Reads  | ContextRetrieval |
| **Impure**  | No  | Writes | Execution, Memory, Metrics |

**Benefits:**
- Pure stages can be cached, replayed, parallelized, unit-tested without
  mocks, and deterministically verified
- Read-only stages are testable with fixture data instead of real backends
- Impure stages are explicitly identified for integration testing

### 3. Stage Contracts

Every stage defines its contract as docstrings with four sections:

| Section | Description |
|---------|-------------|
| Inputs  | Context fields this stage reads |
| Outputs | Context fields this stage writes |
| Owned   | Fields this stage exclusively owns (STAGE_OWNERSHIP) |
| Forbidden | Actions this stage must never perform |

Example (Reasoner):

```
Inputs:        context.classification, context.retrieved_context
Outputs:       context.reasoning_assessment
Owned:         context.reasoning_assessment
Forbidden:     LLM calls, provider selection, memory writes,
               Activity creation, transport I/O
```

### 4. Reasoner Schema

The Reasoner produces an extensible assessment dict:

```python
{
    "complexity": "simple" | "multi_step" | "agentic",
    "requirements": ["research", "browser", ...],   # extensible list
    "constraints": ["real_time", "authoritative"],   # extensible list
    "confidence": 0.92,                              # rule-based score
    "estimated_steps": 3,
    "routing_hints": {"prefer_local": False},
    "metadata": {},
}
```

Future plugins add entries to `requirements[]` and `constraints[]` without
schema changes. The Reasoner is a pure rule engine — no LLM involvement.

### 5. Planner → CapabilitySelection Separation

**Planner** produces logical steps with zero capability knowledge:

```python
# Planner output — logical plan
{
    "goal": context.raw_input,
    "steps": [
        {"intent": "search_web", "objective": "Find latest AI news",
         "constraints": {"freshness": "7d", "sources": "news"}},
        {"intent": "summarize", "objective": "Summarize findings",
         "constraints": {"max_length": 200}},
    ],
}
```

**CapabilitySelection** binds logical steps to capability descriptors:

```python
# CapabilitySelection output — per-step capability bindings
{
    0: [Capability(id="browser", ...), Capability(id="search_api", ...)],
    1: [Capability(id="summarization", ...)],
}
```

Each binding is a `list[Capability]` — the resolver returns all
capabilities that can satisfy an intent, ranked by match score. The
Execution stage chooses which to instantiate.

### 6. Plan Validator

A PlanValidator stage runs **after** Planner and **before**
CapabilitySelection. It enforces:

- Every step has a non-empty `intent`
- Every step has a non-empty `objective`
- `constraints` is a dict (may be empty)
- `estimated_steps` equals `len(steps)` for multi-step plans
- No malformed or null fields

If validation fails, the stage returns `FAIL` with a descriptive error.

### 7. CapabilitySelection as Resolver

CapabilitySelection uses a resolver pattern. Given an intent like
`"search_web"`, it asks:

> Which implementations satisfy this intent?

rather than:

> Which capability matches this input?

This leaves room for:
- Local implementation
- Cloud implementation  
- Marketplace plugin
- Enterprise override

all without changing the Planner.

### 8. Decision Objects

Every stage produces an immutable decision record:

```python
@dataclass(frozen=True)
class Decision:
    activity_id: str
    stage: str
    timestamp: float
    inputs: dict
    outputs: dict
    rationale: str
    confidence: float | None = None
```

Decisions are stored in `context.metadata["decisions"]` as a list.
Each decision references its `activity_id` from day one, making it
trivially mappable to the Activity Graph and future Universal Graph.

### 9. Execution Trace from Activity Spans

The pipeline runner creates a root ActivityNode before the first stage.
Each stage execution is a child span. The Execution Runtime creates
sub-spans for every step, tool call, and LLM invocation:

```
Activity (root, context.activity_id)
├── Step "search_web"           (type="subgoal")
│   ├── LLM call "rewrite query"(type="tool_call")
│   └── Tool "browser.execute"  (type="tool_call")
├── Step "summarize"            (type="subgoal")
│   └── LLM call "generate"     (type="tool_call")
```

`context.execution_trace` is derived from
`ActivityManager.get_tree(context.activity_id)` — no parallel tracking.

### 10. Verification Outcomes

Verification uses three outcomes instead of a boolean:

| Outcome   | Meaning | Pipeline Action |
|-----------|---------|-----------------|
| `PASS`    | All checks passed | Continue |
| `WARNING` | Advisory issue | Continue, log warning |
| `FAIL`    | Critical issue | Stop pipeline |

Multiple verifiers run independently; each produces one verdict.

### 11. Memory Store Decisions

The Memory stage produces an explicit store decision:

```python
{
    "action": "store" | "skip",
    "type": "conversation" | "preference" | "project" | "fact" | "episodic",
    "reason": "New conversation turn",
    "confidence": 0.95,
}
```

Semantic extraction (facts, preferences, projects) is deferred to Phase 4.

## Consequences

**Positive:**
- Reasoning layer separates *how* from *who* from *execute*
- All pure stages are independently testable without mocks
- LLM remains confined to Execution Runtime
- Plan validation catches errors before execution
- Capability resolver supports plugins without planner changes
- Decision objects provide full traceability from day one
- Activity spans eliminate parallel execution tracking

**Negative:**
- Four new stages add pipeline overhead (negligible — all pure/read-only)
- ContextRetrieval introduces memory dependency to the pipeline
- Existing tests must be updated for new stage order

## Phase 3 Completion Criteria

- [ ] Every stage has ownership tests
- [ ] No LLM calls outside Execution stage
- [ ] Planner outputs only logical plans (no capability references)
- [ ] CapabilitySelection returns descriptors only (no executors)
- [ ] Activity graph reconstructs execution history
- [ ] Verification framework supports PASS/WARNING/FAIL
- [ ] Memory decisions are explicit (store/skip with type)
- [ ] Streaming works through the canonical pipeline
- [ ] All legacy fallback paths removed
- [ ] 140+ tests passing

## References

- ADR-006: Canonical Pipeline (stage base, ownership, runner)
- `core/pipeline/decision.py` — Decision dataclass
- `core/pipeline/stages/context_retrieval.py`
- `core/pipeline/stages/reasoner.py`
- `core/pipeline/stages/planner.py`
- `core/pipeline/stages/plan_validator.py`
- `core/pipeline/stages/capability_selection.py`
- `core/activity/manager.py` — Activity spans for execution trace
