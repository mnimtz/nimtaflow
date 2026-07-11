from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, Response, UploadFile, File
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, distinct, extract, text
from sqlalchemy.orm import load_only
from datetime import date, datetime, timezone
import os, subprocess, pathlib, mimetypes, asyncio

from app.core.database import get_db
from app.core.auth_guard import current_user_optional, require_pipeline
from app.core.access import photo_conditions, can_see_photo, user_can_access_photo, feature_allowed, _is_unrestricted
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
    # Wichtig: die Joins mit Face und PhotoTag können ein Foto MEHRFACH
    # zurückgeben (Foto mit mehreren Gesichtern derselben Person; Foto mit
    # mehreren PhotoTag-Zeilen desselben Tag-Namens). Ohne DISTINCT:
    # sichtbare Duplikate in der Galerie + falsches `total` + zu frühes
    # Pagination-Ende (items.length < limit).
    _joined = False
    if person_id:
        from app.models.face import Face
        q = q.join(Face, Face.photo_id == Photo.id).where(Face.person_id == person_id)
        _joined = True
    if tag:
        from app.models.tag import Tag, PhotoTag
        q = q.join(PhotoTag, PhotoTag.photo_id == Photo.id).join(Tag, Tag.id == PhotoTag.tag_id).where(Tag.name == tag)
        _joined = True
    if _joined:
        # SELECT DISTINCT * (Postgres-Standard, kein DISTINCT ON) — Photo.id
        # ist PK, alle Spalten pro id identisch → wirkt genau wie DISTINCT ON (id)
        # und harmoniert mit dem späteren ORDER BY taken_at DESC, id DESC.
        q = q.distinct()
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
    ids: Optional[str] = None,   # kommagetrennte Foto-IDs (KI-Assistent-Ergebnis-Set)
    db: AsyncSession = Depends(get_db),
    user: Optional[User] = Depends(current_user_optional),
):
    q = _base_query(db, search, date_from, date_to, person_id, tag, camera, media_type, favorites, has_gps, view)
    for c in photo_conditions(user):
        q = q.where(c)

    if ids is not None:
        try:
            id_list = [int(x) for x in ids.split(",") if x.strip()]
        except ValueError:
            id_list = []
        # Nur genau diese Fotos (Assistent). Leere Liste → bewusst 0 Treffer.
        q = q.where(Photo.id.in_(id_list) if id_list else Photo.id == -1)

    if lat is not None and lng is not None and radius_km:
        lat_delta = radius_km / 111.0
        lng_delta = radius_km / (111.0 * max(abs(lat), 0.01))
        q = q.where(
            and_(
                Photo.latitude.between(lat - lat_delta, lat + lat_delta),
                Photo.longitude.between(lng - lng_delta, lng + lng_delta),
            )
        )

    # Gesamtzahl nur auf Seite 1 zählen (COUNT über ~140k+ACL-Joins kostet ~140ms) —
    # sie ändert sich beim Weiterscrollen nicht. Das Frontend liest total aus Seite 1
    # und entscheidet „nächste Seite?" anhand der zurückgegebenen Item-Anzahl.
    total = await db.scalar(select(func.count()).select_from(q.subquery())) if page == 1 else -1
    if sort == "oldest":
        q = q.order_by(Photo.taken_at.asc().nullsfirst(), Photo.id.asc())
    elif sort == "added":
        q = q.order_by(Photo.indexed_at.desc().nullslast(), Photo.id.desc())
    elif sort == "name":
        q = q.order_by(Photo.filename.asc())
    else:  # newest (default)
        q = q.order_by(Photo.taken_at.desc().nullslast(), Photo.id.desc())
    q = q.offset((page - 1) * limit).limit(limit)
    # Nur die Spalten laden, die PhotoBase tatsächlich braucht. Erspart pro Row
    # ~800 Bytes (description Text 200-1000 chars, caption, keywords, camera-
    # meta die für die Grid-Ansicht irrelevant sind).
    q = q.options(load_only(
        Photo.id, Photo.path, Photo.filename, Photo.taken_at,
        Photo.width, Photo.height, Photo.latitude, Photo.longitude,
        Photo.status, Photo.thumb_small, Photo.thumb_medium, Photo.processed_at,
        Photo.is_video, Photo.duration_seconds, Photo.is_favorite,
        Photo.is_archived, Photo.is_trashed, Photo.user_rating,
        Photo.focus_x, Photo.focus_y, Photo.blur_data,
    ))
    photos = (await db.execute(q)).scalars().all()
    return PhotoListResponse(total=total or 0, page=page, limit=limit, items=photos)


