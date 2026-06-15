from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, distinct, extract, text
from datetime import date
import os, subprocess, pathlib, mimetypes

from app.core.database import get_db
from app.models.photo import Photo, PhotoStatus
from app.schemas.photo import PhotoListResponse, PhotoDetail, TimelineGroup

router = APIRouter(prefix="/photos", tags=["photos"])

VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".webm", ".mts", ".3gp"}


def _base_query(
    db: AsyncSession,
    search: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    person_id: Optional[int] = None,
    tag: Optional[str] = None,
    camera: Optional[str] = None,
    media_type: Optional[str] = None,  # photo | video | raw
    favorites_only: bool = False,
    has_gps: Optional[bool] = None,
    view: str = "library",  # library | favorites | archive | trash
):
    q = select(Photo).where(Photo.status == PhotoStatus.done, Photo.is_missing == False)
    if view == "trash":
        q = q.where(Photo.is_trashed == True)
    elif view == "archive":
        q = q.where(Photo.is_archived == True, Photo.is_trashed == False)
    elif view == "favorites":
        q = q.where(Photo.is_favorite == True, Photo.is_trashed == False, Photo.is_archived == False)
    else:  # library
        q = q.where(Photo.is_trashed == False, Photo.is_archived == False)
    if search:
        q = q.where(Photo.description.ilike(f"%{search}%"))
    if date_from:
        q = q.where(Photo.taken_at >= date_from)
    if date_to:
        q = q.where(Photo.taken_at <= date_to)
    if camera:
        q = q.where(Photo.camera_model.ilike(f"%{camera}%"))
    if favorites_only:
        q = q.where(Photo.is_favorite == True)
    if has_gps is True:
        q = q.where(Photo.latitude != None)
    elif has_gps is False:
        q = q.where(Photo.latitude == None)
    if media_type == "video":
        q = q.where(Photo.is_video == True)
    elif media_type == "photo":
        q = q.where(Photo.is_video == False, Photo.mime_type.not_like("image/raw%"))
    elif media_type == "raw":
        q = q.where(Photo.mime_type.like("image/raw%"))
    if person_id:
        from app.models.face import Face
        q = q.join(Face, Face.photo_id == Photo.id).where(Face.person_id == person_id)
    if tag:
        from app.models.tag import Tag, PhotoTag
        q = q.join(PhotoTag, PhotoTag.photo_id == Photo.id).join(Tag, Tag.id == PhotoTag.tag_id).where(Tag.name == tag)
    return q


@router.get("", response_model=PhotoListResponse)
async def list_photos(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
    search: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    person_id: Optional[int] = None,
    tag: Optional[str] = None,
    camera: Optional[str] = None,
    media_type: Optional[str] = None,
    favorites: bool = False,
    has_gps: Optional[bool] = None,
    view: str = "library",
    sort: str = "newest",  # newest | oldest | added | name
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    radius_km: Optional[float] = None,
    db: AsyncSession = Depends(get_db),
):
    q = _base_query(db, search, date_from, date_to, person_id, tag, camera, media_type, favorites, has_gps, view)

    if lat and lng and radius_km:
        lat_delta = radius_km / 111.0
        lng_delta = radius_km / (111.0 * max(abs(lat), 0.01))
        q = q.where(
            and_(
                Photo.latitude.between(lat - lat_delta, lat + lat_delta),
                Photo.longitude.between(lng - lng_delta, lng + lng_delta),
            )
        )

    total = await db.scalar(select(func.count()).select_from(q.subquery()))
    if sort == "oldest":
        q = q.order_by(Photo.taken_at.asc().nullsfirst(), Photo.id.asc())
    elif sort == "added":
        q = q.order_by(Photo.indexed_at.desc().nullslast(), Photo.id.desc())
    elif sort == "name":
        q = q.order_by(Photo.filename.asc())
    else:  # newest (default)
        q = q.order_by(Photo.taken_at.desc().nullslast(), Photo.id.desc())
    q = q.offset((page - 1) * limit).limit(limit)
    photos = (await db.execute(q)).scalars().all()
    return PhotoListResponse(total=total or 0, page=page, limit=limit, items=photos)


