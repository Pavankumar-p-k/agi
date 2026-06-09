# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path

import httpx
from authlib.integrations.starlette_client import OAuth, OAuthError
from starlette.config import Config
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

STORE_PATH = Path.home() / ".jarvis" / "oauth_tokens.json"


class OAuthManager:
    """OAuth2 provider for Google, GitHub, Discord logins — added login flow."""

    def __init__(self):
        self._oauth = None
        self._tokens: dict[str, dict] = {}
        self._load()

    def _load(self):
        try:
            if STORE_PATH.exists():
                self._tokens = json.loads(STORE_PATH.read_text())
        except Exception as e:
            logger.warning("[OAuth] Load failed: %s", e)

    def _save(self):
        try:
            STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
            STORE_PATH.write_text(json.dumps(self._tokens, indent=2))
        except Exception as e:
            logger.warning("[OAuth] Save failed: %s", e)

    def _get_oauth(self):
        if self._oauth is not None:
            return self._oauth
        client_id = os.getenv("OAUTH_CLIENT_ID", "")
        client_secret = os.getenv("OAUTH_CLIENT_SECRET", "")
        if not client_id:
            logger.warning("[OAuth] No OAUTH_CLIENT_ID set")
            return None
        starlette_config = Config(environ={
            "OAUTH_CLIENT_ID": client_id,
            "OAUTH_CLIENT_SECRET": client_secret,
        })
        self._oauth = OAuth(starlette_config)
        self._oauth.register(
            name="generic",
            client_id=client_id,
            client_secret=client_secret,
            authorize_url=os.getenv("OAUTH_AUTHORIZE_URL", ""),
            access_token_url=os.getenv("OAUTH_TOKEN_URL", ""),
            userinfo_endpoint=os.getenv("OAUTH_USERINFO_URL", ""),
            client_kwargs={"scope": os.getenv("OAUTH_SCOPE", "openid email profile")},
        )
        return self._oauth

    def _init_providers(self):
        if self._oauth is not None:
            return
        starlette_config = Config(environ={
            "GOOGLE_CLIENT_ID": os.getenv("GOOGLE_CLIENT_ID", ""),
            "GOOGLE_CLIENT_SECRET": os.getenv("GOOGLE_CLIENT_SECRET", ""),
            "GITHUB_CLIENT_ID": os.getenv("GITHUB_CLIENT_ID", ""),
            "GITHUB_CLIENT_SECRET": os.getenv("GITHUB_CLIENT_SECRET", ""),
            "DISCORD_CLIENT_ID": os.getenv("DISCORD_CLIENT_ID", ""),
            "DISCORD_CLIENT_SECRET": os.getenv("DISCORD_CLIENT_SECRET", ""),
        })
        self._oauth = OAuth(starlette_config)

        if os.getenv("GOOGLE_CLIENT_ID"):
            self._oauth.register(
                name="google",
                client_id=os.getenv("GOOGLE_CLIENT_ID"),
                client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
                server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
                client_kwargs={"scope": "openid email profile"},
            )
            logger.info("[OAuth] Google provider registered")

        if os.getenv("GITHUB_CLIENT_ID"):
            self._oauth.register(
                name="github",
                client_id=os.getenv("GITHUB_CLIENT_ID"),
                client_secret=os.getenv("GITHUB_CLIENT_SECRET"),
                access_token_url="https://github.com/login/oauth/access_token",
                authorize_url="https://github.com/login/oauth/authorize",
                userinfo_endpoint="https://api.github.com/user",
                client_kwargs={"scope": "user:email"},
            )
            logger.info("[OAuth] GitHub provider registered")

        if os.getenv("DISCORD_CLIENT_ID"):
            self._oauth.register(
                name="discord",
                client_id=os.getenv("DISCORD_CLIENT_ID"),
                client_secret=os.getenv("DISCORD_CLIENT_SECRET"),
                access_token_url="https://discord.com/api/oauth2/token",
                authorize_url="https://discord.com/api/oauth2/authorize",
                userinfo_endpoint="https://discord.com/api/users/@me",
                client_kwargs={"scope": "identify email"},
            )
            logger.info("[OAuth] Discord provider registered")

    def get_providers(self) -> list[str]:
        self._init_providers()
        if not self._oauth:
            return []
        return list(self._oauth._clients.keys())

    async def authorize_redirect(self, provider: str, request: Request, redirect_uri: str):
        self._init_providers()
        if not self._oauth:
            return JSONResponse({"error": "OAuth not configured"}, status_code=503)
        client = self._oauth.create_client(provider)
        if not client:
            return JSONResponse({"error": f"Unknown provider: {provider}"}, status_code=400)
        return await client.authorize_redirect(request, redirect_uri)

    async def authorize_access_token(self, provider: str, request: Request):
        self._init_providers()
        if not self._oauth:
            return None
        client = self._oauth.create_client(provider)
        if not client:
            return None
        try:
            token = await client.authorize_access_token(request)
            if token:
                userinfo = await self._get_userinfo(provider, token)
                self._store_token(provider, token, userinfo)
                return {"token": token, "userinfo": userinfo}
        except OAuthError as e:
            logger.warning("[OAuth] %s auth error: %s", provider, e)
        except Exception as e:
            logger.warning("[OAuth] %s error: %s", provider, e)
        return None

    async def _get_userinfo(self, provider: str, token: dict) -> dict:
        try:
            if provider == "google":
                userinfo = await self._oauth.google.parse_id_token(token)
                return {
                    "sub": userinfo.get("sub", ""),
                    "email": userinfo.get("email", ""),
                    "name": userinfo.get("name", ""),
                    "picture": userinfo.get("picture", ""),
                }
            elif provider == "github":
                async with httpx.AsyncClient() as client:
                    resp = await client.get(
                        "https://api.github.com/user",
                        headers={"Authorization": f"Bearer {token.get('access_token')}"},
                    )
                    data = resp.json()
                    return {
                        "sub": str(data.get("id", "")),
                        "email": data.get("email", "") or f"{data.get('login')}@github",
                        "name": data.get("name") or data.get("login", ""),
                        "picture": data.get("avatar_url", ""),
                    }
            elif provider == "discord":
                async with httpx.AsyncClient() as client:
                    resp = await client.get(
                        "https://discord.com/api/users/@me",
                        headers={"Authorization": f"Bearer {token.get('access_token')}"},
                    )
                    data = resp.json()
                    return {
                        "sub": str(data.get("id", "")),
                        "email": data.get("email", ""),
                        "name": data.get("global_name") or data.get("username", ""),
                        "picture": f"https://cdn.discordapp.com/avatars/{data.get('id')}/{data.get('avatar')}.png" if data.get("avatar") else "",
                    }
        except Exception as e:
            logger.warning("[OAuth] Userinfo failed for %s: %s", provider, e)
        return {"sub": "", "email": "", "name": "", "picture": ""}

    def _store_token(self, provider: str, token: dict, userinfo: dict):
        key = f"{provider}:{userinfo.get('sub', 'unknown')}"
        self._tokens[key] = {
            "provider": provider,
            "userinfo": userinfo,
            "access_token": token.get("access_token", ""),
            "refresh_token": token.get("refresh_token", ""),
            "expires_at": token.get("expires_at", 0),
            "stored_at": datetime.now().isoformat(),
        }
        self._save()

    def list_tokens(self) -> list[dict]:
        return [
            {
                "provider": t["provider"],
                "user": t["userinfo"].get("name", t["userinfo"].get("email", "unknown")),
                "email": t["userinfo"].get("email", ""),
                "picture": t["userinfo"].get("picture", ""),
                "stored_at": t.get("stored_at", ""),
            }
            for t in self._tokens.values()
        ]

    def remove_token(self, provider: str, user_sub: str) -> bool:
        key = f"{provider}:{user_sub}"
        if key in self._tokens:
            del self._tokens[key]
            self._save()
            return True
        return False


oauth_manager = OAuthManager()
