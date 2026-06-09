# JARVIS Repository Map

Generated: 2026-06-09

## File Counts

- **Total files:** ~120,000+ (including venv, node_modules, build artifacts)
- **Source Python files (project):** ~450+ in core/ + api/ + memory/ + tools/ + modules/
- **Test files:** ~50 files in tests/
- **Documentation:** ~20 files (*.md, *.rst)
- **Config files:** ~15 files (*.yaml, *.yml, *.toml, *.ini, *.json)

> Note: 38,195 Python files counted including `.venv`, `.venv_prod`, `venv`, `__pycache__`, `data/`, `dist/`, and `node_modules/`.

## Language Breakdown (Source)

| Language | Files | Purpose |
|----------|-------|---------|
| Python | ~450 (project) | Core logic, API, CLI, tools |
| TypeScript | ~100 | Web UI |
| JavaScript | ~200 | Web UI, build |
| HTML/CSS | ~50 | Web UI |
| Dart | ~60 | Flutter GUI |
| YAML | ~50 | Config, CI/CD |
| Markdown | ~25 | Documentation |
| Shell/Batch | ~15 | Setup scripts |

## Top-Level Structure

```
jarvis/
├── jarvis.py              # Entry point (263 lines)
├── cli_commands.py        # CLI command handlers (1048 lines)
├── cli_requests.py        # HTTP request helpers (319 lines)
├── cli_server.py          # Server management
├── cli_completer.py       # Tab completion
├── cli_config.py          # CLI configuration
├── cli_helpers.py         # CLI helper utilities
├── cli_slash_commands.py  # /commands
├── cli_state.py           # CLI state management
├── cli_utils.py           # CLI utilities
├── cli_visuals.py         # Terminal visuals
│
├── core/                  # Core engine (450+ files)
│   ├── agent_loop.py      # Streaming StateGraph agent loop
│   ├── agent_helpers.py   # Intent detection, tool resolution, verifier
│   ├── agent_prompts.py   # System prompt assembly
│   ├── agent_tools.py     # Tool block parsing
│   ├── config_schema.py   # Pydantic configuration
│   ├── main.py            # FastAPI application
│   ├── graph/             # StateGraph nodes + edges
│   ├── tools/             # Tool implementations
│   │   ├── execution.py   # Tool dispatcher (1845 lines)
│   │   ├── index.py       # RAG tool index
│   │   ├── security.py    # RBAC
│   │   ├── skill_tools.py # Skill management
│   │   ├── settings_tools.py
│   │   ├── admin_tools.py
│   │   └── persistent_shell.py
│   ├── routes/            # API route modules
│   ├── sub_agents/        # 10 agent implementations
│   ├── plugins/           # Plugin system
│   ├── ssrf.py            # SSRF protection
│   ├── prompt_security.py # Prompt injection defense
│   └── api_key_vault.py   # Encrypted key storage
│
├── memory/                # Memory system
│   ├── memory_facade.py   # Unified store/recall
│   ├── tiered_memory.py   # Hot/Warm/Cold tiers
│   ├── embedding_memory.py# Vector storage
│   ├── mem0_adapter.py    # Mem0 integration
│   └── preferences.py     # User preferences
│
├── api/                   # API route modules
│   ├── os_routes.py
│   ├── agent_routes.py
│   ├── vision_routes.py
│   ├── cookbook_routes.py
│   ├── research_routes.py
│   ├── email_routes.py
│   └── ... (12 more)
│
├── ai_os/                 # AI OS modules
│   ├── docker_sandbox.py  # Docker sandbox
│   └── sandbox.py         # Policy engine
│
├── routers/               # Additional routers
│   ├── whatsapp.py
│   ├── screen.py
│   ├── setup.py
│   ├── jarvishub.py
│   └── chat.py
│
├── channels/              # Communication channels
│   ├── discord.py
│   ├── telegram.py
│   ├── slack.py
│   ├── email.py
│   ├── irc.py
│   └── matrix.py
│
├── assistants/            # Personal assistant logic
├── automation/            # PC automation
├── brain/                 # Cognitive patterns
├── cookbook/              # Model serving
├── daemon/                # Background daemon
├── governance/            # Resource monitoring
├── jarvis_os/             # JARVIS OS interface
├── jarvis_tui/            # Textual TUI
├── learning/              # Student AGI
├── mcp/                   # MCP server
├── media/                 # Media player
├── monitors/              # System monitors
├── network/               # Network tools
├── notes/                 # Notes module
├── notifications/         # Notification system
├── orchestrator/          # Task orchestration
├── pc_agent/              # PC control agent
├── plugins/               # Plugin system
├── reminders/             # Reminder system
├── services/              # Service layer
├── skills/                # Hot-reloadable skills
├── tools/                 # CLI tools
├── train/                 # Training modules
├── utils/                 # Utilities
├── vision/                # Vision/camera
├── web/                   # Web UI source
├── docs/                  # Documentation
├── tests/                 # Tests
├── scripts/               # Setup scripts
├── static/                # Static assets
├── data/                  # Runtime data
├── config/                # Configuration
├── demo/                  # Demo files
└── eval/                  # Evaluation
```

## Module Dependency Graph (Core)

```
jarvis.py → cli_commands.py
          → cli_requests.py
          → cli_server.py
          → cli_slash_commands.py

cli_commands.py → cli_requests.py (HTTP)
                → cli_server.py (process mgmt)
                → cli_state.py
                → cli_utils.py
                → cli_visuals.py
                → core.diagnostics
                → core.settings.store
                → core.sub_agents.registry
                → core.plugins.loader
                → core.plugins.registry

core/main.py → core/routes/* (12 route modules)
             → api/* (15 API modules)
             → routers/* (5 routers)
             → core/auth.py
             → core.middleware

core/agent_loop.py → core.graph (StateGraph)
                   → core.tools._constants
                   → core.graph.state.AgentState

core/graph/ → core/tools/execution.py
            → core/agent_helpers.py
            → core/llm_core.py
            → core/sub_agents/

core/tools/execution.py → core/tools/security.py
                        → core/config_schema
                        → ai_os.docker_sandbox
                        → core.mcp_manager

memory/memory_facade.py → memory/tiered_memory.py
                        → memory/mem0_adapter.py

memory/tiered_memory.py → memory/embedding_memory.py
                        → mem0 library (optional)
                        → qdrant (optional)

core/ssrf.py → ipaddress, socket, urllib.parse

core/prompt_security.py → unicodedata, uuid
```

## Largest Source Files

| File | Lines | Purpose |
|------|-------|---------|
| `core/tools/execution.py` | 1,845 | Tool dispatcher |
| `cli_commands.py` | 1,048 | CLI command handlers |
| `core/agent_prompts.py` | 673 | System prompt assembly |
| `core/tools/index.py` | 492 | RAG tool index |
| `cli_slash_commands.py` | ~450 | CLI slash commands |
| `core/config_schema.py` | 371 | Configuration schema |
| `core/agent_helpers.py` | 336 | Agent helper utilities |
| `cli_requests.py` | 319 | HTTP request helpers |
| `core/main.py` | ~600 | FastAPI app |
