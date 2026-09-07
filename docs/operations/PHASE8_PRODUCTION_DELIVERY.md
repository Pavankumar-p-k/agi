# Phase 8 production delivery

## Validate and start

Copy `.env.production.example` to `.env.production`, set a random
`JARVIS_SECRET_KEY`, database URL, and explicit allowed origins. Validate before
starting:

```bash
python scripts/validate_production.py --env-file .env.production
docker compose -f docker-compose.yml -f docker-compose.production.yml up -d --build
python scripts/smoke_test.py http://localhost:8000
```

The production override removes the host `.env` mount, uses a named data
volume, and enables a read-only application filesystem. It does not expose
database migration or backup commands because this repository has no
production-safe automated backup target. Use the existing `BackupManager` only
after confirming the destination and retention policy.

## Rollback

Keep the previously deployed image tag or build artifact. If a smoke test or
readiness check fails, stop the current stack and redeploy that known-good
artifact:

```bash
docker compose -f docker-compose.yml -f docker-compose.production.yml down
docker compose -f docker-compose.yml -f docker-compose.production.yml up -d
python scripts/smoke_test.py
```

Do not delete named volumes during rollback. Investigate migrations separately
and take a verified backup before any schema change.
