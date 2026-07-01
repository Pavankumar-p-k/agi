# Contributing to JARVIS

## Before You Start

Read these documents in order:
1. [VISION.md](VISION.md) — where JARVIS is going
2. [PRODUCT.md](PRODUCT.md) — what JARVIS is today
3. [ARCHITECTURE.md](ARCHITECTURE.md) — the core pipeline + freeze contract
4. [UX_PRINCIPLES.md](UX_PRINCIPLES.md) — rules every feature must follow

Every contribution is reviewed against those documents. If a proposal doesn't fit the product vision, architecture, or UX principles, it doesn't merge.

## Developer Setup

```bash
git clone https://github.com/Pavankumar-p-k/agi.git
cd agi
pip install -e .
python jarvis.py doctor
```

Prerequisites: Python 3.11+, Ollama running locally.

## Development Commands

```bash
python jarvis.py chat      # Interactive terminal session
python jarvis.py code      # Autonomous coding
python jarvis.py web       # Web UI
python jarvis.py doctor    # Diagnostics
```

## Running Tests

```bash
pytest tests/unit/         # Unit tests
pytest tests/integration/  # Integration tests
```

Tests must NOT depend on external services. Use the `mock_external_calls` autouse fixture in `tests/conftest.py`.

## How to Add a Tool

1. Add implementation in `core/tools/` (e.g., `skill_tools.py`, `settings_tools.py`)
2. Export via `core/tools/implementations.py`
3. Add handler + register in `core/tools/execution.py` `_TOOL_HANDLERS`
4. Add doc line in `core/agent_prompts.py`
5. Add index entry in `core/tools/index.py`
6. Add to `ALWAYS_AVAILABLE` in `core/agent_helpers.py` if it should always appear

## How to Add a Provider

1. Create `provider.yaml` with manifest v2 schema
2. Implement the `ExecutionProvider` ABC
3. Place in `~/.jarvis/providers/` or `./providers/`
4. The ProviderDiscovery and RegistrationPipeline handle the rest

See [docs/providers/create_a_provider.md](providers/create_a_provider.md) for the full SDK guide.

## How to Add a Capability

1. Define the capability ID and its input/output schema
2. Register it in the Capability Graph
3. Implement providers that can fulfill it
4. The Negotiation Engine automatically learns which provider to route to

## Architecture Rules

- **NO silent except blocks** — every `except` must log with `logger.warning()` and include `as e`
- **NO shell=True** in `subprocess` calls — always use `shell=False` with a list argument
- **ALL API keys** from environment variables or `core/config.py`, never hardcoded
- **Config** type-validated by `core/config_schema.py` (`JarvisConfig` pydantic model)
- **Every PR preserves the core flow**: Goal → Planner → Capability → Permission → Negotiation → Provider → Learning

## Code Style

- No comments on code unless necessary to explain why, not what
- Typed Python (PEP 484)
- Follow existing patterns in the file you're editing
- No emojis in code or comments
