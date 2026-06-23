# DUPLICATION KILL LIST — JARVIS Reality Audit

> Generated: 2026-06-10
> Method: Static import chain analysis + production call path tracing (no docs trusted)

---

## Classification Legend

| Label | Meaning |
|-------|---------|
| **TRUE DUPLICATE** | Same purpose, same consumers, one should be deleted |
| **MIGRATION IN PROGRESS** | Old and new coexist; old is being phased out |
| **NOT DUPLICATE** | Different purpose despite similar names |
| **PARTIAL OVERLAP** | Some functional overlap but different scope/consumers |

---

## Collision 1: Routing — core/routes/ vs api/ vs routers/

| Aspect | core/routes/ | api/ | routers/ |
|--------|-------------|------|----------|
| Files | 14 route modules | 18 route modules | 6 route modules |
| Registered in | core/main.py (always loaded) | core/main.py (lazy loaded) | core/main.py (lazy loaded) |
| Imported by | core/main.py, core/routes/settings.py | core/main.py, tests | core/main.py, core/routes/chat.py, tests |
| Route scope | Settings, admin, auth, chat, control, cowork, infra, intelligence, operations, quality, utility, vision, voice, websocket | Vision, cookbook, research, email, settings, website, plugin, cloud, governance, memory, RAGflow | WhatsApp, screen, setup, dot, JARVIS Hub, three-pass chat |

**Verdict: NOT DUPLICATE.** All three serve different route groups. They are complementary, not competing. This is a modular architecture choice, not duplication.

**Action**: Keep all three. Consider whether some could merge, but currently each has distinct consumers.

---

## Collision 2: Brain — brain/UnifiedBrain.py vs core/graph/think_node

| Aspect | brain/UnifiedBrain.py | core/graph/nodes.py (think_node) |
|--------|----------------------|----------------------------------|
| Type | Class (UnifiedBrain) | Async function (think_node) |
| Purpose | Standalone reasoning/planning/adversarial engine | State machine node in agent graph |
| Imported by | api/server.py, core/adversarial.py, core/document_processor.py, core/lifespan.py, core/routes/admin.py, tools/scene_generator.py, routers/chat.py | core/agent_loop.py (via core.graph), core/routes/chat.py, tests |
| Lines | ~250 | ~1,150 (entire file with all nodes) |

**Verdict: NOT DUPLICATE.** UnifiedBrain is a reasoning class used by the API server, document processing, and adversarial module. think_node is a state machine step in the agent graph loop. Different execution contexts.

**Action**: Keep both. They serve different architectural layers.

---

## Collision 3: Memory — memory/ (package) vs core/memory.py

| Aspect | memory/ package | core/memory.py |
|--------|----------------|----------------|
| Key classes | MemoryFacade (facade), TieredMemory, EmbeddingMemory, DecisionMemory, Mem0Adapter | MemoryManager |
| Imported by | 29 files: api, core modules, mcp, learning, tests | mcp/memory_server.py (only) |
| Lines | 7 files total | ~80 lines |
| Purpose | Primary memory subsystem with facade pattern | Simple memory manager for MCP server |

**Verdict: NOT DUPLICATE (Partial Overlap).** The memory/ package is the canonical memory system. core/memory.py is a smaller, separate utility used only by the MCP server. They have different class names (MemoryFacade vs MemoryManager).

**Action**: Keep both for now. If core/memory.py is truly just a simplified version, consider migrating mcp/memory_server.py to use memory.memory_facade instead, then deprecate core/memory.py.

---

## Collision 4: Event Bus — core/event_bus.py vs ai_os/event_bus.py

| Aspect | core/event_bus.py | ai_os/event_bus.py |
|--------|-------------------|---------------------|
| API | Module-level functions: subscribe(), unsubscribe(), fire_event(), get_task_scheduler() | Class: EventBus |
| Imported by | core/tools/document_tools.py, core/tools/skill_tools.py | core/settings/store.py |
| Lines | ~70 | ~80 |

**Verdict: NOT DUPLICATE.** Different APIs (module-level functions vs. class), different consumers. The core/ version is a lightweight event dispatch used by document/skill tools. The ai_os/ version is a class-based event bus used by the settings store.

**Action**: Keep both. Consider unifying the APIs if they serve the same conceptual purpose, but current consumers are distinct.

---

## Collision 5: Tool Execution — tools/executor.py vs core/tools/execution.py

| Aspect | tools/executor.py | core/tools/execution.py |
|--------|-------------------|-------------------------|
| Key class/function | OpenClawExecutor | execute_tool_block (main entry), _TOOL_HANDLERS dict |
| Purpose | External agent executor (OpenClaw/hybrid system) | Main tool dispatch engine for the agent loop |
| Imported by | api/hybrid_integration.py, orchestrator/hybrid_orchestrator.py, tests (unit + e2e) | core/agent_tools.py, core/tools/__init__.py, core/debugger.py, audit script, tests |
| Lines | ~100 | ~1,400 |

