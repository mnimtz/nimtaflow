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

from fastapi import APIRouter, Depends, HTTPException, Request, Query, UploadFile, File
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.auth_guard import current_user_optional
from app.core.security import hash_password, verify_password
from app.models.user import User
from app.models.photo import Photo, PhotoStatus
from app.models.album import Album, AlbumPhoto
from app.models.share import Share, ShareType

router = APIRouter(prefix="/shares", tags=["shares"])
public_router = APIRouter(prefix="/public", tags=["public"])


# ── Schemas ─────────────────────────────────────────────────────────────────

class ShareCreate(BaseModel):
    share_type: ShareType
    album_id: Optional[int] = None
    photo_id: Optional[int] = None
    highlight_id: Optional[int] = None
    trip_from: Optional[str] = None
    trip_to: Optional[str] = None
    title: Optional[str] = None
    password: Optional[str] = None
    expires_days: Optional[int] = None
    allow_download: bool = True
    allow_upload: bool = False      # album shares: let guests upload into the album
    params: Optional[dict] = None   # postcard: {text, subtitle, theme, lang}


class ShareOut(BaseModel):
    id: int
    token: str
    url: str
    share_type: str
    title: Optional[str]
    has_password: bool
    expires_at: Optional[datetime]
    allow_download: bool
    allow_upload: bool = False
    view_count: int
    created_at: datetime


async def _base_url(request: Request, db: AsyncSession) -> str:
    """Public base URL for building share links — the configured external URL
    (share.public_base_url) if set, else the request's own origin."""
    from app.services.settings_loader import load_settings
    s = await load_settings(db)
    # Prefer a dedicated SHARE base URL (e.g. share.nimtaflow.com) over the general
    # public/login base — so share links can look nicer than the login host.
    base = ((s.get("share.share_base_url") or "").strip()
            or (s.get("share.public_base_url") or "").strip()).rstrip("/")
    return base or str(request.base_url).rstrip("/")


