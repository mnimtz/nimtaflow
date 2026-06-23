"""Share links — create/list/revoke (authed) + public token access (no login).

Two routers:
  router        — /shares       authed management (create, list, delete)
  public_router — /public/{token}  login-free guest access, validated per request
"""
import os
import secrets
import mimetypes
from datetime import datetime, timedelta, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.auth_guard import current_user_optional
from app.core.security import hash_password, verify_password
from app.models.user import User
from app.models.photo import Photo
from app.models.album import Album, AlbumPhoto
from app.models.share import Share, ShareType

router = APIRouter(prefix="/shares", tags=["shares"])
public_router = APIRouter(prefix="/public", tags=["public"])


# ── Schemas ─────────────────────────────────────────────────────────────────

class ShareCreate(BaseModel):
    share_type: ShareType
    album_id: Optional[int] = None
    photo_id: Optional[int] = None
    trip_from: Optional[str] = None
    trip_to: Optional[str] = None
    title: Optional[str] = None
    password: Optional[str] = None
    expires_days: Optional[int] = None
    allow_download: bool = True


class ShareOut(BaseModel):
    id: int
    token: str
    url: str
    share_type: str
    title: Optional[str]
    has_password: bool
    expires_at: Optional[datetime]
    allow_download: bool
    view_count: int
    created_at: datetime


async def _base_url(request: Request, db: AsyncSession) -> str:
    """Public base URL for building share links — the configured external URL
    (share.public_base_url) if set, else the request's own origin."""
    from app.services.settings_loader import load_settings
    s = await load_settings(db)
    base = (s.get("share.public_base_url") or "").strip().rstrip("/")
    return base or str(request.base_url).rstrip("/")


def _out(share: Share, base: str) -> ShareOut:
    return ShareOut(
        id=share.id, token=share.token, url=f"{base}/s/{share.token}",
        share_type=share.share_type.value, title=share.title,
        has_password=share.has_password, expires_at=share.expires_at,
        allow_download=share.allow_download, view_count=share.view_count,
        created_at=share.created_at,
    )


# ── Authed management ─────────────────────────────────────────────────────────

@router.post("", response_model=ShareOut, status_code=201)
async def create_share(body: ShareCreate, request: Request,
                       db: AsyncSession = Depends(get_db),
                       user: Optional[User] = Depends(current_user_optional)):
    # Validate the target exists so we never mint a link to nothing.
    if body.share_type == ShareType.album:
        if not body.album_id or not await db.get(Album, body.album_id):
            raise HTTPException(400, "Album nicht gefunden")
        title = body.title or (await db.get(Album, body.album_id)).name
    elif body.share_type == ShareType.photo:
        if not body.photo_id or not await db.get(Photo, body.photo_id):
            raise HTTPException(400, "Foto nicht gefunden")
        title = body.title or "Geteiltes Foto"
    elif body.share_type == ShareType.trip:
        if not (body.trip_from and body.trip_to):
            raise HTTPException(400, "Reise braucht trip_from und trip_to")
        title = body.title or "Reise"
    else:
        raise HTTPException(400, "Unbekannter Typ")

    expires_at = None
    if body.expires_days and body.expires_days > 0:
        expires_at = datetime.now(timezone.utc) + timedelta(days=body.expires_days)

    share = Share(
        token=secrets.token_urlsafe(24),
        share_type=body.share_type,
        album_id=body.album_id if body.share_type == ShareType.album else None,
        photo_id=body.photo_id if body.share_type == ShareType.photo else None,
        trip_from=body.trip_from if body.share_type == ShareType.trip else None,
        trip_to=body.trip_to if body.share_type == ShareType.trip else None,
        title=title,
        password_hash=hash_password(body.password) if body.password else None,
        expires_at=expires_at,
        allow_download=body.allow_download,
        created_by=user.id if user else None,
    )
    db.add(share)
    await db.commit()
    await db.refresh(share)
    return _out(share, await _base_url(request, db))


@router.get("", response_model=List[ShareOut])
async def list_shares(request: Request, db: AsyncSession = Depends(get_db),
                      user: Optional[User] = Depends(current_user_optional)):
    from app.core.access import _is_unrestricted
    q = select(Share).order_by(Share.created_at.desc())
    # A restricted account only ever sees its own share links/tokens, never others'.
    if not _is_unrestricted(user):
        q = q.where(Share.created_by == (user.id if user else -1))
    shares = (await db.execute(q)).scalars().all()
    base = await _base_url(request, db)
    return [_out(s, base) for s in shares]


class ShareUpdate(BaseModel):
    title: Optional[str] = None
    password: Optional[str] = None          # "" clears the password
    expires_days: Optional[int] = None      # 0 = never; -1 = leave unchanged
    allow_download: Optional[bool] = None


@router.patch("/{share_id}", response_model=ShareOut)
async def update_share(share_id: int, body: ShareUpdate, request: Request,
                       db: AsyncSession = Depends(get_db)):
    share = await db.get(Share, share_id)
    if not share:
        raise HTTPException(404)
    if body.title is not None:
        share.title = body.title
    if body.allow_download is not None:
        share.allow_download = body.allow_download
    if body.password is not None:
        share.password_hash = hash_password(body.password) if body.password else None
    if body.expires_days is not None and body.expires_days >= 0:
        share.expires_at = (datetime.now(timezone.utc) + timedelta(days=body.expires_days)
                            if body.expires_days > 0 else None)
    await db.commit()
    await db.refresh(share)
    return _out(share, await _base_url(request, db))


