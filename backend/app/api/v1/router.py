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
from app.core.access import photo_conditions, can_see_photo, feature_allowed
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
    base = str(req.base_url).rstrip("/")
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
    cursor: Optional[int] = Query(None, description="Last photo ID from previous page"),
    limit: int = Query(50, ge=1, le=200),
    favorites: bool = False,
    media_type: Optional[str] = Query(None, description="photo|video"),
    archived: bool = False,
    trashed: bool = False,
    db: AsyncSession = Depends(get_db),
    user: Optional[User] = Depends(current_user_optional),
):
    """Cursor-paginated photo list. Stable under concurrent uploads."""
    acl = photo_conditions(user)
    q = select(Photo).where(
        Photo.status == PhotoStatus.done,
        Photo.is_trashed == trashed,
        Photo.is_archived == archived,
        *acl,
    )
    if favorites:
        q = q.where(Photo.is_favorite == True)
    if media_type == "video":
        q = q.where(Photo.is_video == True)
    elif media_type == "photo":
        q = q.where(Photo.is_video == False)
    if cursor:
        q = q.where(Photo.id < cursor)

    q = q.order_by(Photo.id.desc()).limit(limit + 1)
    rows = (await db.execute(q)).scalars().all()

    has_more = len(rows) > limit
    items = rows[:limit]
    next_cursor = items[-1].id if has_more and items else None

    # Total count (no cursor filter, same access + facets)
    total_q = select(Photo).where(
        Photo.status == PhotoStatus.done, Photo.is_trashed == trashed, Photo.is_archived == archived, *acl,
    )
    if favorites:
        total_q = total_q.where(Photo.is_favorite == True)  # noqa: E712
    if media_type == "video":
        total_q = total_q.where(Photo.is_video == True)  # noqa: E712
    elif media_type == "photo":
        total_q = total_q.where(Photo.is_video == False)  # noqa: E712
    total = await db.scalar(select(__import__("sqlalchemy").func.count()).select_from(total_q.subquery()))

    return PhotoPageV1(
        items=[_to_v1(p, request) for p in items],
        next_cursor=next_cursor,
        total=total or 0,
        has_more=has_more,
    )


# ── Single photo ──────────────────────────────────────────────────────────────

@router.get("/photos/{photo_id}", response_model=PhotoV1)
async def get_photo_v1(photo_id: int, request: Request, db: AsyncSession = Depends(get_db),
                       user: Optional[User] = Depends(current_user_optional)):
    photo = await db.get(Photo, photo_id)
    if not photo or photo.is_trashed or not can_see_photo(photo, user):
        raise HTTPException(404)
    return _to_v1(photo, request)


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
    q = select(Photo).where(Photo.status == PhotoStatus.done, *acl)
    if since_dt:
        q = q.where(Photo.indexed_at >= since_dt)
    q = q.order_by(Photo.indexed_at.desc()).limit(limit)

    changed = (await db.execute(q)).scalars().all()

    # Trashed since (simple: return trashed IDs updated recently)
    trash_q = select(Photo.id).where(Photo.is_trashed == True)
    if since_dt:
        trash_q = trash_q.where(Photo.indexed_at >= since_dt)
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


