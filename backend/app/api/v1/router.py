"""API v1 — designed for iOS app consumption.

Key design decisions:
- Cursor-based pagination (cursor = last photo id) — stable even during inserts
- Range requests for video streaming (iOS AVPlayer requires this)
- Upload endpoint with multipart + duplicate detection (hash)
- Sync endpoint: GET /v1/sync?since=<iso8601> for incremental pull
- Consistent snake_case JSON, ISO-8601 dates
- All responses include X-PhotoFlow-Version header
"""
import hashlib
import os
import shutil
import mimetypes
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Header, Request
from fastapi.responses import FileResponse, StreamingResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from pydantic import BaseModel

from app.core.database import get_db
from app.core.auth_guard import current_user_optional
from app.core.access import photo_conditions, can_see_photo, user_can_access_photo, feature_allowed, upload_base_dir
from app.models.user import User, UserRole
from app.models.photo import Photo, PhotoStatus
from app.schemas.photo import PhotoBase

router = APIRouter(prefix="/v1", tags=["v1-ios"])

_UPLOAD_DIR = Path(os.getenv("CACHE_PATH", "/cache")) / "uploads"
try:
    _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
except PermissionError:
    _UPLOAD_DIR = Path("/tmp/photoflow-uploads")
    _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

APP_VERSION = "1.0.0"


def _version_header() -> dict:
    return {"X-PhotoFlow-Version": APP_VERSION}


# ── Schema ────────────────────────────────────────────────────────────────────

class PhotoV1(BaseModel):
    id: int
    filename: str
    taken_at: Optional[str]
    width: Optional[int]
    height: Optional[int]
    aspect_ratio: Optional[float]
    latitude: Optional[float]
    longitude: Optional[float]
    is_video: bool
    duration_seconds: Optional[float]
    is_favorite: bool
    is_archived: bool
    is_trashed: bool
    user_rating: Optional[int]
    status: str
    thumb_url: str
    thumb_medium_url: str
    original_url: str
    video_url: Optional[str]
    preview_url: Optional[str]

    model_config = {"from_attributes": True}


class PhotoPageV1(BaseModel):
    items: List[PhotoV1]
    next_cursor: Optional[int]   # pass as ?cursor= in next request
    total: int
    has_more: bool


class SyncResultV1(BaseModel):
    changed: List[PhotoV1]
    deleted_ids: List[int]
    server_time: str


def _to_v1(photo: Photo, req: Request) -> PhotoV1:
    # Relative URLs (no scheme/host): same-origin on web so the pf_token cookie is
    # sent and the port is never lost (request.base_url drops :8090 behind the proxy,
    # which broke every <img> on the web dashboard). iOS strips host anyway via
    # api.url(path+query), so relative is safe there too.
    base = ""
    aspect = (photo.width / photo.height) if photo.width and photo.height else None
    return PhotoV1(
        id=photo.id,
        filename=photo.filename,
        taken_at=photo.taken_at.isoformat() if photo.taken_at else None,
        width=photo.width,
        height=photo.height,
        aspect_ratio=round(aspect, 4) if aspect else None,
        latitude=photo.latitude,
        longitude=photo.longitude,
        is_video=photo.is_video,
        duration_seconds=photo.duration_seconds,
        is_favorite=photo.is_favorite,
        is_archived=photo.is_archived,
        is_trashed=photo.is_trashed,
        user_rating=photo.user_rating,
        status=photo.status.value,
        thumb_url=f"{base}/api/photos/{photo.id}/thumbnail?size=small",
        thumb_medium_url=f"{base}/api/photos/{photo.id}/thumbnail?size=medium",
        original_url=f"{base}/api/photos/{photo.id}/original",
        video_url=f"{base}/api/photos/{photo.id}/video/stream" if photo.is_video else None,
        preview_url=f"{base}/api/v1/photos/{photo.id}/preview" if photo.is_video else None,
    )


# ── Photo list with cursor pagination ─────────────────────────────────────────

@router.get("/photos", response_model=PhotoPageV1)
async def list_photos_v1(
    request: Request,
    cursor: Optional[int] = Query(None, description="Offset of the next page (pass back next_cursor)"),
    limit: int = Query(50, ge=1, le=200),
    favorites: bool = False,
    media_type: Optional[str] = Query(None, description="photo|video|raw"),
    person_id: Optional[int] = Query(None, description="only photos containing this person"),
    sort: str = Query("newest", description="newest|oldest|added|name"),
    archived: bool = False,
    trashed: bool = False,
    date_from: Optional[str] = Query(None, description="ISO date — taken_at >= this day"),
    date_to: Optional[str] = Query(None, description="ISO date — taken_at <= end of this day"),
    db: AsyncSession = Depends(get_db),
    user: Optional[User] = Depends(current_user_optional),
):
    """Offset-paginated photo list with the same filters/sort the web gallery has.

    Offset pagination (cursor = rows to skip) instead of id-cursor, so arbitrary
    sort orders (by taken_at etc.) work. Pass the returned next_cursor back.
    """
    from datetime import datetime as _dt, timedelta as _td
    from sqlalchemy import or_, func as _f
    from app.models.face import Face

    def _filtered():
        # Show every photo that has a thumbnail (= viewable), not only fully-'done'
        # ones. During bulk import a photo gets its thumbnail early but stays
        # 'processing' while AI/faces finish — the web shows these, so the app must
        # too (otherwise the app looks like it's missing thousands of new photos).
        q = select(Photo).where(
            Photo.thumb_small.isnot(None),
            Photo.is_trashed == trashed,
            Photo.is_archived == archived,
            *acl,
        )
        if date_from:
            try: q = q.where(Photo.taken_at >= _dt.fromisoformat(date_from))
            except ValueError: pass
        if date_to:
            try: q = q.where(Photo.taken_at < _dt.fromisoformat(date_to) + _td(days=1))
            except ValueError: pass
        if favorites:
            q = q.where(Photo.is_favorite == True)  # noqa: E712
        if media_type == "video":
            q = q.where(Photo.is_video == True)  # noqa: E712
        elif media_type == "photo":
            q = q.where(Photo.is_video == False,  # noqa: E712
                        or_(Photo.mime_type.is_(None), Photo.mime_type.not_like("image/raw%")))
        elif media_type == "raw":
            q = q.where(Photo.mime_type.like("image/raw%"))
        if person_id:
            # Subquery, not a join: a person with several faces in one photo would
            # otherwise yield duplicate rows → duplicate client keys → scrambled order.
            q = q.where(Photo.id.in_(select(Face.photo_id).where(Face.person_id == person_id)))
        return q

    acl = photo_conditions(user)
    q = _filtered()
    if sort == "oldest":
        q = q.order_by(Photo.taken_at.asc().nullsfirst(), Photo.id.asc())
    elif sort == "added":
        q = q.order_by(Photo.indexed_at.desc().nullslast(), Photo.id.desc())
    elif sort == "name":
        q = q.order_by(Photo.filename.asc())
    else:  # newest
        q = q.order_by(Photo.taken_at.desc().nullslast(), Photo.id.desc())

    offset = max(0, cursor or 0)
    rows = (await db.execute(q.offset(offset).limit(limit + 1))).scalars().all()
    has_more = len(rows) > limit
    items = rows[:limit]
    next_cursor = (offset + limit) if has_more else None

    total = await db.scalar(select(_f.count()).select_from(_filtered().subquery()))

    return PhotoPageV1(
        items=[_to_v1(p, request) for p in items],
        next_cursor=next_cursor,
        total=total or 0,
        has_more=has_more,
    )


