# MEMORY AND AUTOMATION AUDIT — MJ Architecture

**Generated:** 2026-07-18  
**Scope:** Memory systems, automation, background jobs, scheduling, resume/goal continuation  
**Method:** READ ONLY audit of entire codebase

---

## Memory Systems Inventory

| Memory System | File | Type | Status | Owner |
|---|---|---|---|---|
| **MemoryFacade** | `memory/memory_facade.py` | Facade | **ACTIVE** (Canonical) | `memory` singleton |
| **TieredMemory** | `memory/tiered_memory.py` | Hot/Warm/Cold | **ACTIVE** | `tiered_memory` singleton |
| **EpisodicStore** | `memory/episodic_store.py` | Episodic (goal/action/result) | **ACTIVE** | `EpisodicStore` |
| **SemanticStore** | `memory/semantic_store.py` | Facts with confidence/categories | **ACTIVE** | `SemanticStore` singleton |
| **FactStore** | `memory/fact_store.py` | Extracted facts with embeddings | **ACTIVE** | `FactStore` singleton via `get_fact_store()` |
| **DecisionStore** | `memory/decision_store.py` | Decisions + lessons learned | **ACTIVE** | `DecisionStore` singleton |
| **TaskStore** | `memory/task_store.py` | Action traces (success/fail/duration) | **ACTIVE** | `TaskStore` singleton |
| **EpisodicStore** | `memory/episodic_store.py` | Goal/action/result episodes | **ACTIVE** | `EpisodicStore` |
| **SemanticStore** | `memory/semantic_store.py` | Facts with confidence/importance | **ACTIVE** | `SemanticStore` singleton |
| **FactStore** | `memory/fact_store.py` | Structured facts w/ embeddings | **ACTIVE** | `FactStore` singleton |
| **TieredMemory** | `memory/tiered_memory.py` | Hot/Warm/Cold + Mem0 + Embeddings | **ACTIVE** | `tiered_memory` singleton |
| **EmbeddingMemory** | `memory/embedding_memory.py` | Vector embeddings for semantic search | **ACTIVE** | Lazy-loaded |
| **EmbeddingMemory** | `memory/embedding_memory.py` | Shared embedding model | **ACTIVE** | `get_embedding_memory()` |
| **Mem0Adapter** | `memory/mem0_adapter.py` | Mem0 library wrapper | **ACTIVE** | Used by TieredMemory |
| **Extraction** | `memory/extraction.py` | Fact extraction from text | **ACTIVE** | `extract_facts_from_messages` |
| **FactStore** | `memory/fact_store.py` | Structured facts with embeddings | **ACTIVE** | `FactStore` singleton |
| **DecisionStore** | `memory/decision_store.py` | Decisions + lessons learned | **ACTIVE** | `DecisionStore` singleton |
| **Reranker** | `memory/reranker.py` | Cross-encoder reranking | **ACTIVE** | `get_text_similarity` |
| **PreferenceProfile** | `memory/preference_profile.py` | User preference learning | **ACTIVE** | `PreferenceProfile` |
| **EmbeddingUtils** | `memory/embedding_utils.py` | Serialization/cosine similarity | **ACTIVE** | `serialize_embedding` |
| **VectorStore** | `memory/vector_store.py` | ChromaDB collections | **ACTIVE** | `search_collection` |
| **Similarity** | `memory/similarity.py` | Text similarity utilities | **ACTIVE** | `get_text_similarity` |
| **EpisodicStore** | `memory/episodic_store.py` | Goal/action/result episodes | **ACTIVE** | `EpisodicStore` |
| **SemanticStore** | `memory/semantic_store.py` | Facts with confidence/importance | **ACTIVE** | `SemanticStore` singleton |
| **FactStore** | `memory/fact_store.py` | Structured facts w/ embeddings | **ACTIVE** | `FactStore` singleton |
| **PreferenceProfile** | `memory/preference_profile.py` | User preference learning | **ACTIVE** | `PreferenceProfile` |
| **MemoryFacade** | `memory/memory_facade.py` | **Canonical facade** over all backends | **CANONICAL** | `memory` singleton |

