# SILENT FAILURE REPORT — JARVIS Runtime Audit

> Generated: 2026-06-10  
> Scope: All .py files in C:\Users\peter\Desktop\jarvis  
> Methodology: Pattern-matched grep for 8 categories of silent failure

---

## EXECUTIVE SUMMARY

| Category | Count | Critical | High | Medium | Low |
|---|---|---|---|---|---|
| except Exception: pass | 18 | 0 | 0 | 0 | 18 |
| eturn "" (error paths) | 60+ | 0 | 11 | 34 | 15 |
| eturn None (error paths) | 100+ | 4 | 28 | 42 | 26 |
| eturn [] (error paths) | 83 | 0 | 18 | 41 | 24 |
| eturn True unconditional | 9 flagged | 1 | 2 | 4 | 2 |
| [ASSUMED]/[UNCERTAIN] tags | 4 (legitimate) | 0 | 0 | 0 | 0 |
| unwrap_or("") chains | 55 (pattern OK) | 0 | 0 | 1 | 0 |
| HTTP 200 with error content | Numerous (pattern OK) | 0 | 0 | 0 | 0 |

**Bottom line:** 260+ silent failure sites exist. 5 are **CRITICAL**, 59 are **HIGH**.

---

## 1. except Exception: pass — Silent exception swallowing

### Rule violated: AGENTS.md "NO silent except blocks — every except must log with logger.warning()"

### All 18 occurrences (all in jarvis_tui/ — UI layer):

| # | File | Line | Code | Impact | Severity |
|---|---|---|---|---|---|
| 1 | jarvis_tui\main.py | 258 | except Exception: pass | Backend status poll fails silently — UI shows stale data | MEDIUM |
| 2 | jarvis_tui\main.py | 276 | except Exception: pass | Reconnection attempt fails silently — stays offline | MEDIUM |
| 3 | jarvis_tui\main.py | 284 | except Exception: pass | Backend connection attempt fails silently | MEDIUM |
| 4 | jarvis_tui\main.py | 347 | except Exception: pass | Theme switch toast fails silently | LOW |
| 5 | jarvis_tui\app\widgets\chat_stream.py | 60 | except: pass | Sparkline rendering bar fails silently | LOW |
| 6 | jarvis_tui\app\widgets\status_bar.py | 51 | except Exception: pass | Session ID widget fails silently | LOW |
| 7 | jarvis_tui\app\widgets\status_bar.py | 55 | except Exception: pass | Token count widget fails silently | LOW |
| 8 | jarvis_tui\app\widgets\status_bar.py | 59 | except Exception: pass | Agent count widget fails silently | LOW |
| 9 | jarvis_tui\app\widgets\status_bar.py | 63 | except Exception: pass | Git branch widget fails silently | LOW |
| 10 | jarvis_tui\app\widgets\sidebar.py | 66 | except Exception: pass | Agent list widget fails silently | LOW |
| 11 | jarvis_tui\app\widgets\sidebar.py | 71 | except Exception: pass | Model selector widget fails silently | LOW |
| 12 | jarvis_tui\app\widgets\sidebar.py | 77 | except Exception: pass | Context progress bar fails silently | LOW |
| 13 | jarvis_tui\app\widgets\sidebar.py | 92 | except Exception: pass | CPU/RAM/VRAM stat widgets fail silently | LOW |
| 14 | jarvis_tui\app\widgets\input_bar.py | 107 | except Exception: pass | Ghost text label update fails silently | LOW |

**Note:** Lines 259, 293 in main.py and 56, 126, 141, 147 in input_bar.py have except Exception: blocks that are NOT followed by pass — they either retry or contain other logic. These were excluded but should be checked for logging compliance.

---

## 2. eturn "" — Empty returns in error handlers

### Key HIGH occurrences:

| # | File | Line | Code | Impact | Severity |
|---|---|---|---|---|---|
| 1 | core/mcp_manager.py | 433,450 | eturn "" | MCP tool calls silently return empty | HIGH |
| 2 | core/cloud/realtime_sync.py | 47,70 | eturn "" | Realtime cloud sync silently returns empty | HIGH |
| 3 | mcp/email_server.py | 70,350,356,376,406 | eturn "" | Email server returns empty on failures | HIGH |
| 4 | 	ools/deep_research.py | 132 | eturn "" | Deep research returns empty | HIGH |
| 5 | 	ools/ragflow_tool.py | 97 | eturn "" | RAGflow query returns empty | HIGH |
| 6 | 	ools/search_fallback.py | 60,81,161,194 | eturn "" | Multi-engine search returns empty on all failures | HIGH |

