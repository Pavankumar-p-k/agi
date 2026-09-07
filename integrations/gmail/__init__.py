"""integrations/gmail/ — Production-grade Gmail API integration.

Usage:
    from integrations.gmail import GmailClient

    client = GmailClient()
    await client.authenticate()
    msgs = await client.list_messages(max_results=5)
    await client.send_message(to="user@example.com", subject="Hello", body="World")
"""
from __future__ import annotations

from .auth import GmailAuth, get_auth
from .client import GmailClient

__all__ = [
    "GmailAuth",
    "GmailClient",
    "get_auth",
]
