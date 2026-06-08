# Contributing to JARVIS AI OS

Thank you for considering contributing! We welcome contributions of all kinds — bug fixes, features, documentation, and tests.

## Getting Started

1. **Fork** the repository and clone your fork.
2. **Set up** your environment: `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
3. **Install pre-commit hooks**: `pre-commit install`
4. **Create a branch**: `git checkout -b your-feature-name`

## Development

- Run tests: `pytest`
- Lint: `ruff check .`
- Type check: `mypy core/`
- Keep lines under 120 characters.
- Write tests for new features.

## Pull Request Process

1. Ensure all lint checks and tests pass.
2. Update the CHANGELOG.md with your change.
3. Open a PR against the `main` branch with a clear title and description.
4. A maintainer will review your PR within a few days.

## Code of Conduct

Be respectful, inclusive, and constructive. See CODE_OF_CONDUCT.md.

## Questions?

Open a GitHub Discussion or issue.