@router.get("/timeline/buckets")
async def timeline_buckets(
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
    ids: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    user: Optional[User] = Depends(current_user_optional),
):
    """Monats-Zählungen für die aktuelle Filter-/Ansicht-Kombination — damit die Galerie
    die GESAMTE Zeitspanne (Höhe + Datums-Sprungmarken) sofort kennt, ohne alle Fotos zu
    laden (Immich-„Timeline-Buckets"). Respektiert dieselbe ACL/Filter wie die Foto-Liste."""
    q = _base_query(db, search, date_from, date_to, person_id, tag, camera, media_type, favorites, has_gps, view)
    for c in photo_conditions(user):
        q = q.where(c)
    if ids is not None:
        try:
            id_list = [int(x) for x in ids.split(",") if x.strip()]
        except ValueError:
            id_list = []
        q = q.where(Photo.id.in_(id_list) if id_list else Photo.id == -1)
    sub = q.subquery()
    month = func.to_char(func.date_trunc("month", sub.c.taken_at), "YYYY-MM")
    rows = (await db.execute(
        select(month.label("m"), func.count().label("c"))
        .select_from(sub).where(sub.c.taken_at.isnot(None))
        .group_by(month).order_by(month.desc())
    )).all()
    undated = await db.scalar(select(func.count()).select_from(sub).where(sub.c.taken_at.is_(None))) or 0
    buckets = [{"month": m, "count": c} for m, c in rows]
    total = sum(c for _, c in rows) + undated
    return {"buckets": buckets, "undated": undated, "total": total}


# Pet keywords the AI tagger emits (DE + EN). Exact (lower-cased) match keeps it
# precise — clean single-word tags like "Hund"/"Katze", no "hundert" false hits.
_PET_TAGS = {
    "hund", "hunde", "hündin", "welpe", "welpen", "katze", "katzen", "kätzchen",
    "kater", "haustier", "haustiere", "vierbeiner",
    "dog", "dogs", "puppy", "puppies", "cat", "cats", "kitten", "kittens", "pet", "pets",
}


