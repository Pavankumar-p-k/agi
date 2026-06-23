# Gmail Codebase Audit

Date: 2026-06-14
Scope: All Gmail/email related files in the JARVIS codebase

## Summary

The codebase has **zero working Gmail API integration**. It has a robust IMAP/SMTP email system (1636 lines in `mcp/email_server.py`) that works with Gmail as an IMAP/SMTP provider using app passwords. The `GmailIntegration` class and `EmailMonitor` are broken/dead code.

## File-by-File Analysis

| File | Lines | Gmail API? | OAuth2? | Status | Verdict |
|------|-------|-----------|---------|--------|---------|
| `core/email_monitor.py` | 147 | Yes (scaffold) | Yes (broken) | **BROKEN** | Missing `health_check()`, OAuth flow requires interactive browser |
| `core/integration_manager.py` (GmailIntegration) | 57 | No (wraps IMAP) | No | **BROKEN** | 3 bugs: missing `health_check()`, bad imports |
| `channels/email_channel.py` | 202 | No | No | **WORKING** | Generic IMAP/SMTP |
| `mcp/email_server.py` | 1636 | No | No | **WORKING** | Full IMAP/SMTP tool suite |
| `api/email_routes.py` | 65 | No | No | **WORKING** | FastAPI wrapper around IMAP |
| `core/oauth.py` | 232 | No (login only) | Yes | **WORKING** | User login OAuth, not Gmail API |
| `core/lifespan.py` (email init) | 18 | N/A | N/A | **PARTIAL** | Starts broken EmailMonitor |
| `core/feature_registry.py` | ~8 | N/A | N/A | **WORKING** | Feature registration |
| `brain/events/event_types.py` | ~6 | N/A | N/A | **STUB** | EmailReceived defined, never emitted |
| `tests/unit/test_oauth.py` | 93 | No | Yes | **WORKING** | Tests login OAuth only |

## Critical Bugs

1. **`EmailMonitor.health_check()` MISSING** — `GmailIntegration.health_check()` at `integration_manager.py:194` calls `await monitor.health_check()`, but `EmailMonitor` has no such method. Raises `AttributeError`.

2. **`GmailIntegration.send()` BROKEN IMPORT** — `integration_manager.py:208` does `from channels.email_channel import send_email as _send`, but `send_email` is an instance method on `EmailChannel`, not a module-level function. Raises `ImportError`.

3. **`GmailIntegration.receive()` BROKEN IMPORT** — `integration_manager.py:218` does `from mcp.email_server import list_emails`, but the function is `_list_emails` (private). Raises `ImportError`.

4. **No OAuth2 credential setup flow** — `email_monitor.py` expects `~/.jarvis/gmail_credentials.json` to exist but has no setup flow or documentation.

5. **Interactive OAuth flow** — `InstalledAppFlow.run_local_server(port=0)` opens a browser on the machine, unsuitable for headless/server deployments.

6. **Read-only scope only** — `email_monitor.py` uses `gmail.readonly` scope, cannot send or manage labels.

## Gmail API Features Missing

| Feature | Status | Notes |
|---------|--------|-------|
| OAuth2 token management | **MISSING** | Scaffold exists, broken |
| Send via Gmail API | **MISSING** | Only SMTP |
| Read inbox via Gmail API | **MISSING** | Uses IMAP only |
| Search via Gmail API | **MISSING** | Uses IMAP SEARCH |
| Read attachments via Gmail API | **MISSING** | Uses raw MIME |
| Download attachments via Gmail API | **MISSING** | Uses IMAP fetch |
| Label management | **MISSING** | Not supported |
| Thread support | **MISSING** | Not supported |
| Gmail push notifications | **MISSING** | Polling only |
| Draft management | **MISSING** | Not supported |
| Gmail filters | **MISSING** | Not supported |
| Gmail API health check | **MISSING** | `EmailMonitor` has none |
| Unit/Integration tests | **MISSING** | No tests for any email code |

## What is Working (IMAP/SMTP — Keep)

- `mcp/email_server.py`: 11 MCP tools (list accounts, list emails, read, send, reply, archive, delete, mark read, bulk email, search, download attachments)
- `channels/email_channel.py`: IMAP/SMTP channel with fetch, triage, draft, send
- `api/email_routes.py`: FastAPI endpoints for email
- `core/tools/schemas_email.py`: Tool schemas

## Recommendation

Replace `core/email_monitor.py` and `core/integration_manager.py`'s `GmailIntegration` with a proper Gmail API client in `integrations/gmail/`:
- OAuth2 with token refresh
- Full Gmail API: send, read, search, labels, threads, attachments
- Headless-compatible OAuth flow
- Health checks
- Comprehensive tests
