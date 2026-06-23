"""integrations/gmail/auth.py — OAuth2 token management with auto-refresh."""
from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.labels",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
]

TOKEN_DIR = Path.home() / ".jarvis"
CREDS_FILE = TOKEN_DIR / "gmail_credentials.json"
TOKEN_FILE = TOKEN_DIR / "gmail_token.json"


class GmailAuth:
    """Manages Gmail API OAuth2 credentials with auto-refresh.

    Token is persisted to ~/.jarvis/gmail_token.json.
    Supports both interactive (browser) and headless (auth code) flows.
    """

    def __init__(self, creds_path: str | Path = CREDS_FILE, token_path: str | Path = TOKEN_FILE):
        self._creds_path = Path(creds_path)
        self._token_path = Path(token_path)
        self._creds = None
        self._lock = threading.Lock()
        self._service = None

    @property
    def is_authenticated(self) -> bool:
        return self._creds is not None and self._creds.valid

    @property
    def email(self) -> str | None:
        if self._creds and self._creds.valid:
            try:
                info = json.loads(self._creds.to_json())
                return info.get("id_token", {}).get("email")
            except Exception:
                pass
        return None

    def has_credentials_file(self) -> bool:
        return self._creds_path.exists()

    def has_token(self) -> bool:
        return self._token_path.exists()

    def get_auth_url(self, port: int = 8080) -> str:
        """Generate an authorization URL for headless OAuth flow.

        After the user visits this URL and authorizes, they will get a
        code that can be passed to finish_authorization().
        """
        from google_auth_oauthlib.flow import InstalledAppFlow
        flow = InstalledAppFlow.from_client_secrets_file(
            str(self._creds_path), SCOPES,
            redirect_uri=f"http://localhost:{port}/"
        )
        auth_url, _ = flow.authorization_url(prompt="consent")
        self._flow = flow
        return auth_url

    def finish_authorization(self, code: str, port: int = 8080) -> bool:
        """Complete OAuth after receiving auth code from user.

        Used in headless/server mode where browser cannot be opened.
        """
        try:
            if hasattr(self, "_flow") and self._flow:
                self._flow.redirect_uri = f"http://localhost:{port}/"
                self._flow.fetch_token(code=code)
                self._creds = self._flow.credentials
            else:
                from google_auth_oauthlib.flow import InstalledAppFlow
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self._creds_path), SCOPES,
                    redirect_uri=f"http://localhost:{port}/"
                )
                flow.fetch_token(code=code)
                self._creds = flow.credentials
            self._save_token()
            self._build_service()
            return True
        except Exception as e:
            logger.error("[GmailAuth] finish_authorization failed: %s", e)
            return False

    def authenticate(self, headless: bool = False) -> bool:
        """Authenticate with Gmail API.

        Args:
            headless: If True, use auth code flow (print URL, wait for code).
                      If False, open browser for interactive flow.

        Returns True if authentication succeeded.
        """
        if self.is_authenticated:
            return True

        if self._token_path.exists():
            return self._load_and_refresh_token()

        if not self._creds_path.exists():
            logger.error(
                "[GmailAuth] Credentials file not found at %s. "
                "Download from Google Cloud Console and save as gmail_credentials.json",
                self._creds_path
            )
            return False

        try:
            if headless:
                url = self.get_auth_url()
                logger.info("[GmailAuth] Visit this URL to authorize:\n%s", url)
                print(f"\n  Visit:\n  {url}\n")
                code = input("  Enter authorization code: ").strip()
                return self.finish_authorization(code)
            return self._interactive_auth()
        except Exception as e:
            logger.error("[GmailAuth] Authentication failed: %s", e)
            return False

    def _interactive_auth(self) -> bool:
        from google_auth_oauthlib.flow import InstalledAppFlow
        flow = InstalledAppFlow.from_client_secrets_file(
            str(self._creds_path), SCOPES
        )
        self._creds = flow.run_local_server(port=0)
        self._save_token()
        self._build_service()
        return True

    def _load_and_refresh_token(self) -> bool:
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials

            self._creds = Credentials.from_authorized_user_file(
                str(self._token_path), SCOPES
            )
            if self._creds and self._creds.expired and self._creds.refresh_token:
                self._creds.refresh(Request())
                self._save_token()
                logger.info("[GmailAuth] Token refreshed")
            if self._creds and self._creds.valid:
                self._build_service()
                return True
            return False
        except Exception as e:
            logger.error("[GmailAuth] Token load/refresh failed: %s", e)
            return False

    def _save_token(self):
        if self._creds is None:
            return
        with self._lock:
            self._token_path.parent.mkdir(parents=True, exist_ok=True)
            self._token_path.write_text(self._creds.to_json())

    def _build_service(self):
        from googleapiclient.discovery import build
        self._service = build("gmail", "v1", credentials=self._creds)

    @property
    def service(self):
        if self._service is None and self.is_authenticated:
            self._build_service()
        return self._service

    def health_check(self) -> dict[str, Any]:
        if not self._creds or not self._creds.valid:
            return {"healthy": False, "error": "Not authenticated"}
        try:
            import time
            start = time.time()
            profile = self.service.users().getProfile(userId="me").execute()
            latency_ms = (time.time() - start) * 1000
            return {
                "healthy": True,
                "email": profile.get("emailAddress", ""),
                "messages_total": profile.get("messagesTotal", 0),
                "latency_ms": round(latency_ms, 1),
            }
        except Exception as e:
            return {"healthy": False, "error": str(e)}

    def revoke(self):
        if self._creds and self._creds.valid:
            try:
                import requests
                requests.post(
                    "https://oauth2.googleapis.com/revoke",
                    params={"token": self._creds.token},
                    headers={"content-type": "application/x-www-form-urlencoded"}
                )
            except Exception:
                pass
        self._creds = None
        self._service = None
        if self._token_path.exists():
            self._token_path.unlink()
        logger.info("[GmailAuth] Token revoked and deleted")


_auth_instance: GmailAuth | None = None
_auth_lock = threading.Lock()


def get_auth() -> GmailAuth:
    global _auth_instance
    if _auth_instance is None:
        with _auth_lock:
            if _auth_instance is None:
                _auth_instance = GmailAuth()
    return _auth_instance
