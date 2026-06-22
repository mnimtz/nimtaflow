from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, distinct, extract, text
from datetime import date, datetime, timezone
import os, subprocess, pathlib, mimetypes

from app.core.database import get_db
from app.core.auth_guard import current_user_optional
from app.core.access import photo_conditions, can_see_photo, feature_allowed, _is_unrestricted
from app.models.photo import Photo, PhotoStatus
from app.models.user import User
from app.schemas.photo import PhotoListResponse, PhotoDetail, TimelineGroup, PhotoBase

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
    # Show a photo as soon as it HAS a thumbnail — don't make it wait for the
    # (possibly slow) AI/face stage to mark it 'done'. So new imports appear fast.
    q = select(Photo).where(Photo.thumb_small.isnot(None), Photo.is_missing == False)
    if view == "trash":
        q = q.where(Photo.is_trashed == True)
    elif view == "archive":
        q = q.where(Photo.is_archived == True, Photo.is_trashed == False)
    elif view == "favorites":
        q = q.where(Photo.is_favorite == True, Photo.is_trashed == False, Photo.is_archived == False)
    else:  # library
        q = q.where(Photo.is_trashed == False, Photo.is_archived == False)
    if search:
        # Match the AI description OR the filename, so typing "IMG_6801.JPG"
        # (or any partial filename) finds the photo directly.
        like = f"%{search.strip()}%"
        q = q.where(or_(Photo.description.ilike(like), Photo.filename.ilike(like)))
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
        q = q.where(Photo.is_video == False, or_(Photo.mime_type.is_(None), Photo.mime_type.not_like("image/raw%")))
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
    user: Optional[User] = Depends(current_user_optional),
):
    q = _base_query(db, search, date_from, date_to, person_id, tag, camera, media_type, favorites, has_gps, view)
    for c in photo_conditions(user):
        q = q.where(c)

    if lat is not None and lng is not None and radius_km:
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
async def semantic_search(q: str, limit: int = Query(60, ge=1, le=200), db: AsyncSession = Depends(get_db),
                          user: Optional[User] = Depends(current_user_optional)):
    """Natural-language semantic search over photo embeddings (pgvector cosine).
    Embeds the query with the configured embedding provider and returns the
    closest photos. Requires photos to have embeddings (AI processing done)."""
    if not q.strip():
        return PhotoListResponse(total=0, page=1, limit=limit, items=[])
    from app.services.settings_loader import load_settings
    from app.services.photo_search import search_photos
    s = await load_settings(db)
    photos = await search_photos(db, q, s, limit=limit, extra_conditions=photo_conditions(user))
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
    user: Optional[User] = Depends(current_user_optional),
):
    """Returns photos grouped by day, newest first, for timeline view."""
    q = _base_query(db, search, date_from, date_to, person_id, None, camera, media_type, favorites)
    for c in photo_conditions(user):
        q = q.where(c)
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

    # Pipeline stage coverage (how far each photo got through processing)
    from app.models.face import Face
    live = [Photo.is_trashed == False]  # noqa: E712
    thumbed = await db.scalar(select(func.count()).where(*live, Photo.thumb_small.isnot(None)))
    described = await db.scalar(select(func.count()).where(*live, Photo.description.isnot(None), Photo.description != ""))
    embedded = await db.scalar(select(func.count()).where(*live, Photo.embedding.isnot(None)))
    # only count AI errors that actually left the photo without a usable index
    ai_failed = await db.scalar(select(func.count()).where(
        *live, Photo.ai_error == True, Photo.embedding.is_(None), Photo.is_video == False))  # noqa: E712
    with_faces = await db.scalar(select(func.count(func.distinct(Face.photo_id))))

    # all indexed (any status) — the right denominator for pipeline coverage %
    total_indexed = await db.scalar(select(func.count()).where(Photo.is_trashed == False))  # noqa: E712

    # "Metadata still pending": indexed photos whose date hasn't been extracted yet —
    # a reliable signal that per-photo processing (date/GPS/thumbnail) isn't finished,
    # even when the folder scan reports done. Drives the Leitstand indicator + button.
    metadata_pending = await db.scalar(select(func.count()).where(
        *live, Photo.taken_at.is_(None)))

    return {
        "total": total or 0,
        "total_indexed": total_indexed or 0,
        "videos": videos or 0,
        "favorites": favorites or 0,
        "with_gps": with_gps or 0,
        "metadata_pending": metadata_pending or 0,
        "cameras": [{"model": r[0], "count": r[1]} for r in cameras],
        "date_min": min_date.isoformat() if min_date else None,
        "date_max": max_date.isoformat() if max_date else None,
        "by_status": by_status,
        "coverage": {
            "thumbnailed": thumbed or 0, "described": described or 0,
            "embedded": embedded or 0, "with_faces": with_faces or 0, "ai_error": ai_failed or 0,
        },
    }


