# Gmail API OAuth2 Setup Guide

## Prerequisites

- A Google Cloud Platform project with billing enabled
- Python 3.8+ with `google-api-python-client` and `google-auth-oauthlib` installed

## Step 1: Create a Google Cloud Project

1. Go to https://console.cloud.google.com/
2. Create a new project or select an existing one
3. Note your Project ID

## Step 2: Enable the Gmail API

1. Go to **APIs & Services > Library**
2. Search for "Gmail API"
3. Click **Enable**

## Step 3: Configure the OAuth Consent Screen

1. Go to **APIs & Services > OAuth consent screen**
2. Choose **External** (or Internal if using a Google Workspace account)
3. Fill in the required fields:
   - App name: "JARVIS"
   - User support email: your email
   - Developer contact email: your email
4. Add the following scopes:
   - `https://www.googleapis.com/auth/gmail.readonly`
   - `https://www.googleapis.com/auth/gmail.send`
   - `https://www.googleapis.com/auth/gmail.modify`
   - `https://www.googleapis.com/auth/gmail.labels`
5. Add yourself as a test user (your Gmail address)
6. Save and continue

## Step 4: Create OAuth Credentials

1. Go to **APIs & Services > Credentials**
2. Click **+ Create Credentials > OAuth client ID**
3. Application type: **Desktop app**
4. Name: "JARVIS Desktop"
5. Click **Create**
6. Click **Download JSON** to download the credentials file

## Step 5: Place Credentials File

Copy the downloaded file to:

```
~/.jarvis/gmail_credentials.json
```

## Step 6: Authenticate

### Interactive Mode (Desktop with Browser)

Run the authentication flow:

```python
from integrations.gmail import GmailClient
client = GmailClient()
client.authenticate(headless=False)
```

This opens a browser window where you log in to Google and grant permissions. The token is saved to `~/.jarvis/gmail_token.json`.

### Headless Mode (Server/SSH)

```python
from integrations.gmail import GmailClient
client = GmailClient()
client.authenticate(headless=True)
```

This prints an authorization URL. Visit it in any browser, log in, and paste the authorization code back into the terminal.

## Step 7: Verify

```python
from integrations.gmail import GmailClient
client = GmailClient()
client.authenticate()
profile = client.get_profile()
print(f"Connected as: {profile.email}")
msgs = client.list_messages(max_results=3)
for m in msgs:
    print(f"  {m.subject} from {m.sender}")
```

## Token Management

- Token is auto-refreshed when expired
- Token stored at `~/.jarvis/gmail_token.json`
- Revoke token: `client._auth.revoke()`

## Troubleshooting

| Error | Solution |
|-------|----------|
| `Credentials file not found` | Place `gmail_credentials.json` in `~/.jarvis/` |
| `Access blocked: 403` | Add your email as a test user in OAuth consent screen |
| `Token has expired` | Delete `~/.jarvis/gmail_token.json` and re-authenticate |
| `Insufficient permission` | Ensure all 4 scopes are added to consent screen |
| `redirect_uri_mismatch` | Use `http://localhost` as redirect URI (not `http://localhost:8080/`) |

## Required Python Packages

```
google-api-python-client>=2.108.0
google-auth-httplib2>=0.1.0
google-auth-oauthlib>=1.0.0
```