@router.get("/pets", response_model=PhotoListResponse)
async def list_pets(page: int = Query(1, ge=1), limit: int = Query(60, ge=1, le=500),
                    db: AsyncSession = Depends(get_db),
                    user: Optional[User] = Depends(current_user_optional)):
    """Photos that show pets — surfaced from the AI tags (Hund/Katze/…). No extra
    model needed: reuses the descriptions/tags already computed for every photo."""
    from app.models.tag import Tag, PhotoTag
    q = (select(Photo).distinct()
         .join(PhotoTag, PhotoTag.photo_id == Photo.id)
         .join(Tag, Tag.id == PhotoTag.tag_id)
         .where(func.lower(Tag.name).in_(_PET_TAGS), Photo.is_trashed == False))  # noqa: E712
    for c in photo_conditions(user):
        q = q.where(c)
    total = await db.scalar(select(func.count()).select_from(q.subquery()))
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
async def get_stats(db: AsyncSession = Depends(get_db),
                    user: Optional[User] = Depends(current_user_optional)):
    """Filter facets: cameras, date range, counts. Scoped to what `user` may see
    (no-op for admins / open mode) so a restricted account can't read
    whole-library totals, date span or camera list."""
    acl = photo_conditions(user)  # [] for unrestricted
    cameras = (await db.execute(
        select(Photo.camera_model, func.count().label("n"))
        .where(Photo.camera_model != None, Photo.is_trashed == False, *acl)
        .group_by(Photo.camera_model).order_by(text("n desc")).limit(20)
    )).all()

    total = await db.scalar(select(func.count()).where(Photo.is_trashed == False, Photo.status == PhotoStatus.done, *acl))
    videos = await db.scalar(select(func.count()).where(Photo.is_video == True, Photo.is_trashed == False, *acl))
    favorites = await db.scalar(select(func.count()).where(Photo.is_favorite == True, Photo.is_trashed == False, *acl))
    with_gps = await db.scalar(select(func.count()).where(Photo.latitude != None, Photo.is_trashed == False, *acl))

    min_date = await db.scalar(select(func.min(Photo.taken_at)).where(Photo.is_trashed == False, *acl))
    max_date = await db.scalar(select(func.max(Photo.taken_at)).where(Photo.is_trashed == False, *acl))

    status_rows = (await db.execute(
        select(Photo.status, func.count()).where(*acl).group_by(Photo.status)
    )).all()
    by_status = {str(getattr(r[0], "value", r[0])): r[1] for r in status_rows}

    # Pipeline stage coverage (how far each photo got through processing)
    from app.models.face import Face
    live = [Photo.is_trashed == False, *acl]  # noqa: E712
    thumbed = await db.scalar(select(func.count()).where(*live, Photo.thumb_small.isnot(None)))
    described = await db.scalar(select(func.count()).where(*live, Photo.description.isnot(None), Photo.description != ""))
    embedded = await db.scalar(select(func.count()).where(*live, Photo.embedding.isnot(None)))
    # only count AI errors that actually left the photo without a usable index
    ai_failed = await db.scalar(select(func.count()).where(
        *live, Photo.ai_error == True, Photo.embedding.is_(None), Photo.is_video == False))  # noqa: E712
    if acl:
        with_faces = await db.scalar(
            select(func.count(func.distinct(Face.photo_id)))
            .select_from(Face).join(Photo, Photo.id == Face.photo_id).where(*acl))
    else:
        with_faces = await db.scalar(select(func.count(func.distinct(Face.photo_id))))

    # all indexed (any status) — the right denominator for pipeline coverage %
    total_indexed = await db.scalar(select(func.count()).where(Photo.is_trashed == False, *acl))  # noqa: E712

    # "Metadata still pending": indexed photos whose date hasn't been extracted yet —
    # a reliable signal that per-photo processing (date/GPS/thumbnail) isn't finished,
    # even when the folder scan reports done. Drives the Leitstand indicator + button.
    # Exclude photos that are already DONE but simply have no date in their metadata
    # (no EXIF date → taken_at stays NULL forever). Counting those made the Leitstand
    # indicator hang at thousands "for days" even though processing was finished.
    # Also exclude status=error: an undecodable/corrupt file will never get a date,
    # so counting it would hang the indicator forever (same reason as 'done' above).
    metadata_pending = await db.scalar(select(func.count()).where(
        *live, Photo.taken_at.is_(None),
        Photo.status.notin_([PhotoStatus.done, PhotoStatus.error])))

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
        photos = list((await db.execute(
            select(Photo)
            .where(Photo.taken_at.between(start, end), Photo.is_trashed == False,  # noqa: E712
                   Photo.status == PhotoStatus.done, *person_cond, *photo_conditions(user))
            .order_by(Photo.taken_at)
            .limit(60)
        )).scalars().all())
        if photos:
            # Smart pick: surface the BEST shot of the day first (cover) instead of
            # whatever happened to be earliest — favorites, rated, with people and
            # higher resolution rank up. Faces = a strong "memorable" signal.
            from app.models.face import Face
            ids = [p.id for p in photos]
            fcounts = dict((await db.execute(
                select(Face.photo_id, func.count()).where(Face.photo_id.in_(ids)).group_by(Face.photo_id)
            )).all()) if ids else {}

            def _score(p: Photo) -> float:
                s = 0.0
                if p.is_favorite:
                    s += 5.0
                if p.user_rating:
                    s += float(p.user_rating)
                s += min(fcounts.get(p.id, 0), 4) * 0.6
                if p.width and p.height:
                    s += min((p.width * p.height) / 1_000_000.0, 4.0) * 0.25
                return s

            photos.sort(key=lambda p: (-_score(p), p.taken_at or start))
            memories.append({"years_ago": years_ago, "date": target.date().isoformat(),
                             "photos": photos[:15]})
    return memories


class AskPhotoBody(BaseModel):
    question: str
    provider: Optional[str] = None   # auto | local | gemini (None = configured default)


@router.post("/{photo_id}/ask")
async def ask_about_photo(photo_id: int, body: AskPhotoBody,
                          db: AsyncSession = Depends(get_db),
                          user: Optional[User] = Depends(current_user_optional)):
    """Frag-das-Foto: free-text question about one photo, answered by a VLM
    (local default; cloud opt-in sends the photo to that provider)."""
    ok = await db.scalar(select(Photo.id).where(Photo.id == photo_id, *photo_conditions(user)))
    if not ok:
        raise HTTPException(404)
    from app.services.settings_loader import load_settings
    from app.services.ask_photo import ask_photo
    s = await load_settings(db)
    return await ask_photo(db, photo_id, body.question, s, body.provider)


