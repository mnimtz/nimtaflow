from typing import List
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.source import PhotoSource
from app.schemas.source import SourceCreate, SourceOut, ScanResult

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
    return source


@router.delete("/{source_id}", status_code=204)
async def delete_source(source_id: int, db: AsyncSession = Depends(get_db)):
    source = await db.get(PhotoSource, source_id)
    if not source:
        raise HTTPException(404)
    await db.delete(source)
    await db.commit()


@router.post("/{source_id}/scan", response_model=ScanResult)
async def trigger_scan(source_id: int, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    source = await db.get(PhotoSource, source_id)
    if not source:
        raise HTTPException(404)

    from app.worker.tasks import scan_source_task
    task = scan_source_task.delay(source_id)

    return ScanResult(task_id=task.id, message="Scan started")