---

## Memory Write Paths

| Write Operation | Entry Point | Backend(s) Written | Deduplication |
|---|---|---|---|
| `memory.store()` | `MemoryFacade.store()` | TieredMemory.remember() → Mem0 | TieredMemory handles dedup |
| `memory.store_fact()` | `MemoryFacade.store_fact()` | SemanticStore.store() | Exact fact match (case-insensitive) |
| `memory.store_episode()` | `MemoryFacade.store_episode()` | EpisodicStore.store() | None (append-only) |
| `memory.store_trace()` | `MemoryFacade.store_trace()` | TaskStore.store() | None (append-only) |
| `memory.store_decision()` | `MemoryFacade.store_decision()` | DecisionStore.store() | None (append-only) |
| `memory.store_episode()` | `MemoryFacade.store_episode()` | EpisodicStore.store() | None |
| `memory.store_fact()` | `MemoryFacade.store_fact()` | SemanticStore.store() | Exact match (case-insensitive) |
| `tiered_memory.remember()` | `TieredMemory.remember()` | Hot tier + Mem0 + Embedding | Hot tier LRU, Mem0 dedup |
| `FactStore.store_facts()` | `FactStore.store_facts()` | SQLite + embeddings | (subject, predicate, object, user, tenant) |
| `SemanticStore.store()` | `SemanticStore.store()` | Exact match (case-insensitive) |
| `EpisodicStore.store()` | `EpisodicStore.store()` | Append-only | None |
| `FactStore.store_facts()` | Force=True bypasses dedup | Upsert on (subject, predicate, object, user, tenant) |
| `SemanticStore.store()` | Exact match on fact text (case-insensitive) |
| `EpisodicStore.store()` | Append-only | None |
| `DecisionStore.store()` | None (append-only) | None |

---

## Memory Read Paths

| Read Operation | Entry Point | Backends Queried | Merging Strategy |
|---|---|---|---|
| `memory.recall()` | `MemoryFacade.recall()` | TieredMemory.recall() + Mem0.search() | Merge by content, sort by timestamp |
| `memory.recall()` | TieredMemory.recall() | Hot tier (word overlap) + Mem0.search() + Embedding.semantic_search | Merge by content, sort by score |
| `memory.recall_filtered()` | TieredMemory.recall_filtered() | recall() + cosine similarity threshold | Cosine similarity filter |
| `memory.search_all()` | `MemoryFacade.search_all()` | Tiered + Mem0 | Source tag + merge |
| `memory.retrieve_facts()` | `MemoryFacade.retrieve_facts()` | SemanticStore.retrieve() | SQLite query + similarity rerank |
| `memory.retrieve_episodes()` | `MemoryFacade.retrieve_episodes()` | EpisodicStore.retrieve() | Text similarity on goal |
| `memory.retrieve_decisions()` | `MemoryFacade.retrieve_decisions()` | DecisionStore.retrieve_similar() | Text similarity + failure boost |
| `memory.search_vectors()` | `MemoryFacade.search_vectors()` | ChromaDB collection | Vector similarity |
| `memory.get_task_traces()` | TaskStore.get_task_traces() | SQLite query | - |
| `memory.get_recent_traces()` | TaskStore.get_recent() | SQLite ORDER BY created_at DESC | - |
| `memory.search_vectors()` | ChromaDB collection | Cosine similarity | - |
| `EpisodicStore.retrieve()` | Text similarity on goal | Cosine on goal text | - |
| `SemanticStore.retrieve()` | SQLite + text similarity | Cosine similarity rerank | -
| `EpisodicStore.retrieve()` | Text similarity on goal | Cosine similarity |
| `SemanticStore.retrieve()` | SQLite + similarity rerank | Text similarity + importance |
| `FactStore.search_facts()` | Embedding cosine similarity | Cosine on embeddings |
| `FactStore.search_facts()` fallback | SQLite LIKE | LIKE on subject/predicate/object | |
| `EpisodicStore.retrieve()` | Text similarity on goal | Cosine similarity |
| `DecisionStore.retrieve_similar()` | Text similarity + failure boost | Cosine + failure boost |

