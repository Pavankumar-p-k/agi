# JARVIS Production Rescue Plan

## Objective
Transition JARVIS from a non-functional "Architecture Demo" to a production-grade, reliable, and secure AI system.

## Key Files & Context
- **Config:** `.env`, `core/config_schema.py`, `data/settings.json`
- **Routing:** `core/llm_router.py`, `core/routes/chat.py`
- **Logic:** `brain/epistemic_tagger.py`, `memory/memory_facade.py`
- **Legacy Artifacts:** `ai_os/`, `api/server.py`, `tools/executor.py`

---

## Phased Implementation Plan

### Sprint 1: Emergency Recovery (Reasoning Restore)
- **Goal:** Enable the first successful end-to-end chat response.
- **Changes:**
    - Update `.env`: Change `EMBEDDING_MODEL` from `nomic-embed-text` to `ollama/nomic-embed-text`.
    - Update `core/llm_router.py`: Enable `litellm_fallback` by default to handle transient provider failures.
    - Update `core/config_schema.py`: Set `llama3.1:8b` as the default model instead of cloud-based Claude.
- **Verification:**
    - Restart server.
    - `curl -X POST http://localhost:8001/api/chat -d '{"message": "hello"}'`
    - Success: Response contains AI-generated text, no `[ASSUMED]` error prefix.

### Sprint 2: Stability & Persistence
- **Goal:** Eliminate "Conversation Amnesia" and expose hidden bugs.
- **Changes:**
    - **Global Refactor:** Replace all `except: pass` and `except Exception: pass` with structured logging using `logger.exception()`.
    - **Immediate Write:** Modify `core/routes/chat.py` to commit messages to SQLite `chat_history` on every turn.
    - **Memory Bridge:** Update `memory/memory_facade.py` to retrieve recent messages from the persistent tier if they are not in the RAM hot-tier.
    - **Error Transparency:** Modify `brain/epistemic_tagger.py` to return the underlying reasoning error instead of masking it with `[ASSUMED]`.
- **Verification:**
    - `grep -rn "except: pass" .` returns 0 results.
    - Send 5 messages, restart server, verify context is retained in the 6th message.

### Sprint 3: Architectural Unification (The Great Cleanup)
- **Goal:** Remove redundant codebases and establish `core/` as the single source of truth.
- **Changes:**
    - **Deletions:** Remove `_archive/`, `api/server.py`, `api/agi_routes.py`, `api/os_routes.py`, `ai_os/orchestrator.py`, `ai_os/planner.py`, `tools/executor.py`, and `tools/browser_agent.py`.
    - **Migrations:** Move `ai_os/docker_sandbox.py` to `core/sandbox/` and merge `ai_os/event_bus.py` into `core/event_bus.py`.
    - **Import Sync:** Update all project-wide imports to use the `core.*` namespace.
- **Verification:**
    - `python -m py_compile core/main.py` succeeds with no missing imports.
    - Full system test (Chat + Tools + Memory) against the `core/` endpoints.

### Sprint 4: Security Hardening
- **Goal:** Protect user data and secure the API for public access.
- **Changes:**
    - **Dev Mode:** Set `dev_mode=False` in `core/config_schema.py`.
    - **CORS:** Replace `*` wildcard in `ALLOWED_ORIGINS` with specific frontend domains.
    - **Fail-Closed Secrets:** Update `core/secret_storage.py` to raise exceptions on encryption failure rather than returning plaintext.
    - **Log Sanitization:** Ensure `core/api_key_vault.py` only logs metadata (key names), never the keys themselves.
- **Verification:**
    - Attempt a loopback tool call from a non-admin session; verify it is blocked.
    - Inspect logs for any sensitive key material.

### Sprint 5: Containerized Deployment
- **Goal:** Deploy JARVIS to a public URL.
- **Changes:**
    - **Dockerfile:** Finalize a multi-stage build using `uv` for dependency management.
    - **Docker Compose:** Create `docker-compose.prod.yml` including the API, Qdrant (Vector DB), and Ollama (if not using external).
    - **CI/CD:** Configure a GitHub Action to build and push the image to a container registry.
- **Verification:**
    - Deploy to a cloud VPC.
    - Access JARVIS via a public HTTPS endpoint and verify successful AI interaction.

---

## Verification Summary
- **Sprint 1:** Reasoning engine responsiveness.
- **Sprint 2:** Context persistence and error visibility.
- **Sprint 3:** Codebase cleanliness and import integrity.
- **Sprint 4:** Authentication and encryption safety.
- **Sprint 5:** Public accessibility and container stability.
