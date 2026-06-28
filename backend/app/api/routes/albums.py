"""Albums API — manual, smart, and AI albums."""
from typing import Optional, Any, List
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
from pydantic import BaseModel

from app.core.database import get_db
from app.core.auth_guard import current_user_optional as _current_user_optional
from app.core.access import photo_conditions as _photo_conditions
from app.models.album import Album, AlbumPhoto, AlbumType
from app.models.photo import Photo, PhotoStatus

router = APIRouter(prefix="/albums", tags=["albums"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class AlbumCreate(BaseModel):
    name: str
    description: Optional[str] = None
    album_type: AlbumType = AlbumType.manual
    smart_criteria: Optional[Any] = None
    ai_prompt: Optional[str] = None

class AlbumUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    cover_photo_id: Optional[int] = None
    smart_criteria: Optional[Any] = None
    ai_prompt: Optional[str] = None
    album_type: Optional[str] = None   # allow converting manual ↔ smart

class AlbumOut(BaseModel):
    id: int
    name: str
    description: Optional[str]
    album_type: str
    cover_photo_id: Optional[int]
    smart_criteria: Optional[Any]
    ai_prompt: Optional[str]
    ai_last_evaluated: Optional[datetime]
    photo_count: int
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}

class AddPhotosRequest(BaseModel):
    photo_ids: List[int]

class ReorderRequest(BaseModel):
    photo_ids: List[int]  # ordered list


def _album_out(album: Album, count: int) -> AlbumOut:
    return AlbumOut(
        id=album.id,
        name=album.name,
        description=album.description,
        album_type=album.album_type.value,
        cover_photo_id=album.cover_photo_id,
        smart_criteria=album.smart_criteria,
        ai_prompt=album.ai_prompt,
        ai_last_evaluated=album.ai_last_evaluated,
        photo_count=count,
        created_at=album.created_at,
        updated_at=album.updated_at,
    )


# ── CRUD ──────────────────────────────────────────────────────────────────────

@router.get("", response_model=List[AlbumOut])
async def list_albums(db: AsyncSession = Depends(get_db),
                      user=Depends(_current_user_optional)):
    from app.core.access import _is_unrestricted
    q = select(Album).order_by(Album.updated_at.desc())
    # A restricted account only sees albums containing at least one photo it may access.
    if not _is_unrestricted(user):
        visible_albums = (select(AlbumPhoto.album_id)
                          .where(AlbumPhoto.photo_id.in_(select(Photo.id).where(*_photo_conditions(user)))))
        q = q.where(Album.id.in_(visible_albums))
    albums = (await db.execute(q)).scalars().all()
    result = []
    for a in albums:
        count = await db.scalar(select(func.count()).where(AlbumPhoto.album_id == a.id))
        result.append(_album_out(a, count or 0))
    return result


@router.post("", response_model=AlbumOut, status_code=201)
async def create_album(body: AlbumCreate, bg: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    album = Album(
        name=body.name,
        description=body.description,
        album_type=body.album_type,
        smart_criteria=body.smart_criteria,
        ai_prompt=body.ai_prompt,
    )
    db.add(album)
    await db.flush()

    if body.album_type == AlbumType.smart:
        await _populate_smart(album, db)
    elif body.album_type == AlbumType.ai:
        bg.add_task(_populate_ai_album_bg, album.id, body.ai_prompt or "")

    await db.commit()
    count = await db.scalar(select(func.count()).where(AlbumPhoto.album_id == album.id))
    return _album_out(album, count or 0)


@router.get("/{album_id}", response_model=AlbumOut)
async def get_album(album_id: int, db: AsyncSession = Depends(get_db),
                    user=Depends(_current_user_optional)):
    from app.core.access import _is_unrestricted
    album = await db.get(Album, album_id)
    if not album:
        raise HTTPException(404)
    if not _is_unrestricted(user):
        visible = await db.scalar(
            select(AlbumPhoto.album_id).where(
                AlbumPhoto.album_id == album_id,
                AlbumPhoto.photo_id.in_(select(Photo.id).where(*_photo_conditions(user)))
            ).limit(1))
        if not visible:
            raise HTTPException(404)
    count = await db.scalar(select(func.count()).where(AlbumPhoto.album_id == album_id))
    return _album_out(album, count or 0)


@router.patch("/{album_id}", response_model=AlbumOut)
async def update_album(album_id: int, body: AlbumUpdate, db: AsyncSession = Depends(get_db)):
    album = await db.get(Album, album_id)
    if not album:
        raise HTTPException(404)
    data = body.model_dump(exclude_none=True)
    criteria_changed = "smart_criteria" in data or "album_type" in data
    for field, val in data.items():
        if field == "album_type":
            try:
                val = AlbumType(val)
            except ValueError:
                continue
        setattr(album, field, val)
    album.updated_at = datetime.now(timezone.utc)
    # If this is (now) a SMART album and the criteria/type were touched, REPOPULATE
    # immediately — otherwise changing the person did nothing (the old bug) and a
    # converted album stayed empty/capped.
    if criteria_changed and album.album_type == AlbumType.smart:
        await _populate_smart(album, db)
    await db.commit()
    count = await db.scalar(select(func.count()).where(AlbumPhoto.album_id == album_id))
    return _album_out(album, count or 0)


@router.delete("/{album_id}", status_code=204)
async def delete_album(album_id: int, db: AsyncSession = Depends(get_db)):
    album = await db.get(Album, album_id)
    if not album:
        raise HTTPException(404)
    await db.delete(album)
    await db.commit()


# ── Photos in album ───────────────────────────────────────────────────────────

@router.get("/{album_id}/photos")
async def album_photos(
    album_id: int,
    page: int = 1,
    limit: int = 50,
    sort: str = "order",   # order | newest | oldest | name
    db: AsyncSession = Depends(get_db),
    user=Depends(_current_user_optional),
):
    album = await db.get(Album, album_id)
    if not album:
        raise HTTPException(404)

    # Respect per-user access restrictions (folder/date/person) — an album
    # must not expose photos a restricted user otherwise can't see.
    acl = _photo_conditions(user)
    _order = {
        "newest": Photo.taken_at.desc().nullslast(),
        "oldest": Photo.taken_at.asc().nullsfirst(),
        "name": Photo.filename.asc(),
    }.get(sort)
    # Stable tiebreaker (Photo.id) so photos sharing a timestamp keep a fixed order
    # across pages — without it offset pagination can re-shuffle equal-date photos.
    order_cols = [_order, Photo.id.desc()] if _order is not None else [AlbumPhoto.sort_order, AlbumPhoto.added_at]
    q = (
        select(Photo)
        .join(AlbumPhoto, AlbumPhoto.photo_id == Photo.id)
        .where(AlbumPhoto.album_id == album_id, *acl)
        .order_by(*order_cols)
        .offset((page - 1) * limit).limit(limit)
    )
    photos = (await db.execute(q)).scalars().all()
    total = await db.scalar(
        select(func.count()).select_from(
            select(Photo.id).join(AlbumPhoto, AlbumPhoto.photo_id == Photo.id)
            .where(AlbumPhoto.album_id == album_id, *acl).subquery()
        )
    )
    # Use the gallery schema (PhotoBase) so serialization is clean — returning
    # raw ORM rows here pulled in the pgvector `embedding` and broke the response,
    # leaving smart albums looking empty despite a correct photo count.
    from app.schemas.photo import PhotoListResponse, PhotoBase
    return PhotoListResponse(
        total=total or 0, page=page, limit=limit,
        items=[PhotoBase.model_validate(p) for p in photos],
    )


@router.post("/{album_id}/photos", status_code=201)
async def add_photos(album_id: int, body: AddPhotosRequest, db: AsyncSession = Depends(get_db)):
    album = await db.get(Album, album_id)
    if not album:
        raise HTTPException(404)
    if album.album_type != AlbumType.manual:
        raise HTTPException(400, "Can only manually add photos to manual albums")

    existing = set(
        (await db.execute(
            select(AlbumPhoto.photo_id).where(AlbumPhoto.album_id == album_id)
        )).scalars().all()
    )
    max_order = await db.scalar(
        select(func.max(AlbumPhoto.sort_order)).where(AlbumPhoto.album_id == album_id)
    ) or 0

    added = 0
    for i, pid in enumerate(body.photo_ids):
        if pid not in existing:
            db.add(AlbumPhoto(album_id=album_id, photo_id=pid, sort_order=max_order + i + 1))
            added += 1

    album.updated_at = datetime.now(timezone.utc)
    if not album.cover_photo_id and body.photo_ids:
        album.cover_photo_id = body.photo_ids[0]

    await db.commit()
    return {"added": added}


@router.delete("/{album_id}/photos/{photo_id}", status_code=204)
async def remove_photo(album_id: int, photo_id: int, db: AsyncSession = Depends(get_db)):
    album = await db.get(Album, album_id)
    if not album or album.album_type != AlbumType.manual:
        raise HTTPException(404)
    await db.execute(
        delete(AlbumPhoto).where(
            AlbumPhoto.album_id == album_id,
            AlbumPhoto.photo_id == photo_id,
        )
    )
    await db.commit()


@router.put("/{album_id}/photos/order")
async def reorder_photos(album_id: int, body: ReorderRequest, db: AsyncSession = Depends(get_db)):
    """Reorder by passing a full ordered list of photo IDs."""
    for order, pid in enumerate(body.photo_ids):
        row = (await db.execute(
            select(AlbumPhoto).where(
                AlbumPhoto.album_id == album_id,
                AlbumPhoto.photo_id == pid,
            )
        )).scalar_one_or_none()
        if row:
            row.sort_order = order
    await db.commit()
    return {"ok": True}


# ── Smart album evaluation ────────────────────────────────────────────────────

async def _populate_smart(album: Album, db: AsyncSession):
    """Fill a smart album from its criteria dict."""
    c = album.smart_criteria or {}
    q = select(Photo).where(
        Photo.status == PhotoStatus.done,
        Photo.is_trashed == False,
    )
    if c.get("date_from"):
        q = q.where(Photo.taken_at >= c["date_from"])
    if c.get("date_to"):
        q = q.where(Photo.taken_at <= c["date_to"])
    if c.get("cameras"):
        from sqlalchemy import or_
        q = q.where(or_(*[Photo.camera_model.ilike(f"%{cam}%") for cam in c["cameras"]]))
    if c.get("media_type") == "video":
        q = q.where(Photo.is_video == True)
    elif c.get("media_type") == "photo":
        q = q.where(Photo.is_video == False)
    if c.get("favorites"):
        q = q.where(Photo.is_favorite == True)
    if c.get("has_gps"):
        q = q.where(Photo.latitude != None)
    if c.get("min_rating"):
        q = q.where(Photo.user_rating >= c["min_rating"])
    if c.get("tags"):
        # Tag-basiertes Smart-Album (z. B. „Haustiere" = Hund/Katze/…). Subquery, damit
        # ein Foto mit mehreren passenden Tags nicht dupliziert wird.
        from app.models.tag import Tag, PhotoTag
        tnames = [str(t).lower() for t in c["tags"]]
        tsub = (select(PhotoTag.photo_id)
                .join(Tag, Tag.id == PhotoTag.tag_id)
                .where(func.lower(Tag.name).in_(tnames)))
        q = q.where(Photo.id.in_(tsub))
    if c.get("person_ids"):
        from app.models.face import Face
        pids = [int(p) for p in c["person_ids"]]
        # Subquery (not a join) so a photo with several matching faces isn't
        # duplicated. person_match: "any" (default) or "all" (must contain
        # every selected person together — e.g. "Fotos von X UND Y").
        if str(c.get("person_match", "any")).lower() == "all" and pids:
            sub = (
                select(Face.photo_id)
                .where(Face.person_id.in_(pids))
                .group_by(Face.photo_id)
                .having(func.count(func.distinct(Face.person_id)) == len(set(pids)))
            )
        else:
            sub = select(Face.photo_id).where(Face.person_id.in_(pids))
        q = q.where(Photo.id.in_(sub))

    # No artificial 500 cap — a person's album should hold ALL their photos.
    photos = (await db.execute(q.order_by(Photo.taken_at.desc().nullslast()).limit(20000))).scalars().all()

    # Clear old entries
    await db.execute(delete(AlbumPhoto).where(AlbumPhoto.album_id == album.id))

    for i, p in enumerate(photos):
        db.add(AlbumPhoto(album_id=album.id, photo_id=p.id, sort_order=i))

    if photos and not album.cover_photo_id:
        album.cover_photo_id = photos[0].id
    album.ai_last_evaluated = datetime.now(timezone.utc)


@router.post("/{album_id}/refresh")
async def refresh_album(album_id: int, bg: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    """Re-evaluate smart or AI album criteria."""
    album = await db.get(Album, album_id)
    if not album:
        raise HTTPException(404)

    if album.album_type == AlbumType.smart:
        await _populate_smart(album, db)
        await db.commit()
        return {"ok": True, "type": "smart"}
    elif album.album_type == AlbumType.ai:
        bg.add_task(_populate_ai_album_bg, album_id, album.ai_prompt or "")
        return {"ok": True, "type": "ai", "status": "queued"}

    raise HTTPException(400, "Only smart and AI albums can be refreshed")


@router.post("/enable-pets")
async def enable_pets_album(db: AsyncSession = Depends(get_db)):
    """Ein-Klick: legt das Smart-Album „Haustiere" an (oder aktualisiert es) — sammelt
    automatisch alle Fotos, die die KI als Tier (Hund/Katze/…) verschlagwortet hat.
    Erbt damit die volle Album-UX (Sortierung, Titelbild, Detail, Teilen)."""
    from app.api.routes.photos import _PET_TAGS
    crit = {"tags": sorted(_PET_TAGS)}
    album = await db.scalar(
        select(Album).where(Album.name == "Haustiere", Album.album_type == AlbumType.smart)
    )
    if not album:
        album = Album(name="Haustiere", description="Automatisch: alle Fotos mit Tieren",
                      album_type=AlbumType.smart, smart_criteria=crit)
        db.add(album)
        await db.flush()
    else:
        album.smart_criteria = crit
    await _populate_smart(album, db)
    await db.commit()
    await db.refresh(album)
    count = await db.scalar(select(func.count()).select_from(AlbumPhoto).where(AlbumPhoto.album_id == album.id))
    return _album_out(album, int(count or 0))


# ── AI album background population ────────────────────────────────────────────

async def _populate_ai_album_bg(album_id: int, prompt: str):
    """Background task: ask AI which photos match the freetext prompt."""
    from app.core.database import _engine
    from sqlalchemy.ext.asyncio import AsyncSession

    async with AsyncSession(_engine) as db:
        album = await db.get(Album, album_id)
        if not album:
            return

        # Semantic + keyword + tag + person search on the freetext prompt.
        from app.services.settings_loader import load_settings
        from app.services.photo_search import search_photos
        s = await load_settings(db)
        photos = await search_photos(db, prompt, s, limit=300)

        await db.execute(delete(AlbumPhoto).where(AlbumPhoto.album_id == album_id))
        for i, p in enumerate(photos):
            db.add(AlbumPhoto(album_id=album_id, photo_id=p.id, sort_order=i, ai_score=1.0))

        if photos and not album.cover_photo_id:
            album.cover_photo_id = photos[0].id
        album.ai_last_evaluated = datetime.now(timezone.utc)
        await db.commit()
