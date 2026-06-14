from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from datetime import date

from app.core.database import get_db
from app.models.photo import Photo, PhotoStatus
from app.schemas.photo import PhotoListResponse, PhotoDetail

router = APIRouter(prefix="/photos", tags=["photos"])


@router.get("", response_model=PhotoListResponse)
async def list_photos(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    person_id: Optional[int] = None,
    tag: Optional[str] = None,
    search: Optional[str] = None,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    radius_km: Optional[float] = None,
    db: AsyncSession = Depends(get_db),
):
    q = select(Photo).where(Photo.status == PhotoStatus.done)

    if date_from:
        q = q.where(Photo.taken_at >= date_from)
    if date_to:
        q = q.where(Photo.taken_at <= date_to)
    if search:
        q = q.where(Photo.description.ilike(f"%{search}%"))
    if lat and lng and radius_km:
        # Simple bounding box; proper haversine via PostGIS in future
        lat_delta = radius_km / 111.0
        lng_delta = radius_km / (111.0 * abs(lat) ** 0.5 + 0.001)
        q = q.where(
            and_(
                Photo.latitude.between(lat - lat_delta, lat + lat_delta),
                Photo.longitude.between(lng - lng_delta, lng + lng_delta),
            )
        )

    if person_id:
        from app.models.face import Face
        q = q.join(Face, Face.photo_id == Photo.id).where(Face.person_id == person_id)

    total = await db.scalar(select(func.count()).select_from(q.subquery()))
    q = q.order_by(Photo.taken_at.desc().nullslast(), Photo.id.desc())
    q = q.offset((page - 1) * limit).limit(limit)

    photos = (await db.execute(q)).scalars().all()
    return PhotoListResponse(total=total, page=page, limit=limit, items=photos)


@router.get("/{photo_id}", response_model=PhotoDetail)
async def get_photo(photo_id: int, db: AsyncSession = Depends(get_db)):
    photo = await db.get(Photo, photo_id)
    if not photo:
        raise HTTPException(404, "Photo not found")
    return photo


@router.get("/{photo_id}/thumbnail")
async def get_thumbnail(photo_id: int, size: str = "medium", db: AsyncSession = Depends(get_db)):
    photo = await db.get(Photo, photo_id)
    if not photo:
        raise HTTPException(404)
    thumb = getattr(photo, f"thumb_{size}", None) or photo.thumb_medium or photo.thumb_small
    if not thumb:
        raise HTTPException(404, "Thumbnail not generated yet")
    return FileResponse(thumb, media_type="image/jpeg")


@router.get("/{photo_id}/original")
async def get_original(photo_id: int, db: AsyncSession = Depends(get_db)):
    photo = await db.get(Photo, photo_id)
    if not photo:
        raise HTTPException(404)
    import mimetypes
    mime = photo.mime_type or mimetypes.guess_type(photo.path)[0] or "application/octet-stream"
    return FileResponse(photo.path, media_type=mime, filename=photo.filename)
