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

from fastapi import APIRouter, Depends, HTTPException, Header, UploadFile, File, Request, Query
from fastapi.responses import FileResponse, PlainTextResponse
import os
import pathlib
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_, func, delete as sql_delete
from pydantic import BaseModel

from app.core.database import get_db
from app.models.photo import Photo, PhotoStatus
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
    # "all" = describe+faces | "faces" = faces-only | "describe" = describe-only
    # (no faces) | "embed" = compute jina image/text vectors only.
    mode: str = "all"
    # Restrict a worker to one media type so machines can specialise: a Mac on
    # images ("images"), the M5 on video ("videos"), or "both" (default).
    media: str = "both"


# ── Remote MUSIC worker (e.g. M3 running stable-audio-open) ───────────────────
async def music_worker_alive() -> int:
    """How many music workers checked in within HEARTBEAT_TTL."""
    try:
        r = await _redis()
        keys = await r.keys("remote:musicworker:*")
        await r.aclose()
        return len(keys)
    except Exception:
        return 0


@router.post("/music-claim")
async def music_claim(body: ClaimReq, db: AsyncSession = Depends(get_db),
                      x_remote_token: Optional[str] = Header(None)):
    """Heartbeat + lease the oldest pending music job (prompt → audio)."""
    await _require_token(db, x_remote_token)
    try:
        r = await _redis()
        await r.set(f"remote:musicworker:{body.worker}", str(int(time.time())), ex=HEARTBEAT_TTL)
        await r.aclose()
    except Exception:
        pass
    from app.models.music_job import MusicJob, MusicJobStatus
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=CLAIM_TTL)
    job = (await db.execute(
        select(MusicJob).where(or_(
            MusicJob.status == MusicJobStatus.pending,
            and_(MusicJob.status == MusicJobStatus.claimed, MusicJob.claimed_at < cutoff),
        )).order_by(MusicJob.id).limit(1).with_for_update(skip_locked=True)
    )).scalars().first()
    if not job:
        return {"job_id": None}
    job.status = MusicJobStatus.claimed
    job.claimed_at = datetime.now(timezone.utc)
    job.worker = (body.worker or "worker")[:80]
    await db.commit()
    return {"job_id": job.id, "prompt": job.prompt, "seconds": job.seconds}


