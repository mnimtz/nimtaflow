"""Highlights API — generate & manage short highlight slideshow videos."""
import os
from typing import Optional, Any, List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Header, Request
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.core.database import get_db
from app.core.auth_guard import current_user_optional
from app.core.access import _is_unrestricted
from app.models.user import User
from app.models.highlight import Highlight, HighlightStatus
from app.services.highlights import MOTTOS

router = APIRouter(prefix="/highlights", tags=["highlights"])

_VALID_MOTTOS = {m["motto"] for m in MOTTOS}
_MOTTO_LABEL = {m["motto"]: m["label"] for m in MOTTOS}


def _default_title(motto: str) -> str:
    """A human title when the client sends none (or just the raw motto). week_review
    gets the current calendar week so it reads 'Highlight der Woche (KW 26)'."""
    if motto == "week_review":
        import datetime
        return f"Highlight der Woche (KW {datetime.datetime.now(datetime.timezone.utc).isocalendar().week})"
    return _MOTTO_LABEL.get(motto, motto)


# ── Schemas ───────────────────────────────────────────────────────────────────

class HighlightCreate(BaseModel):
    motto: str
    title: Optional[str] = None
    duration_sec: float = 60.0
    person_id: Optional[int] = None
    person_id2: Optional[int] = None
    person_ids: Optional[List[int]] = None
    year: Optional[int] = None
    album_id: Optional[int] = None
    season: Optional[str] = None
    month: Optional[int] = None
    ai_clips: Optional[bool] = None       # opt-in: animate top keyframes into film clips (KI-Verschmelzung)
    ai_clip_count: Optional[int] = None   # how many keyframes to animate (1–5)
    music: Optional[bool] = None          # per-video music override (None = use global default)


class HighlightOut(BaseModel):
    id: int
    title: Optional[str]
    motto: str
    status: str
    duration_sec: Optional[float]
    photo_count: Optional[int]
    cover_photo_id: Optional[int]
    params: Optional[Any]
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


def _out(h: Highlight) -> HighlightOut:
    return HighlightOut(
        id=h.id,
        title=h.title,
        motto=h.motto,
        status=h.status.value if hasattr(h.status, "value") else str(h.status),
        duration_sec=h.duration_sec,
        photo_count=h.photo_count,
        cover_photo_id=h.cover_photo_id,
        params=h.params,
        error_message=h.error_message,
        created_at=h.created_at,
        updated_at=h.updated_at,
    )


# ── Endpoints ───────────────────────────────────────────────────────────────────

@router.get("/mottos")
async def list_mottos():
    """The available mottos with German labels and which params each needs,
    so the UI can build the right form."""
    return {"mottos": MOTTOS}


@router.get("/music-library")
async def music_library_status(user: Optional[User] = Depends(current_user_optional)):
    """How many CC0/generated soundtrack tracks are in the library (for the UI)."""
    import glob
    from app.core.config import get_settings
    from app.services.highlights import library_dir
    d = library_dir(get_settings().cache_path)
    files = [os.path.basename(f) for f in glob.glob(os.path.join(d, "*")) if os.path.isfile(f)] if os.path.isdir(d) else []
    return {"count": len(files), "tracks": sorted(files)}


@router.post("/music-library/generate")
async def music_library_generate(user: Optional[User] = Depends(current_user_optional)):
    """Admin: (re)generate the CC0 soundtrack library with the configured model.
    Runs in the background (one track per mood) and costs generation budget."""
    if not _is_unrestricted(user):
        raise HTTPException(403, "Nur Admins dürfen die Musik-Bibliothek erzeugen.")
    from app.worker.tasks import generate_music_library_task
    r = generate_music_library_task.delay()
    return {"queued": True, "task_id": str(r.id)}


@router.get("", response_model=List[HighlightOut])
async def list_highlights(db: AsyncSession = Depends(get_db),
                          user: Optional[User] = Depends(current_user_optional)):
    q = select(Highlight).order_by(Highlight.created_at.desc())
    # Restricted (e.g. demo) users see only highlights they created — never the
    # family's. Admins / unrestricted see all.
    if not _is_unrestricted(user):
        q = q.where(Highlight.created_by == user.id)
    rows = (await db.execute(q)).scalars().all()
    return [_out(h) for h in rows]


def _can_access(h: Highlight, user: Optional[User]) -> bool:
    return _is_unrestricted(user) or (h.created_by is not None and h.created_by == user.id)


@router.post("", response_model=HighlightOut, status_code=201)
async def create_highlight(
    body: HighlightCreate,
    db: AsyncSession = Depends(get_db),
    user: Optional[User] = Depends(current_user_optional),
):
    if body.motto not in _VALID_MOTTOS:
        raise HTTPException(400, f"Unbekanntes Motto: {body.motto}")
    duration = max(8.0, min(900.0, float(body.duration_sec or 60.0)))

    params = {
        "duration_sec": duration,
        "person_id": body.person_id,
        "person_id2": body.person_id2,
        "person_ids": body.person_ids,
        "year": body.year,
        "album_id": body.album_id,
        "season": body.season,
        "month": body.month,
        "ai_clips": body.ai_clips,
        "ai_clip_count": body.ai_clip_count,
        "music": body.music,
    }
    params = {k: v for k, v in params.items() if v is not None}
    params["duration_sec"] = duration

    # Empty title (or the client just echoing the raw motto) → a proper German label.
    title = (body.title or "").strip()
    if not title or title == body.motto:
        title = _default_title(body.motto)

    h = Highlight(
        title=title,
        motto=body.motto,
        duration_sec=duration,
        params=params,
        status=HighlightStatus.pending,
        created_by=getattr(user, "id", None),
    )
    db.add(h)
    await db.commit()
    await db.refresh(h)

    # Enqueue the render (video queue). Import lazily so the web app never needs
    # the worker module graph at import time.
    from app.worker.tasks import render_highlight_task
    render_highlight_task.delay(h.id)

    return _out(h)


