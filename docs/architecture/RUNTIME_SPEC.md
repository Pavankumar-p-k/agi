# Runtime v1.0 Specification

> Canonical reference for the JARVIS Runtime — independent of implementation.
> Freeze date: 2026-07-07.  Breaking changes require a new ADR.
>
> Version constants: ``core/runtime_version.py`` — ``RuntimeVersion(pipeline, runtime_spec, architecture, snapshot)``
> Current: pipeline=1.0, runtime_spec=1.0, architecture=1.0, snapshot=1.0

---

## 1. Runtime Lifecycle

Every request follows exactly one path through the runtime:

```
Signal
  │
  ▼
process_message(Request) ──► Pipeline.execute(PipelineContext)
                                  │
                          ┌───────┴────────┐
                          │   16 Stages     │
                          │  (ADR-007 order)│
                          └───────┬────────┘
                                  │
                          ┌───────▼────────┐
                          │  Outcome        │
                          │  (immutable)    │
                          └───────┬────────┘
                                  │
                          ┌───────▼────────┐
                          │  Response       │
                          └────────────────┘
```

### 1.1 Entry point

```python
async def process_message(request: Request, services: DeterministicServices | None = None) -> Response:
```

- Every transport adapter calls exactly this function.
- `services` is optional; when omitted the runtime uses real UUIDs and system clock.
- Returns a `Response`; the transport adapter converts to wire format.

### 1.2 Pipeline execution

```python
class Pipeline:
    version: str = "1.0"

    async def execute(self, context: PipelineContext | None = None) -> PipelineContext:
```

- Stages execute sequentially in registered order.
- Any stage may short-circuit (SHORT_CIRCUIT, FAIL, DEFER, CANCELLED).
- After all stages complete, `context.architecture_metrics` is auto-populated.

### 1.3 Cancellation

- `Pipeline.cancel()` sets a flag checked between stages.
- `context.cancelled` may also be set by long-running stages.
- Cancelled requests produce `CANCELLED` outcome.

---

## 2. Artifact Ownership

Each artifact is created by exactly one stage.  No stage may create an artifact
owned by another stage.

| Artifact | Creator Stage | Frozen |
|---|---|---|
| `Observation` | Execution (Runtime) | Yes |
| `Outcome` | Execution (Runtime) | Yes |
| `Decision` | Reasoner / Planner | Yes |
| `Verdict` | VerificationStage | Yes |
| `StoreDecision` | MemoryStage | Yes |
| `ArchitectureMetrics` | Pipeline (auto) | No (mutable dataclass) |
| `Plan` | PlannerStage | No (dict) |
| `CapabilityBindings` | CapabilitySelectionStage | No (dict) |

### 2.1 Activity spine

One `activity_id` roots every artifact in a single request:

| Artifact | References |
|---|---|
| `Observation.activity_id` | Required |
| `Outcome.activity_id` | Required |
| `Decision.activity_id` | Required |
| `Verdict.metadata` | Convention: `activity_id` |
| `StoreDecision.memory_refs` | Contains `activity_id` |
| `ArchitectureMetrics` | Implicit via `PipelineContext.activity_id` |
| `PipelineContext.activity_id` | Set before execution |

---

## 3. Stage Responsibilities

### 3.1 Receive
- **Field:** `parsed_request`
- **Purity:** Pure
- Parse and validate raw transport input.

### 3.2 LoadContext
- **Fields:** `metadata`, `session_id`, `user_id`
- **Purity:** Read-only
- Load session, user, and metadata from external stores.

### 3.3 Authentication
- **Purity:** Read-only
- Authenticate user/session.  May short-circuit on failure.

### 3.4 RateLimit
- **Purity:** Read-only
- Check rate limits.  May short-circuit on limit exceeded.

### 3.5 Intent
- **Field:** `classification`
- **Purity:** Pure
- Classify request intent (keyword-only, no LLM).

### 3.6 ContextRetrieval
- **Field:** `retrieved_context`
- **Purity:** Read-only
- Retrieve relevant context from memory (facts, preferences, conversation history).

### 3.7 Reasoner
- **Field:** `reasoning_assessment`
- **Purity:** Pure
- Assess reasoning complexity, requirements, constraints.  Rule-based, no LLM.

### 3.8 Planner
- **Field:** `plan`
- **Purity:** Pure
- Produce logical plan: `{goal, steps: [{intent, objective, constraints}]}`.

### 3.9 PlanValidator
- **Field:** `plan_validated`
- **Purity:** Pure
- Validate plan structure before capability binding.

### 3.10 CapabilitySelection
- **Field:** `selected_capabilities`
- **Purity:** Pure
- Resolve plan intents to capability descriptors.

### 3.11 Execution
- **Fields:** `execution_result`, `execution_state`, `outcome`
- **Purity:** Impure
- Execute plan steps via Runtime.  Creates Observations and Outcome.
- The **only** stage that may call LLM providers.

### 3.12 Verification
- **Field:** `verification_result`
- **Purity:** Pure
- Run verifiers (safety, schema, confidence) against Outcome.
- Produces `Verdict` list.

