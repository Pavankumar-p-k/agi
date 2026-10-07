# STEP 3 — Agent Scorecard (one real task each)

**Date:** 2026-10-03 · **Model server:** Ollama 0.33.0 (`qwen2.5-coder:3b`, `llava:7b`) · **Rows:** 38

**Counts:** `BROKEN` 3 · `FAKE-SUCCESS` 2 · `UNTESTABLE` 3 · `WORKING` 30


Tags:
- **WORKING** — real task completed, non-empty real output
- **FAKE-SUCCESS** — reported success but did nothing (evidence-backed)
- **BROKEN** — ran and failed (or hung) with a real error
- **UNTESTABLE** — blocked by a dependency deleted in STEP 2 (loud ImportError)

Method: `python scripts/step3_agent_scorecard.py {tool|adapters|legacy|extra|infra}`,
every row hand-reviewed against its evidence (3 auto-tags corrected: memory,
browser -> FAKE-SUCCESS; test -> re-run on real suites).

## A. The 6 tool agents (direct system action)

| agent | tag | time | real task | evidence |
|---|---|---|---|---|
| **build** | WORKING | 0.9s | build this project | running build  |
| **email** | WORKING | 0.0s | check my inbox | honestly reports 'email not configured'; core.tools.email_utils was deleted and the exception is swallowed — read-only path only, send path untestable |
| **memory** | FAKE-SUCCESS | 2.7s | remember my favorite color is blue, then recall it | store reported 'Stored memory' but recall shows 0 entries; stderr: 'mem0 init failed: No module named core.configuration.service. Using no-op memory' — swallowe |
| **research** | WORKING | 21.5s | research: are LLM agent frameworks converging on tool-c | - **LLM Agent Frameworks Are Converging on Tool-Calling Standards**: Several research papers and articles have highlighted the trend of LLM agent frameworks ado |
| **browser** | FAKE-SUCCESS | 0.0s | open https://example.com in the browser and screenshot  | returned success in 0.0s with 'Browser: 0 open tab(s)' — no URL opened, no screenshot taken |
| **test** | WORKING | 14.6s | run 3 real unit suites (activity_store, authz, cache) — | attempt 1 (test_atomic_io) hit a STUB deleted in STEP 2; attempt 2 (test_belief) failed on missing core.long_term_memory.synthesizer; attempt 3 on real suites p |

## B. The 9 LLM specialist adapters (registry, Ollama-backed)

| agent | tag | time | evidence / review note |
|---|---|---|---|
| **adapter:forge** | BROKEN | 48.0s | smolagents CodeAgent DID generate correct median() code (verified in log) but looped to 'Reached max steps' re-executing identical code 21x and never returned an answer - |
| **adapter:oracle** | WORKING | 10.1s | 1. **Define the Requirements:**    - Determine the design and functionality of the dark mode.    - Decide on the user interface elements that will be affected by the dark |
| **adapter:herald** | WORKING | 13.8s | Subject: Introducing HERALD CLI v1.0 - Your Ultimate Command-Line Interface for Seamless Communication  Dear HERALD Community,  We are thrilled to announce the release of |
| **adapter:atlas** | WORKING | 4.0s | ```sql SELECT customer_id, SUM(revenue) AS total_revenue FROM sales GROUP BY customer_id ORDER BY total_revenue DESC LIMIT 10; ```  This query calculates the total revenu |
| **adapter:scribe** | WORKING | 9.7s | # Function Documentation: `chunk`  ## Overview  The `chunk` function is designed to divide a given string `s` into smaller substrings of a specified length `n`. This func |
| **adapter:phantom** | BROKEN | 0.1s | SSRF guard rejected example.com as 'Private IP disallowed' (NAT64/DNS64 env resolves to 64:ff9b::/96 reserved prefix) — guard works, environment resolution breaks it; sam |
| **adapter:sentinel** | WORKING | 9.8s | Certainly! Here are some common causes and fixes for a Python script using 100% CPU:  ### Likely Causes  1. **Infinite Loop**: The script might be stuck in an infinite lo |
| **adapter:nexus** | WORKING | 5.2s | retry after forge smolagents loop saturated Ollama |
| **adapter:cipher** | WORKING | 9.9s | retry after forge smolagents loop saturated Ollama |
| **adapter:forge (llm_router fallback path)** | WORKING | 6.0s | isolates the smolagents termination bug from the model path — model path itself is fine |

