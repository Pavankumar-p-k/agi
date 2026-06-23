# PHASE 9 — Performance Audit

Static analysis of latency characteristics, bottlenecks, and scaling constraints.
No runtime profiling infrastructure exists — analysis is based on code structure and timeouts.

---

## Component Latency Analysis

### 1. Classification (Intent Detection)

**Path:** `core/main.py:581-670` — `execute_action()`

| Classifier | Method | Est. Latency | Notes |
|------------|--------|-------------|-------|
| Intent detection | LLM call via `llm_router.generate()` | ~500-2000ms | Depends on model size |
| Keyword fallback | String matching | <5ms | For known patterns (open, play, search, etc.) |
| Action routing | Switch-case on intent type | <1ms | 7 intent types handled |

**Timeout:** 15s hardcoded (`core/routes/websocket.py:90`)

---

### 2. Fast Path (Intent Actions)

**Path:** `core/main.py:581-670`

| Action | Implementation | Est. Latency | Notes |
|--------|---------------|-------------|-------|
| `open_url` | Browser launch | ~200-500ms | Chrome process spawn |
| `play_media` | `media/player.py` | ~100-300ms | Local media player |
| `web_search` | API call | ~500-3000ms | External search API |
| `reminder` | DB write | ~50-100ms | SQLite insert |
| `weather` | API call | ~500-2000ms | Weather API |
| `build` | Subprocess | Variable | Build duration |
| `pc_control` | Platform API | ~100-500ms | OS automation |
| `browser_task` | Vision browser | ~2000-10000ms | Screenshot + analyze |

---

### 3. Agent Loop (StateGraph)

**Path:** `core/agent_loop.py:31-87` → `core/graph/graph.py:43-88`

| Node | Est. Latency | Parallel | Notes |
|------|-------------|----------|-------|
| `setup_node` | ~500-3000ms | No | MCP init, tool RAG, prompt building |
| `think_node` | ~1000-10000ms | No | LLM call (dominant latency source) |
| `route_node` | ~50-200ms | No | Tool block parsing, loop detection |
| `tool_call_node` | Variable | **Yes** | Concurrent tool execution |
| `verify_node` | ~500-2000ms | No | Verifier subagent LLM call |
| `pause_node` | Variable | No | Human-in-the-loop wait |
| `parallel_sub_agents` | Variable | **Yes** | Fan-out sub-agents |
| `force_answer_node` | ~100-500ms | No | Final synthesis |
| `finish_node` | ~50-100ms | No | Metrics + cleanup |

**Max rounds:** 15 (default) — worst case: 15 × ~10s = ~150 seconds per response

---

### 4. Tool Execution

| Tool | Est. Latency | Timeout | Notes |
|------|-------------|---------|-------|
| `bash`/`python` | Variable | 1 hour | Long-running scripts |
| `read_file` | <50ms | — | Local file read |
| `write_file` | <50ms | — | Local file write |
| `web_search` | ~500-3000ms | — | External API |
| `web_fetch` | ~500-5000ms | — | URL fetch + SSRF check |
| `semantic_search` | ~100-500ms | — | ChromaDB query |
| `edit_file` | <100ms | — | Local file edit |
| `create_document` | <100ms | — | DB insert |

---

### 5. Ollama (LLM Backend)

| Model | Est. Tokens/sec | Est. TTFT | Notes |
|-------|----------------|-----------|-------|
| qwen2.5-coder:3b | ~30-50 t/s | ~500ms | Default small model |
| qwen2.5-coder:7b | ~15-30 t/s | ~1000ms | Medium model |
| llama3:8b | ~10-20 t/s | ~1500ms | Large model |
| deepseek-coder:6.7b | ~15-25 t/s | ~1000ms | Code-optimized |

**Source:** `core/model_providers/ollama.py` — all models run locally via Ollama

---

### 6. Database Operations

| DB | Operation | Est. Latency | Notes |
|----|-----------|-------------|-------|
| SQLite (brain.db) | READ (indexed) | <5ms | WAL mode, synchronous=NORMAL |
| SQLite (brain.db) | WRITE (indexed) | <20ms | WAL mode |
| ChromaDB | Vector search | ~50-200ms | HNSW index |
| SQLite (embedding) | Full-scan cosine | O(n) — degrades | No vector index |
| JSON files | READ | <10ms | Small files |
| JSON files | WRITE | <20ms | Atomic replace |

---

## Bottleneck Analysis

| Bottleneck | Impact | Location | Mitigation |
|------------|--------|----------|------------|
| **LLM call latency** | Dominant (90%+ of response time) | `think_node` | Model selection, streaming, caching |
| **Full-scan embedding search** | O(n) degradation | `memory/embedding_memory.py:94` | Add vector index |
| **Triple-write memory** | 3x storage I/O | Multiple locations | Consolidate backends |
| **Sequential agent loop** | 15 rounds × slowest node | `core/graph/graph.py:43-88` | Parallel sub-agent execution |
| **300ms polling** | Unnecessary I/O | `/ws/logs` — `websocket.py:261` | Push-based log delivery |
| **DNS rebinding delay** | +100ms per URL fetch | `core/ssrf.py:157` | Optional (security feature) |

---

## Startup Performance

| Component | Est. Startup Time | Notes |
|-----------|------------------|-------|
| Python imports (all modules) | ~2000-5000ms | 30+ module-level singletons |
| FastAPI app creation | ~500-2000ms | 40+ route modules |
| SQLite DB init | ~100-300ms | Creates tables on first access |
| ChromaDB init | ~500-2000ms | Loads collection |
| Mem0 adapter init | ~500-2000ms | Loads LLM config |
| **Total startup** | **~3-8 seconds** | |

---

## Memory Growth

| Component | Growth Rate | Bound | Notes |
|-----------|------------|-------|-------|
| Hot tier (RAM) | ~1KB/memory | 10 max entries | Self-limiting |
| ChromaDB (disk) | ~1-5KB/conversation | Unlimited | No GC for deleted sessions |
| SQLite (brain.db) | ~2-10KB/action | Unlimited | Episodic 30-day summarization helps |
| JSON sessions (disk) | ~1-5KB/conversation | Unlimited | Manual `compact()` needed |
| Agent checkpoints | ~5-50KB/session | 7-day GC, 10/session | Auto-limited |

---

## Recommendations

1. **Add runtime profiling** — no `cProfile`, `py-spy`, or `opentelemetry` integration found
2. **Consolidate memory backends** — eliminate triple-write latency
3. **Add vector index** to `embedding_memory.py` for O(log n) search
4. **Implement response caching** for repeated queries
5. **Add Prometheus metrics** — the `MetricsMiddleware` exists but is optional (`core/main.py:185`)
6. **Measure time-to-first-token** — currently tracked in `AgentState` but not exposed to any API