**Verdict: NOT DUPLICATE.** Different scopes. core/tools/execution.py is the central tool execution engine that handles all tool dispatch for the agent system. tools/executor.py is a specialized executor for the OpenClaw hybrid system. Different consumers, different use cases.

**Action**: Keep both. They serve different architectural layers (core agent system vs. hybrid orchestrator).

---

## Collision 6: Settings — core/settings/store.py vs core/settings_legacy.py

| Aspect | core/settings/store.py | core/settings_legacy.py |
|--------|------------------------|------------------------|
| Key exports | SettingsStore class, get_settings_store() | load_settings(), save_settings(), get_setting(), _load_legacy() |
| Lines | ~300 | ~98 |
| Mechanism | Pydantic-validated settings store | Dict-based legacy settings |
| Imported by | core/settings/__init__.py, cli_commands.py, api/settings_routes.py, ai_os/config.py, assistant/voice_pipeline.py, core/agi_core.py, tests | core/agent_prompts.py, core/lifespan.py, core/graph/nodes.py, core/routes/chat.py, core/routes/websocket.py, core/tools/settings_tools.py, _archive/context_compactor.py |

**Verdict: TRUE DUPLICATE — MIGRATION IN PROGRESS.** These are two implementations of the same concept. store.py (pydantic-based) is the NEW canonical version. settings_legacy.py (dict-based) is the OLD version that is still actively imported by production code (not just archive code).

**Canonical**: `core/settings/store.py` (the new pydantic-validated store)

**Legacy**: `core/settings_legacy.py` (should be deleted after migration)

**Migration needed**: The following files still import from `core.settings_legacy`:
- core/agent_prompts.py (lines 450, 521)
- core/lifespan.py (line 73)
- core/graph/nodes.py (line 50)
- core/routes/chat.py (line 79)
- core/routes/websocket.py (line 273)
- core/tools/settings_tools.py (lines 36, 192)

**Action**: Migrate these 6 callers to use `core.settings.store`, then delete `core/settings_legacy.py`.

---

## Collision 7: Resource Monitor — monitors/resource.py vs core/governance/resource_monitor.py

| Aspect | monitors/resource.py | core/governance/resource_monitor.py |
|--------|----------------------|--------------------------------------|
| Key classes | ResourceSnapshot, ResourceMonitor | ResourceSnapshot, ResourceMonitor |
| Lines | ~152 | ~178 |
| Imported by (production) | NONE | core/governance/work_queue.py, core/governance/cli_commands.py, core/system_governor.py, api/governance_routes.py |
| Imported by (test only) | tests/unit/test_monitors.py | tests/unit/test_governance.py |

**Verdict: TRUE DUPLICATE.** Same class names (ResourceSnapshot, ResourceMonitor). monitors/resource.py is ONLY imported by test_monitors.py. core/governance/resource_monitor.py is the one actually used by production code.

**Canonical**: `core/governance/resource_monitor.py` (used by governance, system governor, API routes)

**Legacy**: `monitors/resource.py` (only test code imports it)

**Action**: Delete monitors/resource.py. Migrate test_monitors.py to import from core.governance.resource_monitor instead. The monitors/ directory has 3 other files (alerts.py, services.py, __init__.py) — check if those also have duplicates in core/governance/ or can be removed entirely.

---

## Summary: Kill List

| Collision | Type | Keep | Delete | Priority |
|-----------|------|------|--------|----------|
| Settings (store vs legacy) | MIGRATION | core/settings/store.py | core/settings_legacy.py | HIGH — actively confusing two parallel systems |
| Resource Monitor (monitors vs governance) | TRUE DUPLICATE | core/governance/resource_monitor.py | monitors/resource.py | MEDIUM — dead code, only tests import it |
| Memory (package vs core/memory.py) | PARTIAL OVERLAP | memory/ package | Consider deprecating core/memory.py | LOW — only MCP server depends on it |
| Routing (core/routes/ vs api/ vs routers/) | NOT DUPLICATE | All three | None | NONE |
| Brain (UnifiedBrain vs think_node) | NOT DUPLICATE | Both | None | NONE |
| Event Bus (core vs ai_os) | NOT DUPLICATE | Both | None | NONE |
| Tool Execution (executor vs execution) | NOT DUPLICATE | Both | None | NONE |

## Additional Duplication Worthy of Investigation

While not part of the original collision list, the following were discovered during audit:

| Suspicious Pair | Notes |
|----------------|-------|
| core/supervisor_routes.py vs core/routes/control.py vs core/control_loop.py | Three separate "control" files with unclear separation |
| core/build_routes.py vs core/plan_routes.py | Separate route files for build/plan that may overlap with core/routes/operations.py |
| tools/deep_research.py vs core/routes/intelligence.py vs core/sub_agents/agents/nexus.py | Multiple research/intelligence pathways |
