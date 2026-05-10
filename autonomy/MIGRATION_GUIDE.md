# JARVIS AUTONOMOUS — Complete Migration Guide

## What This Changes vs What It Doesn't

### DOES NOT CHANGE (all existing code untouched)
```
jarvis_main.py               ← still works exactly as before
core/world_state.py          ← unchanged
core/cognitive_engine.py     ← unchanged
core/decision_engine.py      ← unchanged
core/simulation_engine.py    ← unchanged
core/fusion_engine.py        ← unchanged
core/personality_layer.py    ← unchanged
memory/semantic_store.py     ← unchanged
memory/insight_engine.py     ← unchanged
orchestrator/brain.py        ← unchanged (JarvisBrain 8-agent)
adb/adb_controller.py        ← unchanged
notifications/notification_hub.py ← unchanged
voice/voice_pipeline.py      ← unchanged
api/gateway.py               ← unchanged (/chat /health /state untouched)
All existing Flutter API     ← unchanged
```

### ADDS (new files only)
```
jarvis_autonomous/
  jarvis_main_autonomous.py  ← replaces jarvis_main.py as entry point
  l1_brain/brain_layer.py    ← wraps JarvisBrain, adds routing
  l2_assistant/assistant_layer.py ← CodebaseIndexer + Codex integration
  l3_executor/executor_layer.py   ← TaskPlanner + Sandbox + AuditLog
  l4_controller/controller_layer.py ← SafetyGuard + Terminal + FS + ADB
  core/autonomous_orchestrator.py   ← wires all 4 layers
  api/autonomous_routes.py          ← 9 new API endpoints
  cli/jarvis_cli.py                 ← think/plan/run/status/memory/exec/chat
  config/personality.yaml           ← JARVIS personality config
  test_autonomous.py                ← integration test suite
  requirements_autonomous.txt
```

---

## Step-by-Step Migration

### Step 1 — Copy files
```bash
# Copy the entire jarvis_autonomous/ folder to your project root
cp -r jarvis_autonomous/ /path/to/your/jarvis/project/

# Your project structure should now be:
# /your/project/
#   jarvis_main.py                  ← OLD entry (keep it)
#   jarvis_main_autonomous.py       ← NEW entry (use this)
#   core/
#   memory/
#   orchestrator/
#   ...all existing files...
#   l1_brain/
#   l2_assistant/
#   l3_executor/
#   l4_controller/
#   cli/
#   api/autonomous_routes.py        ← new
#   config/personality.yaml         ← new
```

### Step 2 — Install new dependencies
```bash
pip install httpx>=0.26.0 sentence-transformers>=2.6.0

# Optional for full L4:
pip install pyautogui selenium webdriver-manager plyer psutil
```

### Step 3 — Pull Ollama models (if not already done)
```bash
ollama pull qwen3:4b          # L1 Brain + L3 planning
ollama pull qwen2.5-coder:3b  # L2 code completion/fix
ollama pull deepseek-r1:1.5b  # L2 code explanation
```

### Step 4 — Run integration tests
```bash
cd /your/project
python -m pytest jarvis_autonomous/test_autonomous.py -v
# OR
python jarvis_autonomous/test_autonomous.py
```
All 60+ tests should pass. They run without starting Ollama.

### Step 5 — Start the autonomous server
```bash
python jarvis_main_autonomous.py
```
Expected output:
```
  JARVIS AUTONOMOUS v3.0 — Multi-Layer Intelligence
  L1 Brain → L2 Assistant → L3 Executor → L4 Controller
  ...
  [BOOT]  1/21 WorldState ✓
  [BOOT]  2/21 Memory ✓
  ...
  [BOOT] 18/21 L1 BrainLayer ✓
  [BOOT] 19/21 L2 AssistantLayer ✓ (scanning .)
  [BOOT] 20/21 L3 ExecutorLayer ✓
  [BOOT] 21/21 L4 ControllerLayer ✓
  [BOOT] AutonomousOrchestrator wired ✓
  [BOOT] Autonomous routes mounted ✓
  JARVIS AUTONOMOUS ONLINE — http://0.0.0.0:8000
```

### Step 6 — Verify all 4 layers
```bash
curl http://localhost:8000/layers/status | python -m json.tool
```
Expected:
```json
{
  "layers": {
    "L1_brain": true,
    "L2_assistant": true,
    "L3_executor": true,
    "L4_controller": true,
    "orchestrator": true
  },
  "memory": {"online": true, "stats": {"total": 42}},
  "safety": {"recent_blocks": []}
}
```

### Step 7 — Test the CLI
```bash
python cli/jarvis_cli.py status
python cli/jarvis_cli.py think "what should I focus on today?"
python cli/jarvis_cli.py plan "build a REST API for user management"
python cli/jarvis_cli.py chat
```

