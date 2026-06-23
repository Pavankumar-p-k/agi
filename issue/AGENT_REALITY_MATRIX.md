# AGENT REALITY MATRIX
## Phase 5 — Runtime Audit Report
> Generated: 2026-06-10
> Source: C:\Users\peter\Desktop\jarvis

---

## Summary

| Category        | Count |
|-----------------|-------|
| Registered Agents | 10 |
| Selectable via CLI | 10 |
| Actually Invokable | 10 |
| Produces Output | 2+ (HERALD, NEXUS tested) |
| Uses LLM (calls tools) | 10 (base class calls `complete()`) |
| Fully Working | 9 (all except those with unloaded models) |

---

## 1. Registry

All agents are registered in `core/sub_agents/registry.py`:

| Agent | Class | Source File |
|-------|-------|-------------|
| NEXUS | NexusAgent | `core/sub_agents/agents/nexus.py` |
| FORGE | ForgeAgent | `core/sub_agents/agents/forge.py` |
| ORACLE | OracleAgent | `core/sub_agents/agents/oracle.py` |
| PHANTOM | PhantomAgent | `core/sub_agents/agents/phantom.py` |
| CIPHER | CipherAgent | `core/sub_agents/agents/cipher.py` |
| HERALD | HeraldAgent | `core/sub_agents/agents/herald.py` |
| SCRIBE | ScribeAgent | `core/sub_agents/agents/scribe.py` |
| ATLAS | AtlasAgent | `core/sub_agents/agents/atlas.py` |
| SENTINEL | SentinelAgent | `core/sub_agents/agents/sentinel.py` |
| MAESTRO | MaestroAgent | `core/sub_agents/agents/maestro.py` |

---

## 2. Agent Reality Check

### 2a. Runtime Tests (executed against the live system)

| Agent | Can Select? | Can Invoke? | Executes? | Calls Tools? | Returns Output? | Status |
|-------|-------------|-------------|-----------|--------------|-----------------|--------|
| **HERALD** | YES (`jarvis.py agent run HERALD`) | YES (SubAgent.run) | YES (LLM called, 6.2s) | No (pure text gen) | YES ("Subject: System Update Notification...") | **WORKING** |
| **NEXUS** | YES (`jarvis.py agent run NEXUS`) | YES (SubAgent.run) | PARTIAL (times out due to torch loading) | No | PARTIAL (hangs on memory init) | **PARTIAL** |
| **FORGE** | YES (`jarvis.py agent run FORGE`) | YES (SubAgent.run) | PARTIAL (LLM model "code" not found) | No | PARTIAL (error: model not found) | **BROKEN** (needs Ollama model) |
| ORACLE | YES | YES | Unknown (not tested) | No | Unknown | UNTESTED |
| PHANTOM | YES | YES | Unknown (not tested) | No | Unknown | UNTESTED |
| CIPHER | YES | YES | Unknown (not tested) | No | Unknown | UNTESTED |
| SCRIBE | YES | YES | Unknown (not tested) | No | Unknown | UNTESTED |
| ATLAS | YES | YES | Unknown (not tested) | No | Unknown | UNTESTED |
| SENTINEL | YES | YES | Unknown (not tested) | No | Unknown | UNTESTED |
| MAESTRO | YES | YES | Unknown (not tested) | No | Unknown | UNTESTED |

### 2b. Execution Flow

```
CLI (jarvis.py agent run <name> <task>)
  ? cli_commands.cmd_agent_run()
    ? agent_registry.run(name, task, mode)
      ? SubAgent.run(task, mode)
        ? get_system_prompt(mode)  (agent-specific prompts)
        ? complete(MODEL_GROUP, messages)  (LLM router call)
        ? AgentResult (output, success, duration)
```

**Key observations:**
- All agents inherit from `SubAgent` base class in `core/sub_agents/base_agent.py`
- Agents do NOT call tools — they are text-generation only (system prompt + user task ? LLM ? response)
- Agents use the `complete()` function from `core.llm_router` which routes to models by group (`analysis`, `code`, `chat`, etc.)
- Model availability is the main bottleneck — FORGE requires ollama/code, NEXUS needs ollama/analysis
- HERALD uses default `chat` model group and works because an LLM is available for that group

---

## 3. Detailed Agent Information

| Agent | Modes | Default Mode | Model Group | Max Tokens | Description |
|-------|-------|-------------|-------------|------------|-------------|
| NEXUS | research, synthesize, compare, brief | research | analysis | 2000 | Deep research, synthesis, comparison, intelligence briefs |
| FORGE | generate, debug, refactor, doc | generate | code | 4000 | Production-grade code generation, debugging, refactoring |
| ORACLE | plan, decompose, prioritize, estimate | plan | analysis | 2000 | Goal planning, task decomposition, prioritization |
| PHANTOM | scrape, extract, summarize, monitor | scrape | chat | 2000 | Web scraping, content extraction, summarization |
| CIPHER | audit, threat, harden, review | audit | analysis | 1500 | Security auditing, threat modeling, hardening guidance |
| HERALD | draft, summarize, alert, reply | draft | chat | 1500 | Message drafting, communication summarization, alerts |
| SCRIBE | docs, report, readme, changelog | docs | chat | 2000 | Technical docs, reports, READMEs, changelogs |
| ATLAS | analyze, sql, pandas, visualize | analyze | analysis | 2000 | Data analysis, SQL generation, pandas code, visualization |
| SENTINEL | diagnose, optimize, predict, report | diagnose | analysis | 2000 | System health monitoring, diagnostics, optimization |
| MAESTRO | route, orchestrate | route | chat | 2000 | Routes tasks to the right sub-agent(s), orchestrates |

---

## 4. Issues Found

1. **No tool integration** — Agents generate text only. They do not call any tools (semantic_search, bash, etc.) during execution. This means they cannot perform actions — they can only reason and respond with text.
2. **Model dependency** — Agents depend on specific Ollama models being available. NEXUS/ORACLE/CIPHER/ATLAS/SENTINEL need model group "analysis", FORGE needs "code". If these models aren\'t installed, the agents fail.
3. **NEXUS deep research integration** — NEXUS has special code to call `deep_research()` from `tools.deep_research`, but this module may not exist.
4. **No cancellation support** — `cancel_event` parameter exists in base class but is never wired from CLI.
5. **MAESTRO agent** — Routes tasks to other agents but has no actual routing logic beyond text generation.

---
