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


@celery_app.task(bind=True, name="auto_cluster_faces")
def auto_cluster_faces_task(self):
    """Beat task: periodically group unassigned faces into (unnamed) people, so
    detected faces don't pile up individually in the 'Gesichter' list. Honours
    the same thresholds as the manual 'Clustern' button; opt-out via
    face.auto_cluster = false."""
    async def _run_cluster():
        from app.core.database import init_db, get_db
        from app.services.settings_loader import load_settings
        init_db()
        async for db in get_db():
            s = await load_settings(db)
            if str(s.get("face.auto_cluster", "true")).lower() == "false":
                return {"skipped": "disabled"}
            try:
                from app.services.face_cluster import cluster_unassigned
                res = await cluster_unassigned(db)
            except ImportError:
                return {"skipped": "no sklearn"}
            # Keep person-based smart albums current (face↔person links just changed).
            try:
                from sqlalchemy import select as _sel
                from app.models.album import Album, AlbumType
                from app.api.routes.albums import _populate_smart
                albums = (await db.execute(_sel(Album).where(Album.album_type == AlbumType.smart))).scalars().all()
                refreshed = 0
                for a in albums:
                    if (a.smart_criteria or {}).get("person_ids"):
                        await _populate_smart(a, db)
                        refreshed += 1
                if refreshed:
                    await db.commit()
                    res["smart_albums_refreshed"] = refreshed
            except Exception:
                pass
            return res

    return _run(_run_cluster())


@celery_app.task(bind=True, name="write_person_name")
def write_person_name_task(self, person_id: int):
    """Write a person's name into their photos as XMP:PersonInImage (best-effort),
    so the tagging survives a re-import into Lightroom/digiKam/Immich."""
    async def _main():
        import shutil, subprocess
        from app.core.database import init_db, get_db
        from app.models.person import Person
        from app.models.photo import Photo
        from app.models.face import Face
        from app.services.feature_log import log as flog
        from sqlalchemy import select
        init_db()
        exe = shutil.which("exiftool")
        if not exe:
            return {"written": 0}
        async for db in get_db():
            person = await db.get(Person, person_id)
            if not person or not (person.name or "").strip():
                return {"written": 0}
            name = person.name.strip()
            rows = (await db.execute(
                select(Photo.path).join(Face, Face.photo_id == Photo.id)
                .where(Face.person_id == person_id).distinct()
            )).all()
            written = 0
            for (path,) in rows:
                try:
                    r = subprocess.run(
                        [exe, "-overwrite_original",
                         f"-XMP:PersonInImage+={name}", f"-XMP-iptcExt:PersonInImage+={name}",
                         path],
                        capture_output=True, timeout=30,
                    )
                    if r.returncode == 0:
                        written += 1
                except Exception:
                    pass
            flog("faces", "INFO", f"Name '{name}' in {written} Foto(s) geschrieben (XMP:PersonInImage)")
            return {"written": written}
    return _run(_main())