### MEDIUM occurrences (34 total — key ones):

| # | File | Line | Code | Severity |
|---|---|---|---|---|
| 7 | core/personal_docs.py | 46 | eturn "" — PDF extraction fails silently | MEDIUM |
| 8 | ssistant/voice_pipeline.py | 127 | eturn "" — Both cloud & local LLM failed | MEDIUM |
| 9 | ssistant/providers/faster_whisper.py | 92 | eturn "" — STT transcription fails silently | MEDIUM |
| 10 | ssistant/providers/deepgram.py | 52,65,68 | eturn "" — Deepgram STT failures | MEDIUM |
| 11 | ssistant/providers/azure_speech.py | 39,61,67 | eturn "" — Azure STT failures | MEDIUM |
| 12 | core/codebase_indexer.py | 45,78 | eturn "" — Indexing & search silently return empty | MEDIUM |
| 13 | core/agent_helpers.py | 162 | eturn "" — send_message returns empty on failure | MEDIUM |
| 14 | core/document_processor.py | 309 | eturn "" — Document parse failure | MEDIUM |
| 15 | core/repomap.py | 143 | eturn "" — Repo map generation fails | MEDIUM |
| 16 | core/real_validator.py | 237 | eturn "" — Real-time validation fails | MEDIUM |
| 17 | core/vision_agent.py | 418,433 | eturn "" — Vision agent returns blank | MEDIUM |
| 18 | core/session.py | 176 | eturn "" — Session info fetch | LOW |
| 19 | core/shared_context.py | 48,61 | eturn "" — Shared context returns empty | MEDIUM |
| 20 | memory/tiered_memory.py | 213 | eturn "" — Memory retrieval fails | MEDIUM |
| 21 | memory/preferences.py | 63 | eturn "" — User preference fetch | MEDIUM |
| 22 | memory/memory_facade.py | 156 | eturn "" — Memory facade returns empty | MEDIUM |
| 23 | memory/mem0_adapter.py | 131 | eturn "" — mem0 adapter returns empty | MEDIUM |
| 24 | learning/student_agi/teacher/jarvis_teacher.py | 508 | eturn "" — Teacher AGI fails | MEDIUM |
| 25 | 	ools/website_generator.py | 153,326 | eturn "" — Website generation fails | MEDIUM |
| 26 | rain/UnifiedBrain.py | 126 | eturn "" — Unified brain fails | MEDIUM |
| 27 | i_os/ollama_client.py | 39 | eturn "" — Ollama client fails | MEDIUM |
| 28 | demo/agent_stream.py | 33 | eturn "" — Demo agent stream fails | LOW |
| 29 | services/memory/skills.py | 66,69 | eturn "" — Skills memory fails | MEDIUM |

---

## 3. eturn None — Silent None returns breaking caller chains

### CRITICAL:

| # | File | Line | Code | Impact | Severity |
|---|---|---|---|---|---|
| 1 | core/agent_registry.py | 83 | eturn None | Agent lookup returns None — every agent dispatch can crash | **CRITICAL** |
| 2 | core/api_key_vault.py | 83,98 | eturn None | Key decryption fails silently — downstream crashes | **CRITICAL** |
| 3 | core/auth.py | 379,444,477,483,496 | eturn None | Auth checks return None — access control bypass risk | **CRITICAL** |
| 4 | core/embeddings.py | 265 | eturn None | Embedding generation fails — breaks all vector ops | **CRITICAL** |

### HIGH:

