"""Upload-Phase 3 — per-user self-managed sources.

A NON-admin user may add/manage their OWN photo source folders, but ONLY within
their allowed scope (home_root / folder_whitelist) and ONLY when the admin granted
the `allow_manage_sources` feature flag. Path validation is realpath-based so no
'..'/symlink can escape the scope (the IDOR class we guard everywhere). Admins use
the global /sources router; this one is for restricted accounts.
"""
import os
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.auth_guard import current_user_optional
from app.core.access import feature_allowed, path_within_user_scope, user_scope_prefixes
from app.models.source import PhotoSource
from app.schemas.source import SourceCreate, SourceOut

router = APIRouter(prefix="/my-sources", tags=["my-sources"])


def _require(user):
    """Must be a logged-in user with the allow_manage_sources flag (admins allowed too,
    feature_allowed → True for them)."""
    if user is None:
        raise HTTPException(401, "Anmeldung erforderlich.")
    if not feature_allowed(user, "allow_manage_sources", default=False):
        raise HTTPException(403, "Eigene Quellen verwalten ist für dieses Konto nicht freigeschaltet.")


@router.get("", response_model=List[SourceOut])
async def list_my_sources(db: AsyncSession = Depends(get_db), user=Depends(current_user_optional)):
    _require(user)
    rows = (await db.execute(
        select(PhotoSource).where(PhotoSource.owner_user_id == user.id).order_by(PhotoSource.created_at.desc())
    )).scalars().all()
    return rows


@router.get("/allowed-roots")
async def my_allowed_roots(user=Depends(current_user_optional)):
    """The folder prefixes the user may add sources under (shown as a hint in the UI)."""
    _require(user)
    return {"roots": user_scope_prefixes(user)}


@router.post("", response_model=SourceOut, status_code=201)
async def create_my_source(data: SourceCreate, db: AsyncSession = Depends(get_db),
                           user=Depends(current_user_optional)):
    _require(user)
    path = (data.path or "").rstrip("/")
    if not path:
        raise HTTPException(422, "Pfad fehlt.")
    # SECURITY: the path must be inside the user's allowed area, exist, and be a dir.
    if not path_within_user_scope(user, path):
        raise HTTPException(403, "Pfad liegt außerhalb deines erlaubten Bereichs.")
    if not os.path.isdir(path):
        raise HTTPException(400, "Ordner existiert nicht (oder ist kein Verzeichnis).")
    if await db.scalar(select(PhotoSource).where(PhotoSource.path == path)):
        raise HTTPException(409, "Diese Quelle gibt es bereits.")
    source = PhotoSource(
        path=path,
        name=(data.name or os.path.basename(path) or path)[:256],
        enabled=True,
        watch_enabled=bool(data.watch_enabled),
        recursive=bool(data.recursive),
        exclusion_patterns=data.exclusion_patterns,
        scan_interval_minutes=max(0, int(data.scan_interval_minutes or 0)),
        detect_deletions=bool(data.detect_deletions),
        owner_user_id=user.id,
    )
    db.add(source)
    await db.commit()
    await db.refresh(source)
    from app.worker.tasks import scan_source_task
    scan_source_task.delay(source.id)
    return source


async def _own_source(db, user, source_id) -> PhotoSource:
    src = await db.get(PhotoSource, source_id)
    if not src or src.owner_user_id != user.id:
        raise HTTPException(404, "Quelle nicht gefunden.")
    return src


@router.delete("/{source_id}", status_code=204)
async def delete_my_source(source_id: int, db: AsyncSession = Depends(get_db),
                           user=Depends(current_user_optional)):
    _require(user)
    src = await _own_source(db, user, source_id)
    await db.delete(src)
    await db.commit()


@router.post("/{source_id}/scan")
async def scan_my_source(source_id: int, db: AsyncSession = Depends(get_db),
                         user=Depends(current_user_optional)):
    _require(user)
    src = await _own_source(db, user, source_id)
    from app.worker.tasks import scan_source_task
    scan_source_task.delay(src.id)
    return {"status": "queued", "source_id": src.id}