@router.get("/search/semantic", response_model=PhotoListResponse)
async def semantic_search(q: str, limit: int = Query(60, ge=1, le=200), db: AsyncSession = Depends(get_db)):
    """Natural-language semantic search over photo embeddings (pgvector cosine).
    Embeds the query with the configured embedding provider and returns the
    closest photos. Requires photos to have embeddings (AI processing done)."""
    if not q.strip():
        return PhotoListResponse(total=0, page=1, limit=limit, items=[])
    from app.services.settings_loader import load_settings
    from app.services.ai.manager import AIManager
    s = await load_settings(db)
    ai = AIManager(s)
    vec, provider = await ai.embed_text(q.strip())
    if not vec:
        raise HTTPException(400, "Kein Embedding-Provider aktiv/erreichbar. In Foto-AI konfigurieren.")
    # match the stored 768-dim space (some providers return more → truncate+renormalize)
    if len(vec) > 768:
        import math
        vec = vec[:768]
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        vec = [x / norm for x in vec]
    if len(vec) != 768:
        raise HTTPException(400, f"Embedding-Dimension {len(vec)} passt nicht zur DB (768).")
    # Hybrid: keyword match (description/keywords) OR a strict semantic distance.
    # Pure semantic over a tiny library returns everything; requiring a term hit
    # (or a very close vector) makes results exact-ish. Slider tunes the vector part.
    import re as _re
    max_dist = float(s.get("search.max_distance", "0.78") or 0.78)
    tokens = [t for t in _re.findall(r"[\wäöüÄÖÜß]{3,}", q.lower())
              if t not in {"der", "die", "das", "ein", "eine", "mit", "und", "beim", "der", "den", "von", "auf", "im", "in"}]
    dist = Photo.embedding.cosine_distance(vec)
    base = [Photo.status == PhotoStatus.done, Photo.is_missing == False,
            Photo.is_trashed == False, Photo.embedding.isnot(None)]
    photos = []
    if tokens:
        # Keep only tokens that actually occur somewhere (so a synonym we don't
        # have, e.g. "Junge" when the caption says "Kind", doesn't kill the query).
        present = []
        for t in tokens:
            hit = await db.scalar(select(Photo.id).where(
                or_(Photo.description.ilike(f"%{t}%"), Photo.keywords.ilike(f"%{t}%"))).limit(1))
            if hit:
                present.append(t)
        if present:
            # ALL present tokens must match (AND) → exact-ish results
            and_conds = [or_(Photo.description.ilike(f"%{t}%"), Photo.keywords.ilike(f"%{t}%")) for t in present]
            qy = select(Photo).where(*base, *and_conds).order_by(dist).limit(limit)
            photos = (await db.execute(qy)).scalars().all()
    if not photos:
        # fallback: closest semantic matches within the distance threshold
        qy = select(Photo).where(*base, dist < max_dist).order_by(dist).limit(limit)
        photos = (await db.execute(qy)).scalars().all()
    return PhotoListResponse(total=len(photos), page=1, limit=limit, items=photos)


