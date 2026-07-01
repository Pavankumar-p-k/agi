# RC1 — Gate 2: End-to-End Production Validation Report

**Date:** 2026-06-28  
**Architecture:** Frozen (no changes made, no code modified)  
**Primary Model:** qwen2.5:7b  

---

## Entry Point Matrix

| Entry Point | Reaches Pipeline? | Reaches Router? | Reaches Activity? | Reaches Learning? | Status |
|-------------|------------------|-----------------|-------------------|-------------------|--------|
| **POST /api/agent/stream** | ✅ via stream_agent_loop | ✅ Phase A.5 | ✅ Phase A.7 | ✅ Phase A.9 | Production |
| **WS /ws/agent_stream** (AGENT/CODEBASE mode) | ✅ via stream_agent_loop | ✅ Phase A.5 | ✅ Phase A.7 | ✅ Phase A.9 | Production |
| **jarvis chat** (CLI) | ✅ via WS → stream_agent_loop | ✅ Phase A.5 | ✅ Phase A.7 | ✅ Phase A.9 | Production |
| **Evaluation framework** | ✅ via stream_agent_loop | ✅ Phase A.5 | ✅ Phase A.7 | ✅ Phase A.9 | Test only |
| **Browser E2E tests** | ✅ via stream_agent_loop | ✅ Phase A.5 | ✅ Phase A.7 | ✅ Phase A.9 | Test only |
| WS /ws/agent_stream (DIRECT/ACTION mode) | ❌ fast-path bypass | ❌ | ❌ | ❌ | Legacy |
| WS /ws/chat_stream (legacy) | ❌ legacy graph | ❌ | ❌ | ❌ | Legacy |
| POST /api/chat | ❌ three_pass_handler | ❌ | ❌ | ❌ | Legacy |
| POST /v1/chat/completions | ❌ llm_router.complete | ❌ | ❌ | ❌ | Legacy |
| POST /api/agent/resume/{id} | ❌ graph.execute direct | ❌ | ❌ | ❌ | Legacy |
| jarvis code / build / run | ❌ AgentOrchestrator → AutomationLoop | ❌ | ❌ | ❌ | Legacy |
| All other CLI commands | ❌ REST API or in-process | ❌ | ❌ | ❌ | Legacy |
| All background services (Scheduler, Consolidator, etc.) | ❌ standalone subsystems | ❌ | ❌ | ❌ | Background |
| Scheduler tick | ❌ ResumeEngine → PlannerStateMachine | ❌ | ❌ | ❌ | Background |
| All 30+ CRUD API routes | ❌ direct to subsystem | ❌ | ❌ | ❌ | CRUD |

**Of 239 total API endpoints, only 2 reach the pipeline:** `POST /api/agent/stream` and `WS /ws/agent_stream` (in AGENT/CODEBASE modes). The AGENTS.md goal "Every entry point must enter RuntimePipeline" remains aspirational.

---

## Runtime Trace

### Actual execution path (instrumented live trace):

```
User message
  │
  ▼
stream_agent_loop()             ← agent_loop.py:72 — pipeline try block
  │
  ▼
RuntimePipeline.__init__()      ← creates all defaults
  │
  ▼
RuntimePipeline.execute()
  │
  ├── ✅ A.8 Knowledge Injection  → BehaviorAdapter.for_planner() fires (0 items — expected, no accumulated experience)
  ├── ✅ A.1 Planning             → PlannerExecutor.create_plan() → 4 steps (build_validate_notify)
  ├── ⚠️ A.2 Strategy Selection   → StrategyGenerator generates 4 → StrategySelector returns None
  ├── ✅ A.3 Decision Evidence    → DecisionEvidence.collect() + UnifiedDecisionModel.rank() → score=0.425
  ├── ✅ A.4 Capability Inference → infer_capabilities() → ["coding"]
  ├── ⚠️ A.5 Provider Selection   → Router selects claude_code (priority 50 beats forge priority 10 — health cache UNKNOWN)
  ├── ✅ A.7 Activity Recording   → ActivityManager.create_activity() + create_agent_task()
  ├── ✅ A.6 Workflow Execution   → WorkflowEngine.start_workflow() for 4 StepDefinitions
  │
  ▼
build_default_graph() + graph.execute(state)   ← ACTUAL EXECUTION
  │
  ├── setup_node: prompt_build (95s), tool selection
  ├── think_node: LLM call with pipeline_context.knowledge_prompt injected
  ├── route_node → tool_call_node → dispatch_node
  │
  ▼
Post-execution phases:
  ├── ✅ Activity completion     → mark_completed/mark_failed on exec_node + activity root
  ├── ✅ Provider Memory         → provider_memory.record(ProviderResult) for selected provider
  ├── ⚠️ Calibration update      → DecisionRecorder.record_outcome() fires → CalibrationEngine.update_from_outcomes()
  ├── ✅ Learning Feedback       → Consolidator.consolidate_once_async() spawned as background task
```

