"""User management (admin-only) + self-service profile ("Mein Profil")."""
import io
import os
import re
import pathlib
from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.database import get_db
from app.core.security import hash_password, verify_password
from app.core.auth_guard import require_admin
from app.api.routes.auth import get_current_user
from app.models.user import User, UserRole
from app.schemas.user import (
    UserDetail, UserCreate, UserUpdate, PasswordSet, ProfileUpdate, PasswordChange,
)

router = APIRouter(prefix="/users", tags=["users"])

_AVATAR_DIR = pathlib.Path(os.getenv("CONFIG_PATH", "/config")) / "avatars"
try:
    _AVATAR_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    pass

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ── Self-service profile (current user) ──────────────────────────────────────
# NOTE: these /me routes MUST be declared before the /{user_id} routes below,
# otherwise FastAPI would match "me" as a user_id.

@router.get("/me", response_model=UserDetail)
async def get_my_profile(me: User = Depends(get_current_user)):
    return me


@router.patch("/me", response_model=UserDetail)
async def update_my_profile(body: ProfileUpdate, me: User = Depends(get_current_user),
                            db: AsyncSession = Depends(get_db)):
    fields = body.model_dump(exclude_unset=True)
    if "email" in fields and fields["email"] is not None:
        email = fields["email"].strip()
        if not _EMAIL_RE.match(email):
            raise HTTPException(400, "Bitte eine gültige E-Mail angeben — sie ist dein Login.")
        clash = await db.scalar(select(User).where(User.email == email, User.id != me.id))
        if clash:
            raise HTTPException(409, "E-Mail bereits vergeben")
        me.email = email
    if "name" in fields and fields["name"] is not None:
        me.name = fields["name"].strip() or me.name
    if "birthdate" in fields:
        me.birthdate = (fields["birthdate"] or None)
    await db.commit()
    await db.refresh(me)
    return me


@router.post("/me/password", status_code=204)
async def change_my_password(body: PasswordChange, me: User = Depends(get_current_user),
                             db: AsyncSession = Depends(get_db)):
    if not verify_password(body.current_password, me.hashed_password):
        raise HTTPException(400, "Aktuelles Passwort ist falsch")
    if len(body.new_password) < 6:
        raise HTTPException(400, "Neues Passwort zu kurz (min. 6 Zeichen)")
    me.hashed_password = hash_password(body.new_password)
    await db.commit()


@router.post("/me/avatar", response_model=UserDetail)
async def upload_my_avatar(file: UploadFile = File(...), me: User = Depends(get_current_user),
                           db: AsyncSession = Depends(get_db)):
    from PIL import Image
    data = await file.read()
    try:
        img = Image.open(io.BytesIO(data)).convert("RGB")
    except Exception:
        raise HTTPException(400, "Keine gültige Bilddatei")
    img.thumbnail((512, 512))
    out = _AVATAR_DIR / f"user_{me.id}.jpg"
    try:
        img.save(str(out), "JPEG", quality=85)
    except Exception:
        raise HTTPException(500, "Avatar konnte nicht gespeichert werden")
    me.avatar_path = str(out)
    await db.commit()
    await db.refresh(me)
    return me


@router.delete("/me/avatar", response_model=UserDetail)
async def delete_my_avatar(me: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if me.avatar_path and os.path.exists(me.avatar_path):
        try:
            os.remove(me.avatar_path)
        except Exception:
            pass
    me.avatar_path = None
    await db.commit()
    await db.refresh(me)
    return me


@router.get("/{user_id}/avatar")
async def get_user_avatar(user_id: int, db: AsyncSession = Depends(get_db)):
    user = await db.get(User, user_id)
    if not user or not user.avatar_path or not os.path.exists(user.avatar_path):
        raise HTTPException(404, "Kein Avatar")
    return FileResponse(user.avatar_path, media_type="image/jpeg",
                        headers={"Cache-Control": "no-cache"})


@router.get("", response_model=List[UserDetail])
async def list_users(_: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return (await db.execute(select(User).order_by(User.created_at))).scalars().all()


@router.post("", response_model=UserDetail, status_code=201)
async def create_user(body: UserCreate, _: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    exists = await db.scalar(select(User).where(User.email == body.email))
    if exists:
        raise HTTPException(409, "E-Mail bereits vergeben")
    user = User(
        email=body.email.strip(), name=body.name.strip(),
        hashed_password=hash_password(body.password),
        role=body.role, access_config=body.access_config,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.patch("/{user_id}", response_model=UserDetail)
async def update_user(user_id: int, body: UserUpdate, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404)
    fields = body.model_dump(exclude_unset=True)
    # Guard: don't let an admin lock the system out by demoting/deactivating the last active admin.
    if user.role == UserRole.admin and (fields.get("role") == UserRole.user or fields.get("is_active") is False):
        other_admins = await db.scalar(
            select(func.count()).where(
                User.role == UserRole.admin, User.is_active == True, User.id != user_id  # noqa: E712
            )
        )
        if not other_admins:
            raise HTTPException(400, "Das ist der letzte aktive Admin — Rolle/Status kann nicht entzogen werden.")
    for k, v in fields.items():
        setattr(user, k, v)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/{user_id}/password", status_code=204)
async def set_password(user_id: int, body: PasswordSet, _: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404)
    if len(body.password) < 6:
        raise HTTPException(400, "Passwort zu kurz (min. 6 Zeichen)")
    user.hashed_password = hash_password(body.password)
    await db.commit()


@router.delete("/{user_id}", status_code=204)
async def delete_user(user_id: int, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    if user_id == admin.id:
        raise HTTPException(400, "Du kannst dich nicht selbst löschen.")
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404)
    await db.delete(user)
    await db.commit()