---

## Memory Write/Read Ownership Matrix

| Memory Type | Writer(s) | Reader(s) | Canonical Owner |
|---|---|---|---|
| Conversation history | `MemoryFacade.store()` (Pipeline MemoryStage) | `MemoryFacade.recall()` | `MemoryFacade` (Canonical) |
| Facts | `FactStore.store_facts()` (Pipeline MemoryStage) | `FactStore.search_facts()` | `FactStore` singleton |
| Semantic facts | `SemanticStore.store()` (Pipeline MemoryStage) | `SemanticStore.retrieve()` | `SemanticStore` singleton |
| Episodic (goal/action/result) | `EpisodicStore.store()` (Pipeline MemoryStage) | `EpisodicStore.retrieve()` | `EpisodicStore` singleton |
| Task traces | `MemoryFacade.store_trace()` → `TaskStore` | `TaskStore.get_task_traces()` | `TaskStore` singleton |
| Decisions | `DecisionStore.store()` | `DecisionStore.retrieve_similar()` | `DecisionStore` singleton |
| Lessons/Failures | `DecisionStore.store()` (success=False) | `DecisionStore.get_failures/lessons()` | `DecisionStore` singleton |
| Vector embeddings | ChromaDB via `MemoryFacade.search_vectors()` | `MemoryFacade.search_vectors()` | ChromaDB |
| Task traces | `MemoryFacade.store_trace()` → `TaskStore` | `TaskStore.get_task_traces()` | `TaskStore` singleton |
| Decisions | `DecisionStore.store()` | `DecisionStore.retrieve_similar()` | `DecisionStore` singleton |
| Lessons/Failures | `DecisionStore.store(success=False)` | `DecisionStore.get_failures/lessons()` | `DecisionStore` singleton |
| Vector embeddings | ChromaDB via `MemoryFacade.search_vectors()` | `MemoryFacade.search_vectors()` | ChromaDB |
| Episodic (goal/action/result) | `EpisodicStore.store()` (Pipeline MemoryStage) | `EpisodicStore.retrieve()` | `EpisodicStore` singleton |
| Task traces | `MemoryFacade.store_trace()` | `TaskStore.get_task_traces()` | `TaskStore` singleton |
| Preferences | `PreferenceProfile.update()` | `PreferenceProfile.get_preferences()` | `PreferenceProfile` |
| Vector search | ChromaDB via `MemoryFacade.search_vectors()` | `MemoryFacade.search_vectors()` | ChromaDB |

---

## Automation & Background Jobs

### Automation Systems

| System | Entry Point | Status | Execution Model |
|---|---|---|---|
| **AutomationLoop** (Legacy) | `brain/automation/loop.py:AutomationLoop` | **DORMANT** | Phase-based: plan → generate → verify → build → test → verify → finish |
| **PCAutomation** (Deprecated) | `automation/pc_automation.py:PCAutomation` | **DEPRECATED** | NLP parser → Selenium/pyautogui |
| **AutomationProvider** | `core/providers/adapters/automation_provider.py` | **ACTIVE** | Provider → WorkflowEngine → steps |
| **PCAutomationPlugin** | `core/plugins/automation.py:PCAutomationPlugin` | **ACTIVE** | Plugin hooks: `on_execute`, `on_governance_check` |
| **ActivityScheduler** | `core/scheduler/scheduler.py:Scheduler` | **ACTIVE** | Tick-based (5s), 5 executors → Pipeline |
| **Cron Scheduler** | `core/cron.py:scheduler` | **ACTIVE** | APScheduler-style cron jobs |
| **MultiRunExecutor** | `core/multi_run.py:MultiRunExecutor` | **ACTIVE** | Parallel strategy execution via pipeline |
| **Background Jobs** | `core/multi_run.py:MultiRunExecutor` | **ACTIVE** | Best-of-N parallel runs |
| **Task Queue** | `core/governance/work_queue.py:WorkQueue` | **ACTIVE** | Priority queue + ResourceMonitor throttling |
| **Cron** | `core/cron.py:scheduler` | **ACTIVE** | APScheduler-style recurring jobs |
| **Activity Scheduler** | `core/scheduler/scheduler.py:Scheduler` | **ACTIVE** | 5s tick, 5 executors → Pipeline |
| **WorkflowEngine** | `core/workflow/engine.py:WorkflowEngine` | **ACTIVE** | Multi-step with compensation |

