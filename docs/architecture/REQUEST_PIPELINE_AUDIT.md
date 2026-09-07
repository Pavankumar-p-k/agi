# Request Pipeline Audit — Phase 1 (Document 3)

> **Purpose:** Trace every request from user input through normalization, language detection, intent/entity extraction, constraint injection, context retrieval, planning, and into execution. Builds on the execution architecture audit by filling in everything *before* execution.
>
> **Scope:** All entry points, the 19-stage canonical pipeline, the legacy 10-phase RuntimePipeline, and all decision/branching points.

---

## Table of Contents

1. [Pipeline Architecture Overview](#1-pipeline-architecture-overview)
2. [Entry Points & Adapters](#2-entry-points--adapters)
3. [Full 19-Stage Pipeline Trace](#3-full-19-stage-pipeline-trace)
4. [Legacy RuntimePipeline (10-Phase)](#4-legacy-runtimepipeline-10-phase)
5. [Decision Points & Branching](#5-decision-points--branching)
6. [Context Flow & Field Ownership](#6-context-flow--field-ownership)
7. [Bypass Paths](#7-bypass-paths)
8. [Key Findings](#8-key-findings)
9. [Recommendations](#9-recommendations)

---

## 1. Pipeline Architecture Overview

### Two Parallel Systems

| System | Stages/Phases | Entry Points | Status |
|--------|---------------|-------------|--------|
| **Canonical Pipeline** (ADR-007) | 19 stages, sequential | All transport adapters | Primary path |
| **Legacy RuntimePipeline** (ADR-008) | 10 phases, LangGraph-based | Legacy agent graph | Deprecated but still functional |

### Canonical Pipeline Stage Map

```
┌──────────────────────────────────────────────────────────────┐
│                      PIPELINE CONTEXT                        │
│  ~35 fields: request, response, identity, plan, decisions,   │
│  outcomes, observations, metrics, preferences, memory_refs,  │
│  stage_results, error, metadata, deterministic_services       │
└──────────────────────────────────────────────────────────────┘
         ▲              ▲              ▲              ▲
         │              │              │              │
    ┌────┴────┐   ┌────┴────┐   ┌────┴────┐   ┌────┴────┐
    │ Stage 1 │   │ Stage 2 │   │  ...    │   │ Stage 19│
    │ Receive │──▶│  Load   │──▶│  ...    │──▶│ Format  │
    └─────────┘   │ Context │   └─────────┘   └─────────┘
                  └─────────┘
```

### Data Flow (User → Goal → Execution → Response)

```
User Input
  │
  ▼
[Transport Adapter] ─── converts to Request(text, transport, user_id, ...)
  │
  ▼
[Pipeline.execute()] ─── creates PipelineContext, iterates 19 stages
  │
  ├── [Stages 1-7] Infrastructure: Receive, LoadContext, Auth, Tenant, Authz, ResourceAccess, RateLimit
  │     Pure metadata processing. No understanding of the request content.
  │
  ├── [Stage 8] IntentStage: classify_request(text) → {mode, confidence, sub_type}
  │     Keyword match (<1ms) → LLM fallback if low confidence → AGENT mode as uncertainty floor
  │
  ├── [Stage 9] ContextRetrievalStage: memory.recall() → ReRanker → PreferenceProfile
  │     Lazy imports: memory facade, reranker, fact store, preference profile
  │
  ├── [Stage 10] ReasonerStage: assess complexity, requirements, constraints from keywords
  │     Deterministic rules. No LLM. Output: {complexity, requirements, constraints, confidence}
  │
  ├── [Stage 11] PlannerStage: build plan steps from requirements
  │     Simple → 1 step. Multi-step/agentic → decompose into research/browse/code/respond steps.
  │
  ├── [Stage 12] PlanValidatorStage: validate plan structure (intent, objective, constraints)
  │     6 validation rules. FAIL if any rule is violated.
  │
  ├── [Stage 13] CapabilitySelectionStage: map plan steps to capabilities
  │     Maps intent string to capability ID via hardcoded dict → fallback to "documentation"
  │
  ├── [Stage 14] ExecutionStage: call LLM or execute plan steps
  │     FIRST LLM call. LiteLLMProvider → OllamaFallbackProvider. Routes via core.llm_router.
  │
  ├── [Stage 15] VerificationStage: SafetyVerifier → SchemaVerifier → ConfidenceVerifier
  │     Can FAIL and block the response. Lazy loaded DEFAULT_VERIFIERS list.
  │
  ├── [Stage 16] EpistemicTaggingStage: {model, confidence, timestamp, provenance}
  │     Simple: confidence 1.0 if no error, 0.0 if error.
  │
  ├── [Stage 17] MemoryStage: classify conversation → extract facts → store
  │     Branches on verification result. Can IGNORE or STORE.
  │
  └── [Stage 18-19] MetricsStage → FormatterStage
        Aggregate metrics → Build final response text
  │
  ▼
[process_message()] ─── reads context.formatted_response → builds Response
  │
  ▼
[Transport Adapter] ─── converts Response to platform format
  │
  ▼
User receives response
```

---

## 2. Entry Points & Adapters

### Canonical Pipeline Entry Points

| Transport | Adapter | File | Request Source |
|-----------|---------|------|----------------|
| REST API | `rest_adapter()` | `core/pipeline/adapters/rest_adapter.py` | FastAPI `/api/chat` endpoint |
| WebSocket | `ws_adapter()` / `stream_via_pipeline()` | `core/pipeline/adapters/websocket_adapter.py` | `/ws/chat_stream`, `/ws/agent_stream` |
| Channel (Telegram, Discord, Slack, etc.) | `channel_adapter()` | `core/pipeline/adapters/channel_adapter.py` | `channels/processor.py` |
| Voice | `voice_adapter()` | `core/pipeline/adapters/voice_adapter.py` | Transcribed speech from `assistant/voice_pipeline.py` |
| Internal | `prompt()` | `core/pipeline/internal_client.py` | Internal LLM calls (agent, classifier, tools) |

### Legacy Entry Points (Bypass Canonical Pipeline)

| Transport | Handler | File | Note |
|-----------|---------|------|------|
| Legacy WebSocket | `handle_message()` | `network/websocket_server.py` | Calls `intent_router.extract_intent()` directly. Does NOT use pipeline. |
| Legacy CLI | `cli_commands` | `cli_commands` | Some commands bypass pipeline for direct execution. |

### Request Model

```python
@dataclass
class Request:
    message_id: str        # UUID, generated
    channel: str           # "rest", "ws", "telegram", "voice", "internal"
    user_id: str           # From transport auth
    session_id: str        # From transport or generated
    text: str              # The user's input
    attachments: list      # File attachments
    metadata: dict         # Transport-specific metadata
    timestamp: datetime    # When received
```

---

## 3. Full 19-Stage Pipeline Trace

### Stage 1: `ReceiveStage` (`core/pipeline/stages/receive.py`)

| Aspect | Detail |
|--------|--------|
| **Reads** | `context.raw_input`, `context.attachments` |
| **Writes** | `context.parsed_request = {"text": ..., "attachment_count": ...}` |
| **Decision** | None (pass-through) |
| **Failure** | Never fails |
| **LLM call** | ❌ |

### Stage 2: `LoadContextStage` (`core/pipeline/stages/load_context.py`)

| Aspect | Detail |
|--------|--------|
| **Reads** | `context.transport`, `context.user_id`, `context.session_id` |
| **Writes** | `context.metadata["transport/ user_id/ session_id"]` |
| **Decision** | Only writes if user_id/session_id are non-None |
| **Failure** | Never fails |
| **LLM call** | ❌ |

### Stage 3: `AuthenticationStage` (`core/pipeline/stages/auth.py`)

| Aspect | Detail |
|--------|--------|
| **Reads** | `context.identity`, `context.metadata["auth_token"]` |
| **Writes** | `context.authentication_result = AuthenticationResult(...)` |
| **Decision** | Validates token via `IdentityService.authenticate_session()`. FAIL if invalid. |
| **Failure** | FAIL on invalid/expired token |
| **LLM call** | ❌ |

### Stage 4: `TenantResolutionStage` (`core/pipeline/stages/tenant_resolution.py`)

| Aspect | Detail |
|--------|--------|
| **Reads** | `context.identity`, `context.authentication_result` |
| **Writes** | `context.tenant_resolution_result`, updates `context.resource_scope.tenant_id` |
| **Decision** | Resolves canonical tenant via `IdentityService.resolve_tenant()` |
| **Failure** | FAIL if tenant resolution fails |
| **LLM call** | ❌ |

### Stage 5: `AuthorizationStage` (`core/pipeline/stages/authorization.py`)

| Aspect | Detail |
|--------|--------|
| **Reads** | `context.metadata["auth_scope"]`, `context.identity`, `context.authentication_result` |
| **Writes** | `context.authorization_result`, `context.resource_grant = ResourceGrant(...)` |
| **Decision** | Checks scope against canonical scopes via `IdentityService.authorize()` |
| **Failure** | FAIL if unauthorized |
| **LLM call** | ❌ |

### Stage 6: `ResourceAccessStage` (`core/pipeline/stages/resource_access.py`)

| Aspect | Detail |
|--------|--------|
| **Reads** | `context.resource_scope`, `context.resource_grant` |
| **Writes** | `context.resource_access_result` |
| **Decision** | Evaluates visibility (PUBLIC/TENANT/WORKSPACE/PRIVATE). Checks grant expiry. |
| **Failure** | FAIL if access denied or grant expired |
| **LLM call** | ❌ |

### Stage 7: `RateLimitStage` (`core/pipeline/stages/rate_limit.py`)

| Aspect | Detail |
|--------|--------|
| **Reads** | (nothing) |
| **Writes** | (nothing) |
| **Decision** | **Pass-through.** No rate limiting implemented at stage level. |
| **Failure** | Never fails |
| **LLM call** | ❌ |

### Stage 8: `IntentStage` (`core/pipeline/stages/intent.py`)

| Aspect | Detail |
|--------|--------|
| **Reads** | `context.raw_input` |
| **Writes** | `context.classification = {"mode": ..., "confidence": ..., "sub_type": ...}` |
| **Key call** | `classify_request(text)` from `core/routing/request_classifier.py` |
| **Algorithm** | 1. Keyword match (5 pattern groups, <1ms). 2. If confidence < 0.85: LLM fallback via `internal_client.prompt()`. 3. If still < 0.70: escalate to AGENT mode. |
| **Failure** | Never fails (degraded classification returned) |
| **LLM call** | ✅ (only if keyword confidence < 0.85) |

### Stage 9: `ContextRetrievalStage` (`core/pipeline/stages/context_retrieval.py`)

| Aspect | Detail |
|--------|--------|
| **Reads** | `context.raw_input`, `context.user_id`, `context.session_id` |
| **Writes** | `context.retrieved_context = {"memories": [...], "formatted_context": "...", "preferences": {...}}` |
| **Sub-calls** | 1. `memory.recall(query, user_id, limit=5)` — 5-second timeout. 2. `ReRanker.rerank(query, items, preferences)` — optional. 3. `PreferenceProfile(user_id).build(fact_store)` → `.format_context()`. |
| **Lazy imports** | `memory.memory_facade.memory`, `memory.reranker.ReRanker`, `memory.fact_store.get_fact_store`, `memory.preference_profile.PreferenceProfile` — all wrapped in try/except |
| **Failure** | Never fails (returns empty context on error) |
| **LLM call** | ❌ |

### Stage 10: `ReasonerStage` (`core/pipeline/stages/reasoner.py`)

| Aspect | Detail |
|--------|--------|
| **Reads** | `context.classification`, `context.raw_input`, `context.retrieved_context` |
| **Writes** | `context.reasoning_assessment = {"complexity", "requirements", "constraints", "confidence", "estimated_steps", "routing_hints"}` |
| **Methods** | 1. `_assess_complexity()` — keyword match: simple/multi_step/agentic based on classification mode. 2. `_assess_requirements()` — keyword detection for research/browser/coding/memory. 3. `_assess_constraints()` — keyword detection for speed/accuracy/freshness. 4. `_estimate_steps()` — simple=1, multi_step=len(reqs)+1, agentic=len(reqs)+2. |
| **Decision** | Branching is purely rule-based on classification mode |
| **Failure** | Never fails |
| **LLM call** | ❌ |

### Stage 11: `PlannerStage` (`core/pipeline/stages/planner.py`)

| Aspect | Detail |
|--------|--------|
| **Reads** | `context.reasoning_assessment`, `context.raw_input` |
| **Writes** | `context.plan = {"goal": raw_input, "steps": [{"intent", "objective", "constraints"}]}` |
| **Algorithm** | 1. If complexity == "simple": single `respond` step. 2. Otherwise: map requirements → steps (research→search_web, browser→browse_web, coding→write_code). Always appends `respond`. |
| **Decision** | Based entirely on complexity from ReasonerStage |
| **Failure** | Never fails |
| **LLM call** | ❌ (deterministic) |

### Stage 12: `PlanValidatorStage` (`core/pipeline/stages/plan_validator.py`)

| Aspect | Detail |
|--------|--------|
| **Reads** | `context.plan` |
| **Writes** | `context.plan_validated = True` or **FAIL** |
| **Validation Rules** | 1. Plan is None → FAIL. 2. Steps not a list or empty → FAIL. 3. Any step not a dict → FAIL. 4. Any step missing `intent` → FAIL. 5. Any step missing `objective` → FAIL. 6. Any step has non-dict `constraints` → FAIL. |
| **Failure** | FAIL if any rule violated. Blocks pipeline. |
| **LLM call** | ❌ |

### Stage 13: `CapabilitySelectionStage` (`core/pipeline/stages/capability_selection.py`)

| Aspect | Detail |
|--------|--------|
| **Reads** | `context.plan` |
| **Writes** | `context.selected_capabilities = {step_index: [Capability, ...]}` |
| **Key function** | `_resolve(intent)` — maps intent string to capability ID via hardcoded `intent_to_cap` dict |
| **Fallback** | If no capabilities match: uses `_BUILTIN_CAPABILITIES.get("documentation")` |
| **Lazy imports** | `core.capability.registry.capability_registry` (wrapped in try/except), `core.capability.models._BUILTIN_CAPABILITIES` |
| **Failure** | Never fails (returns fallback capability) |
| **LLM call** | ❌ |

### Stage 14: `ExecutionStage` (`core/pipeline/stages/execution.py`)

| Aspect | Detail |
|--------|--------|
| **Reads** | `context.raw_input`, `context.plan`, `context.selected_capabilities` |
| **Writes** | `context.execution_result`, `context.outcome`, `context.execution_state`, `context.error` |
| **Sub-components** | 1. `ProviderManager` — chains providers (LiteLLM → Ollama). 2. `Runtime` — step-by-step plan execution with activity recording. 3. `LLMStepExecutor` — default step executor. 4. `LiteLLMProvider` — calls `core.llm_router.get_router().acompletion()`. 5. `OllamaFallbackProvider` — direct HTTP call to Ollama. |
| **Branching** | 1. Empty input → CONTINUE. 2. Plan + capabilities → `_execute_plan()` (multi-step). 3. Otherwise → `_execute_simple()` (single LLM call). |
| **Provider Chain** | `LiteLLMProvider` (primary) → `OllamaFallbackProvider` (if LiteLLM fails). Both registered in `with_default_providers()`. |
| **Lazy imports** | `core.llm_router.get_router`, `core.activity.models.ActivityStatus`, `core.activity.manager.ActivityManager`, `httpx`, `core.llm_router.get_ollama_url` |
| **Failure** | Can fail on LLM or provider error. Writes error to context. |
| **LLM call** | ✅ **Primary LLM call location** |

### Stage 15: `VerificationStage` (`core/pipeline/stages/verification/__init__.py`)

| Aspect | Detail |
|--------|--------|
| **Reads** | `context.outcome`, `context.execution_result`, `context.epistemic_tags` |
| **Writes** | `context.verification_result = {"verdicts": [...], "passed": bool}` |
| **Verifiers** | 1. `SafetyVerifier` — blocks injection patterns ("ignore previous instructions", "system prompt:"). 2. `SchemaVerifier` — checks `outcome.success` + "text" field. 3. `ConfidenceVerifier` — warns if epistemic confidence < 0.3. |
| **Decision** | FAIL if any `blocking=True` verifier returns FAIL |
| **Failure** | FAIL on safety/schema violation. Blocks response. |
| **LLM call** | ❌ |

### Stage 16: `EpistemicTaggingStage` (`core/pipeline/stages/epistemic.py`)

| Aspect | Detail |
|--------|--------|
| **Reads** | `context.execution_result`, `context.error` |
| **Writes** | `context.epistemic_tags = {"model": ..., "confidence": 1.0|0.0, "timestamp": ..., "provenance": "execution"}` |
| **Logic** | Confidence 1.0 if no error, 0.0 if error |
| **Note** | Trivial implementation. `brain/epistemic_tagger.py` has richer tagging but is NOT used by this stage. |
| **Failure** | Never fails |
| **LLM call** | ❌ |

### Stage 17: `MemoryStage` (`core/pipeline/stages/memory.py`)

| Aspect | Detail |
|--------|--------|
| **Reads** | `context.outcome`, `context.execution_result`, `context.raw_input`, `context.user_id`, `context.activity_id`, `context.verification_result` |
| **Writes** | `context.memory_refs`, `context.store_decision` |
| **Key calls** | 1. `_classify()` — keyword matching (preference/project/fact/conversation). 2. `memory.store(messages, user_id)` — conversation storage. 3. `extract_facts_from_messages()` — structured fact extraction. 4. `fact_store.find_contradictions()` — conflict check. 5. `fact_store.store_facts()` — persistence. |
| **Branching** | 1. Verification failed → `StoreAction.IGNORE`. 2. No output text → `StoreAction.IGNORE`. 3. Otherwise → `StoreAction.STORE`. |
| **Lazy imports** | `memory.memory_facade.memory`, `memory.extraction.extract_facts_from_messages`, `memory.fact_store.get_fact_store` |
| **Failure** | Never fails (silent catch-all on memory errors) |
| **LLM call** | ❌ |

### Stage 18: `MetricsStage` (`core/pipeline/stages/metrics.py`)

| Aspect | Detail |
|--------|--------|
| **Reads** | `context.classification`, `context.execution_result` |
| **Writes** | `context.metrics = {"intent": ..., "provider": ..., "tokens": ...}` |
| **Failure** | Never fails |
| **LLM call** | ❌ |

### Stage 19: `FormatterStage` (`core/pipeline/stages/formatter.py`)

| Aspect | Detail |
|--------|--------|
| **Reads** | `context.outcome`, `context.execution_result`, `context.error`, `context.epistemic_tags`, `context.metrics` |
| **Writes** | `context.formatted_response = {"text": ..., "epistemic": ..., "metrics": ...}` |
| **Text resolution** | `context.outcome.text` → `context.execution_result.get("text")` → `f"Error: {context.error}"` |
| **This is the LAST stage** | After this, `process_message()` reads `context.formatted_response["text"]` into `Response.text` |
| **Failure** | Never fails |
| **LLM call** | ❌ |

---

## 4. Legacy RuntimePipeline (10-Phase)

### Overview

The legacy `RuntimePipeline` in `core/pipeline.py` is a completely separate execution path. It uses LangGraph agent graphs instead of sequential stages.

### Phase Order

```
1.  Knowledge Injection       — BehaviorAdapter.for_planner() + format_for_prompt()
2.  Planning                  — PlannerExecutor.create_plan(goal) → ExecutionPlan
3.  Strategy Selection        — StrategyGenerator.generate() + StrategySelector.select()
4.  Decision + Capability     — infer_capabilities(goal), DecisionEvidence.collect(), UnifiedDecisionModel.rank()
5.  Provider Selection        — ProviderRouter.select(cap, task)
6.  Activity Recording        — ActivityManager.create_activity(), create_agent_task()
7.  Workflow Execution        — WorkflowEngine.start_workflow() with steps from plan
8.  Graph Execution           — AgentState + build_default_graph().execute(state) → SSE events
9.  Post-execution Recording  — marks activity nodes completed/failed
10. Provider Memory Feedback  — provider_memory.record(), calibration update
11. Learning Feedback         — Consolidator.consolidate_once_async() (background)
```

### Key Differences from Canonical Pipeline

| Aspect | Canonical Pipeline (19-stage) | Legacy RuntimePipeline (10-phase) |
|--------|------------------------------|-----------------------------------|
| Architecture | Sequential stages | LangGraph agent graph |
| Execution engine | Pipeline.execute() | build_default_graph().execute() |
| Knowledge injection | ContextRetrievalStage | BehaviorAdapter |
| Strategy selection | None (deterministic) | StrategyGenerator + StrategySelector |
| Capability inference | CapabilitySelectionStage (hardcoded dict) | infer_capabilities() (different implementation) |
| Provider selection | ExecutionStage (chain) | ProviderRouter.select() |
| Activity recording | ExecutionStage (inline) | Explicit phases 6 + 9 |
| Workflow engine | ExecutionStage (inline) | Explicit phase 7 |
| LLM calling | LiteLLMProvider → OllamaFallback | LangGraph agent nodes |
| Learning feedback | MemoryStage | Consolidator (background) |
| Used by | All transport adapters | Legacy agent graph only |

---

## 5. Decision Points & Branching

### Critical Decision Points in the Canonical Pipeline

| Stage | Decision | Options | Outcome |
|-------|----------|---------|---------|
| 8. Intent | Classification confidence | < 85% → LLM fallback. < 70% → escalate to AGENT mode | Changes how the request is handled |
| 10. Reasoner | Complexity assessment | simple / multi_step / agentic | Determines plan structure |
| 11. Planner | Complexity-based branching | simple → 1 respond step. multi_step → decompose into steps | Changes execution path |
| 12. PlanValidator | Plan validity | Valid → continue. Invalid → FAIL | Blocks entire request |
| 14. Execution | Input type | empty → skip. plan exists → execute plan. otherwise → simple LLM | Changes execution engine |
| 14. Execution | Provider success | LiteLLM works → use result. LiteLLM fails → try Ollama | Determines provider used |
| 15. Verification | Safety/schema check | Pass → continue. Fail → block response | Can block response |
| 17. Memory | Store classification | verification failed → ignore. no text → ignore. otherwise → store | Determines if conversation is persisted |

### StageOutcome Values

| Outcome | Meaning | Effect |
|---------|---------|--------|
| `CONTINUE` | Stage succeeded | Proceed to next stage |
| `SHORT_CIRCUIT` | Skip remaining stages | Jump to FormatterStage |
| `RETRY` | Stage failed but retryable | Retry up to max_retries (default 3) |
| `FAIL` | Stage failed permanently | Break pipeline, return error |
| `DEFER` | Stage deferred execution | Break pipeline (resume later) |
| `CANCELLED` | Stage cancelled | Break pipeline |

---

## 6. Context Flow & Field Ownership

### PipelineContext Fields (~35 total)

| Field | Owner Stage | Written By | Read By |
|-------|-------------|-----------|---------|
| `request` | — | process_message() | All stages |
| `response` | 19. Formatter | FormatterStage | process_message() |
| `identity` | — | process_message() via IdentityService | 3. AuthenticationStage |
| `authentication_result` | 3. Auth | AuthenticationStage | 4. TenantResolution, 5. Authorization |
| `authorization_result` | 5. Authz | AuthorizationStage | 6. ResourceAccess |
| `resource_access_result` | 6. ResourceAccess | ResourceAccessStage | 17. MemoryStage |
| `resource_grant` | 5. Authz | AuthorizationStage | 6. ResourceAccess |
| `tenant_resolution_result` | 4. TenantResolution | TenantResolutionStage | context.resource_scope update |
| `classification` | 8. Intent | IntentStage | 10. ReasonerStage |
| `retrieved_context` | 9. ContextRetrieval | ContextRetrievalStage | 10. ReasonerStage |
| `reasoning_assessment` | 10. Reasoner | ReasonerStage | 11. PlannerStage |
| `plan` | 11. Planner | PlannerStage | 12. PlanValidator, 13. CapabilitySelection, 14. Execution |
| `plan_validated` | 12. PlanValidator | PlanValidatorStage | Pipeline execution loop |
| `selected_capabilities` | 13. CapabilitySelection | CapabilitySelectionStage | 14. Execution |
| `execution_result` | 14. Execution | ExecutionStage | 15. Verification, 16. Epistemic |
| `outcome` | 14. Execution | ExecutionStage | 15. Verification, 17. Memory, 19. Formatter |
| `execution_state` | 14. Execution | ExecutionStage | Pipeline execution loop |
| `verification_result` | 15. Verification | VerificationStage | 16. Epistemic, 17. Memory |
| `epistemic_tags` | 16. Epistemic | EpistemicTaggingStage | 15. Verification, 17. Memory, 19. Formatter |
| `memory_refs` | 17. Memory | MemoryStage | — |
| `store_decision` | 17. Memory | MemoryStage | — |
| `metrics` | 18. Metrics | MetricsStage | 19. Formatter |
| `formatted_response` | 19. Formatter | FormatterStage | process_message() |
| `error` | Any | Any failing stage | 19. Formatter |
| `metadata` | 2. LoadContext | LoadContextStage | Multiple |
| `resource_scope` | 4. TenantResolution | TenantResolutionStage | 6. ResourceAccess |
| `security_context` | — | Built from identity + grant | System-level |
| `deterministic_services` | — | process_message() | Testing only |

### Field Ownership Enforcement

`STAGE_OWNERSHIP` in `core/pipeline/base.py` maps each stage to the set of context fields it owns. `PipelineContext.set_stage_field()` emits a runtime warning if a non-owner stage writes to an owned field. This is the only cross-cutting enforcement in the pipeline.

---

## 7. Bypass Paths

### Known Pipeline Bypasses

| # | Bypass | From | To | Why |
|---|--------|------|----|-----|
| B1 | Legacy WebSocket | `network/websocket_server.py` | `core.intent_router.extract_intent()` → `core.main.execute_action()` | Pre-dates canonical pipeline. Not migrated. |
| B2 | Channel processor hooks | `channels/processor.py` | `mcp.server.mcp_server` + `brain.events.PluginEventBus` | Emits hooks in parallel with pipeline call. MCP and event bus receive messages without pipeline processing. |
| B3 | Internal client fallback | `core/pipeline/internal_client.py` | `core.pipeline.pipeline.process_message()` | If import fails, prompt() returns None. Silent degradation. |
| B4 | Agent graph execution | `core/pipeline.py` | LangGraph agent graph (`build_default_graph()`) | Entirely separate path. Bypasses all 19 stages. |
| B5 | Config `_PIPELINE_ENABLED` | `core/pipeline.py` | If False, skips pipeline entirely | Feature flag that bypasses the entire legacy pipeline. |

---

## 8. Key Findings

### Critical

| # | Finding | Impact |
|---|---------|--------|
| F1 | **No LLM is called until stage 14 (ExecutionStage)** — stages 1-13 are entirely deterministic (keyword matching, rules, DB lookups). The pipeine is a pure rule engine until the final execution. | This is actually correct design. The pipeline filters, classifies, and plans without LLM cost. |
| F2 | **Two complete pipeline architectures coexist** — the canonical 19-stage pipeline and the legacy 10-phase RuntimePipeline. They share no code, use different execution engines, and produce different results. | Any refactoring must deal with both. The legacy path is still wired in for agent graph execution. |
| F3 | **The canonical pipeline has 150+ lines of lazy imports** — every stage that touches memory, capability, or activity uses lazy imports wrapped in try/except. | Silent degradation. If memory facade import fails, context retrieval returns empty and the pipeline continues. |
| F4 | **RateLimitStage is a no-op** — the stage exists but does nothing. Rate limiting is handled at the HTTP middleware level, not in the pipeline. | Feature gap. If rate limiting is needed at pipeline level, it must be built. |
| F5 | **CapabilitySelectionStage uses a hardcoded intent-to-capability dict** — not the CapabilityRegistry. The `core/capability/` package is bypassed entirely in the canonical pipeline. | CapabilityRegistry is unused in the primary request path. |
| F6 | **PlanValidatorStage only checks structural validity** — it validates that the plan has `intent` and `objective` keys but does NOT validate that the capability exists, the provider can handle it, or the user has permission. | Plans can pass validation but fail at execution due to missing capabilities. |

### High

| # | Finding | Impact |
|---|---------|--------|
| F7 | **IntentStage can call LLM as fallback** — if keyword classification confidence < 85%, it calls `internal_client.prompt()` which goes through the pipeline recursively. | Recursive pipeline call. Potential for infinite loops if the fallback itself fails. |
| F8 | **ContextRetrievalStage has no retry** — memory.recall() has a 5-second timeout and no retry. If the memory service is slow, context is silently empty. | Users get responses with no memory context. |
| F9 | **VerificationStage uses module-level mutable `DEFAULT_VERIFIERS` list** — any code that imports the verifier module can modify the list, affecting all subsequent verifications. | Thread-unsafe verifier configuration. |
| F10 | **MemoryStage silently catches all exceptions** — memory store failures are logged but the pipeline continues. | Users are not notified when their conversations fail to persist. |
| F11 | **PlannerStage decomposes deterministically** — no LLM-based planning. All plan structure is keyword-driven. | Cannot handle ambiguous or novel requests that don't match keyword patterns. |

### Medium

| # | Finding | Impact |
|---|---------|--------|
| F12 | **The WebSocket server (`network/websocket_server.py`) has its own connection manager and intent router** — completely separate from the canonical pipeline's WebSocket adapter. | Two WebSocket paths. Feature divergence risk. |
| F13 | **EpistemicTaggingStage is trivial** — just sets confidence 1.0/0.0 based on error presence. The richer `brain/epistemic_tagger.py` is not used. | Epistemic tags provide no useful information. |
| F14 | **`context.parsed_request` is written but never read** — ReceiveStage writes it but no subsequent stage reads it. | Dead field in PipelineContext. |
| F15 | **`core/intent_router.py` is deprecated** — emits DeprecationWarning but is still used by the legacy WebSocket server. | Dead code path that should be migrated. |

---

## 9. Recommendations

### Pre-Build

| # | Recommendation | Target |
|---|---------------|--------|
| R1 | **Deprecate and remove legacy RuntimePipeline** — migrate the LangGraph agent graph execution to use the canonical pipeline's ExecutionStage. This eliminates the dual-pipeline problem (F2). | F2 |
| R2 | **Remove RateLimitStage if not needed** — or implement actual rate limiting. A no-op stage is dead code (F4). | F4 |
| R3 | **Wire CapabilitySelectionStage to CapabilityRegistry** — replace the hardcoded `intent_to_cap` dict with `capability_registry.match_goal()`. The CapabilityRegistry currently has no callers in the primary pipeline (F5). | F5 |
| R4 | **Add plan validation for capability existence** — PlanValidatorStage should verify that selected capabilities exist before returning SUCCESS (F6). | F6 |

### Design-Level

| # | Recommendation | Target |
|---|---------------|--------|
| R5 | **Replace lazy imports with explicit dependency injection** — every lazy import in stages is a hidden coupling. Pipeline stages should receive dependencies via constructor injection. | F3 |
| R6 | **Merge legacy WebSocket into canonical pipeline** — deprecate `network/websocket_server.py` and route all WebSocket traffic through `core/pipeline/adapters/websocket_adapter.py`. | F12, F15 |
| R7 | **Replace recursive IntentStage LLM fallback** — instead of calling the pipeline recursively, use a direct LLM call from a dedicated model provider. | F7 |
| R8 | **Make DEFAULT_VERIFIERS immutable** — use a tuple instead of a list to prevent runtime modification. | F9 |

### Architectural

| # | Recommendation | Target |
|---|---------------|--------|
| R9 | **Add retry and degradation reporting to ContextRetrievalStage** — if memory recall fails, the pipeline should report the failure to the user or use cached context as fallback (F8). | F8 |
| R10 | **Add LLM-based planning as an optional upgrade path** — the deterministic PlannerStage is fast but limited. Add an LLM-based planner that can handle novel requests (F11). | F11 |
| R11 | **Replace EpistemicTaggingStage** — wire in `brain/epistemic_tagger.py` or implement proper provenance tracking instead of trivial pass/fail tagging (F13). | F13 |

---

*End of REQUEST_PIPELINE_AUDIT.md — 19 stages traced, 2 pipeline architectures documented, 15 findings, 11 recommendations.*
