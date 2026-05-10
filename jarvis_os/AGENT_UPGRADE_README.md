# JARVIS OS Agent Brain Upgrade

## Overview

This document describes the production-grade cognitive agent brain upgrade applied to the JARVIS OS system. The changes transform the system from heuristic-based automation to an LLM-driven autonomous agent capable of self-correction and iteration.

## Key Architectural Changes

### 1. Intent Engine → Goal Passthrough
- **File**: `core/intent.py`
- **Change**: Removed keyword-based intent classification
- **Output**: Simple goal passthrough: `{"goal": prompt, "type": "auto"}`
- **Benefit**: Intent determination now deferred to LLM planner, reducing brittleness

### 2. Planner → LLM-Based DAG
- **File**: `core/planner.py`
- **Change**: Replaced heuristic rules with LLM generation
- **Output**: Strict JSON DAG format with task dependencies
- **Format**:
```json
{
  "tasks": [
    {
      "id": "t1",
      "tool": "tool_name",
      "args": {},
      "deps": [],
      "success": ""
    }
  ]
}
```
- **Retry**: Failed JSON parsing triggers automatic retry with correction prompt
- **Fallback**: Graceful degradation to `assistant_chat` if LLM fails

### 3. Agent Loop → True Cognitive Loop
- **File**: `core/loop.py`
- **Class**: `AgentLoop` (renamed from `ReasoningLoop`)
- **Cycle**: Plan → Execute → Evaluate → (Replan or Stop)
- **Iterations**: configurable 5-8 max iterations
- **Control**: Meta-controller decides stop/replan based on evaluation score

### 4. Reasoning Engine → Critic Engine
- **File**: `core/critic.py` (new)
- **Purpose**: Structured evaluation of execution outcomes
- **Triggers**: Automatic replanning when score < 0.8
- **Output Format**:
```json
{
  "score": 0.0,
  "failure_type": "",
  "issues": [],
  "fix_strategy": "",
  "replan": true
}
```

### 5. Memory → Persistent Smart Store
- **File**: `memory/vector_store.py`
- **Features**:
  - JSON-based persistence with auto-save
  - Semantic search via token matching
  - Context compression (truncate > 500 chars)
  - Metadata filtering by agent scope
  - Top-K retrieval (configurable, default 5)

### 6. Executor → Async-Ready Retry Engine
- **File**: `core/executor.py`
- **Features**:
  - 3-attempt retry with exponential backoff
  - DAG execution support (sequential placeholder)
  - Dependency respecting (stub)
  - Structured output validation
  - Policy enforcement at step level

### 7. Tool Interface → Standardized Format
- **File**: `tools/tool_registry.py`
- **Standard Output**:
```json
{
  "status": "success|error",
  "data": {},
  "error": ""
}
```
- **Auto-Normalization**: Registry automatically wraps non-standard outputs
- **Error Handling**: All exceptions converted to structured errors

### 8. Meta-Controller → Loop Decision Maker
- **File**: `core/meta_controller.py` (new)
- **Decisions**:
  - `stop`: When score ≥ 0.8 or max iterations reached
  - `replan`: When critic indicates issues found
  - `continue`: Proceed with next iteration
- **Max Iterations**: 5 (configurable)

### 9. API → Unified Endpoints
- **File**: `backend/api/os_routes.py`
- **Main Endpoint**: `POST /os/run`
- **Backup Routes**: `/os/agents/run`, `/os/agent/think` (aliases)
- **Status Check**: `GET /os/status`
- **Tool Catalog**: `GET /os/tools`

## Integration Points

### Bootstrap Initialization
- **File**: `jarvis_os/bootstrap.py`
- **Changes**:
  - Instantiate `CriticEngine` with models
  - Create `MetaController` with max_iterations=5
  - Wire `AgentLoop` with all components
  - Replace old `ReasoningLoop` with new `AgentLoop`

### Backward Compatibility
- Old `ReasoningEngine` methods simplified but retained
- `summarize()` still available for legacy code
- API accepts legacy endpoint aliases
- Agent.handle_prompt() works with new loop

## System Properties

