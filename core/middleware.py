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
# core/middleware.py
# Shared middleware, decorators, and request helpers

import logging
import os
import secrets

logger = logging.getLogger(__name__)

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

INTERNAL_TOOL_TOKEN = os.environ.get("JARVIS_INTERNAL_TOKEN") or secrets.token_hex(32)
INTERNAL_TOOL_HEADER = "X-Jarvis-Internal-Token"


def require_admin(request: Request):
    """Raise 403 if the current user isn't an admin.

    Allows access when:
    - AUTH_ENABLED=false, or
    - The request carries the in-process internal-tool token used by loopback agent tools, or
    - The authenticated user is an admin (Firebase ID token or AuthManager session).
    """
    try:
        hdr = request.headers.get(INTERNAL_TOOL_HEADER)
        if hdr and secrets.compare_digest(hdr, INTERNAL_TOOL_TOKEN):
            return
        if getattr(request.state, "current_user", None) == "internal-tool":
            return
    except Exception as _e:
        logger.debug("middleware require_admin failed: %s", _e)

    if os.getenv("AUTH_ENABLED", "true").lower() == "false":
        return

    # Check AuthManager admin status
    auth_mgr = getattr(request.app.state, "auth_manager", None)
    if auth_mgr and auth_mgr.is_configured:
        user = getattr(request.state, "current_user", None)
        if user and auth_mgr.is_admin(user):
            return
    else:
        # Fallback: if no AuthManager, check via Firestore User model (admin field)
        user = getattr(request.state, "current_user_obj", None)
        if user and getattr(user, "is_admin", False):
            return

    raise HTTPException(403, "Admin only")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add standard security headers to all responses."""

    async def dispatch(self, request: Request, call_next) -> Response:
        nonce = secrets.token_hex(16)
        request.state.csp_nonce = nonce

        response = await call_next(request)
        path = request.url.path

        is_tool_render = path.startswith("/api/tools/") and path.endswith("/render")
        is_report = path.startswith("/api/research/report/")

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"

        if is_report:
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline'; "
                "style-src 'self' 'unsafe-inline'; "
                "font-src 'self'; "
                "img-src 'self' data: blob: https:; "
                "connect-src 'self'; "
                "frame-ancestors 'none'"
            )
        elif is_tool_render:
            pass
        else:
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                f"script-src 'self' 'nonce-{nonce}' https://cdn.jsdelivr.net; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "font-src 'self' https://cdn.jsdelivr.net; "
                "img-src 'self' data: blob:; "
                "media-src 'self' blob:; "
                "connect-src 'self'; "
                "frame-src 'self'; "
                "frame-ancestors 'none'"
            )
        return response