@router.get("/photos/pets", response_model=PhotoPageV1)
async def list_pets_v1(request: Request, cursor: Optional[int] = Query(None),
                       limit: int = Query(60, ge=1, le=200),
                       db: AsyncSession = Depends(get_db),
                       user: Optional[User] = Depends(current_user_optional)):
    """Photos showing pets (from the AI tags) — iOS Haustiere view."""
    from app.models.tag import Tag, PhotoTag
    from app.api.routes.photos import _PET_TAGS
    from sqlalchemy import func as _f
    acl = photo_conditions(user)
    q = (select(Photo).distinct()
         .join(PhotoTag, PhotoTag.photo_id == Photo.id)
         .join(Tag, Tag.id == PhotoTag.tag_id)
         .where(_f.lower(Tag.name).in_(_PET_TAGS), Photo.is_trashed == False,  # noqa: E712
                Photo.thumb_small.isnot(None), *acl)
         .order_by(Photo.taken_at.desc().nullslast(), Photo.id.desc()))
    offset = max(0, cursor or 0)
    rows = (await db.execute(q.offset(offset).limit(limit + 1))).scalars().all()
    has_more = len(rows) > limit
    items = rows[:limit]
    return PhotoPageV1(items=[_to_v1(p, request) for p in items],
                       next_cursor=(offset + limit) if has_more else None,
                       total=0, has_more=has_more)


# ── Timeline buckets ─────────────────────────────────────────────────────────

@router.get("/photos/timeline/buckets")
async def timeline_buckets_v1(
    favorites: bool = False,
    media_type: Optional[str] = Query(None),
    person_id: Optional[int] = Query(None),
    archived: bool = False,
    trashed: bool = False,
    db: AsyncSession = Depends(get_db),
    user: Optional[User] = Depends(current_user_optional),
):
    """Monthly photo counts for the full (filtered) library — feeds the iOS
    timeline scrubber so it covers the complete date range without loading
    all photos first."""
    from datetime import datetime as _dt
    from sqlalchemy import func as _f, or_
    from app.models.face import Face

    acl = photo_conditions(user)
    q = select(Photo).where(
        Photo.thumb_small.isnot(None),
        Photo.is_trashed == trashed,
        Photo.is_archived == archived,
        *acl,
    )
    if favorites:
        q = q.where(Photo.is_favorite == True)  # noqa: E712
    if media_type == "video":
        q = q.where(Photo.is_video == True)  # noqa: E712
    elif media_type == "photo":
        q = q.where(Photo.is_video == False,  # noqa: E712
                    or_(Photo.mime_type.is_(None), Photo.mime_type.not_like("image/raw%")))
    elif media_type == "raw":
        q = q.where(Photo.mime_type.like("image/raw%"))
    if person_id:
        q = q.where(Photo.id.in_(select(Face.photo_id).where(Face.person_id == person_id)))

    sub = q.subquery()
    month = _f.to_char(_f.date_trunc("month", sub.c.taken_at), "YYYY-MM")
    rows = (await db.execute(
        select(month.label("m"), _f.count().label("c"))
        .select_from(sub)
        .where(sub.c.taken_at.isnot(None))
        .group_by(month)
        .order_by(month.desc())
    )).all()
    undated = await db.scalar(
        select(_f.count()).select_from(sub).where(sub.c.taken_at.is_(None))
    ) or 0
    buckets = [{"month": m, "count": c} for m, c in rows]
    return {"buckets": buckets, "undated": undated, "total": sum(c for _, c in rows) + undated}


# ── Single photo ──────────────────────────────────────────────────────────────

@router.get("/photos/{photo_id}", response_model=PhotoV1)
async def get_photo_v1(photo_id: int, request: Request, db: AsyncSession = Depends(get_db),
                       user: Optional[User] = Depends(current_user_optional)):
    photo = await db.get(Photo, photo_id)
    if not photo or photo.is_trashed or not await user_can_access_photo(db, photo_id, user):
        raise HTTPException(404)
    return _to_v1(photo, request)


class PhotoIdsRequest(BaseModel):
    ids: List[int] = []


@router.post("/photos/by-ids", response_model=List[PhotoV1])
async def photos_by_ids_v1(body: PhotoIdsRequest, request: Request,
                           db: AsyncSession = Depends(get_db),
                           user: Optional[User] = Depends(current_user_optional)):
    """Batch-load exactly these photo ids (ACL-scoped), returned IN THE REQUESTED ORDER.
    Powers 'open all chat results in the gallery' on iOS: the assistant returns result_ids,
    the app fetches the full PhotoV1 objects here and shows them in the swipe gallery."""
    ids = [int(i) for i in (body.ids or [])][:2000]
    if not ids:
        return []
    rows = (await db.execute(select(Photo).where(
        Photo.id.in_(ids), Photo.is_trashed == False, *photo_conditions(user)))).scalars().all()  # noqa: E712
    by_id = {p.id: p for p in rows}
    return [_to_v1(by_id[i], request) for i in ids if i in by_id]


@router.get("/photos/{photo_id}/detail")
async def photo_detail_v1(photo_id: int, request: Request, db: AsyncSession = Depends(get_db),
                          user: Optional[User] = Depends(current_user_optional)):
    """Full detail for the iOS photo-info sheet: description, place, people, tags,
    camera/EXIF — everything the thin PhotoV1 omits."""
    from app.models.tag import Tag, PhotoTag
    from app.models.face import Face
    from app.models.person import Person
    photo = await db.get(Photo, photo_id)
    if not photo or not await user_can_access_photo(db, photo_id, user):
        raise HTTPException(404)
    tags = [t for (t,) in (await db.execute(
        select(Tag.name).join(PhotoTag, PhotoTag.tag_id == Tag.id)
        .where(PhotoTag.photo_id == photo_id))).all()]
    # Per-FACE (with face_id) so the app can remove/reassign a single recognised face.
    people = [{"face_id": fid, "person_id": pid, "name": nm,
               "birthdate": bd.isoformat() if bd else None}
              for (fid, pid, nm, bd) in (await db.execute(
        select(Face.id, Face.person_id, Person.name, Person.birthdate).join(Person, Person.id == Face.person_id)
        .where(Face.photo_id == photo_id, Person.name.isnot(None)).order_by(Face.id))).all()]
    base = _to_v1(photo, request).model_dump()
    base.update({
        "description": photo.user_description or photo.description,
        "city": getattr(photo, "city", None),
        "country": getattr(photo, "country", None),
        "location_name": getattr(photo, "location_name", None),
        "camera_make": photo.camera_make, "camera_model": photo.camera_model,
        "lens_model": getattr(photo, "lens_model", None),
        "focal_length": getattr(photo, "focal_length", None),
        "aperture": getattr(photo, "aperture", None),
        "shutter_speed": getattr(photo, "shutter_speed", None),
        "iso": getattr(photo, "iso", None),
        "file_size": photo.file_size,
        "tags": tags, "people": people,
        "has_voice_note": bool(getattr(photo, "voice_note_path", None)),
    })
    return base


@router.delete("/photos/{photo_id}")
async def delete_photo_v1(photo_id: int, delete_file: bool = True,
                          db: AsyncSession = Depends(get_db),
                          user: Optional[User] = Depends(current_user_optional)):
    """Hard-delete from the iOS app (endgültig löschen)."""
    from app.api.routes.photos import _hard_delete, _source_roots
    photo = await db.get(Photo, photo_id)
    if not photo or not await user_can_access_photo(db, photo_id, user):
        raise HTTPException(404)
    await _hard_delete(db, photo, delete_file, await _source_roots(db))
    await db.commit()
    return {"deleted": photo_id}


# ── Sync endpoint (incremental pull for iOS background fetch) ─────────────────

