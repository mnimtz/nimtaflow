from typing import List
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.source import PhotoSource
from app.schemas.source import SourceCreate, SourceUpdate, SourceOut, ScanResult

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("", response_model=List[SourceOut])
async def list_sources(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(PhotoSource).order_by(PhotoSource.id))
    return result.scalars().all()


@router.post("", response_model=SourceOut, status_code=201)
async def create_source(data: SourceCreate, db: AsyncSession = Depends(get_db)):
    source = PhotoSource(**data.model_dump())
    db.add(source)
    await db.commit()
    await db.refresh(source)
    # Auto-scan immediately after adding
    from app.worker.tasks import scan_source_task
    scan_source_task.delay(source.id)
    return source


@router.patch("/{source_id}", response_model=SourceOut)
async def update_source(source_id: int, data: SourceUpdate, db: AsyncSession = Depends(get_db)):
    source = await db.get(PhotoSource, source_id)
    if not source:
        raise HTTPException(404)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(source, key, value)
    await db.commit()
    await db.refresh(source)
    return source


@router.delete("/{source_id}")
async def delete_source(source_id: int, db: AsyncSession = Depends(get_db)):
    """Remove a watched folder AND everything derived from it: photos, cached
    thumbnails/previews, faces, tag links, album entries, and any person that
    is left with no faces — so no dead links remain."""
    from sqlalchemy import delete as sql_delete
    from app.models.photo import Photo
    from app.models.face import Face
    from app.models.person import Person
    from app.models.tag import PhotoTag
    from app.models.album import AlbumPhoto
    import os

    source = await db.get(PhotoSource, source_id)
    if not source:
        raise HTTPException(404)

    prefix = source.path.rstrip("/")
    # Match files directly in the folder or any subfolder, but not sibling
    # folders that merely share a name prefix.
    rows = (await db.execute(
        select(Photo.id, Photo.thumb_small, Photo.thumb_medium, Photo.thumb_large, Photo.video_webm_path)
        .where((Photo.path == prefix) | (Photo.path.startswith(prefix + "/")))
    )).all()
    photo_ids = [r[0] for r in rows]

    removed_files = 0
    for r in rows:
        for cached in (r[1], r[2], r[3], r[4]):
            if cached and os.path.isfile(cached):
                try:
                    os.remove(cached)
                    removed_files += 1
                except OSError:
                    pass

    if photo_ids:
        # children first (FKs), then photos
        await db.execute(sql_delete(Face).where(Face.photo_id.in_(photo_ids)))
        await db.execute(sql_delete(PhotoTag).where(PhotoTag.photo_id.in_(photo_ids)))
        await db.execute(sql_delete(AlbumPhoto).where(AlbumPhoto.photo_id.in_(photo_ids)))
        await db.execute(sql_delete(Photo).where(Photo.id.in_(photo_ids)))

    # Drop persons that no longer have any faces anywhere
    await db.execute(sql_delete(Person).where(
        ~Person.id.in_(select(Face.person_id).where(Face.person_id.isnot(None)))
    ))

    await db.delete(source)
    await db.commit()
    return {"deleted_photos": len(photo_ids), "deleted_files": removed_files}


@router.post("/{source_id}/scan", response_model=ScanResult)
async def trigger_scan(source_id: int, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    source = await db.get(PhotoSource, source_id)
    if not source:
        raise HTTPException(404)

    from app.worker.tasks import scan_source_task
    task = scan_source_task.delay(source_id)

    return ScanResult(task_id=task.id, message="Scan started")
