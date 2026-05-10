# JARVIS AUTONOMOUS INTELLIGENCE — Architecture

## Text Diagram

```
INPUT (voice / chat / API / schedule / detector / CLI)
                     │
                     ▼
┌────────────────────────────────────────────────────────────┐
│  L1 — BRAIN  (ChatGPT/Claude equivalent)                   │
│                                                            │
│  [Classifier] → [Emotion] → [Context] → [Model Router]    │
│       ↓                                         ↓          │
│  [Memory Retrieval]              [Generator] → [Quality]   │
│       ↓                                         ↓          │
│  [FusionEngine]              [PersonalityFilter]           │
│                                                            │
│  OUTPUT: reply + intent + emotion + route decision         │
└────────────────────────────────────────────────────────────┘
       │           │            │              │
    BRAIN      ASSISTANT    EXECUTOR      CONTROLLER
       │           │            │              │
       ▼           ▼            ▼              ▼
  Direct reply  ┌──────┐   ┌──────────┐   ┌──────────────┐
                │  L2  │   │    L3    │   │      L4      │
                │      │   │          │   │              │
                │Index │   │  Plan    │   │  Safety      │
                │er    │   │  ↓       │   │  Guard       │
                │+     │   │Simulate  │   │  ↓           │
                │Multi-│   │  ↓       │   │  Terminal    │
                │file  │   │ Execute  │   │  FileSystem  │
                │ctx   │   │  ↓       │   │  Apps        │
                │+     │   │ Verify   │   │  ADB         │
                │Codex │   │  ↓       │   │              │
                │server│   │Fix(3x)   │   │              │
                └──────┘   └──────────┘   └──────────────┘

SHARED CORE (all layers read/write through WorldState):
  WorldState → CognitiveCore → DecisionEngine → SimulationEngine
  FusionEngine → PersonalityFilter → SemanticStore
  Detectors (6) → NotificationHub → ADB + Voice + TTS
```

## Example Flow: "run a script to backup my files"

1. User says "run a script to backup my files"
2. L1 Brain: classifier → intent=task, emotion=neutral
   Routing table: task → EXECUTOR
   ReasoningPlanner: generates 4-step plan
3. L3 Executor:
   a. TaskPlanner: asks qwen3:4b for step decomposition
   b. SimulationEngine.simulate(): estimates risk=0.2
   c. Step 1: code = "import shutil; shutil.copy2(...)"
   d. ExecutionSandbox.run(): executes safely, captures output
   e. Verify: output contains "Backup created"
   f. AuditLog.record(): saved to exec_audit table
4. OrchestratorResult: "Done. 3 steps completed. Backup saved to /backup/"
5. PersonalityFilter: "Backup complete. Remarkably."
6. WorldState updated: tasks.completed_today += 1
7. SemanticStore: conversation stored for context

## Migration Steps

1. Copy jarvis_autonomous/ to your project root
2. pip install -r requirements_autonomous.txt
3. python jarvis_main_autonomous.py
4. Test: curl http://localhost:8000/layers/status
5. CLI: python cli/jarvis_cli.py status
6. All existing endpoints (/chat /health etc.) unchanged