@router.post("/music-result/{job_id}")
async def music_result(job_id: int, file: Optional[UploadFile] = File(None),
                       x_music_error: Optional[str] = Header(None),
                       db: AsyncSession = Depends(get_db),
                       x_remote_token: Optional[str] = Header(None)):
    """Store the generated track (or record an error) for a claimed music job."""
    await _require_token(db, x_remote_token)
    from app.models.music_job import MusicJob, MusicJobStatus
    from app.services.feature_log import log as flog
    job = await db.get(MusicJob, job_id)
    if not job:
        raise HTTPException(404)
    if x_music_error and not file:
        job.status = MusicJobStatus.error
        job.error = x_music_error[:500]
        job.done_at = datetime.now(timezone.utc)
        await db.commit()
        flog("highlights", "WARNING", f"Remote-Musik #{job_id} fehlgeschlagen: {x_music_error[:160]}")
        return {"ok": True, "stored": "error"}
    if not file:
        raise HTTPException(400, "Keine Audiodatei")
    data = await file.read()
    from app.core.config import get_settings
    d = os.path.join(get_settings().cache_path, "music", "remote")
    os.makedirs(d, exist_ok=True)
    ext = ".wav"
    fn = (file.filename or "").lower()
    if fn.endswith(".mp3"):
        ext = ".mp3"
    path = os.path.join(d, f"{job_id}{ext}")
    with open(path, "wb") as fh:
        fh.write(data)
    job.status = MusicJobStatus.done
    job.result_path = path
    job.done_at = datetime.now(timezone.utc)
    await db.commit()
    flog("highlights", "INFO", f"Remote-Musik #{job_id} fertig ({len(data)//1024} KB, {job.worker})")
    return {"ok": True, "stored": "done"}


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

    from sqlalchemy import and_, exists
    from app.models.face import Face
    from app.services.ai.manager import build_video_settings
    include_videos = str(s.get("remote.include_videos", "true")).lower() != "false"
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=CLAIM_TTL)
    not_claimed = or_(Photo.ai_claimed_at.is_(None), Photo.ai_claimed_at < cutoff)

    # The remote agent runs the LOCAL VLM, so it only DESCRIBES media whose
    # provider is 'local'. Images set to Gemini/OpenAI/Ollama are described on the
    # server; the remote still does their FACES (below), so every face uses the
    # same insightface engine and clustering stays consistent.
    _mode = (body.mode or "all").strip().lower()
    faces_mode = _mode == "faces"        # only sweeps faces (e.g. the Asus GPU box)
    describe_mode = _mode == "describe"  # only describes, never faces (e.g. a Mac/Ollama worker)
    embed_mode = _mode == "embed"        # only computes jina image/text vectors
    # Media restriction so a worker can specialise: M3 = images, M5 = videos.
    _media = (body.media or "both").strip().lower()
    media_conds = []
    if _media == "images":
        media_conds = [Photo.is_video == False]  # noqa: E712
    elif _media == "videos":
        media_conds = [Photo.is_video == True]   # noqa: E712

    image_provider = (s.get("ai.provider") or "none").strip()
    video_provider = (build_video_settings(s).get("ai.provider") or "none").strip()
    desc_scope = []
    if image_provider == "local":
        desc_scope.append(Photo.is_video == False)  # noqa: E712
    if video_provider == "local" and include_videos:
        desc_scope.append(Photo.is_video == True)   # noqa: E712
    where_terms = []

    if embed_mode:
        # jina vectors: need the IMAGE vector (embedding NULL) OR the description
        # TEXT vector (embedding_text NULL, once a description exists). No describe
        # lease — skip_locked already serialises concurrent embed workers.
        where_terms.append(and_(
            Photo.thumb_large.isnot(None), Photo.is_trashed == False,  # noqa: E712
            Photo.is_missing == False,                                 # noqa: E712
            or_(Photo.embedding.is_(None),
                and_(Photo.embedding_text.is_(None), Photo.description.isnot(None))),
            *media_conds,
        ))
    else:
        # describe term — a faces-only worker NEVER describes.
        if desc_scope and not faces_mode:
            # Source gating per type: images need a thumbnail to send; videos need
            # the pre-transcoded 1080p web MP4 (the native-video worker downloads it).
            src_ok = or_(
                and_(Photo.is_video == False, Photo.thumb_large.isnot(None)),   # noqa: E712
                and_(Photo.is_video == True, Photo.video_webm_path.isnot(None)),  # noqa: E712
            )
            where_terms.append(and_(
                Photo.description.is_(None), Photo.ai_error == False,  # noqa: E712
                src_ok, not_claimed, or_(*desc_scope), *media_conds,
            ))
        # Images still lacking a face pass. A faces-only worker takes ANY such image;
        # the "all" worker only does the faces-only pass for ALREADY-DESCRIBED images
        # so it doesn't steal fresh descriptions from itself. faces_scanned stops re-claims.
        faces_enabled = str(s.get("faces.enabled", "true")).lower() != "false"
        faces_on_import = str(s.get("scan.faces_on_import", "true")).lower() != "false"
        if faces_enabled and (faces_on_import or faces_mode) and not describe_mode:
            no_faces = ~exists().where(Face.photo_id == Photo.id)
            face_terms = [Photo.thumb_large.isnot(None), Photo.is_video == False,  # noqa: E712
                          Photo.faces_scanned == False, no_faces, not_claimed]  # noqa: E712
            if not faces_mode:
                face_terms.insert(0, Photo.description.isnot(None))
            where_terms.append(and_(*face_terms))
    if not where_terms:
        return {"photo_id": None}
    where_any = or_(*where_terms)
    # Row-lock + skip_locked so two workers polling at once lease DIFFERENT photos.
    photo = (await db.execute(
        select(Photo).where(where_any).order_by(Photo.id).limit(1).with_for_update(skip_locked=True)
    )).scalars().first()
    if not photo:
        return {"photo_id": None}
    # faces-only when the worker is a faces worker, or the photo already has a
    # description (imported/Gemini) and only needs its face pass.
    faces_only = faces_mode or (photo.description is not None)
    # Embed workers don't take the describe lease (they don't describe) — just
    # release the row lock so another worker can describe/face it meanwhile.
    if not embed_mode:
        photo.ai_claimed_at = datetime.now(timezone.utc)
    await db.commit()
    if embed_mode:
        return {
            "photo_id": photo.id, "mode": "embed",
            "is_video": bool(photo.is_video),
            "image_url": f"/api/remote/image/{photo.id}",
            # the agent computes the text vector from this (None → only image vector)
            "description": photo.description or None,
            "need_image": photo.embedding is None,
            "need_text": photo.embedding_text is None and bool(photo.description),
        }
    # The remote worker can run a heavier model than the local host is capable
    # of: prefer `remote.model` (Settings → Remote-Worker). For videos the agent
    # describes the extracted frame (thumb_large).
    model = (s.get("remote.model") or "").strip() or s.get("ai.local.model", "florence2-base")
    prompt_key = "ai.prompt.video" if photo.is_video else "ai.prompt.image"
    # For videos: hand the worker several frames evenly spread across the whole
    # duration (adaptive count) instead of a single 10%-mark frame, so Qwen sees
    # the whole video. Qwen-only (Florence can't do multi-frame) — others fall
    # back to the single image_url.
    frame_urls = []
    if photo.is_video and str(model).startswith("qwen"):
        from app.services.processing.thumbnails import video_frame_plan
        n = video_frame_plan(photo.duration_seconds)
        if n > 1:
            frame_urls = [f"/api/remote/frame/{photo.id}/{i}" for i in range(n)]

    # Video face recognition (opt-in: Settings → Video-AI). Sample MORE frames
    # than for the description — evenly across the whole clip — and let the agent
    # detect + dedup faces. video.max_frames caps the count.
    faces_for_image = str(s.get("faces.enabled", "true")).lower() != "false"
    video_faces = str(s.get("video.face_recognition", "false")).lower() == "true"
    face_frames = []  # [{url, t}] — t = the frame's timestamp so the crop can use it
    if photo.is_video and video_faces:
        nf = max(4, min(60, int(float(s.get("video.max_frames", "15") or 15))))
        dur = photo.duration_seconds or 0
        for i in range(nf):
            t = round((i + 0.5) * dur / nf, 2) if dur else 0
            face_frames.append({"url": f"/api/remote/frame/{photo.id}/{i}?n={nf}", "t": t})

    return {
        "photo_id": photo.id,
        "is_video": bool(photo.is_video),
        "faces_only": faces_only,
        "image_url": f"/api/remote/image/{photo.id}",
        # Native-video worker (Qwen3-VL/MLX): the pre-transcoded 1080p web MP4 is
        # the AI source (player + AI share it). duration drives adaptive frame
        # sampling on the worker. Non-video → null.
        "video_url": (f"/api/remote/video/{photo.id}" if photo.is_video else None),
        "duration": photo.duration_seconds,
        "frame_urls": frame_urls,
        "face_frames": face_frames,
        "language": s.get("ai.language", "de"),
        "prompt": s.get(prompt_key) or None,
        "tag_prompt": (s.get("ai.prompt.tags") or "").strip() or None,
        "model": model,
        "face_engine": str(s.get("face.engine", "insightface")).lower(),
        "faces_enabled": (faces_for_image and not photo.is_video) or (photo.is_video and video_faces),
        "min_face_px": float(s.get("face.min_size_px", "40") or 0),
        # Photos: 0.7 (clear faces, rejects walls). Video: lower (0.6) — sampled
        # frames are blurrier/lower-res so det_scores run lower; 0.7 dropped them all.
        "min_conf": (float(s.get("video.face_min_confidence", "0.65") or 0.65) if photo.is_video
                     else float(s.get("face.min_confidence", "0.7") or 0.7)),
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


@router.get("/video/{photo_id}")
async def video(photo_id: int, db: AsyncSession = Depends(get_db),
                x_remote_token: Optional[str] = Header(None)):
    """Serve the pre-transcoded 1080p web MP4 for native-video AI (Qwen3-VL/MLX).
    The same small file the player streams — far cheaper than shipping the 4K
    original. 404 (→ worker skips) until the transcode has produced it."""
    await _require_token(db, x_remote_token)
    photo = await db.get(Photo, photo_id)
    if not photo or not photo.is_video:
        raise HTTPException(404)
    wp = photo.video_webm_path
    if not wp or not os.path.exists(wp):
        raise HTTPException(404, "Kein transkodiertes Video verfügbar")
    return FileResponse(wp, media_type="video/mp4")


# ── Remote 1080p transcoding (Asus NVENC) ───────────────────────────────────────
# Offloads the web-MP4 backlog to a remote GPU worker. Coordinates with the local
# QSV worker via the SAME per-photo Redis lock (transcode:lock:{id}, NX) so the two
# never transcode the same file.

@router.get("/transcode-jobs")
async def transcode_jobs(limit: int = 2, db: AsyncSession = Depends(get_db),
                         x_remote_token: Optional[str] = Header(None)):
    """Lease up to `limit` videos that still lack a 1080p web transcode."""
    await _require_token(db, x_remote_token)
    n = max(1, min(limit, 4))
    rows = (await db.execute(
        select(Photo.id, Photo.path).where(
            Photo.is_video == True, Photo.is_trashed == False, Photo.is_missing == False,  # noqa: E712
            Photo.video_webm_path.is_(None), Photo.status != PhotoStatus.error,
        ).order_by(Photo.id.desc()).limit(n * 6)
    )).all()
    jobs = []
    try:
        r = await _redis()
        for pid, path in rows:
            if not path or not os.path.exists(path):
                continue
            if await r.set(f"transcode:lock:{pid}", "remote", nx=True, ex=1800):
                jobs.append({"photo_id": pid, "resolution": 1080})
                if len(jobs) >= n:
                    break
        await r.aclose()
    except Exception:
        pass
    return {"jobs": jobs}


@router.get("/transcode-source/{photo_id}")
async def transcode_source(photo_id: int, db: AsyncSession = Depends(get_db),
                           x_remote_token: Optional[str] = Header(None)):
    """Stream the ORIGINAL source video for the remote worker to transcode."""
    await _require_token(db, x_remote_token)
    photo = await db.get(Photo, photo_id)
    if not photo or not photo.is_video or not photo.path or not os.path.exists(photo.path):
        raise HTTPException(404)
    return FileResponse(photo.path, media_type="video/mp4")


@router.post("/transcode-result/{photo_id}")
async def transcode_result(photo_id: int, resolution: int = 1080,
                           file: UploadFile = File(...),
                           db: AsyncSession = Depends(get_db),
                           x_remote_token: Optional[str] = Header(None)):
    """Store a remote-transcoded web MP4 (validated via ffprobe) + release the lock."""
    await _require_token(db, x_remote_token)
    photo = await db.get(Photo, photo_id)
    if not photo or not photo.is_video:
        raise HTTPException(404)
    import subprocess, pathlib
    from app.core.config import get_settings
    out_dir = pathlib.Path(get_settings().cache_path) / "videos"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{photo_id}_{resolution}.mp4"
    tmp_path = out_dir / f"{photo_id}_{resolution}.remote.part.mp4"
    with open(tmp_path, "wb") as fh:
        while chunk := await file.read(1 << 20):
            fh.write(chunk)
    ok = False
    try:
        pr = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                             "-of", "default=nw=1:nk=1", str(tmp_path)],
                            capture_output=True, timeout=60)
        d = pr.stdout.decode().strip()
        ok = pr.returncode == 0 and d not in ("", "N/A") and float(d) > 0
    except Exception:
        ok = False
    if not ok:
        try: os.unlink(tmp_path)
        except Exception: pass
        raise HTTPException(400, "Ungültiges Transcode-Ergebnis")
    os.replace(str(tmp_path), str(out_path))
    photo.video_webm_path = str(out_path)
    await db.commit()
    try:
        r = await _redis(); await r.delete(f"transcode:lock:{photo_id}"); await r.aclose()
    except Exception:
        pass
    return {"ok": True}


