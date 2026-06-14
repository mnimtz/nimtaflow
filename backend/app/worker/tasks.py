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
        from app.services.processing.thumbnails import generate_thumbnail, open_image_for_ai
        from app.services.ai.manager import AIManager
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
                # Generate all thumbnail sizes
                for size in ("small", "medium", "large"):
                    thumb = generate_thumbnail(photo.path, settings.cache_path, size)
                    if thumb:
                        setattr(photo, f"thumb_{size}", thumb)

                # AI processing — load provider config from DB settings
                from app.services.settings_loader import load_settings
                ai_settings = await load_settings(db)
                ai = AIManager(ai_settings)

                img = open_image_for_ai(photo.path)
                if img:
                    description, provider = await ai.describe_image(img, "de")
                    if description:
                        photo.description = description

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
                            photo.embedding = embedding

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
                photo.status = PhotoStatus.error
                photo.error_message = str(e)
                await db.commit()
                if job_id:
                    db.add(JobLog(job_id=job_id, photo_id=photo_id, level="ERROR", message=f"❌ {photo.filename}: {e}"))
                    await db.commit()

    _run(_run_process())
