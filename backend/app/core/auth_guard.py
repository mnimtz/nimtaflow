"""Shared auth dependencies.

- enforce_auth: applied to the web data routers. It only requires a valid login
  when the `auth.enforce` setting is "true" — so the app keeps working until the
  admin explicitly turns login on (and the separate /v1 iOS API is unaffected).
- require_admin: always requires an authenticated admin (for user management),
  regardless of the enforce setting.

Token is accepted from the `Authorization: Bearer` header OR a `pf_token` cookie,
because <img>/AsyncImage requests (thumbnails, avatars, face crops) can't send a
custom header — the cookie lets them authenticate under enforce mode.
"""
from typing import Optional
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_token
from app.models.user import User, UserRole

# auto_error=False → missing token doesn't 401 by itself; we decide per setting.
_optional_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def _extract_token(request: Request, header_token: Optional[str]) -> Optional[str]:
    # Query param `access_token` lets media players that can't send an
    # Authorization header (iOS AVPlayer for video streaming) authenticate via a
    # plain URL. Same security posture as the web's pf_token cookie for <img>.
    return header_token or request.cookies.get("pf_token") or request.query_params.get("access_token")


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
    request: Request,
    token: Optional[str] = Depends(_optional_scheme),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    from app.services.settings_loader import load_settings
    s = await load_settings(db)
    if str(s.get("auth.enforce", "true")).lower() != "true":
        return None  # login not enforced yet — allow through
    user = await _user_from_token(_extract_token(request, token), db)
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Login erforderlich")
    return user


async def current_user_optional(
    request: Request,
    token: Optional[str] = Depends(_optional_scheme),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """Resolve the logged-in user from header or cookie token, or None — without
    consulting the enforce setting (used for per-user access_config filtering)."""
    return await _user_from_token(_extract_token(request, token), db)


async def require_admin(
    request: Request,
    token: Optional[str] = Depends(_optional_scheme),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """Require an admin — but only once login is enforced. When `auth.enforce`
    is off the whole app is open (single-user mode), so admin-only endpoints
    must NOT force a login (otherwise the UI bounces to /login with no reason)."""
    from app.services.settings_loader import load_settings
    s = await load_settings(db)
    user = await _user_from_token(_extract_token(request, token), db)
    if str(s.get("auth.enforce", "true")).lower() != "true":
        return user  # login not enforced — allow through (open app)
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Login erforderlich")
    if user.role != UserRole.admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Adminrechte erforderlich")
    return user