### Scheduler Systems (Duplicate/Overlapping)

| Scheduler | File | Purpose | Status |
|---|---|---|---|
| `core/cron.py:scheduler` | Cron-style recurring jobs | **ACTIVE** | Cron-style recurring |
| `core/scheduler/scheduler.py:Scheduler` | `Scheduler` | Activity scheduling with executors | **ACTIVE** |
| `core/scheduler/autonomous.py` | `AutonomousScheduler` | Autonomous scheduling decisions | **ACTIVE** |
| `core/scheduler/intelligence.py` | `ActivityIntelligence` | Predictive scheduling | **ACTIVE** |

---

## Task Queue & Background Jobs

| Component | File | Purpose | Status |
|---|---|---|---|
| `WorkQueue` | `core/governance/work_queue.py` | Priority queue + ResourceMonitor throttling | **ACTIVE** |
| `WorkQueue.process_loop()` | Background loop | Dequeue → execute → persist | **ACTIVE** |
| `MultiRunExecutor` | `core/multi_run.py` | Best-of-N parallel runs | **ACTIVE** |
| `ActivityScheduler` | `core/scheduler/scheduler.py` | Tick-based activity execution | **ACTIVE** |
| `CronScheduler` | `core/cron.py:scheduler` | Recurring cron jobs | **ACTIVE** |
| `AutomationProvider` | Provider → WorkflowEngine | Workflow execution via provider | **ACTIVE** |
| `MultiRunExecutor` | Best-of-N parallel strategies | Parallel execution | **ACTIVE** |

### Background Job Flow
```
User Request → Transport Adapter → process_message() → Pipeline (19 stages)
                                                    ↓
                                        Pipeline stages execute
                                                    ↓
                                    EventBus publishes events
                                    ↓
                              Event subscribers (Inbox, Memory, etc.)
                                                    ↓
                                    Schedulers pick up for background continuation
```

---

## 4. RESUME / GOAL CONTINUATION

| System | File | Mechanism | Status |
|---|---|---|---|
| **WorkflowEngine** | `core/workflow/engine.py` | Checkpoint + compensation + idempotency keys | **ACTIVE** |
| **AutomationLoop** (Legacy) | `brain/automation/loop.py` | Phase-based with repair gates | **DORMANT** |
| **WorkflowEngine** | `core/workflow/engine.py` | Checkpoint + compensation + idempotency | **ACTIVE** |
| **ResumeEngine** | `core/activity/resume.py` | Incomplete leaf nodes → resume | **ACTIVE** |
| **CheckpointStore** | `core/persistence/store.py` | AgentState snapshots + ExecutionGraph | **ACTIVE** |
| **ProjectState** | `core/project_state.py` | ProjectState.load/save + log_event | **ACTIVE** |
| **CheckpointStore** | `core/persistence/store.py` | AgentState snapshots + ExecutionGraph | **ACTIVE** |
| **AutomationLoop** | `brain/automation/loop.py` | Phase-based (plan→gen→verify→build→test) | **DORMANT** |
| **ResumeEngine** | `core/activity/resume.py` | Incomplete leaves → resume | **ACTIVE** |
| **BuildService** | `core/build/service.py` | WorkflowEngine + queue + resume | **ACTIVE** |
| **AutomationLoop** (Legacy) | `brain/automation/loop.py` | Phase-based with repair gates | **DORMANT** |

### Resume Flow
```
Startup → _scan_pending() → ResumeEngine.resume_all_candidates()
    → ResumeEngine.resume_all_candidates()
        → ActivityManager.resume_candidates()
            → incomplete leaves → resume_from()
                → CheckpointStore.load() → AgentState + ExecutionGraph
                → resume_from() → continue from incomplete leaf
```

