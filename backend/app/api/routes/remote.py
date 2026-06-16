"""Remote worker API — let an external GPU box pull AI jobs over HTTP.

Generic + storage-free by design: a worker only ever receives a JPEG and returns
JSON (description/tags/embedding/faces), so it needs no DB, no filesystem and no
shared storage. Anyone can run the agent in their own environment. Auth is a
single shared token (Settings → Remote-Worker), separate from user login — so
these routes are mounted WITHOUT the normal auth guard.
"""
import time
import math
from datetime import datetime, timezone, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Header
from fastapi.responses import FileResponse
import os
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, func, delete as sql_delete
from pydantic import BaseModel

from app.core.database import get_db
from app.models.photo import Photo
from app.services.settings_loader import load_settings

router = APIRouter(prefix="/remote", tags=["remote"])

CLAIM_TTL = 300       # s before a claimed-but-unfinished photo is reclaimable
HEARTBEAT_TTL = 120   # s a worker is considered "alive" after its last claim


async def _redis():
    import redis.asyncio as aioredis
    from app.core.config import get_settings
    return aioredis.from_url(get_settings().redis_url)


async def remote_worker_alive() -> int:
    """How many remote workers checked in within HEARTBEAT_TTL (keys auto-expire)."""
    try:
        r = await _redis()
        keys = await r.keys("remote:worker:*")
        await r.aclose()
        return len(keys)
    except Exception:
        return 0


async def _require_token(db: AsyncSession, token: Optional[str]) -> dict:
    s = await load_settings(db)
    if str(s.get("remote.enabled", "false")).lower() != "true":
        raise HTTPException(403, "Remote-Worker ist deaktiviert")
    want = (s.get("remote.token") or "").strip()
    if not want or (token or "") != want:
        raise HTTPException(401, "Ungültiges Remote-Token")
    return s


class ClaimReq(BaseModel):
    worker: str = "worker"


@router.post("/claim")
async def claim(body: ClaimReq, db: AsyncSession = Depends(get_db),
                x_remote_token: Optional[str] = Header(None)):
    """Heartbeat + lease the oldest photo still needing AI."""
    s = await _require_token(db, x_remote_token)
    try:
        r = await _redis()
        await r.set(f"remote:worker:{body.worker}", str(int(time.time())), ex=HEARTBEAT_TTL)
        await r.aclose()
    except Exception:
        pass

    include_videos = str(s.get("remote.include_videos", "true")).lower() != "false"
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=CLAIM_TTL)
    conds = [
        Photo.description.is_(None),
        Photo.ai_error == False,                           # noqa: E712
        Photo.thumb_large.isnot(None),                     # need a displayable JPEG/frame
        or_(Photo.ai_claimed_at.is_(None), Photo.ai_claimed_at < cutoff),
    ]
    if not include_videos:
        conds.insert(0, Photo.is_video == False)           # noqa: E712
    photo = (await db.execute(select(Photo).where(*conds).order_by(Photo.id).limit(1))).scalars().first()
    if not photo:
        return {"photo_id": None}
    photo.ai_claimed_at = datetime.now(timezone.utc)
    await db.commit()
    # The remote worker can run a heavier model than the local host is capable
    # of: prefer `remote.model` (Settings → Remote-Worker). For videos the agent
    # describes the extracted frame (thumb_large).
    model = (s.get("remote.model") or "").strip() or s.get("ai.local.model", "florence2-base")
    prompt_key = "ai.prompt.video" if photo.is_video else "ai.prompt.image"
    return {
        "photo_id": photo.id,
        "is_video": bool(photo.is_video),
        "image_url": f"/api/remote/image/{photo.id}",
        "language": s.get("ai.language", "de"),
        "prompt": s.get(prompt_key) or None,
        "model": model,
        "face_engine": str(s.get("face.engine", "insightface")).lower(),
        "faces_enabled": str(s.get("faces.enabled", "true")).lower() != "false" and not photo.is_video,
    }


@router.get("/image/{photo_id}")
async def image(photo_id: int, db: AsyncSession = Depends(get_db),
                x_remote_token: Optional[str] = Header(None)):
    await _require_token(db, x_remote_token)
    photo = await db.get(Photo, photo_id)
    if not photo:
        raise HTTPException(404)
    thumb = photo.thumb_large or photo.thumb_medium or photo.thumb_small
    if not thumb or not os.path.exists(thumb):
        raise HTTPException(404, "Kein Bild verfügbar")
    return FileResponse(thumb, media_type="image/jpeg")


class FaceIn(BaseModel):
    bbox_x: float
    bbox_y: float
    bbox_w: float
    bbox_h: float
    confidence: float = 0.9
    embedding: Optional[List[float]] = None