@router.get("/timeline", response_model=List[TimelineGroup])
async def get_timeline(
    search: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    person_id: Optional[int] = None,
    camera: Optional[str] = None,
    media_type: Optional[str] = None,
    favorites: bool = False,
    limit_per_group: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Returns photos grouped by day, newest first, for timeline view."""
    q = _base_query(db, search, date_from, date_to, person_id, None, camera, media_type, favorites)
    q = q.order_by(Photo.taken_at.desc().nullslast(), Photo.id.desc())
    all_photos = (await db.execute(q)).scalars().all()

    from collections import defaultdict
    groups: dict = defaultdict(list)
    for photo in all_photos:
        key = photo.taken_at.date().isoformat() if photo.taken_at else "unknown"
        groups[key].append(photo)

    result = []
    for day_key in sorted(groups.keys(), reverse=True):
        photos_in_group = groups[day_key]
        result.append(TimelineGroup(
            date=day_key,
            count=len(photos_in_group),
            photos=photos_in_group[:limit_per_group],
        ))
    return result


@router.get("/stats")
async def get_stats(db: AsyncSession = Depends(get_db)):
    """Filter facets: cameras, date range, counts."""
    cameras = (await db.execute(
        select(Photo.camera_model, func.count().label("n"))
        .where(Photo.camera_model != None, Photo.is_trashed == False)
        .group_by(Photo.camera_model).order_by(text("n desc")).limit(20)
    )).all()

    total = await db.scalar(select(func.count()).where(Photo.is_trashed == False, Photo.status == PhotoStatus.done))
    videos = await db.scalar(select(func.count()).where(Photo.is_video == True, Photo.is_trashed == False))
    favorites = await db.scalar(select(func.count()).where(Photo.is_favorite == True, Photo.is_trashed == False))
    with_gps = await db.scalar(select(func.count()).where(Photo.latitude != None, Photo.is_trashed == False))

    min_date = await db.scalar(select(func.min(Photo.taken_at)).where(Photo.is_trashed == False))
    max_date = await db.scalar(select(func.max(Photo.taken_at)).where(Photo.is_trashed == False))

    status_rows = (await db.execute(
        select(Photo.status, func.count()).group_by(Photo.status)
    )).all()
    by_status = {str(getattr(r[0], "value", r[0])): r[1] for r in status_rows}

    return {
        "total": total or 0,
        "videos": videos or 0,
        "favorites": favorites or 0,
        "with_gps": with_gps or 0,
        "cameras": [{"model": r[0], "count": r[1]} for r in cameras],
        "date_min": min_date.isoformat() if min_date else None,
        "date_max": max_date.isoformat() if max_date else None,
        "by_status": by_status,
    }


@router.get("/memories")
async def get_memories(db: AsyncSession = Depends(get_db)):
    """Photos from exactly 1, 2, 3... years ago today."""
    from datetime import datetime, timezone, timedelta
    today = datetime.now(timezone.utc)
    memories = []
    for years_ago in range(1, 11):
        target = today.replace(year=today.year - years_ago)
        start = target - timedelta(days=1)
        end = target + timedelta(days=1)
        photos = (await db.execute(
            select(Photo)
            .where(Photo.taken_at.between(start, end), Photo.is_trashed == False, Photo.status == PhotoStatus.done)
            .order_by(Photo.taken_at)
            .limit(20)
        )).scalars().all()
        if photos:
            memories.append({"years_ago": years_ago, "date": target.date().isoformat(), "photos": photos})
    return memories


@router.get("/{photo_id}")
async def get_photo(photo_id: int, db: AsyncSession = Depends(get_db)):
    photo = await db.get(Photo, photo_id)
    if not photo:
        raise HTTPException(404, "Photo not found")

    from sqlalchemy import inspect as sa_inspect
    from app.models.tag import Tag, PhotoTag
    from app.models.face import Face
    from app.models.person import Person

    # all scalar columns (except the heavy embedding vector)
    data = {c.key: getattr(photo, c.key) for c in sa_inspect(photo).mapper.column_attrs}
    data.pop("embedding", None)

    tag_rows = await db.execute(
        select(Tag.name).join(PhotoTag, PhotoTag.tag_id == Tag.id).where(PhotoTag.photo_id == photo_id)
    )
    data["tags"] = [t for t in tag_rows.scalars()]

    face_rows = (await db.execute(
        select(Face.id, Face.bbox_x, Face.bbox_y, Face.bbox_w, Face.bbox_h,
               Face.confidence, Person.id, Person.name)
        .join(Person, Person.id == Face.person_id, isouter=True)
        .where(Face.photo_id == photo_id)
    )).all()
    data["people"] = [
        {"face_id": r[0], "bbox": [r[1], r[2], r[3], r[4]], "confidence": r[5],
         "person_id": r[6], "name": r[7]}
        for r in face_rows
    ]
    return data


@router.patch("/{photo_id}/favorite")
async def toggle_favorite(photo_id: int, db: AsyncSession = Depends(get_db)):
    photo = await db.get(Photo, photo_id)
    if not photo:
        raise HTTPException(404)
    photo.is_favorite = not photo.is_favorite
    await db.commit()
    return {"is_favorite": photo.is_favorite}


@router.patch("/{photo_id}/archive")
async def toggle_archive(photo_id: int, db: AsyncSession = Depends(get_db)):
    photo = await db.get(Photo, photo_id)
    if not photo:
        raise HTTPException(404)
    photo.is_archived = not photo.is_archived
    await db.commit()
    return {"is_archived": photo.is_archived}


@router.patch("/{photo_id}/rating")
async def set_rating(photo_id: int, rating: int = 0, db: AsyncSession = Depends(get_db)):
    photo = await db.get(Photo, photo_id)
    if not photo:
        raise HTTPException(404)
    photo.user_rating = max(0, min(5, rating))
    await db.commit()
    return {"user_rating": photo.user_rating}


@router.patch("/{photo_id}/trash")
async def toggle_trash(photo_id: int, db: AsyncSession = Depends(get_db)):
    photo = await db.get(Photo, photo_id)
    if not photo:
        raise HTTPException(404)
    photo.is_trashed = not photo.is_trashed
    await db.commit()
    return {"is_trashed": photo.is_trashed}


# ── Bulk actions ──────────────────────────────────────────────────────────────

from pydantic import BaseModel as _BM
from typing import List as _List


class BatchAction(_BM):
    ids: _List[int]
    action: str  # favorite | unfavorite | archive | unarchive | trash | untrash


@router.post("/reprocess-failed")
async def reprocess_failed(db: AsyncSession = Depends(get_db)):
    """Re-queue all photos that errored or never finished (error/pending/processing)."""
    from app.worker.tasks import process_photo_task
    rows = (await db.execute(
        select(Photo.id).where(Photo.status.in_([PhotoStatus.error, PhotoStatus.pending, PhotoStatus.processing]))
    )).all()
    ids = [r[0] for r in rows]
    for pid in ids:
        process_photo_task.delay(pid)
    return {"reprocessing": len(ids)}


@router.post("/batch")
async def batch_action(body: BatchAction, db: AsyncSession = Depends(get_db)):
    """Apply an action to many photos at once (selection bar in the gallery)."""
    field_value = {
        "favorite": ("is_favorite", True),
        "unfavorite": ("is_favorite", False),
        "archive": ("is_archived", True),
        "unarchive": ("is_archived", False),
        "trash": ("is_trashed", True),
        "untrash": ("is_trashed", False),
    }.get(body.action)
    if not field_value:
        raise HTTPException(400, f"Unknown action: {body.action}")
    field, value = field_value
    result = await db.execute(select(Photo).where(Photo.id.in_(body.ids)))
    photos = result.scalars().all()
    for p in photos:
        setattr(p, field, value)
    await db.commit()
    return {"updated": len(photos), "action": body.action}


# ── EXIF / metadata editing ───────────────────────────────────────────────────

class MetaUpdate(_BM):
    title: Optional[str] = None
    caption: Optional[str] = None
    user_description: Optional[str] = None
    description: Optional[str] = None      # AI description, can be corrected manually
    keywords: Optional[str] = None         # comma-separated
    artist: Optional[str] = None
    copyright: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    altitude: Optional[float] = None
    taken_at: Optional[str] = None         # ISO-8601
    write_to_file: bool = False            # also write to original via exiftool
    write_xmp_sidecar: bool = False        # write .xmp sidecar


@router.patch("/{photo_id}/meta")
async def update_meta(photo_id: int, body: MetaUpdate, db: AsyncSession = Depends(get_db)):
    """Edit metadata in DB and optionally write to file / XMP sidecar."""
    photo = await db.get(Photo, photo_id)
    if not photo:
        raise HTTPException(404)

    # Update DB fields
    for field in ("title", "caption", "user_description", "description",
                  "keywords", "artist", "copyright", "latitude", "longitude", "altitude"):
        val = getattr(body, field, None)
        if val is not None:
            setattr(photo, field, val)

    if body.taken_at:
        from datetime import datetime as dt
        try:
            photo.taken_at = dt.fromisoformat(body.taken_at.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(400, "Invalid taken_at format, use ISO-8601")

    errors = []

    # Write to original file via exiftool
    if body.write_to_file:
        from app.services.exif_edit import write_exif, exiftool_available
        if exiftool_available():
            tags = {}
            if body.title: tags["XMP:Title"] = body.title
            if body.caption: tags["IPTC:Caption-Abstract"] = body.caption
            if body.description: tags["XMP:Description"] = body.description
            if body.artist: tags["EXIF:Artist"] = body.artist
            if body.copyright: tags["EXIF:Copyright"] = body.copyright
            if body.keywords: tags["XMP:Subject"] = body.keywords
            if body.latitude is not None and body.longitude is not None:
                from app.services.exif_edit import write_gps
                try:
                    await write_gps(photo.path, body.latitude, body.longitude, body.altitude)
                except Exception as e:
                    errors.append(f"GPS write: {e}")
            if tags:
                try:
                    from app.services.exif_edit import write_exif
                    await write_exif(photo.path, tags, make_backup=False)
                except Exception as e:
                    errors.append(f"exiftool: {e}")
        else:
            errors.append("exiftool not installed — file not modified")

    # Write XMP sidecar
    if body.write_xmp_sidecar:
        try:
            from app.services.xmp_sidecar import write_sidecar
            kw_list = [k.strip() for k in (body.keywords or photo.keywords or "").split(",") if k.strip()]
            sidecar_path = write_sidecar(
                photo.path,
                description=photo.description,
                user_description=photo.user_description,
                rating=photo.user_rating,
                keywords=kw_list or None,
                title=photo.title,
                artist=photo.artist,
                caption=photo.caption,
                latitude=photo.latitude,
                longitude=photo.longitude,
                city=photo.city,
                country=photo.country,
            )
            photo.xmp_sidecar_written = True
            photo.xmp_sidecar_path = sidecar_path
        except Exception as e:
            errors.append(f"XMP sidecar: {e}")

    await db.commit()
    return {"ok": True, "errors": errors}


@router.get("/{photo_id}/thumbnail")
async def get_thumbnail(photo_id: int, size: str = "medium", db: AsyncSession = Depends(get_db)):
    photo = await db.get(Photo, photo_id)
    if not photo:
        raise HTTPException(404)
    thumb = getattr(photo, f"thumb_{size}", None) or photo.thumb_medium or photo.thumb_small
    if not thumb or not os.path.exists(thumb):
        raise HTTPException(404, "Thumbnail not ready")
    return FileResponse(thumb, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=31536000"})


@router.get("/{photo_id}/preview")
async def get_video_preview(photo_id: int, db: AsyncSession = Depends(get_db)):
    """Animated hover preview clip for a video (webp/gif)."""
    photo = await db.get(Photo, photo_id)
    if not photo or not photo.video_preview_path or not os.path.exists(photo.video_preview_path):
        raise HTTPException(404, "Preview not ready")
    ext = os.path.splitext(photo.video_preview_path)[1].lower()
    media = "image/gif" if ext == ".gif" else "image/webp"
    return FileResponse(photo.video_preview_path, media_type=media,
                        headers={"Cache-Control": "public, max-age=31536000"})


@router.get("/{photo_id}/original")
async def get_original(photo_id: int, db: AsyncSession = Depends(get_db)):
    photo = await db.get(Photo, photo_id)
    if not photo:
        raise HTTPException(404)
    mime = photo.mime_type or mimetypes.guess_type(photo.path)[0] or "application/octet-stream"
    return FileResponse(photo.path, media_type=mime, filename=photo.filename)


@router.get("/{photo_id}/video/stream")
async def stream_video(photo_id: int, db: AsyncSession = Depends(get_db)):
    """Stream video directly or serve transcoded WebM."""
    photo = await db.get(Photo, photo_id)
    if not photo or not photo.is_video:
        raise HTTPException(404)

    # Prefer pre-transcoded WebM
    if photo.video_webm_path and os.path.exists(photo.video_webm_path):
        return FileResponse(photo.video_webm_path, media_type="video/webm",
                            headers={"Cache-Control": "public, max-age=86400"})

    # Fall back to original (browser handles mp4/mov natively)
    mime = photo.mime_type or "video/mp4"
    return FileResponse(photo.path, media_type=mime)


@router.post("/{photo_id}/video/transcode")
async def transcode_video(
    photo_id: int,
    codec: str = "h264",          # h264 (faster, wider support) | vp9 (webm)
    resolution: int = 720,
    db: AsyncSession = Depends(get_db),
):
    """Hardware-accelerated video transcode (CUDA/QSV/VAAPI → H.264 MP4 or VP9 WebM)."""
    from app.core.config import get_settings
    from app.services.hw_accel import detect_hw, build_transcode_cmd

    photo = await db.get(Photo, photo_id)
    if not photo or not photo.is_video:
        raise HTTPException(404)

    settings = get_settings()
    ext = "mp4" if codec == "h264" else "webm"
    out_dir = pathlib.Path(settings.cache_path) / "videos"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{photo_id}_{resolution}.{ext}"

    if out_path.exists():
        photo.video_webm_path = str(out_path)
        await db.commit()
        return {"status": "already_done", "path": str(out_path), "hw": "cached"}

    hw = detect_hw()
    cmd = build_transcode_cmd(photo.path, str(out_path), resolution=resolution, codec=codec, hw=hw)

    proc = subprocess.run(cmd, capture_output=True, timeout=600)
    if proc.returncode == 0 and out_path.exists():
        photo.video_webm_path = str(out_path)
        await db.commit()
        return {"status": "done", "path": str(out_path), "hw": hw.name, "info": hw.info}
    else:
        # Fallback to software if HW failed
        if hw.name != "software":
            sw_cmd = [
                "ffmpeg", "-y", "-i", photo.path,
                "-c:v", "libvpx-vp9" if codec == "vp9" else "libx264",
                "-vf", f"scale=-2:{resolution}",
                "-crf", "28", "-b:v", "0",
                "-c:a", "aac" if codec == "h264" else "libopus", "-b:a", "128k",
                str(out_path),
            ]
            proc2 = subprocess.run(sw_cmd, capture_output=True, timeout=600)
            if proc2.returncode == 0 and out_path.exists():
                photo.video_webm_path = str(out_path)
                await db.commit()
                return {"status": "done_sw_fallback", "path": str(out_path), "hw": "software"}
        raise HTTPException(500, f"ffmpeg error ({hw.name}): {proc.stderr.decode()[-500:]}")
