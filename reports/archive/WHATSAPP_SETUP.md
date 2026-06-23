# WhatsApp Setup Guide

JARVIS supports two WhatsApp providers:

- **Meta Cloud API** (primary) — production-grade, official WhatsApp Business API
- **Twilio WhatsApp** (alternative) — uses Twilio's WhatsApp integration

---

## Prerequisites

| Provider | Requirements |
|----------|-------------|
| **Meta Cloud API** | WhatsApp Business Account, Meta Developer account, Business phone number |
| **Twilio** | Twilio account with WhatsApp Sandbox or approved sender |

---

## Meta Cloud API Setup

### 1. Meta Developer Account

1. Go to [https://developers.facebook.com](https://developers.facebook.com)
2. Create a new app (type: Business) or use existing
3. Add **WhatsApp** product to your app

### 2. Get Credentials

1. In your app dashboard, go to **WhatsApp > Getting Started**
2. Copy the **Phone Number ID** (looks like a long number, e.g. `123456789012345`)
3. Copy the **WhatsApp Business Account ID**
4. Generate or copy a **Permanent Access Token** (long-lived token, valid for 60 days or permanent)

### 3. Set Up Webhook

1. In your app dashboard, go to **WhatsApp > Configuration**
2. Click **Edit** next to Webhook
3. Enter your webhook URL: `https://your-domain.com/api/whatsapp/webhook`
4. Enter a **Verify Token** (any string you choose, e.g. `jarvis_verify_2024`)
5. Subscribe to these fields:
   - `messages`
   - `message_deliveries`
   - `message_reads`
   - `message_template_status_update`

### 4. Configure Environment

```bash
# Required
META_WHATSAPP_TOKEN=your_permanent_access_token
META_WHATSAPP_PHONE_ID=your_phone_number_id
META_VERIFY_TOKEN=your_chosen_verify_token

# Optional (recommended for security)
META_APP_SECRET=your_app_secret
```

### 5. Send a Test Message

```bash
curl -X POST "http://localhost:8000/api/automation/whatsapp/send" \
  -H "Content-Type: application/json" \
  -d '{"to": "+1234567890", "message": "Hello from JARVIS!"}'
```

---

## Twilio WhatsApp Setup

### 1. Twilio Account

1. Go to [https://console.twilio.com](https://console.twilio.com)
2. Sign up or log in
3. Get your **Account SID** and **Auth Token** from the console dashboard

### 2. WhatsApp Sandbox

1. In Twilio Console, go to **Messaging > Try it > Send a WhatsApp message**
2. You'll get a WhatsApp Sandbox number (e.g. `+14155238886`)
3. Join the sandbox by sending the join code to the sandbox number

### 3. Configure Environment

```bash
TWILIO_ACCOUNT_SID=your_account_sid
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
```

### 4. Webhook Setup

1. In Twilio Console, go to **Messaging > Try it > Send a WhatsApp message**
2. Set the **When a message comes in** webhook to: `https://your-domain.com/api/whatsapp/webhook`
3. Set method to **HTTP POST**

---

## Provider Selection

JARVIS auto-detects the provider based on available environment variables:

| Provider | Detection |
|----------|-----------|
| **Meta Cloud API** (default) | `META_WHATSAPP_TOKEN` + `META_WHATSAPP_PHONE_ID` set |
| **Twilio** | `TWILIO_ACCOUNT_SID` + `TWILIO_AUTH_TOKEN` + `TWILIO_WHATSAPP_FROM` set |

To specify a provider explicitly:

```python
from core.integration_manager import get_integration_manager

mgr = get_integration_manager()
await mgr.connect("whatsapp", provider="cloud_api")  # or "twilio"
```

---

## Sending Messages

### Text Messages

```python
await mgr.send("whatsapp", "+1234567890", "Hello world")
```

### Image Messages

```python
await mgr.send("whatsapp", "+1234567890", "", media_url="https://example.com/image.jpg", media_type="image", caption="Check this out")
```

### Document Messages

```python
await mgr.send("whatsapp", "+1234567890", "", media_url="https://example.com/doc.pdf", media_type="document", filename="report.pdf")
```

### Audio Messages

```python
await mgr.send("whatsapp", "+1234567890", "", media_url="https://example.com/audio.ogg", media_type="audio")
```

### Location Messages

```python
await mgr.send("whatsapp", "+1234567890", "", media_type="location", latitude=37.77, longitude=-122.42, location_name="San Francisco")
```

### Reply to Context

```python
await mgr.send("whatsapp", "+1234567890", "Sure!", context_message_id="wamid.original_message_id")
```

---

## Receiving Messages

Incoming messages arrive via webhook. The `WhatsAppIntegration.receive()` method provides a buffered read:

```python
messages = await mgr.receive("whatsapp")
for msg in messages:
    print(f"{msg['from']}: {msg['text']}")
    if msg['media']:
        print(f"Media: {msg['media']['filename']} ({msg['media']['mime_type']})")
```

The buffer holds the last 100 messages and can be cleared or not:

```python
# Non-destructive read (doesn't clear buffer)
msgs = await mgr.receive("whatsapp", clear_buffer=False)

# Limit results
msgs = await mgr.receive("whatsapp", limit=5)
```

---

## Webhook Verification

JARVIS validates incoming webhooks with HMAC-SHA256 signature verification:

- Meta Cloud API: `X-Hub-Signature-256` header signed with `META_APP_SECRET`
- Twilio: `X-Twilio-Signature` header signed with `TWILIO_AUTH_TOKEN`

If `META_APP_SECRET` is not set, signature verification is bypassed (not recommended for production).

---

## Architecture

```
incoming webhook POST
  └──> routers/whatsapp.py
         ├──> verify signature (HMAC-SHA256)
         ├──> parse payload
         ├──> download media if needed
         ├──> process via chat_handler
         ├──> send reply
         └──> buffer for receive()

outgoing message send
  └──> integration_manager.send("whatsapp", ...)
         ├──> WhatsAppIntegration.send()
         ├──> BaseWhatsAppProvider.send_text/image/etc()
         └──> Meta Cloud API or Twilio API

Provider files:
  integrations/whatsapp/
    ├── __init__.py          Exports
    ├── base.py              BaseWhatsAppProvider (abstract)
    ├── cloud_api.py         Meta Cloud API provider
    ├── twilio_provider.py   Twilio provider
    ├── models.py            WhatsAppMessage, WhatsAppMedia, SendResult
    ├── webhook.py           Webhook handler + signature verification
    ├── media.py             Media download/cache + type detection
    └── retry.py             AsyncRetry with exponential backoff
```