### Key finding: The pipeline executes all phases. No silent bypass occurs. The legacy fallback only activates if `_PIPELINE_ENABLED = False` or if an exception propagates from graph.execute().

### All pre-execution phases (A.1–A.8) are wrapped in try/except logger.debug — they silently skip on failure but never prevent execution.

---

## Bugs Found

### B1 — Critical: Evidence fallback chain never matches stored records

**File:** `core/providers/memory.py:_FALLBACK_CHAIN` (line 278) + `_match_keys` (line 292)

**Severity:** Critical

**Evidence:** 
- Evidence recorded with key: `(forge, coding, "", qwen2.5:7b, "")` (empty task_type, empty language)
- Evidence looked up with key: `(forge, coding, implement, qwen2.5:7b, python)` (populated task_type, populated language)
- Fallback chain: exact → drop model → drop model+task_type → capability only → provider-wide
- **None of these patterns produce a matching key** because each fallback masks different fields than what differs in the stored record

**Root cause:** `evidence_key()` creates exact 5-tuple string keys. The fallback chain only produces specific masked variants (e.g., `(c, tt, "", l)`, then `(c, "", "", l)`, then `(c, "", "", "")`, then `("", "", "", "")`). If the stored record has a field populated that the lookup has empty (or vice versa), the keys never match despite representing the same provider+capability.

**Impact:**
- Provider memory is recorded correctly but NEVER retrieved
- `get_performance_score()` always returns 0.5 (prior) → historical_success weight (0.20) is always 0
- Calibration adjustments are computed but never applied to routing (adjustment added to score, but score is based on stale prior data)
- The entire learning feedback loop (ProviderResult → FeedbackStore → Calibration → Future routing) is structurally broken
- **No amount of execution data will ever change routing decisions**

**Cross-check:**
- `provider_memory.record()` in line 334-395 — correctly stores data in _records dict
- `router._score()` in line 250 — calls `self._memory.get_performance_score(pid, task)` → always returns 0.5
- `get_performance_score()` in line 550 — calls `get_distribution()` → runs fallback chain → never matches → returns 0.5
- `_FALLBACK_CHAIN` has 5 patterns but none bridge this specific field mismatch
- Confirmed via 3-run test: scores never changed despite recording 3 outcomes

**Regression risk of fix:** Low. This is a lookup key matching issue. Fixing the fallback chain to include all 2^4 = 16 possible field combinations would restore the learning loop without affecting any other functionality.

---

### B2 — Medium: Health cache never refreshed in async context

**File:** `core/providers/router.py:select()` (lines 137-143)

**Severity:** Medium

**Evidence:**
- `asyncio.get_running_loop()` → True (always in production) → uses `provider._health_cache` directly
- `_health_cache` defaults to `UNKNOWN` (base.py:56) and is never refreshed during selection
- `cached_health()` (which refreshes the cache) is never called from select()
- Router filters only `DOWN` status — UNKNOWN passes through
- claude_code (priority 50) beats forge (priority 10) because all caches show UNKNOWN
- `forge` has a working `handle_tool` implementation that's never invoked

**Impact:**
- The highest-priority provider is always selected regardless of actual health
- forge's handle_tool (for forge-specific tools) is effectively dead code
- claude_code is selected despite being DOWN (not installed)

**Regression risk of fix:** Medium — fixing async health check refresh could change provider selection behavior

---

### B3 — Low: forge provider's handle_tool is dead code

**File:** `core/providers/adapters/forge.py:handle_tool()` (line 64)

**Severity:** Low