@router.delete("/{share_id}", status_code=204)
async def delete_share(share_id: int, db: AsyncSession = Depends(get_db)):
    share = await db.get(Share, share_id)
    if share:
        await db.delete(share)
        await db.commit()


# ── Public token access (no login) ────────────────────────────────────────────

async def _load_valid(token: str, db: AsyncSession) -> Share:
    share = (await db.execute(select(Share).where(Share.token == token))).scalar_one_or_none()
    if not share or share.is_expired:
        raise HTTPException(404, "Link ungültig oder abgelaufen")
    return share


def _check_pw(share: Share, pw: Optional[str]):
    if share.has_password and not (pw and verify_password(pw, share.password_hash)):
        raise HTTPException(401, "Passwort erforderlich oder falsch")


async def _photo_ids_query(share: Share):
    """A SELECT of the photo ids that belong to this share."""
    if share.share_type == ShareType.album:
        return select(AlbumPhoto.photo_id).where(AlbumPhoto.album_id == share.album_id)
    if share.share_type == ShareType.photo:
        return select(Photo.id).where(Photo.id == share.photo_id)
    # trip: date range on taken_at
    conds = [Photo.is_trashed == False]  # noqa: E712
    if share.trip_from:
        conds.append(Photo.taken_at >= datetime.fromisoformat(share.trip_from))
    if share.trip_to:
        conds.append(Photo.taken_at < datetime.fromisoformat(share.trip_to) + timedelta(days=1))
    return select(Photo.id).where(*conds)


async def _owns(share: Share, photo_id: int, db: AsyncSession) -> bool:
    sub = await _photo_ids_query(share)
    hit = await db.scalar(select(Photo.id).where(Photo.id == photo_id, Photo.id.in_(sub)))
    return hit is not None


class PublicPhoto(BaseModel):
    id: int
    is_video: bool
    width: Optional[int]
    height: Optional[int]


class PublicShare(BaseModel):
    type: str
    title: Optional[str]
    requires_password: bool
    allow_download: bool
    items: List[PublicPhoto] = []


@public_router.get("/{token}", response_model=PublicShare)
async def public_meta(token: str, db: AsyncSession = Depends(get_db),
                      pw: Optional[str] = Query(None)):
    share = await _load_valid(token, db)
    # Locked → reveal only that a password is needed, never the contents.
    if share.has_password and not (pw and verify_password(pw, share.password_hash)):
        return PublicShare(type=share.share_type.value, title=share.title,
                           requires_password=True, allow_download=share.allow_download, items=[])
    sub = await _photo_ids_query(share)
    rows = (await db.execute(
        select(Photo.id, Photo.is_video, Photo.width, Photo.height)
        .where(Photo.id.in_(sub), Photo.is_trashed == False)  # noqa: E712
        .order_by(Photo.taken_at.desc().nullslast(), Photo.id.desc())
    )).all()
    share.view_count = (share.view_count or 0) + 1
    await db.commit()
    return PublicShare(
        type=share.share_type.value, title=share.title, requires_password=False,
        allow_download=share.allow_download,
        items=[PublicPhoto(id=r[0], is_video=r[1], width=r[2], height=r[3]) for r in rows],
    )


async def _guard_media(token: str, photo_id: int, pw: Optional[str], db: AsyncSession) -> Photo:
    share = await _load_valid(token, db)
    _check_pw(share, pw)
    if not await _owns(share, photo_id, db):
        raise HTTPException(404)
    photo = await db.get(Photo, photo_id)
    if not photo:
        raise HTTPException(404)
    return photo


@public_router.get("/{token}/photo/{photo_id}/thumbnail")
async def public_thumbnail(token: str, photo_id: int, size: str = "medium",
                           pw: Optional[str] = Query(None), db: AsyncSession = Depends(get_db)):
    photo = await _guard_media(token, photo_id, pw, db)
    thumb = getattr(photo, f"thumb_{size}", None) or photo.thumb_medium or photo.thumb_small
    if not thumb or not os.path.exists(thumb):
        raise HTTPException(404, "Thumbnail not ready")
    return FileResponse(thumb, media_type="image/jpeg",
                        headers={"Cache-Control": "public, max-age=3600"})


@public_router.get("/{token}/photo/{photo_id}/original")
async def public_original(token: str, photo_id: int,
                          pw: Optional[str] = Query(None), db: AsyncSession = Depends(get_db)):
    share = await _load_valid(token, db)
    _check_pw(share, pw)
    if not share.allow_download:
        raise HTTPException(403, "Download für diesen Link nicht erlaubt")
    if not await _owns(share, photo_id, db):
        raise HTTPException(404)
    photo = await db.get(Photo, photo_id)
    if not photo:
        raise HTTPException(404)
    mime = photo.mime_type or mimetypes.guess_type(photo.path)[0] or "application/octet-stream"
    return FileResponse(photo.path, media_type=mime, filename=photo.filename)


@public_router.get("/{token}/photo/{photo_id}/video/stream")
async def public_video(token: str, photo_id: int,
                       pw: Optional[str] = Query(None), db: AsyncSession = Depends(get_db)):
    photo = await _guard_media(token, photo_id, pw, db)
    if not photo.is_video:
        raise HTTPException(404)
    web = photo.video_webm_path
    if web and os.path.exists(web):
        mt = "video/mp4" if web.endswith(".mp4") else "video/webm"
        return FileResponse(web, media_type=mt, headers={"Cache-Control": "public, max-age=86400"})
    mime = photo.mime_type or "video/mp4"
    return FileResponse(photo.path, media_type=mime)