@router.get("/{photo_id}/postcard")
async def photo_postcard(photo_id: int, lang: str = "de",
                         text: Optional[str] = None, subtitle: Optional[str] = None,
                         theme: str = "classic", text_color: Optional[str] = None,
                         db: AsyncSession = Depends(get_db),
                         user: Optional[User] = Depends(current_user_optional)):
    """A shareable postcard PNG generated from the photo. Greeting (text), personal
    message (subtitle) and theme are caller-supplied → drives the live editor."""
    photo = await db.scalar(select(Photo).where(Photo.id == photo_id, *photo_conditions(user)))
    if not photo:
        raise HTTPException(404)
    path = photo.thumb_large or photo.thumb_medium or photo.path
    if not path or not os.path.exists(path):
        raise HTTPException(404, "Kein Bild")
    place = ", ".join([p for p in (photo.city, photo.country) if p]) or photo.location_name or None
    from app.services.postcard import make_postcard
    png = await asyncio.to_thread(make_postcard, path, place, photo.taken_at, lang,
                                  (text or None), (subtitle or None), theme, (text_color or None))
    return Response(content=png, media_type="image/png",
                    headers={"Content-Disposition": 'inline; filename="nimtaflow-postkarte.png"'})


@router.post("/{photo_id}/voice-note")
async def set_voice_note(photo_id: int, file: UploadFile = File(...),
                         db: AsyncSession = Depends(get_db),
                         user: Optional[User] = Depends(current_user_optional)):
    """Attach a voice memo (recorded audio) to a photo. Stored in the cache."""
    photo = await db.scalar(select(Photo).where(Photo.id == photo_id, *photo_conditions(user)))
    if not photo:
        raise HTTPException(404)
    from app.core.config import get_settings
    data = await file.read()
    if len(data) > 25 * 1024 * 1024:
        raise HTTPException(413, "Sprach-Memo zu groß")
    d = os.path.join(get_settings().cache_path, "voice_notes")
    os.makedirs(d, exist_ok=True)
    ext = ".webm"
    fn = (file.filename or "").lower()
    if fn.endswith(".m4a") or "mp4" in (file.content_type or ""):
        ext = ".m4a"
    elif fn.endswith(".mp3"):
        ext = ".mp3"
    path = os.path.join(d, f"{photo_id}{ext}")
    with open(path, "wb") as fh:
        fh.write(data)
    photo.voice_note_path = path
    await db.commit()
    return {"ok": True}


@router.get("/{photo_id}/voice-note")
async def get_voice_note(photo_id: int, db: AsyncSession = Depends(get_db),
                         user: Optional[User] = Depends(current_user_optional)):
    photo = await db.scalar(select(Photo).where(Photo.id == photo_id, *photo_conditions(user)))
    if not photo or not photo.voice_note_path or not os.path.exists(photo.voice_note_path):
        raise HTTPException(404)
    ext = os.path.splitext(photo.voice_note_path)[1].lower()
    mt = {".m4a": "audio/mp4", ".mp3": "audio/mpeg"}.get(ext, "audio/webm")
    from fastapi.responses import FileResponse
    return FileResponse(photo.voice_note_path, media_type=mt)


