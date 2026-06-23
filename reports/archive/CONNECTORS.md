# Connectors — JARVIS Integration System

## Architecture

The IntegrationManager (`core/integration_manager.py`) provides a unified interface for all external service connections.

## Supported Integrations

| Integration | Class | Status | Auth | Local Fallback |
|-------------|-------|--------|------|----------------|
| Gmail | `GmailIntegration` | 🟡 Beta | OAuth2 | Email channel (IMAP) |
| Telegram | `TelegramIntegration` | 🟡 Beta | Bot Token | — |
| Discord | `DiscordIntegration` | 🟡 Beta | Bot Token | — |
| Slack | `SlackIntegration` | 🟡 Beta | Bot Token | — |
| WhatsApp | `WhatsAppIntegration` | 🟡 Beta | Token + Phone ID | Selenium Web |
| GitHub | `GitHubIntegration` | 🟡 Beta | Personal Token | — |
| Google Drive | `GoogleDriveIntegration` | 📋 Planned | API Key | — |

## IntegrationManager API

```python
from core.integration_manager import get_integration_manager

mgr = get_integration_manager()

# Connect
await mgr.connect("gmail", client_id="...", client_secret="...")

# Health check
status = await mgr.health_check("telegram")

# Send message
await mgr.send("whatsapp", "+1234567890", "Hello from JARVIS!")

# Receive
messages = await mgr.receive("github", repo="owner/repo")

# Disconnect
await mgr.disconnect("discord")
```

## Credential Storage

Credentials are stored encrypted using `core/secret_storage.py` (Fernet encryption) at `~/.jarvis/integrations/`.

API keys are managed by `core/api_key_vault.py` which supports:
- Multi-key rotation on rate limits
- Environment variable fallback
- Usage tracking

## OAuth Flow

The service-level OAuth flow uses the existing `core/oauth.py` with encrypted token storage. OAuth tokens are stored at `~/.jarvis/oauth_tokens.json`.

## Message Channels

The existing channel system (`channels/`) provides real-time messaging for Discord, Slack, Telegram, Matrix, IRC, and Email. These are wrapped by the IntegrationManager for unified access.

## Webhook System

The webhook system (`core/webhook_manager.py`) dispatches events to registered webhooks:
- Events: `chat.completed`, `agent.completed`, `build.completed`, `tool.executed`, etc.
- Delivery: HTTP POST with HMAC signature
- Retry: Up to 3 attempts with exponential backoff

```bash
jarvis plugin webhook add https://my-server.com/webhook --events chat.completed build.completed
```