@router.post("/upload", response_model=List[UploadResult])
async def upload_photos(
    files: List[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Accept photo/video uploads from iOS. Deduplicates by SHA-256 hash."""
    results: List[UploadResult] = []

    for upload in files:
        try:
            content = await upload.read()
            file_hash = hashlib.sha256(content).hexdigest()

            # Check duplicate
            existing = await db.scalar(
                select(Photo.id).where(Photo.file_hash == file_hash)
            )
            if existing:
                results.append(UploadResult(
                    id=existing, filename=upload.filename or "unknown",
                    status="duplicate", duplicate_of=existing,
                ))
                continue

            # Save to upload staging area
            ext = Path(upload.filename or "upload").suffix.lower()
            dest = _UPLOAD_DIR / f"{file_hash}{ext}"
            dest.write_bytes(content)

            # Create Photo record in pending state
            mime = upload.content_type or mimetypes.guess_type(str(dest))[0] or "application/octet-stream"
            is_video = mime.startswith("video/")

            photo = Photo(
                path=str(dest),
                filename=upload.filename or dest.name,
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
    if not photo or not photo.is_video or not can_see_photo(photo, user):
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
async def video_preview_v1(photo_id: int, db: AsyncSession = Depends(get_db)):
    """Return animated WebP hover preview for a video."""
    photo = await db.get(Photo, photo_id)
    if not photo or not photo.is_video:
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
async def video_sprite_v1(photo_id: int, db: AsyncSession = Depends(get_db)):
    """JPEG sprite sheet for video scrubbing (thumbnail track)."""
    photo = await db.get(Photo, photo_id)
    if not photo or not photo.is_video:
        raise HTTPException(404)

    cache_root = os.getenv("CACHE_PATH", "/cache")
    from app.services.processing.thumbnails import generate_video_sprite
    result = generate_video_sprite(photo.path, cache_root)
    if not result:
        raise HTTPException(404, "Sprite not available")
    sprite_path, _ = result
    return FileResponse(sprite_path, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=604800"})


@router.get("/photos/{photo_id}/sprite.vtt")
async def video_sprite_vtt_v1(photo_id: int, db: AsyncSession = Depends(get_db)):
    """WebVTT thumbnail track for timeline scrubbing."""
    photo = await db.get(Photo, photo_id)
    if not photo or not photo.is_video:
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
async def favorite_v1(photo_id: int, db: AsyncSession = Depends(get_db)):
    photo = await db.get(Photo, photo_id)
    if not photo:
        raise HTTPException(404)
    photo.is_favorite = not photo.is_favorite
    await db.commit()
    return {"id": photo_id, "is_favorite": photo.is_favorite}


@router.patch("/photos/{photo_id}/rating")
async def rating_v1(photo_id: int, rating: int = 0, db: AsyncSession = Depends(get_db)):
    photo = await db.get(Photo, photo_id)
    if not photo:
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
    avatar_url: str


@router.get("/people", response_model=List[PersonV1])
async def people_v1(request: Request, include_unnamed: bool = True, db: AsyncSession = Depends(get_db),
                    user: Optional[User] = Depends(current_user_optional)):
    from app.models.person import Person
    from app.models.face import Face
    from sqlalchemy import func as _f
    base = str(request.base_url).rstrip("/")
    pq = select(Person).where(Person.is_hidden == False).order_by(Person.name)  # noqa: E712
    # If the user is restricted to specific people, only list those.
    if user is not None and user.role != UserRole.admin:
        vis = (user.access_config or {}).get("visible_person_ids")
        if vis:
            pq = pq.where(Person.id.in_(vis))
    persons = (await db.execute(pq)).scalars().all()
    counts = dict((await db.execute(
        select(Face.person_id, _f.count()).where(Face.person_id.isnot(None)).group_by(Face.person_id)
    )).all())
    out = []
    for p in persons:
        named = bool((p.name or "").strip())
        if not named and not include_unnamed:
            continue
        out.append(PersonV1(id=p.id, name=p.name or "Unbekannt", face_count=counts.get(p.id, 0),
                            avatar_url=f"{base}/api/people/{p.id}/avatar"))
    return out


@router.get("/people/{person_id}/photos", response_model=PhotoPageV1)
async def person_photos_v1(person_id: int, request: Request,
                           cursor: Optional[int] = Query(None), limit: int = Query(50, ge=1, le=200),
                           db: AsyncSession = Depends(get_db),
                           user: Optional[User] = Depends(current_user_optional)):
    from app.models.face import Face
    from sqlalchemy import func as _f
    acl = photo_conditions(user)
    sub = select(Face.photo_id).where(Face.person_id == person_id)
    q = select(Photo).where(Photo.id.in_(sub), Photo.status == PhotoStatus.done, Photo.is_trashed == False, *acl)  # noqa: E712
    if cursor:
        q = q.where(Photo.id < cursor)
    rows = (await db.execute(q.order_by(Photo.id.desc()).limit(limit + 1))).scalars().all()
    has_more = len(rows) > limit
    items = rows[:limit]
    total = await db.scalar(select(_f.count()).select_from(
        select(Photo).where(Photo.id.in_(sub), Photo.is_trashed == False, *acl).subquery()))  # noqa: E712
    return PhotoPageV1(items=[_to_v1(p, request) for p in items],
                       next_cursor=(items[-1].id if has_more and items else None),
                       total=total or 0, has_more=has_more)


# ── Relationships (iOS app) ───────────────────────────────────────────────────

@router.get("/relationships")
async def relationships_v1(db: AsyncSession = Depends(get_db)):
    from app.api.routes.relationships import graph as _graph
    return await _graph(db)
