# Migration Backlog

Architecture debt register — pre-existing violations of Runtime v1 ownership
boundaries found by the architecture audit.

**Lifecycle:** OPEN → PLANNED → IN_PROGRESS → VERIFIED → REMOVED

---

## LLM Outside Execution ❌ RESOLVED

All 23 files migrated to route through `core.pipeline.internal_client.prompt()`
or use `importlib`-based lazy access to `core.llm_router` for vision/plumbing calls.
`core/llm_failover.py` exempted as LLM infrastructure.

---

## Memory Writes Outside Memory

Memory facade writes must be confined to the Memory stage.

| ID | File | Severity | Target Phase | Owner | Status |
|---|---|---|---|---|---|
| MEM-01 | `core/agents/_legacy/nexus.py` | medium | Phase 6 | — | OPEN |
| MEM-02 | `core/context_builder.py` | medium | Phase 6 | — | OPEN |
| MEM-03 | `core/routes/intelligence.py` | medium | Phase 6 | — | OPEN |

**Replacement:** Route memory writes through `MemoryStage` or the canonical
`process_message()` pipeline.

---

## ProviderManager Outside Execution

Provider management must be confined to the Execution stage.

| ID | File | Severity | Target Phase | Owner | Status |
|---|---|---|---|---|---|
| PRV-01 | `core/pipeline/__init__.py` | low | Phase 5 | — | OPEN |
| PRV-02 | `core/providers/manager.py` | low | Phase 6 | — | OPEN |

**Notes:**
- `core/pipeline/__init__.py` re-exports `ProviderManager` and `Provider` for
  external use.  This is a convenience export, not a usage violation.
- `core/providers/manager.py` is a different `ProviderManager` (legacy provider
  abstraction).

---

## Activity Mutations Outside Execution

ActivityGraph mutations should be confined to the Execution stage (Runtime
class) and ActivityManager internals.

| ID | File | Severity | Target Phase | Owner | Status |
|---|---|---|---|---|---|
| ACT-01 | `core/activity/__init__.py` | medium | Phase 6 | — | OPEN |
| ACT-02 | `core/activity/recorder.py` | medium | Phase 6 | — | OPEN |
| ACT-03 | `core/activity/resume.py` | medium | Phase 6 | — | OPEN |
| ACT-04 | `core/coding/build_benchmark.py` | medium | Phase 6 | — | OPEN |
| ACT-05 | `core/lifespan.py` | medium | Phase 6 | — | OPEN |
| ACT-06 | `core/long_term_memory/consolidator.py` | medium | Phase 6 | — | OPEN |
| ACT-07 | `core/long_term_memory/extractor.py` | medium | Phase 6 | — | OPEN |
| ACT-08 | `core/pipeline.py` | medium | Phase 6 | — | OPEN |
| ACT-09 | `core/routes/activity.py` | medium | Phase 6 | — | OPEN |
| ACT-10 | `core/scheduler/queue.py` | medium | Phase 5 | — | OPEN |
| ACT-11 | `core/scheduler/scheduler.py` | medium | Phase 5 | — | OPEN |
| ACT-12 | `core/tools/automated_build.py` | medium | Phase 6 | — | OPEN |
| ACT-13 | `core/workflow/recorder.py` | medium | Phase 6 | — | OPEN |

**Notes:**
- `core/scheduler/scheduler.py` and `core/scheduler/queue.py` are intentionally
  exempt during Phase 5 — the scheduler is being migrated to use
  `PipelineExecutor`, after which activity mutations will be owned by Execution.

---

## Duplicate Reasoner

There must be exactly one Reasoner abstraction (ReasonerStage).

| ID | File | Severity | Target Phase | Owner | Status |
|---|---|---|---|---|---|
| RSN-01 | `core/schemas.py` (class `ReasonResult`) | low | Phase 6 | — | OPEN |

**Replacement:** `ReasonResult` should be replaced by the canonical
`Decision` dataclass from `core/pipeline/decision.py`.

---

## Duplicate Verification

All verification logic must live in `core/pipeline/stages/verification/`.

| ID | File | Severity | Target Phase | Owner | Status |
|---|---|---|---|---|---|
| VRF-01 | `core/plugins/verification.py` (`VerificationMode`, `ManifestVerifier`) | low | Marketplace | — | OPEN |

**Replacement:** Implement as `Verifier` subclass in the verification package.