---

## Environment Variables
```bash
# Required
JARVIS_DB=database.db           # SQLite path
JARVIS_YAML=config/personality.yaml

# Server
JARVIS_HOST=0.0.0.0
JARVIS_PORT=8000

# Optional
JARVIS_ADB_IP=192.168.1.x       # Android device IP
JARVIS_MIC=true                  # Enable voice input
JARVIS_PROJECT=.                 # Codebase root for L2 indexing
JARVIS_CODEX=http://localhost:11435  # Codex server URL
JARVIS_SERVER=http://localhost:8000  # For CLI
```

---

## New API Endpoints

All new. Existing endpoints (/chat /state /tool /health) are unchanged.

```
POST /think              Full 4-layer routing
POST /plan               L3 dry-run plan generation
POST /execute            L3 full execution loop
POST /assist             L2 code assistant actions
GET  /memory/search      Semantic memory search
POST /system/action      L4 direct system control
GET  /layers/status      All 4 layer health check
GET  /executions/recent  L3 execution audit log
GET  /safety/blocks      L4 SafetyGuard block log
```

### /think — main entry
```bash
curl -X POST http://localhost:8000/think \
  -H "Content-Type: application/json" \
  -d '{"text": "create a Python script that monitors disk usage"}'
```
Response:
```json
{
  "reply": "Done. 3 steps completed.\nprint(shutil.disk_usage('/'))...",
  "intent": "task",
  "emotion": "neutral",
  "confidence": 0.87,
  "route": "executor",
  "source": "l3_executor",
  "plan": ["Step 1: import shutil", "Step 2: monitor loop", "Step 3: alerts"],
  "exec_output": "Disk: 256GB total, 180GB used (70%)",
  "latency_ms": 2341
}
```

### /plan — dry run
```bash
curl -X POST http://localhost:8000/plan \
  -d '{"goal": "build a REST API", "dry_run": true}'
```

### /execute — run task
```bash
curl -X POST http://localhost:8000/execute \
  -d '{"goal": "create a backup script", "dry_run": false}'
```

### /system/action — L4 direct
```bash
# Run terminal command
curl -X POST http://localhost:8000/system/action \
  -d '{"action": "terminal", "params": {"cmd": "git status"}}'

# Open app
curl -X POST http://localhost:8000/system/action \
  -d '{"action": "app_open", "params": {"app": "chrome"}}'

# Read file
curl -X POST http://localhost:8000/system/action \
  -d '{"action": "file_read", "params": {"path": "/home/pavan/notes.txt"}}'
```

---

## Full Example Flow

**User:** "write a Python function that calculates fibonacci numbers and test it"

```
1. CLI / Flutter / voice sends to /think

2. L1 Brain (JarvisBrain 8-agent pipeline):
   ClassifierAgent → intent="task", topic="fibonacci, python, testing"
   EmotionAgent    → emotion="neutral"
   ModelRouter     → route=EXECUTOR
   ReasoningPlanner → 5-step plan:
     ["Import math", "Define fib(n)", "Add memoization",
      "Write pytest tests", "Run tests"]

3. L3 Executor (ExecutionLoop):
   Step 1: code = "import functools" → sandbox OK → executed ✓
   Step 2: code = """
     @functools.lru_cache(maxsize=None)
     def fib(n):
         if n < 2: return n
         return fib(n-1) + fib(n-2)
   """ → sandbox OK → executed ✓
   Step 3: code = "print([fib(i) for i in range(10)])"
           → executed → output: "[0, 1, 1, 2, 3, 5, 8, 13, 21, 34]" ✓
   Step 4: code = """
     def test_fib():
         assert fib(0) == 0
         assert fib(1) == 1
         assert fib(10) == 55
     test_fib()
     print("All tests passed")
   """ → executed → output: "All tests passed" ✓
   Step 5: verify → all steps done → SUCCESS

4. AuditLog: saved to exec_audit table with audit_id=47

5. OrchestratorResult:
   reply = "Done. 4 steps completed.\n[0, 1, 1, 2, 3, 5, 8, 13, 21, 34]\nAll tests passed"
   source = "l3_executor"
   route = "executor"
   steps_done = 4, steps_total = 4

6. PersonalityFilter: "Complete. The tests passed. Somewhat reliably."

7. WorldState: tasks.completed_today += 1
8. SemanticStore: conversation + code + result stored
```

---

## Rollback

If anything breaks, revert in 5 seconds:
```bash
python jarvis_main.py   # start old entry point — nothing changed
```

The autonomous layers are additive only. The old system is fully intact.