@router.post("/video-broken/{photo_id}")
async def video_broken(photo_id: int, db: AsyncSession = Depends(get_db),
                       x_remote_token: Optional[str] = Header(None)):
    """A video worker couldn't open the served web-MP4 (truncated / no moov). Drop the
    bad transcode and re-enqueue a fresh one instead of letting the worker skip it
    forever. NOT an ai_error — the source is usually fine, only the transcode broke."""
    await _require_token(db, x_remote_token)
    photo = await db.get(Photo, photo_id)
    if not photo or not photo.is_video:
        raise HTTPException(404)
    wp = photo.video_webm_path
    if wp and os.path.exists(wp):
        try: os.unlink(wp)
        except Exception: pass
    photo.video_webm_path = None
    photo.ai_error = False
    photo.ai_claimed_at = None
    await db.commit()
    from app.worker.tasks import transcode_video_task
    transcode_video_task.delay(photo_id)
    return {"ok": True, "requeued": True}


@router.post("/revalidate-transcodes")
async def revalidate_transcodes(db: AsyncSession = Depends(get_db),
                                x_remote_token: Optional[str] = Header(None)):
    """Maintenance: ffprobe every web-MP4 and re-transcode the broken ones. Runs in the
    background (celery) so the request returns immediately."""
    await _require_token(db, x_remote_token)
    from app.worker.tasks import revalidate_transcodes_task
    revalidate_transcodes_task.delay()
    return {"ok": True, "queued": True}


@router.get("/frame/{photo_id}/{idx}")
async def video_frame(photo_id: int, idx: int, n: Optional[int] = None,
                      db: AsyncSession = Depends(get_db),
                      x_remote_token: Optional[str] = Header(None)):
    """Serve the idx-th of N evenly-spaced frames of a video (for multi-frame AI
    / face sampling). N defaults to the description plan; pass ?n= for a denser
    face sweep. Frame timestamp = (idx+0.5) * duration / N — on demand, no cache."""
    from fastapi.responses import Response
    from app.services.processing.thumbnails import video_frame_plan, extract_video_frame_bytes, video_duration
    await _require_token(db, x_remote_token)
    photo = await db.get(Photo, photo_id)
    if not photo or not photo.is_video:
        raise HTTPException(404)
    dur = photo.duration_seconds or video_duration(photo.path) or 0
    n = max(1, int(n)) if n else max(1, video_frame_plan(dur))
    if dur <= 0 or idx >= n:
        raise HTTPException(404, "Frame außerhalb des Bereichs")
    ts = (idx + 0.5) * dur / n
    data = extract_video_frame_bytes(photo.path, ts)
    if not data:
        raise HTTPException(404, "Frame nicht extrahierbar")
    return Response(content=data, media_type="image/jpeg")


class FaceIn(BaseModel):
    bbox_x: float
    bbox_y: float
    bbox_w: float
    bbox_h: float
    confidence: float = 0.9
    embedding: Optional[List[float]] = None
    frame_time: Optional[float] = None   # video: timestamp of the detection frame


class ResultIn(BaseModel):
    description: Optional[str] = None
    tags: List[str] = []
    embedding: Optional[List[float]] = None
    faces: List[FaceIn] = []
    provider: str = "remote"
    error: Optional[str] = None
    worker: Optional[str] = None
    duration: Optional[float] = None   # seconds the worker spent on this photo
    faces_done: bool = True            # did a face pass actually run? describe-only
                                       # workers (e.g. Ollama on a Mac, no InsightFace)
                                       # set this False so the photo stays claimable
                                       # for a faces worker. Default True = legacy agents.


async def _record_worker_stat(worker: str, duration: Optional[float]):
    """Track per-worker throughput in Redis for the live status/ETA display."""
    try:
        r = await _redis()
        key = f"remote:wstats:{worker}"
        n = int(await r.hincrby(key, "jobs", 1))
        if duration is not None:
            prev = await r.hget(key, "avg")
            prev = float(prev) if prev else float(duration)
            avg = duration if n <= 1 else 0.7 * prev + 0.3 * float(duration)
            await r.hset(key, mapping={"last_dur": float(duration), "avg": round(avg, 2)})
        await r.set(f"remote:worker:{worker}", str(int(time.time())), ex=HEARTBEAT_TTL)  # refresh heartbeat
        await r.aclose()
    except Exception:
        pass


