# INTEGRATIONS AUDIT — Telegram, Discord, Slack, WhatsApp, GitHub, Google Drive

## Scope

Audit of 6 integration wrappers in `core/integration_manager.py` plus the 5 channel plugins in `channels/` and supporting files. Gmail is excluded (already covered by `GMAIL_AUDIT.md`).

**Last updated:** June 2026 — all critical, high, and medium findings have been resolved for Telegram, Discord, Slack, WhatsApp, and GitHub.

---

## 1. Telegram

**Files:** `channels/telegram_channel.py`, `core/integration_manager.py:254-308`
**Config:** `TELEGRAM_BOT_TOKEN` in `core/settings/schema.py:98` and `store.py:104`
**Feature status:** STABLE (under `channels`)
**Tests:** `test_channels.py::TestTelegramChannel` (3 tests) + `test_integration_manager.py::TestTelegramIntegration` (9 tests)

### Status: ✅ PRODUCTION GRADE

| # | Severity | Finding | Status |
|---|----------|---------|--------|
| T1 | LOW | `connect()` stores config without validating token — by design (delegates to channel plugin) | ACCEPTED |
| T2 | LOW | `receive()` now polls via `Bot.get_updates()` with offset tracking | ✅ FIXED |
| T3 | MED | `health_check()` uses `httpx.AsyncClient` per call — acceptable for occasional health checks | ACCEPTED |
| T4 | MED | IntegrationManager tests added (9 tests) | ✅ FIXED |

---

## 2. Discord

**Files:** `channels/discord_channel.py`, `core/integration_manager.py:311-353`, `core/oauth.py:113-123`
**Config:** `DISCORD_BOT_TOKEN` added to `settings/schema.py` and `store.py` + existing OAuth client ID/secret
**Feature status:** STABLE (under `channels`)
**Tests:** `test_channels.py::TestDiscordChannel` (4 tests) + `test_integration_manager.py::TestDiscordIntegration` (8 tests)

### Status: ✅ PRODUCTION GRADE

| # | Severity | Finding | Status |
|---|----------|---------|--------|
| D1 | MED | `discord_bot_token` added to settings schema | ✅ FIXED |
| D2 | LOW | `health_check()` now pings Discord REST API (`/users/@me`) | ✅ FIXED |
| D3 | LOW | `receive()` now fetches messages via Discord REST API (`channels/{id}/messages`) | ✅ FIXED |
| D4 | MED | IntegrationManager tests added (8 tests) | ✅ FIXED |

---

## 3. Slack

**Files:** `channels/slack_channel.py`, `core/integration_manager.py:356-393`
**Config:** `SLACK_BOT_TOKEN` and `SLACK_APP_TOKEN` added to `settings/schema.py` and `store.py`
**Feature status:** STABLE (under `channels`)
**Tests:** `test_channels.py::TestSlackChannel` (4 tests) + `test_integration_manager.py::TestSlackIntegration` (9 tests)

### Status: ✅ PRODUCTION GRADE

| # | Severity | Finding | Status |
|---|----------|---------|--------|
| S1 | MED | `slack_bot_token` and `slack_app_token` added to settings schema | ✅ FIXED |
| S2 | LOW | `health_check()` now calls Slack `auth_test()` API | ✅ FIXED |
| S3 | MED | `SlackIntegration` now owns its own `WebClient`, `SlackChannel.send()` reuses `self._client` | ✅ FIXED |
| S4 | MED | IntegrationManager tests added (9 tests) | ✅ FIXED |

---

## 4. WhatsApp

**Files:** `routers/whatsapp.py`, `tools/whatsapp_sender.py`, `core/integration_manager.py:396-438`, `automation/messaging.py`
**Config:** `META_WHATSAPP_TOKEN`, `META_WHATSAPP_PHONE_ID` in `schema.py:101-102` and `store.py:107-108`
**Feature status:** BETA
**Tests:** `test_channels_e2e.py::TestWhatsappWebhook` (6 tests) + `test_integration_manager.py::TestWhatsAppIntegration` (8 tests)

### Status: ✅ PRODUCTION GRADE

| # | Severity | Finding | Status |
|---|----------|---------|--------|
| W1 | CRITICAL | `health_check()` now uses `WhatsAppSender.health_check()` (new method) instead of non-existent `verify_token` | ✅ FIXED |
| W2 | MED | `send()` now uses `whatsapp_sender.send()` singleton instead of free function | ✅ FIXED |
| W3 | LOW | `WhatsAppSender` reads env vars at construction — by design for singleton pattern | ACCEPTED |
| W4 | LOW | `receive()` returns `[]` — webhook-only protocol, cannot poll Meta API for inbound | DOCUMENTED |
| W5 | MED | IntegrationManager tests added (8 tests) | ✅ FIXED |

