# Canonical Runtime Flow

## Lifecycle

Every request through the system follows the same lifecycle:

```
Signal → Observation → Opportunity → Decision → Plan → CapBinding
    → Execution → Outcome → Verification → Memory
```

### 1. Signal
An external trigger arrives through a transport adapter (HTTP, WS, CLI,
Telegram, Voice).  Transports call exactly one function:
`process_message(request: Request) -> Response`.

### 2. Observation
The **Execution** runtime converts each plan step into an ``Observation``
dataclass.  Observations are:

- **Immutable** (frozen dataclass)
- **Content-addressable** (``fingerprint`` = SHA-256 of source + type + payload)
- Published to the **Observation Hub** after each pipeline stage that produces
  them.

The **Observation Hub** is a thin adapter that converts Observation objects to
``Event`` objects and publishes them on the canonical ``EventBus``.  The hub
never knows its subscribers — it is a pure publisher.

Event type: ``observation.observed``.

### 3. Opportunity
The **OpportunityDiscoveryEngine** (legacy, ``core/opportunity/engine.py``)
listens for ``observation.observed`` events.  It detects patterns that warrant
autonomous action.  Every Opportunity records its originating observations in
``source_observation_ids``.

### 4. Decision
The **DecisionEngine** (``core/scheduler/decision.py``) evaluates opportunities
and produces a ``DecisionEstimate`` (impact, risk, expected value, confidence).
The highest-value decisions are forwarded to the Scheduler.

### 5. Plan
The **Planner** (ReasonerStage + PlannerStage) takes the decision's goal and
produces a logical plan (objectives, constraints, requirements).  The
**PlanValidator** checks structural validity before capability binding.

### 6. Capability Binding
The **CapabilitySelectionStage** resolves plan intents to concrete capability
descriptors from ``CapabilityRegistry``.

### 7. Execution
The **ExecutionStage** creates a **Runtime** instance that dispatches each plan
step through a **StepExecutor** (``LLMStepExecutor`` for LLM calls,
``SimpleStepExecutor`` for direct commands).  Each step produces an
``Observation`` (type: ``"tool_output"`` or ``"text"``).  The Runtime collects
all observations into the final ``Outcome``.

The Execution stage owns ``context.execution_state`` and ``context.outcome``.

### 8. Outcome
After all steps complete, the Runtime builds an immutable ``Outcome``:

```python
@dataclass(frozen=True)
class Outcome:
    success: bool
    outputs: list[Any]
    artifacts: list[Any]
    tool_results: list[dict[str, Any]]
    observations: list[Observation]
    metrics: dict[str, Any]
    activity_id: str
    errors: list[str]
```

The Outcome is stored in ``context.outcome`` and is published via the
Observation Hub.

### 9. Verification
The **VerificationStage** runs built-in verifiers (SafetyVerifier,
SchemaVerifier, ConfidenceVerifier) against the Outcome.  It produces a
``Verdict``:

```python
@dataclass(frozen=True)
class Verdict:
    status: Literal["PASS", "WARNING", "FAIL"]
    blocking: bool = True
    confidence: float = 1.0
    metadata: dict = field(default_factory=dict)
```

FAIL + blocking=True stops the pipeline. FAIL + blocking=False is advisory.

### 10. Memory
The **MemoryStage** extracts facts from the Outcome, checks for
contradictions, and produces a ``StoreDecision``:

```python
@dataclass(frozen=True)
class StoreDecision:
    action: StoreAction
    store_type: str
    reason: str
    confidence: float
    fact_count: int = 0
    contradictions: list[dict] = field(default_factory=list)
    memory_refs: list[str] = field(default_factory=list)
```

---

## Ownership Table

| Artifact | Created By | Stage |
|---|---|---|
| Observation | Runtime (ExecutionStage) | Execution |
| Outcome | Runtime (ExecutionStage) | Execution |
| Decision | ReasonerStage / PlannerStage | Reasoner / Planner |
| Verdict | VerificationStage | Verification |
| StoreDecision | MemoryStage | Memory |

---

## One Activity Roots Everything

Every artifact in a single request shares the same ``activity_id``:

- ``Observation.activity_id``
- ``Decision.activity_id``
- ``Outcome.activity_id``
- ``Verdict.metadata["activity_id"]`` (convention)
- ``StoreDecision.memory_refs`` (references)

This enables full traceability from Signal through Memory.

---

## Wiring

```
Transport Adapter
    │
    ▼
process_message(request) ────► Pipeline.execute(ctx)
                                    │
                            ┌───────┴───────┐
                            │  16 Stages    │
                            │  (ADR-007)    │
                            └───────┬───────┘
                                    │
                            ┌───────▼───────┐
                            │  Outcome      │
                            │  (immutable)  │
                            └───────┬───────┘
                                    │
                            ┌───────▼───────┐
                            │ Observation   │
                            │ Hub           │──► EventBus
                            └───────┬───────┘
                                    │
                            ┌───────▼───────┐
                            │ Opportunity   │
                            │ Engine        │
                            └───────┬───────┘
                                    │
                            ┌───────▼───────┐
                            │ Decision      │
                            │ Engine        │
                            └───────┬───────┘
                                    │
                            ┌───────▼───────┐
                            │ Scheduler     │
                            │ (+ worker)    │
                            └───────┬───────┘
                                    │
                            ┌───────▼───────┐
                            │ Pipeline      │
                            │ Executor      │──► process_message()
                            └───────────────┘
```

The Scheduler uses `PipelineExecutor` (the only adapter) to send autonomous
activities back through the pipeline, creating a closed loop.
