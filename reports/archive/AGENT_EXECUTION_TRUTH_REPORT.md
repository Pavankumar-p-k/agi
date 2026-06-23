# AGENT EXECUTION TRUTH REPORT

**Date:** 2026-06-16 20:00 UTC+5:30
**Method:** Instrumented end-to-end execution of 3 real browser tasks through `stream_agent_loop()`

---

## SECTION 1: Architecture Actually Used

### Graph Pipeline (StateGraph nodes executed)

```
User Request
  └─ stream_agent_loop()               [core/agent_loop.py:31]
       └─ build_default_graph()          [core/graph/__init__.py]
            ├─ setup_node()              [core/graph/nodes.py:71]   ✅ EXECUTED
            │    • Selects relevant tools via ALWAYS_AVAILABLE + keyword fallback
            │    • Builds system prompt: _assemble_prompt(compact=False)
            │    • Context: 4000 input tokens
            ├─ think_node()              [core/graph/nodes.py:257]  ✅ EXECUTED
            │    • Calls Ollama: POST http://localhost:11434/api/chat
            │    • Model: qwen2.5-coder:3b (Ollama PID 7656)
            │    • tools_sent=0  ← NO tool schemas for local models
            │    • LLM response: 127 tokens (text only, no tool calls)
            ├─ finish_node()             [core/graph/nodes.py:1157] ✅ EXECUTED
            │    • Teacher escalation hook: FAILED (module not installed)
            └─ [DONE]
```

### Ollama LLM Confirmed
```
Ollama PID:    7656 (persistent across all 3 tasks)
Memory:        146 MB → 182 MB → 146 MB
Model:         qwen2.5-coder:3b
Inference:     ✅ 3/3 tasks produced tokens (127, 50, 56 tokens)
API calls:     POST http://localhost:11434/api/chat → 200 OK
Token rate:    10-11 tok/s
```

---

## SECTION 2: Components Bypassed vs Active

| Component | Status | Evidence |
|-----------|--------|----------|
| **Classifier** | ❌ Bypassed | `stream_agent_loop()` called directly; no classification step |
| **WebSocket** | ❌ Bypassed | No server started; direct function call |
| **REST API** | ❌ Bypassed | No server started |
| **route_node** | ❌ Never reached | `think_node` produced no tool blocks → graph went to `finish` |
| **tool_call_node** | ❌ Never reached | No tools to execute |
| **Browser tool dispatch** | ❌ Never reached | No tool was selected by LLM |
| **BrowserManager** | ❌ Never launched | No browser tool ever called |

### Active (confirmed executing):
- `setup_node` — ✅ Builds system prompt
- `think_node` — ✅ Calls Ollama, streams response
- `finish_node` — ✅ Emits metrics, ends session
- **Ollama LLM** — ✅ Generates text responses

---

## SECTION 3: Agent Driven vs Direct Tool Call

| Category | Count | Percentage |
|----------|-------|------------|
| AGENT_DRIVEN (LLM decides → tool executes) | **0** | **0%** |
| DIRECT_TOOL_CALL (bypasses agent) | **0** | **0%** |
| MOCK/FAKE | **0** | **0%** |
| LLM responded with text (no tool call) | **3** | **100%** |

**Root cause:** The system prompt for local models (`compact=False`) uses `_TOOL_SHORTLIST` which only documents 6 code tools. Browser tools (defined in `_TOOL_SECTIONS`) are **never injected into the prompt**.

File: `core/agent_prompts.py:43-51`
```python
_TOOL_SHORTLIST = """\
## Code tools
- bash
- read_file / write_file
- create_document / edit_document / update_document
- build_repomap
- code_graph
- app_api"""
```

Line 53: `_TOOL_SECTIONS` — contains browser tool docs but is **never referenced** in prompt assembly.

For API models (GPT-4, Claude), native function-calling schemas ARE sent via the `tools` API parameter — they would work. But `_is_api_model=False` for Ollama, so `tools_sent=0`.

---

## SECTION 4: Browser Verification

| Check | Result | Evidence |
|-------|--------|----------|
| Browser launched by agent? | **No** | No `browser_navigate` tool call ever reached dispatch |
| Chromium PID from agent path? | **N/A** | Browser never started through agent |
| Existing Chrome processes (system) | 22 PIDs | User's Chrome instances, not Playwright |
| headless value at runtime | `True` | `browser.headed=False` in `data/settings.json` |
| Window visible | **No** | Headless mode |

**Conclusion:** The agent pipeline never launches the browser for local Ollama models. The LLM doesn't know browser tools exist.