class ResultIn(BaseModel):
    description: Optional[str] = None
    tags: List[str] = []
    embedding: Optional[List[float]] = None
    faces: List[FaceIn] = []
    provider: str = "remote"
    error: Optional[str] = None


@router.post("/result/{photo_id}")
async def result(photo_id: int, body: ResultIn, db: AsyncSession = Depends(get_db),
                 x_remote_token: Optional[str] = Header(None)):
    """Write back what the remote worker computed (mirrors the local ai_photo step)."""
    await _require_token(db, x_remote_token)
    from app.models.tag import Tag, PhotoTag
    from app.models.face import Face
    from app.services.feature_log import log as flog

    photo = await db.get(Photo, photo_id)
    if not photo:
        raise HTTPException(404)

    if body.error and not body.description:
        photo.ai_error = True
        photo.ai_claimed_at = None
        await db.commit()
        flog("ai", "WARNING", f"Remote-Fehler ({body.provider}): {photo.filename}: {body.error[:160]}")
        return {"ok": True, "stored": "error"}

    if body.description:
        photo.description = body.description
        photo.description_model = (body.provider or "remote")[:120]
        flog("ai", "INFO", f"Beschreibung ({body.provider}): {photo.filename} — {body.description}")

    # tags (replace previous AI tags)
    if body.tags:
        await db.execute(sql_delete(PhotoTag).where(PhotoTag.photo_id == photo_id, PhotoTag.source == "ai"))
        for name in [t.strip()[:120] for t in body.tags[:20] if t.strip()]:
            tag = await db.scalar(select(Tag).where(Tag.name == name))
            if not tag:
                from sqlalchemy.exc import IntegrityError
                try:
                    async with db.begin_nested():
                        tag = Tag(name=name); db.add(tag); await db.flush()
                except IntegrityError:
                    tag = await db.scalar(select(Tag).where(Tag.name == name))
            if tag and not await db.scalar(select(PhotoTag).where(PhotoTag.photo_id == photo_id, PhotoTag.tag_id == tag.id)):
                db.add(PhotoTag(photo_id=photo_id, tag_id=tag.id, source="ai"))

    # embedding (fit pgvector 768)
    if body.embedding:
        emb = body.embedding
        if len(emb) > 768:
            emb = emb[:768]
            n = math.sqrt(sum(x * x for x in emb)) or 1.0
            emb = [x / n for x in emb]
        if len(emb) == 768:
            photo.embedding = emb

    # faces (only if none yet — don't wipe existing person links)
    if body.faces:
        existing = await db.scalar(select(func.count()).where(Face.photo_id == photo_id))
        if not existing:
            for f in body.faces:
                db.add(Face(
                    photo_id=photo_id, bbox_x=f.bbox_x, bbox_y=f.bbox_y, bbox_w=f.bbox_w, bbox_h=f.bbox_h,
                    confidence=f.confidence, embedding=f.embedding, detector="insightface",
                ))
            cxs = [f.bbox_x + f.bbox_w / 2 for f in body.faces]
            cys = [f.bbox_y + f.bbox_h / 2 for f in body.faces]
            photo.focus_x = min(1.0, max(0.0, sum(cxs) / len(cxs)))
            photo.focus_y = min(1.0, max(0.0, sum(cys) / len(cys)))
            flog("faces", "INFO", f"{len(body.faces)} Gesicht(er) (remote): {photo.filename}")

    photo.ai_claimed_at = None
    photo.processed_at = datetime.now(timezone.utc)
    await db.commit()
    return {"ok": True}


@router.get("/status")
async def status(db: AsyncSession = Depends(get_db)):
    """For the Settings UI: enabled flag, alive worker count, pending AI count.
    (Mounted behind the normal auth guard via the router include — see main.py.)"""
    s = await load_settings(db)
    pending = await db.scalar(
        select(func.count()).where(
            Photo.description.is_(None), Photo.ai_error == False,  # noqa: E712
            Photo.thumb_large.isnot(None),
        )
    )
    workers = []
    try:
        r = await _redis()
        for k in await r.keys("remote:worker:*"):
            ts = await r.get(k)
            name = k.decode().split(":")[-1] if isinstance(k, bytes) else str(k).split(":")[-1]
            workers.append({"name": name, "last_seen": int(ts) if ts else 0})
        await r.aclose()
    except Exception:
        pass
    return {
        "enabled": str(s.get("remote.enabled", "false")).lower() == "true",
        "has_token": bool((s.get("remote.token") or "").strip()),
        "pending": pending or 0,
        "workers": workers,
    }
