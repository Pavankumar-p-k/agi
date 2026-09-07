# Storage Architecture Audit — Phase 3 (Document 8)

> **Purpose:** Catalog every persistent store in the codebase — SQLite databases, JSON files, vector stores, and cloud backends — with schemas, ownership, migration status, and coupling analysis.
>
> **Scope:** All 27+ SQLite databases, 6+ JSON file stores, 3 vector stores, Supabase tables, and Redis cache.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [ORM-Managed Databases (SQLAlchemy)](#2-orm-managed-databases-sqlalchemy)
3. [Raw SQLite Databases by Category](#3-raw-sqlite-databases-by-category)
4. [Complete Database Inventory](#4-complete-database-inventory)
5. [JSON File Stores](#5-json-file-stores)
6. [Vector Stores](#6-vector-stores)
7. [Cloud Backends (Supabase)](#7-cloud-backends-supabase)
8. [Cache Layer (Redis)](#8-cache-layer-redis)
9. [Migration Management](#9-migration-management)
10. [Database Coupling Map](#10-database-coupling-map)
11. [Ownership Matrix](#11-ownership-matrix)
12. [Findings](#12-findings)
13. [Recommendations](#13-recommendations)

---

## 1. Executive Summary

### Total Persistent Stores: ~36

| Type | Count | Backends |
|------|-------|---------|
| SQLite databases (ORM) | 2 files, 24 tables | SQLAlchemy (async + sync) |
| SQLite databases (raw) | 25+ files, 60+ tables | Direct `sqlite3` |
| JSON file stores | 6+ files | Flat file |
| Vector stores | 3 stores | ChromaDB (2), Qdrant (1) |
| Cloud backends | 1 service, 4 tables | Supabase (PostgreSQL) |
| Cache | 1 service | Redis (optional) |

### Key Finding: 27+ SQLite Databases with No Centralized Management

The codebase creates a new SQLite database file for almost every subsystem. There are **27+ distinct `.db` files** on disk, each managed independently with its own schema creation code and connection management. The total exceeds 60 tables across all databases.

### Database Count by Installation Scope

| Scope | Count | Example |
|-------|-------|---------|
| In `data/` (project-scoped) | ~17 | `data/workflow.db`, `data/brain.db` |
| In `~/.jarvis/` (user-scoped) | ~8 | `~/.jarvis/agent_state.db`, `~/.jarvis/cron.db` |
| In project root | ~2 | `ai_os_memory.db`, `database.db` |

---

## 2. ORM-Managed Databases (SQLAlchemy)

### 2.1 Async Models (core/database.py) — Alembic-Managed

| Aspect | Detail |
|--------|--------|
| **File** | `core/database.py` |
| **Engine** | `create_async_engine(DATABASE_URL)` — `sqlite+aiosqlite:///data/jarvis.db` |
| **Pool** | 10 connections, max_overflow=20, pool_pre_ping=True |
| **Session** | `AsyncSessionLocal` (async_sessionmaker) |
| **URL** | Configurable via `DATABASE_URL` or `JARVIS_DB__URL` env var |
| **Migration** | Alembic (`alembic/versions/f3bda4c1fa05_initial.py`) |

#### Models (11 tables, all in `data/jarvis.db`)

| Model | Table | Key Columns |
|-------|-------|-------------|
| `User` | users | id (PK), uid (unique), email, display_name, created_at, last_seen, preferences (JSON) |
| `Note` | notes | id (PK), user_id (FK), title, content, created_at, updated_at |
| `Reminder` | reminders | id (PK), user_id (FK), title, datetime, done |
| `Activity` | activities | id (PK), user_id (FK), type, description, timestamp |
| `DailySummary` | daily_summaries | id (PK), user_id (FK), date, summary, mood |
| `KnownFace` | known_faces | id (PK), user_id (FK), name, encoding, image_path |
| `ChatHistory` | chat_history | id (PK), user_id (FK), role, message, intent, session_id, timestamp |
| `ConnectedDevice` | connected_devices | id (PK), user_id (FK), device_name, device_type, last_seen |
| `JarvisSkill` | skills | id (PK), name, description, enabled, version |
| `ExecutionLog` | execution_logs | id (PK), user_id (FK), action, status, duration_ms, timestamp |
| `SubagentRun` | subagent_runs | id (PK), session_id, agent_id, task, result, started_at, completed_at |

### 2.2 Sync Models (core/database_models.py) — NOT Alembic-Managed

| Aspect | Detail |
|--------|--------|
| **File** | `core/database_models.py` |
| **Engine** | `create_engine("sqlite:///data/jarvis.db")` — **same file as async** |
| **Pool** | check_same_thread=False (no pooling) |
| **Session** | `SessionLocal` (sync sessionmaker) |
| **Migration** | **None** — uses `Base.metadata.create_all(engine)` via `ensure_tables()` |

#### Models (13 tables, same `data/jarvis.db` as async)

| Model | Table | Notes |
|-------|-------|-------|
| `Session` | sessions | User sessions |
| `ChatMessage` | chat_messages | Legacy chat messages (separate from ChatHistory) |
| `Document` | documents | User documents |
| `DocumentVersion` | document_versions | Document version history |
| `McpServer` | mcp_servers | MCP server registrations |
| `ScheduledTask` | scheduled_tasks | Cron-style tasks |
| `ModelEndpoint` | model_endpoints | API endpoint configs |
| `Webhook` | webhooks | Webhook registrations |
| `CalendarCal` | calendar_cals | Calendar definitions |
| `CalendarEvent` | calendar_events | Calendar events |
| `Note` | agent_notes | Agent notes (different table from async Note) |
| `GalleryImage` | gallery_images | Gallery images |

### 2.3 Critical Issue: Two ORM Systems, Same File, One Migration

The async models (11 tables) and sync models (13 tables) share `data/jarvis.db` but:
- Only the async models have Alembic migration (`f3bda4c1fa05`)
- The sync models use `create_all()` on every startup
- If Alembic downgrades or recreates, the sync models' tables are **not restored**
- There is no coordination between the two schema management systems

---

## 3. Raw SQLite Databases by Category

### 3.1 Shared Database: `data/workflow.db`

**Most-coupled database** — shared by 12+ subsystems:

| Owner | Tables | Purpose |
|-------|--------|---------|
| WorkflowStore | `workflow_instances`, `workflow_steps`, `workflow_events`, `workflow_contexts`, `workflow_artifacts` | Workflow execution |
| ActivityStore | `activity_nodes`, `activity_edges` | Activity graph |
| PlanStore | `plans` | Plan trees |
| PlanOutcomeStore | `plan_outcomes` | Prediction vs actual |
| SchedulerStore | `scheduled_activities` | Scheduled tasks |
| SchedulerIntelligence | `activity_stats`, `activity_resource_usage`, `resource_calibration` | Scheduling metrics |
| KnowledgeStore | `knowledge_items`, `experience_summaries` | Long-term knowledge |
| FactStore (research) | `research_facts` | Research facts |
| GraphStore (research) | `kg_nodes`, `kg_edges` | Knowledge graph |
| BeliefStore | `source_profiles`, `accuracy_records` | Belief tracking |
| NegotiationEngine | `negotiations` | Negotiation state |
| ModificationStore | `modification_records` | Self-modification log |
| OpportunityStore | `opportunity_records` | Opportunity tracking |
| ExperimentRunner | `experiments` | A/B experiments |
| PlannerExperimentManager | `planner_experiments` | Planner experiments |
| SelfModificationPlanner | - | (uses same db path) |

### 3.2 Shared Database: `data/brain.db`

Shared by brain subsystems:

| Owner | Tables | Purpose |
|-------|--------|---------|
| EpisodicMemory | `episodic_memories` | Task episodes |
| SemanticMemory | `semantic_memories` | Agent facts |
| TaskMemory | `task_memories` | Execution traces |
| DecisionMemory (brain) | `decision_memories` | Decisions/lessons |
| GoalManager | `goals` | Goal CRUD |
| ProjectPersistence | `project_checkpoints`, `decision_journal` | Checkpoints |

### 3.3 User-Scoped Databases (`~/.jarvis/`)

| Database | Owner | Tables | Purpose |
|----------|-------|--------|---------|
| `agent_state.db` | session_db | `agent_state_snapshots` | Agent state per round |
| `agent_checkpoints.db` | CheckpointStore | `checkpoints`, `node_checkpoints` | Agent graph checkpoints |
| `constitutional_memory.db` | ConstitutionalMemory | `grade_history` | Grading history |
| `cron.db` | Cron | `jobs` | Scheduled jobs |
| `commitments.db` | CommitmentStore | `commitments` | User commitments |
| `principles.db` | GeneralizationStore | `structural_properties`, `system_profiles`, `principle_data_points`, `principles`, `proposals` | System principles |
| `feedback.db` | FeedbackStore | `routing_decisions`, `routing_outcomes`, `calibration_entries` | Provider feedback |
| `orchestration.db` | OrchestrationStore | `orchestration_plans`, `orchestration_steps` | Provider orchestration |

### 3.4 Specialized Databases

| Database | Owner | Purpose |
|----------|-------|---------|
| `data/jarvis_memory.db` | FactStore + EmbeddingMemory | User facts + embeddings |
| `data/goals.db` | GoalManager (in core/) | Goal storage |
| `data/benchmark.db` | BenchmarkResultsStore | Benchmark results |
| `data/plugin_state.db` | PluginStateStore | Plugin persistence |
| `data/repo_index.db` | RepositoryIndexer | Code index |
| `data/inbox.db` | InboxStore | Inbox items |
| `data/browser_facts.db` | FactStore (browser) | Browser extracted facts |
| `data/failure_memory.db` | AutomationLoop | Build failure memory |
| `data/email_cache.db` | EmailServer | Email cache |
| `data/app.db` | EmailServer | Email accounts |
| `data/call_records_pc.db` | CallSyncServer | Call records |
| `data/training_log.db` | TrainingCollector | Training data |
| `data/student/*.db` | StudentBrain | Student AGI state |
| `data/jarvis_os_world.db` | SystemSnapshot | OS snapshots |
| `ai_os_memory.db` | CloudMemory | Cloud memory fallback |
| `~/.jarvis/workflow_learning.db` | WorkflowHistoryStore + CalibrationStore | Workflow learning |

---

## 4. Complete Database Inventory

### All Known SQLite Database Files

| # | Path | Tables | Migration | Created By |
|---|------|--------|-----------|------------|
| 1 | `data/jarvis.db` | 24 (11 async + 13 sync) | Alembic (partial) | SQLAlchemy |
| 2 | `data/workflow.db` | ~20+ | None | Raw sqlite3 |
| 3 | `data/brain.db` | 7 | None | Raw sqlite3 |
| 4 | `data/jarvis_memory.db` | 2 | None | Raw sqlite3 |
| 5 | `data/goals.db` | 1 | None | Raw sqlite3 |
| 6 | `data/benchmark.db` | 3 | None | Raw sqlite3 |
| 7 | `data/plugin_state.db` | 1 | None | Raw sqlite3 |
| 8 | `data/repo_index.db` | 1 | None | Raw sqlite3 |
| 9 | `data/inbox.db` | 1 | None | Raw sqlite3 |
| 10 | `data/browser_facts.db` | 1 | None | Raw sqlite3 |
| 11 | `data/failure_memory.db` | 1 | None | Raw sqlite3 |
| 12 | `data/email_cache.db` | - | None | Raw sqlite3 |
| 13 | `data/app.db` | 1 | None | Raw sqlite3 |
| 14 | `data/call_records_pc.db` | - | None | Raw sqlite3 |
| 15 | `data/training_log.db` | 1 | None | Raw sqlite3 |
| 16 | `data/student/student_brain.db` | - | None | Raw sqlite3 |
| 17 | `data/student/world_model.db` | - | None | Raw sqlite3 |
| 18 | `data/jarvis_os_world.db` | 2 | None | Raw sqlite3 |
| 19 | `ai_os_memory.db` | 1 | None | Raw sqlite3 |
| 20 | `database.db` | - | None | Unknown |
| 21 | `~/.jarvis/agent_state.db` | 1 | None | Raw sqlite3 |
| 22 | `~/.jarvis/agent_checkpoints.db` | 2 | None | Raw sqlite3 |
| 23 | `~/.jarvis/constitutional_memory.db` | 1 | None | Raw sqlite3 |
| 24 | `~/.jarvis/cron.db` | 1 | None | Raw sqlite3 |
| 25 | `~/.jarvis/commitments.db` | 1 | None | Raw sqlite3 |
| 26 | `~/.jarvis/principles.db` | 5 | None | Raw sqlite3 |
| 27 | `~/.jarvis/feedback.db` | 3 | None | Raw sqlite3 |
| 28 | `~/.jarvis/orchestration.db` | 2 | None | Raw sqlite3 |
| 29 | `~/.jarvis/workflow_learning.db` | 2 | None | Raw sqlite3 |
| 30 | `~/.jarvis/whatsapp_history.db` | - | None | Raw sqlite3 |
| 31 | `~/.jarvis/provider_benchmark.db` | 1 | None | Raw sqlite3 |

---

## 5. JSON File Stores

| File | Path | Managed By | Content Type | Persistence |
|------|------|-----------|-------------|-------------|
| `auth.json` | `data/auth.json` | AuthManager | User credentials (bcrypt hashes) | Read/write per login |
| `sessions.json` | `data/sessions.json` | AuthManager | Session tokens with TTL | Read/write per session |
| `memory.json` | `{data_dir}/memory.json` | System C MemoryManager | Deprecated memory entries | Legacy |
| `decision_memory.json` | `~/.jarvis/decision_memory.json` | DecisionMemory (memory/) | Agent selection learning | Write per action |
| `pattern_failures.json` | `~/.jarvis/pattern_failures.json` | PatternFailureMemory | Error patterns with strategies | Write per error |
| `provider_memory/memory.json` | `~/.jarvis/provider_memory/memory.json` | ProviderMemory | Bayesian provider evidence | Write per provider call |
| `permission_audit.jsonl` | `~/.jarvis/permission_audit.jsonl` | PermissionAudit | Permission decisions (append-only) | Append per decision |
| `oauth_tokens.json` | `~/.jarvis/oauth_tokens.json` | OAuthManager | OAuth tokens (unencrypted) | Write per login/refresh |
| Session files | `~/.jarvis/sessions/{id}.json` | ConversationManager | Conversation messages | Write per message |
| Checkpoint files | `~/.jarvis/checkpoints/{project}/` | CheckpointManager | Project checkpoints + file backups | Write per checkpoint |
| Graph checkpoints | `~/.jarvis/graph_checkpoints/{id}.json` | GraphCheckpointer | Distributed DAG snapshots | Write per checkpoint |

---

## 6. Vector Stores

| Vector Store | Type | Engine | Path | Collection | Data | Managed By |
|-------------|------|--------|------|-----------|------|-----------|
| ChromaDB #1 | Local | mem0 library | `./data/chroma/` | `jarvis_memories` | User memory embeddings | Mem0Adapter |
| ChromaDB #2 | Local | core chroma_client | `./data/chroma/` (same dir) | `odysseus_memories` | Semantic memory embeddings | MemoryVectorStore |
| Qdrant | Local | mem0 library | `./data/qdrant_storage/` | mem0-managed | Warm/cold tier vectors | TieredMemory |

**Critical:** Two ChromaDB clients write to the same directory (`./data/chroma/`) but use different collection names. The mem0 library internally manages its own ChromaDB client, while `core/chroma_client.py` manages a separate client. There is no coordination between them.

---

## 7. Cloud Backends (Supabase)

| Service | Schema | Tables | Sync Mechanism | Used By |
|---------|--------|--------|---------------|---------|
| Supabase | `001_init.sql` | `jarvis_memories`, `jarvis_conversations`, `jarvis_goals`, `jarvis_plugins_settings` | Bi-directional sync via CloudMemory | cloud_routes.py |
| Firebase | Admin SDK | Auto-sync to SQLAlchemy `users` table | `_get_or_create_user()` | auth.py |

---

## 8. Cache Layer (Redis)

| Aspect | Detail |
|--------|--------|
| **File** | `core/cache/redis_cache.py` |
| **Type** | LRU cache with optional Redis backend |
| **Config** | `JARVIS_REDIS_URL` env var (default None → LRU fallback) |
| **Prefix** | `jarvis:cache:` |
| **Timeout** | 2 seconds default |
| **Persistence** | None (ephemeral) |

---

## 9. Migration Management

### Current State

| System | Migration Tool | Status |
|--------|---------------|--------|
| Async SQLAlchemy models (11 tables) | Alembic | Has 1 migration |
| Sync SQLAlchemy models (13 tables) | None | `create_all()` on startup |
| All raw SQLite databases (25+ files) | None | `CREATE TABLE IF NOT EXISTS` in code |
| Supabase schema | Manual SQL | Must be run via SQL Editor |

### Alembic Coverage

The single Alembic migration (`f3bda4c1fa05_initial.py`) creates exactly 11 tables:
```
users, notes, reminders, activities, daily_summaries,
known_faces, chat_history, connected_devices, skills,
execution_logs, subagent_runs
```

**Not covered by Alembic:**
- 13 sync tables in `data/jarvis.db` (sessions, chat_messages, documents, etc.)
- All 20+ tables in `data/workflow.db`
- All 7 tables in `data/brain.db`
- All 2 tables in `data/jarvis_memory.db`
- All other raw sqlite3 databases

---

## 10. Database Coupling Map

### Most-Coupled Databases

```
data/workflow.db
  ├── WorkflowEngine (workflow execution)
  ├── ActivityManager (activity graph)  
  ├── Planner (plan trees)
  ├── Scheduler (scheduled activities)
  ├── KnowledgeStore (long-term memory)
  ├── Research stores (facts, knowledge graph)
  ├── Belief system (source profiles)
  ├── Negotiation (negotiation state)
  ├── Self-modification (modification records)
  ├── Opportunities (opportunity records)
  ├── Experiments (A/B tests)
  └── Planner experiments
  **12+ subsystems, ~20+ tables**

data/brain.db
  ├── MemoryManager (4 memory types) [brain/memory/]
  ├── GoalManager (goals) [brain/goals/]
  └── ProjectPersistence (checkpoints) [brain/persistence/]
  **3 subsystems, ~7 tables**

data/jarvis.db
  ├── SQLAlchemy async (11 models) [core/database.py]
  └── SQLAlchemy sync (13 models) [core/database_models.py]
  **2 systems, 24 tables combined, same file**
```

### Coupling Risks

1. **workflow.db hosts 12+ subsystems**: A schema change in any one subsystem's tables could affect all others. There is no tenant isolation within the database.
2. **brain.db mixes memory, goals, and checkpoints**: GoalManager writes to the same database as EpisodicMemory. A migration for one could block the other.
3. **jarvis.db hosts two ORM systems**: The async and sync models coexist in the same file with independent schema management. Schema conflicts are possible.

---

## 11. Ownership Matrix

| Database | Primary Owner | Table Count | Schema Management | Location | Backup Status |
|----------|--------------|-------------|-------------------|----------|---------------|
| `data/jarvis.db` | SQLAlchemy (dual) | 24 | Alembic (partial) | Project data dir | None |
| `data/workflow.db` | WorkflowStore | ~20 | `CREATE TABLE` in code | Project data dir | None |
| `data/brain.db` | MemoryManager (brain) | 7 | `CREATE TABLE` in code | Project data dir | None |
| `data/jarvis_memory.db` | FactStore | 2 | `CREATE TABLE` in code | Project data dir | None |
| `data/goals.db` | GoalManager (core) | 1 | `CREATE TABLE` in code | Project data dir | None |
| `~/.jarvis/agent_state.db` | session_db | 1 | `CREATE TABLE` in code | User config dir | None |
| `~/.jarvis/agent_checkpoints.db` | CheckpointStore | 2 | `CREATE TABLE` in code | User config dir | None |
| `~/.jarvis/cron.db` | Cron | 1 | `CREATE TABLE` in code | User config dir | None |
| `~/.jarvis/principles.db` | GeneralizationStore | 5 | `CREATE TABLE` in code | User config dir | None |
| Auth JSON files | AuthManager | N/A | Manual | Project data dir | None |
| OAuth JSON file | OAuthManager | N/A | Manual | User config dir | None |

**No database has automated backup, replication, or point-in-time recovery.**

---

## 12. Findings

### F-1: (Critical) 27+ SQLite Databases with No Centralized Management
Each subsystem creates its own database file with its own schema. There is no registry, no connection pool sharing, no migration coordination, and no way to discover all databases at runtime. 60+ tables across 27+ files.

### F-2: (Critical) Two ORM Systems Share the Same Database File
`core/database.py` (async, Alembic-managed) and `core/database_models.py` (sync, `create_all`-managed) both write to `data/jarvis.db`. Alembic only knows about 11 of the 24 tables. If Alembic ever recreates the database, 13 tables are silently lost.

### F-3: (High) No Migration Management for 90% of Databases
Only 11 of 24 ORM tables have Alembic migration. Zero raw SQLite databases have versioned migrations. All use `CREATE TABLE IF NOT EXISTS` with best-effort `ALTER TABLE ADD COLUMN` in try/except blocks.

### F-4: (High) data/workflow.db Has 12+ Subsystems with No Isolation
The shared `workflow.db` creates tight coupling between the workflow engine, planner, scheduler, activity system, knowledge store, belief system, negotiation, self-modification, and experiments. A corrupt write from any subsystem affects all others.

### F-5: (Medium) AuthManager Uses JSON Files Instead of SQLite
User credentials and session tokens are stored in `data/auth.json` and `data/sessions.json` with no write-ahead logging, no transactions, and no concurrency protection. Every other subsystem uses SQLite — Auth is the odd one out.

### F-6: (Medium) OAuth Tokens Stored Unencrypted
`~/.jarvis/oauth_tokens.json` stores OAuth refresh tokens as plaintext. These tokens provide long-lived API access to Google, GitHub, and Discord.

### F-7: (Medium) Two ChromaDB Instances in the Same Directory
The mem0 adapter and the core `MemoryVectorStore` both use ChromaDB at `./data/chroma/` but with different collection names and different client instances. They can interfere with each other's data.

### F-8: (Medium) Backup Strategy Is Absent
No database has automated backup, WAL checkpoint management, or corruption detection. The only recovery mechanism is the workflow engine's heartbeat-based recovery (for active workflows only).

### F-9: (Low) Supabase Schema Is Decoupled from Code
The Supabase migration (`001_init.sql`) must be run manually. There is no integration with Alembic or any other migration tool.

### F-10: (Low) Data Files in Project Root
`ai_os_memory.db` and `database.db` exist in the project root directory with no clear ownership. These should be in `data/`.

### F-11: (Low) Inconsistent Path Conventions
Some databases use `data/` prefix (e.g., `data/workflow.db`), some use `~/.jarvis/` prefix (e.g., `~/.jarvis/cron.db`), and some use neither (`ai_os_memory.db`). There is no consistent convention for what goes where.

---

## 13. Recommendations

### R-1: (Critical) Consolidate Raw SQLite Databases
Target: Reduce from 27+ files to ~3-5 well-defined databases.
- **`data/system.db`** — Merge `workflow.db`, `brain.db`, and `jarvis_memory.db` into a single system database. Use table namespace prefixes or a schema-per-module pattern.
- **`data/app.db`** — Keep the ORM-managed `jarvis.db` for user-facing application data.
- **`data/user.db`** — Merge all `~/.jarvis/*.db` files into a single user-scoped database.

This reduces connections from 27+ to 3 and enables unified backup, migration, and connection pooling.

### R-2: (Critical) Complete Alembic Migration Coverage
Add Alembic migrations for:
- All 13 sync model tables in `database_models.py`
- All tables in the consolidated system database
- Retire `CREATE TABLE IF NOT EXISTS` pattern entirely

### R-3: (High) Separate ORM Systems into Different Databases
Move the 13 sync model tables out of `data/jarvis.db` into their own database file (e.g., `data/legacy.db`). This eliminates the risk of Alembic operations silently dropping sync tables.

### R-4: (High) Migrate AuthManager to SQLite
Replace `auth.json` and `sessions.json` with SQLite tables in a dedicated `data/auth.db`. This brings auth in line with the rest of the system and adds transaction safety.

### R-5: (Medium) Encrypt OAuth Token Storage
Add at-rest encryption for `oauth_tokens.json` using a key derived from the configured secret.

### R-6: (Medium) Consolidate Vector Stores
Migrate both ChromaDB instances and the Qdrant instance into a single vector store. The mem0 adapter should be the primary interface, with `MemoryVectorStore` either removed or integrated as an alternative backend.

### R-7: (Medium) Add Automated Backup
Implement WAL-based backup for all critical databases (`workflow.db`, `brain.db`, `jarvis_memory.db`) using `sqlite3.backup()` on a daily schedule. Store backups in `~/.jarvis/backups/`.

### R-8: (Low) Standardize Database Path Conventions
Move all databases to `data/` (project scoped) or `~/.jarvis/` (user scoped). Remove databases from the project root.

### R-9: (Low) Create Database Registry
Add a `DatabaseRegistry` module that tracks all active database connections with health check endpoints. This would enable `GET /api/system/databases` to list all databases, their sizes, table counts, and connection status.

### R-10: (Low) Integrate Supabase Migrations into Codebase
Add a programmatic migration step for Supabase schema (check and apply), or integrate the SQL migration into the startup process.
