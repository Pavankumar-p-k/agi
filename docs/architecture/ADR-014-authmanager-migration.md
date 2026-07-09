# ADR-014: AuthManager Migration from JSON to SQLite

**Status:** Proposed  
**Date:** 2026-07-09  
**Phase:** 6  

## Context

The IDENTITY_PERMISSION_AUDIT found that `AuthManager` (`core/auth.py`) persists sessions and users to JSON files:

- `sessions.json` — session tokens with expiry timestamps
- `auth.json` — user credentials (username, password hash, admin status)

These JSON files have no transaction safety, no WAL mode, no concurrent-read protection. Race conditions in `_save_sessions()` cause session data loss under concurrent login. `_load_config()` reads the entire file into memory. There is no migration path, no schema versioning, and no backup strategy.

The STORAGE_ARCHITECTURE_AUDIT confirmed that SQLite with WAL mode is the project's standard persistence layer. Alembic is already set up for ORM models.

## Decision

**Migrate AuthManager from JSON files to SQLite tables managed by Alembic.**

1. Create `users` and `sessions` tables in `data/system.db` (bounded context: system state).
2. Implement Alembic migration for both tables.
3. Password hashes remain bcrypt (no change).
4. Session tokens remain 64-char hex strings (no change).
5. JSON files are kept as read-only fallback during migration, then removed after verification.

## Consequences

**Positive:**
- Transaction safety for session creation and revocation
- WAL mode for concurrent reads (multiple users authenticating simultaneously)
- Schema versioning via Alembic
- Enables future features: session expiration cleanup, rate limiting per user, audit log per session

**Negative:**
- Migration script must handle existing sessions.json and auth.json data
- AuthManager startup time changes (SQLite connection vs JSON read)
- JSON files during migration window add a second code path (read from SQLite, fall back to JSON)