| Property | Value | Notes |
|----------|-------|-------|
| **Planning Method** | LLM DAG | Self-correcting via retry |
| **Execution Strategy** | Sequential + Retry | Up to 3 attempts per step |
| **Loop Iterations** | 5-8 | Configurable max iterations |
| **Evaluation** | Critic Engine | Structured scoring (0.0-1.0) |
| **Success Threshold** | 0.8 score | Auto-stop above threshold |
| **Memory Persistence** | JSON file | `vector_store.json` |
| **Tool Outputs** | Structured JSON | Auto-normalized by registry |
| **Error Handling** | Structured errors | `{"status": "error", "error": "..."}` |

## Prompts (LLM-Facing)

### Planner Prompt
```
Generate a DAG plan for the goal: <PROMPT>

Available tools: <TOOL_LIST>

Output STRICT JSON only:
{
  "tasks": [
    {
      "id": "t1",
      "tool": "tool_name",
      "args": {},
      "deps": [],
      "success": ""
    }
  ]
}
```

### Critic Prompt
```
Evaluate the execution of goal: <GOAL>

Plan: <PLAN_JSON>
Execution results: <RESULTS_JSON>

Output STRICT JSON only:
{
  "score": 0.0,
  "failure_type": "",
  "issues": [],
  "fix_strategy": "",
  "replan": true
}
```

## Usage Example

### Direct Python
```python
from jarvis_os.bootstrap import build_jarvis_os

runtime = build_jarvis_os()
result = runtime.handle_prompt(
    "List all Python files in src/",
    context={"workspace": "/path/to/project"}
)
print(result["execution"]["summary"])
```

### REST API
```bash
curl -X POST http://localhost:8000/os/run \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Fix the failing test in tests/unit/test_api.py",
    "context": {"workspace": "/path/to/project"},
    "agent_name": "auto"
  }'
```

### Response Structure
```json
{
  "plan": {...},
  "execution": {
    "success": true,
    "summary": "Fixed test by...",
    "results": [...]
  },
  "trace": {
    "cycles": [
      {
        "cycle_index": 1,
        "stages": [
          {"name": "plan", "status": "..."},
          {"name": "execute", "status": "..."},
          {"name": "evaluate", "status": "..."}
        ]
      }
    ]
  }
}
```

## Migration Guide

### For Existing Code
1. **Intent Parsing**: Old code expecting `Intent` objects gets dict now
   - Update: `intent.name` → `intent.get("type", "auto")`
   
2. **Planner Output**: Still returns `Plan` object with DAG steps
   - No changes needed; interface preserved

3. **Tool Handlers**: Wrap outputs in `{"status": "success"/"error", "data": {...}}`
   - Registry auto-normalizes; no changes required unless custom tools exist

4. **Loop Execution**: `AgentLoop.run()` supports `**kwargs` for backward compat
   - Old parameters are accepted but ignored

### Testing New System
```python
from jarvis_os.core.intent import IntentEngine
from jarvis_os.core.planner import PlanningEngine
from jarvis_os.core.critic import CriticEngine
from jarvis_os.core.meta_controller import MetaController
from jarvis_os.core.loop import AgentLoop

# Intent: simple goal passthrough
intent = intent_engine.parse("Do something")
assert intent == {"goal": "Do something", "type": "auto"}

# Plan: LLM generates DAG
plan = planner.build_plan("...", intent, analysis)
assert "tasks" in str(plan.to_dict())

# Eval: Critic scores execution
eval = critic.evaluate("...", plan, execution)
assert 0.0 <= eval["score"] <= 1.0

# Meta: Controller decides next action
decision = meta.decide(iteration=1, evaluation=eval)
assert decision["action"] in {"stop", "replan", "continue"}
```

## Performance Targets

- **Planning**: < 2s (LLM inference)
- **Execution**: < 30s (per iteration, depends on tools)
- **Evaluation**: < 1s (LLM inference)
- **Full Cycle**: < 5 iterations typical case
- **Memory Footprint**: < 50MB (typical use)

## Troubleshooting

### LLM Planner Returns Invalid JSON
- **Symptom**: "Fallback to assistant_chat"
- **Cause**: Model output not strict JSON
- **Fix**: Retry prompt is automatically triggered; check model logs

### Execution Keeps Replanning
- **Symptom**: Loops through 5 iterations without success
- **Cause**: Critic score stays < 0.8; issues with tool or planning
- **Fix**: Check tool outputs are returning `{"status": "success", "data": {...}}`

### Memory Persistence Issues
- **Symptom**: `vector_store.json` not created/updated
- **Cause**: File permissions or path issues
- **Fix**: Ensure write access to `jarvis_os/` directory

<END_OF_README>