| # | File | Line | Code | Impact | Severity |
|---|---|---|---|---|---|
| 5 | core/control_loop.py | 267,926 | eturn None | Agent loop step evaluation breaks execution | HIGH |
| 6 | core/conflict_resolver.py | 75,79,90 | eturn None | Conflict resolution silently gives up | HIGH |
| 7 | core/cloud/cloud_memory.py | 144,204 | eturn None | Cloud memory silently fails | HIGH |
| 8 | core/cloud/supabase_client.py | 43,52,55 | eturn None | Supabase operations silently return None | HIGH |
| 9 | core/cloud/project_manager.py | 180,229 | eturn None | Project cloud ops silently fail | HIGH |
| 10 | i_os/sandbox_manager.py | 64,91,144 | eturn None | Sandbox operations silently fail | HIGH |
| 11 | core/agent_launcher.py | 142 | eturn None | Agent launch silently fails | HIGH |
| 12 | core/context_hub.py | 145 | eturn None | Context hub returns None | HIGH |
| 13 | mcp/email_server.py | 111,141,296,647,665,672 | eturn None | Email operations return None | HIGH |
| 14 | core/cron.py | 96 | eturn None | Cron scheduler silently stops | HIGH |
| 15 | core/email_monitor.py | 77,85,88 | eturn None | Email monitoring silently fails | HIGH |
| 16 | memory/decision_memory.py | 123,134,151,165 | eturn None | Decision memory queries fail | HIGH |
| 17 | core/checkpoint_manager.py | 77 | eturn None | Checkpoint restoration fails | MEDIUM |
| 18 | core/diagnostics.py | 252,257 | eturn None | Diagnostics system health checks fail | MEDIUM |
| 19 | core/ambiguity_resolver.py | 176 | eturn None | Ambiguity resolution fails | MEDIUM |
| 20 | mcp/server.py | 177 | eturn None | MCP RPC with no method returns None | MEDIUM |
| 21 | core/event_bus.py | 70 | eturn None | Event bus clear | LOW |

---

## 4. eturn [] — Empty list returns losing data silently

### HIGH:

| # | File | Line | Count | Impact | Severity |
|---|---|---|---|---|---|
| 1 | core/memory.py | 155,166,198,219,319 | 5x | Memory queries return empty on error — data loss | HIGH |
| 2 | core/rag_vector.py | 199,201,203,264,269,298,463 | 7x | RAG vector searches return empty — no results | HIGH |
| 3 | memory/mem0_adapter.py | 87,93,98,104,109,115 | 6x | mem0 adapter returns empty on every failure mode | HIGH |
| 4 | memory/memory_facade.py | 104 | 1x | Memory facade list returns empty | HIGH |
| 5 | core/llm_failover.py | 340 | 1x | LLM failover list returns empty | HIGH |
| 6 | core/oauth.py | 128 | 1x | OAuth providers list returns empty | HIGH |
| 7 | core/cloud/cloud_memory.py | 245 | 1x | Cloud memory search returns empty | HIGH |
| 8 | 	ools/search_fallback.py | 108,114,138,145,185 | 5x | Search engine fallbacks all return empty | HIGH |
| 9 | 	ools/ragflow_tool.py | 80,91 | 2x | RAGflow tool returns empty | HIGH |

### MEDIUM:

| # | File | Line | Impact | Severity |
|---|---|---|---|---|
| 10 | memory/tiered_memory.py | 177,186 | Tiered memory returns empty | MEDIUM |
| 11 | core/checkpoint_manager.py | 83 | Checkpoints return none | MEDIUM |
| 12 | core/control_loop.py | 981 | Execution result retrieval empty | MEDIUM |
| 13 | core/email_monitor.py | 103,113 | Email fetch silently empty | MEDIUM |
| 14 | core/file_agent.py | 185 | File search returns empty | MEDIUM |
| 15 | core/codebase_indexer.py | 109,181 | Code search returns empty | MEDIUM |
| 16 | core/llm_messages.py | 26 | Message history returns empty | MEDIUM |
| 17 | core/session.py | 190 | Session listing returns empty | MEDIUM |
| 18 | core/cloud/project_manager.py | 205 | Project listing returns empty | MEDIUM |
| 19 | 	ools/image_gen.py | 53,69,100,121,146 | Image generation fails silently | MEDIUM |
| 20 | 	ools/file_search.py | 82 | File search returns empty | MEDIUM |
| 21 | core/tools/index.py | 291,302 | Tool index retrieval fails | MEDIUM |
| 22 | core/tools/cookbook_tools.py | 369 | Cookbook search returns empty | MEDIUM |
| 23 | core/personal_docs.py | 58 | Personal docs search returns empty | MEDIUM |
| 24 | core/hardware_advisor.py | 141,150 | Hardware advice returns empty | MEDIUM |

---

## 5. eturn True unconditional — Fake success signals