**Evidence:**
- forge has a working handle_tool for forge-specific tools (lines 64-90)
- forge is never selected by the router (claude_code wins due to priority)
- claude_code inherits default handle_tool from ExecutionProvider (returns None)
- All tool execution falls through to execute_tool_block() in the graph dispatch

**Impact:** forge's handle_tool specialization is never used in production.

---

### B4 — Low: DecisionRecorder + CalibrationEngine orphaned

**Files:** 
- `core/providers/feedback/recorder.py:DecisionRecorder`
- `core/providers/feedback/calibrator.py:CalibrationEngine`

**Severity:** Low

**Evidence:**
- Pipeline Phase A.8.5 calls `recorder.record_outcome()` and `calibrator.update_from_outcomes()` via `provider_router._get_decision_recorder()` / `_get_calibration_engine()`
- These fire correctly (confirmed via trace)
- But the recorded data is never used because `_score()`'s calibration adjustment (line 265-275) calls `calibration.get_adjustment()` which reads the calibration data
- The calibration data contains valid adjustments
- However, since the base score components (historical_success, benchmark_quality) always return 0.5/0 due to B1, the calibration adjustment of ~0.0-0.1 has no meaningful impact on ranking

**Impact:** FeedbackStore and CalibrationEngine are correctly implemented but their output is invisible because the base score doesn't reflect actual evidence.

---

## Remaining Production Risks

### Critical
- **Evidence fallback chain broken** — learning feedback is ornamental. No execution data affects routing.

### High
- **Only 2/239 endpoints reach the pipeline** — all CLI commands (code/build/run) and most API paths bypass the intended architecture. The pipeline is only used for streaming agent chat.

### Medium
- **Health cache never refreshed in async context** — router selects by priority, not by health. claude_code (DOWN) is preferred over forge (HEALTHY).
- **StrategySelector always returns None** — strategy dimension (line 191) produces no actionable output.

### Low
- **forge handle_tool dead code** — not invoked due to claude_code being preferred.
- **Knowledge injection returns 0 items** — BehaviorAdapter has no accumulated experiences yet (expected for cold start).
- **Autonomous workflow A still FAIL** — LLM hallucinates `trigger_research` instead of using `browser_snapshot` (model capability gap, documented in Gate 1).

---

## Files Examined (no changes made)

| File | Phase |
|------|-------|
| `core/pipeline.py` | P1, P2 |
| `core/agent_loop.py` | P1, P2 |
| `core/main.py` | P1 |
| `core/routes/chat.py` | P1 |
| `core/routes/websocket.py` | P1 |
| `core/routes/` (all 33 route files) | P1 |
| `core/providers/router.py` | P2, P3, P4 |
| `core/providers/memory.py` | P4 |
| `core/providers/base.py` | P3 |
| `core/providers/adapters/forge.py` | P3 |
| `core/providers/adapters/claude_code.py` | P3 |
| `core/providers/feedback/recorder.py` | P4 |
| `core/providers/feedback/calibrator.py` | P4 |
| `core/providers/bootstrap.py` | P2 |
| `core/graph/nodes.py` | P3 |

---

## GA Recommendation

### RC2 recommended

**Reasoning:**
- **One critical bug found:** The evidence fallback chain (B1) prevents the learning loop from ever affecting routing. This is a structural defect that makes the entire provider memory, feedback store, and calibration system decorative.
- **No code was changed** — this report only identifies the issue. A targeted fix (adding missing fallback patterns to `_FALLBACK_CHAIN`) would restore the learning feedback loop.
- **Pipeline runs correctly** — all phases fire in production, graph execution completes, activity recording works, and provider memory records data.
- **Known issue deferred:** Autonomous workflow A (model hallucination) is a model capability gap, not an architecture defect.
- **Architecture freeze preserved** — no features added, no redesign, no refactoring.

### Recommendation for RC2

1. **Fix B1** — Add the 11 missing fallback patterns to `_FALLBACK_CHAIN` in `core/providers/memory.py`. The current 5 patterns cover only 5/16 possible field wildcard combinations. Adding all 16 ensures any stored evidence can be matched regardless of context field differences.

2. **Fix B2 (optional)** — Add `await provider.cached_health()` call inside the async branch of `select()` in `core/providers/router.py` so the health cache is refreshed during selection.

3. **Re-run Phase 4** — Verify that after B1 fix, 3 identical tasks produce changing routing decisions.
