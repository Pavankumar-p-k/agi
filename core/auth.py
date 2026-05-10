# core/auth.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import DEV_MODE, FIREBASE_CREDENTIALS
from .database import get_db, User

_firebase_ready = False


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
            # Assume env provided a raw JSON string is not supported here
            raise FileNotFoundError("Firebase credentials path must be a .json file")

        if cred_path and __import__("os").path.exists(cred_path):
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)
            _firebase_ready = True
    except Exception:
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


async def verify_token(
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
) -> User:
    # DEV mode bypass
    if not authorization:
        if DEV_MODE:
            return await _get_or_create_user(db, uid="dev", email="dev@local", display_name="Dev User")
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    token = authorization.replace("Bearer", "").strip()
    if not token:
        if DEV_MODE:
            return await _get_or_create_user(db, uid="dev", email="dev@local", display_name="Dev User")
        raise HTTPException(status_code=401, detail="Invalid token")

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

    # Fallback: treat token as uid/email
    uid = token
    email = token if "@" in token else f"{token}@local"
    return await _get_or_create_user(db, uid=uid, email=email, display_name=uid)