@router.get("/sync", response_model=SyncResultV1)
async def sync_v1(
    request: Request,
    since: Optional[str] = Query(None, description="ISO-8601 datetime, e.g. 2026-01-01T00:00:00Z"),
    limit: int = Query(500, ge=1, le=2000),
    db: AsyncSession = Depends(get_db),
    user: Optional[User] = Depends(current_user_optional),
):
    """Return photos changed/added since `since`. iOS app calls this on wake."""
    since_dt: Optional[datetime] = None
    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(400, "Invalid since format. Use ISO-8601.")

    acl = photo_conditions(user)
    # Key off updated_at (bumped by a DB trigger on every change) so favorites,
    # ratings, descriptions, trashing etc. all surface in incremental sync —
    # not just newly-imported photos (indexed_at never changes).
    q = select(Photo).where(Photo.thumb_small.isnot(None), Photo.is_trashed == False, *acl)  # noqa: E712
    if since_dt:
        q = q.where(Photo.updated_at >= since_dt)
    q = q.order_by(Photo.updated_at.desc()).limit(limit)

    changed = (await db.execute(q)).scalars().all()

    # Photos trashed since `since` → the client removes them locally.
    trash_q = select(Photo.id).where(Photo.is_trashed == True)  # noqa: E712
    if since_dt:
        trash_q = trash_q.where(Photo.updated_at >= since_dt)
    deleted_ids = list((await db.execute(trash_q)).scalars().all())

    return SyncResultV1(
        changed=[_to_v1(p, request) for p in changed],
        deleted_ids=deleted_ids,
        server_time=datetime.now(timezone.utc).isoformat(),
    )


# ── Upload (for iOS share sheet / camera roll backup) ─────────────────────────

class UploadResult(BaseModel):
    id: Optional[int]
    filename: str
    status: str          # "accepted" | "duplicate" | "error"
    duplicate_of: Optional[int] = None


def _unique_path(directory: Path, filename: str) -> Path:
    """A non-colliding destination path inside `directory` — appends ' (2)', ' (3)'…"""
    stem = Path(filename).stem or "upload"
    ext = Path(filename).suffix
    cand = directory / f"{stem}{ext}"
    i = 2
    while cand.exists():
        cand = directory / f"{stem} ({i}){ext}"
        i += 1
    return cand


