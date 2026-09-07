# ADR-006: Canonical Request Processing Pipeline

**Status:** Accepted  
**Date:** 2026-07-05  
**Phase:** 2a  

## Context

Every user request (chat, voice, agent, plugin, CLI, API, scheduler, browser,
autonomous loop) needs to go through the same processing lifecycle:

```
Receive → Load Context → Auth → Rate Limit → Intent → Capabilities →
Planner → Execution → Verification → Epistemic Tagging → Memory →
Metrics → Formatter → Transport Adapter
```

Before Phase 2 this lifecycle existed implicitly, with logic duplicated
across every transport handler:

- **3+ routes** called LLMs directly (`channels/processor.py`,
  `core/routes/websocket.py`, `network/websocket_server.py`)
- **3 routes** did their own intent classification
- **4+ locations** had ad-hoc provider fallback
- **No single `process_message()`** — every transport had its own entry point

This ADR freezes the canonical pipeline architecture.  Implementation of
individual stages happens in later milestones (2C+).

## Decision

**Every request enters through exactly one `process_message()` call that
runs an ordered pipeline of stages.**  Transports are thin adapters.

### 1. Pipeline Lifecycle

```
Transport (HTTP / WS / Channel / CLI / Voice / …)
    │
    ▼
RequestAdapter (transport → canonical Request)
    │
    ▼
process_message(request)
    │
    ▼
┌──────────────────────────────────────────────┐
│  Pipeline (ordered stages)                    │
│                                               │
│  Receive                                      │
│  LoadContext                                  │
│  Authentication                               │
│  RateLimit                                    │
│  IntentClassification                         │
│  CapabilitySelection                          │
│  Planner                                      │
│  Execution (with ProviderManager inside)       │
│  Verification                                 │
│  EpistemicTagging                             │
│  Memory                                       │
│  Metrics                                      │
│  Formatter                                    │
│                                               │
│  ActivityGraph spans the entire lifecycle     │
└──────────────────────────────────────────────┘
    │
    ▼
ResponseAdapter (canonical Response → transport format)
    │
    ▼
Transport
```

### 2. Stage Interface

Every stage implements:

```
PipelineStage (ABC):
    name: str
    execute(context: PipelineContext) → StageResult
```

`StageResult` supports five outcomes:

| Outcome        | Meaning                                      | Pipeline Action               |
|----------------|----------------------------------------------|-------------------------------|
| `CONTINUE`     | Stage succeeded                              | Execute next stage            |
| `SHORT_CIRCUIT`| Processing complete (e.g. auth denied)       | Skip to response formatting   |
| `RETRY`        | Transient failure                            | Retry (up to N times)         |
| `FAIL`         | Permanent failure                            | Halt, return error            |
| `DEFER`        | Waiting for external input                   | Suspend, resume later         |

### 3. Canonical Context

`PipelineContext` is the single mutable object flowing through the pipeline.
All stages read from and write to it:

```
PipelineContext:
    request_id, transport, user_id, session_id   # routing
    raw_input, parsed_request                     # request
    classification, selected_capabilities, plan   # planning
    execution_state, execution_result              # execution
    verification_result                           # verification
    epistemic_tags                                # epistemic
    memory_refs, activity_id, trace_id             # storage
    formatted_response                            # final output (Formatter)
    metrics, metadata                             # observability
```

**Invariant:** No stage interacts with external systems without going
through the context.

### 4. Frozen Stage Order

```
Order  Stage                  Responsibility
─────  ─────────────────────  ───────────────────────────────────────────
  1    Receive                Accept raw input, parse into structured form
  2    LoadContext            Resolve user, session, transport metadata
  3    Authentication         Validate identity (API keys, tokens, …)
  4    RateLimit              Enforce per-user / per-IP rate limits
  5    IntentClassification   Classify request mode (chat/action/agent/…)
  6    CapabilitySelection    Match intent to registered capabilities
  7    Planner                Decompose goal into an executable plan
  8    Execution              Execute plan (LLM calls, tools, sub-agents)
                              ProviderManager handles model selection +
                              fallback internally (not a separate stage)
  9    Verification           Validate output (safety, quality, schema)
 10    EpistemicTagging       Tag output with confidence / provenance
 11    MemoryUpdate           Store relevant context in memory facade
 12    Metrics                Emit timing, token counts, retries
 13    Formatter              Build final response payload
```

### 5. Stage Invariants

| Stage | May NOT |
|---|---|
| IntentClassification | Call an LLM, access memory, select providers |
| CapabilitySelection | Call LLMs, format responses |
| Planner | Talk to transports, access memory, call LLMs |
| Execution | Write memory directly, format responses |
| ProviderManager (inside Execution) | None — owns all fallback logic |
| Verification | Call LLMs, select providers |
| MemoryUpdate | Fire before Verification passes |
| Formatter | Call LLMs, select providers, execute tools |

### 6. ActivityGraph Wrapping

Activity is **not a stage**.  The pipeline runner itself creates an
Activity node (start) before the first stage and completes it (finish)
after the last stage.  Every individual stage execution is a child span
of that Activity.

This ensures every request — regardless of transport — produces exactly
one Activity node, making the Activity Graph complete by construction.

### 7. No GoalResolution Stage

A dedicated Goal Resolution stage is deferred until a proper Goal Engine
exists (Phase 3).  Until then, intent classification feeds directly into
capability selection, and the Planner works with the raw classification.

### 8. No Separate ProviderSelection Stage

Provider selection is **execution policy**, not business logic.  The
Execution stage owns a `ProviderManager` that handles model selection,
provider routing, and fallback internally.  This avoids the awkward
"Execution → ProviderSelection → Execution" circularity.

### 9. Response is Created Last

The `formatted_response` field on `PipelineContext` is only populated by
the final `Formatter` stage.  No earlier stage writes to the response.
The transport adapter reads `context.formatted_response` and converts it
to the wire format.

## Consequences

**Positive:**
- Single `process_message()` entry point for all requests
- All routes eventually become thin adapters
- Provider fallback is centralized (Execution stage)
- Activity Graph coverage is guaranteed
- Independent testability of every stage

**Negative:**
- Existing routes continue to bypass the pipeline during migration
  (addressed by Phase 2D — Transport Migration)
- Pipeline adds ~13 stages of overhead per request (negligible since
  every stage is synchronous and the bottleneck is LLM execution)
- Stage ordering must be maintained as new capabilities are added

**Migration:** Phase 2B defines `process_message()`.  Phase 2C extracts
stages.  Phase 2D migrates transports one by one.
