# JARVIS — Deep System Audit

**Date:** 2026-06-15
**Repository:** `C:\Users\peter\Desktop\jarvis`
**Audit Scope:** Full source analysis — architecture, security, performance, memory, tools, UI, execution flow

---

## Audit Results Overview

| Metric | Value |
|--------|-------|
| Python source files | 761 |
| Test files | ~103 |
| Skills (packages) | 40 |
| Folders | ~350 |
| Empty/dead folders | 9 |
| Registered tools | 61 (49 implemented, 10 broken, 2 ghost) |
| REST API endpoints | 90+ |
| WebSocket endpoints | 8 |
| Memory backends | 14+ |
| Databases | 7 (SQLite ×6, ChromaDB ×2) |
| Security issues | CRITICAL: 1, HIGH: 4, MEDIUM: 5, LOW: 3 |

### Grade Summary

| Category | Grade | Classification |
|----------|-------|---------------|
| Architecture | B | WARNING |
| Reliability | B | WARNING |
| Memory | B | WARNING |
| Agent Capability | A | SAFE |
| Tooling | A | SAFE |
| Browser Automation | C | WARNING |
| Voice | B | WARNING |
| UI Integration | C | WARNING |
| Security | C | WARNING |
| Performance | B | WARNING |
| Maintainability | C | WARNING |

---

## Phase Documents

| # | Document | Status | Key Finding |
|---|----------|--------|-------------|
| 1 | [PROJECT_INVENTORY.md](PROJECT_INVENTORY.md) | Complete | 5 dead Android calculator dirs, 4 empty dirs, ~95K total files |
| 2 | [IMPORT_GRAPH.md](IMPORT_GRAPH.md) | Complete | Two parallel import systems, 30+ module-level singletons |
| 3 | [EXECUTION_FLOW.md](EXECUTION_FLOW.md) | Complete | CLI → WS → agent_loop → StateGraph (10 nodes) |
| 4 | [UI_CONNECTION_AUDIT.md](UI_CONNECTION_AUDIT.md) | Complete | 30 pages, 90+ API calls, all genuinely connected (no fake data) |
| 5 | [FEATURE_REALITY_AUDIT.md](FEATURE_REALITY_AUDIT.md) | Complete | 19 features graded — most IMPLEMENTED, 2 FAKE, 1 BROKEN |
| 6 | [TOOL_AUDIT.md](TOOL_AUDIT.md) | Complete | 49 implemented, 10 broken, 2 ghost tools |
| 7 | [MEMORY_DEEP_AUDIT.md](MEMORY_DEEP_AUDIT.md) | Complete | Triple-write amplification, 14+ backends, all survive restart |
| 8 | [WEBSOCKET_AUDIT.md](WEBSOCKET_AUDIT.md) | Complete | 8 WS endpoints, all unauthenticated, streaming implemented |
| 9 | [PERFORMANCE_AUDIT.md](PERFORMANCE_AUDIT.md) | Complete | Token rates depend on model, no profiling infrastructure |
| 10 | [SECURITY_AUDIT.md](SECURITY_AUDIT.md) | Complete | 1 CRITICAL, 4 HIGH, 5 MEDIUM, 3 LOW findings |
| 11 | [CLEANUP_PLAN.md](CLEANUP_PLAN.md) | Complete | ~35 files removable, ~15K lines removable, 5 legacy dirs |
| 12 | [SYSTEM_SCORECARD.md](SYSTEM_SCORECARD.md) | Complete | 11 categories graded A-F with evidence |

---

## Critical Issues Requiring Immediate Action

### CRITICAL: `core/tools/bg_jobs.py:41`
`asyncio.create_subprocess_shell()` — async `shell=True` equivalent. Model-generated bash commands run unfiltered through the shell. Full command injection vector.

### HIGH: `core/routes/websocket.py:691`
`subprocess.Popen(["start", "chrome"], shell=True)` — Windows-only shell spawn with `shell=True`.

### HIGH: Path confinement bypasses
Three tool handlers (`do_refactor`, `do_undo_edit_file`, `do_batch_edit_file`) in `core/tools/execution.py` bypass the `_resolve_tool_path()` confinement system.

---

## System Architecture Diagram

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────────┐
│  jarvis.py  │────▶│  cli_commands.py │────▶│  cli_requests.py   │
│  (CLI entry)│     │  (10 commands)   │     │  (WS/REST helpers) │
└─────────────┘     └──────────────────┘     └─────────────────────┘
                                                    │
                           ┌────────────────────────┼────────────────────┐
                           ▼                        ▼                    ▼
                    ┌──────────────┐       ┌────────────────┐   ┌──────────────┐
                    │  /ws/agent_  │       │  core/main.py  │   │  local       │
                    │  stream      │       │  FastAPI App   │   │  runtime     │
                    └──────┬───────┘       └───────┬────────┘   └──────────────┘
                           │                       │
                           ▼                       ▼
                    ┌─────────────────────────────────────────────┐
                    │           core/agent_loop.py                │
                    │    stream_agent_loop() — async generator    │
                    └───────────────────┬─────────────────────────┘
                                        │
                                        ▼
                    ┌─────────────────────────────────────────────┐
                    │           core/graph/  StateGraph           │
                    │  10 nodes: setup→think→tool_call→verify→…  │
                    └───────────────────┬─────────────────────────┘
                                        │
                    ┌───────────────────┴─────────────────────────┐
                    │               ▼                             │
                    │   core/tools/execution.py                   │
                    │   _TOOL_HANDLERS (50+ tools)                │
                    │   MCP bridge, persistent_shell              │
                    └─────────────────────────────────────────────┘
```

## Database Footprint

| Database | Location | Size Estimate | Contents |
|----------|----------|--------------|----------|
| brain.db | `data/brain.db` | Variable | Episodic, Semantic, Task, Decision memories |
| chroma/ | `data/chroma/` | Variable | Vector embeddings (mem0) |
| qdrant_storage/ | `data/qdrant_storage/` | Variable | Vector embeddings (warm tier) |
| jarvis_memory.db | `data/jarvis_memory.db` | Variable | Embedding memory (SQLite + vectors) |
| agent_checkpoints.db | `~/.jarvis/agent_checkpoints.db` | Variable | Agent execution checkpoints |
| preferences.db | `~/.jarvis/preferences.db` | Small | User preference key/values |
| decision_memory.json | `~/.jarvis/decision_memory.json` | Small | Action→outcome learning |
| pattern_failures.json | `~/.jarvis/pattern_failures.json` | Small | Build error patterns |
| sessions/ | `~/.jarvis/sessions/` | Variable | Conversation history (JSON files) |
| memory.json | `{data_dir}/memory.json` | Variable | Core memory store |

---

*For detailed evidence and file:line references, consult individual phase documents listed above.*