class MemoryGroupWeb(BaseModel):
    years_ago: int
    date: str
    photos: List[PhotoBase]


@router.get("/memories", response_model=List[MemoryGroupWeb])
async def get_memories(db: AsyncSession = Depends(get_db),
                       user: Optional[User] = Depends(current_user_optional)):
    """Photos from exactly 1, 2, 3... years ago today. Optionally limited to
    photos containing selected people (Settings → Erinnerungen).

    Respects per-user access (folder/date/person restrictions) so a restricted
    user never sees memories from photos they cannot access."""
    from datetime import datetime, timezone, timedelta
    from app.services.settings_loader import load_settings
    settings = await load_settings(db)
    pid_raw = (settings.get("memories.person_ids") or "").strip()
    person_ids = [int(x) for x in pid_raw.replace(" ", "").split(",") if x.strip().isdigit()]
    person_cond = []
    if person_ids:
        from app.models.face import Face
        from app.models.person import Person
        # Drop hidden persons so hiding someone automatically removes them from
        # memories (only NAMED + visible persons count). If all selected are hidden,
        # the result is empty rather than falling back to "all photos".
        visible = list((await db.execute(
            select(Person.id).where(Person.id.in_(person_ids), Person.is_hidden == False)  # noqa: E712
        )).scalars())
        person_cond = [Photo.id.in_(select(Face.photo_id).where(Face.person_id.in_(visible)))]

    today = datetime.now(timezone.utc)
    try:
        max_years = int(settings.get("memories.max_years") or 30)
    except (TypeError, ValueError):
        max_years = 30
    memories = []
    for years_ago in range(1, max(2, max_years + 1)):
        try:
            target = today.replace(year=today.year - years_ago)
        except ValueError:  # Feb 29 → Feb 28
            target = today.replace(year=today.year - years_ago, day=28)
        start = target - timedelta(days=1)
        end = target + timedelta(days=1)
        photos = (await db.execute(
            select(Photo)
            .where(Photo.taken_at.between(start, end), Photo.is_trashed == False,  # noqa: E712
                   Photo.status == PhotoStatus.done, *person_cond, *photo_conditions(user))
            .order_by(Photo.taken_at)
            .limit(30)
        )).scalars().all()
        if photos:
            memories.append({"years_ago": years_ago, "date": target.date().isoformat(), "photos": photos})
    return memories


