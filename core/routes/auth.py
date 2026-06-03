from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from datetime import timedelta
from typing import Dict

from ..auth import verify_token, init_firebase
from ..database import get_db, User
from ..config import SUPABASE_URL, SUPABASE_SERVICE_KEY

router = APIRouter(tags=["Authentication"])

@router.get("/auth/status")
async def auth_status():
    return {"status": "active", "provider": "firebase"}

# More auth routes would go here if they weren't in core/auth.py
# For now, we'll keep main.py's verify_token dependency as is.