@router.post("/result/{photo_id}")
async def result(photo_id: int, body: ResultIn, db: AsyncSession = Depends(get_db),
                 x_remote_token: Optional[str] = Header(None)):
    """Write back what the remote worker computed (mirrors the local ai_photo step)."""
    s = await _require_token(db, x_remote_token)
    from app.models.tag import Tag, PhotoTag
    from app.models.face import Face
    from app.services.feature_log import log as flog

    photo = await db.get(Photo, photo_id)
    if not photo:
        raise HTTPException(404)

    # Faces-only pass: the agent produced no description (faces-only worker, or an
    # already-described photo) and there was no describe error. Used for an
    # accurate log line (no XMP is expected for these).
    faces_only_pass = (not body.description) and (not body.error)

    # The photo is at status=processing (process_photo handed it off and ai_photo
    # yielded). Mark it done now so it appears in the iOS feed + search, which
    # filter on status==done.
    photo.status = PhotoStatus.done

    worker = (body.worker or "worker")[:60]
    dur = f"{body.duration:.1f}s" if body.duration is not None else "?"
    if body.worker is not None:
        await _record_worker_stat(worker, body.duration)

    if body.error and not body.description:
        photo.ai_error = True
        # Count the attempt so retry_failed_ai's cap (ai_attempts < 20) stops re-serving
        # a video the model can't describe. A "degenerate"/"too few frames" verdict is
        # FINAL (the worker already retried with sampling) — retire the clip at once
        # (jump to the cap) instead of grinding it ~20 more times every 15 min. That's
        # exactly the surveillance-cam case (Rec_*_S.mp4 → '!!!!').
        _err = (body.error or "").lower()
        final = any(k in _err for k in ("degenerate", "few frames", "nframes", "must be in"))
        photo.ai_attempts = 20 if final else (photo.ai_attempts or 0) + 1
        photo.ai_claimed_at = None
        photo.processed_at = datetime.now(timezone.utc)
        await db.commit()
        flog("ai", "WARNING", f"Remote-Fehler ({body.provider}): {photo.filename}: {body.error[:160]}")
        flog("remote", "WARNING", f"[{worker}] #{photo_id} {photo.filename} fehlgeschlagen nach {dur}: {body.error[:120]}")
        return {"ok": True, "stored": "error"}

    if body.description:
        photo.description = body.description
        photo.description_model = (body.provider or "remote")[:120]
        flog("ai", "INFO", f"Beschreibung ({body.provider}): {photo.filename} — {body.description}")
        if photo.is_video:
            flog("video", "INFO", f"KI-Beschreibung (remote, {dur}): {photo.filename} — {body.description[:120]}")

    # tags (replace previous AI tags)
    n_tags = 0
    clean: List[str] = []
    if body.tags:
        await db.execute(sql_delete(PhotoTag).where(PhotoTag.photo_id == photo_id, PhotoTag.source == "ai"))
        clean = [t.strip()[:120] for t in body.tags[:20] if t.strip()]
        for name in clean:
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
        n_tags = len(clean)
        if clean:
            flog("ai", "INFO", f"Tags ({body.provider}): {photo.filename} — {', '.join(clean)}")

    # Write the AI result INTO the file / sidecar — mirrors the local ai_photo
    # step. The remote worker is storage-free; the SERVER owns the /photos mount,
    # so we do the exiftool write here (xmp.write_mode: off|file|file_sidecar|sidecar).
    wrote_file = False
    xmp_mode = str(s.get("xmp.write_mode", "off")).lower()
    # Datei am gespeicherten Pfad weg (verschoben/umbenannt/gelöscht)? Dann NICHT
    # versuchen zu schreiben (das flutete sonst das Log mit „File not found"-WARNINGs)
    # — stattdessen als fehlend markieren. Die Claim-Queries filtern is_missing==False,
    # also wird das Foto danach nicht erneut beschrieben/geschrieben.
    import os as _os
    if photo.path and not _os.path.exists(photo.path):
        if not photo.is_missing:
            photo.is_missing = True
            flog("ai", "INFO", f"Datei nicht mehr am Pfad — als fehlend markiert (remote): {photo.filename}")
    elif (body.description or clean) and xmp_mode in ("file", "file_sidecar", "sidecar"):
        try:
            # Videos: never embed (exiftool can't write MTS/AVCHD and many video
            # containers) — always use a .xmp sidecar instead. Images embed per mode.
            if xmp_mode in ("file", "file_sidecar") and not photo.is_video:
                from app.services.exif_edit import write_description as _wd, write_keywords as _wk, ensure_capture_date as _ecd
                # If the file has no capture date, derive one from its filesystem
                # date BEFORE we touch it (and mirror it into the DB).
                set_date = await _ecd(photo.path)
                if set_date and photo.taken_at is None:
                    try:
                        photo.taken_at = datetime.strptime(set_date[:19], "%Y:%m:%d %H:%M:%S")
                        flog("ai", "INFO", f"Aufnahmedatum aus Dateidatum gesetzt (remote): {photo.filename} → {set_date}")
                    except Exception:
                        pass
                if body.description:
                    await _wd(photo.path, body.description, overwrite=True)
                if clean:
                    await _wk(photo.path, clean)
                wrote_file = True
                flog("ai", "INFO", f"Beschreibung in Datei geschrieben (remote): {photo.filename}")
            if photo.is_video or xmp_mode in ("file_sidecar", "sidecar"):
                from app.services.xmp_sidecar import write_sidecar, file_capture_date
                # Nur photo.taken_at für den Sidecar-Header — KEIN file_capture_date() in die DB.
                # file_capture_date() = os.path.getmtime() = Sync-Datum, nicht Aufnahmedatum.
                cap = photo.taken_at or file_capture_date(photo.path)
                xmp_path = write_sidecar(
                    photo.path, description=body.description, title=photo.title,
                    keywords=clean or None,
                    latitude=photo.latitude, longitude=photo.longitude,
                    city=photo.city, country=photo.country,
                    capture_date=cap.strftime("%Y-%m-%dT%H:%M:%S") if cap else None,
                )
                photo.xmp_sidecar_written = True
                photo.xmp_sidecar_path = xmp_path
                wrote_file = True
                flog("ai", "INFO", f"XMP-Sidecar geschrieben (remote): {photo.filename}")
        except Exception as xe:
            flog("ai", "WARNING", f"Metadaten-Schreiben fehlgeschlagen (remote): {photo.filename}: {str(xe)[:120]}")

    # NOTE: embeddings are NOT computed here. The dedicated jina-clip-v2 `embed`
    # worker owns BOTH vectors (image + description text) so the whole library
    # stays in one joint space — computing an e5 vector here would clobber the
    # jina image vector. A describe result just sets the description; the embed
    # worker then picks the photo up (embedding_text IS NULL AND description set).

    # faces (only if none yet — don't wipe existing person links)
    n_faces = 0
    # Safety net (also enforced in the agent): drop non-face-shaped boxes, which
    # interlaced video frames produce as high-confidence false positives.
    body.faces = [f for f in (body.faces or [])
                  if f.bbox_h and 0.45 <= (f.bbox_w / f.bbox_h) <= 1.8]
    if body.faces:
        existing = await db.scalar(select(func.count()).where(Face.photo_id == photo_id))
        if not existing:
            # Recovery: if the file named exactly ONE person (XMP:PersonInImage read
            # on import), this is an unambiguous single-person photo — assign the
            # detected face(s) to that person directly. Ambiguous multi-name photos
            # are left for clustering (the names stay searchable on the photo).
            auto_pid = None
            names = [n.strip() for n in (photo.imported_person_names or "").split(",") if n.strip()]
            if len(names) == 1:
                from app.models.person import Person
                person = await db.scalar(select(Person).where(Person.name == names[0]))
                if not person:
                    person = Person(name=names[0]); db.add(person); await db.flush()
                auto_pid = person.id
            for f in body.faces:
                db.add(Face(
                    photo_id=photo_id, bbox_x=f.bbox_x, bbox_y=f.bbox_y, bbox_w=f.bbox_w, bbox_h=f.bbox_h,
                    confidence=f.confidence, embedding=f.embedding, detector="insightface",
                    frame_time=f.frame_time, person_id=auto_pid,
                ))
            if auto_pid:
                flog("faces", "INFO", f"Gesicht(er) Person '{names[0]}' zugeordnet (aus Datei): {photo.filename}")
            cxs = [f.bbox_x + f.bbox_w / 2 for f in body.faces]
            cys = [f.bbox_y + f.bbox_h / 2 for f in body.faces]
            photo.focus_x = min(1.0, max(0.0, sum(cxs) / len(cxs)))
            photo.focus_y = min(1.0, max(0.0, sum(cys) / len(cys)))
            n_faces = len(body.faces)
            flog("faces", "INFO", f"{n_faces} Gesicht(er) (remote): {photo.filename}")

    photo.ai_claimed_at = None
    # Mark faces done ONLY if a face pass actually ran (even with 0 faces). A
    # describe-only worker (faces_done=False) leaves this so a faces worker still
    # claims the photo — otherwise its faces would be silently lost.
    if body.faces_done:
        photo.faces_scanned = True
    photo.processed_at = datetime.now(timezone.utc)
    await db.commit()

    # One consolidated line per finished photo for the live Remote-Worker log:
    # duration + what was produced + final status. (Description, tag list and
    # faces also land in their own ai/faces logs above.)
    if faces_only_pass:
        file_note = "nur Gesichter"
    else:
        file_note = "✎ XMP" if wrote_file else ("kein XMP" if xmp_mode == "off" else "XMP-Fehler")
    flog("remote", "INFO",
         f"[{worker}] #{photo_id} {photo.filename} ✓ {dur} · {n_tags} Tags · {n_faces} Gesichter · "
         f"{file_note} · status=done — {(body.description or photo.description or '')[:140]}")
    return {"ok": True}


class EmbedResultIn(BaseModel):
    embedding: Optional[List[float]] = None        # jina-clip-v2 IMAGE vector (768)
    embedding_text: Optional[List[float]] = None   # jina-clip-v2 description vector (768)
    worker: Optional[str] = None
    duration: Optional[float] = None