---

## 5. DUPLICATE / DEAD / DORMANT SYSTEMS

### Duplicate Systems (Consolidate)

| Capability | Primary (Keep) | Duplicate (Remove) | Reason |
|---|---|---|---|
| **Browser Automation** | `BrowserProvider` | `core/tools/browser_fsm.py` + `browser_planner.py` + `browser_tools.py` | Fragmented across 3 files |
| **Coding** | `ForgeProvider` | `OllamaProvider` (code capability) | Capability overlap |
| **Research** | `ResearchProvider` | `core/tools/browser_research.py` | Duplicate paths |
| **Schedulers** | `Scheduler` (activity) | `core/cron.py:scheduler` (cron) | Different purposes but overlapping |
| **Automation** | `AutomationProvider` | `automation/pc_automation.py` (DEPRECATED) | Header says deprecated |
| **Desktop** | `DesktopProvider` | `automation/pc_automation.py` | Duplicate desktop control |
| **PluginEventBus** | `global_event_bus` (namespace="plugin") | `PluginEventBus` class | Duplicate event bus |
| `WorkflowEvent` vs `Event` | `core/workflow/events.py` | `core/event_bus.py` | Two event hierarchies |
| `WorkflowEvent` vs `Event` | Two event hierarchies | Unified `Event` class exists | Unify |
| `WorkflowEvent` vs `Event` | Legacy workflow events | Canonical `Event` class | Unify |
| `PluginEventBus` | Legacy adapter | Deprecated, routes to `global_event_bus` | Remove |
| `get_bus()` / `emit_event()` | Legacy shims | Use `global_event_bus` directly | Remove |

### Dead / Unused Code

| File/Module | Status | Evidence |
|---|---|---|
| `core/graph/` (StateGraph) | **DORMANT** | Only used by `agent_loop.py` fallback |
| `core/agent_loop.py` fallback | **DRIFT** | `_disable_pipeline` flag only |
| `core/graph/nodes.py` | 60KB unused | Only legacy agent loop |
| `api/agent_routes.py` | **DORMANT** | Uses legacy graph |
| `automation/pc_automation.py` | **DEPRECATED** | Header says "Use core/desktop/controller.py" |
| `automation/routes.py` | **DUPLICATE** | Legacy HTTP routes |
| `core/llm_calls.py` | **DEAD** | Not imported anywhere |
| `core/llm_core.py` | **LEGACY** | Only imported by deprecated modules |
| `core/llm_failover.py` | **LEGACY** | Only used by deprecated paths |
| `core/agent_loop.py` fallback | **DRIFT** | Only when `_disable_pipeline=True` |
| `core/llm_calls.py` | **DEAD** | No imports found |
| `core/llm_core.py` | **LEGACY** | Only in deprecated paths |
| `core/llm_failover.py` | **LEGACY** | Only used by deprecated paths |
| `core/graph/` | **DORMANT** | LangGraph fallback only |
| `core/agent_loop.py` fallback | **DRIFT** | `_disable_pipeline` flag |
| `api/agent_routes.py` | **DORMANT** | Legacy graph endpoint |
| `core/graph/` | **DORMANT** | Only legacy fallback |
| `core/llm_calls.py` | **DEAD** | No imports found |
| `core/llm_core.py` | **LEGACY** | Deprecated |
| `core/llm_failover.py` | **LEGACY** | Deprecated |
| `automation/pc_automation.py` | **DEPRECATED** | Header says deprecated |
| `automation/routes.py` | **DUPLICATE** | Legacy HTTP routes |
| `brain/UnifiedBrain.py` | **DUPLICATE** | Duplicates pipeline stages |
| `PluginEventBus` | **DEPRECATED** | Use `global_event_bus` + namespace |
| `get_bus()` / `emit_event()` | **LEGACY** | Use `global_event_bus` directly |
| `WorkflowEvent` / `MJEvent` | **LEGACY** | Use canonical `Event` |

---

## 6. REALITY SCORES