### 3.13 Epistemic
- **Field:** `epistemic_tags`
- **Purity:** Pure
- Tag confidence, provenance for response.

### 3.14 Memory
- **Fields:** `memory_refs`, `store_decision`
- **Purity:** Impure
- Extract facts from Outcome, check contradictions, store.
- The **only** stage that may write to the memory facade.

### 3.15 Metrics
- **Field:** `metrics`
- **Purity:** Pure
- Aggregate timing, token counts, retries.

### 3.16 Formatter
- **Field:** `formatted_response`
- **Purity:** Pure
- Produce final response payload.

---

## 4. Determinism Guarantees

### 4.1 DeterministicServices

```python
@dataclass
class DeterministicServices:
    uuid4: Callable[[], str]
    now: Callable[[], datetime]
    seed: int
```

- `real()` — uses `uuid.uuid4().hex` and `datetime.now(timezone.utc)`.
- `fake()` — uses sequential IDs (`00000000000000000000000000000001`, …)
  and a fixed timestamp.  `seed=42`.

### 4.2 Guarantees

When a `FakeServices` instance is injected AND the LLM provider is mocked:

1. **Replay identity:** Running the same `Request` twice produces identical
   structural artifacts (fingerprints, payloads, execution_state, plan steps,
   capabilities, verdict outcomes, memory decisions).
2. **Fingerprints are deterministic:** `Observation.fingerprint` = SHA-256 of
   `{source, type, payload}` (content-addressable, no time component).
3. **Observation IDs differ per call** even within the same request (sequential
   counter advances).
4. **No cross-request leakage:** Each `Pipeline.execute()` call starts with
   a fresh context; accumulated state (`_observations`, `_step_results`) is
   cleared at the start of each execution.

---

## 5. Observation Model

```python
@dataclass(frozen=True)
class Observation:
    id: str
    fingerprint: str          # SHA-256(source + type + payload)[:16]
    activity_id: str          # Must match the root Activity
    source: str               # "execution", "scheduler", "tool", "llm", …
    type: str                 # "text", "tool_output", "search_result", …
    timestamp: datetime
    payload: dict
    confidence: float | None
    metadata: dict
    parent_id: str | None     # Parent Observation or Activity node id
    tenant_id: str | None     # Enterprise (Phase 6)
    organization_id: str | None
    workspace_id: str | None
```

### 5.1 Invariants

- Every `Observation` belongs to exactly one Activity (`activity_id` required).
- `fingerprint` is deterministic given the same source + type + payload.
- `Observation.new()` factory auto-generates `id` (UUID4 or sequential) and
  `fingerprint`.
- Observations are **immutable** (frozen dataclass).
- The Observation Hub publishes them as `Event(type="observation.observed")`
  on the canonical EventBus after execution.

### 5.2 Sources

`execution`, `scheduler`, `tool`, `llm`, `filesystem`, `user`, `browser`,
`plugin`, `webhook`, `timer`.

### 5.3 Types

`text`, `tool_output`, `search_result`, `browser_page`, `error`, `metric`,
`code`, `image`.

---

## 6. Outcome Model

```python
@dataclass(frozen=True)
class Outcome:
    success: bool
    outputs: list[Any]
    artifacts: list[Any]
    tool_results: list[dict]
    observations: list[Observation]
    metrics: dict[str, Any]
    activity_id: str
    errors: list[str]
```

### 6.1 Invariants

- **Immutable** (frozen).  Cannot be modified after creation.
- `activity_id` must match `PipelineContext.activity_id`.
- `observations` list may be empty (unexpected) but should contain at least
  one Observation for non-empty input.
- `outcome.activity_id == context.activity_id == every Observation.activity_id`.

---

## 7. Verification Model

```python
@dataclass(frozen=True)
class Verdict:
    status: Literal["PASS", "WARNING", "FAIL"]
    blocking: bool = True       # FAIL + blocking=True → pipeline stops
    confidence: float = 1.0
    metadata: dict = field(default_factory=dict)
```

### 7.1 Invariants

- Verdicts are produced by `VerificationStage` only.
- `FAIL + blocking=True` causes pipeline to stop.
- `FAIL + blocking=False` is advisory (continues execution).
- Verification result stored as `{"verdicts": [...], "passed": bool}` in
  `context.verification_result`.

---

## 8. Memory Model

```python
class StoreAction(Enum):
    STORE = "store"
    UPDATE = "update"
    MERGE = "merge"
    DELETE = "delete"
    IGNORE = "ignore"

@dataclass(frozen=True)
class StoreDecision:
    action: StoreAction
    store_type: str
    reason: str
    confidence: float
    fact_count: int = 0
    contradictions: list[dict] | None = None
    memory_refs: list[str] = field(default_factory=list)
```

### 8.1 Invariants

- `StoreDecision` replaces raw dicts (`context.store_decision`).
- Memory writes happen only in `MemoryStage`.
- Facts are extracted from `Outcome` using pattern-based extraction (no LLM).
- Contradiction detection is rule-based (no LLM).
- Enterprise fields (`tenant_id`, `organization_id`, `workspace_id`) are
  nullable on `ExtractedFact` from day one.