class AnimatePhotoRequest(BaseModel):
    photo_id: int
    prompt: Optional[str] = None      # creative scene description ("… durch eine Unterwasserwelt …")


@router.post("/animate-photo", response_model=HighlightOut, status_code=201)
async def animate_photo(
    body: AnimatePhotoRequest,
    db: AsyncSession = Depends(get_db),
    user: Optional[User] = Depends(current_user_optional),
):
    """External video-AI: turn ONE still photo into a short animated clip — optionally with a
    creative scene prompt (place the person in a new world). Opt-in (highlights.ai_enabled)
    + budget-capped in the worker. Returns a pending Highlight."""
    from app.models.photo import Photo
    from app.services.settings_loader import load_settings
    s = await load_settings(db)
    if str(s.get("highlights.ai_enabled", "false")).lower() != "true":
        raise HTTPException(400, "KI-Video ist deaktiviert. Aktiviere es unter Einstellungen → Highlights.")
    photo = await db.get(Photo, body.photo_id)
    if not photo:
        raise HTTPException(404, "Foto nicht gefunden.")

    seconds = float(int(float(s.get("highlights.ai_clip_seconds", "4") or 4)))
    prompt = (body.prompt or "").strip() or None
    h = Highlight(
        title=("KI-Szene" if prompt else "Animiertes Foto"),
        motto="photo_animate",
        duration_sec=seconds,
        params={"photo_id": body.photo_id, "provider": s.get("highlights.ai_provider", "veo"),
                **({"prompt": prompt} if prompt else {})},
        status=HighlightStatus.pending,
        cover_photo_id=body.photo_id,
        created_by=getattr(user, "id", None),
    )
    db.add(h)
    await db.commit()
    await db.refresh(h)

    # Cloud providers (veo/fal) render in the Celery worker. The local M3 provider
    # leaves the job pending — the M3 LTX worker pulls it via /api/remote/video-jobs.
    if str(s.get("highlights.ai_provider", "veo")).lower() != "local":
        from app.worker.tasks import animate_photo_task
        animate_photo_task.delay(h.id)
    return _out(h)


@router.get("/{highlight_id}", response_model=HighlightOut)
async def get_highlight(highlight_id: int, db: AsyncSession = Depends(get_db),
                        user: Optional[User] = Depends(current_user_optional)):
    h = await db.get(Highlight, highlight_id)
    if not h or not _can_access(h, user):
        raise HTTPException(404, "Highlight nicht gefunden")
    return _out(h)


@router.get("/{highlight_id}/video")
async def get_highlight_video(highlight_id: int, request: Request,
                              range: Optional[str] = Header(None),
                              db: AsyncSession = Depends(get_db),
                              user: Optional[User] = Depends(current_user_optional)):
    """HTTP Range-aware stream — iOS AVPlayer needs 206/Accept-Ranges to play an MP4
    (a plain 200 FileResponse just hangs/does nothing). Same pattern as /v1 stream."""
    h = await db.get(Highlight, highlight_id)
    if not h or not _can_access(h, user):
        raise HTTPException(404, "Highlight nicht gefunden")
    if h.status != HighlightStatus.done or not h.file_path or not os.path.exists(h.file_path):
        raise HTTPException(404, "Video noch nicht fertig")
    path = h.file_path
    file_size = os.path.getsize(path)
    if range:
        try:
            br = range.replace("bytes=", "")
            s_str, e_str = br.split("-")
            start = int(s_str) if s_str else 0
            end = int(e_str) if e_str else file_size - 1
        except Exception:
            raise HTTPException(416)
        end = min(end, file_size - 1)
        chunk = end - start + 1

        def iter_range():
            with open(path, "rb") as f:
                f.seek(start)
                remaining = chunk
                while remaining > 0:
                    data = f.read(min(65536, remaining))
                    if not data:
                        break
                    remaining -= len(data)
                    yield data
        return StreamingResponse(iter_range(), status_code=206, media_type="video/mp4",
                                 headers={"Content-Range": f"bytes {start}-{end}/{file_size}",
                                          "Accept-Ranges": "bytes", "Content-Length": str(chunk)})

    def iter_full():
        with open(path, "rb") as f:
            while True:
                data = f.read(65536)
                if not data:
                    break
                yield data
    return StreamingResponse(iter_full(), media_type="video/mp4",
                             headers={"Accept-Ranges": "bytes", "Content-Length": str(file_size)})


@router.delete("/{highlight_id}", status_code=204)
async def delete_highlight(highlight_id: int, db: AsyncSession = Depends(get_db),
                           user: Optional[User] = Depends(current_user_optional)):
    h = await db.get(Highlight, highlight_id)
    if not h or not _can_access(h, user):
        raise HTTPException(404, "Highlight nicht gefunden")
    if h.file_path and os.path.exists(h.file_path):
        try:
            os.remove(h.file_path)
        except OSError:
            pass
    await db.delete(h)
    await db.commit()
    return None