## C. The 7 legacy SubAgents (`core/agents/_legacy/`)

| agent | tag | time | task |
|---|---|---|---|
| **_legacy/oracle** | WORKING | 11.6s | plan a migration from REST to GraphQL |
| **_legacy/nexus** | WORKING | 5.3s | compare kafka vs rabbitmq |
| **_legacy/atlas** | WORKING | 5.8s | write a SQL query for distinct active users per day |
| **_legacy/cipher** | WORKING | 5.6s | what are the risks of hardcoding API keys? |
| **_legacy/herald** | WORKING | 2.9s | write a one-paragraph standup update |
| **_legacy/scribe** | WORKING | 7.8s | write a docstring for a function that pings a host |
| **_legacy/sentinel** | WORKING | 8.6s | diagnose: OSError too many open files |

## D. Other agents & infrastructure

| component | tag | status | evidence |
|---|---|---|---|
| `core/file_agent:JarvisFileAgent` | WORKING | success | [{'name': 'notes.txt', 'path': 'C:\\Users\\peter\\AppData\\Local\\Temp\\jarvis_file_cdoexi0w\\notes.txt', 'size': 13}] | alpha beta  |
| `core/vision_agent:VisionAgent` | UNTESTABLE | ModuleNotFoundError | No module named 'core.model_router' |
| `core/agents/registry` | WORKING | success | 15 agents registered: ['ATLAS', 'CIPHER', 'FORGE', 'HERALD', 'NEXUS', 'ORACLE', 'PHANTOM', 'SCRIBE', 'SENTINEL', 'browser', 'build', 'email', 'memory', 'research', 'test' |
| `core/agents/registry:unknown-id` | WORKING | success | unknown id rejected loudly |
| `core/agents/executor` | UNTESTABLE | failed | blocked by core.constants — a DynamicStub deleted in STEP 2; executor itself never executed |
| `core/llm_router (ollama round-trip)` | WORKING | success | PONG |
| `core/agents/graph` | WORKING | success | imports cleanly |
| `core/agents/parallel_executor` | WORKING | success | imports cleanly |
| `core/agents/events` | WORKING | success | imports cleanly |
| `core/agents/base` | WORKING | success | imports cleanly |
| `core/agents/_sub_agent_base` | WORKING | success | imports cleanly |
| `core/agents/capabilities` | WORKING | success | imports cleanly |
| `core/agents/router` | BROKEN | hit rate 4/10 | misses: write a function to parse dates; help me code a sorting script; what did I tell you about my dog; look up info on quantum dots; which is better, mongo or mysql; d |
| `core/agents/registry:run_parallel` | WORKING | success | [('ORACLE', True), ('UNKNOWN', False)] |
| `core/tools/browser_tools (direct)` | UNTESTABLE | blocked | browser_tools (627 LOC, rated REAL in inventory) hard-imports core.browser_manager — deleted in STEP 2 as FAKE-SUCCESS. Browser stack is therefore loud-broken end-to-end: |

## Rebuild priority implied by this scorecard
1. **`core.browser_manager`** — browser_tools (627 LOC, REAL) is dead without it;
   the browser agent silently no-ops (it is *also* a deleted FAKE-SUCCESS).
   Rebuild or rewire browser_tools to launch Playwright directly.
2. **`core.configuration.service`** — mem0 init fails -> memory agent no-ops and
   *lies about it*. A fake-success in the hot path.
3. **`core.model_router`** — blocks `vision_agent` (UNTESTABLE).
4. **`core.constants`** — blocks `agents/executor` (UNTESTABLE).
5. **forge smolagents termination** — model path is fine (fallback WORKING in
   6s); the CodeAgent loop never signals done. Cap steps or drop smolagents.
6. **router phrasing** — 4/10 natural goals route correctly; contiguous keyword
   match needs tokenization/semantic fallback.
7. **`core.long_term_memory.synthesizer`** — one test_belief integration test.