---

## 9. Architecture Metrics Model

```python
@dataclass
class ArchitectureMetrics:
    reasoning_complexity: str    # "simple", "multi_step", "unknown"
    plan_steps: int
    selected_capabilities: int
    observations: int
    verifiers: int
    memory_operations: int
    activity_depth: int
    retries: int
    execution_state: str
```

### 9.1 Collection

- Auto-populated by `Pipeline.execute()` after all stages complete via
  `ArchitectureMetrics.from_context(ctx)`.
- Per-request — not a global aggregate.  A separate `MetricsCollector`
  (future) aggregates across requests.
- Serialized to JSON in snapshot traces.

---

## 10. Snapshot Format

```json
{
  "activity_id": "00000000000000000000000000000001",
  "request_id": "00000000000000000000000000000001",
  "execution_state": "completed",
  "runtime_version": {
    "pipeline": "1.0",
    "runtime_spec": "1.0",
    "architecture": "1.0",
    "snapshot": "1.0"
  },
    "architecture_metrics": {
      "reasoning_complexity": "unknown",
      "plan_steps": 0,
      "selected_capabilities": 0,
      "observations": 1,
      "verifiers": 3,
      "memory_operations": 1,
      "activity_depth": 1,
      "retries": 0,
      "execution_state": "completed",
      "runtime_version": {
        "pipeline": "1.0",
        "runtime_spec": "1.0",
        "architecture": "1.0",
        "snapshot": "1.0"
      }
    },
  "outcome": {
    "activity_id": "00000000000000000000000000000001",
    "success": true,
    "observations": [
      {
        "id": "00000000000000000000000000000002",
        "fingerprint": "9d3d2e55ddb44b56",
        "activity_id": "00000000000000000000000000000001",
        "source": "execution",
        "type": "text",
        "payload": {"text": "response"}
      }
    ]
  },
  "verification": {
    "passed": true,
    "verdicts": [
      {"verifier": "safety", "outcome": "PASS", "blocking": true, "confidence": 1.0}
    ]
  },
  "store_decision": {
    "action": "store",
    "store_type": "conversation",
    "confidence": 0.95
  },
  "pipeline_version": "1.0"
}
```

### 10.1 Invariants

- `activity_id` matches `outcome.activity_id` matches every
  `observation.activity_id`.
- `store_decision.action` is one of `store`, `skip`, `update`, `merge`,
  `delete`, `ignore`.
- Every observation has a `fingerprint` and `id`.
- Snapshot files are stored as `tests/architecture/snapshots/*.json`.

---

## 11. Runtime Invariants (Dynamic)

These six invariants are verified by `test_trace_validation.py` after every
pipeline execution:

| # | Invariant | Test Name |
|---|---|---|
| 1 | Every Observation belongs to exactly one Activity | `test_every_observation_belongs_to_activity` |
| 2 | No duplicate Observation IDs within an Activity | `test_no_duplicate_observation_ids` |
| 3 | Outcome.activity_id matches context.activity_id | `test_outcome_matches_activity_id` |
| 4 | Verdicts are present after VerificationStage | `test_verdict_present_in_context` |
| 5 | StoreDecision is present after MemoryStage | `test_memory_decision_present_in_context` |
| 6 | Two sequential executions produce different activity IDs | `test_no_cross_activity_leakage` |

---

## 12. Replay Guarantees

When `DeterministicServices.fake()` is injected and the LLM provider is mocked:

1. **Structural identity:** Two runs of the same `Request` produce identical:
   `execution_state`, `error`, `outcome.success`, `observation_count`,
   `fingerprints`, payloads, verdict outcomes, memory decisions.
2. **Fingerprint repeatability:** Same source + type + payload always produces
   the same SHA-256 fingerprint.
3. **Replay with plan:** Pre-setting `plan` and `selected_capabilities` does
   not affect replay identity.

---

## 13. Change Policy

### 13.1 Breaking changes (require new ADR)

- Changing the stage order defined in ADR-007.
- Adding or removing fields from frozen dataclasses
  (`Observation`, `Outcome`, `Decision`, `Verdict`, `StoreDecision`).
- Changing the `process_message()` signature.
- Changing the `Pipeline.execute()` return type.
- Removing fields from `ArchitectureMetrics`.
- Changing the snapshot format in a way that breaks existing snapshots.

### 13.2 Additive changes (allowed freely)

- Adding new fields to `PipelineContext`.
- Adding new stages (before or after existing stages).
- Adding new verifier implementations.
- Adding new fact extraction patterns.
- Adding new metric fields to `ArchitectureMetrics`.
- Adding new snapshot tests.

### 13.3 Merge gate

Every PR must pass:
1. **Architecture audit** (static rules, `test_architecture_audit.py`).
2. **Runtime validation** (dynamic rules, `test_trace_validation.py`).
3. **Replay validation** (`test_replay_validation.py`).
4. **All existing tests** — regressions are not permitted.
