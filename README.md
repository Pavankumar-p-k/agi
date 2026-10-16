# Fresh Start

This project was rebuilt from scratch on 2026-10-16.

The previous implementation is preserved in two places:

- **Git branch:** `snapshot/pre-rebuild-2026-10-16`
- **Tarball:** `../rebuild-backup-20261016.tar.gz` (one level above this directory)

## What this is

A minimal, honest Python skeleton — no stubs, no fake modules, no "auto-reconstructed"
placeholders. It does exactly what it claims and nothing more:

- `src/app/` — a small package with a CLI entry point (`python -m app`)
- `tests/` — pytest smoke tests that verify the CLI works
- `pyproject.toml` / `requirements.txt` — dependency and tooling config

## Usage

```bash
pip install -r requirements.txt   # dev tooling only; no runtime deps
python -m app hello               # prints "hello"
python -m pytest tests/           # runs the test suite
```

## Rebuild rules

1. Every module added must be real, working code — if it can't run, it doesn't ship.
2. Every claim of "working" is demonstrated with a test or a live command run.
3. Tests never assert less to pass; missing behavior is implemented, not skipped.
