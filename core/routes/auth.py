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

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(tags=["Authentication"])


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/auth/login")
async def password_login(body: LoginRequest, request: Request):
    """Authenticate with username+password, return session token."""
    from core.config import DEV_MODE
    auth_mgr = getattr(request.app.state, "auth_manager", None)
    if not auth_mgr:
        return {"token": None, "detail": "Auth not configured"}
    token = auth_mgr.create_session(body.username, body.password)
    if not token and DEV_MODE:
        auth_mgr.create_user(body.username, body.password, is_admin=True)
        token = auth_mgr.create_session(body.username, body.password)
    if not token:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=401, content={"detail": "Invalid credentials"})
    return {"token": token, "username": body.username.strip().lower()}

@router.get("/auth/status")
async def auth_status():
    try:
        from ..auth import get_auth_manager
        from ..oauth import oauth_manager
        am = get_auth_manager()
        providers = oauth_manager.get_providers() if hasattr(oauth_manager, "get_providers") else []
        return {
            "configured": am.is_configured,
            "user_count": len(am.users) if hasattr(am, "users") else 0,
            "providers": providers,
            "signup_enabled": am.signup_enabled if hasattr(am, "signup_enabled") else False,
        }
    except Exception as e:
        from fastapi import logger as _log
        _log.warning("[auth] status check failed: %s", e)
        return {"configured": False, "error": str(e)}


@router.get("/auth/providers")
async def oauth_providers():
    from ..oauth import oauth_manager
    return {"providers": oauth_manager.get_providers()}


@router.get("/auth/tokens")
async def oauth_tokens():
    from ..oauth import oauth_manager
    return {"tokens": oauth_manager.list_tokens()}


@router.get("/auth/login/{provider}")
async def oauth_login(provider: str, request: Request):
    from ..oauth import oauth_manager
    redirect_uri = str(request.url_for("oauth_callback"))
    return await oauth_manager.authorize_redirect(provider, request, redirect_uri)


@router.get("/auth/callback")
async def oauth_callback(request: Request):
    from ..oauth import oauth_manager
    provider = request.query_params.get("provider", "")
    if not provider:
        for p in oauth_manager.get_providers():
            if request.query_params.get("code") or request.query_params.get("state", "").startswith(p):
                provider = p
                break
    result = await oauth_manager.authorize_access_token(provider or "google", request)
    if result:
        return {"success": True, "user": result["userinfo"]}
    return {"success": False, "error": "OAuth failed"}


@router.post("/auth/revoke")
async def oauth_revoke(body: dict):
    from ..oauth import oauth_manager
    provider = body.get("provider", "")
    sub = body.get("sub", "")
    ok = oauth_manager.remove_token(provider, sub)
    return {"success": ok}