@router.delete("/{photo_id}/voice-note")
async def delete_voice_note(photo_id: int, db: AsyncSession = Depends(get_db),
                            user: Optional[User] = Depends(current_user_optional)):
    photo = await db.scalar(select(Photo).where(Photo.id == photo_id, *photo_conditions(user)))
    if not photo:
        raise HTTPException(404)
    if photo.voice_note_path:
        try:
            if os.path.exists(photo.voice_note_path):
                os.remove(photo.voice_note_path)
        except Exception:
            pass
        photo.voice_note_path = None
        await db.commit()
    return {"ok": True}


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
        if not (cur and (ta - cur["last"]) <= timedelta(hours=gap_hours)):
            if cur:
                events.append(cur)
            cur = {"ids": [], "first": ta, "last": ta, "cities": Counter(),
                   "cover": None, "cover_by_city": {}}
        cur["ids"].append(pid); cur["last"] = ta
        if city:
            cur["cities"][city] += 1
            # remember the FIRST real photo per city so the cover can come from the
            # trip's actual destination, not a home snapshot that bracketed the cluster.
            if not is_video and city not in cur["cover_by_city"]:
                cur["cover_by_city"][city] = pid
        if not is_video and cur["cover"] is None:
            cur["cover"] = pid
    if cur:
        events.append(cur)
    from app.services.geo_names import fix_city
    out = []
    for ev in events:
        if len(ev["ids"]) < min_photos:
            continue
        dom = ev["cities"].most_common()
        # Title = the most-photographed city that ISN'T home (a day-trip's destination),
        # falling back to the top city if the whole cluster is at home.
        away = [(c, n) for c, n in dom if c and c != home_city]
        city_raw = away[0][0] if away else (dom[0][0] if dom else None)
        city = fix_city(city_raw)
        cover = ev["cover_by_city"].get(city_raw) or ev["cover"] or ev["ids"][len(ev["ids"]) // 2]
        out.append({
            "count": len(ev["ids"]),
            "date_from": ev["first"].date().isoformat(),
            "date_to": ev["last"].date().isoformat(),
            "days": (ev["last"].date() - ev["first"].date()).days + 1,
            "city": city,
            "is_trip": bool(city and city != fix_city(home_city)),
            "cover_photo_id": cover,
        })
    out.sort(key=lambda e: e["date_from"], reverse=True)
    return {"home_city": home_city, "events": out}


@router.get("/map")
async def map_points(ids: Optional[str] = None,
                     person_id: Optional[int] = None,
                     date_from: Optional[str] = None,
                     date_to: Optional[str] = None,
                     db: AsyncSession = Depends(get_db),
                     user: Optional[User] = Depends(current_user_optional)):
    """Lightweight: every photo with GPS as {id, latitude, longitude}.
    Accepts ids (comma-separated), person_id, date_from, date_to for
    Ambient-Assistent intent filtering."""
    from datetime import datetime as _dt, timedelta as _td
    from app.models.face import Face
    conds = photo_conditions(user)
    extra = []
    if ids is not None:
        try:
            id_list = [int(x) for x in ids.split(",") if x.strip()]
        except ValueError:
            id_list = []
        extra.append(Photo.id.in_(id_list) if id_list else Photo.id == -1)
    if person_id:
        extra.append(Photo.id.in_(select(Face.photo_id).where(Face.person_id == person_id)))
    if date_from:
        try: extra.append(Photo.taken_at >= _dt.fromisoformat(date_from))
        except ValueError: pass
    if date_to:
        try: extra.append(Photo.taken_at < _dt.fromisoformat(date_to) + _td(days=1))
        except ValueError: pass
    rows = (await db.execute(
        select(Photo.id, Photo.latitude, Photo.longitude, Photo.is_video,
               Photo.city, Photo.country, Photo.location_name).where(
            Photo.latitude.isnot(None), Photo.longitude.isnot(None),
            Photo.is_trashed == False, Photo.is_archived == False,  # noqa: E712
            *conds, *extra,
        )
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

    # all scalar columns, EXCEPT pgvector embedding columns: those load as numpy
    # ndarrays which FastAPI's jsonable_encoder can't serialize (it tries dict(obj)
    # → 500 for the whole response). Skip every ndarray generically so a future
    # vector column (e.g. embedding_text) can't reintroduce the bug.
    data = {}
    for c in sa_inspect(photo).mapper.column_attrs:
        v = getattr(photo, c.key)
        if type(v).__name__ == "ndarray":
            continue
        data[c.key] = v
    data.pop("embedding", None)

    tag_rows = await db.execute(
        select(Tag.name).join(PhotoTag, PhotoTag.tag_id == Tag.id).where(PhotoTag.photo_id == photo_id)
    )
    data["tags"] = [t for t in tag_rows.scalars()]

    face_rows = (await db.execute(
        select(Face.id, Face.bbox_x, Face.bbox_y, Face.bbox_w, Face.bbox_h,
               Face.confidence, Person.id, Person.name, Person.birthdate)
        .join(Person, Person.id == Face.person_id, isouter=True)
        .where(Face.photo_id == photo_id)
    )).all()
    data["people"] = [
        {"face_id": r[0], "bbox": [r[1], r[2], r[3], r[4]], "confidence": r[5],
         "person_id": r[6], "name": r[7], "birthdate": r[8].isoformat() if r[8] else None}
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


@router.post("/plan-trip", dependencies=[Depends(require_pipeline)])
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


@router.post("/create-trip", dependencies=[Depends(require_pipeline)])
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


@router.get("/error-report", dependencies=[Depends(require_pipeline)])
async def error_report(db: AsyncSession = Depends(get_db),
                       user: Optional[User] = Depends(current_user_optional)):
    """Full report of the error queue: which files failed and why (status=error =
    processing aborted, or ai_error = the AI step failed). Drives the 'Bericht' button."""
    rows = (await db.execute(
        select(Photo.id, Photo.filename, Photo.path, Photo.status, Photo.is_video,
               Photo.ai_error, Photo.ai_attempts, Photo.thumb_attempts, Photo.error_message)
        .where(Photo.is_trashed == False,  # noqa: E712
               or_(Photo.status == PhotoStatus.error, Photo.ai_error == True))  # noqa: E712
        .order_by(Photo.id)
    )).all()
    items = []
    for r in rows:
        if r[3] == PhotoStatus.error:
            reason = "Verarbeitung abgebrochen / Datei nicht dekodierbar"
        elif r[5]:
            reason = "KI-Beschreibung fehlgeschlagen"
        else:
            reason = "Fehler"
        items.append({
            "id": r[0], "filename": r[1], "path": r[2], "status": str(r[3].value if hasattr(r[3], 'value') else r[3]),
            "is_video": r[4], "ai_error": r[5], "ai_attempts": r[6], "thumb_attempts": r[7],
            "reason": reason, "error_message": r[8],
        })
    return {"count": len(items), "items": items}


@router.post("/reprocess-failed", dependencies=[Depends(require_pipeline)])
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


@router.post("/scan-metadata", dependencies=[Depends(require_pipeline)])
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


@router.post("/reprocess-missing-ai", dependencies=[Depends(require_pipeline)])
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


@router.post("/backfill-xmp", dependencies=[Depends(require_pipeline)])
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
    if not photo or not await user_can_access_photo(db, photo_id, user):
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
    # X-Accel-Redirect: nginx serves the file directly from the SSD cache volume,
    # bypassing Python I/O in the data path. Backend only handles auth + DB lookup.
    # Falls back to FileResponse if the path isn't under /cache/ (shouldn't happen).
    _cache_prefix = "/cache/"
    if thumb.startswith(_cache_prefix):
        accel_loc = "/internal-cache-immutable/" if served_exact else "/internal-cache-nc/"
        accel_path = accel_loc + thumb[len(_cache_prefix):]
        return Response(headers={"X-Accel-Redirect": accel_path, "Content-Type": "image/jpeg"})
    cache = "public, max-age=31536000, immutable" if served_exact else "no-cache, must-revalidate"
    return FileResponse(thumb, media_type="image/jpeg", headers={"Cache-Control": cache})


@router.get("/{photo_id}/preview")
async def get_video_preview(photo_id: int, db: AsyncSession = Depends(get_db),
                            user: Optional[User] = Depends(current_user_optional)):
    """Animated hover preview clip for a video (webp/gif)."""
    photo = await db.get(Photo, photo_id)
    if not photo or not can_see_photo(photo, user):
        raise HTTPException(404, "Preview not ready")
    if not photo.video_preview_path or not os.path.exists(photo.video_preview_path):
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


@router.get("/{photo_id}/video/variants")
async def video_variants(photo_id: int, db: AsyncSession = Depends(get_db),
                         user: Optional[User] = Depends(current_user_optional)):
    """Liste der verfügbaren Web-Video-Auflösungen. Der Player nutzt sie für den
    Qualitäts-Selector. Fehlt eine, kann sie per POST /transcode angefordert
    werden."""
    photo = await db.get(Photo, photo_id)
    if not photo or not photo.is_video or not can_see_photo(photo, user):
        raise HTTPException(404)
    out = []
    for res in (480, 720, 1080):
        p = pathlib.Path("/cache/videos") / f"{photo_id}_{res}.mp4"
        if p.exists():
            try:
                sz = p.stat().st_size
            except Exception:
                sz = 0
            out.append({"resolution": res, "size_bytes": sz,
                        "url": f"/api/photos/{photo_id}/video/stream?res={res}"})
    # Default-Rendition (das ist die die als „normal" ausgeliefert wird)
    default_res = 720 if any(v["resolution"] == 720 for v in out) else (
                  1080 if any(v["resolution"] == 1080 for v in out) else
                  (out[0]["resolution"] if out else None))
    return {"variants": out, "default": default_res}


@router.get("/{photo_id}/video/stream")
async def stream_video(photo_id: int,
                       res: Optional[int] = None,
                       db: AsyncSession = Depends(get_db),
                       user: Optional[User] = Depends(current_user_optional)):
    """Stream video. `res` wählt die Qualität (480/720/1080). Ohne `res` liefert der
    Server 720p wenn vorhanden (sonst 1080p) — die Version die auf Handys/älteren
    Rechnern flüssig läuft. Fehlt die gewünschte Auflösung: enqueue transcode +
    fallback auf das nächste-höhere/niedrigere vorhandene."""
    photo = await db.get(Photo, photo_id)
    if not photo or not photo.is_video or not can_see_photo(photo, user):
        raise HTTPException(404)

    def _cache_path(r: int) -> pathlib.Path:
        return pathlib.Path("/cache/videos") / f"{photo_id}_{r}.mp4"

    def _serve(path: pathlib.Path):
        mt = "video/mp4"
        s = str(path)
        _cache_prefix = "/cache/"
        if s.startswith(_cache_prefix):
            accel_path = "/internal-video-cache/" + s[len(_cache_prefix):]
            return Response(headers={"X-Accel-Redirect": accel_path, "Content-Type": mt})
        return FileResponse(s, media_type=mt,
                            headers={"Cache-Control": "public, max-age=86400"})

    # 1) explizit gewünschte Auflösung
    if res in (480, 720, 1080):
        p = _cache_path(res)
        if p.exists():
            return _serve(p)
        # nicht da → enqueue + Fallback auf beste vorhandene
        try:
            from app.worker.tasks import transcode_video_task
            transcode_video_task.delay(photo_id, res)
        except Exception:
            pass
        # Fallback in Präferenz-Reihenfolge
        for alt in (720, 1080, 480):
            if alt == res:
                continue
            ap = _cache_path(alt)
            if ap.exists():
                return _serve(ap)

    # 2) Default: 720p bevorzugt (kleiner + garantiert HW-decodable), sonst 1080p
    for r in (720, 1080, 480):
        p = _cache_path(r)
        if p.exists():
            return _serve(p)

    # 3) DB-Fallback (falls video_webm_path an andere Stelle zeigt) + enqueue 720
    web = photo.video_webm_path
    if web and os.path.exists(web):
        try:
            from app.worker.tasks import transcode_video_task
            transcode_video_task.delay(photo_id, 720)
        except Exception:
            pass
        return _serve(pathlib.Path(web))

    # 4) Nichts transkodiert → HW transcode enqueue + Original als Fallback
    try:
        from app.worker.tasks import transcode_video_task
        transcode_video_task.delay(photo_id, 720)
        transcode_video_task.delay(photo_id, 1080)
    except Exception:
        pass
    mime = photo.mime_type or "video/mp4"
    return FileResponse(photo.path, media_type=mime)


@router.post("/{photo_id}/video/transcode")
async def transcode_video(
    photo_id: int,
    resolution: int = 1080,
    db: AsyncSession = Depends(get_db),
    user: Optional[User] = Depends(current_user_optional),
):
    """Queue a hardware-accelerated transcode on the worker. We must NOT run ffmpeg
    inline here: a 600s `subprocess.run` would block the event loop AND hold the DB
    connection idle-in-transaction (asyncpg starvation). The worker does it safely
    with no session held — the player polls /stream until the file appears."""
    photo = await db.get(Photo, photo_id)
    if not photo or not photo.is_video:
        raise HTTPException(404)
    if not can_see_photo(photo, user):
        raise HTTPException(404)
    if not feature_allowed(user, "allow_pipeline"):
        raise HTTPException(403, "Nicht erlaubt")

    out_path = pathlib.Path("/cache/videos") / f"{photo_id}_{resolution}.mp4"
    if out_path.exists():
        if photo.video_webm_path != str(out_path):
            photo.video_webm_path = str(out_path)
            await db.commit()
        return {"status": "already_done", "path": str(out_path)}

    from app.worker.tasks import transcode_video_task
    transcode_video_task.delay(photo_id, resolution)
    return {"status": "queued", "photo_id": photo_id}