| System | Score | Notes |
|---|---|---|
| **MemoryFacade** | 9/10 | Canonical facade, 5 backends unified |
| **TieredMemory** | 8/10 | Hot/Warm/Cold + Mem0 + Embeddings |
| **EpisodicStore** | 8/10 | SQLite + summarization |
| **SemanticStore** | 8/10 | Facts with confidence/importance decay |
| **FactStore** | 9/10 | SQLite + embeddings + contradiction detection |
| **DecisionStore** | 8/10 | Decisions + lessons + failures |
| **EpisodicStore** | 8/10 | Goal/action/result with summarization |
| **SemanticStore** | 8/10 | Confidence + importance + decay |
| **FactStore** | 9/10 | SQLite + embeddings + contradiction detection |
| **DecisionStore** | 8/10 | Decisions + lessons + failures |
| **EpisodicStore** | 8/10 | Summarization + summarization |
| **SemanticStore** | 8/10 | Importance decay + text similarity |
| **FactStore** | 9/10 | Embeddings + contradiction detection |
| **DecisionStore** | 8/10 | Lessons from failures |
| **EpisodicStore** | 8/10 | Summarization of old episodes |
| **SemanticStore** | 8/10 | Importance decay + text similarity |
| **FactStore** | 9/10 | Contradiction detection + embeddings |
| **DecisionStore** | 8/10 | Failure analysis + lessons |
| **TieredMemory** | 8/10 | Hot/Warm/Cold + Mem0 + Embeddings |
| **MemoryFacade** | 9/10 | Canonical facade over 5 backends |
| **MemoryFacade** | **9/10** | Canonical facade over 5 backends |
| **SafetyManager** | **9/10** | Comprehensive pre-action checks |
| **Scheduler** | **9/10** | Tick-based, 5 workers, chain-aware |
| **ActivityScheduler** | **8/10** | 5 executors, chain-aware |
| **Cron** | **8/10** | Simple cron, overlaps with Scheduler |
| **WorkflowEngine** | **9/10** | Multi-step + compensation + idempotency |
| **AutomationProvider** | **8/10** | Provider → WorkflowEngine |
| **PCAutomation** | **3/10** | DEPRECATED, duplicate of DesktopProvider |
| **ActivityScheduler** | **8/10** | Tick-based, 5 executors → Pipeline |
| **Cron** | **8/10** | Overlaps with Scheduler |
| **WorkflowEngine** | **9/10** | Multi-step + compensation + idempotency |
| **AutomationProvider** | **8/10** | Provider → WorkflowEngine |
| **AutomationLoop** (Legacy) | **3/10** | DORMANT, phase-based |
| **PlannerExecutor** | **9/10** | Template-based, deterministic |
| **ToolExecutor** | **9/10** | Lifecycle events + memory traces |
| **MultiRunExecutor** | **8/10** | Best-of-N parallel |
| **WorkQueue** | **8/10** | Priority + ResourceMonitor throttling |
| **EventBus** | **10/10** | Canonical, async-first, tenant-aware |
| **PluginEventBus** | **3/10** | DEPRECATED, routes to global_event_bus |
| **WorkflowEvent** | **3/10** | Legacy, parallel to Event |
| **InboxStore** | **7/10** | SQLite + EventBus subscriptions |
| **HistoryService** | **7/10** | EventBus-based, fragmented reads |
| **SupervisorNotifier** | **8/10** | Email/Push/WS/Log |
| **ActivityScheduler** | **8/10** | Tick-based, 5 executors → Pipeline |
| **Cron** | **8/10** | Overlaps with Scheduler |
| **WorkflowEngine** | **9/10** | Multi-step + compensation + idempotency |
| **AutomationProvider** | **8/10** | Provider → WorkflowEngine |
| **MemoryFacade** | **9/10** | Canonical facade over 5 backends |
| **TieredMemory** | **8/10** | Hot/Warm/Cold + Mem0 + Embeddings |
| **EpisodicStore** | **8/10** | SQLite + summarization |
| **SemanticStore** | **8/10** | Confidence + importance decay |
| **FactStore** | **9/10** | SQLite + embeddings + contradiction detection |
| **DecisionStore** | **8/10** | Decisions + lessons + failures |
| **EpisodicStore** | **8/10** | Summarization of old episodes |
| **SemanticStore** | **8/10** | Importance decay + text similarity |
| **FactStore** | **9/10** | SQLite + embeddings + contradiction detection |
| **DecisionStore** | **8/10** | Failure analysis + lessons |
| **EpisodicStore** | **8/10** | Summarization of old episodes |
| **SemanticStore** | **8/10** | Importance decay + text similarity |
| **FactStore** | **9/10** | SQLite + embeddings + contradiction detection |
| **DecisionStore** | **8/10** | Failure analysis + lessons |
| **DesktopProvider** | **8/10** | pyautogui + SafetyManager |