---

## SECTION 5: Ollama Verification

| Check | Result | Evidence |
|-------|--------|----------|
| Ollama process running | ✅ Yes | PID 7656 |
| Model loaded | ✅ qwen2.5-coder:3b | Loaded on demand by agent |
| Tokens generated | 233 total across 3 tasks | 127 + 50 + 56 |
| Latency per request | 44-52s | TTFT: 32-47s (model load from disk) |
| HTTP errors | ❌ Fixed | `OLLAMA_KEEP_ALIVE=-1` → HTTP 400. Fixed by setting to `5m` |
| API endpoint | POST /api/chat | Ollama native API (not OpenAI-compatible /v1/chat) |

---

## SECTION 6: WebSocket Verification

| Check | Result |
|-------|--------|
| WebSocket server running? | No |
| REST API server running? | No |
| Test invoked via WebSocket? | No — direct `stream_agent_loop()` call |
| Does WS add any graph logic? | No — WS is a transport layer only |

The WebSocket server (`core/routes/websocket.py`) adds:
1. Session initialization with project context
2. Request classification (DIRECT / ACTION / CODEBASE / AGENT)
3. SSE forwarding for real-time streaming

The core graph pipeline (`setup → think → finish`) is identical whether invoked via WebSocket or direct call.

---

## SECTION 7: End-to-End Trace (3 Tasks)

### Task 1: "Open GitHub and find Playwright"
```
User: "Open https://github.com in the browser and find Playwright library..."
  ↓
stream_agent_loop(endpoint=http://localhost:11434, model=qwen2.5-coder:3b)
  ↓  [0.0s]
setup_node()
  • relevant_tools_set = {browser_navigate, browser_click, browser_find, ...}
  • system prompt built with _TOOL_SHORTLIST (NO browser tools listed)
  ↓  [32.3s]
think_node() — calls Ollama POST /api/chat
  • tools_sent = 0  ← no tool schemas for local model
  • model: qwen2.5-coder:3b (Ollama PID 7656)
  • input_tokens: 4040
  • output_tokens: 127 (12.6s generation at 10.1 tok/s)
  • LLM output: PLAIN TEXT — "I'll help you find Playwright on GitHub..."
  • NO fenced code blocks → NO tool blocks parsed
  ↓  [44.9s]
route_node() — resolves tool blocks: 0 found
  ↓
tool_call_node() — no tools to execute, skipped
  ↓
finish_node() — computes metrics, emits [DONE]
  ↓  [78.2s total]
Result: "The model returned an empty response..."
         (no browser launched, no tool called)
```

### Task 2 & 3 — identical pattern, same outcome.

---

## SECTION 8: Root Cause Analysis

### The 3-blocking issues:

| # | Issue | Impact | Location |
|---|-------|--------|----------|
| 1 | `OLLAMA_KEEP_ALIVE=-1` env var | HTTP 400 from Ollama — model won't load | User env var |
| 2 | `_is_api_model=False` → `tools_sent=0` | No native function-calling schemas sent to Ollama | `nodes.py:162-165` |
| 3 | `_TOOL_SHORTLIST` missing browser tools | LLM doesn't know browser tools exist | `agent_prompts.py:43-51` |

### Fix required for local models:
The prompt must include browser tool descriptions so the LLM knows it can call ````browser_navigate\nhttps://...````. The `_TOOL_SECTIONS` dict already has the content — it just needs to be injected into the prompt for local models.

---

## FINAL CLASSIFICATION

| Metric | Value |
|--------|-------|
| Total Tasks | 3 |
| Agent Pipeline Executed (setup→think→finish) | 3/3 (100%) |
| LLM Called | 3/3 (100%) |
| Browser Tools Reached via Agent | **0/3 (0%)** |
| Direct Tool Calls | 0 |
| Mock/Fake | 0 |

### Classification: **RELEASE_BLOCKER**

The agent pipeline infrastructure works (StateGraph executes, Ollama responds), but **browser tools are completely unreachable** through the local-model agent path. The system prompt never tells the LLM that browser tools exist. The `_TOOL_SHORTLIST` constant in `agent_prompts.py:43-51` only lists 6 code tools — it doesn't include any browser tools. The actual browser tool descriptions sit unused in `_TOOL_SECTIONS` (line 53+).

**The browser tools DO work** — proven by 40/95 passing workflow tests calling `do_browser_*()` directly. But they only work via `DIRECT_TOOL_CALL`, never through the agent → LLM → tool dispatch path for local models.
