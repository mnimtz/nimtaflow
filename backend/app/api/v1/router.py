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
        q = select(Photo).where(
            Photo.status == PhotoStatus.done,
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
            q = q.join(Face, Face.photo_id == Photo.id).where(Face.person_id == person_id)
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
    # Key off updated_at (bumped by a DB trigger on every change) so favorites,
    # ratings, descriptions, trashing etc. all surface in incremental sync —
    # not just newly-imported photos (indexed_at never changes).
    q = select(Photo).where(Photo.status == PhotoStatus.done, Photo.is_trashed == False, *acl)  # noqa: E712
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
    return await _graph(db=db)   # first positional arg is `category`, not db


# ── Albums (iOS app) ──────────────────────────────────────────────────────────

class AlbumV1(BaseModel):
    id: int
    name: str
    description: Optional[str]
    album_type: str
    photo_count: int
    cover_url: Optional[str]


@router.get("/albums", response_model=List[AlbumV1])
async def albums_v1(request: Request, db: AsyncSession = Depends(get_db),
                    user: Optional[User] = Depends(current_user_optional)):
    """Album list with cover thumbnails — same shape the gallery grid understands."""
    from app.models.album import Album, AlbumPhoto
    from sqlalchemy import func as _f
    base = str(request.base_url).rstrip("/")
    albums = (await db.execute(select(Album).order_by(Album.created_at.desc()))).scalars().all()
    counts = dict((await db.execute(
        select(AlbumPhoto.album_id, _f.count()).group_by(AlbumPhoto.album_id)
    )).all())
    # cover = explicit cover_photo_id, else the first photo in the album
    first_photo = dict((await db.execute(
        select(AlbumPhoto.album_id, _f.min(AlbumPhoto.photo_id)).group_by(AlbumPhoto.album_id)
    )).all())
    out = []
    for a in albums:
        cover_id = a.cover_photo_id or first_photo.get(a.id)
        out.append(AlbumV1(
            id=a.id, name=a.name, description=a.description,
            album_type=a.album_type.value if hasattr(a.album_type, "value") else str(a.album_type),
            photo_count=counts.get(a.id, 0),
            cover_url=(f"{base}/api/photos/{cover_id}/thumbnail?size=medium" if cover_id else None),
        ))
    return out


@router.get("/albums/{album_id}/photos", response_model=PhotoPageV1)
async def album_photos_v1(album_id: int, request: Request,
                          cursor: Optional[int] = Query(None), limit: int = Query(60, ge=1, le=200),
                          db: AsyncSession = Depends(get_db),
                          user: Optional[User] = Depends(current_user_optional)):
    from app.models.album import Album, AlbumPhoto
    from sqlalchemy import func as _f
    if not await db.get(Album, album_id):
        raise HTTPException(404)
    acl = photo_conditions(user)
    sub = select(AlbumPhoto.photo_id).where(AlbumPhoto.album_id == album_id)
    q = select(Photo).where(Photo.id.in_(sub), Photo.is_trashed == False, *acl)  # noqa: E712
    if cursor:
        q = q.where(Photo.id < cursor)
    rows = (await db.execute(q.order_by(Photo.id.desc()).limit(limit + 1))).scalars().all()
    has_more = len(rows) > limit
    items = rows[:limit]
    total = await db.scalar(select(_f.count()).select_from(
        select(Photo.id).where(Photo.id.in_(sub), Photo.is_trashed == False, *acl).subquery()))  # noqa: E712
    return PhotoPageV1(items=[_to_v1(p, request) for p in items],
                       next_cursor=(items[-1].id if has_more and items else None),
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
    db: AsyncSession = Depends(get_db),
    user: Optional[User] = Depends(current_user_optional),
):
    """Server-side grid clustering for the visible bbox. Buckets photos into a
    grid (≈grid×grid cells) in SQL and returns one centroid+count per cell — so
    the map transfers a few hundred clusters, not 27k points, and resolves as you
    zoom (smaller bbox → finer cells)."""
    from sqlalchemy import func as _f
    acl = photo_conditions(user)
    cell_lat = max((max_lat - min_lat) / grid, 1e-6)
    cell_lng = max((max_lng - min_lng) / grid, 1e-6)
    gy = _f.floor(Photo.latitude / cell_lat)
    gx = _f.floor(Photo.longitude / cell_lng)
    rows = (await db.execute(
        select(_f.count(), _f.avg(Photo.latitude), _f.avg(Photo.longitude),
               _f.min(Photo.id), _f.bool_or(Photo.is_video))
        .where(Photo.latitude.isnot(None), Photo.longitude.isnot(None),
               Photo.latitude >= min_lat, Photo.latitude <= max_lat,
               Photo.longitude >= min_lng, Photo.longitude <= max_lng,
               Photo.is_trashed == False, *acl)  # noqa: E712
        .group_by(gy, gx)
    )).all()
    return [MapClusterV1(count=r[0], latitude=float(r[1]), longitude=float(r[2]),
                         photo_id=(r[3] if r[0] == 1 else None), is_video=bool(r[4]))
            for r in rows]


# ── Chat (iOS app) — proxies the same Gemini/local assistant the web uses ────────

class ChatRequestV1(BaseModel):
    message: str
    history: List[dict] = []
    provider: Optional[str] = None


@router.get("/chat/status")
async def chat_status_v1(db: AsyncSession = Depends(get_db)):
    from app.api.routes.chat import chat_status as _status
    return await _status(db)


@router.post("/chat")
async def chat_v1(body: ChatRequestV1, db: AsyncSession = Depends(get_db)):
    """Returns {answer, photo_ids}. The app then loads each photo via /v1/photos/{id}."""
    from app.services import chat as chat_svc
    from app.services.settings_loader import load_settings
    s = await load_settings(db)
    hist = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in body.history]
    return await chat_svc.chat(body.message, hist, s, db, provider=body.provider)


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
    base = str(request.base_url).rstrip("/")
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
            cover_url=(f"{base}/api/photos/{cid}/thumbnail?size=medium" if cid else None),
        ))
    return TripsV1(home_city=res.get("home_city"), events=out)


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
    groups = await get_memories(db=db)
    return [MemoryGroupV1(years_ago=g["years_ago"], date=g["date"],
                          items=[_to_v1(p, request) for p in g["photos"]])
            for g in groups]