@router.post("/embed-result/{photo_id}")
async def embed_result(photo_id: int, body: EmbedResultIn, db: AsyncSession = Depends(get_db),
                       x_remote_token: Optional[str] = Header(None)):
    """Persist jina-clip-v2 vectors computed by a remote embed worker (GPU bulk).
    Storage-free worker → the server just stores the 768-dim image/text vectors."""
    await _require_token(db, x_remote_token)
    photo = await db.get(Photo, photo_id)
    if not photo:
        raise HTTPException(404)

    def _fit(v):
        if not v:
            return None
        if len(v) > 768:
            v = v[:768]
            n = math.sqrt(sum(x * x for x in v)) or 1.0
            v = [x / n for x in v]
        return v if len(v) == 768 else None

    iv, tv = _fit(body.embedding), _fit(body.embedding_text)
    if iv is not None:
        photo.embedding = iv
    if tv is not None:
        photo.embedding_text = tv
    await db.commit()
    if body.worker:
        await _record_worker_stat((body.worker or "embed")[:60], body.duration)
    return {"ok": True, "image": iv is not None, "text": tv is not None}


async def _celery_active_tasks() -> list[dict]:
    """Return active tasks from local Celery workers via inspect (non-blocking, 2s timeout)."""
    import asyncio, subprocess, json as _json
    try:
        proc = await asyncio.create_subprocess_exec(
            "celery", "-A", "app.worker.celery_app", "inspect", "active",
            "--timeout", "2", "--json",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            cwd="/app",
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=4)
        data = _json.loads(out or b"{}")
    except Exception:
        return []
    result = []
    _queue_label = {
        "gpu": "GPU (Server)", "video": "Video (Server)", "cpu": "CPU (Server)",
        "scan": "Scan (Server)", "celery": "Server",
    }
    _task_label = {
        "detect_video_faces": "Video-Gesichter",
        "detect_faces": "Gesichter",
        "transcode_video": "Video-Transcode",
        "describe_photo": "Beschreibung",
        "generate_thumbnail": "Thumbnail",
        "scan_source": "Quellen-Scan",
        "backfill_blur": "Blur-Daten",
        "cluster_faces": "Gesichts-Cluster",
    }
    for worker_name, tasks in data.items():
        for t in (tasks or []):
            q = (t.get("delivery_info") or {}).get("routing_key", "")
            args = t.get("args") or []
            result.append({
                "worker": worker_name,
                "worker_label": _queue_label.get(q, q or worker_name),
                "queue": q,
                "task": t.get("name", "").split(".")[-1],
                "task_label": _task_label.get(t.get("name", "").split(".")[-1], t.get("name", "").split(".")[-1]),
                "photo_id": args[0] if args and isinstance(args[0], int) else None,
                "started_at": t.get("time_start"),
            })
    return result


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
    # Faces backlog (the OTHER remote pipeline) so the UI can show description
    # and face progress separately instead of one vague "AI jobs" number.
    faces_pending = await db.scalar(
        select(func.count()).where(
            Photo.faces_scanned == False, Photo.thumb_large.isnot(None),  # noqa: E712
            Photo.is_video == False, Photo.is_trashed == False,  # noqa: E712
        )
    )
    # jina-clip-v2 embedding progress (image vectors)
    embed_total = await db.scalar(select(func.count()).where(
        Photo.thumb_large.isnot(None), Photo.is_trashed == False, Photo.is_missing == False))  # noqa: E712
    embed_done = await db.scalar(select(func.count()).where(
        Photo.embedding.isnot(None), Photo.is_trashed == False))  # noqa: E712
    now = int(time.time())
    workers = []
    durs = []
    try:
        r = await _redis()
        for k in await r.keys("remote:worker:*"):
            ts = await r.get(k)
            name = k.decode().split(":")[-1] if isinstance(k, bytes) else str(k).split(":")[-1]
            st = await r.hgetall(f"remote:wstats:{name}")
            st = {(kk.decode() if isinstance(kk, bytes) else kk):
                  (vv.decode() if isinstance(vv, bytes) else vv) for kk, vv in (st or {}).items()}
            avg = float(st["avg"]) if st.get("avg") else None
            last_dur = float(st["last_dur"]) if st.get("last_dur") else None
            jobs = int(st["jobs"]) if st.get("jobs") else 0
            if avg:
                durs.append(avg)
            # Role from the worker name (embed / faces / else describe) so we never
            # average a 10s describe together with a 1s face pass.
            nl = name.lower()
            role = ("embed" if "embed" in nl else "faces" if "face" in nl
                    else "video" if "video" in nl else "describe")
            workers.append({
                "name": name, "role": role,
                "last_seen": int(ts) if ts else 0,
                "idle_s": now - int(ts) if ts else None,
                "jobs": jobs,
                "last_dur": last_dur,
                "avg_dur": avg,
            })
        await r.aclose()
    except Exception:
        pass

    # Describe split: images (gemma4/Ollama, thumb_large source) vs videos
    # (Qwen3-VL/MLX, 1080p web-mp4 source) — different workers + sources, so shown
    # as separate lines instead of one lumped "describe".
    img_describe_pending = await db.scalar(select(func.count()).where(
        Photo.description.is_(None), Photo.ai_error == False,  # noqa: E712
        Photo.thumb_large.isnot(None), Photo.is_video == False, Photo.is_trashed == False))  # noqa: E712
    vid_describe_pending = await db.scalar(select(func.count()).where(
        Photo.description.is_(None), Photo.is_video == True, Photo.ai_error == False,  # noqa: E712
        Photo.video_webm_path.isnot(None), Photo.is_trashed == False))  # noqa: E712
    # 1080p web transcode (server-side worker-video, QSV) — the player + video-AI
    # source. "done" = has a *_1080.mp4; pending = remaining videos.
    vid_total = await db.scalar(select(func.count()).where(
        Photo.is_video == True, Photo.is_trashed == False, Photo.is_missing == False))  # noqa: E712
    vid_1080 = await db.scalar(select(func.count()).where(
        Photo.is_video == True, Photo.video_webm_path.like("%_1080.mp4"),  # noqa: E712
        Photo.is_trashed == False))  # noqa: E712
    transcode_pending = max(0, (vid_total or 0) - (vid_1080 or 0))

    # Progress ("done") counts for the dashboard's per-stage progress bars.
    from app.models.face import Face
    from app.models.person import Person
    img_described = await db.scalar(select(func.count()).where(
        Photo.description.isnot(None), Photo.is_video == False,  # noqa: E712
        Photo.thumb_large.isnot(None), Photo.is_trashed == False))  # noqa: E712
    vid_described = await db.scalar(select(func.count()).where(
        Photo.description.isnot(None), Photo.is_video == True, Photo.is_trashed == False))  # noqa: E712
    faces_done = await db.scalar(select(func.count()).where(
        Photo.faces_scanned == True, Photo.is_video == False, Photo.is_trashed == False))  # noqa: E712
    thumb_done = await db.scalar(select(func.count()).where(
        Photo.thumb_large.isnot(None), Photo.is_trashed == False))  # noqa: E712
    thumb_pending = await db.scalar(select(func.count()).where(
        Photo.thumb_large.is_(None), Photo.is_trashed == False, Photo.is_missing == False,
        Photo.status != PhotoStatus.error))  # exclude undecodable/corrupt source files (marked error) so the bar reaches 100%  # noqa: E712
    photos_total = await db.scalar(select(func.count()).where(Photo.is_trashed == False))  # noqa: E712
    with_faces = await db.scalar(select(func.count(func.distinct(Face.photo_id))))
    named_persons = await db.scalar(select(func.count()).where(
        Person.name.isnot(None), func.length(func.trim(Person.name)) > 0))
    # The number that actually answers "how far is face RECOGNITION": faces assigned
    # to a person vs. all (non-ignored) detected faces. (with_faces above is only the
    # share of PHOTOS that contain any face — not a progress metric.)
    faces_total = await db.scalar(select(func.count()).where(Face.is_ignored == False)) or 0  # noqa: E712
    faces_assigned = await db.scalar(select(func.count()).where(
        Face.person_id.isnot(None), Face.is_ignored == False)) or 0  # noqa: E712

    # PER-ROLE stats + ETA — each pipeline gets its own backlog, its own workers'
    # mean time, and its own honest projection. Mixing them made ETA meaningless.
    role_pending = {"describe": img_describe_pending or 0, "video": vid_describe_pending or 0,
                    "faces": faces_pending or 0,
                    "embed": max(0, (embed_total or 0) - (embed_done or 0))}
    role_done = {"describe": img_described or 0, "video": vid_described or 0,
                 "faces": faces_done or 0, "embed": embed_done or 0}
    role_label = {"describe": "Bild-Beschreibung", "video": "Video-Beschreibung",
                  "embed": "Embeddings", "faces": "Gesichter"}
    roles = []
    # Thumbnails first in the chain (server-side worker-cpu, ~4 slots).
    roles.append({"role": "thumbnails", "label": "Thumbnails", "pending": thumb_pending or 0,
                  "done": thumb_done or 0, "workers": 4, "avg_dur": None,
                  "eta_seconds": int((thumb_pending or 0) * 2 / 4) if thumb_pending else 0})
    for role in ("describe", "video", "embed", "faces"):
        rw = [w for w in workers if w["role"] == role and (w["idle_s"] is None or w["idle_s"] < 120)]
        rdurs = [w["avg_dur"] for w in rw if w["avg_dur"]]
        ravg = round(sum(rdurs) / len(rdurs), 1) if rdurs else None
        pend = role_pending.get(role, 0)
        eta = int(pend * ravg / len(rw)) if (ravg and rw and pend) else None
        roles.append({"role": role, "label": role_label[role], "pending": pend,
                      "done": role_done.get(role, 0),
                      "workers": len(rw), "avg_dur": ravg, "eta_seconds": eta})
    # Video 1080p transcode — server-side (worker-video, 2 QSV slots), no remote
    # heartbeat; rough ETA at ~8s/video over 2 parallel slots.
    if transcode_pending or vid_1080:
        roles.append({"role": "transcode", "label": "Video 1080p (Web)",
                      "pending": transcode_pending, "done": vid_1080 or 0,
                      "workers": 2, "avg_dur": None,
                      "eta_seconds": int(transcode_pending * 8 / 2) if transcode_pending else 0})

    local_active = await _celery_active_tasks()

    return {
        "enabled": str(s.get("remote.enabled", "false")).lower() == "true",
        "has_token": bool((s.get("remote.token") or "").strip()),
        "pending": pending or 0,
        "faces_pending": faces_pending or 0,
        "embed_done": embed_done or 0,
        "embed_total": embed_total or 0,
        "workers": workers,
        "local_active": local_active,
        "roles": roles,
        "avg_dur": round(sum(durs) / len(durs), 1) if durs else None,  # legacy
        # Library headline numbers for the dashboard.
        "library": {
            "photos": photos_total or 0,
            "videos": vid_total or 0,
            "images": max(0, (photos_total or 0) - (vid_total or 0)),
            "described": (img_described or 0) + (vid_described or 0),
            "with_faces": with_faces or 0,
            "faces_total": faces_total,
            "faces_assigned": faces_assigned,
            "faces_unassigned": max(0, faces_total - faces_assigned),
            "named_persons": named_persons or 0,
            "embeddings": embed_done or 0,
            "thumbnails": thumb_done or 0,
        },
    }


