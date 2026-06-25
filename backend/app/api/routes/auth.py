import re
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, timezone
from pydantic import BaseModel

from app.core.database import get_db
from app.core.security import verify_password, hash_password, create_access_token, create_refresh_token, decode_token
from app.models.user import User, UserRole
from app.schemas.user import UserOut, UserDetail, TokenResponse
from app.core.auth_guard import require_admin

router = APIRouter(prefix="/auth", tags=["auth"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@router.get("/status")
async def auth_status(db: AsyncSession = Depends(get_db)):
    """Tells the UI whether a first admin must be created (fresh install) and
    whether login is enforced (default: ON)."""
    from app.services.settings_loader import load_settings
    count = await db.scalar(select(func.count()).select_from(User))
    s = await load_settings(db)
    return {
        "needs_setup": (count or 0) == 0,
        "enforce": str(s.get("auth.enforce", "true")).lower() == "true",
    }


class SetupRequest(BaseModel):
    email: str
    name: str = "Admin"
    password: str


@router.post("/setup", response_model=TokenResponse)
async def setup(body: SetupRequest, db: AsyncSession = Depends(get_db)):
    """Create the FIRST admin on a fresh install (only works while there are no
    users). Auto-logs in by returning tokens."""
    if await db.scalar(select(func.count()).select_from(User)):
        raise HTTPException(409, "Einrichtung bereits abgeschlossen — bitte anmelden.")
    if not _EMAIL_RE.match((body.email or "").strip()):
        raise HTTPException(400, "Bitte eine gültige E-Mail angeben.")
    if len(body.password) < 6:
        raise HTTPException(400, "Passwort zu kurz (min. 6 Zeichen).")
    user = User(email=body.email.strip(), name=(body.name.strip() or "Admin"),
                hashed_password=hash_password(body.password), role=UserRole.admin)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
        token_type="bearer",
    )


@router.post("/login", response_model=TokenResponse)
async def login(form: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    user = await db.scalar(select(User).where(User.email == form.username, User.is_active == True))
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")

    user.last_login = datetime.now(timezone.utc)
    await db.commit()

    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
        token_type="bearer",
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(refresh_token: str, db: AsyncSession = Depends(get_db)):
    user_id = decode_token(refresh_token)
    if not user_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")
    user = await db.get(User, int(user_id))
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED)
    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
        token_type="bearer",
    )


async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)) -> User:
    user_id = decode_token(token)
    if not user_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")
    user = await db.get(User, int(user_id))
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED)
    return user


@router.get("/me", response_model=UserDetail)
async def me(current_user: User = Depends(get_current_user)):
    return current_user


class SelfPersonIn(BaseModel):
    person_id: Optional[int] = None      # null = unlink


@router.put("/me/person", response_model=UserDetail)
async def set_my_person(body: SelfPersonIn,
                        current_user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    """Link the logged-in account to a Person ('das bin ich'). Powers 'meine Frau',
    'wann habe ich X getroffen' etc. in chat. null unlinks."""
    if body.person_id is not None:
        from app.models.person import Person
        if not await db.get(Person, body.person_id):
            raise HTTPException(404, "Person nicht gefunden")
    current_user.person_id = body.person_id
    await db.commit()
    await db.refresh(current_user)
    return current_user


# ── NimtaFlow Pro: Schlüssel einlösen / generieren ──────────────────────────────

class RedeemIn(BaseModel):
    code: str


@router.post("/me/redeem", response_model=UserDetail)
async def redeem_pro_key(body: RedeemIn,
                         current_user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    """Redeem a NimtaFlow Pro license key → unlock Pro for this account."""
    from app.models.pro_key import ProKey
    from datetime import timezone
    code = (body.code or "").strip().upper()
    if not code:
        raise HTTPException(400, "Kein Schlüssel angegeben")
    key = (await db.execute(select(ProKey).where(ProKey.code == code))).scalar_one_or_none()
    if not key:
        raise HTTPException(404, "Ungültiger Schlüssel")
    if key.used_by_user_id and key.used_by_user_id != current_user.id:
        raise HTTPException(409, "Schlüssel wurde bereits eingelöst")
    key.used_by_user_id = current_user.id
    key.used_at = datetime.now(timezone.utc)
    current_user.is_pro = True
    if current_user.pro_source != "iap":
        current_user.pro_source = "key"
    await db.commit()
    await db.refresh(current_user)
    return current_user


class GenKeysIn(BaseModel):
    count: int = 1
    note: Optional[str] = None


@router.post("/pro/keys")
async def generate_pro_keys(body: GenKeysIn,
                            admin: User = Depends(require_admin),
                            db: AsyncSession = Depends(get_db)):
    """Admin: generate redeemable Pro keys (zum Verschenken / Familie)."""
    # require_admin lets anyone through when auth.enforce is off (open mode) and may
    # return None — but minting Pro keys must ALWAYS require a real admin.
    if admin is None or admin.role != UserRole.admin:
        raise HTTPException(403, "Adminrechte erforderlich")
    import secrets
    from app.models.pro_key import ProKey
    n = max(1, min(int(body.count or 1), 100))
    codes = []
    for _ in range(n):
        raw = secrets.token_hex(8).upper()                      # 16 hex chars
        code = f"NF-{raw[:4]}-{raw[4:8]}-{raw[8:12]}-{raw[12:16]}"
        db.add(ProKey(code=code, note=(body.note or None)))
        codes.append(code)
    await db.commit()
    return {"keys": codes}
