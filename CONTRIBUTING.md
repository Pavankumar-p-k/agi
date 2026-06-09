# Contributing to JARVIS

Thanks for your interest! We welcome contributions of all kinds.

## Quick Start

```bash
git clone https://github.com/Pavankumar-p-k/agi.git
cd agi
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\Activate.ps1 on Windows
pip install -e ".[dev]"
pre-commit install
```

## Development

- **Tests**: `pytest tests/unit/` (unit), `pytest tests/integration/` (integration)
- **Lint**: `ruff check .` then `ruff format --check .`
- **Type check**: `mypy core/ --ignore-missing-imports`
- **Coverage**: `pytest tests/unit/ --cov=core --cov-report=term-missing`

## Architecture Principles

- **Zero breakage** — new code is appended, nothing renamed or removed. `get_router()` (LiteLLM) and `get_config_router()` (LLMRouter) coexist
- **Config registry** — all defaults are in `core/config_registry.py`. No hardcoded values in business logic. Use `config.get("key")` instead of `os.getenv()`
- **Secret safety** — API keys come from env vars or vault, never hardcoded. Test fixtures use obviously fake values (`sk-123`)
- **Apache 2.0** — all source files must carry the license header

## Pull Request Process

1. Fork, branch from `main`
2. Write tests. Run full suite: `pytest tests/unit/ tests/contract/`
3. Lint + typecheck pass
4. PR title describes the change, body explains why
5. A maintainer reviews within a few days

## Code of Conduct

Be respectful and constructive. See `CODE_OF_CONDUCT.md`.

## Questions?

Open a GitHub Discussion or issue.