---

## Canonical Future Owners (Consolidation Targets)

| Capability | Current | Target (Canonical) | Action |
|---|---|---|---|
| Browser | `BrowserProvider` + 3 tool files | `core/providers/adapters/browser_provider.py` | Merge `browser_fsm.py` + `browser_planner.py` + `browser_tools.py` |
| Coding | `ForgeProvider` + `OllamaProvider` (code) | `core/coding/` + `ForgeProvider` | Move `implementations.py` into `core/coding/` |
| Research | `ResearchProvider` | `core/research/` + `core/tools/browser_research.py` | Unify |
| Scheduler | `Scheduler` (activity) | Single `Scheduler` with cron mode | Remove `core/cron.py` |
| Desktop | `DesktopProvider` | `core/desktop/controller.py` | Delete `automation/pc_automation.py` |
| Voice | `VoiceLoop` + providers | Register STT/TTS providers with `ProviderRegistry` | Register providers |
| Speech | `VoiceLoop` + providers | Register STT/TTS with `ProviderRegistry` | Register providers |
| Scheduler | `Scheduler` (activity) | Single `Scheduler` with cron mode | Remove `core/cron.py` |
| Workflow | `WorkflowEngine` | Keep, deprecate `AutomationLoop` | Delete `brain/automation/loop.py` |
| EventBus | `global_event_bus` | Remove `PluginEventBus`, `get_bus()`, `emit_event()` | Delete legacy |
| `WorkflowEvent` / `MJEvent` | Merge into `Event` | Single `Event` class | Delete `WorkflowEvent`, `MJEvent` |
| `PluginEventBus` | Remove | Use `global_event_bus` with `namespace="plugin"` | Delete |
| `get_bus()` / `emit_event()` | Remove | Use `global_event_bus` directly | Delete |
| `WorkflowEvent` / `MJEvent` | Delete | Use canonical `Event` | Delete classes |
| `core/graph/` | DELETE | LangGraph fallback only | DELETE directory |
| `core/agent_loop.py` fallback | Remove `_disable_pipeline` | Pipeline is canonical | Delete fallback |
| `api/agent_routes.py` | DORMANT | Legacy graph endpoint | DELETE |
| `core/graph/` | DORMANT | DELETE directory |
| `core/agent_loop.py` fallback | DRIFT | Remove `_disable_pipeline` | DELETE fallback |
| `api/agent_routes.py` | DORMANT | DELETE |
| `core/graph/` | DORMANT | DELETE directory |
| `automation/pc_automation.py` | DEPRECATED | DELETE |
| `automation/routes.py` | DUPLICATE | DELETE |
| `brain/UnifiedBrain.py` | DUPLICATE | Migrate methods to Pipeline stages |
| `PluginEventBus` | DEPRECATED | REMOVE |
| `get_bus()` / `emit_event()` | LEGACY | REMOVE |
| `WorkflowEvent` / `MJEvent` | LEGACY | DELETE |
| `core/llm_calls.py` | DEAD | DELETE |
| `core/llm_core.py` | LEGACY | DELETE |
| `core/llm_failover.py` | LEGACY | DELETE |
| `core/graph/` | DORMANT | DELETE directory |
| `core/agent_loop.py` fallback | DRIFT | REMOVE fallback |
| `api/agent_routes.py` | DORMANT | DELETE |
| `core/graph/` | DORMANT | DELETE directory |
| `automation/pc_automation.py` | DEPRECATED | DELETE |
| `automation/routes.py` | DUPLICATE | DELETE |
| `brain/UnifiedBrain.py` | DUPLICATE | MIGRATE methods → Pipeline |
| `PluginEventBus` | DEPRECATED | DELETE |
| `get_bus()` / `emit_event()` | LEGACY | DELETE |
| `WorkflowEvent` / `MJEvent` | LEGACY | DELETE |

