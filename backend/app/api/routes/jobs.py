from typing import List, Optional
from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
import asyncio
import json

from app.core.database import get_db
from app.models.job import Job, JobLog
from app.schemas.job import JobOut, JobLogOut

router = APIRouter(prefix="/jobs", tags=["jobs"])

# Active WebSocket clients for live updates
_ws_clients: List[WebSocket] = []


@router.get("", response_model=List[JobOut])
async def list_jobs(limit: int = Query(20, ge=1, le=100), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Job).order_by(desc(Job.created_at)).limit(limit))
    return result.scalars().all()


@router.get("/queues")
async def queue_depths():
    """Live Celery queue depths so the UI can show how much work is waiting.
    cpu = scans/thumbnails (parallel), gpu = AI/faces (single-slot)."""
    from app.core.config import get_settings
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(get_settings().redis_url)
        out = {q: int(await r.llen(q)) for q in ("cpu", "gpu", "celery")}
        await r.aclose()
        return out
    except Exception as e:
        return {"error": str(e)[:120], "cpu": None, "gpu": None, "celery": None}


@router.get("/{job_id}", response_model=JobOut)
async def get_job(job_id: int, db: AsyncSession = Depends(get_db)):
    job = await db.get(Job, job_id)
    if not job:
        from fastapi import HTTPException
        raise HTTPException(404)
    return job


@router.get("/{job_id}/logs", response_model=List[JobLogOut])
async def get_job_logs(
    job_id: int,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    level: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    q = select(JobLog).where(JobLog.job_id == job_id)
    if level:
        q = q.where(JobLog.level == level.upper())
    q = q.order_by(JobLog.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(q)
    return result.scalars().all()


@router.websocket("/ws")
async def job_ws(websocket: WebSocket):
    await websocket.accept()
    _ws_clients.append(websocket)
    try:
        while True:
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        _ws_clients.remove(websocket)


async def broadcast_job_update(data: dict):
    dead = []
    for ws in _ws_clients:
        try:
            await ws.send_text(json.dumps(data))
        except Exception:
            dead.append(ws)
    for ws in dead:
        _ws_clients.remove(ws)
