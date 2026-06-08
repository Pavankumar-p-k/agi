# JARVIS — Architecture Guide for AI Coding Assistants

This document helps AI coding tools understand the JARVIS codebase structure, conventions, and patterns.

## Location of Key Files

| Component | Path |
|-----------|------|
| Entry point | `jarvis.py` |
| CLI commands | `cli_commands.py` |
| CLI request helpers | `cli_requests.py` |
| CLI server management | `cli_server.py` |
| Config schema | `core/config_schema.py` |
| Agent loop | `core/agent_loop.py` |
| Tool execution | `core/tools/execution.py` |
| Tool implementations | `core/tools/skill_tools.py`, `settings_tools.py`, `admin_tools.py`, `cookbook_tools.py` |
| Persistent shell | `core/tools/persistent_shell.py` |
| Skill loader | `core/skill_loader.py` |
| Prompt security | `core/prompt_security.py` |
| SSRF protection | `core/ssrf.py` |
| API key vault | `core/api_key_vault.py` |
| Docker sandbox | `ai_os/docker_sandbox.py` |
| Diagnostics | `core/diagnostics.py` |
| FastAPI app | `core/main.py` |
| Skill index (SKILL.md format) | `core/tools/skill_tools.py` (`do_manage_skills`) |
| Media player | `media/player.py` |
| Tests | `tests/unit/` |

## Key Architecture Rules

1. **NO silent except blocks** — every `except` must log with `logger.warning()` and include `as e`. Zero remaining in live code.
2. **NO shell=True** in `subprocess` calls — always use `shell=False` with a list argument.
3. **ALL API keys** must come from environment variables or `core/config.py`, never hardcoded.
4. **Config** is type-validated by `core/config_schema.py` (`JarvisConfig` pydantic model).
5. **Tools** are registered in `core/tools/execution.py` `_TOOL_HANDLERS` dict — add new tools there plus in `core/tools/index.py` (description), `core/agent_prompts.py` (usage docs), and `core/agent_helpers.py` (ALWAYS_AVAILABLE list).

## Adding a New Tool

1. Add implementation function in `core/tools/` (e.g., `skill_tools.py`, `settings_tools.py`)
2. Export it via `core/tools/implementations.py`
3. Add handler + register in `core/tools/execution.py` `_TOOL_HANDLERS`
4. Add doc line in `core/agent_prompts.py`
5. Add index entry in `core/tools/index.py`
6. Add to `ALWAYS_AVAILABLE` in `core/agent_helpers.py` if it should be available in every turn

## Import Convention

- `jarvis_os/` provides `bootstrap.py`, `core/planner.py`, `memory/memory_manager.py` — these are stubs imported by `cli_requests.py`, `api/os_routes.py`, `ai_os/`
- `skills/` contains `{name}.md` (frontmatter + triggers) + `{name}.py` (handler)
- `core/` contains all core logic — no deep nesting beyond 1 level

## Testing

- `pytest tests/unit/` for unit tests
- `pytest tests/integration/` for integration tests
- Tests must NOT depend on external services — use `mock_external_calls` autouse fixture in `tests/conftest.py`
- Do NOT use the `db_init` fixture unless the test actually needs a database
