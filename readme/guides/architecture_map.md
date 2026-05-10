# Architecture Map

## Runtime Layers
- `backend/jarvis_os/core.py` wires the OS runtime, tool router, planning, executor, safety, learning, access, gateway, scheduler, memory facade, model facade, and multi-agent hub.
- `backend/jarvis_os/reasoning.py` performs intent analysis and tool recommendation.
- `backend/jarvis_os/planning.py` turns goals into multi-step plans with approval metadata.
- `backend/jarvis_os/executor/executor.py` runs plans with retries, safety checks, and world-model updates.
- `backend/jarvis_os/api/routes.py` exposes the AI OS over FastAPI under `/os/*`.

## Specialized Layers
- `backend/jarvis_os/agents/` adds research, coding, planning, and debugging specialists over the live OS.
- `backend/jarvis_os/memory/` exposes memory manager, vector store, and context manager facades.
- `backend/jarvis_os/models/` exposes Ollama routing and model-manager facades.
- `backend/jarvis_os/interface/` exposes CLI, API, and voice wrappers.
- `backend/jarvis_os/runtime/` exposes runtime config and logger helpers.

## File Count Snapshot
- Source-like files after cleanup: 967
- Python modules after cleanup: 265
- On-disk total remains higher because the live virtual environment `backend/.venv/` is intentionally preserved for runtime stability.