"""User management (admin-only) + self-service password change."""
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.database import get_db
from app.core.security import hash_password
from app.core.auth_guard import require_admin
from app.models.user import User, UserRole
from app.schemas.user import UserDetail, UserCreate, UserUpdate, PasswordSet

router = APIRouter(prefix="/users", tags=["users"])


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
