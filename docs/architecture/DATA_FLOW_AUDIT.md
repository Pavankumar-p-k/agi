# Data Flow Audit — Phase 5 (Document 11)

> **Purpose:** Trace every major data transformation across the system — who creates data, who mutates it, where copies occur, where serialization happens, and where data can diverge between stores.
>
> **Scope:** All data flows through chat/conversation, goal/plan, memory, config, and auth paths.

---

## Table of Contents

1. [Chat/Conversation Data Flow](#1-chatconversation-data-flow)
2. [Goal/Plan Data Flow](#2-goalplan-data-flow)
3. [Memory Data Flow](#3-memory-data-flow)
4. [Configuration Data Flow](#4-configuration-data-flow)
5. [Auth Data Flow](#5-auth-data-flow)
6. [Deep Copy vs Reference Map](#6-deep-copy-vs-reference-map)
7. [Serialization Boundaries](#7-serialization-boundaries)
8. [Data Divergence Risks](#8-data-divergence-risks)
9. [Findings & Recommendations](#9-findings--recommendations)

---

## 1. Chat/Conversation Data Flow

### Full Transformation Chain

```
HTTP Request (raw bytes)
  │  DESERIALIZATION: FastAPI parses JSON body → Request dataclass
  ▼
Request (dataclass):
  text: str, transport: str, user_id: str|None, session_id: str|None,
  identity: IdentityContext|None, attachments: list[dict], metadata: dict
  │
  │  SHALLOW COPY: dict(request.metadata), list(request.attachments)
  ▼
PipelineContext (dataclass, mutable, ~35 fields):
  raw_input: str           ← request.text (str copy)
  transport: str           ← request.transport (str copy)
  user_id: str|None        ← request.user_id (str copy)
  session_id: str|None     ← request.session_id (str copy)
  metadata: dict           ← SHALLOW COPY of request.metadata
  attachments: list[dict]  ← NEW list, SAME dict refs
  identity: IdentityContext ← NEW from IdentityService.create_context()
  resource_scope: ResourceScope ← NEW from identity
  services: DeterministicServices ← NEW instance
  trace_id: str            ← request_id
  │
  ├── Stage 2a: ReceiveStage
  │     parses_request: dict ← raw_input (str ref)
  │
  ├── Stage 2b: LoadContextStage
  │     metadata.setdefault("transport", transport)  ← mutates existing dict
  │
  ├── Stage 2c-2f: Auth/Identity stages
  │     identity: IdentityContext ← REPLACED with authenticated version (shares agent, tenant refs)
  │     resource_scope: ResourceScope ← REPLACED with resolved tenant
  │
  ├── Stage 2i: ContextRetrievalStage
  │     retrieved_context: dict ← NEW dict with memories list, formatted_context str
  │
  ├── Stage 2j: ReasonerStage
  │     reasoning_assessment: dict ← NEW dict from keyword rules
  │
  ├── Stage 2k: PlannerStage
  │     plan: dict ← NEW dict with goal (raw_input[:200]), steps list
  │
  ├── Stage 2n: ExecutionStage
  │     execution_result: dict ← from LLM provider
  │     outcome: Outcome (frozen) ← NEW
  │     execution_state: str ← "completed"|"failed"
  │
  ├── Stage 2q: MemoryStage
  │     messages: list ← NEW [{"role":"user","content":raw_input}, {"role":"assistant","content":output}]
  │     memory_refs: list[str] ← from MemoryFacade + FactStore
  │     store_decision: StoreDecision ← NEW
  │
  └── Stage 2s: FormatterStage
        formatted_response: dict ← NEW with text, data, epistemic tags
  │
  │  Response assembly: NEW Response dataclass from formatted_response + metadata
  ▼
Response (dataclass): text, error, data, metadata
  │
  │  SERIALIZATION: FastAPI → JSON response body
  ▼
HTTP Response (JSON bytes)
```

### Data Origins by Field

| Field | Created By | Mutated By | Final Reader |
|-------|-----------|------------|-------------|
| `raw_input` | process_message() | Never mutated | All stages read-only |
| `identity` | IdentityService | AuthenticationStage (replace) | AuthZ, ResourceAccess stages |
| `metadata` | process_message() | LoadContext (+ auth tokens) | Auth, ResourceAccess stages |
| `plan` | PlannerStage | Never mutated | CapabilitySelection, Execution |
| `execution_result` | ExecutionStage | Never mutated | MemoryStage, FormatterStage |
| `memory_refs` | MemoryStage | Never mutated | FormatterStage |
| `retrieved_context` | ContextRetrievalStage | Never mutated | ReasonerStage only |

---

## 2. Goal/Plan Data Flow

### Full Transformation Chain

```
User Goal (natural language str)
  │
  │  GoalDecomposer.decompose() — keyword heuristics, no LLM
  ▼
SubGoal (recursive tree dataclass):
  id, description, template_id, step_name, agent_id,
  children: list[SubGoal], parameters: dict, status: str
  │
  │  _subgoal_to_dict(sg) — recursive dict converter
  │  ADDS: title=description[:80], estimated_duration=None, priority=0
  ▼
Dict tree:
  {id, title, description, assigned_agent, estimated_duration, priority, status, children:[...]}
  │
  │  json.dumps(node) — SERIALIZATION BOUNDARY
  ▼
JSON string
  │
  │  SQLite INSERT INTO plans (root_node)
  ▼
SQLite storage
  │
  │  PlanStore.get() → json.loads() → dict — DESERIALIZATION BOUNDARY
  ▼
Dict tree (back in memory)
  │
  │  PlannerExecutor transforms to StepDefinition list
  ▼
list[StepDefinition]:
  [{tool_name, input_data, timeout_seconds, max_retries, compensation_tool, compensation_data}]
  │
  │  WorkflowEngine.start_workflow() → NEW WorkflowStep + WorkflowInstance
  │  ADDS: step_id, idempotency_key, status=PENDING, retry_count=0, timestamps
  ▼
WorkflowInstance (dataclass, ~20 fields):
  workflow_id, workflow_type, status=PENDING, steps=[WorkflowStep, ...], ...
  │
  │  WorkflowStore.create_workflow() — SERIALIZATION BOUNDARY
  ▼
SQLite: workflow_instances + workflow_steps (multi-table INSERT)
  │
  │  _execute_step() — step.input_data → json.dumps() → ToolBlock.content
  ▼
ToolBlock (dataclass): tool_type, content=json_str
  │
  │  execute_tool_block() — TOOL EXECUTION
  ▼
(result dict): {exit_code, error, output, _artifacts}
  │
  │  step.output_data = result (DICT REFERENCE COPY)
  │  wf.current_step += 1
  ▼
WorkflowStore.update_step() — SERIALIZATION BOUNDARY
```

### Data Added at Each Transformation

| Stage | New Data | Data Loss |
|-------|----------|-----------|
| GoalDecomposer → SubGoal | id (UUID), children (tree structure) | None (pure enrichment) |
| SubGoal → Dict | title truncated to 80 chars, estimated_duration=None, priority=0 | description is preserved in parallel field |
| Dict → JSON string | JSON structure | Python types → strings |
| SQLite → Dict | None | None (round-trip) |
| Dict → StepDefinition | tool_name, input_data from plan steps | SubGoal tree structure lost |
| StepDefinition → WorkflowStep | step_id, idempotency_key, status, retry_count, timestamps | StepDefinition is consumed |
| WorkflowStep → ToolBlock | json.dumps(input_data) | dict → JSON string |
| ToolBlock → result | exit_code, error, output, artifacts | ToolBlock consumed |

---

## 3. Memory Data Flow

### 3.1 Store Path (Conversation → Facts)

```
Pipeline Stage 17: MemoryStage
  │
  ├──) MemoryFacade.store([user_msg, assistant_msg], user_id)
  │     │
  │     └──) TieredMemory.remember(assistant_content, metadata, user_id)
  │           │
  │           ├── Hot tier: {"content": str, "timestamp": float, "metadata": dict}
  │           │             (max 10, FIFO, volatile)
  │           │
  │           ├── Mem0: mem0.add(content, user_id, metadata)
  │           │         (vector embedding → Qdrant/ChromaDB, persistent)
  │           │
  │           └── Semantic: EmbeddingMemory.store(content, metadata)
  │                         (if importance > 0.8)
  │                         → Ollama embed → np.array → .tobytes() → SQLite BLOB
  │
  └──) extract_facts_from_messages([user_msg, assistant_msg], ...)
        │
        └── For each message:
              For each of 16 regex patterns:
                → ExtractedFact (frozen dataclass, 16 fields)
                  subject, predicate, object, confidence, category,
                  source_text, user_id, activity_id, conversation_id,
                  source_message, created_at, ...
        │
        └──) FactStore.store_facts([ExtractedFact], user_id)
              │
              └── For each fact:
                    dedup by (LOWER(s,p,o), user_id, tenant_id)
                    → Embedding: Ollama → np.array → struct.pack() → BLOB
                    → SQLite INSERT INTO facts (19 columns)
```

### 3.2 Recall Path (Query → Memories)

```
Pipeline Stage 9: ContextRetrievalStage
  │
  └──) MemoryFacade.recall(query, limit=5, user_id)
        │
        ├── TieredMemory.recall():
        │     ├── Hot tier: word overlap ≥ 30% → content strings
        │     └── Mem0: vector search → memory dicts
        │     └── Semantic: brute-force cosine similarity → text entries
        │
        └── Merge results → dedup by (memory|text|content) → sort by timestamp → limit
  │
  └──) ReRanker.rerank(query, items, user_preferences)
        scores = 0.5*similarity + 0.3*recency + 0.1*confidence + 0.1*preference
  │
  └──) PreferenceProfile.build() from FactStore (category=preference)
  │
  └──) format_context(memories) → LLM-readable str
```

### 3.3 Embedding Serialization (Key Detail)

Writing:
```
Text → Ollama /api/embed → {"embeddings": [[f1, f2, ..., fn]]}
     → np.array(embedding, dtype=np.float32)
     → struct.pack(f"{len(embedding)}f", *embedding)  → bytes BLOB
     → SQLite BLOB column
```

Reading:
```
SQLite BLOB → struct.unpack(f"{N}f", blob) → list[float]
     → np.array(embedding, dtype=np.float32)
     → cosine similarity with query embedding
     → sorted results
```

**Two separate implementations** do this:
1. `memory/fact_store.py:_serialize_embedding()` / `_deserialize_embedding()` — struct-based
2. `memory/embedding_memory.py` — uses `.tobytes()` / `np.frombuffer()`

These are **incompatible** — data written by one cannot be read by the other.

---

## 4. Configuration Data Flow

### Full Resolution Chain

```
configuration.get("server.port")
  │
  │  1. In-memory overrides     ← configuration.set() at runtime
  │  2. Environment cache       ← scanned from _REGISTRY env_vars
  │  3. Flat config             ← config.yaml + data/settings.json
  │  4. SettingsStore           ← ~/.jarvis/settings.json (Pydantic)
  │  5. Auto-resolve capability  ← model routing logic
  │  6. Registry default         ← _REGISTRY_MAP["server.port"].default → 8000
  │  7. Caller default           ← None
  ▼
coerced value (str → int via ConfigEntry.type)
```

### Data Transformations

| Stage | Input | Output | Transformation |
|-------|-------|--------|---------------|
| `.env` file | `KEY=VALUE\n` | os.environ dict | dotenv parses text |
| `config.yaml` | YAML text | nested dict | yaml.safe_load() |
| `_scan_env_vars()` | os.environ | flat _env_cache dict | iterates _REGISTRY, reads by env_var name |
| `_load_yaml()` | nested dict | flat _flat_config dict | _flatten(dot.notation) |
| ConfigEntry type coercion | str | int/float/bool/list | Casting per type field |
| SettingsStore | JSON file | Pydantic BaseModel | model_validate() |
| `configuration.get()` | raw value | coerced value | Type coercion from ConfigEntry.type |
| `configuration.set()` | coerced value | JSON-serialized | json.dump() to settings.json |

---

## 5. Auth Data Flow

### Session Creation

```
Login Request: POST /auth/login {username, password}
  │
  │  bcrypt.checkpw(password.encode(), stored_hash) — VERIFICATION
  ▼
secrets.token_hex(32)  → token (64-char hex string)
  │
  │  SHALLOW COPY of _sessions dict
  │  NEW entry: _sessions[token] = {"username": username, "expiry": now + 7d}
  ▼
json.dump(snapshot) → sessions.json — SERIALIZATION
```

### Token Validation

```
Request: Authorization: Bearer <token>
  │
  │  AuthManager.validate_token(token)
  │    → _sessions[token] lookup (DICT ACCESS)
  │    → time.time() > session["expiry"] check
  │    → session["username"] in self.users check
  │    → if invalid: pop from _sessions, save, return False
  ▼
AuthManager.get_username_for_token(token) → "username"
  │
  │  _get_or_create_user(db, uid="username") → SQLAlchemy User ORM
  ▼
get_auth_context(user, request) → AuthContext:
  user_id=user.uid, roles={Role.GUEST, +ADMIN if admin, +DEVELOPER if known},
  scopes=set() → filled by resolve_context(),
  ip_address=request.client.host,
  session_id=request.cookies.get("session_token")
```

### Identity Propagation through Pipeline

```
process_message():
  → IdentityService.create_context(user_id=request.user_id)
    → IdentityContext(user=UserIdentity(id=user_id), tenant=TenantIdentity(), ...)
    → authentication_state = IDENTIFIED | ANONYMOUS
  → PipelineContext.identity = identity

AuthenticationStage:
  → if token valid: REPLACE IdentityContext
    → new IdentityContext(user=UserIdentity(id=username),
                          session=SessionIdentity(id=token),
                          agent=SHARED from old identity,
                          tenant=SHARED from old identity,
                          authentication_state=AUTHENTICATED)

AuthorizationStage:
  → reads identity.user.id (str ref)
  → builds AuthContext (different class from IdentityContext!)
  → authz_engine.evaluate(authz_ctx, scope)
```

---

## 6. Deep Copy vs Reference Map

| Location | What is copied | Copy Type | Why It Matters |
|----------|---------------|-----------|----------------|
| `pipeline.py:96` | `dict(request.metadata)` | Shallow | Shared dict refs between request and context |
| `pipeline.py:97` | `list(request.attachments)` | New list, same dicts | Mutations to attachment dicts affect both |
| `session.py:137` | `[dict(m) for m in self.messages]` | Deep (per message dict) | Only deep copy in conversation path |
| `context_retrieval.py` | memory recall result list | Reference | Memory items not isolated per-use |
| `execution.py:103` | `list(self._step_results)` | New list, same dicts | Results shared across stages |
| `auth.py:199` | `dict(self._sessions)` | Shallow | _save_sessions() race window |
| `tiered_memory.py:103` | `{**(metadata or {}), "user_id": uid}` | Spread copy | Metadata dict is isolated per hot entry |
| `fact_store.py:136` | `fact_user = fact.user_id or user_id` | Str ref | Immutable, safe |
| `identity/service.py` | `IdentityContext(user, session, agent, tenant)` | **Frozen**, object refs | Sub-objects shared but never mutated |
| `workflow/engine.py:367` | `json.dumps(step.input_data)` | Serialization | Creates entirely new string |
| `configuration/service.py:get()` | Coerced value per call | New object each call | Not cached after coercion |

---

## 7. Serialization Boundaries

### External Boundaries (wire format ↔ memory)

| Boundary | Direction | Format | Module | Risk |
|----------|-----------|--------|--------|------|
| HTTP request → Request | Inbound | JSON | FastAPI | Standard |
| Response → HTTP response | Outbound | JSON | FastAPI | Standard |
| WebSocket frame → message | Inbound | JSON | websocket_manager | Standard |
| CLI stdin → text | Inbound | Raw text | jarvis.py | Standard |
| MCP tool call → ToolBlock | Inbound | JSON | mcp/server.py | Standard |

### Internal Boundaries (memory ↔ storage)

| Boundary | Direction | Format | Module | Risk |
|----------|-----------|--------|--------|------|
| SubGoal → PlanStore | Both | JSON in SQLite TEXT | `planner/store.py` | Round-trips through JSON lose Python types |
| WorkflowInstance → WorkflowStore | Both | Per-column SQLite | `workflow/storage.py` | execution_context and artifacts are JSON TEXT columns |
| ExtractedFact → FactStore | Write only | 19-col SQLite | `fact_store.py` | embedding is binary BLOB |
| ToolBlock → execute_tool_block() | Both | json.dumps(input_data) | `workflow/engine.py` | dict → JSON → dict round-trip |
| Auth:_sessions → sessions.json | Both | JSON file | `auth.py` | No WAL, no transactions |
| Auth:_config → auth.json | Both | JSON file | `auth.py` | No WAL, no transactions |
| Configuration → settings.json | Both | JSON file | `settings/store.py` | Has backup + validation |
| EmbeddingMemory → SQLite | Write only | np.array.tobytes() → BLOB | `embedding_memory.py` | Incompatible with FactStore serialization |
| FactStore → SQLite | Write only | struct.pack() → BLOB | `fact_store.py` | Incompatible with EmbeddingMemory |

### Missing Serialization Boundaries

| Gap | Impact |
|-----|--------|
| No canonical Message type | Each subsystem defines its own message dict shape |
| No canonical Event type | 3+ event systems with incompatible payloads |
| PipelineContext has no schema validation | ~35 fields, no Pydantic model, no type enforcement |

---

## 8. Data Divergence Risks

### Risk 1: Memory Data Split Across Three Systems

A single "I like Python" message creates data in:
- **Hot tier** (RAM — volatile, lost on restart)
- **Mem0** (ChromaDB — persistent, different from FactStore)
- **Semantic memory** (SQLite — if importance > 0.8)
- **FactStore** (SQLite — extracted fact: "user prefers Python")
- **Session history** (JSON — full conversation)
- **ChatHistory** (SQLite — ORM model)

These six stores have no cross-references. If the FactStore is rebuilt, the facts from "I like Python" are lost even though the same data exists in Mem0 and session history.

### Risk 2: Embedding Binary Format Incompatibility

FactStore uses `struct.pack()`; EmbeddingMemory uses `np.tobytes()`. These produce different byte layouts for the same vector. A database consolidation that mixed these formats would produce silent corruption.

### Risk 3: IdentityContext vs AuthContext Dual Classes

Two different classes named similarly:
- `IdentityContext` (frozen, pipeline-scoped, 5 fields: user, session, agent, tenant, state)
- `AuthContext` (mutable, authz-scoped, 6 fields: user_id, roles, scopes, ip, session_id, metadata)

They share user/session information but in different formats. AuthorizationStage builds an `AuthContext` from `IdentityContext.user.id`, creating a copy point where identity data can diverge.

### Risk 4: Plan Round-Trip Through JSON

SubGoal objects → dict (with new fields added) → JSON → SQLite → JSON → dict. The round-trip adds fields (`title`, `estimated_duration`, `priority`) that are never used by the downstream planner. If a future version adds a field to SubGoal, the JSON round-trip silently drops it.

### Risk 5: Config Has Four Sources With Different Update Mechanisms

`configuration.set()` → in-memory + optionally file; `SettingsStore.set()` → Pyand valid + EventBus; direct env var change → not detected; REST API → two parallel endpoints with different schemas. There is no single "config changed" event that all consumers observe.

---

## 9. Findings & Recommendations

### F-1: No Canonical Message Type
Every subsystem defines message dicts with different schemas: `[{"role","content"}]`, `[{"role","content","timestamp"}]`, `{"text","data","metadata"}`. No Pydantic model enforces a common shape.

**R-1:** Define a `Message` dataclass with `role`, `content`, `timestamp`, `metadata` fields. Use it across all subsystems.

### F-2: Embedding Serialization Incompatible
FactStore (struct.pack) and EmbeddingMemory (np.tobytes) use different binary formats for the same data type.

**R-2:** Standardize on one binary embedding format (prefer `struct.pack` for portability, or `np.tobytes` for performance). Migrate all stores to the same format.

### F-3: IdentityContext ↔ AuthContext Data Duplication
User identity is represented in two different dataclasses with different field shapes.

**R-3:** Merge `IdentityContext` and `AuthContext` into a single `Identity` dataclass used by both pipeline and authz engine. Or at minimum, add a conversion method that guarantees field consistency.

### F-4: Plan Round-Trip Through JSON Drops Unknown Fields
`_subgoal_to_dict()` adds fields, `json.loads()` loses them.

**R-4:** Use a versioned serialization format. Add a `__schema_version` field to serialized dicts. Validate on deserialization.

### F-5: Config Update Has No Single Notification Channel
`ConfigurationService.set()` fires `on_change` listeners; `SettingsStore.set()` publishes EventBus event. These are not the same channel.

**R-5:** Unify config change notifications through the EventBus. Make `configuration.set()` publish to the canonical event bus so all consumers receive the same notification.

### F-6: Memory Write Path Creates Data in 6 Independent Stores
Each store is written independently with no transaction coordination.

**R-6:** Implement a two-phase write for memory: write to primary store (Mem0/FactStore), then asynchronously propagate to secondary stores (hot tier, semantic memory). Add a reconciliation mechanism for crash recovery.
