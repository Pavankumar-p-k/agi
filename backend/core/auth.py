from __future__ import annotations

from typing import Optional

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import FIREBASE_CREDENTIALS
from core.database import User, get_db, get_or_create_user

security = HTTPBearer(auto_error=False)
firebase_ready = False


def init_firebase() -> None:
    global firebase_ready
    try:
        import firebase_admin
        from firebase_admin import credentials

        if not firebase_admin._apps:
            cred = credentials.Certificate(FIREBASE_CREDENTIALS)
            firebase_admin.initialize_app(cred)
        firebase_ready = True
        print('[Auth] Firebase initialized')
    except Exception as exc:
        firebase_ready = False
        print(f'[Auth] Firebase disabled: {exc}')


async def _dev_user(db: AsyncSession) -> User:
    return await get_or_create_user(db, uid='dev-user', email='dev@local', display_name='Developer')


async def verify_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not credentials:
        return await _dev_user(db)

    token = credentials.credentials
    if not firebase_ready:
        return await _dev_user(db)

    try:
        from firebase_admin import auth

        decoded = auth.verify_id_token(token)
        uid = decoded.get('uid', 'dev-user')
        email = decoded.get('email') or f'{uid}@firebase.local'
        display_name = decoded.get('name') or 'Firebase User'
        return await get_or_create_user(db, uid=uid, email=email, display_name=display_name)
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f'Invalid auth token: {exc}') from exc
