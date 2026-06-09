# JARVIS Audit Fixes

This directory contains verified patches from the pre-release engineering audit.

## Structure

```
fixes/
  patches/           # Targeted code patches (.patch files)
  refactored/        # Full refactored files (when patches are insufficient)
  migrations/        # Schema / data migrations
```

## Applying Patches

```bash
# From repo root:
git apply fixes/patches/<name>.patch

# Test after applying:
python jarvis.py doctor
pytest tests/
```

## Severity Legend

- **CRITICAL** — Must fix before public release
- **HIGH** — Should fix before public release
- **MEDIUM** — Fix within first milestone
- **LOW** — Nice to have
