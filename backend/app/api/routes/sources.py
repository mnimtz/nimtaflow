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


@router.get("/counts")
async def source_counts(db: AsyncSession = Depends(get_db)):
    """Per-source indexed counts (images / videos / missing) so the user can see at
    a glance how much each folder contributed and spot mounting problems."""
    from app.models.photo import Photo
    from sqlalchemy import func, or_
    result = await db.execute(select(PhotoSource).order_by(PhotoSource.id))
    out = []
    for s in result.scalars().all():
        prefix = (s.path or "").rstrip("/")
        cond = or_(Photo.path == prefix, Photo.path.like(prefix + "/%"))
        row = (await db.execute(select(
            func.count().filter(Photo.is_video == False),   # noqa: E712
            func.count().filter(Photo.is_video == True),     # noqa: E712
            func.count().filter(Photo.is_missing == True),   # noqa: E712
        ).where(cond))).one()
        out.append({"id": s.id, "path": s.path,
                    "images": int(row[0] or 0), "videos": int(row[1] or 0),
                    "missing": int(row[2] or 0)})
    return out


@router.get("/scan-progress")
async def scan_progress(db: AsyncSession = Depends(get_db)):
    """Live scan progress per source (published to Redis by scan_source during a
    long-running scan), plus a grand total of files found vs. scanned across all
    sources — so the UI can show "X / Y gescannt" during the initial library scan."""
    import json
    from app.core.config import get_settings
    result = await db.execute(select(PhotoSource).order_by(PhotoSource.id))
    sources = result.scalars().all()
    per_source = []
    grand_total = grand_scanned = 0
    any_running = False
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(get_settings().redis_url)
        try:
            for s in sources:
                raw = await r.get(f"scan:progress:{s.id}")
                prog = json.loads(raw) if raw else None
                per_source.append({"id": s.id, "name": s.name, "path": s.path,
                                   "progress": prog})
                if prog:
                    grand_total += int(prog.get("total") or 0)
                    grand_scanned += int(prog.get("scanned") or 0)
                    any_running = any_running or bool(prog.get("running"))
        finally:
            await r.aclose()
    except Exception:
        per_source = [{"id": s.id, "name": s.name, "path": s.path, "progress": None}
                      for s in sources]
    return {"sources": per_source, "total": grand_total,
            "scanned": grand_scanned, "running": any_running}


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


@router.post("/{source_id}/reprocess")
async def reprocess_source(source_id: int, redo_faces: bool = False, db: AsyncSession = Depends(get_db)):
    """Re-run thumbnails + AI (and optionally re-detect faces) for all photos
    of a source — 'erneut ausführen' on folder level."""
    from app.models.photo import Photo
    from app.worker.tasks import process_photo_task
    source = await db.get(PhotoSource, source_id)
    if not source:
        raise HTTPException(404)
    prefix = source.path.rstrip("/")
    rows = (await db.execute(
        select(Photo.id).where((Photo.path == prefix) | (Photo.path.startswith(prefix + "/")))
    )).all()
    ids = [r[0] for r in rows]
    for pid in ids:
        # reprocess always forces fresh thumbnails — overwrites any stale cached
        # crop (e.g. old ffmpeg-tile HEIC thumbnails) instead of short-circuiting.
        process_photo_task.delay(pid, None, redo_faces, True)
    return {"reprocessing": len(ids), "redo_faces": redo_faces}


@router.post("/scan-all")
async def scan_all(db: AsyncSession = Depends(get_db)):
    """Trigger a scan for every enabled source."""
    from app.worker.tasks import scan_source_task
    rows = (await db.execute(select(PhotoSource.id).where(PhotoSource.enabled == True))).all()  # noqa: E712
    ids = [r[0] for r in rows]
    for sid in ids:
        scan_source_task.delay(sid)
    return {"scanning": ids}


@router.post("/verify")
async def verify_library(delete: bool = True, db: AsyncSession = Depends(get_db)):
    """Check every indexed photo against the filesystem. Entries whose original
    file no longer exists are removed (with their thumbnails/previews/faces) when
    delete=true, otherwise just flagged is_missing. Cleans up dead links left by
    deleted files or whole removed folders."""
    from sqlalchemy import delete as sql_delete, update as sql_update
    from app.models.photo import Photo
    from app.models.face import Face
    from app.models.person import Person
    from app.models.tag import PhotoTag
    from app.models.album import AlbumPhoto
    from datetime import datetime, timezone
    import os

    # Roots of all enabled sources — a photo is only valid if it lives under one.
    src_rows = (await db.execute(select(PhotoSource.path).where(PhotoSource.enabled == True))).all()  # noqa: E712
    roots = [s[0].rstrip("/") for s in src_rows]

    def _under_a_source(p: str) -> bool:
        return any(p == root or p.startswith(root + "/") for root in roots)

    rows = (await db.execute(
        select(Photo.id, Photo.path, Photo.thumb_small, Photo.thumb_medium,
               Photo.thumb_large, Photo.video_preview_path)
    )).all()

    checked = len(rows)
    missing_ids: list[int] = []
    removed_files = 0
    for r in rows:
        # orphaned = file gone from disk OR no longer under any watched source
        if not os.path.exists(r[1]) or not _under_a_source(r[1]):
            missing_ids.append(r[0])
            if delete:
                for cached in (r[2], r[3], r[4], r[5]):
                    if cached and os.path.isfile(cached):
                        try:
                            os.remove(cached); removed_files += 1
                        except OSError:
                            pass

    def _chunks(seq, n=400):
        for i in range(0, len(seq), n):
            yield seq[i:i + n]

    if missing_ids and delete:
        for chunk in _chunks(missing_ids):
            await db.execute(sql_delete(Face).where(Face.photo_id.in_(chunk)))
            await db.execute(sql_delete(PhotoTag).where(PhotoTag.photo_id.in_(chunk)))
            await db.execute(sql_delete(AlbumPhoto).where(AlbumPhoto.photo_id.in_(chunk)))
            await db.execute(sql_delete(Photo).where(Photo.id.in_(chunk)))
        await db.execute(sql_delete(Person).where(
            ~Person.id.in_(select(Face.person_id).where(Face.person_id.isnot(None)))
        ))
    elif missing_ids:
        for chunk in _chunks(missing_ids):
            await db.execute(sql_update(Photo).where(Photo.id.in_(chunk)).values(
                is_missing=True, missing_at=datetime.now(timezone.utc)))

    await db.commit()
    return {"checked": checked, "missing": len(missing_ids),
            "removed_photos": len(missing_ids) if delete else 0,
            "removed_files": removed_files, "deleted": delete}


@router.post("/{source_id}/scan", response_model=ScanResult)
async def trigger_scan(source_id: int, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    source = await db.get(PhotoSource, source_id)
    if not source:
        raise HTTPException(404)

    from app.worker.tasks import scan_source_task
    task = scan_source_task.delay(source_id)

    return ScanResult(task_id=task.id, message="Scan started")