# ── Local video-AI jobs (the M3 LTX worker pulls these) ───────────────────────
# Producer/consumer for image-to-video done LOCALLY on the M3: highlights created
# with params.provider == "local" stay pending until the M3 worker claims them here,
# renders with LTX (offline), and uploads the MP4. Decoupled from the Mac being online
# (your "M3 produces when available + keep a buffer" idea). Source image is fetched
# via the existing /remote/image/{photo_id} (thumb_large).
@router.get("/video-jobs/next")
async def video_job_next(db: AsyncSession = Depends(get_db),
                         x_remote_token: Optional[str] = Header(None)):
    await _require_token(db, x_remote_token)
    from app.models.highlight import Highlight, HighlightStatus
    rows = (await db.execute(
        select(Highlight).where(
            Highlight.status == HighlightStatus.pending,
            Highlight.motto == "photo_animate",
        ).order_by(Highlight.created_at).limit(10)
    )).scalars().all()
    job = next((h for h in rows if (h.params or {}).get("provider") == "local"), None)
    if not job:
        return {"job": None}
    job.status = HighlightStatus.rendering
    await db.commit()
    p = job.params or {}
    return {"job": {"id": job.id, "photo_id": job.cover_photo_id,
                    "prompt": p.get("prompt") or "", "seconds": int(job.duration_sec or 4)}}


@router.post("/video-jobs/{job_id}/complete")
async def video_job_complete(job_id: int, file: UploadFile = File(...),
                             db: AsyncSession = Depends(get_db),
                             x_remote_token: Optional[str] = Header(None)):
    """M3 uploads the finished MP4 → cached + Highlight done."""
    await _require_token(db, x_remote_token)
    from app.models.highlight import Highlight, HighlightStatus
    from app.core.config import get_settings
    job = await db.get(Highlight, job_id)
    if not job:
        raise HTTPException(404)
    out_dir = os.path.join(get_settings().cache_path, "highlights", "clips")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{job_id}.mp4")
    tmp = out_path + ".part"
    with open(tmp, "wb") as f:
        f.write(await file.read())
    os.replace(tmp, out_path)
    try:
        from app.services.processing.thumbnails import video_duration
        dur = video_duration(out_path)
    except Exception:
        dur = None
    job.file_path = out_path
    job.duration_sec = round(dur, 1) if dur else job.duration_sec
    job.photo_count = 1
    job.status = HighlightStatus.done
    job.error_message = None
    await db.commit()
    return {"ok": True}


@router.post("/video-jobs/{job_id}/fail")
async def video_job_fail(job_id: int, error: Optional[str] = None,
                         db: AsyncSession = Depends(get_db),
                         x_remote_token: Optional[str] = Header(None)):
    await _require_token(db, x_remote_token)
    from app.models.highlight import Highlight, HighlightStatus
    job = await db.get(Highlight, job_id)
    if not job:
        raise HTTPException(404)
    job.status = HighlightStatus.error
    job.error_message = (error or "Lokale Generierung (M3) fehlgeschlagen.")[:500]
    await db.commit()
    return {"ok": True}


# ── Standalone worker installer (curl | bash) ──────────────────────────────────

@router.get("/worker.py", response_class=PlainTextResponse)
async def serve_worker_py():
    """Serves the self-contained standalone worker script (no repo clone needed)."""
    p = pathlib.Path(__file__).parent.parent / "remote_worker" / "standalone.py"
    return PlainTextResponse(p.read_text(), media_type="text/plain")