| # | File | Line | Code | Impact | Severity |
|---|---|---|---|---|---|
| 1 | i_os/orchestrator.py | 202 | eturn True  # read-only + shell ops — **LIE:** unconditionally True | **CRITICAL** |
| 2 | i_os/tool_registry.py | 108 | eturn {"success": True, ..."Code agent would run"} — never runs | HIGH |
| 3 | core/agent_registry.py | 43,54,67 | eturn True — agent existence checks unconditional | HIGH |
| 4 | core/ambiguity_resolver.py | 122,125,132,153,155 | Always resolved | MEDIUM |
| 5 | core/conflict_resolver.py | 48,57 | Always resolved | MEDIUM |
| 6 | channels/base.py | 49 | eturn True # Open by default — **Security:** access allowed by default | HIGH |

---

## 6. Epistemic Tags ([ASSUMED] / [UNCERTAIN])

**Verdict: NOT silent failures.** These are intentional epistemic markers in rain/epistemic_tagger.py. The tagger is a legitimate working component that classifies responses by provenance. Tests exist in 	ests/integration/test_memory_privacy.py.

---

## 7. unwrap_or("") Chains

**Verdict: Pattern is correct** (Rust-style Result type properly implemented in core/result.py). The concern is downstream consumers that don't check for empty strings.

**Key hazard sites (empty string propagates silently):**

| File | Line | Code | Risk |
|---|---|---|---|
| core/goal_interpreter.py | 74 | (await llm_complete(...)).unwrap_or("") | Empty string→goal analysis |
| core/file_agent.py | 363,416 | (await llm_complete(...)).unwrap_or("") | Empty string→file operations |
| core/supervisor_agent.py | 140 | (await llm_complete(...)).unwrap_or("") | Empty string→supervisor |
| core/routes/chat.py | 117 | es.unwrap_or("Error processing request.") | Error text as 200 OK |
| core/routes/cowork.py | 101 | (await llm_complete(...)).unwrap_or("") | Empty string→cowork output |
| core/routes/utility.py | 66 | (await llm_complete(...)).unwrap_or("") | Empty string→code review |
| core/quality_grader.py | 85 | aw_r.unwrap_or("{}") | Empty JSON→quality grading |
| 	ools/website_generator.py | 130 | esult.unwrap_or("") | Empty string→HTML generation |
| 	ools/template_library.py | 183 | illed_result.unwrap_or(template_html) | Unfilled template→output |

---

## 8. HTTP 200 with Error Content

**Verdict: Deliberate design pattern** (error status in JSON body rather than HTTP status code). Prevents HTTP-level monitoring but is consistent across the codebase. Not classified as a silent failure.

---

## PRIORITY FIX LIST

### IMMEDIATE (CRITICAL — fix within 1 sprint):

1. **core/agent_registry.py:83** — Agent lookup returns None, crashes agent dispatch
2. **core/api_key_vault.py:83,98** — Key not found returns None, breaks all API calls
3. **core/auth.py:379,444,477,483,496** — Auth checks return None, access bypass risk
4. **core/embeddings.py:265** — Embedding failure returns None, breaks all vector ops
5. **i_os/orchestrator.py:202** — Unconditional eturn True hides all execution failures

### HIGH PRIORITY (fix within 2 sprints):

1. **core/memory.py** — 5x eturn [] on memory query failures → data loss
2. **core/rag_vector.py** — 7x eturn [] on RAG query failures → no search results
3. **memory/mem0_adapter.py** — 6x eturn [] on all failure modes
4. **	ools/search_fallback.py** — 9x eturn "" / eturn [] on search failures
5. **mcp/email_server.py** — 8x eturn None / eturn "" on email operations
6. **core/mcp_manager.py:433,450** — MCP tool calls silently return empty
7. **core/cloud/** — 5x eturn None across cloud services (supabase, memory, project)
8. **i_os/sandbox_manager.py** — 3x eturn None on sandbox operations
9. **core/control_loop.py:267,926** — Step evaluation returns None
10. **core/cloud/realtime_sync.py:47,70** — Cloud sync silently returns empty

### MEDIUM PRIORITY:

- All eturn "" in ssistant/providers/ (faster_whisper, deepgram, azure)
- All eturn "" in core/vision_agent.py:418,433
- core/file_agent.py:185 — File search returns []
- core/email_monitor.py — Email monitoring fails silently
- All TUI except Exception: pass (14 blocks) — add logger.warning()
- i_os/tool_registry.py:108 — Code agent handler lies about success
- channels/base.py:49 — Security: channel access allowed by default
