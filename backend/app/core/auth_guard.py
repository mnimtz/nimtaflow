"""Shared auth dependencies.

- enforce_auth: applied to the web data routers. It only requires a valid login
  when the `auth.enforce` setting is "true" — so the app keeps working until the
  admin explicitly turns login on (and the separate /v1 iOS API is unaffected).
- require_admin: always requires an authenticated admin (for user management),
  regardless of the enforce setting.
"""
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_token
from app.models.user import User, UserRole

# auto_error=False → missing token doesn't 401 by itself; we decide per setting.
_optional_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


async def _user_from_token(token: Optional[str], db: AsyncSession) -> Optional[User]:
    if not token:
        return None
    uid = decode_token(token)
    if not uid:
        return None
    user = await db.get(User, int(uid))
    if not user or not user.is_active:
        return None
    return user


async def enforce_auth(
    token: Optional[str] = Depends(_optional_scheme),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    from app.services.settings_loader import load_settings
    s = await load_settings(db)
    if str(s.get("auth.enforce", "false")).lower() != "true":
        return None  # login not enforced yet — allow through
    user = await _user_from_token(token, db)
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Login erforderlich")
    return user


async def require_admin(
    token: Optional[str] = Depends(_optional_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    user = await _user_from_token(token, db)
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Login erforderlich")
    if user.role != UserRole.admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Adminrechte erforderlich")
    return user