@router.get("/install", response_class=PlainTextResponse)
async def install_script(
    request: Request,
    token: str = Query(""),
    name: str = Query("mac-describe"),
    media: str = Query("images"),
    model: str = Query("gemma4:27b"),
):
    """Returns a complete bash installer. Pipe to bash:
       curl -sSL 'http://server:8090/api/remote/install?token=...&name=mac-describe' | bash
    """
    base = str(request.base_url).rstrip("/")
    plist_label = f"com.nimtaflow.{name}"
    script = f"""#!/bin/bash
# NimtaFlow Remote-Worker Installer
# Automatisch generiert — einfach pipen: curl -sSL '...' | bash
set -e

SERVER="{base}"
TOKEN="{token}"
WORKER_NAME="{name}"
WORKER_MEDIA="{media}"
OLLAMA_MODEL="{model}"
DIR="$HOME/nimtaflow-worker"
PLIST="$HOME/Library/LaunchAgents/{plist_label}.plist"

echo "=== NimtaFlow Worker Setup: $WORKER_NAME ==="
echo "Server: $SERVER"
echo "Modell: $OLLAMA_MODEL"
echo ""

# ── 1. Prüfe Python 3.10+ ─────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
  echo "❌ python3 fehlt. Bitte Python 3.10+ installieren."; exit 1
fi
PY_VER=$(python3 -c "import sys; print(sys.version_info.minor)")
if [ "$PY_VER" -lt 10 ]; then
  echo "❌ Python 3.10+ benötigt (gefunden: 3.$PY_VER)"; exit 1
fi

# ── 2. Prüfe Ollama ────────────────────────────────────────────────────────────
if ! command -v ollama &>/dev/null; then
  echo "❌ Ollama fehlt → https://ollama.ai installieren und nochmal ausführen."
  exit 1
fi

# ── 3. Worker-Verzeichnis & venv ───────────────────────────────────────────────
mkdir -p "$DIR"
if [ ! -d "$DIR/venv" ]; then
  echo "→ Erstelle venv …"
  python3 -m venv "$DIR/venv"
fi
echo "→ Installiere Abhängigkeiten (httpx, pillow) …"
"$DIR/venv/bin/pip" install -q --upgrade httpx pillow

# ── 4. worker.py herunterladen ─────────────────────────────────────────────────
echo "→ Lade worker.py herunter …"
curl -sSL "$SERVER/api/remote/worker.py" -o "$DIR/worker.py"

# ── 5. Ollama-Modell laden ─────────────────────────────────────────────────────
echo "→ Lade Ollama-Modell: $OLLAMA_MODEL …"
ollama pull "$OLLAMA_MODEL"

# ── 6. Launchd-Plist schreiben ─────────────────────────────────────────────────
echo "→ Schreibe LaunchAgent: $PLIST …"
cat > "$PLIST" << 'PLIST_EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
PLIST_EOF

cat >> "$PLIST" << PLIST_EOF
  <key>Label</key>
  <string>{plist_label}</string>
  <key>ProgramArguments</key>
  <array>
    <string>$DIR/venv/bin/python</string>
    <string>$DIR/worker.py</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PHOTOFLOW_SERVER</key>
    <string>$SERVER</string>
    <key>PHOTOFLOW_REMOTE_TOKEN</key>
    <string>$TOKEN</string>
    <key>WORKER_NAME</key>
    <string>$WORKER_NAME</string>
    <key>WORKER_MEDIA</key>
    <string>$WORKER_MEDIA</string>
    <key>OLLAMA_URL</key>
    <string>http://localhost:11434</string>
    <key>OLLAMA_MODEL</key>
    <string>$OLLAMA_MODEL</string>
  </dict>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$DIR/worker.log</string>
  <key>StandardErrorPath</key>
  <string>$DIR/worker.log</string>
PLIST_EOF

cat >> "$PLIST" << 'PLIST_EOF'
</dict>
</plist>
PLIST_EOF

# ── 7. Dienst (neu) starten ────────────────────────────────────────────────────
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load -w "$PLIST"

echo ""
echo "✅ Worker '$WORKER_NAME' läuft!"
echo "   Logs:  tail -f $DIR/worker.log"
echo "   Stop:  launchctl unload $PLIST"
echo "   Start: launchctl load -w $PLIST"
"""
    return PlainTextResponse(script, media_type="text/plain")


@router.get("/backfill-progress")
async def backfill_progress():
    """Live-Fortschritt des laufenden backfill_xmp-Tasks aus Redis."""
    import json
    try:
        import redis as _redis
        from app.core.config import get_settings
        rc = _redis.from_url(get_settings().redis_url, decode_responses=True)
        raw = rc.get("backfill_xmp:progress")
        if not raw:
            return {"running": False, "total": 0, "done": 0, "failed": 0, "pct": 0, "finished": False}
        d = json.loads(raw)
        total = d.get("total", 0)
        done = d.get("done", 0)
        pct = round(100 * done / total) if total else 0
        elapsed = time.time() - d.get("started_at", time.time())
        eta = None
        if done > 0 and not d.get("finished"):
            eta = int(elapsed / done * (total - done))
        return {
            "running": not d.get("finished", False),
            "finished": d.get("finished", False),
            "full": d.get("full", False),
            "total": total,
            "done": done,
            "failed": d.get("failed", 0),
            "pct": pct,
            "elapsed_s": int(elapsed),
            "eta_s": eta,
        }
    except Exception:
        return {"running": False, "total": 0, "done": 0, "failed": 0, "pct": 0, "finished": False}


# ── Sidecar-Audit ────────────────────────────────────────────────────────────
# Prüft die REALE Disk-Situation der XMP-Sidecars — nicht das DB-Flag.
# Kategorien:
#   ok              — Sidecar existiert und enthält die aktuelle Beschreibung
#   missing         — Sidecar fehlt komplett obwohl DB flag=true
#   stale           — Sidecar existiert, aber Description in DB neuer als Sidecar-mtime
#   no_description  — Foto hat keine Beschreibung, nichts zu prüfen (übersprungen)

def _check_embed(path: str, needle_bytes: bytes) -> str:
    """Prüft ob die Description im Datei-Header (EXIF/XMP) vorkommt.

    Für JPEG/HEIC/PNG/TIFF liegt XMP praktisch immer in den ersten 256 KB —
    exiftool schreibt es standardmäßig ganz vorn. MP4 ist Ausnahme: XMP-Chunks
    können am Ende sitzen, deshalb schauen wir zusätzlich am Dateiende nach.

    Rückgabe: "ok" | "missing" | "read_error"
    """
    import os
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            head = f.read(min(size, 262_144))  # 256 KB
            if needle_bytes in head:
                return "ok"
            # Bei größeren Videos zusätzlich Tail lesen (letzte 128 KB)
            if size > 262_144 + 131_072:
                f.seek(max(0, size - 131_072))
                tail = f.read(131_072)
                if needle_bytes in tail:
                    return "ok"
            return "missing"
    except FileNotFoundError:
        return "read_error"
    except Exception:
        return "read_error"