@router.get("/trips")
async def trips(db: AsyncSession = Depends(get_db),
                user: Optional[User] = Depends(current_user_optional),
                min_photos: Optional[int] = None, gap_hours: int = 20):
    """Auto-detect events/trips: walk photos by time, start a new event after a gap
    > gap_hours, keep events with >= min_photos. 'is_trip' = the event's dominant
    city differs from the library's home (most-common) city. Powers auto albums.
    min_photos defaults to the 'trips.min_photos' setting (8)."""
    from collections import Counter
    from datetime import timedelta
    if min_photos is None:
        from app.services.settings_loader import load_settings
        s = await load_settings(db)
        try:
            min_photos = max(1, int(s.get("trips.min_photos", "8") or 8))
        except Exception:
            min_photos = 8
    conds = photo_conditions(user)
    rows = (await db.execute(
        select(Photo.id, Photo.taken_at, Photo.city, Photo.is_video).where(
            Photo.taken_at.isnot(None), Photo.is_trashed == False, Photo.is_archived == False,  # noqa: E712
            *conds,
        ).order_by(Photo.taken_at)
    )).all()
    if not rows:
        return {"home_city": None, "events": []}
    home = Counter(r[2] for r in rows if r[2]).most_common(1)
    home_city = home[0][0] if home else None
    events, cur = [], None
    for pid, ta, city, is_video in rows:
        if cur and (ta - cur["last"]) <= timedelta(hours=gap_hours):
            cur["ids"].append(pid); cur["last"] = ta
            if city:
                cur["cities"][city] += 1
            if not is_video and cur["cover"] is None:
                cur["cover"] = pid
        else:
            if cur:
                events.append(cur)
            cur = {"ids": [pid], "first": ta, "last": ta, "cities": Counter(),
                   "cover": (None if is_video else pid)}
            if city:
                cur["cities"][city] += 1
    if cur:
        events.append(cur)
    out = []
    for ev in events:
        if len(ev["ids"]) < min_photos:
            continue
        dom = ev["cities"].most_common(1)
        city = dom[0][0] if dom else None
        out.append({
            "count": len(ev["ids"]),
            "date_from": ev["first"].date().isoformat(),
            "date_to": ev["last"].date().isoformat(),
            "days": (ev["last"].date() - ev["first"].date()).days + 1,
            "city": city,
            "is_trip": bool(city and city != home_city),
            "cover_photo_id": ev["cover"] or ev["ids"][len(ev["ids"]) // 2],
        })
    out.sort(key=lambda e: e["date_from"], reverse=True)
    return {"home_city": home_city, "events": out}


@router.get("/map")
async def map_points(db: AsyncSession = Depends(get_db),
                     user: Optional[User] = Depends(current_user_optional)):
    """Lightweight: every photo with GPS as {id, latitude, longitude} — NO 500
    cap (the gallery list capped the map at 500). Just coordinates, so the whole
    library's points render; clicking a point fetches the photo detail by id."""
    conds = photo_conditions(user)
    # Return ALL gps points (newest first) — the 2D map clusters them
    # (react-leaflet-cluster, zoom-adaptive); the globe slices to a renderable
    # subset client-side. Lightweight rows (just coords), so the full set is fine.
    rows = (await db.execute(
        select(Photo.id, Photo.latitude, Photo.longitude, Photo.is_video,
               Photo.city, Photo.country, Photo.location_name).where(
            Photo.latitude.isnot(None), Photo.longitude.isnot(None),
            Photo.is_trashed == False, Photo.is_archived == False,  # noqa: E712
            *conds,
        ).order_by(Photo.taken_at.desc().nullslast())
    )).all()
    return [{"id": r[0], "latitude": r[1], "longitude": r[2], "is_video": r[3],
             "city": r[4], "country": r[5], "location_name": r[6]} for r in rows]


@router.get("/{photo_id}")
async def get_photo(photo_id: int, db: AsyncSession = Depends(get_db),
                    user: Optional[User] = Depends(current_user_optional)):
    photo = await db.get(Photo, photo_id)
    if not photo:
        raise HTTPException(404, "Photo not found")
    if not can_see_photo(photo, user):
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


async def _persist_rating(photo) -> None:
    """Write the photo's rating into the file as XMP:Rating (0-5). Favourite maps
    to 5 stars (user-chosen convention) so a re-import recovers it. Best-effort —
    never let a file-write failure break the API call."""
    try:
        from app.services.exif_edit import write_rating
        eff = 5 if photo.is_favorite else int(photo.user_rating or 0)
        await write_rating(photo.path, eff)
    except Exception:
        pass


@router.patch("/{photo_id}/favorite")
async def toggle_favorite(photo_id: int, db: AsyncSession = Depends(get_db),
                          user: Optional[User] = Depends(current_user_optional)):
    photo = await db.get(Photo, photo_id)
    if not photo or not can_see_photo(photo, user):
        raise HTTPException(404)
    photo.is_favorite = not photo.is_favorite
    await db.commit()
    await _persist_rating(photo)
    return {"is_favorite": photo.is_favorite}


@router.patch("/{photo_id}/archive")
async def toggle_archive(photo_id: int, db: AsyncSession = Depends(get_db),
                         user: Optional[User] = Depends(current_user_optional)):
    photo = await db.get(Photo, photo_id)
    if not photo or not can_see_photo(photo, user):
        raise HTTPException(404)
    photo.is_archived = not photo.is_archived
    await db.commit()
    return {"is_archived": photo.is_archived}


@router.patch("/{photo_id}/rating")
async def set_rating(photo_id: int, rating: int = 0, db: AsyncSession = Depends(get_db),
                     user: Optional[User] = Depends(current_user_optional)):
    photo = await db.get(Photo, photo_id)
    if not photo or not can_see_photo(photo, user):
        raise HTTPException(404)
    photo.user_rating = max(0, min(5, rating))
    await db.commit()
    await _persist_rating(photo)
    return {"user_rating": photo.user_rating}


@router.patch("/{photo_id}/trash")
async def toggle_trash(photo_id: int, db: AsyncSession = Depends(get_db),
                       user: Optional[User] = Depends(current_user_optional)):
    photo = await db.get(Photo, photo_id)
    if not photo or not can_see_photo(photo, user):
        raise HTTPException(404)
    photo.is_trashed = not photo.is_trashed
    photo.trashed_at = datetime.now(timezone.utc) if photo.is_trashed else None
    await db.commit()
    return {"is_trashed": photo.is_trashed}


async def _source_roots(db: AsyncSession) -> list:
    """Configured source roots — we only ever unlink files UNDER these, so a bug
    can never delete an arbitrary path."""
    from app.models.source import PhotoSource
    return [r for (r,) in (await db.execute(select(PhotoSource.path))).all() if r]


def _safe_unlink(path: str, roots: list) -> bool:
    """Delete a file only if it sits under a configured source root. Best-effort."""
    import os
    try:
        rp = os.path.realpath(path)
        if not any(rp == os.path.realpath(r) or rp.startswith(os.path.realpath(r) + os.sep)
                   for r in roots):
            return False
        if os.path.isfile(rp):
            os.remove(rp)
        # sidecars next to the file
        for sc in (path + ".xmp", os.path.splitext(path)[0] + ".xmp"):
            if os.path.isfile(sc):
                try: os.remove(sc)
                except OSError: pass
        return True
    except OSError:
        return False


async def _hard_delete(db: AsyncSession, photo: Photo, delete_file: bool, roots: list):
    """Permanently remove a photo: optionally unlink the original file (+sidecars)
    and its cached thumbnails, then delete the DB row (faces/tags/album-entries
    cascade per the model)."""
    import os
    if delete_file:
        _safe_unlink(photo.path, roots)
    for t in (photo.thumb_small, photo.thumb_medium, photo.thumb_large,
              getattr(photo, "video_preview_path", None)):
        if t and os.path.isabs(t) and os.path.isfile(t):
            try: os.remove(t)
            except OSError: pass
    await db.delete(photo)


@router.delete("/{photo_id}")
async def delete_photo(photo_id: int, delete_file: bool = True,
                       db: AsyncSession = Depends(get_db),
                       user: Optional[User] = Depends(current_user_optional)):
    """Hard-delete a single photo (DB row + cached thumbnails, and the original
    file unless delete_file=false). This is the 'endgültig löschen' action."""
    photo = await db.get(Photo, photo_id)
    if not photo or not can_see_photo(photo, user):
        raise HTTPException(404)
    roots = await _source_roots(db)
    await _hard_delete(db, photo, delete_file, roots)
    await db.commit()
    return {"deleted": photo_id}


# ── Bulk actions ──────────────────────────────────────────────────────────────

from pydantic import BaseModel as _BM
from typing import List as _List


class BatchAction(_BM):
    ids: _List[int]
    action: str  # favorite | unfavorite | archive | unarchive | trash | untrash


class TripPlanRequest(_BM):
    description: str
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    trip_type: Optional[str] = None  # kreuzfahrt | pauschalurlaub | flugreise | roadtrip | …


@router.post("/plan-trip")
async def plan_trip_endpoint(body: TripPlanRequest, db: AsyncSession = Depends(get_db)):
    """AI trip planner: rough text → structured itinerary (waypoints with coords +
    dates) via Gemini with Google-Search grounding. Used by the 'Reise anlegen'-Assistent."""
    from app.services.settings_loader import load_settings
    from app.services.trip_planner import plan_trip
    s = await load_settings(db)
    return await plan_trip(body.description, body.date_from, body.date_to, s, body.trip_type)


class CreateTripRequest(_BM):
    name: str
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    waypoints: Optional[list] = None
    description: Optional[str] = None
    trip_type: Optional[str] = None


@router.post("/create-trip")
async def create_trip(body: CreateTripRequest, db: AsyncSession = Depends(get_db)):
    """Create a trip = a MANUAL album (photos materialised → removable) whose route
    (waypoints) is stored in smart_criteria. Auto-fills with all photos in the
    date range; the user can then remove non-fitting ones via the album."""
    from datetime import datetime as _dt, timedelta as _td
    from app.models.album import Album, AlbumPhoto, AlbumType

    def _pd(s):
        try:
            return _dt.strptime(s[:10], "%Y-%m-%d") if s else None
        except Exception:
            return None
    df, dt = _pd(body.date_from), _pd(body.date_to)
    album = Album(
        name=(body.name or "Reise").strip()[:256],
        album_type=AlbumType.manual,
        description=body.description,
        smart_criteria={"trip": True, "route": body.waypoints or [],
                        "trip_type": body.trip_type,
                        "date_from": body.date_from, "date_to": body.date_to},
    )
    db.add(album)
    await db.flush()
    added = 0
    if df and dt:
        rows = (await db.execute(
            select(Photo.id).where(
                Photo.taken_at >= df, Photo.taken_at < dt + _td(days=1),
                Photo.is_trashed == False, Photo.is_archived == False,  # noqa: E712
            ).order_by(Photo.taken_at)
        )).all()
        ids = [r[0] for r in rows]
        for i, pid in enumerate(ids):
            db.add(AlbumPhoto(album_id=album.id, photo_id=pid, sort_order=i))
        added = len(ids)
        if ids:
            album.cover_photo_id = ids[len(ids) // 2]
    await db.commit()
    return {"album_id": album.id, "added": added, "name": album.name}


@router.post("/reprocess-failed")
async def reprocess_failed(db: AsyncSession = Depends(get_db)):
    """Re-queue all photos that errored, never finished, or whose AI step failed
    (e.g. a transient Gemini 503) while the thumbnail succeeded."""
    from app.worker.tasks import process_photo_task
    rows = (await db.execute(
        select(Photo.id).where(
            (Photo.status.in_([PhotoStatus.error, PhotoStatus.pending, PhotoStatus.processing]))
            | (Photo.ai_error == True)  # noqa: E712
        )
    )).all()
    ids = [r[0] for r in rows]
    for pid in ids:
        process_photo_task.delay(pid, None, False, True)
    return {"reprocessing": len(ids)}


@router.post("/scan-metadata")
async def scan_metadata(db: AsyncSession = Depends(get_db)):
    """Manually trigger the fast EXIF date+GPS(+city) backfill (Leitstand button).
    Runs on the 'scan' queue so it bypasses the slow process_photo backlog — date,
    GPS and place names for already-scanned files populate within minutes."""
    pending = await db.scalar(select(func.count()).where(
        Photo.is_trashed == False,  # noqa: E712
        or_(Photo.taken_at.is_(None), Photo.latitude.is_(None))))
    from app.worker.tasks import backfill_metadata_task
    backfill_metadata_task.delay()
    return {"queued": True, "candidates": pending or 0}


@router.post("/{photo_id}/reprocess")
async def reprocess_photo(photo_id: int, db: AsyncSession = Depends(get_db),
                          user: Optional[User] = Depends(current_user_optional)):
    """On-demand: re-run processing for ONE photo (re-detect faces, re-make
    thumbnails, and let the AI step re-attempt by clearing ai_error). The detail
    view polls afterwards so the fresh result appears live. Keeps the existing
    description until a new one lands (non-destructive)."""
    photo = await db.get(Photo, photo_id)
    if not photo or not can_see_photo(photo, user):
        raise HTTPException(404)
    photo.ai_error = False
    photo.faces_scanned = False   # force a fresh face pass
    if photo.status == PhotoStatus.error:
        photo.status = PhotoStatus.pending
    await db.commit()
    from app.worker.tasks import process_photo_task
    process_photo_task.delay(photo_id, None, True, True)  # redo_faces + redo_thumbs
    return {"ok": True, "photo_id": photo_id}


@router.post("/reprocess-missing-ai")
async def reprocess_missing_ai(db: AsyncSession = Depends(get_db)):
    """Re-queue done photos that have no embedding yet (AI never ran / was off) —
    'KI nachholen' so search & AI albums work for them."""
    from app.worker.tasks import process_photo_task
    rows = (await db.execute(
        select(Photo.id).where(
            Photo.status == PhotoStatus.done, Photo.is_trashed == False,  # noqa: E712
            Photo.embedding.is_(None), Photo.is_video == False,  # noqa: E712
        )
    )).all()
    ids = [r[0] for r in rows]
    for pid in ids:
        process_photo_task.delay(pid)
    return {"reprocessing": len(ids)}


@router.post("/backfill-xmp")
async def backfill_xmp(db: AsyncSession = Depends(get_db)):
    """Write existing DB descriptions + tags INTO the image files (honours
    xmp.write_mode). Repairs photos processed by the remote worker before it
    wrote files, or after enabling XMP. Runs as one background task."""
    from app.worker.tasks import backfill_xmp_task
    n = await db.scalar(select(func.count()).where(Photo.description.isnot(None)))
    backfill_xmp_task.delay()
    return {"queued": True, "described_photos": n or 0}


@router.post("/batch")
async def batch_action(body: BatchAction, db: AsyncSession = Depends(get_db),
                       user: Optional[User] = Depends(current_user_optional)):
    """Apply an action to many photos at once (selection bar in the gallery)."""
    # Restrict the affected set to photos this user may actually see, so a
    # restricted user can never mutate/delete photos outside their whitelist.
    ids = body.ids
    if not _is_unrestricted(user):
        allowed = (await db.execute(
            select(Photo.id).where(Photo.id.in_(body.ids), *photo_conditions(user))
        )).scalars().all()
        ids = list(allowed)
    # Bulk hard-delete (endgültig löschen) — selection bar "Löschen".
    if body.action == "delete":
        roots = await _source_roots(db)
        photos = (await db.execute(select(Photo).where(Photo.id.in_(ids)))).scalars().all()
        for p in photos:
            await _hard_delete(db, p, delete_file=True, roots=roots)
        await db.commit()
        return {"deleted": len(photos), "action": "delete"}

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
    result = await db.execute(select(Photo).where(Photo.id.in_(ids)))
    photos = result.scalars().all()
    for p in photos:
        setattr(p, field, value)
        if field == "is_trashed":
            p.trashed_at = datetime.now(timezone.utc) if value else None
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
async def update_meta(photo_id: int, body: MetaUpdate, db: AsyncSession = Depends(get_db),
                      user: Optional[User] = Depends(current_user_optional)):
    """Edit metadata in DB and optionally write to file / XMP sidecar."""
    photo = await db.get(Photo, photo_id)
    if not photo or not can_see_photo(photo, user):
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
async def get_thumbnail(photo_id: int, size: str = "medium", db: AsyncSession = Depends(get_db),
                        user: Optional[User] = Depends(current_user_optional)):
    photo = await db.get(Photo, photo_id)
    if not photo or not can_see_photo(photo, user):
        raise HTTPException(404)
    exact = getattr(photo, f"thumb_{size}", None)
    # Serve the requested size if its FILE exists, else fall back to ANY size whose
    # file is actually on disk (a set-but-missing thumb_medium must not 404 when
    # thumb_small exists — that was the grey-tile cause in search/grids).
    thumb = next((t for t in (exact, photo.thumb_large, photo.thumb_medium, photo.thumb_small)
                  if t and os.path.exists(t)), None)
    if not thumb:
        raise HTTPException(404, "Thumbnail not ready")
    # Cache forever ONLY when we serve the exact size requested. If the requested
    # size isn't ready yet and we fall back to a smaller one, send no-cache so the
    # browser refetches later — otherwise it would keep the fallback (small) image
    # permanently even after the larger one is generated ("clicked photo stays small").
    served_exact = bool(exact) and os.path.exists(exact)
    cache = "public, max-age=31536000, immutable" if served_exact else "no-cache, must-revalidate"
    return FileResponse(thumb, media_type="image/jpeg", headers={"Cache-Control": cache})


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
async def get_original(photo_id: int, db: AsyncSession = Depends(get_db),
                       user: Optional[User] = Depends(current_user_optional)):
    photo = await db.get(Photo, photo_id)
    if not photo or not can_see_photo(photo, user):
        raise HTTPException(404)
    if not feature_allowed(user, "allow_download"):
        raise HTTPException(403, "Download nicht erlaubt")
    mime = photo.mime_type or mimetypes.guess_type(photo.path)[0] or "application/octet-stream"
    return FileResponse(photo.path, media_type=mime, filename=photo.filename)


@router.get("/{photo_id}/video/stream")
async def stream_video(photo_id: int, db: AsyncSession = Depends(get_db),
                       user: Optional[User] = Depends(current_user_optional)):
    """Stream video directly or serve transcoded WebM."""
    photo = await db.get(Photo, photo_id)
    if not photo or not photo.is_video or not can_see_photo(photo, user):
        raise HTTPException(404)

    # Prefer the cached web-optimised version (H.264 MP4 with faststart, or WebM)
    web = photo.video_webm_path
    if web and os.path.exists(web):
        mt = "video/mp4" if web.endswith(".mp4") else "video/webm"
        return FileResponse(web, media_type=mt,
                            headers={"Cache-Control": "public, max-age=86400"})

    # No web version yet → kick off a background HW transcode (single-flight) so
    # the NEXT play starts instantly, and serve the original meanwhile (works for
    # native mp4/mov; non-streamable formats become playable after the transcode).
    try:
        from app.worker.tasks import transcode_video_task
        transcode_video_task.delay(photo_id)
    except Exception:
        pass
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
