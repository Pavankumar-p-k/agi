
# core/auth.py
from __future__ import annotations

import hmac
import os
from datetime import datetime
from typing import Optional

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import DEV_MODE, FIREBASE_CREDENTIALS
from .database import get_db, User
from .rate_limiter import api_rate_limiter

import time as time_module
import logging

logger = logging.getLogger(__name__)

_firebase_ready = False


def _safe_compare(a: str, b: str) -> bool:
    """Constant-time string comparison to prevent timing attacks."""
    return hmac.compare_digest(a.encode(), b.encode())


def _resolve_api_token() -> Optional[str]:
    """Resolve API token from env or config file."""
    return os.getenv("JARVIS_API_TOKEN") or os.getenv("API_TOKEN") or None


def _is_trusted_proxy(request: Request) -> bool:
    """Check if request came through a trusted proxy (Caddy, nginx, Traefik)."""
    trusted_proxies = os.getenv("TRUSTED_PROXIES", "").split(",")
    client_host = request.client.host if request.client else ""
    return client_host in ("127.0.0.1", "::1") or client_host in trusted_proxies


def init_firebase() -> None:
    global _firebase_ready
    try:
        import firebase_admin
        from firebase_admin import credentials

        if firebase_admin._apps:
            _firebase_ready = True
            return

        cred_path = FIREBASE_CREDENTIALS
        if cred_path and not cred_path.endswith(".json"):
            raise FileNotFoundError("Firebase credentials path must be a .json file")

        if cred_path and __import__("os").path.exists(cred_path):
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)
            _firebase_ready = True
    except Exception as e:
        logger.warning("[AUTH] Firebase init failed: %s", e)
        _firebase_ready = False


async def _get_or_create_user(
    db: AsyncSession,
    uid: str,
    email: Optional[str] = None,
    display_name: Optional[str] = None,
) -> User:
    result = await db.execute(select(User).where(User.uid == uid))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(uid=uid, email=email or f"{uid}@local", display_name=display_name)
        db.add(user)
        await db.commit()
        await db.refresh(user)
    else:
        user.last_seen = datetime.utcnow()
        await db.commit()
    return user


def _is_loopback(ip: str) -> bool:
    return ip in ("127.0.0.1", "::1", "localhost")


async def verify_token(
    authorization: Optional[str] = Header(None),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
) -> User:
    client_ip = request.client.host if request and request.client else "unknown"

    if not authorization:
        if DEV_MODE and _is_loopback(client_ip):
            return await _get_or_create_user(db, uid="dev", email="dev@local", display_name="Dev User")
        if not api_rate_limiter.check("auth", client_ip):
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    token = authorization.replace("Bearer", "").strip()
    if not token:
        if DEV_MODE and _is_loopback(client_ip):
            return await _get_or_create_user(db, uid="dev", email="dev@local", display_name="Dev User")
        if not api_rate_limiter.check("auth", client_ip):
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
        raise HTTPException(status_code=401, detail="Invalid token")

    # Constant-time API token check
    api_token = _resolve_api_token()
    if api_token and _safe_compare(token, api_token):
        return await _get_or_create_user(db, uid="api", email="api@local", display_name="API User")

    if _firebase_ready:
        try:
            from firebase_admin import auth as fb_auth

            decoded = fb_auth.verify_id_token(token)
            uid = decoded.get("uid")
            email = decoded.get("email")
            name = decoded.get("name") or decoded.get("displayName")
            return await _get_or_create_user(db, uid=uid, email=email, display_name=name)
        except Exception as e:
            if not DEV_MODE:
                raise HTTPException(status_code=401, detail=f"Token verification failed: {e}")

    if DEV_MODE and _is_loopback(client_ip):
        uid = token
        email = token if "@" in token else f"{token}@local"
        return await _get_or_create_user(db, uid=uid, email=email, display_name=uid)
    if not api_rate_limiter.check("auth", client_ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    raise HTTPException(status_code=401, detail="Invalid token")


async def verify_token_from_request(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    """Alternative auth dependency that reads the token from the request (supports trusted-proxy forwarding)."""
    auth_header = request.headers.get("Authorization")
    if auth_header:
        return await verify_token(authorization=auth_header, request=request, db=db)

    # Trusted-proxy: read X-Forwarded-User
    if _is_trusted_proxy(request):
        forwarded_user = request.headers.get("X-Forwarded-User") or request.headers.get("X-User")
        if forwarded_user:
            return await _get_or_create_user(db, uid=forwarded_user, email=f"{forwarded_user}@local", display_name=forwarded_user)

    if DEV_MODE:
        return await _get_or_create_user(db, uid="dev", email="dev@local", display_name="Dev User")

    raise HTTPException(status_code=401, detail="Missing Authorization header")