@router.get("/sidecar-audit")
async def sidecar_audit(
    limit: int = 0,
    sample: bool = False,
    with_embed: bool = True,
    db: AsyncSession = Depends(get_db),
):
    """Reale Prüfung: welche Fotos haben tatsächlich saubere Sidecars UND
    eingebettete EXIF/XMP-Beschreibungen.

    limit=0: ALLE Fotos (kann Minuten dauern bei 138k). Sonst nur die ersten N.
    sample=true: Repräsentative Stichprobe von 500 quer über die DB.
    with_embed=true (default): auch prüfen ob Description im Bild-Header steht
      (nicht nur im Sidecar). Nur wenn false: Reine Sidecar-Prüfung.

    Kategorien:
      ok             — Sidecar + Embed enthalten die aktuelle Beschreibung
      sidecar_missing — kein .xmp auf Disk
      sidecar_stale  — .xmp existiert, Beschreibung veraltet
      embed_missing  — Description NICHT im Bild-Header (Sidecar egal)
      read_error     — Datei nicht lesbar

    Ein Foto kann in MEHREREN Kategorien sein: sidecar_missing UND embed_missing
    zählen beide. `problem_photo_ids` enthält je Kategorie die IDs (max 1000).
    `repair_ids` = union aller Problem-IDs → an /sidecar-repair übergeben.
    """
    import os
    from app.services.xmp_sidecar import sidecar_for
    from sqlalchemy import select as _sel

    q = _sel(Photo.id, Photo.path, Photo.description, Photo.is_video).where(
        Photo.description.isnot(None),
        Photo.is_missing == False,  # noqa: E712
        Photo.is_trashed == False,  # noqa: E712
    ).order_by(Photo.id)
    if sample:
        q = q.order_by(func.random()).limit(500)
    elif limit > 0:
        q = q.limit(limit)

    rows = (await db.execute(q)).all()

    counts = {
        "checked": 0, "ok": 0,
        "sidecar_missing": 0, "sidecar_stale": 0,
        "embed_missing": 0, "read_error": 0,
    }
    sidecar_missing_ids: list[int] = []
    sidecar_stale_ids: list[int] = []
    embed_missing_ids: list[int] = []
    repair_ids: set[int] = set()

    for row in rows:
        counts["checked"] += 1
        pid, ppath, pdesc, is_video = row
        needle_str = (pdesc or "")[:40].strip()
        needle_bytes = needle_str.encode("utf-8", errors="replace") if needle_str else b""

        problem = False

        # ── Sidecar-Check ─────────────────────────────────────────────
        sc_ok = False
        try:
            sc_path = sidecar_for(ppath)
            if not os.path.exists(sc_path):
                counts["sidecar_missing"] += 1
                sidecar_missing_ids.append(pid)
                problem = True
            else:
                try:
                    with open(sc_path, encoding="utf-8", errors="replace") as f:
                        content = f.read()
                    if needle_str and needle_str not in content:
                        counts["sidecar_stale"] += 1
                        sidecar_stale_ids.append(pid)
                        problem = True
                    else:
                        sc_ok = True
                except Exception:
                    counts["read_error"] += 1
                    problem = True
        except Exception:
            counts["read_error"] += 1
            problem = True

        # ── Embed-Check (Videos übersprungen — MP4-XMP ist nicht zuverlässig
        #    per Byte-Search auffindbar, für Videos zählt Sidecar als Wahrheit)
        embed_ok = True
        if with_embed and not is_video and needle_bytes:
            embed_status = _check_embed(ppath, needle_bytes)
            if embed_status == "missing":
                counts["embed_missing"] += 1
                embed_missing_ids.append(pid)
                problem = True
                embed_ok = False
            elif embed_status == "read_error":
                counts["read_error"] += 1
                problem = True
                embed_ok = False

        if not problem:
            counts["ok"] += 1
        else:
            repair_ids.add(pid)

    return {
        "counts": counts,
        "problem_photo_ids": {
            "sidecar_missing": sidecar_missing_ids[:1000],
            "sidecar_stale":   sidecar_stale_ids[:1000],
            "embed_missing":   embed_missing_ids[:1000],
        },
        "repair_ids": sorted(repair_ids)[:20_000], # cap für Repair-Endpoint-Limit
        "problem_count_total": len(repair_ids),
        "scope": "sample" if sample else ("all" if limit == 0 else f"first_{limit}"),
        "with_embed": with_embed,
    }


class SidecarRepairBody(BaseModel):
    """Startet einen gezielten backfill_xmp-Lauf für die angegebenen Photo-IDs."""
    photo_ids: list[int]


@router.post("/sidecar-repair")
async def sidecar_repair(body: SidecarRepairBody):
    """(Legacy) Startet backfill_xmp gezielt für die vom Audit gemeldeten
    Photo-IDs. Für zuverlässigen Massen-Repair siehe /xmp-repair-queue/*."""
    if not body.photo_ids:
        raise HTTPException(400, "photo_ids leer")
    if len(body.photo_ids) > 20000:
        raise HTTPException(400, "max 20 000 IDs pro Aufruf")
    from app.worker.tasks import backfill_xmp_task
    try:
        import redis as _redis_sync
        _rc = _redis_sync.from_url(get_settings().redis_url, decode_responses=True)
        _rc.delete("backfill_xmp:progress")
    except Exception:
        pass
    result = backfill_xmp_task.delay(photo_ids=body.photo_ids)
    return {"task_id": result.id, "count": len(set(body.photo_ids))}


# ── XMP-Repair-Queue: persistenter, crash-fester Massen-Repair ──────────────

@router.post("/xmp-repair-queue/populate")
async def xmp_repair_populate(reset_failed: bool = True):
    """Startet den Populate-Task (Celery). Der Task scannt alle Fotos,
    prüft Sidecars + EXIF-Embed real auf Disk und legt Problem-Fotos in
    die xmp_repair_queue. Bei bestehenden Zeilen: kein Überschreiben.

    Läuft ~5-10 min bei 138k Fotos. Fortschritt via /populate-status.
    """
    from app.worker.tasks import xmp_repair_populate_task
    result = xmp_repair_populate_task.delay(reset_failed=reset_failed)
    return {"task_id": result.id, "started": True}


@router.get("/xmp-repair-queue/populate-status")
async def xmp_repair_populate_status():
    """Live-Fortschritt des Populate-Tasks."""
    try:
        import redis as _redis_sync
        import json as _json
        _rc = _redis_sync.from_url(get_settings().redis_url, decode_responses=True)
        raw = _rc.get("xmp_repair:populate")
        if not raw:
            return {"running": False, "known": False}
        return _json.loads(raw)
    except Exception:
        return {"running": False, "known": False}


@router.post("/xmp-repair-queue/start")
async def xmp_repair_start(max_items: int = 0):
    """Startet den xmp_repair_run-Task. max_items=0 → bis Queue leer."""
    from app.worker.tasks import xmp_repair_run_task
    # Prüfen ob schon ein Lauf aktiv
    try:
        import redis as _redis_sync
        _rc = _redis_sync.from_url(get_settings().redis_url, decode_responses=True)
        existing = _rc.get("xmp_repair:progress")
        if existing:
            import json as _json
            d = _json.loads(existing)
            if d.get("running"):
                return {"already_running": True, "worker_id": d.get("worker_id")}
    except Exception:
        pass
    result = xmp_repair_run_task.delay(max_items=max_items)
    return {"task_id": result.id, "started": True}


@router.get("/xmp-repair-queue/status")
async def xmp_repair_status(db: AsyncSession = Depends(get_db)):
    """Live-Fortschritt: DB-Zahlen + laufender Task-State aus Redis."""
    from app.models.xmp_repair import XmpRepairItem
    counts_stmt = select(
        XmpRepairItem.status, func.count()
    ).group_by(XmpRepairItem.status)
    rows = (await db.execute(counts_stmt)).all()
    counts = {"pending": 0, "in_progress": 0, "done": 0, "failed": 0, "skipped": 0}
    for status, cnt in rows:
        counts[status] = cnt
    total = sum(counts.values())

    # Redis-Status des aktuellen Runs
    run_state = None
    try:
        import redis as _redis_sync
        import json as _json
        _rc = _redis_sync.from_url(get_settings().redis_url, decode_responses=True)
        raw = _rc.get("xmp_repair:progress")
        if raw:
            run_state = _json.loads(raw)
    except Exception:
        pass

    return {
        "queue": {
            "total": total,
            "pending": counts["pending"],
            "in_progress": counts["in_progress"],
            "done": counts["done"],
            "failed": counts["failed"],
            "skipped": counts["skipped"],
            "pct": round(100 * counts["done"] / total) if total else 0,
        },
        "current_run": run_state,
    }


@router.post("/xmp-repair-queue/clear")
async def xmp_repair_clear(db: AsyncSession = Depends(get_db)):
    """Leert die Repair-Queue komplett — für Neustart nach Design-Änderung."""
    from app.models.xmp_repair import XmpRepairItem
    from sqlalchemy import delete as _del
    result = await db.execute(_del(XmpRepairItem))
    await db.commit()
    return {"deleted": result.rowcount}
