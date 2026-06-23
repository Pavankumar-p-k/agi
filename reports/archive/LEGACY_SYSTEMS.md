# JARVIS Legacy Systems Detection

## 1. `ai_os/` and `jarvis_os/`
**Problem:** These were intended to be a full "AI Operating System" layer, but `jarvis_os` has been deleted or is missing, leaving `ai_os` as a ghost shell.
**Status:** **BROKEN / GHOST**.
**Action:** Delete `ai_os/` and remove `/ai_os` routes from `core/main.py`.

## 2. `api/hybrid_integration.py`
**Problem:** Re-implements planning, execution, and chat fallback logic independent of the core `UnifiedBrain` and `StateGraph`. Creates a "shadow" system that leads to inconsistent results.
**Status:** **REDUNDANT**.
**Action:** Extract unique tools (OpenClaw) and migrate to the core `tool_registry`, then delete.

## 3. `api/server.py`
**Problem:** Old entry point that duplicates chat logic but lacks modern session and memory features.
**Status:** **OBSOLETE**.
**Action:** Delete.

## 4. `api/agi_routes.py`
**Problem:** Duplicates `/api/chat` logic under `/solve` and adds many stubs (`/habit`, `/predictions`) that return mocked or empty data.
**Status:** **REDUNDANT**.
**Action:** Delete.

## 5. `api/agent_routes.py`
**Problem:** While active, it uses an older `AgentRegistry` system that should be unified into the `StateGraph` node-based specialty system.
**Status:** **LEGACY**.
**Action:** Migrate to `core/graph` specialties.