@router.post("/upload", response_model=List[UploadResult])
async def upload_photos(
    files: List[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    user: Optional[User] = Depends(current_user_optional),
):
    """Accept photo/video uploads. Each file lands in the UPLOADER'S OWN tree under
    `<home>/Upload/YYYY/YYYY-MM/` (so uploads never mix between users and are visible
    only to that user via the folder rules), enters the normal pipeline, and is
    deduplicated by SHA-256."""
    if not feature_allowed(user, "allow_upload"):
        raise HTTPException(403, "Upload für dieses Konto nicht erlaubt")

    from app.services.settings_loader import load_settings
    settings = await load_settings(db)
    # Deployment-agnostic upload base for unrestricted (admin) users: an explicit
    # `upload.default_dir` setting wins; otherwise derive from the FIRST configured
    # photo source root (guarantees the upload lands under a real, scanned source —
    # whatever the host's folder layout is), falling back to the configured
    # photos_path mount. No hardcoded "/photos" assumption.
    from app.models.source import PhotoSource
    from app.core.config import get_settings
    default_dir = settings.get("upload.default_dir")
    if not default_dir:
        # Prefer the SHORTEST enabled source root (the top-level mount, e.g. /photos)
        # over a deep per-person folder — a cleaner, more predictable upload home.
        roots = (await db.execute(
            select(PhotoSource.path).where(PhotoSource.enabled == True)  # noqa: E712
        )).scalars().all()
        default_dir = min(roots, key=len) if roots else None
    default_dir = default_dir or get_settings().photos_path
    base = upload_base_dir(user, default_dir)
    now = datetime.now(timezone.utc)
    dest_dir = Path(base) / "Upload" / now.strftime("%Y") / now.strftime("%Y-%m")

    results: List[UploadResult] = []
    for upload in files:
        try:
            content = await upload.read()
            file_hash = hashlib.sha256(content).hexdigest()

            existing = await db.scalar(select(Photo.id).where(Photo.file_hash == file_hash))
            if existing:
                results.append(UploadResult(
                    id=existing, filename=upload.filename or "unknown",
                    status="duplicate", duplicate_of=existing,
                ))
                continue

            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = _unique_path(dest_dir, upload.filename or f"{file_hash}")
            # Atomic write: .part → os.replace, so an aborted upload leaves no torso.
            tmp = dest.with_suffix(dest.suffix + ".part")
            tmp.write_bytes(content)
            os.replace(tmp, dest)

            mime = upload.content_type or mimetypes.guess_type(str(dest))[0] or "application/octet-stream"
            is_video = mime.startswith("video/")

            photo = Photo(
                path=str(dest),
                filename=dest.name,
                file_hash=file_hash,
                file_size=len(content),
                mime_type=mime,
                is_video=is_video,
                status=PhotoStatus.pending,
            )
            db.add(photo)
            await db.flush()
            results.append(UploadResult(id=photo.id, filename=photo.filename, status="accepted"))

        except Exception as e:
            results.append(UploadResult(id=None, filename=upload.filename or "?", status=f"error: {e}"))

    await db.commit()

    # Kick off the full pipeline (thumbnails + AI + faces) for each newly accepted
    # photo — without this they'd sit in 'pending' forever with no thumbnail.
    try:
        from app.worker.tasks import process_photo_task
        for r in results:
            if r.status == "accepted" and r.id:
                process_photo_task.delay(r.id)
    except Exception:
        pass

    return results


# ── Video streaming with Range support (required for iOS AVPlayer) ─────────────

@router.get("/photos/{photo_id}/stream")
async def stream_video_v1(
    photo_id: int,
    request: Request,
    range: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
    user: Optional[User] = Depends(current_user_optional),
):
    """HTTP Range-aware video stream. iOS AVPlayer requires Range support."""
    photo = await db.get(Photo, photo_id)
    if not photo or not photo.is_video or not await user_can_access_photo(db, photo_id, user):
        raise HTTPException(404)
    if not feature_allowed(user, "allow_download"):
        raise HTTPException(403, "Download nicht erlaubt")

    video_path = photo.video_webm_path or photo.path
    if not os.path.exists(video_path):
        raise HTTPException(404, "Video file not found")

    file_size = os.path.getsize(video_path)
    mime = "video/webm" if video_path.endswith(".webm") else (photo.mime_type or "video/mp4")

    if range:
        # Parse Range: bytes=start-end
        try:
            byte_range = range.replace("bytes=", "")
            start_str, end_str = byte_range.split("-")
            start = int(start_str) if start_str else 0
            end = int(end_str) if end_str else file_size - 1
        except Exception:
            raise HTTPException(416)

        end = min(end, file_size - 1)
        chunk_size = end - start + 1

        def iter_file():
            with open(video_path, "rb") as f:
                f.seek(start)
                remaining = chunk_size
                while remaining > 0:
                    data = f.read(min(65536, remaining))
                    if not data:
                        break
                    remaining -= len(data)
                    yield data

        return StreamingResponse(
            iter_file(),
            status_code=206,
            media_type=mime,
            headers={
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(chunk_size),
                **_version_header(),
            },
        )

    return FileResponse(
        video_path,
        media_type=mime,
        headers={"Accept-Ranges": "bytes", **_version_header()},
    )


# ── Video preview (animated WebP) ─────────────────────────────────────────────

@router.get("/photos/{photo_id}/preview")
async def video_preview_v1(photo_id: int, db: AsyncSession = Depends(get_db),
                           user: Optional[User] = Depends(current_user_optional)):
    """Return animated WebP hover preview for a video."""
    photo = await db.get(Photo, photo_id)
    if not photo or not photo.is_video or not await user_can_access_photo(db, photo_id, user):
        raise HTTPException(404)

    cache_root = os.getenv("CACHE_PATH", "/cache")
    from app.services.processing.thumbnails import generate_video_preview_webp
    preview = generate_video_preview_webp(photo.path, cache_root)
    if not preview or not os.path.exists(preview):
        raise HTTPException(404, "Preview not available")

    mime = "image/webp" if preview.endswith(".webp") else "image/gif"
    return FileResponse(preview, media_type=mime, headers={"Cache-Control": "public, max-age=86400"})


# ── Sprite sheet for video scrubbing ─────────────────────────────────────────

@router.get("/photos/{photo_id}/sprite.jpg")
async def video_sprite_v1(photo_id: int, db: AsyncSession = Depends(get_db),
                          user: Optional[User] = Depends(current_user_optional)):
    """JPEG sprite sheet for video scrubbing (thumbnail track)."""
    photo = await db.get(Photo, photo_id)
    if not photo or not photo.is_video or not await user_can_access_photo(db, photo_id, user):
        raise HTTPException(404)

    cache_root = os.getenv("CACHE_PATH", "/cache")
    from app.services.processing.thumbnails import generate_video_sprite
    result = generate_video_sprite(photo.path, cache_root)
    if not result:
        raise HTTPException(404, "Sprite not available")
    sprite_path, _ = result
    return FileResponse(sprite_path, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=604800"})


@router.get("/photos/{photo_id}/sprite.vtt")
async def video_sprite_vtt_v1(photo_id: int, db: AsyncSession = Depends(get_db),
                              user: Optional[User] = Depends(current_user_optional)):
    """WebVTT thumbnail track for timeline scrubbing."""
    photo = await db.get(Photo, photo_id)
    if not photo or not photo.is_video or not await user_can_access_photo(db, photo_id, user):
        raise HTTPException(404)

    cache_root = os.getenv("CACHE_PATH", "/cache")
    from app.services.processing.thumbnails import generate_video_sprite
    result = generate_video_sprite(photo.path, cache_root)
    if not result:
        raise HTTPException(404)
    _, vtt_path = result
    return FileResponse(vtt_path, media_type="text/vtt", headers={"Cache-Control": "public, max-age=604800"})


# ── Favorites / Rating (mobile actions) ───────────────────────────────────────

@router.patch("/photos/{photo_id}/favorite")
async def favorite_v1(photo_id: int, db: AsyncSession = Depends(get_db),
                      user: Optional[User] = Depends(current_user_optional)):
    photo = await db.get(Photo, photo_id)
    if not photo or not await user_can_access_photo(db, photo_id, user):
        raise HTTPException(404)
    photo.is_favorite = not photo.is_favorite
    await db.commit()
    return {"id": photo_id, "is_favorite": photo.is_favorite}


@router.patch("/photos/{photo_id}/rating")
async def rating_v1(photo_id: int, rating: int = 0, db: AsyncSession = Depends(get_db),
                    user: Optional[User] = Depends(current_user_optional)):
    photo = await db.get(Photo, photo_id)
    if not photo or not await user_can_access_photo(db, photo_id, user):
        raise HTTPException(404)
    photo.user_rating = max(0, min(5, rating))
    await db.commit()
    return {"id": photo_id, "user_rating": photo.user_rating}


# ── Search ────────────────────────────────────────────────────────────────────

@router.get("/search", response_model=PhotoPageV1)
async def search_v1(
    request: Request,
    q: str = Query(..., min_length=1),
    limit: int = Query(30, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: Optional[User] = Depends(current_user_optional),
):
    """Smart search — same engine as the web: semantic (embeddings) + keywords +
    tags + person names + relationship phrases ("Bilder meiner Ehefrau")."""
    from app.services.photo_search import search_photos
    from app.services.settings_loader import load_settings
    settings = await load_settings(db)
    photos = await search_photos(db, q, settings, limit=limit, extra_conditions=photo_conditions(user))
    return PhotoPageV1(
        items=[_to_v1(p, request) for p in photos],
        next_cursor=None,
        total=len(photos),
        has_more=False,
    )


# ── App info / capabilities ───────────────────────────────────────────────────

@router.get("/info")
async def info_v1():
    """iOS app uses this to discover server capabilities on first connect."""
    from app.services.hw_accel import detect_hw
    hw = detect_hw()
    return {
        "version": APP_VERSION,
        "api_version": 1,
        "features": {
            "upload": True,
            "video": True,
            "hw_transcode": hw.available and hw.name != "software",
            "hw_accel": hw.name,
            "face_recognition": False,   # toggle when enabled
            "semantic_search": False,     # toggle when AI configured
        },
        "limits": {
            "upload_max_mb": 500,
            "upload_formats": ["jpg", "jpeg", "png", "heic", "heif", "raw", "dng", "mp4", "mov", "m4v"],
        },
    }


# ── People (iOS app) ──────────────────────────────────────────────────────────

class PersonV1(BaseModel):
    id: int
    name: str
    face_count: int
    photo_count: int = 0
    avatar_url: str


@router.get("/people", response_model=List[PersonV1])
async def people_v1(request: Request, include_unnamed: bool = True, db: AsyncSession = Depends(get_db),
                    user: Optional[User] = Depends(current_user_optional)):
    from app.models.person import Person
    from app.models.face import Face
    from sqlalchemy import func as _f
    from app.core.access import visible_person_subquery, photo_conditions
    pq = select(Person).where(Person.is_hidden == False).order_by(Person.name)  # noqa: E712
    # A restricted account only sees persons that appear in photos it may access
    # (else the iOS People tab leaks the whole library) — see visible_person_subquery.
    vps = visible_person_subquery(user)
    if vps is not None:
        pq = pq.where(Person.id.in_(vps))
    persons = (await db.execute(pq)).scalars().all()
    acl = photo_conditions(user)
    cq = select(Face.person_id, _f.count()).where(Face.person_id.isnot(None))
    # photo_count = DISTINCT photos a person appears in (several faces in one photo
    # must not inflate it) — this is the metric the People tab sorts by.
    pcq = select(Face.person_id, _f.count(_f.distinct(Face.photo_id))).where(Face.person_id.isnot(None))
    if acl:
        sub_ids = select(Photo.id).where(*acl)
        cq = cq.where(Face.photo_id.in_(sub_ids))
        pcq = pcq.where(Face.photo_id.in_(sub_ids))
    counts = dict((await db.execute(cq.group_by(Face.person_id))).all())
    photo_counts = dict((await db.execute(pcq.group_by(Face.person_id))).all())
    out = []
    for p in persons:
        named = bool((p.name or "").strip())
        if not named and not include_unnamed:
            continue
        out.append(PersonV1(id=p.id, name=p.name or "Unbekannt", face_count=counts.get(p.id, 0),
                            photo_count=photo_counts.get(p.id, 0),
                            avatar_url=f"/api/people/{p.id}/avatar"))
    # Sort most photos → fewest (then name) so the People tab opens on the people
    # the user has the most pictures of. iOS keeps server order, so this fixes the
    # already-installed app without an app update.
    out.sort(key=lambda r: (-r.photo_count, -r.face_count, r.name.lower()))
    return out


@router.get("/people/{person_id}/photos", response_model=PhotoPageV1)
async def person_photos_v1(person_id: int, request: Request,
                           cursor: Optional[int] = Query(None), limit: int = Query(50, ge=1, le=200),
                           sort: str = Query("newest", description="newest | oldest"),
                           media_type: Optional[str] = Query(None, description="photo | video"),
                           db: AsyncSession = Depends(get_db),
                           user: Optional[User] = Depends(current_user_optional)):
    from app.models.face import Face
    from sqlalchemy import func as _f
    acl = photo_conditions(user)
    sub = select(Face.photo_id).where(Face.person_id == person_id)
    # Media filter so the person-detail "Fotos/Videos" toggle actually works (the
    # iOS GridMediaFilter sends "photo"/"video"). Applied to BOTH the page and the
    # total count so the toggle is consistent.
    mt = []
    if media_type == "video":
        mt = [Photo.is_video == True]   # noqa: E712
    elif media_type == "photo":
        mt = [Photo.is_video == False]  # noqa: E712
    q = select(Photo).where(Photo.id.in_(sub), Photo.thumb_small.isnot(None), Photo.is_trashed == False, *mt, *acl)  # noqa: E712
    # Sort by CAPTURE DATE, not Photo.id. id-order = IMPORT order: an old photo
    # imported recently has a high id and wrongly floated to the top of "newest"
    # ("Sortierung total gemischt"). Offset-cursor so date sorting paginates cleanly;
    # Photo.id is only the stable tiebreaker for equal timestamps.
    if sort == "oldest":
        q = q.order_by(Photo.taken_at.asc().nullsfirst(), Photo.id.asc())
    else:
        q = q.order_by(Photo.taken_at.desc().nullslast(), Photo.id.desc())
    offset = max(0, cursor or 0)
    rows = (await db.execute(q.offset(offset).limit(limit + 1))).scalars().all()
    has_more = len(rows) > limit
    items = rows[:limit]
    total = await db.scalar(select(_f.count()).select_from(
        select(Photo).where(Photo.id.in_(sub), Photo.is_trashed == False, *mt, *acl).subquery()))  # noqa: E712
    return PhotoPageV1(items=[_to_v1(p, request) for p in items],
                       next_cursor=(offset + limit) if has_more else None,
                       total=total or 0, has_more=has_more)


@router.get("/photos/{photo_id}/postcard")
async def photo_postcard_v1(photo_id: int, lang: str = "de",
                            text: Optional[str] = None, subtitle: Optional[str] = None,
                            theme: str = "classic", text_color: Optional[str] = None,
                            db: AsyncSession = Depends(get_db),
                            user: Optional[User] = Depends(current_user_optional)):
    """Shareable postcard PNG (iOS share sheet). Auth via ?access_token=.
    Greeting (text), message (subtitle) and theme are caller-supplied."""
    from fastapi import HTTPException
    from fastapi.responses import Response
    import os as _os
    photo = await db.scalar(select(Photo).where(Photo.id == photo_id, *photo_conditions(user)))
    if not photo:
        raise HTTPException(404)
    path = photo.thumb_large or photo.thumb_medium or photo.path
    if not path or not _os.path.exists(path):
        raise HTTPException(404)
    place = ", ".join([p for p in (photo.city, photo.country) if p]) or photo.location_name or None
    import asyncio as _a
    from app.services.postcard import make_postcard
    png = await _a.to_thread(make_postcard, path, place, photo.taken_at, lang,
                             (text or None), (subtitle or None), theme, (text_color or None))
    return Response(content=png, media_type="image/png")


@router.post("/photos/{photo_id}/voice-note")
async def set_voice_note_v1(photo_id: int, file: UploadFile = File(...),
                            db: AsyncSession = Depends(get_db),
                            user: Optional[User] = Depends(current_user_optional)):
    """Attach a voice memo to a photo (iOS). Stored in the cache."""
    from fastapi import HTTPException
    import os as _os
    from app.core.config import get_settings
    photo = await db.get(Photo, photo_id)
    if not photo or not await user_can_access_photo(db, photo_id, user):
        raise HTTPException(404)
    data = await file.read()
    if len(data) > 25 * 1024 * 1024:
        raise HTTPException(413)
    d = _os.path.join(get_settings().cache_path, "voice_notes")
    _os.makedirs(d, exist_ok=True)
    fn = (file.filename or "").lower()
    ext = ".m4a" if (fn.endswith(".m4a") or "mp4" in (file.content_type or "")) else (".mp3" if fn.endswith(".mp3") else ".webm")
    path = _os.path.join(d, f"{photo_id}{ext}")
    with open(path, "wb") as fh:
        fh.write(data)
    photo.voice_note_path = path
    await db.commit()
    return {"ok": True}


@router.get("/photos/{photo_id}/voice-note")
async def get_voice_note_v1(photo_id: int, db: AsyncSession = Depends(get_db),
                            user: Optional[User] = Depends(current_user_optional)):
    from fastapi import HTTPException
    from fastapi.responses import FileResponse
    import os as _os
    photo = await db.get(Photo, photo_id)
    if not photo or not await user_can_access_photo(db, photo_id, user) or not getattr(photo, "voice_note_path", None) or not _os.path.exists(photo.voice_note_path):
        raise HTTPException(404)
    ext = _os.path.splitext(photo.voice_note_path)[1].lower()
    mt = {".m4a": "audio/mp4", ".mp3": "audio/mpeg"}.get(ext, "audio/webm")
    return FileResponse(photo.voice_note_path, media_type=mt)


@router.delete("/photos/{photo_id}/voice-note")
async def delete_voice_note_v1(photo_id: int, db: AsyncSession = Depends(get_db),
                               user: Optional[User] = Depends(current_user_optional)):
    from fastapi import HTTPException
    import os as _os
    photo = await db.get(Photo, photo_id)
    if not photo or not await user_can_access_photo(db, photo_id, user):
        raise HTTPException(404)
    if getattr(photo, "voice_note_path", None):
        try:
            if _os.path.exists(photo.voice_note_path):
                _os.remove(photo.voice_note_path)
        except Exception:
            pass
        photo.voice_note_path = None
        await db.commit()
    return {"ok": True}


class AskPhotoV1(BaseModel):
    question: str
    provider: Optional[str] = None


@router.post("/photos/{photo_id}/ask")
async def ask_photo_v1(photo_id: int, body: AskPhotoV1, db: AsyncSession = Depends(get_db),
                       user: Optional[User] = Depends(current_user_optional)):
    """Frag-das-Foto (iOS): free-text question about one photo via a VLM."""
    from fastapi import HTTPException
    ok = await db.scalar(select(Photo.id).where(Photo.id == photo_id, *photo_conditions(user)))
    if not ok:
        raise HTTPException(404)
    from app.services.settings_loader import load_settings
    from app.services.ask_photo import ask_photo
    s = await load_settings(db)
    return await ask_photo(db, photo_id, body.question, s, body.provider)


# ── Relationships (iOS app) ───────────────────────────────────────────────────

@router.get("/relationships")
async def relationships_v1(db: AsyncSession = Depends(get_db),
                           user: Optional[User] = Depends(current_user_optional)):
    from app.api.routes.relationships import graph as _graph
    return await _graph(db=db, user=user)   # restricted accounts get an empty graph


# ── Albums (iOS app) ──────────────────────────────────────────────────────────

class AlbumV1(BaseModel):
    id: int
    name: str
    description: Optional[str]
    album_type: str
    photo_count: int
    cover_url: Optional[str]
    is_trip: bool = False   # stored manual trip (smart_criteria.trip) → iOS Reisen tab


@router.get("/albums", response_model=List[AlbumV1])
async def albums_v1(request: Request, db: AsyncSession = Depends(get_db),
                    user: Optional[User] = Depends(current_user_optional)):
    """Album list with cover thumbnails — same shape the gallery grid understands."""
    from app.models.album import Album, AlbumPhoto
    from sqlalchemy import func as _f
    from app.core.access import photo_conditions
    acl = photo_conditions(user)
    albums = (await db.execute(select(Album).order_by(Album.created_at.desc()))).scalars().all()
    # Counts + covers scoped to accessible photos so a restricted account never sees
    # album names/counts/covers for albums it has no access into.
    cnt_q = select(AlbumPhoto.album_id, _f.count())
    if acl:
        cnt_q = cnt_q.join(Photo, Photo.id == AlbumPhoto.photo_id).where(*acl)
    counts = dict((await db.execute(cnt_q.group_by(AlbumPhoto.album_id))).all())
    # cover = explicit cover_photo_id (if visible), else the first accessible photo
    cov_q = select(AlbumPhoto.album_id, _f.min(AlbumPhoto.photo_id))
    if acl:
        cov_q = cov_q.join(Photo, Photo.id == AlbumPhoto.photo_id).where(*acl)
    first_photo = dict((await db.execute(cov_q.group_by(AlbumPhoto.album_id))).all())
    out = []
    for a in albums:
        cnt = counts.get(a.id, 0)
        if acl and not cnt:
            continue  # restricted user can't see into this album at all → hide it
        cover_id = first_photo.get(a.id) if acl else (a.cover_photo_id or first_photo.get(a.id))
        out.append(AlbumV1(
            id=a.id, name=a.name, description=a.description,
            album_type=a.album_type.value if hasattr(a.album_type, "value") else str(a.album_type),
            photo_count=cnt,
            cover_url=(f"/api/photos/{cover_id}/thumbnail?size=medium" if cover_id else None),
            is_trip=bool((a.smart_criteria or {}).get("trip")),
        ))
    return out


@router.get("/albums/{album_id}/photos", response_model=PhotoPageV1)
async def album_photos_v1(album_id: int, request: Request,
                          cursor: Optional[int] = Query(None), limit: int = Query(60, ge=1, le=200),
                          sort: str = Query("newest", description="newest | oldest | order | name"),
                          db: AsyncSession = Depends(get_db),
                          user: Optional[User] = Depends(current_user_optional)):
    from app.models.album import Album, AlbumPhoto
    from sqlalchemy import func as _f
    if not await db.get(Album, album_id):
        raise HTTPException(404)
    acl = photo_conditions(user)
    sub = select(AlbumPhoto.photo_id).where(AlbumPhoto.album_id == album_id)
    q = select(Photo).where(Photo.id.in_(sub), Photo.is_trashed == False, *acl)  # noqa: E712
    # Sort by CAPTURE DATE by default, not Photo.id (= import order, which mixed old
    # photos imported recently to the top). Offset-cursor so date sorting paginates.
    if sort == "oldest":
        q = q.order_by(Photo.taken_at.asc().nullsfirst(), Photo.id.asc())
    elif sort == "name":
        q = q.order_by(Photo.filename.asc(), Photo.id.asc())
    elif sort == "order":
        q = q.join(AlbumPhoto, AlbumPhoto.photo_id == Photo.id).where(AlbumPhoto.album_id == album_id)\
             .order_by(AlbumPhoto.sort_order, AlbumPhoto.added_at)
    else:  # newest
        q = q.order_by(Photo.taken_at.desc().nullslast(), Photo.id.desc())
    offset = max(0, cursor or 0)
    rows = (await db.execute(q.offset(offset).limit(limit + 1))).scalars().all()
    has_more = len(rows) > limit
    items = rows[:limit]
    total = await db.scalar(select(_f.count()).select_from(
        select(Photo.id).where(Photo.id.in_(sub), Photo.is_trashed == False, *acl).subquery()))  # noqa: E712
    return PhotoPageV1(items=[_to_v1(p, request) for p in items],
                       next_cursor=(offset + limit) if has_more else None,
                       total=total or 0, has_more=has_more)


# ── Map (iOS app) — lightweight geo points ──────────────────────────────────────

class MapPointV1(BaseModel):
    id: int
    latitude: float
    longitude: float
    is_video: bool


@router.get("/map", response_model=List[MapPointV1])
async def map_v1(db: AsyncSession = Depends(get_db),
                 user: Optional[User] = Depends(current_user_optional)):
    """Lightweight geo points (no thumb URL — the map renders dots/clusters, and
    the per-point thumbnail bloated the response to several MB)."""
    acl = photo_conditions(user)
    rows = (await db.execute(
        select(Photo.id, Photo.latitude, Photo.longitude, Photo.is_video).where(
            Photo.latitude.isnot(None), Photo.longitude.isnot(None),
            Photo.is_trashed == False, *acl)  # noqa: E712
    )).all()
    return [MapPointV1(id=r[0], latitude=r[1], longitude=r[2], is_video=r[3]) for r in rows]


class MapClusterV1(BaseModel):
    latitude: float
    longitude: float
    count: int
    photo_id: Optional[int]   # set only when count == 1 (a single photo to open)
    is_video: bool


@router.get("/map/clusters", response_model=List[MapClusterV1])
async def map_clusters_v1(
    min_lat: float = Query(-90), min_lng: float = Query(-180),
    max_lat: float = Query(90), max_lng: float = Query(180),
    grid: int = Query(12, ge=2, le=40, description="cells across the viewport"),
    person_id: Optional[int] = Query(None, description="Filter auf eine Person (Face-Join)"),
    date_from: Optional[str] = Query(None, description="ISO-Datum Anfang (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="ISO-Datum Ende (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
    user: Optional[User] = Depends(current_user_optional),
):
    """Server-side grid clustering for the visible bbox. Buckets photos into a
    grid (≈grid×grid cells) in SQL and returns one centroid+count per cell — so
    the map transfers a few hundred clusters, not 27k points, and resolves as you
    zoom (smaller bbox → finer cells).

    Optionale Filter (Phase 1 Assistent-Intents): person_id, date_from, date_to."""
    from sqlalchemy import func as _f
    from datetime import date as _date
    acl = photo_conditions(user)
    cell_lat = max((max_lat - min_lat) / grid, 1e-6)
    cell_lng = max((max_lng - min_lng) / grid, 1e-6)
    gy = _f.floor(Photo.latitude / cell_lat)
    gx = _f.floor(Photo.longitude / cell_lng)
    extra = []
    if person_id:
        from app.models.face import Face
        extra.append(Photo.id.in_(select(Face.photo_id).where(Face.person_id == person_id)))
    if date_from:
        try: extra.append(Photo.taken_at >= _date.fromisoformat(date_from))
        except ValueError: pass
    if date_to:
        try: extra.append(Photo.taken_at <= _date.fromisoformat(date_to))
        except ValueError: pass
    rows = (await db.execute(
        select(_f.count(), _f.avg(Photo.latitude), _f.avg(Photo.longitude),
               _f.min(Photo.id), _f.bool_or(Photo.is_video))
        .where(Photo.latitude.isnot(None), Photo.longitude.isnot(None),
               Photo.latitude >= min_lat, Photo.latitude <= max_lat,
               Photo.longitude >= min_lng, Photo.longitude <= max_lng,
               Photo.is_trashed == False, *acl, *extra)  # noqa: E712
        .group_by(gy, gx)
    )).all()
    return [MapClusterV1(count=r[0], latitude=float(r[1]), longitude=float(r[2]),
                         photo_id=(r[3] if r[0] == 1 else None), is_video=bool(r[4]))
            for r in rows]


@router.get("/map/photos", response_model=PhotoPageV1)
async def map_photos_v1(
    request: Request,
    min_lat: float = Query(...), min_lng: float = Query(...),
    max_lat: float = Query(...), max_lng: float = Query(...),
    limit: int = Query(300, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    user: Optional[User] = Depends(current_user_optional),
):
    """All geo-tagged photos inside a bbox — for the map's cluster drilldown
    (tap a small cluster → see its photos), newest first."""
    acl = photo_conditions(user)
    rows = (await db.execute(
        select(Photo).where(
            Photo.latitude >= min_lat, Photo.latitude <= max_lat,
            Photo.longitude >= min_lng, Photo.longitude <= max_lng,
            Photo.is_trashed == False, Photo.thumb_small.isnot(None), *acl)  # noqa: E712
        .order_by(Photo.taken_at.desc().nullslast(), Photo.id.desc()).limit(limit)
    )).scalars().all()
    return PhotoPageV1(items=[_to_v1(p, request) for p in rows],
                       next_cursor=None, total=len(rows), has_more=False)


class PhotoFaceV1(BaseModel):
    face_id: int
    person_id: int
    person_name: str


@router.get("/photos/{photo_id}/faces", response_model=List[PhotoFaceV1])
async def photo_faces_v1(photo_id: int, db: AsyncSession = Depends(get_db),
                         user: Optional[User] = Depends(current_user_optional)):
    """Recognised, named persons in this photo (with their face id) — so the app
    can offer 'set this as <name>'s profile picture' from the photo detail."""
    if not await user_can_access_photo(db, photo_id, user):
        raise HTTPException(404)
    from app.models.face import Face
    from app.models.person import Person
    rows = (await db.execute(
        select(Face.id, Face.person_id, Person.name)
        .join(Person, Person.id == Face.person_id)
        .where(Face.photo_id == photo_id, Person.name.isnot(None), Person.name != "")  # noqa: E712
    )).all()
    return [PhotoFaceV1(face_id=r[0], person_id=r[1], person_name=r[2]) for r in rows]


# ── Chat (iOS app) — proxies the same Gemini/local assistant the web uses ────────

class ChatRequestV1(BaseModel):
    message: str
    history: List[dict] = []
    provider: Optional[str] = None
    context_ids: List[int] = []   # letztes Suchergebnis → "davon", "daraus" Folgefragen


@router.get("/chat/status")
async def chat_status_v1(db: AsyncSession = Depends(get_db)):
    from app.api.routes.chat import chat_status as _status
    return await _status(db)


@router.post("/chat")
async def chat_v1(body: ChatRequestV1, db: AsyncSession = Depends(get_db),
                  user: Optional[User] = Depends(current_user_optional)):
    """Returns {answer, photo_ids}. The app then loads each photo via /v1/photos/{id}.
    Chat search/count is now scoped per user (photo_conditions in chat.py), so a
    restricted account safely chats over only its own photos; write-actions stay off."""
    from app.services import chat as chat_svc
    from app.services.settings_loader import load_settings
    from app.core.access import _is_unrestricted
    import logging as _lg
    s = await load_settings(db)
    hist = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in body.history]
    ctx = [int(i) for i in (body.context_ids or [])][:2000]
    res = await chat_svc.chat(body.message, hist, s, db, provider=body.provider, user=user,
                              context_ids=ctx or None)
    # DIAGNOSE (temporär): wer fragt, was, wie viele Treffer — um Client/Account/Scope-
    # Probleme im Chat sichtbar zu machen (Screenshots zeigten 0 Treffer trotz Daten).
    try:
        _lg.getLogger("uvicorn.error").info(
            "CHATDIAG user=%s(id=%s) unrestricted=%s msg=%r -> photos=%d",
            getattr(user, "email", None), getattr(user, "id", None),
            _is_unrestricted(user), (body.message or "")[:80],
            len((res or {}).get("photo_ids") or []))
    except Exception:
        pass
    return res


# ── Trips / events (iOS app) ────────────────────────────────────────────────────

class TripEventV1(BaseModel):
    count: int
    date_from: str
    date_to: str
    days: int
    city: Optional[str]
    is_trip: bool
    cover_photo_id: Optional[int]
    cover_url: Optional[str]


class TripsV1(BaseModel):
    home_city: Optional[str]
    events: List[TripEventV1]


@router.get("/trips", response_model=TripsV1)
async def trips_v1(request: Request, db: AsyncSession = Depends(get_db),
                   user: Optional[User] = Depends(current_user_optional),
                   trips_only: bool = Query(False, description="only events away from home city"),
                   min_photos: Optional[int] = Query(None, ge=1, description="override trips.min_photos live")):
    """Auto-detected events with cover thumbs. The detail loads each event's
    photos via /v1/photos?date_from=&date_to=. trips_only hides everyday clusters;
    min_photos overrides the server threshold so the app can tune it live."""
    from app.api.routes.photos import trips as _trips
    res = await _trips(db=db, user=user, min_photos=min_photos)
    events = res.get("events", [])
    if trips_only:
        events = [e for e in events if e.get("is_trip")]
    out = []
    for e in events:
        cid = e.get("cover_photo_id")
        out.append(TripEventV1(
            count=e["count"], date_from=e["date_from"], date_to=e["date_to"], days=e["days"],
            city=e.get("city"), is_trip=e.get("is_trip", False), cover_photo_id=cid,
            cover_url=(f"/api/photos/{cid}/thumbnail?size=medium" if cid else None),
        ))
    return TripsV1(home_city=res.get("home_city"), events=out)


# ── Library stats (iOS app) ─────────────────────────────────────────────────────

class LibraryStatsV1(BaseModel):
    total: int
    images: int
    videos: int
    processing: int
    described: int
    with_faces: int
    favorites: int
    with_gps: int
    date_min: Optional[str]
    date_max: Optional[str]


@router.get("/stats", response_model=LibraryStatsV1)
async def stats_v1(db: AsyncSession = Depends(get_db),
                   user: Optional[User] = Depends(current_user_optional)):
    """Library totals for the app's overview: images vs videos, processing,
    AI/faces coverage, date span — the 'what did the scan find' summary."""
    from app.api.routes.photos import get_stats
    s = await get_stats(db=db, user=user)
    by = s.get("by_status", {})
    processing = int(by.get("processing", 0)) + int(by.get("pending", 0))
    total_idx = int(s["total_indexed"]); videos = int(s["videos"])
    return LibraryStatsV1(
        total=total_idx, videos=videos, images=max(0, total_idx - videos),
        processing=processing, described=int(s["coverage"]["described"]),
        with_faces=int(s["coverage"]["with_faces"]),
        favorites=int(s["favorites"]), with_gps=int(s["with_gps"]),
        date_min=s["date_min"], date_max=s["date_max"],
    )


# ── Leitstand / Ops-Status (iOS app, admin-only) ────────────────────────────────

@router.get("/ops")
async def ops_status_v1(db: AsyncSession = Depends(get_db),
                        user: Optional[User] = Depends(current_user_optional)):
    """Betriebs-/Leitstand-Status für die iOS-App: Queue-Tiefen, Worker-Liveness,
    globaler Backlog, grobe Restzeit — NUR für Administratoren (system-weite Daten)."""
    from app.core.access import _is_unrestricted
    if not _is_unrestricted(user):
        raise HTTPException(403, "Nur für Administratoren.")
    from app.services.chat import _ops_status
    return await _ops_status(db)


# ── Erinnerungen / Memories (iOS app) ───────────────────────────────────────────

class MemoryGroupV1(BaseModel):
    years_ago: int
    date: str
    items: List[PhotoV1]


@router.get("/memories", response_model=List[MemoryGroupV1])
async def memories_v1(request: Request, db: AsyncSession = Depends(get_db),
                      user: Optional[User] = Depends(current_user_optional)):
    """'Vor X Jahren heute' — same logic the web uses, as PhotoV1 groups."""
    from app.api.routes.photos import get_memories
    groups = await get_memories(db=db, user=user)
    return [MemoryGroupV1(years_ago=g["years_ago"], date=g["date"],
                          items=[_to_v1(p, request) for p in g["photos"]])
            for g in groups]


# ── Dashboard / Startseite (web + iOS) ──────────────────────────────────────────

import time as _time
_DASH_CACHE: dict = {}     # user_id → (expiry_ts, payload) — Kurz-Cache gegen ~10s-Ladezeit
_DASH_TTL = 90             # 90s: kurz genug, dass frisch getrashte/hochgeladene Fotos schnell
                           # verschwinden/erscheinen; lang genug, dass Wiederholaufrufe instant sind.
_DASH_CACHE_MAX = 256      # harte Obergrenze gegen unbegrenztes Wachstum (Memory-Leak)


async def _lean_stats_v1(db: AsyncSession, user: Optional[User]) -> LibraryStatsV1:
    """Startseiten-Stats in 2 Queries statt ~13. get_stats() scannte 140k Fotos/Gesichter
    ~13× einzeln (~4s) — der größte Brocken der Dashboard-Ladezeit. Hier alle Kennzahlen
    per Conditional-Aggregation (FILTER) in EINEM Scan + eine Gesichts-Query. Gleiche ACL."""
    from sqlalchemy import func as _f
    from app.models.face import Face
    acl = photo_conditions(user)
    D = PhotoStatus.done
    row = (await db.execute(select(
        _f.count().filter(Photo.status == D).label("total"),
        _f.count().filter(Photo.is_video == True, Photo.status == D).label("videos"),          # noqa: E712
        _f.count().filter(Photo.latitude.isnot(None)).label("with_gps"),
        _f.count().filter(Photo.description.isnot(None), Photo.description != "").label("described"),
        _f.count().filter(Photo.is_favorite == True).label("favorites"),                        # noqa: E712
        _f.count().filter(Photo.status.notin_([D, PhotoStatus.error])).label("processing"),
        _f.min(Photo.taken_at).label("dmin"), _f.max(Photo.taken_at).label("dmax"),
    ).where(Photo.is_trashed == False, *acl))).one()                                            # noqa: E712
    wf_q = select(_f.count(_f.distinct(Face.photo_id))).select_from(Face)
    if acl:
        wf_q = wf_q.join(Photo, Photo.id == Face.photo_id).where(*acl)
    with_faces = int(await db.scalar(wf_q) or 0)
    total, videos = int(row.total or 0), int(row.videos or 0)
    return LibraryStatsV1(
        total=total, videos=videos, images=max(0, total - videos),
        processing=int(row.processing or 0), described=int(row.described or 0),
        with_faces=with_faces, favorites=int(row.favorites or 0), with_gps=int(row.with_gps or 0),
        date_min=row.dmin.isoformat() if row.dmin else None,
        date_max=row.dmax.isoformat() if row.dmax else None,
    )


@router.get("/dashboard")
async def dashboard_v1(request: Request, db: AsyncSession = Depends(get_db),
                       user: Optional[User] = Depends(current_user_optional)):
    """Everything the home screen needs in ONE call: library stats, 'on this day'
    memories, a rotating Person of the Week (+ sample photos), featured people &
    albums, the newest additions, and a few random highlights."""
    import datetime
    from sqlalchemy import func as _f, or_
    from app.models.person import Person
    from app.models.face import Face
    from app.models.album import Album, AlbumPhoto
    acl = photo_conditions(user)

    # Kurz-Cache: die Startseite ist teuer zu bauen (~mehrere Sekunden) — Wiederhol-
    # aufrufe innerhalb des TTL kommen sofort (behebt den langsamen ersten Eindruck
    # nach dem ersten Laden). Pro Nutzer getrennt (ACL).
    _ckey = user.id if user else 0
    _now = _time.time()
    _hit = _DASH_CACHE.get(_ckey)
    if _hit and _hit[0] > _now:
        return _hit[1]

    out: dict = {}

    # 1) stats — schlanke Variante (2 Queries statt ~13 → ~4s gespart)
    try:
        out["stats"] = (await _lean_stats_v1(db, user)).model_dump()
    except Exception:
        out["stats"] = None

    # 2) on this day — MUST respect the user's folder/person/date restrictions:
    # a restricted user must never see memories from folders they can't access.
    try:
        from app.api.routes.photos import get_memories
        groups = await get_memories(db=db, user=user)
        od = []
        for g in groups:
            vis = [p for p in g["photos"] if can_see_photo(p, user)][:12]
            if vis:
                od.append({"years_ago": g["years_ago"], "date": g["date"],
                           "items": [_to_v1(p, request).model_dump() for p in vis]})
        out["on_this_day"] = od
    except Exception:
        out["on_this_day"] = []

    # named, visible people + their face counts. A restricted account must only see
    # persons that appear in photos it may access (else the home screen leaks the
    # whole library's people — names, faces and counts) — see visible_person_subquery.
    from app.core.access import visible_person_subquery
    pq = select(Person).where(
        Person.is_hidden == False, _f.length(_f.coalesce(Person.name, "")) > 0)  # noqa: E712
    vps = visible_person_subquery(user)
    if vps is not None:
        pq = pq.where(Person.id.in_(vps))
    ppl = (await db.execute(pq)).scalars().all()
    # Counts are scoped to accessible photos too, so a restricted user never even
    # learns how many photos a person has library-wide.
    cq = select(Face.person_id, _f.count()).where(Face.person_id.isnot(None))
    if acl:
        cq = cq.where(Face.photo_id.in_(select(Photo.id).where(*acl)))
    counts = dict((await db.execute(cq.group_by(Face.person_id))).all())
    named_sorted = sorted(ppl, key=lambda p: -counts.get(p.id, 0))

    def _person_obj(p):
        return {"id": p.id, "name": p.name, "face_count": counts.get(p.id, 0),
                "avatar_url": f"/api/people/{p.id}/avatar"}

    # 3) Person of the Week — rotates by ISO week so it changes weekly
    out["person_of_week"] = None
    pool = [p for p in named_sorted if counts.get(p.id, 0) >= 5] or named_sorted
    if pool:
        wk = datetime.date.today().isocalendar()[1]
        pw = pool[wk % len(pool)]
        sub = select(Face.photo_id).where(Face.person_id == pw.id)
        ph = (await db.execute(select(Photo).where(
            Photo.id.in_(sub), Photo.thumb_small.isnot(None), Photo.is_trashed == False, *acl)  # noqa: E712
            .order_by(Photo.id.desc()).limit(9))).scalars().all()
        out["person_of_week"] = {**_person_obj(pw),
                                 "items": [_to_v1(p, request).model_dump() for p in ph]}

    # 4) featured people — the most-photographed named people (spotlight strip)
    pow_id = out["person_of_week"]["id"] if out["person_of_week"] else None
    out["featured_people"] = [_person_obj(p) for p in named_sorted if p.id != pow_id][:12]

    # 5) featured albums (random, with cover). For a restricted user, count only the
    # photos it may see and SKIP albums it can't see into at all — otherwise album
    # NAMES + library-wide counts leak even when every photo is off-limits.
    albums = (await db.execute(select(Album).order_by(_f.random()).limit(24))).scalars().all()
    fa = []
    for a in albums:
        cnt_q = (select(_f.count()).select_from(AlbumPhoto)
                 .where(AlbumPhoto.album_id == a.id))
        if acl:
            cnt_q = cnt_q.join(Photo, Photo.id == AlbumPhoto.photo_id).where(*acl)
        cnt = await db.scalar(cnt_q)
        # Cover must be a photo the user may actually see (folder/person ACL).
        cover = await db.scalar(
            select(Photo.id).join(AlbumPhoto, AlbumPhoto.photo_id == Photo.id)
            .where(AlbumPhoto.album_id == a.id, Photo.thumb_small.isnot(None),
                   Photo.is_trashed == False, *acl).limit(1))  # noqa: E712
        # Restricted user with no accessible photo in this album → don't reveal it.
        if acl and not cnt and not cover:
            continue
        fa.append({"id": a.id, "name": a.name, "photo_count": int(cnt or 0),
                   "cover_url": (f"/api/photos/{cover}/thumbnail?size=medium" if cover else None)})
        if len(fa) >= 8:
            break
    out["featured_albums"] = fa

    # 6) recent additions
    recent = (await db.execute(select(Photo).where(
        Photo.thumb_small.isnot(None), Photo.is_trashed == False, *acl)  # noqa: E712
        .order_by(Photo.id.desc()).limit(12))).scalars().all()
    out["recent"] = [_to_v1(p, request).model_dump() for p in recent]

    # 7) random highlights (favourites / well-rated, else random)
    hi = (await db.execute(select(Photo).where(
        Photo.thumb_small.isnot(None), Photo.is_trashed == False,
        or_(Photo.is_favorite == True, Photo.user_rating >= 4), *acl)  # noqa: E712
        .order_by(_f.random()).limit(12))).scalars().all()
    if len(hi) < 6:
        hi = (await db.execute(select(Photo).where(
            Photo.thumb_small.isnot(None), Photo.is_trashed == False, *acl)  # noqa: E712
            .order_by(_f.random()).limit(12))).scalars().all()
    out["highlights"] = [_to_v1(p, request).model_dump() for p in hi]

    # 8) latest rendered recap video ("Highlight der Woche" & co.) for the start page.
    # Only for unrestricted users (highlights aren't per-folder scoped); excludes the
    # single-photo photo_animate clips.
    out["weekly_highlight"] = None
    from app.core.access import _is_unrestricted
    if _is_unrestricted(user):  # admin / open mode only (not per-folder scoped)
        from app.models.highlight import Highlight, HighlightStatus
        wh = (await db.execute(select(Highlight).where(
            Highlight.status == HighlightStatus.done, Highlight.file_path.isnot(None),
            Highlight.motto != "photo_animate")
            .order_by(Highlight.created_at.desc()).limit(1))).scalars().first()
        if wh:
            out["weekly_highlight"] = {
                "id": wh.id, "title": wh.title, "motto": wh.motto,
                "duration_sec": wh.duration_sec,
                "video_url": f"/api/highlights/{wh.id}/video",
                "cover_url": (f"/api/photos/{wh.cover_photo_id}/thumbnail?size=large"
                              if wh.cover_photo_id else None),
            }

    if len(_DASH_CACHE) >= _DASH_CACHE_MAX:   # Obergrenze: alte Einträge verwerfen (kein Leak)
        _DASH_CACHE.clear()
    _DASH_CACHE[_ckey] = (_now + _DASH_TTL, out)
    return out
