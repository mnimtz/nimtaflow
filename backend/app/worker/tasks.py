"""Celery tasks for photo processing pipeline."""
import asyncio
from datetime import datetime, timezone
from typing import Optional

from .celery_app import celery_app


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(bind=True, name="scan_source")
def scan_source_task(self, source_id: int):
    async def _run_scan():
        from app.core.database import init_db, get_db
        from app.models.source import PhotoSource
        from app.services.processing.scanner import scan_source
        from app.core.config import get_settings

        init_db()
        settings = get_settings()

        async for db in get_db():
            source = await db.get(PhotoSource, source_id)
            if not source:
                return {"error": "Source not found"}
            stats = await scan_source(source, db, settings.cache_path)
            return stats

    return _run(_run_scan())


@celery_app.task(bind=True, name="watch_sources")
def watch_sources_task(self):
    """Beat task: trigger a re-scan for every watched source whose interval elapsed."""
    async def _check():
        from app.core.database import init_db, get_db
        from app.models.source import PhotoSource
        from sqlalchemy import select
        from datetime import timedelta

        init_db()
        triggered = []
        now = datetime.now(timezone.utc)

        async for db in get_db():
            result = await db.execute(
                select(PhotoSource).where(
                    PhotoSource.enabled == True,  # noqa: E712
                    PhotoSource.watch_enabled == True,  # noqa: E712
                    PhotoSource.scan_interval_minutes > 0,
                )
            )
            for src in result.scalars():
                due = (
                    src.last_scan_at is None
                    or (now - src.last_scan_at) >= timedelta(minutes=src.scan_interval_minutes)
                )
                if due:
                    scan_source_task.delay(src.id)
                    triggered.append(src.id)
            return {"triggered": triggered}

    return _run(_check())


@celery_app.task(bind=True, name="process_photo")
def process_photo_task(self, photo_id: int, job_id: Optional[int] = None):
    async def _run_process():
        from app.core.database import init_db, get_db
        from app.models.photo import Photo, PhotoStatus
        from app.models.job import JobLog
        from app.models.tag import Tag, PhotoTag
        from app.services.processing.thumbnails import (
            generate_thumbnail, generate_video_thumbnail, video_duration, open_image_for_ai,
        )
        from app.services.ai.manager import AIManager
        from app.services.feature_log import log as flog
        from app.core.config import get_settings
        from sqlalchemy import select
        import time

        init_db()
        settings = get_settings()

        async for db in get_db():
            photo = await db.get(Photo, photo_id)
            if not photo:
                return

            photo.status = PhotoStatus.processing
            await db.commit()

            start = time.time()
            try:
                # Generate all thumbnail sizes — videos need a frame extracted via ffmpeg
                if photo.is_video:
                    for size in ("small", "medium", "large"):
                        thumb = generate_video_thumbnail(photo.path, settings.cache_path, size)
                        if thumb:
                            setattr(photo, f"thumb_{size}", thumb)
                    if photo.duration_seconds is None:
                        photo.duration_seconds = video_duration(photo.path)
                    if photo.thumb_small:
                        flog("video", "INFO", f"Thumbnail erstellt: {photo.filename}")
                    else:
                        flog("video", "WARNING", f"Kein Frame extrahierbar: {photo.filename}")
                else:
                    for size in ("small", "medium", "large"):
                        thumb = generate_thumbnail(photo.path, settings.cache_path, size)
                        if thumb:
                            setattr(photo, f"thumb_{size}", thumb)
                    if not photo.thumb_small:
                        flog("scanner", "WARNING", f"Thumbnail fehlgeschlagen: {photo.filename}")

                # Persist thumbnails immediately — AI is best-effort and must
                # never cost us the thumbnail or stick the photo on a transient error.
                await db.commit()

                # AI processing — load provider config from DB settings (non-fatal)
                try:
                    from app.services.settings_loader import load_settings
                    ai_settings = await load_settings(db)
                    ai = AIManager(ai_settings)

                    # Videos: describe from the extracted frame; else the photo
                    img = open_image_for_ai(photo.thumb_large or photo.thumb_medium or photo.path) if photo.is_video \
                        else open_image_for_ai(photo.path)
                    if img:
                        description, provider = await ai.describe_image(img, "de")
                        if description:
                            photo.description = description
                            photo.description_model = provider
                            flog("ai", "INFO", f"Beschreibung ({provider}): {photo.filename} — {description[:60]}")
                        elif provider == "none":
                            flog("ai", "WARNING", f"Kein AI-Provider aktiv/erreichbar für {photo.filename}")

                        tags, _ = await ai.generate_tags(img)
                        for tag_name in tags[:20]:
                            tag = await db.scalar(select(Tag).where(Tag.name == tag_name))
                            if not tag:
                                tag = Tag(name=tag_name)
                                db.add(tag)
                                await db.flush()
                            existing_pt = await db.scalar(
                                select(PhotoTag).where(PhotoTag.photo_id == photo_id, PhotoTag.tag_id == tag.id)
                            )
                            if not existing_pt:
                                db.add(PhotoTag(photo_id=photo_id, tag_id=tag.id, source="ai"))

                        if description:
                            embedding, _ = await ai.embed_text(description)
                            if embedding:
                                # pgvector column is fixed at 768 dims. Some models
                                # (e.g. gemini-embedding-001) return 3072 — truncate
                                # (Matryoshka) + renormalize so any model fits.
                                if len(embedding) > 768:
                                    import math
                                    embedding = embedding[:768]
                                    norm = math.sqrt(sum(x * x for x in embedding)) or 1.0
                                    embedding = [x / norm for x in embedding]
                                if len(embedding) == 768:
                                    photo.embedding = embedding
                                else:
                                    flog("ai", "WARNING", f"Embedding {len(embedding)}≠768 dims, übersprungen: {photo.filename}")
                except Exception as ai_err:
                    await db.rollback()
                    photo = await db.get(Photo, photo_id)
                    flog("ai", "WARNING", f"AI übersprungen (Thumbnail bleibt): {photo.filename if photo else photo_id}: {str(ai_err)[:160]}")

                photo.status = PhotoStatus.done
                photo.processed_at = datetime.now(timezone.utc)

                if job_id:
                    duration_ms = int((time.time() - start) * 1000)
                    db.add(JobLog(
                        job_id=job_id,
                        photo_id=photo_id,
                        level="INFO",
                        message=f"✅ {photo.filename}",
                        duration_ms=duration_ms,
                    ))

                await db.commit()

            except Exception as e:
                # Roll back the broken transaction before recording the error,
                # otherwise the error-write itself fails and the row stays "processing".
                try:
                    await db.rollback()
                except Exception:
                    pass
                fname = "?"
                try:
                    p2 = await db.get(Photo, photo_id)
                    if p2:
                        fname = p2.filename
                        p2.status = PhotoStatus.error
                        p2.error_message = str(e)[:500]
                        await db.commit()
                except Exception:
                    pass
                flog("system", "ERROR", f"Verarbeitung fehlgeschlagen: {fname}: {str(e)[:200]}")
                if job_id:
                    try:
                        db.add(JobLog(job_id=job_id, photo_id=photo_id, level="ERROR", message=f"❌ {fname}: {e}"))
                        await db.commit()
                    except Exception:
                        pass

    _run(_run_process())