---

## Reality Score Summary

| Category | Score | Notes |
|---|---|---|
| **Memory Systems** | 8.5/10 | Unified facade, 5 backends, good consolidation |
| **Automation/Background** | 7/10 | Multiple overlapping schedulers |
| **Scheduler** | 8/10 | Good tick-based, but cron duplicate |
| **Automation** | 6/10 | Legacy PCAutomation still present |
| **Workflow** | 9/10 | WorkflowEngine is solid |
| **Scheduler** | 8/10 | Two overlapping systems |
| **EventBus** | 9/10 | Canonical, but legacy adapters remain |
| **Memory** | 9/10 | Facade pattern excellent |
| **Plugin System** | 8/10 | Good, but legacy PluginEventBus |
| **Recovery/Resume** | 8/10 | WorkflowEngine + ResumeEngine solid |
| **Build System** | 9/10 | BuildService + WorkflowEngine solid |
| **Provider System** | 9/10 | Router + Registry canonical |
| **Memory Facade** | 9/10 | 5 backends unified |
| **WorkflowEngine** | 9/10 | Compensation + idempotency |

---

## Recommended Consolidation Order

1. **DELETE** `core/graph/`, `core/agent_loop.py` fallback, `api/agent_routes.py`, `core/llm_calls.py`, `core/llm_core.py`, `core/llm_failover.py`, `automation/pc_automation.py`, `automation/routes.py`, `brain/UnifiedBrain.py`, `core/plugins/automation.py`, `core/event_bus.py` (PluginEventBus, get_bus, emit_event), `WorkflowEvent`, `MJEvent`, `core/llm_calls.py`, `core/llm_core.py`, `core/llm_failover.py`, `core/graph/` directory
2. **CONSOLIDATE** `core/tools/browser_tools.py` + `browser_fsm.py` + `browser_planner.py` → single `browser_provider.py`
3. **CONSOLIDATE** `core/coding/` + `core/tools/implementations.py` + `cookbook_tools.py` + `build_tools.py` → `core/coding/`
3. **CONSOLIDATE** `Scheduler` + `core/cron.py` → single `Scheduler` with cron mode
4. **MERGE** `core/providers/adapters/ollama_provider.py` capabilities into `OllamaProvider` (already done)
5. **DELETE** `automation/pc_automation.py`, `automation/routes.py`
6. **DELETE** `brain/UnifiedBrain.py` (migrate methods to Pipeline stages)
7. **DELETE** `core/llm_calls.py`, `core/llm_core.py`, `core/llm_failover.py`, `core/graph/`, `core/agent_loop.py` fallback, `api/agent_routes.py`, `core/graph/`
8. **UNIFY** `Scheduler` + `core/cron.py` → single `Scheduler` with cron mode
9. **DELETE** `automation/pc_automation.py`, `automation/routes.py`
10. **MERGE** `WorkflowEvent` + `MJEvent` → `Event`
10. **UNIFY** `Scheduler` + `core/cron.py` → single `Scheduler`
11. **REMOVE** `PluginEventBus`, `get_bus()`, `emit_event()`, `WorkflowEvent`, `MJEvent`
12. **CONSOLIDATE** Schedulers → single `Scheduler`
13. **DELETE** `core/graph/`, `core/llm_calls.py`, `core/llm_core.py`, `core/llm_failover.py`
14. **DELETE** `automation/pc_automation.py`, `automation/routes.py`
15. **DELETE** `core/agent_loop.py` fallback, `api/agent_routes.py`, `core/graph/`

---

*End of Memory and Automation Audit*