def _out(share: Share, base: str) -> ShareOut:
    return ShareOut(
        id=share.id, token=share.token, url=f"{base}/s/{share.token}",
        share_type=share.share_type.value, title=share.title,
        has_password=share.has_password, expires_at=share.expires_at,
        allow_download=share.allow_download, allow_upload=bool(getattr(share, "allow_upload", False)),
        view_count=share.view_count, created_at=share.created_at,
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
    elif body.share_type == ShareType.highlight:
        from app.models.highlight import Highlight
        h = await db.get(Highlight, body.highlight_id) if body.highlight_id else None
        if not h:
            raise HTTPException(400, "Highlight nicht gefunden")
        title = body.title or h.title or "Highlight"
    elif body.share_type == ShareType.postcard:
        if not body.photo_id or not await db.get(Photo, body.photo_id):
            raise HTTPException(400, "Foto nicht gefunden")
        title = body.title or (body.params or {}).get("text") or "Postkarte"
    else:
        raise HTTPException(400, "Unbekannter Typ")

    expires_at = None
    if body.expires_days and body.expires_days > 0:
        expires_at = datetime.now(timezone.utc) + timedelta(days=body.expires_days)

    share = Share(
        token=secrets.token_urlsafe(24),
        share_type=body.share_type,
        album_id=body.album_id if body.share_type == ShareType.album else None,
        photo_id=body.photo_id if body.share_type in (ShareType.photo, ShareType.postcard) else None,
        trip_from=body.trip_from if body.share_type == ShareType.trip else None,
        trip_to=body.trip_to if body.share_type == ShareType.trip else None,
        highlight_id=body.highlight_id if body.share_type == ShareType.highlight else None,
        params=body.params if body.share_type == ShareType.postcard else None,
        title=title,
        password_hash=hash_password(body.password) if body.password else None,
        expires_at=expires_at,
        allow_download=body.allow_download,
        allow_upload=body.allow_upload if body.share_type == ShareType.album else False,
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
                       db: AsyncSession = Depends(get_db),
                       user: Optional[User] = Depends(current_user_optional)):
    share = await db.get(Share, share_id)
    if not share:
        raise HTTPException(404)
    from app.core.access import _is_unrestricted
    if not _is_unrestricted(user) and share.created_by != (user.id if user else None):
        raise HTTPException(403)
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
async def delete_share(share_id: int, db: AsyncSession = Depends(get_db),
                       user: Optional[User] = Depends(current_user_optional)):
    share = await db.get(Share, share_id)
    if not share:
        return
    from app.core.access import _is_unrestricted
    if not _is_unrestricted(user) and share.created_by != (user.id if user else None):
        raise HTTPException(403)
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
    filename: Optional[str] = None
    taken_at: Optional[str] = None   # ISO date (so the guest view can show date + details)
    place: Optional[str] = None      # "Stadt, Land" (or location_name) when known


class PublicShare(BaseModel):
    type: str
    title: Optional[str]
    requires_password: bool
    allow_download: bool
    allow_upload: bool = False
    items: List[PublicPhoto] = []
    # Nur bei Video-Postkarte gesetzt: {text, subtitle, theme, text_color, lang, video}
    params: Optional[dict] = None


@public_router.get("/{token}", response_model=PublicShare)
async def public_meta(token: str, db: AsyncSession = Depends(get_db),
                      pw: Optional[str] = Query(None)):
    share = await _load_valid(token, db)
    # Locked → reveal only that a password is needed, never the contents.
    if share.has_password and not (pw and verify_password(pw, share.password_hash)):
        return PublicShare(type=share.share_type.value, title=share.title,
                           requires_password=True, allow_download=share.allow_download, items=[])
    # Highlight share = a single rendered video → no photo items; the guest page
    # plays it via /public/{token}/highlight-video.
    if share.share_type == ShareType.highlight:
        share.view_count = (share.view_count or 0) + 1
        await db.commit()
        return PublicShare(type="highlight", title=share.title, requires_password=False,
                           allow_download=share.allow_download, items=[])
    # Postcard share = a single rendered image → the guest page shows it via
    # /public/{token}/postcard. No photo items / no original download.
    if share.share_type == ShareType.postcard:
        share.view_count = (share.view_count or 0) + 1
        await db.commit()
        # Video-Grußkarte: eine Postkarte, deren Photo ein Video ist und
        # params.video=true. Der Frontend-Guest zeigt dann den Video-Player mit
        # Grußtext-Overlay statt eines statischen PNG. Wir signalisieren das über
        # den Type — der bestehende /postcard-PNG-Endpoint bleibt Fallback.
        _pr = share.params or {}
        _kind = "video_postcard" if _pr.get("video") else "postcard"
        _items = []
        if _kind == "video_postcard" and share.photo_id:
            ph = await db.get(Photo, share.photo_id)
            if ph and ph.is_video:
                _items = [PublicPhoto(id=ph.id, is_video=True,
                                      width=ph.width, height=ph.height,
                                      filename=ph.filename,
                                      taken_at=ph.taken_at.isoformat() if ph.taken_at else None,
                                      place=None)]
        return PublicShare(type=_kind, title=share.title, requires_password=False,
                           allow_download=False, items=_items,
                           params=(_pr if _kind == "video_postcard" else None))
    sub = await _photo_ids_query(share)
    rows = (await db.execute(
        select(Photo.id, Photo.is_video, Photo.width, Photo.height,
               Photo.filename, Photo.taken_at, Photo.city, Photo.country, Photo.location_name)
        .where(Photo.id.in_(sub), Photo.is_trashed == False)  # noqa: E712
        .order_by(Photo.taken_at.desc().nullslast(), Photo.id.desc())
    )).all()
    share.view_count = (share.view_count or 0) + 1
    await db.commit()

    def _place(city, country, loc):
        parts = [p for p in (city, country) if p]
        return ", ".join(parts) if parts else (loc or None)

    return PublicShare(
        type=share.share_type.value, title=share.title, requires_password=False,
        allow_download=share.allow_download,
        allow_upload=bool(getattr(share, "allow_upload", False)) and share.share_type == ShareType.album,
        items=[PublicPhoto(
            id=r[0], is_video=r[1], width=r[2], height=r[3], filename=r[4],
            taken_at=r[5].isoformat() if r[5] else None,
            place=_place(r[6], r[7], r[8]),
        ) for r in rows],
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


@public_router.post("/{token}/upload")
async def public_upload(token: str, files: List[UploadFile] = File(...),
                        pw: Optional[str] = Query(None), db: AsyncSession = Depends(get_db)):
    """Guest upload into a shared album. Only when the owner enabled it. Files land
    in the OWNER's Upload tree, are deduplicated, added to the album and enter the
    normal pipeline. Capped to images/videos under 300 MB each."""
    import hashlib
    from pathlib import Path
    from app.core.access import upload_base_dir
    from app.core.config import get_settings
    from app.models.source import PhotoSource
    share = await _load_valid(token, db)
    _check_pw(share, pw)
    if share.share_type != ShareType.album or not getattr(share, "allow_upload", False) or not share.album_id:
        raise HTTPException(403, "Upload für diesen Link nicht erlaubt")
    owner = await db.get(User, share.created_by) if share.created_by else None

    from app.services.settings_loader import load_settings
    s = await load_settings(db)
    default_dir = s.get("upload.default_dir")
    if not default_dir:
        roots = (await db.execute(select(PhotoSource.path).where(PhotoSource.enabled == True))).scalars().all()  # noqa: E712
        default_dir = min(roots, key=len) if roots else None
    default_dir = default_dir or get_settings().photos_path
    base = upload_base_dir(owner, default_dir)
    now = datetime.now(timezone.utc)
    dest_dir = Path(base) / "Upload" / now.strftime("%Y") / now.strftime("%Y-%m")
    MAX = 300 * 1024 * 1024

    results = []
    new_ids = []
    for up in files:
        try:
            content = await up.read()
            if len(content) > MAX:
                results.append({"filename": up.filename, "status": "too_large"}); continue
            mime = up.content_type or mimetypes.guess_type(up.filename or "")[0] or "application/octet-stream"
            if not (mime.startswith("image/") or mime.startswith("video/")):
                results.append({"filename": up.filename, "status": "rejected"}); continue
            h = hashlib.sha256(content).hexdigest()
            existing = await db.scalar(select(Photo.id).where(Photo.file_hash == h))
            if existing:
                pid = existing
                status = "duplicate"
            else:
                dest_dir.mkdir(parents=True, exist_ok=True)
                raw = up.filename or h
                dest = dest_dir / raw
                stem, suf, n = Path(raw).stem, Path(raw).suffix, 1
                while dest.exists():
                    dest = dest_dir / f"{stem}_{n}{suf}"; n += 1
                tmp = dest.with_suffix(dest.suffix + ".part")
                tmp.write_bytes(content); os.replace(tmp, dest)
                photo = Photo(path=str(dest), filename=dest.name, file_hash=h, file_size=len(content),
                              mime_type=mime, is_video=mime.startswith("video/"), status=PhotoStatus.pending)
                db.add(photo); await db.flush(); pid = photo.id
                new_ids.append(pid)
                status = "accepted"
            in_album = await db.scalar(select(AlbumPhoto.id).where(
                AlbumPhoto.album_id == share.album_id, AlbumPhoto.photo_id == pid))
            if not in_album:
                db.add(AlbumPhoto(album_id=share.album_id, photo_id=pid))
            results.append({"filename": up.filename, "status": status})
        except Exception:
            results.append({"filename": getattr(up, "filename", "?"), "status": "error"})
    await db.commit()
    try:
        from app.worker.tasks import process_photo_task
        for pid in new_ids:
            process_photo_task.delay(pid)
    except Exception:
        pass
    ok = sum(1 for r in results if r["status"] in ("accepted", "duplicate"))
    return {"uploaded": ok, "results": results}


@public_router.get("/{token}/postcard")
async def public_postcard(token: str, pw: Optional[str] = Query(None),
                          db: AsyncSession = Depends(get_db)):
    """Render the shared postcard PNG from its stored photo + text/theme params."""
    share = await _load_valid(token, db)
    _check_pw(share, pw)
    if share.share_type != ShareType.postcard or not share.photo_id:
        raise HTTPException(404)
    photo = await db.get(Photo, share.photo_id)
    if not photo:
        raise HTTPException(404)
    # Videos brauchen ein Bild-Thumbnail — photo.path zeigt bei Videos auf die
    # MP4/MOV-Datei, die PIL nicht öffnen kann. Vorher: Krachen mit 500. Jetzt:
    # bevorzugt thumb_large/medium/small (alles JPEG), Original nur bei Bildern.
    if photo.is_video:
        path = photo.thumb_large or photo.thumb_medium or photo.thumb_small
        if not path:
            raise HTTPException(415, "Postkarte für dieses Video nicht möglich (kein Vorschaubild)")
    else:
        path = photo.thumb_large or photo.thumb_medium or photo.path
    if not path or not os.path.exists(path):
        raise HTTPException(404, "Kein Bild")
    pr = share.params or {}
    place = ", ".join([p for p in (photo.city, photo.country) if p]) or photo.location_name or None
    import asyncio as _a
    from app.services.postcard import make_postcard
    png = await _a.to_thread(make_postcard, path, place, photo.taken_at,
                             pr.get("lang", "de"), pr.get("text") or None,
                             pr.get("subtitle") or None, pr.get("theme", "classic"),
                             pr.get("text_color") or None)
    return Response(content=png, media_type="image/png",
                    headers={"Cache-Control": "public, max-age=3600"})


@public_router.get("/{token}/postcard-video")
async def public_postcard_video(token: str, res: Optional[int] = Query(None),
                                pw: Optional[str] = Query(None),
                                db: AsyncSession = Depends(get_db)):
    """Stream für Video-Grußkarte: share.share_type=postcard mit params.video=true
    hat als share.photo_id ein Video. Der Gast bekommt den 720p-Transcode (bevorzugt),
    sonst 1080p/480p — je nachdem was fertig ist. `res` schaltet die Wunsch-Auflösung."""
    share = await _load_valid(token, db)
    _check_pw(share, pw)
    if share.share_type != ShareType.postcard or not share.photo_id:
        raise HTTPException(404)
    if not (share.params or {}).get("video"):
        raise HTTPException(404, "Kein Video für diese Postkarte")
    photo = await db.get(Photo, share.photo_id)
    if not photo or not photo.is_video:
        raise HTTPException(404)
    import pathlib as _pl

    def _cache_path(r: int) -> _pl.Path:
        return _pl.Path("/cache/videos") / f"{photo.id}_{r}.mp4"

    def _serve(p: _pl.Path):
        _cache_prefix = "/cache/"
        s = str(p)
        if s.startswith(_cache_prefix):
            return Response(headers={
                "X-Accel-Redirect": "/internal-video-cache/" + s[len(_cache_prefix):],
                "Content-Type": "video/mp4",
            })
        return FileResponse(s, media_type="video/mp4",
                            headers={"Cache-Control": "public, max-age=86400"})

    if res in (480, 720, 1080):
        p = _cache_path(res)
        if p.exists():
            return _serve(p)
        try:
            from app.worker.tasks import transcode_video_task
            transcode_video_task.delay(photo.id, res)
        except Exception:
            pass
    for r in (720, 1080, 480):
        p = _cache_path(r)
        if p.exists():
            return _serve(p)
    web = photo.video_webm_path
    if web and os.path.exists(web):
        return _serve(_pl.Path(web))
    mime = photo.mime_type or "video/mp4"
    return FileResponse(photo.path, media_type=mime)


@public_router.get("/{token}/highlight-video")
async def public_highlight_video(token: str, pw: Optional[str] = Query(None),
                                 db: AsyncSession = Depends(get_db)):
    """Stream the shared highlight's rendered MP4 (FileResponse handles Range)."""
    share = await _load_valid(token, db)
    _check_pw(share, pw)
    if share.share_type != ShareType.highlight or not share.highlight_id:
        raise HTTPException(404)
    from app.models.highlight import Highlight
    h = await db.get(Highlight, share.highlight_id)
    if not h or not h.file_path or not os.path.exists(h.file_path):
        raise HTTPException(404, "Highlight-Video nicht verfügbar")
    return FileResponse(h.file_path, media_type="video/mp4",
                        headers={"Cache-Control": "public, max-age=3600"})
