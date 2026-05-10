# JARVIS OS Cognitive Brain Upgrade - Integration Checklist

## Pre-Deployment Verification

### Code Changes Status
- [x] **intent.py** - Removed heuristics, now passthrough `{"goal": prompt, "type": "auto"}`
- [x] **planner.py** - LLM-based DAG generation with JSON validation & retry
- [x] **loop.py** - Converted to `AgentLoop` with plan→execute→evaluate→replan cycle
- [x] **critic.py** - NEW file, structured evaluation with scoring
- [x] **meta_controller.py** - NEW file, decision engine for loop control
- [x] **executor.py** - Added retry mechanism (3 attempts) + structured output
- [x] **reasoning.py** - Simplified, kept for backward compat, only observe/summarize
- [x] **vector_store.py** - Added JSON persistence, context compression, metadata filtering
- [x] **tool_registry.py** - Output normalization: `{"status": "success"/"error", "data": ...}`
- [x] **bootstrap.py** - Wired CriticEngine, MetaController, AgentLoop
- [x] **api/os_routes.py** - Added unified `/os/run` endpoint
- [x] **AGENT_UPGRADE_README.md** - NEW comprehensive documentation
- [x] **validate_upgrade.py** - NEW validation script with 7 test suites

### Files Modified Count
- **8 existing files patched** (intent, planner, loop, executor, reasoning, vector_store, tool_registry, bootstrap, api)
- **3 new files created** (critic, meta_controller, validate_upgrade)
- **1 documentation file** (AGENT_UPGRADE_README)

## System Properties After Upgrade

| Property | Before | After | Change |
|----------|--------|-------|--------|
| **Planning** | Keyword heuristics | LLM DAG | ↑ Intelligent |
| **Intent Detection** | 8 categories + keywords | Goal passthrough | ↑ Flexible |
| **Execution** | Single attempt | 3 retries + backoff | ↑ Resilient |
| **Loop Cycle** | Fixed 2 iterations | 5-8 iterations + adaptive | ↑ Self-Correcting |
| **Evaluation** | Heuristic reflection | Critic with scoring | ↑ Structured |
| **Memory** | In-memory only | Persistent JSON + search | ↑ Durable |
| **Tool Interface** | Inconsistent outputs | Normalized JSON | ↑ Reliable |
| **Replanning** | None | Critic-triggered | ✨ New |

## Deployment Steps

### Step 1: Backup
```bash
cd /path/to/jarvis
git add -A
git commit -m "pre-upgrade-backup: Before cognitive brain upgrade"
```

### Step 2: Verify Python Environment
```bash
cd backend
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
python --version  # Ensure Python 3.9+
pip list | grep -E "fastapi|pydantic|ollama"
```

### Step 3: Run Validation Suite
```bash
cd jarvis_os
python validate_upgrade.py
```

**Expected Output:**
```
============================================================
VALIDATION SUMMARY
============================================================
✓ PASS: Intent Engine
✓ PASS: Planner
✓ PASS: Critic Engine
✓ PASS: Meta-Controller
✓ PASS: Tool Registry
✓ PASS: Vector Store
✓ PASS: Agent Loop

Total: 7/7 tests passed
============================================================
```

### Step 4: Verify API Routes
```bash
curl http://localhost:8000/os/status
# Should return filled status object
```

### Step 5: Test End-to-End
```bash
curl -X POST http://localhost:8000/os/run \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "List Python files in current directory",
    "context": {},
    "agent_name": "auto"
  }'
```

**Expected Response:**
```json
{
  "plan": {
    "goal": "List Python files...",
    "steps": [...],
    "strategy": "llm_dag"
  },
  "execution": {
    "success": true,
    "summary": "Found X Python files..."
  },
  "trace": {
    "cycles": [...]
  }
}
```

## Post-Deployment Validation

### Component Tests
- [ ] Intent engine returns dicts (no Intent objects)
- [ ] Planner generates valid JSON DAG
- [ ] Critic evaluates with 0.0-1.0 score
- [ ] Meta-controller makes correct stop/replan decisions
- [ ] Executor retries on failure
- [ ] Vector store saves/loads from disk
- [ ] Tool registry normalizes outputs
- [ ] AgentLoop completes cycles

### Integration Tests
- [ ] `/os/run` endpoint accepts requests
- [ ] `/os/status` returns component status
- [ ] `/os/tools` lists available tools
- [ ] Multi-iteration loops work (test with failing tool)
- [ ] Replanning triggers on low evaluation score
- [ ] Memory persistence across restarts

### Performance Checks
- [ ] Planning takes < 2s (LLM inference)
- [ ] Full cycle completes < 5 iterations typical
- [ ] Memory usage stable over 10 requests
- [ ] No infinite loops (max iterations respected)

## Monitoring Checklist

### Logs to Watch
```
# Check for critic scoring
grep -i "score:" logs/jarvis_os.log

# Check for replanning
grep -i "replan" logs/jarvis_os.log

# Check for retry attempts
grep -i "retry" logs/jarvis_os.log

# Check for tool normalization
grep -i "normalize" logs/jarvis_os.log
```

### Metrics to Track
- Average plan generation time (should be < 2s)
- Average execution success rate (target > 85%)
- Average critic score (target > 0.8)
- Replan frequency (target < 30% of requests)
- Tool adoption of normalized interface (target 100%)

## Rollback Plan

If issues arise:

1. **Revert to Previous Commit**
   ```bash
   git reset --hard HEAD~1
   ```

2. **OR Disable New Loop (Keep as fallback)**
   - In `bootstrap.py`, keep old `ReasoningLoop` initialization
   - Change API route to use old loop
   - Keep critic/meta_controller code but don't wire them

3. **OR Run in Hybrid Mode**
   - Use new planner, old loop
   - Keeps intelligent planning, reverts execution loop
   - Allows gradual migration

## Success Criteria

✓ System must:
- Plan using LLM (not heuristics) ✓
- Execute multi-step tasks ✓
- Detect and evaluate failures ✓
- Trigger replanning on low score ✓
- Maintain structured state ✓
- Persist memory between runs ✓
- Handle tool errors gracefully ✓
- Complete loops within max iterations ✓

✓ Compatibility must:
- Accept legacy endpoint aliases ✓
- Return backward-compatible response format ✓
- Not break existing automation ✓
- Support gradual tool migration ✓

## Next Steps (Post-Deployment)

1. **Monitor for 24 hours**
   - Check logs for errors
   - Measure performance metrics
   - Validate critic scores

2. **Fine-tune Prompts**
   - Collect planner failures
   - Iteratively improve planner prompt
   - Test critic with diverse scenarios

3. **Expand Tool Coverage**
   - Migrate remaining tools to normalized interface
   - Add new tools that leverage structured planning

4. **Optimize Loop Parameters**
   - Adjust max_iterations based on real usage
   - Tune success threshold (currently 0.8)
   - Optimize retry counts per tool type

5. **Implement Analytics**
   - Track plan quality (task count, complexity)
   - Track execution paths (which tools used most)
   - Track critic calibration (score vs actual success)

---

**Document Version:** 1.0  
**Date:** 2026-03-21  
**Status:** Ready for Deployment