---

## 5. GitHub

**Files:** `core/integration_manager.py:441-519`, `core/oauth.py:101-111`
**Config:** `GITHUB_TOKEN` in `schema.py:97` and `store.py:103`
**Feature status:** BETA (promoted from PLANNED)
**Tests:** `test_integration_manager.py::TestGitHubIntegration` (8 tests)

### Status: ✅ PRODUCTION GRADE

| # | Severity | Finding | Status |
|---|----------|---------|--------|
| GH1 | MED | Feature status promoted from PLANNED to BETA in feature_registry | ✅ FIXED |
| GH2 | LOW | Logic inline in `integration_manager.py` — acceptable pattern for a wrapper | ACCEPTED |
| GH3 | MED | `receive()` now returns structured dicts (id, number, title, state, body, url, user, labels, type) | ✅ FIXED |
| GH4 | LOW | Issue-focused — scope limitation, acceptable for current tier | ACCEPTED |
| GH5 | LOW | No rate limit handling — acceptable for initial BETA | ACCEPTED |
| GH6 | MED | IntegrationManager tests added (8 tests) | ✅ FIXED |

---

## 6. Google Drive

**Files:** `core/integration_manager.py:522-551`
**Config:** None
**Feature status:** PLANNED
**Tests:** None

### Gaps

| # | Severity | Finding | File |
|---|----------|---------|------|
| GD1 | CRITICAL | `connect()` just sets `_connected = True` — no actual authentication | `integration_manager.py:525-529` |
| GD2 | CRITICAL | `send()` and `receive()` are stubs that log "not implemented" and return False/[] | `integration_manager.py:545-551` |
| GD3 | CRITICAL | No Google Drive API client exists anywhere in the codebase | `integration_manager.py` |
| GD4 | HIGH | `health_check()` checks for `api_key` but Google Drive requires **OAuth 2.0**, not API key auth | `integration_manager.py:535-543` |
| GD5 | HIGH | No settings/schema entries for Google Drive credentials | `schema.py` |
| GD6 | HIGH | No OAuth flow — unlike Gmail which has a complete OAuth module | `integrations/` |
| GD7 | MED | No tests at all | `tests/` |

---

## 7. Cross-Cutting Issues

| # | Severity | Finding |
|---|----------|---------|
| X1 | MED | `receive()` returns `[]` for all push-based integrations (Telegram, Discord, Slack, WhatsApp, GitHub). Should implement a buffered read or document the limitation. |
| X2 | LOW | `connect()` is lazy for Telegram/Discord/Slack — stores config but doesn't validate credentials against the actual API |
| X3 | MED | Missing settings schema entries: `discord_bot_token`, `slack_bot_token`, `slack_app_token`, `google_drive_*` |
| X4 | HIGH | No IntegrationManager-level tests exist for any integration — only ChannelPlugin tests exist for Telegram/Discord/Slack |
| X5 | MED | `github` feature status is set to PLANNED in `feature_registry.py` but has working code — should be BETA |
| X6 | LOW | IRC and Matrix channels exist as ChannelPlugins but have **no BaseIntegration wrapper** in `integration_manager.py` |

---

## Summary

| Integration | Code Quality | Config | Tests | Status |
|-------------|-------------|--------|-------|--------|
| **Telegram** | Good | ✅ `TELEGRAM_BOT_TOKEN` | 3 channel + 9 manager | ✅ PRODUCTION |
| **Discord** | Good | ✅ `DISCORD_BOT_TOKEN` added | 4 channel + 8 manager | ✅ PRODUCTION |
| **Slack** | Good | ✅ `SLACK_BOT_TOKEN` + `SLACK_APP_TOKEN` added | 4 channel + 9 manager | ✅ PRODUCTION |
| **WhatsApp** | Good | ✅ `META_WHATSAPP_TOKEN/PHONE_ID` | 6 sender + 8 manager | ✅ PRODUCTION |
| **GitHub** | Good | ✅ `GITHUB_TOKEN` | 8 manager | ✅ PRODUCTION |
| **Google Drive** | **Stub** | ❌ None | None | ❌ STUB |
| **IRC** | Basic | ❌ None | Channel only | Not in manager |
| **Matrix** | Basic | ❌ None | Channel only | Not in manager |

### Remaining work

1. **Google Drive** needs full implementation (OAuth2 + API client) or removal — 3 critical, 3 high findings
2. **IRC/Matrix** need BaseIntegration wrappers if they should be managed by IntegrationManager