@celery_app.task(bind=True, name="process_photo")
def process_photo_task(self, photo_id: int, job_id: Optional[int] = None, redo_faces: bool = False, redo_thumbs: bool = False):
    async def _run_process():
        from app.core.database import init_db, get_db
        from app.models.photo import Photo, PhotoStatus
        from app.models.job import JobLog
        from app.models.tag import Tag, PhotoTag
        from app.services.processing.thumbnails import (
            generate_thumbnail, generate_video_thumbnail, generate_video_preview_webp,
            video_duration, open_image_for_ai,
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
                # Refresh metadata (fills GPS/date/camera that PIL missed on HEIC/MOV,
                # so reprocessing also repairs older entries).
                try:
                    from app.services.processing.exif import extract_exif
                    ex = extract_exif(photo.path)
                    if ex.width and ex.height:
                        photo.width, photo.height = ex.width, ex.height  # orientation-corrected
                    if photo.latitude is None and ex.latitude is not None:
                        photo.latitude, photo.longitude, photo.altitude = ex.latitude, ex.longitude, ex.altitude
                    if photo.taken_at is None and ex.taken_at is not None:
                        photo.taken_at = ex.taken_at
                    if not photo.camera_make and ex.camera_make:
                        photo.camera_make = ex.camera_make[:120]
                    if not photo.camera_model and ex.camera_model:
                        photo.camera_model = ex.camera_model[:120]
                except Exception:
                    pass

                # Generate all thumbnail sizes — videos need a frame extracted via ffmpeg
                if photo.is_video:
                    for size in ("small", "medium", "large"):
                        thumb = generate_video_thumbnail(photo.path, settings.cache_path, size, force=redo_thumbs)
                        if thumb:
                            setattr(photo, f"thumb_{size}", thumb)
                    if photo.duration_seconds is None:
                        photo.duration_seconds = video_duration(photo.path)
                    # animated hover preview (best-effort)
                    try:
                        preview = generate_video_preview_webp(photo.path, settings.cache_path, force=redo_thumbs)
                        if preview:
                            photo.video_preview_path = preview
                    except Exception:
                        pass
                    if photo.thumb_small:
                        flog("video", "INFO", f"Thumbnail + Vorschau erstellt: {photo.filename}")
                    else:
                        flog("video", "WARNING", f"Kein Frame extrahierbar: {photo.filename}")
                else:
                    for size in ("small", "medium", "large"):
                        thumb = generate_thumbnail(photo.path, settings.cache_path, size, force=redo_thumbs)
                        if thumb:
                            setattr(photo, f"thumb_{size}", thumb)
                    if not photo.thumb_small:
                        flog("scanner", "WARNING", f"Thumbnail fehlgeschlagen: {photo.filename}")

                # Persist thumbnails immediately — AI is best-effort and must
                # never cost us the thumbnail or stick the photo on a transient error.
                await db.commit()

                # AI processing — load provider config from DB settings (non-fatal)
                photo.ai_error = False  # cleared on success; set in except below
                try:
                    from app.services.settings_loader import load_settings
                    from app.services.ai.manager import build_video_settings
                    ai_settings = await load_settings(db)
                    # Videos use the separate video.* provider (e.g. moondream/ollama)
                    eff_settings = build_video_settings(ai_settings) if photo.is_video else ai_settings
                    ai = AIManager(eff_settings)

                    # Videos: describe from the extracted frame; else the photo
                    img = open_image_for_ai(photo.thumb_large or photo.thumb_medium or photo.path) if photo.is_video \
                        else open_image_for_ai(photo.path)
                    if img:
                        lang = ai_settings.get("ai.language", "de")
                        custom_prompt = ai_settings.get("ai.prompt.video" if photo.is_video else "ai.prompt.image") or None
                        description, provider = await ai.describe_image(img, lang, custom_prompt)
                        if description:
                            photo.description = description
                            photo.description_model = (provider or "")[:120]
                            flog("ai", "INFO", f"Beschreibung ({provider}): {photo.filename} — {description}")
                        elif provider == "none":
                            flog("ai", "WARNING", f"Kein AI-Provider aktiv/erreichbar für {photo.filename}")

                        tags, _ = await ai.generate_tags(img, lang)
                        if tags:
                            # replace previous AI tags (e.g. old English ones) for this photo
                            from sqlalchemy import delete as _deltag
                            await db.execute(_deltag(PhotoTag).where(PhotoTag.photo_id == photo_id, PhotoTag.source == "ai"))
                        for tag_name in tags[:20]:
                            tag_name = (tag_name or "").strip()[:120]  # column is VARCHAR(128)
                            if not tag_name:
                                continue
                            tag = await db.scalar(select(Tag).where(Tag.name == tag_name))
                            if not tag:
                                # Concurrency-safe get-or-create: parallel workers can
                                # race on the same tag name (unique ix_tags_name). Insert
                                # inside a SAVEPOINT so a UniqueViolation only rolls back
                                # this insert (not the whole AI tx), then re-select.
                                from sqlalchemy.exc import IntegrityError as _IntegrityError
                                try:
                                    async with db.begin_nested():
                                        tag = Tag(name=tag_name)
                                        db.add(tag)
                                        await db.flush()
                                except _IntegrityError:
                                    tag = await db.scalar(select(Tag).where(Tag.name == tag_name))
                                if not tag:
                                    continue
                            existing_pt = await db.scalar(
                                select(PhotoTag).where(PhotoTag.photo_id == photo_id, PhotoTag.tag_id == tag.id)
                            )
                            if not existing_pt:
                                db.add(PhotoTag(photo_id=photo_id, tag_id=tag.id, source="ai"))

                        # Write the AI description into the file and/or a sidecar.
                        # xmp.write_mode: off | file | file_sidecar | sidecar
                        xmp_mode = str(ai_settings.get("xmp.write_mode", "off")).lower()
                        if description and xmp_mode in ("file", "file_sidecar", "sidecar"):
                            kw = [t for t in tags[:20]]
                            try:
                                if xmp_mode in ("file", "file_sidecar"):
                                    from app.services.exif_edit import write_description as _wd, write_keywords as _wk
                                    await _wd(photo.path, description, overwrite=True)
                                    if kw:
                                        await _wk(photo.path, kw)
                                    flog("ai", "INFO", f"Beschreibung in Datei geschrieben: {photo.filename}")
                                if xmp_mode in ("file_sidecar", "sidecar"):
                                    from app.services.xmp_sidecar import write_sidecar
                                    xmp_path = write_sidecar(
                                        photo.path,
                                        description=description,
                                        title=photo.title,
                                        keywords=kw or None,
                                        latitude=photo.latitude, longitude=photo.longitude,
                                        city=photo.city, country=photo.country,
                                    )
                                    photo.xmp_sidecar_written = True
                                    photo.xmp_sidecar_path = xmp_path
                                    flog("ai", "INFO", f"XMP-Sidecar geschrieben: {photo.filename}")
                            except Exception as xe:
                                flog("ai", "WARNING", f"Metadaten-Schreiben fehlgeschlagen: {photo.filename}: {str(xe)[:120]}")

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
                    if photo:
                        photo.ai_error = True  # persisted by the final commit below
                    flog("ai", "WARNING", f"AI übersprungen (Thumbnail bleibt): {photo.filename if photo else photo_id}: {str(ai_err)[:160]}")

                # ── Face detection (local, best-effort) ───────────────────────
                if str(ai_settings.get("faces.enabled", "true")).lower() != "false":
                    try:
                        from app.services.face_detect import detect_faces_engine, engine_available
                        from app.models.face import Face
                        from sqlalchemy import func as _func
                        face_engine = str(ai_settings.get("face.engine", "facenet")).lower()
                        # Skip if this photo already has faces — re-detecting on every
                        # reprocess would wipe Face IDs and break person clusters.
                        existing = await db.scalar(select(_func.count()).where(Face.photo_id == photo_id))
                        if redo_faces and existing:
                            from sqlalchemy import delete as _del
                            await db.execute(_del(Face).where(Face.photo_id == photo_id))
                            existing = 0
                        if engine_available(face_engine) and not existing:
                            face_img = open_image_for_ai(photo.thumb_large or photo.thumb_medium or photo.path)
                            if face_img is not None:
                                min_conf = float(ai_settings.get("face.min_confidence", "0.9") or 0.9)
                                faces = detect_faces_engine(face_img, min_conf, face_engine)
                                for f in faces:
                                    db.add(Face(
                                        photo_id=photo_id,
                                        bbox_x=f.bbox_x, bbox_y=f.bbox_y, bbox_w=f.bbox_w, bbox_h=f.bbox_h,
                                        confidence=f.confidence, embedding=f.embedding, detector=face_engine,
                                    ))
                                await db.commit()
                                if faces:
                                    flog("faces", "INFO", f"{len(faces)} Gesicht(er) erkannt ({face_engine}): {photo.filename}")
                    except Exception as fe:
                        try:
                            await db.rollback()
                            photo = await db.get(Photo, photo_id)
                        except Exception:
                            pass
                        flog("faces", "WARNING", f"Gesichtserkennung fehlgeschlagen: {getattr(photo, 'filename', photo_id)}: {str(fe)[:160]}")

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
