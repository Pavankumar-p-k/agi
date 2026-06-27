# JARVIS Architecture

## The Vision in One Sentence

JARVIS is an AI Operating System whose brain remains permanent while every model, agent, service, and tool is an interchangeable capability provider selected by evidence and continuously improved through learning.

---

## 1. Constitution (Stable)

The 12 laws below define the architecture's inviolable constraints. They rarely change — only when the architecture itself changes.

### Law 1 — Brain First

The JARVIS Brain always owns planning, reasoning, decision-making, orchestration, recovery, learning, and memory. No provider, model, or plugin is allowed to bypass or replace the brain.

### Law 2 — One Pipeline

```
User
  ↓
Planner
  ↓
Decision
  ↓
Capability
  ↓
Provider
  ↓
Workflow
  ↓
Learning
  ↓
Memory
```

Every request follows this pipeline.

### Law 3 — Capability, Never Provider

The planner requests capabilities (coding, browser, vision, deployment, messaging) — never specific providers (Claude Code, Codex, Jules, GPT, Gemini). Providers are selected later.

### Law 4 — Providers Are Replaceable

Every external system is optional. Users can install, update, disable, or uninstall providers at any time. Removing them must never break JARVIS.

### Law 5 — Offline Is Always Possible

A fresh installation with only the core should still work: planning, reasoning, coding (Forge), workflows, memory, research, recovery. External providers only improve results.

### Law 6 — Evidence Over Opinions

Routing decisions are based on measurable evidence (benchmark quality, historical success, workflow calibration, health, latency, cost, confidence). Never hard-coded preferences.

### Law 7 — Learn From Everything

Every completed workflow should improve at least one of: provider calibration, workflow calibration, benchmark data, generalized principles, memory, strategy. Nothing important should be "forgotten."

### Law 8 — Plugins Extend, Never Control

Plugins add capabilities. They never become the orchestrator. The brain remains in charge.

### Law 9 — Stable Core, Fast Ecosystem

The core changes rarely. The ecosystem evolves constantly. Hundreds of providers can come and go without architectural changes.

### Law 10 — No Duplicate Systems

Before adding any subsystem ask: can this extend an existing one? If yes, extend. If no, only then create something new.

### Law 11 — Explain Every Decision

JARVIS should always be able to answer: why was this provider chosen, why was this workflow selected, why was this recovery attempted, why did confidence change, why did strategy change. No "black box" decisions.

### Law 12 — Evolution Without Rewrites

Future versions should primarily improve decision quality, learning quality, calibration, generalization, and the plugin ecosystem — not replace the architecture.

---

## 2. Core Architecture (Stable)

These components form the permanent brain. Changes here are uncommon and require strong justification.

| Component | Location | Responsibility |
|-----------|----------|----------------|
| **Planner** | `core/planner/` | Decomposes goals, enforces step sequences, owns workflow completion |
| **Decision** | `core/decision/` | Evidence collection, weighted scoring, explainable selection |
| **Capability Registry** | `core/providers/` | Maps capability names to available providers |
| **Workflow Engine** | `core/workflow/` | Durable step execution, retry, compensation, crash recovery |
| **Learning** | `core/workflow/` (calibration) | Provider + workflow calibration from execution history |
| **Memory** | `core/long_term_memory/` | Knowledge consolidation, experience extraction, behavior adaptation |
| **Activity Graph** | `core/activity/` | Persistent DAG of goals, subgoals, agents, tools, artifacts |
| **Strategy** | `core/strategy/`, `core/strategy_v2/` | Candidate generation, outcome prediction, tradeoff analysis |

### Data Flow

```
User Goal
  ↓
Planner (decompose → route → enforce)
  ↓
Decision Engine (collect evidence → score → select)
  ↓
Capability Registry (resolve capability → available providers)
  ↓
Provider (execute work)
  ↓
Workflow Engine (durable steps, retry, compensation)
  ↓
Activity Graph (record lineage)
  ↓
Learning Systems (calibrate, extract, synthesize)
  ↓
Memory (store, consolidate, adapt)
```

---

## 3. Extension Points (Evolving)

New functionality enters through these seams. Changes here are routine and expected.

| Extension Point | Mechanism | Examples |
|-----------------|-----------|----------|
| **Providers** | Capability-based implementations | Claude Code, Forge, Jules, Playwright, Telegram |
| **Plugins** | Skill manifests + handlers | Custom workflows, integrations |
| **Workflow Templates** | Step sequences in activity store | Build→Test→Deploy, Research→Code→Email |
| **Decision Dimensions** | New `EvidenceDimension` in evidence.py | future_value, portfolio_score |
| **Capability Manifests** | Provider registration metadata | Languages, frameworks, project sizes supported |
| **Benchmarks** | New task suites in `benchmarks/` | Domain-specific quality evaluations |
| **Learning Signals** | New outcome fields in calibration | Recovery patterns, error categories |

---

## 4. Roadmap (Changing)

### v3.x — Intelligence & Quality

- Portfolio decision (recursive candidates)
- Long-horizon evidence (future value, maintenance cost, learning value)
- Self-tuning decision weights via experiment loop
- Pattern learning (principles feed back into planning and scoring)
- Better calibration with richer context
- Larger benchmark suites

### v4 — Scale

- Thousands of benchmark tasks
- Long-running autonomous projects
- Enterprise plugin marketplace
- Distributed execution
- Team collaboration
- Cross-device continuity
- Larger knowledge bases

---

## Engineering Rule

Before merging any architectural change, answer:

1. Does this violate one of the 12 laws?
2. Does it introduce a second way to solve an existing problem?
3. Can it be expressed as a new provider, capability, workflow, plugin, evidence dimension, or learning signal instead?
4. Does it preserve offline functionality?
5. Does it keep providers replaceable?

If any answer is "no," the proposal needs another design review.
