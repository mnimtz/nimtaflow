"""Celery tasks for photo processing pipeline."""
import asyncio
from datetime import datetime, timezone
from typing import Optional

from .celery_app import celery_app


def _run(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        # 1) Finalize any still-open async generators (notably get_db()): their
        #    `finally: await session.close()` only runs on generator finalization.
        #    `loop.close()` alone NEVER finalizes them — so a task using
        #    `async for db in get_db(): … return` leaked its DB connection, which
        #    piled up as idle/ROLLBACK sessions until Postgres hit "too many
        #    clients". asyncio.run() does this step; our manual loop must too.
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception:
            pass
        # 2) Dispose the async engine on THIS loop so its asyncpg connections are
        #    closed cleanly before the loop dies.
        try:
            from app.core.database import dispose_db
            loop.run_until_complete(dispose_db())
        except Exception:
            pass
        loop.close()


@celery_app.task(bind=True, name="scan_source")
def scan_source_task(self, source_id: int):
    async def _run_scan():
        from app.core.database import init_db, get_db
        from app.models.source import PhotoSource
        from app.services.processing.scanner import scan_source
        from app.core.config import get_settings
        from app.services.feature_log import log as flog

        init_db()
        settings = get_settings()

        # Single-flight per source: a full-library scan runs for hours/days, but
        # watch_sources only learns it finished once last_scan_at is set at the
        # END. Without a lock it re-triggers every 60 s → dozens of overlapping
        # scans that starve the cpu workers (no process_photo → no big thumbs/AI).
        # Redis NX lock with a long TTL; auto-expires if the worker dies.
        lock_key = f"scan:lock:{source_id}"
        r = None
        try:
            import redis.asyncio as aioredis
            r = aioredis.from_url(get_settings().redis_url)
            got = await r.set(lock_key, "1", nx=True, ex=6 * 3600)
            if not got:
                await r.aclose()
                flog("scanner", "INFO", f"Scan übersprungen (läuft bereits) für Quelle {source_id}")
                return {"skipped": "already running"}
        except Exception:
            r = None  # Redis unavailable → proceed without the lock rather than block

        try:
            async for db in get_db():
                source = await db.get(PhotoSource, source_id)
                if not source:
                    return {"error": "Source not found"}
                stats = await scan_source(source, db, settings.cache_path)
                # Flag any newly-added photos that fall under a hidden folder.
                if stats and (stats.get("added") or stats.get("new") or stats.get("indexed")):
                    try:
                        apply_hidden_folders_task.delay()
                    except Exception:
                        pass
                return stats
        finally:
            if r is not None:
                try:
                    await r.delete(lock_key); await r.aclose()
                except Exception:
                    pass

    return _run(_run_scan())


@celery_app.task(bind=True, name="purge_trash")
def purge_trash_task(self):
    """Permanently delete photos trashed longer than trash.retention_days
    (0/empty = keep forever). Removes the original file (+sidecars), cached
    thumbnails and the DB row."""
    async def _run_purge():
        from app.core.database import init_db, get_db
        from app.models.photo import Photo
        from app.services.settings_loader import load_settings
        from app.api.routes.photos import _hard_delete, _source_roots
        from sqlalchemy import select
        from datetime import timedelta
        init_db()
        async for db in get_db():
            s = await load_settings(db)
            try:
                days = int(s.get("trash.retention_days") or 0)
            except (TypeError, ValueError):
                days = 0
            if days <= 0:
                return {"skipped": "retention off"}
            delete_files = str(s.get("trash.delete_files", "true")).lower() != "false"
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            roots = await _source_roots(db)
            rows = (await db.execute(select(Photo).where(
                Photo.is_trashed == True,                       # noqa: E712
                Photo.trashed_at.isnot(None), Photo.trashed_at < cutoff,
            ).limit(2000))).scalars().all()
            for p in rows:
                await _hard_delete(db, p, delete_files, roots)
            await db.commit()
            return {"purged": len(rows)}
    return _run(_run_purge())


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


@celery_app.task(bind=True, name="reclaim_ai")
def reclaim_ai_task(self):
    """Fallback for the remote-worker flow: ai_photo yields its job when a remote
    GPU worker is alive. If remote is enabled but no worker has checked in, those
    photos would sit pending — so re-queue them locally. No-op when remote is off
    (the normal pipeline already covers it) or a worker is alive (it'll claim)."""
    async def _run_reclaim():
        from app.core.database import init_db, get_db
        from app.models.photo import Photo
        from app.services.settings_loader import load_settings
        from app.api.routes.remote import remote_worker_alive
        from sqlalchemy import select, or_
        from datetime import timedelta
        init_db()
        async for db in get_db():
            s = await load_settings(db)
            if str(s.get("remote.enabled", "false")).lower() != "true":
                return {"skipped": "remote off"}
            if await remote_worker_alive() > 0:
                return {"skipped": "worker alive"}
            cutoff = datetime.now(timezone.utc) - timedelta(seconds=300)
            q = select(Photo.id).where(
                Photo.is_video == False,                    # noqa: E712
                Photo.description.is_(None),
                Photo.ai_error == False,                    # noqa: E712
                Photo.thumb_large.isnot(None),
                or_(Photo.ai_claimed_at.is_(None), Photo.ai_claimed_at < cutoff),
            ).limit(200)
            ids = [r[0] for r in (await db.execute(q)).all()]
            for pid in ids:
                ai_photo_task.delay(pid)
            return {"requeued": len(ids)}
    return _run(_run_reclaim())


@celery_app.task(bind=True, name="scheduled_backup")
def scheduled_backup_task(self):
    """Run an automatic full backup when due (Settings → Backup: schedule).
    Self-paced: compares the newest db backup's age to the chosen interval, so
    the hourly beat tick only actually backs up daily/weekly."""
    async def _run_backup():
        import os
        import datetime as _dt
        from app.core.database import init_db, get_db
        from app.services.settings_loader import load_settings
        from app.services.backup import run_full_backup, list_backups, prune_backups
        from app.services.feature_log import log as flog
        init_db()
        async for db in get_db():
            s = await load_settings(db)
            sched = str(s.get("backup.schedule", "off")).lower()
            if sched not in ("daily", "weekly"):
                return {"skipped": "disabled"}
            interval_h = 24 if sched == "daily" else 168
            newest = next((f["created_at"] for f in list_backups() if f["type"] == "db"), None)
            if newest:
                try:
                    age = (_dt.datetime.now() - _dt.datetime.fromisoformat(newest)).total_seconds()
                    if age < interval_h * 3600 - 600:  # 10-min grace
                        return {"skipped": "not due"}
                except Exception:
                    pass
            keep = int(float(s.get("backup.keep_days", "30") or 30))
            remote = (s.get("backup.rclone_remote") or "").strip() or None
            incl_thumbs = str(s.get("backup.include_thumbnails", "true")).lower() != "false"
            try:
                res = await run_full_backup(os.getenv("DATABASE_URL"), os.getenv("CONFIG_PATH", "/config"),
                                            remote, os.getenv("CACHE_PATH", "/cache"),
                                            include_thumbnails=incl_thumbs, settings=s)
                deleted = prune_backups(keep)
                ok = res["db"]["ok"] and res["config"]["ok"] and (res["cache"]["ok"] or res["cache"].get("skipped"))
                flog("system", "INFO" if ok else "WARNING",
                     f"Geplantes Backup ({sched}): db={res['db']['ok']} thumbs={res['cache']['ok']} config={res['config']['ok']}, {deleted} alte entfernt")
                return {"ran": True, "ok": ok, "pruned": deleted}
            except Exception as e:
                flog("system", "ERROR", f"Geplantes Backup fehlgeschlagen: {str(e)[:200]}")
                return {"error": str(e)[:200]}
    return _run(_run_backup())


@celery_app.task(bind=True, name="mirror_originals")
def mirror_originals_task(self, force: bool = False):
    """Offsite mirror of the ORIGINAL photo/video files (one-way rclone sync with a
    recoverable dated remote trash). Self-paced like scheduled_backup: the beat tick
    is hourly, but a sync only runs when due per backup.mirror_schedule
    (off|daily|weekly), tracked via the backup.mirror_last timestamp setting.
    force=True (on-demand endpoint) bypasses the due check."""
    async def _run_mirror():
        import datetime as _dt
        from app.core.database import init_db, get_db
        from app.models.source import PhotoSource
        from app.models.settings import Setting
        from app.services.settings_loader import load_settings
        from app.services.backup import mirror_originals_to_remote
        from app.services.feature_log import log as flog
        from sqlalchemy import select
        init_db()
        async for db in get_db():
            s = await load_settings(db)
            remote = (s.get("backup.mirror_remote") or "").strip()
            if not remote:
                return {"skipped": "no remote"}
            sched = str(s.get("backup.mirror_schedule", "off")).lower()
            if not force:
                if sched not in ("daily", "weekly"):
                    return {"skipped": "disabled"}
                interval_h = 24 if sched == "daily" else 168
                last = (s.get("backup.mirror_last") or "").strip()
                if last:
                    try:
                        age = (_dt.datetime.utcnow() - _dt.datetime.fromisoformat(last)).total_seconds()
                        if age < interval_h * 3600 - 600:  # 10-min grace
                            return {"skipped": "not due"}
                    except Exception:
                        pass
            # Collect enabled source paths.
            sources = [r for (r,) in (await db.execute(
                select(PhotoSource.path).where(PhotoSource.enabled == True)  # noqa: E712
            )).all()]
            if not sources:
                return {"skipped": "no enabled sources"}
            flog("system", "INFO", f"Originale-Spiegelung gestartet → {remote} ({len(sources)} Quelle(n))")
            try:
                res = await mirror_originals_to_remote(sources, remote)
            except Exception as e:
                flog("system", "ERROR", f"Originale-Spiegelung fehlgeschlagen: {str(e)[:200]}")
                return {"error": str(e)[:200]}
            # Persist the last-run timestamp only on success (so a failure retries
            # next tick rather than waiting a full interval).
            if res.get("ok"):
                now = _dt.datetime.utcnow().isoformat()
                row = await db.get(Setting, "backup.mirror_last")
                if row:
                    row.value = now
                else:
                    db.add(Setting(key="backup.mirror_last", value=now))
                await db.commit()
            flog("system", "INFO" if res.get("ok") else "WARNING",
                 f"Originale-Spiegelung fertig: ok={res.get('ok')} ({len(res.get('sources', []))} Quelle(n))")
            return res
    return _run(_run_mirror())


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
                # grow_only: only assign loose faces to EXISTING people (light).
                # The heavy HDBSCAN that forms NEW clusters runs only on the manual
                # "Clustern" button — auto-running it on ~13k faces spiked CPU and
                # made the website hang. New clusters: user-triggered.
                res = await cluster_unassigned(db, grow_only=True)
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


@celery_app.task(bind=True, name="cluster_faces_full")
def cluster_faces_full_task(self):
    """Nightly FULL clustering — forms NEW people from the loose-face pool (the
    heavy HDBSCAN the 'Clustern' button runs), not just grow. This is why ~13k
    faces with embeddings sat unassigned: auto-cluster only grows existing people,
    and new-cluster formation was manual-only. Runs in the CPU worker at a quiet
    hour so it never blocks the website. Opt-out: face.auto_cluster_full=false."""
    async def _run_full():
        from app.core.database import init_db, get_db
        from app.services.settings_loader import load_settings
        init_db()
        async for db in get_db():
            s = await load_settings(db)
            if str(s.get("face.auto_cluster_full", "true")).lower() == "false":
                return {"skipped": "disabled"}
            try:
                from app.services.face_cluster import cluster_unassigned
                res = await cluster_unassigned(db)  # full: grow + form new clusters
            except ImportError:
                return {"skipped": "no sklearn"}
            return res
    return _run(_run_full())


@celery_app.task(bind=True, name="retry_failed_ai")
def retry_failed_ai_task(self):
    """Retry queue: re-enqueue photos whose AI failed (e.g. a Gemini outage) so a
    transient provider hiccup doesn't permanently drop them. Capped by ai_attempts
    so genuinely-bad media eventually stops being retried. Beat-scheduled."""
    async def _main():
        from app.core.database import init_db, get_db
        from app.models.photo import Photo
        from app.services.feature_log import log as flog
        from sqlalchemy import select, update
        init_db()
        MAX_ATTEMPTS = 20
        async for db in get_db():
            ids = [r for (r,) in (await db.execute(
                select(Photo.id).where(
                    Photo.ai_error == True, Photo.description.is_(None),  # noqa: E712
                    Photo.ai_attempts < MAX_ATTEMPTS, Photo.thumb_large.isnot(None),
                    Photo.is_missing == False,  # noqa: E712
                ).order_by(Photo.id).limit(2000)
            )).all()]
            if not ids:
                return {"retried": 0}
            await db.execute(update(Photo).where(Photo.id.in_(ids)).values(ai_error=False))
            await db.commit()
            flog("ai", "INFO", f"Retry-Queue: {len(ids)} fehlgeschlagene Fotos erneut eingereiht")
            for pid in ids:
                process_photo_task.delay(pid)
            return {"retried": len(ids)}
    return _run(_main())


@celery_app.task(bind=True, name="reap_stuck_photos")
def reap_stuck_photos_task(self):
    """Self-heal photos stuck at status=processing: a deploy/container-recreate (or
    max-tasks-per-child restart) kills process_photo mid-flight, leaving the row in
    'processing' forever even though the thumbnail work already finished. Those
    orphans both inflate the "noch in Verarbeitung"-counter AND get re-queued by the
    retry sweeps → the worker churns photos that are actually done. A photo that has
    a thumbnail and hasn't been touched in 30 min is no longer being worked → mark it
    done (faces/AI run off their own flags, not status). Beat-scheduled every 10 min."""
    async def _main():
        from app.core.database import init_db, get_db
        from app.models.photo import Photo, PhotoStatus
        from app.services.feature_log import log as flog
        from sqlalchemy import update, func
        import datetime
        init_db()
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=30)
        async for db in get_db():
            res = await db.execute(update(Photo).where(
                Photo.status == PhotoStatus.processing,
                Photo.thumb_small.isnot(None),
                Photo.updated_at < cutoff,
            ).values(status=PhotoStatus.done))
            await db.commit()
            n = res.rowcount or 0
            if n:
                flog("scanner", "INFO", f"Reaper: {n} hängende 'processing'-Foto(s) → done")
            return {"reaped": n}
    return _run(_main())


@celery_app.task(bind=True, name="apply_hidden_folders")
def apply_hidden_folders_task(self):
    """Sync Photo.is_hidden to the display.hidden_folders setting: photos under a
    listed folder are hidden from ALL display (face recognition still runs). Idempotent
    — only flips rows that disagree. Triggered on settings save + after a scan."""
    async def _main():
        from app.core.database import init_db, get_db
        from app.models.photo import Photo
        from app.services.settings_loader import load_settings
        from app.core.access import _esc
        from app.services.feature_log import log as flog
        from sqlalchemy import update, or_
        init_db()
        async for db in get_db():
            s = await load_settings(db)
            raw = (s.get("display.hidden_folders") or "").strip()
            folders = [p.strip().rstrip("/") for p in raw.replace("\n", ",").split(",") if p.strip()]
            if folders:
                cond = or_(*[Photo.path.like(f"{_esc(p)}/%", escape="\\") for p in folders])
                r1 = await db.execute(update(Photo).where(cond, Photo.is_hidden == False).values(is_hidden=True))  # noqa: E712
                r2 = await db.execute(update(Photo).where(~cond, Photo.is_hidden == True).values(is_hidden=False))  # noqa: E712
            else:
                r1 = await db.execute(update(Photo).where(Photo.is_hidden == True).values(is_hidden=False))  # noqa: E712
                r2 = None
            await db.commit()
            n_hidden = (r1.rowcount or 0)
            n_shown = (r2.rowcount or 0) if r2 is not None else (r1.rowcount or 0)
            if n_hidden or n_shown:
                flog("scanner", "INFO", f"Versteckte Ordner angewandt: {len(folders)} Ordner, "
                                        f"{n_hidden} versteckt / {n_shown} wieder sichtbar")
            return {"folders": len(folders)}
    return _run(_main())


@celery_app.task(bind=True, name="retry_missing_thumbnails")
def retry_missing_thumbnails_task(self):
    """Self-heal thumbnail gaps: re-queue EVERY photo still missing its large
    thumbnail, whether it was attempted-but-failed (e.g. a stubborn TIFF a newly
    added ImageMagick fallback can now decode) OR never attempted at all (a scan
    that enqueued newest-first and never reached the backlog — these have
    thumb_attempts = 0 and would otherwise sit forever). Capped by thumb_attempts
    so genuinely-undecodable files eventually stop. Beat-scheduled."""
    async def _main():
        from app.core.database import init_db, get_db
        from app.models.photo import Photo
        from app.services.feature_log import log as flog
        from sqlalchemy import select
        init_db()
        CAP = 5
        async for db in get_db():
            ids = [r for (r,) in (await db.execute(
                select(Photo.id).where(
                    Photo.thumb_large.is_(None), Photo.is_missing == False,  # noqa: E712
                    Photo.is_trashed == False,                               # noqa: E712
                    Photo.thumb_attempts < CAP,   # incl. 0 = never attempted
                ).order_by(Photo.id).limit(1000)
            )).all()]
            if not ids:
                return {"retried": 0}
            flog("scanner", "INFO", f"Thumbnail-Retry: {len(ids)} Foto(s) ohne Thumbnail erneut eingereiht")
            for pid in ids:
                process_photo_task.delay(pid, None, False, True)  # redo_thumbs=True
            return {"retried": len(ids)}
    return _run(_main())


# NOTE: person-name persistence is handled by write_faces_task (the "In Dateien
# schreiben" button → /people/write-faces), which writes MWG face regions carrying
# both the box AND the name (+ a PersonInImage mirror) into the file/sidecar. The
# old standalone write_person_name task was never wired to any endpoint and has
# been removed to avoid two divergent name-writing paths.


@celery_app.task(bind=True, name="reembed_imported")
def reembed_imported_faces_task(self):
    """Imported faces (recreated from MWG regions on re-import) have a box but NO
    embedding, so they can't be clustered/matched. Crop each region (with margin)
    from the image, run insightface on the crop to recover a proper ArcFace
    embedding, and flip the detector to 'insightface' so it re-joins clustering.
    Closes the recovery loop: a restored library can be re-clustered."""
    async def _main():
        from app.core.database import init_db, get_db
        from app.models.photo import Photo
        from app.models.face import Face
        from app.services.processing.thumbnails import open_image_for_ai
        from app.services.feature_log import log as flog
        from sqlalchemy import select, update
        init_db()
        async for db in get_db():
            from app.services import face_detect_insightface as fi
            if not fi.available():
                flog("faces", "WARNING", "Re-Embed: insightface nicht verfügbar")
                return {"reembedded": 0}
            rows = (await db.execute(
                select(Face.id, Face.photo_id, Face.bbox_x, Face.bbox_y, Face.bbox_w, Face.bbox_h)
                .where(Face.detector == "imported", Face.embedding.is_(None))
                .order_by(Face.photo_id)
            )).all()
            flog("faces", "INFO", f"Re-Embed importierter Gesichter: {len(rows)}")
            done = failed = via_orig = 0
            cache_pid, cache_thumb, cache_orig, cache_path = None, None, None, None

            def _embed_from(img, bx, by, bw, bh):
                """Crop the (margined) face region from img and run insightface.
                Returns the best embedding or None. Coords are normalised (0–1),
                so the same box works on a thumb or a full-res original."""
                if not img:
                    return None
                W, H = img.size
                mx, my = (bw or 0) * 0.6, (bh or 0) * 0.6  # 60% margin → better re-detect
                crop = img.crop((int(max(0.0, bx - mx) * W), int(max(0.0, by - my) * H),
                                 int(min(1.0, bx + bw + mx) * W), int(min(1.0, by + bh + my) * H)))
                faces = fi.detect_faces(crop, 0.3)  # low conf — we know it IS a face
                best = max(faces, key=lambda f: f.confidence or 0) if faces else None
                return best.embedding if (best and best.embedding) else None

            for fid, pid, bx, by, bw, bh in rows:
                try:
                    if pid != cache_pid:
                        photo = await db.get(Photo, pid)
                        cache_thumb = open_image_for_ai(
                            photo.thumb_large or photo.thumb_medium or photo.path) if photo else None
                        cache_orig, cache_path = None, (photo.path if photo else None)
                        cache_pid = pid
                    emb = _embed_from(cache_thumb, bx, by, bw, bh)
                    # Fallback: tiny/cropped faces aren't re-detectable on the ~1024px
                    # thumb. Retry on the ORIGINAL at high res (3000px) — recovers the
                    # small faces that otherwise stay stuck as 'imported' forever.
                    if emb is None and cache_path:
                        if cache_orig is None:
                            cache_orig = open_image_for_ai(cache_path, max_size=3000) or False
                        if cache_orig:
                            emb = _embed_from(cache_orig, bx, by, bw, bh)
                            if emb is not None:
                                via_orig += 1
                    if emb is None:
                        failed += 1; continue
                    await db.execute(update(Face).where(Face.id == fid).values(
                        embedding=emb, detector="insightface"))
                    done += 1
                    if (done + failed) % 50 == 0:
                        await db.commit()
                except Exception:
                    failed += 1
            await db.commit()
            flog("faces", "INFO",
                 f"Re-Embed fertig: {done} neu eingebettet ({via_orig} via Original), {failed} ohne Treffer")
            return {"reembedded": done, "failed": failed, "via_original": via_orig}
    return _run(_main())


@celery_app.task(bind=True, name="write_faces")
def write_faces_task(self):
    """Write EVERY photo's detected faces as MWG face regions (box + name where
    known) into the files — button-driven, run once face clustering has settled.
    Saves a future tool from re-running face DETECTION on the whole library.
    Images: embedded XMP. Videos (can't embed): a `.xmp` sidecar."""
    async def _main():
        from app.core.database import init_db, get_db
        from app.models.photo import Photo
        from app.models.face import Face
        from app.models.person import Person
        from app.services.exif_edit import write_face_regions
        from app.services.xmp_sidecar import write_sidecar
        from app.services.settings_loader import load_settings
        from app.services.feature_log import log as flog
        from sqlalchemy import select
        init_db()
        async for db in get_db():
            s = await load_settings(db)
            xmp_mode = str(s.get("xmp.write_mode", "off")).lower()
            pids = [p for (p,) in (await db.execute(
                select(Face.photo_id).where(Face.is_ignored == False).distinct()  # noqa: E712
            )).all()]
            flog("faces", "INFO", f"Gesichts-Regionen schreiben: {len(pids)} Foto(s) (Modus {xmp_mode})")
            done = failed = 0
            for pid in pids:
                photo = await db.get(Photo, pid)
                if not photo or photo.is_missing:
                    continue
                # ALL non-ignored faces — including unknown/loose ones. Unknown
                # faces get the box only (no name), so a future tool keeps the
                # coordinates and never has to re-detect; you just re-name them.
                rows = (await db.execute(
                    select(Face.bbox_x, Face.bbox_y, Face.bbox_w, Face.bbox_h, Person.name)
                    .join(Person, Person.id == Face.person_id, isouter=True)
                    .where(Face.photo_id == pid, Face.is_ignored == False)  # noqa: E712
                )).all()
                regions = [{
                    "cx": (x or 0) + (w or 0) / 2, "cy": (y or 0) + (h or 0) / 2,
                    "w": w or 0, "h": h or 0, "name": nm or "",
                } for (x, y, w, h, nm) in rows if w and h]
                if not regions:
                    continue
                # Placement follows xmp.write_mode, mirroring the describe path:
                #   embed into the image for file/file_sidecar (images only), and
                #   merge into the consolidated <name>.xmp sidecar for sidecar/
                #   file_sidecar — and ALWAYS for videos (can't embed). The button
                #   is an explicit "persist" action, so if the mode is "off" we
                #   still write a sidecar rather than silently doing nothing.
                want_embed = (xmp_mode in ("file", "file_sidecar")) and not photo.is_video
                want_sidecar = photo.is_video or xmp_mode in ("file_sidecar", "sidecar")
                if not want_embed and not want_sidecar:
                    want_sidecar = True
                try:
                    ok = True
                    if want_embed:
                        ok = await write_face_regions(photo.path, regions,
                                                      photo.width or 0, photo.height or 0)
                    if want_sidecar:
                        # Merges into the sidecar, preserving any description/tags
                        # a describe job already wrote there (and vice-versa).
                        write_sidecar(photo.path, faces=regions,
                                      width=photo.width or 0, height=photo.height or 0)
                    done += 1 if ok else 0
                    failed += 0 if ok else 1
                except Exception:
                    failed += 1
                if (done + failed) % 100 == 0:
                    flog("faces", "INFO", f"Gesichts-Regionen: {done} geschrieben, {failed} Fehler …")
            flog("faces", "INFO", f"Gesichts-Regionen fertig: {done} geschrieben, {failed} Fehler")
            return {"written": done, "failed": failed}
    return _run(_main())


@celery_app.task(bind=True, name="warm_face_crops")
def warm_face_crops_task(self):
    """Pre-generate the 256px face-crop cache for EVERY non-ignored face so the
    People page never has to crop on-demand. The expensive case is VIDEO faces:
    each uncached crop runs ffmpeg to pull the exact detected frame — so we check
    the cache FIRST and only extract when a crop is genuinely missing. Idempotent;
    re-running is cheap (all hits are skips)."""
    async def _main():
        from app.core.database import init_db, get_db
        from app.models.photo import Photo
        from app.models.face import Face
        from app.services.face_crop import crop_face, crop_cached
        from app.services.processing.thumbnails import extract_video_frame_bytes
        from app.services.feature_log import log as flog
        from sqlalchemy import select
        init_db()
        # Fetch EVERYTHING (face boxes + the photo fields crop_face needs) in ONE
        # query, then release the DB session. Crop generation runs ffmpeg per video
        # face and takes minutes over 30k faces — holding the session across it
        # tripped idle_in_transaction_session_timeout, killing the connection mid-run
        # ("connection was closed in the middle of operation") so warming never
        # finished. No DB is touched during the loop now.
        from app.models.photo import Photo as _P
        async for db in get_db():
            rows = (await db.execute(
                select(Face.id, Face.person_id, Face.bbox_x, Face.bbox_y, Face.bbox_w,
                       Face.bbox_h, Face.frame_time, _P.path, _P.thumb_large, _P.thumb_medium,
                       _P.is_video, _P.is_missing, _P.video_webm_path)
                .join(_P, _P.id == Face.photo_id)
                .where(Face.is_ignored == False)  # noqa: E712
                .order_by(Face.person_id.isnot(None).desc(), Face.photo_id)
            )).all()
            break
        flog("faces", "INFO", f"Crop-Cache vorbereiten: {len(rows)} Gesicht(er)")
        done = skipped = failed = 0
        import io, os
        from PIL import Image
        for (fid, person_id, bx, by, bw, bh, ft, p_path, p_large, p_medium,
             p_is_video, p_is_missing, p_webm) in rows:
            if p_is_missing:
                failed += 1
                continue
            pid = person_id or 0
            bbox = [bx, by, bw, bh]
            use_frame = bool(p_is_video) and ft is not None
            # The cache key matches whatever path crop_face will be called with:
            # the original video for frame-extracted faces, else the thumbnail.
            key_path = p_path if use_frame else (p_large or p_medium or p_path)
            if crop_cached(key_path, pid, fid):
                skipped += 1
                continue
            try:
                out = None
                if use_frame:
                    # SSD only: exact frame from the 1080p web MP4, else the video
                    # thumbnail — never ffmpeg the 4K original on the HDD.
                    src_img = None
                    vsrc = p_webm if (p_webm and os.path.exists(p_webm)) else None
                    if vsrc:
                        data = extract_video_frame_bytes(vsrc, float(ft))
                        if data:
                            src_img = Image.open(io.BytesIO(data))
                    if src_img is None:
                        thumb = p_large or p_medium
                        if thumb and os.path.exists(thumb):
                            src_img = Image.open(thumb)
                    if src_img is not None:
                        out = crop_face(p_path, bbox, pid, fid, source_image=src_img)
                else:
                    out = crop_face(key_path, bbox, pid, fid)
                if out:
                    done += 1
                else:
                    failed += 1
            except Exception:
                failed += 1
            if (done + failed) % 500 == 0 and (done + failed) > 0:
                flog("faces", "INFO", f"Crop-Cache: {done} erzeugt, {skipped} bereits da, {failed} Fehler …")
        flog("faces", "INFO", f"Crop-Cache fertig: {done} erzeugt, {skipped} bereits da, {failed} Fehler")
        return {"warmed": done, "skipped": skipped, "failed": failed}
    return _run(_main())


@celery_app.task(bind=True, name="verify_unnamed_faces")
def verify_unnamed_faces_task(self, limit: int = 20000, include_named: bool = True):
    """False-positive filter: re-run InsightFace on each face's cached CROP. A
    context-triggered FP (a hand/pattern/skin the full-image detector fired on)
    usually does NOT re-detect as a face once isolated → remove it. Conservative:
    only act when ZERO faces are found at a LOW threshold, so real faces survive.
    Reversible: sets is_ignored (off the grid); for a face that was wrongly
    clustered into a NAMED person, ALSO unassigns it (person_id=None) so the hand/
    pattern leaves that person. include_named=False restricts to unnamed only.
    Newest faces first (recent clusters are the usual FP source). Reads only the
    SSD crop, never the HDD original."""
    async def _main():
        import os
        from app.core.database import init_db, get_db
        from app.models.photo import Photo as _P
        from app.models.face import Face
        from app.services import face_detect_insightface as fdi
        from app.services.feature_log import log as flog
        from app.services.face_crop import crop_out_path
        from sqlalchemy import select, update as _upd
        from PIL import Image
        init_db()
        if not fdi.available():
            return {"skipped": "no insightface"}
        # phase 1: snapshot candidates + crop key in a SHORT session, then release.
        # (insightface over thousands of crops takes minutes — never hold the session
        # across it; same idle_in_transaction trap as the other heavy tasks.)
        async for db in get_db():
            rows = (await db.execute(
                select(Face.id, Face.person_id, _P.path, _P.thumb_large, _P.thumb_medium,
                       _P.is_video, Face.frame_time)
                .join(_P, _P.id == Face.photo_id)
                .where(Face.is_ignored == False, _P.is_missing == False)  # noqa: E712
                .order_by(Face.id.desc()).limit(limit)
            )).all()
            break
        flog("faces", "INFO", f"FP-Filter: prüfe {len(rows)} Gesicht(er) (inkl. benannte={include_named})")
        to_ignore, to_unassign = [], []
        checked = 0
        for fid, person_id, p_path, p_large, p_medium, p_is_video, ft in rows:
            if person_id is not None and not include_named:
                continue
            use_frame = bool(p_is_video) and ft is not None
            key_path = p_path if use_frame else (p_large or p_medium or p_path)
            cp = str(crop_out_path(key_path, person_id or 0, fid))
            if not os.path.exists(cp):
                continue  # no cached crop yet → warm task will make it, next run verifies
            try:
                found = fdi.detect_faces(Image.open(cp), min_conf=0.35)
            except Exception:
                continue
            checked += 1
            if not found:
                to_ignore.append(fid)
                if person_id is not None:
                    to_unassign.append(fid)
        # phase 3: apply removals in short batched sessions
        unassign_set = set(to_unassign)
        for i in range(0, len(to_ignore), 300):
            batch = to_ignore[i:i + 300]
            unb = [f for f in batch if f in unassign_set]
            async for db in get_db():
                await db.execute(_upd(Face).where(Face.id.in_(batch)).values(is_ignored=True))
                if unb:
                    await db.execute(_upd(Face).where(Face.id.in_(unb)).values(person_id=None))
                await db.commit()
                break
        flog("faces", "INFO", f"FP-Filter fertig: {checked} geprüft, {len(to_ignore)} entfernt ({len(to_unassign)} von Personen gelöst)")
        return {"checked": checked, "ignored": len(to_ignore), "unassigned": len(to_unassign)}
    return _run(_main())


@celery_app.task(bind=True, name="detect_faces_local")
def detect_faces_local_task(self, photo_id: int):
    """Detect faces on the SERVER with insightface (buffalo_l, CPU) — DECOUPLED
    from the slow description pass. Same model as the remote agent → compatible
    embeddings + same aspect-ratio gate. Reads thumb_large directly (no HTTP),
    idempotent, skips photos that already have faces."""
    async def _main():
        from app.core.database import init_db, get_db
        from app.models.photo import Photo
        from app.models.face import Face
        from app.services.settings_loader import load_settings
        from app.services.processing.thumbnails import open_image_for_ai
        from app.services.feature_log import log as flog
        from sqlalchemy import select, func as _func
        init_db()
        async for db in get_db():
            photo = await db.get(Photo, photo_id)
            if not photo or photo.is_missing or photo.is_video:
                return
            if await db.scalar(select(_func.count()).where(Face.photo_id == photo_id)):
                photo.faces_scanned = True
                await db.commit()
                return
            from app.services import face_detect_insightface as fi
            if not fi.available():
                return
            s = await load_settings(db)
            if str(s.get("faces.enabled", "true")).lower() == "false":
                return
            img = open_image_for_ai(photo.thumb_large or photo.thumb_medium or photo.path)
            if img is None:
                photo.faces_scanned = True
                await db.commit()
                return
            W, H = img.size
            min_conf = float(s.get("face.min_confidence", "0.7") or 0.7)
            min_px = float(s.get("face.min_size_px", "40") or 0)
            cxs, cys, added = [], [], 0
            for f in fi.detect_faces(img, min_conf):
                if min_px > 0 and (f.bbox_h * H < min_px or f.bbox_w * W < min_px):
                    continue
                ar = (f.bbox_w / f.bbox_h) if f.bbox_h else 0.0
                if ar < 0.45 or ar > 1.8:   # same non-face gate as the remote path
                    continue
                db.add(Face(photo_id=photo_id, bbox_x=f.bbox_x, bbox_y=f.bbox_y,
                            bbox_w=f.bbox_w, bbox_h=f.bbox_h, confidence=f.confidence,
                            embedding=f.embedding, detector="insightface"))
                cxs.append(f.bbox_x + f.bbox_w / 2); cys.append(f.bbox_y + f.bbox_h / 2); added += 1
            if cxs:
                photo.focus_x = min(1.0, max(0.0, sum(cxs) / len(cxs)))
                photo.focus_y = min(1.0, max(0.0, sum(cys) / len(cys)))
            photo.faces_scanned = True
            await db.commit()
            if added:
                flog("faces", "INFO", f"{added} Gesicht(er) (lokal insightface): {photo.filename}")
    return _run(_main())


@celery_app.task(bind=True, name="sweep_faces_local")
def sweep_faces_local_task(self):
    """Enqueue local face detection for every image still lacking a face pass, so
    faces finish in parallel to (and independently of) the slow descriptions."""
    async def _main():
        from app.core.database import init_db, get_db
        from app.models.photo import Photo
        from app.models.face import Face
        from app.services.feature_log import log as flog
        from sqlalchemy import select, exists as _exists
        init_db()
        async for db in get_db():
            pids = (await db.execute(select(Photo.id).where(
                Photo.thumb_large.isnot(None), Photo.is_video == False,  # noqa: E712
                Photo.is_missing == False, Photo.faces_scanned == False,  # noqa: E712
                ~_exists().where(Face.photo_id == Photo.id),
            ).order_by(Photo.id))).scalars().all()
            flog("faces", "INFO", f"Lokale Gesichtserkennung gestartet: {len(pids)} Bild(er) eingereiht")
            for pid in pids:
                detect_faces_local_task.delay(pid)
            return {"queued": len(pids)}
    return _run(_main())


@celery_app.task(bind=True, name="detect_video_faces")
def detect_video_faces_task(self, photo_id: int):
    """Detect faces in a VIDEO: sample frames from the 1080p web MP4 (SSD, never the
    HDD original), run insightface on each, then DEDUP across frames by ArcFace
    cosine so a person appearing in many frames becomes ONE face record (with its
    best frame + frame_time). Embeddings drop into the same ArcFace space → cluster
    with photo faces. Idempotent; skips videos that already have faces."""
    async def _main():
        import io, os
        import numpy as np
        from app.core.database import init_db, get_db
        from app.models.photo import Photo
        from app.models.face import Face
        from app.services.settings_loader import load_settings
        from app.services.processing.thumbnails import extract_video_frame_bytes, video_duration
        from app.services import face_detect_insightface as fi
        from app.services.feature_log import log as flog
        from sqlalchemy import select, func as _func
        from PIL import Image
        init_db()
        # ── phase 1: read params in a SHORT session, then release it. The frame
        # sampling below runs ffmpeg+insightface for up to 30 frames (often >60s);
        # holding the DB session across that tripped idle_in_transaction_session_timeout
        # → "connection was closed in the middle of operation" on commit → the task
        # failed + retried forever, clogging the cpu queue. So: gather → release →
        # work → reopen to write.
        params = None
        async for db in get_db():
            photo = await db.get(Photo, photo_id)
            if not photo or not photo.is_video or photo.is_missing:
                return
            if await db.scalar(select(_func.count()).where(Face.photo_id == photo_id)):
                photo.faces_scanned = True; await db.commit(); return
            if not fi.available():
                return
            s = await load_settings(db)
            if str(s.get("faces.enabled", "true")).lower() == "false":
                return
            if str(s.get("video.face_recognition", "true")).lower() == "false":
                photo.faces_scanned = True; await db.commit(); return
            src = photo.video_webm_path
            if not src or not os.path.exists(src):
                return  # 1080p web version not ready yet — sweep will retry later
            dur = photo.duration_seconds or video_duration(src) or 0
            if dur <= 0:
                photo.faces_scanned = True; await db.commit(); return
            params = {
                "src": src, "dur": dur, "filename": photo.filename,
                "n": max(8, min(30, int(dur / 3) + 1)),   # frame count scales with duration
                "min_conf": float(s.get("video.face_min_confidence", "0.6") or 0.6),
                "min_px": float(s.get("face.min_size_px", "40") or 0),
                "sim": float(s.get("video.face_dedup_sim", "0.45") or 0.45),
            }
            break
        if not params:
            return

        # ── phase 2: sample frames + detect — NO db session held over this slow work ──
        src, dur, n = params["src"], params["dur"], params["n"]
        min_conf, min_px, sim = params["min_conf"], params["min_px"], params["sim"]
        reps = []  # [{emb: np, det: {f, ts}}] — one per distinct person in the clip
        for i in range(n):
            ts = round((i + 0.5) * dur / n, 2)
            data = extract_video_frame_bytes(src, ts)
            if not data:
                continue
            try:
                img = Image.open(io.BytesIO(data))
            except Exception:
                continue
            W, H = img.size
            for f in fi.detect_faces(img, min_conf):
                if min_px > 0 and (f.bbox_h * H < min_px or f.bbox_w * W < min_px):
                    continue
                ar = (f.bbox_w / f.bbox_h) if f.bbox_h else 0.0
                if ar < 0.45 or ar > 1.8:
                    continue
                emb = np.asarray(f.embedding, dtype="float32")
                matched = False
                for rep in reps:
                    if float(np.dot(emb, rep["emb"])) >= sim:  # ArcFace normed → cosine
                        if f.confidence > rep["det"]["f"].confidence:
                            rep["det"] = {"f": f, "ts": ts}; rep["emb"] = emb
                        matched = True
                        break
                if not matched:
                    reps.append({"emb": emb, "det": {"f": f, "ts": ts}})

        # ── phase 3: persist in a fresh SHORT session ──
        async for db in get_db():
            photo = await db.get(Photo, photo_id)
            if not photo:
                return
            if await db.scalar(select(_func.count()).where(Face.photo_id == photo_id)):
                photo.faces_scanned = True; await db.commit(); return  # a concurrent run won
            added = 0
            for rep in reps:
                f = rep["det"]["f"]
                db.add(Face(photo_id=photo_id, bbox_x=f.bbox_x, bbox_y=f.bbox_y,
                            bbox_w=f.bbox_w, bbox_h=f.bbox_h, confidence=f.confidence,
                            embedding=f.embedding, frame_time=rep["det"]["ts"],
                            detector="insightface"))
                added += 1
            photo.faces_scanned = True
            await db.commit()
            if added:
                flog("faces", "INFO", f"{added} Person(en) im Video erkannt: {params['filename']}")
            break
    return _run(_main())


@celery_app.task(bind=True, name="sweep_video_faces")
def sweep_video_faces_task(self, limit: int = 400):
    """Enqueue video face detection for videos that have a 1080p web version but no
    face pass yet. Nightly + on-demand; gated by the transcode (needs the SSD mp4)."""
    async def _main():
        from app.core.database import init_db, get_db
        from app.models.photo import Photo
        from app.services.feature_log import log as flog
        from sqlalchemy import select
        init_db()
        async for db in get_db():
            pids = (await db.execute(select(Photo.id).where(
                Photo.is_video == True, Photo.faces_scanned == False,  # noqa: E712
                Photo.video_webm_path.isnot(None), Photo.is_missing == False,  # noqa: E712
                Photo.is_trashed == False,  # noqa: E712
            ).order_by(Photo.id).limit(limit))).scalars().all()
            flog("faces", "INFO", f"Video-Gesichtserkennung: {len(pids)} Video(s) eingereiht")
            for pid in pids:
                detect_video_faces_task.delay(pid)
            return {"queued": len(pids)}
    return _run(_main())


@celery_app.task(bind=True, name="backfill_xmp")
def backfill_xmp_task(self, full: bool = False):
    """Write the existing DB AI description + tags INTO the image files for every
    described photo (honours xmp.write_mode). One-off repair for photos that were
    described while xmp.write_mode was still 'off' (the default) and only got the
    description in the DB. Idempotent — exiftool overwrites.

    full=False (nightly self-heal): only photos NOT yet stamped
    (xmp_sidecar_written is not True) → cheap, just closes new gaps.
    full=True (manual one-off): re-stamp EVERY described photo, also fixing stale
    in-file copies that lag behind a re-description."""
    async def _main():
        from app.core.database import init_db, get_db
        from app.models.photo import Photo
        from app.models.tag import Tag, PhotoTag
        from app.services.settings_loader import load_settings
        from app.services.feature_log import log as flog
        from app.services.exif_edit import write_description as _wd, write_keywords as _wk, ensure_capture_date as _ecd, write_rating as _wr
        from app.services.xmp_sidecar import write_sidecar
        from sqlalchemy import select, or_, update as _upd
        from collections import defaultdict
        init_db()
        # ── phase 1: snapshot ALL work + tags in a SHORT session, then release it.
        # The exiftool writes below take ~1-3s EACH over thousands of files (hours);
        # holding the DB session across that tripped idle_in_transaction_session_timeout
        # and killed the backfill mid-run. So: snapshot → write files (no session) →
        # reopen briefly to persist derived dates / sidecar paths.
        items, mode = [], "off"
        async for db in get_db():
            s = await load_settings(db)
            mode = str(s.get("xmp.write_mode", "off")).lower()
            if mode not in ("file", "file_sidecar", "sidecar"):
                flog("ai", "WARNING", "Backfill übersprungen: xmp.write_mode=off")
                return {"skipped": "xmp.write_mode=off"}
            # Cover everything that carries durable user info: a description, OR a
            # rating/favourite (those may have no description but must still be
            # stamped into the file so they survive a solution switch).
            conds = [
                Photo.is_missing == False,  # noqa: E712
                or_(Photo.description.isnot(None), Photo.is_favorite == True,  # noqa: E712
                    Photo.user_rating.isnot(None)),
            ]
            if not full:
                # nightly self-heal: only photos that were never stamped into a file
                conds.append(or_(Photo.xmp_sidecar_written == False,  # noqa: E712
                                 Photo.xmp_sidecar_written.is_(None)))
            photos = (await db.execute(
                select(Photo).where(*conds).order_by(Photo.id)
            )).scalars().all()
            tagmap = defaultdict(list)
            for pid, name in (await db.execute(
                select(PhotoTag.photo_id, Tag.name).join(Tag, Tag.id == PhotoTag.tag_id)
            )).all():
                tagmap[pid].append(name)
            items = [{
                "id": p.id, "path": p.path, "filename": p.filename, "description": p.description,
                "title": p.title, "city": p.city, "country": p.country,
                "latitude": p.latitude, "longitude": p.longitude,
                "user_rating": p.user_rating, "is_favorite": p.is_favorite,
                "taken_at": p.taken_at, "kw": tagmap.get(p.id, []),
            } for p in photos]
            break
        flog("ai", "INFO", f"XMP-Backfill gestartet: {len(items)} Fotos (Modus={mode})")

        # ── phase 2: write files in CHUNKS — write a chunk (no session), then stamp
        # just that chunk in a short session. Progress is visible live (stamped count
        # grows) and an interruption keeps every completed chunk (no all-or-nothing).
        from app.services.exif_edit import write_all as _wall
        from app.services.xmp_sidecar import file_capture_date
        done = failed = 0
        CH = 100
        for start in range(0, len(items), CH):
            chunk = items[start:start + CH]
            stamps = []  # (id, taken_at_or_None, xmp_path_or_None)
            for it in chunk:
                try:
                    new_taken = None
                    xmp_path = None
                    if mode in ("file", "file_sidecar"):
                        set_date = await _ecd(it["path"])
                        if set_date and it["taken_at"] is None:
                            try:
                                new_taken = datetime.strptime(set_date[:19], "%Y:%m:%d %H:%M:%S")
                            except Exception:
                                new_taken = None
                        # ONE exiftool call for description+keywords+rating+title+place
                        # (favourite = 5 stars) — ~5× faster than the old per-field spawns.
                        eff = 5 if it["is_favorite"] else int(it["user_rating"] or 0)
                        await _wall(it["path"], description=it["description"],
                                    keywords=it["kw"] or None, rating=(eff if eff > 0 else None),
                                    title=it["title"], city=it["city"], country=it["country"])
                    if mode in ("file_sidecar", "sidecar"):
                        cap = it["taken_at"] or new_taken or file_capture_date(it["path"])
                        if cap and it["taken_at"] is None and new_taken is None:
                            new_taken = cap
                        xmp_path = write_sidecar(
                            it["path"], description=it["description"], title=it["title"],
                            keywords=it["kw"] or None, latitude=it["latitude"], longitude=it["longitude"],
                            city=it["city"], country=it["country"],
                            capture_date=cap.strftime("%Y-%m-%dT%H:%M:%S") if cap else None,
                        )
                    stamps.append((it["id"], new_taken, xmp_path))
                    done += 1
                except Exception as e:
                    failed += 1
                    flog("ai", "WARNING", f"XMP-Backfill-Fehler: {it['filename']}: {str(e)[:120]}")
            # stamp this chunk (mark written so progress shows + nightly skips it)
            async for db in get_db():
                for pid, taken, xpath in stamps:
                    vals = {"xmp_sidecar_written": True}
                    if taken is not None:
                        vals["taken_at"] = taken
                    if xpath:
                        vals["xmp_sidecar_path"] = xpath
                    await db.execute(_upd(Photo).where(Photo.id == pid).values(**vals))
                await db.commit()
                break
            flog("ai", "INFO", f"XMP-Backfill: {done}/{len(items)} geschrieben ({failed} Fehler)")
        flog("ai", "INFO", f"XMP-Backfill fertig: {done} geschrieben, {failed} Fehler")
        # NOTE: person names (XMP:PersonInImage) are intentionally NOT written
        # here — they are persisted separately via the explicit "Namen schreiben"
        # button (POST /people/write-names) once face clustering has settled.
        return {"written": done, "failed": failed}
    return _run(_main())


@celery_app.task(bind=True, name="backfill_geo")
def backfill_geo_task(self, limit: int = 60000):
    """Reverse-geocode GPS photos that have no place name yet, OFFLINE (bundled
    ~150k-city DB, no external request) → sets city + region (location_name) so the
    map's 'Ort suchen' and the detail 'Ort' line work. Idempotent: only photos
    still missing a city. Nightly + on-demand."""
    async def _main():
        from app.core.database import init_db, get_db
        from app.models.photo import Photo
        from app.services.feature_log import log as flog
        from sqlalchemy import select, update as _upd, or_
        init_db()
        async for db in get_db():
            rows = (await db.execute(select(Photo.id, Photo.latitude, Photo.longitude).where(
                Photo.latitude.isnot(None), Photo.longitude.isnot(None),
                or_(Photo.city.is_(None), Photo.city == ""),
                Photo.is_trashed == False,  # noqa: E712
            ).limit(limit))).all()
            break
        if not rows:
            return {"geocoded": 0}
        try:
            import reverse_geocoder as rg
        except Exception:
            flog("scanner", "WARNING", "Reverse-Geocoding übersprungen: reverse_geocoder fehlt")
            return {"skipped": "no reverse_geocoder"}
        flog("scanner", "INFO", f"Reverse-Geocoding (offline): {len(rows)} Foto(s)")
        # mode=1 = single-threaded; mode=2 (multiprocessing) can hang in containers.
        results = rg.search([(float(r[1]), float(r[2])) for r in rows], mode=1)
        updates = []
        for r, res in zip(rows, results):
            city = (res.get("name") or "").strip()
            region = (res.get("admin1") or "").strip()
            if city or region:
                updates.append((r[0], city or None, region or None))
        done = 0
        for i in range(0, len(updates), 500):
            async for db in get_db():
                for pid, city, region in updates[i:i + 500]:
                    vals = {}
                    if city:
                        vals["city"] = city
                    if region:
                        vals["location_name"] = region
                    if vals:
                        await db.execute(_upd(Photo).where(Photo.id == pid).values(**vals))
                        done += 1
                await db.commit()
                break
        flog("scanner", "INFO", f"Reverse-Geocoding fertig: {done} Orte gesetzt")
        return {"geocoded": done}
    return _run(_main())


@celery_app.task(bind=True, name="backfill_metadata")
def backfill_metadata_task(self, limit: int = 200000):
    """Fast date+GPS(+city) backfill straight from EXIF via batched exiftool — for
    photos the slow process_photo queue hasn't reached yet. Idempotent: only fills
    NULL taken_at / latitude. Runs on the 'scan' queue so it doesn't wait behind the
    process_photo cpu backlog → the map + timeline populate without a multi-hour wait."""
    async def _main():
        import json, subprocess, datetime as _dt
        from app.core.database import init_db, get_db
        from app.models.photo import Photo
        from app.services.feature_log import log as flog
        from sqlalchemy import select, update as _upd, or_
        init_db()

        def _parse_dt(s):
            if not s or not isinstance(s, str):
                return None
            s = s.strip().split(".")[0].split("+")[0].strip()
            for f in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
                try: return _dt.datetime.strptime(s, f)
                except Exception: pass
            return None

        async for db in get_db():
            rows = (await db.execute(select(Photo.id, Photo.path).where(
                or_(Photo.taken_at.is_(None), Photo.latitude.is_(None)),
                Photo.is_trashed == False, Photo.is_missing == False  # noqa: E712
            ).limit(limit))).all()
            break
        by_path = {p: i for (i, p) in rows}
        paths = list(by_path.keys())
        if not paths:
            return {"checked": 0, "dates": 0, "gps": 0}
        flog("scanner", "INFO", f"Metadaten-Backfill: {len(paths)} Foto(s) (Datum/GPS aus EXIF)")
        dt_set = gps_set = 0
        geo = []  # (id, lat, lon)
        CH = 400
        for k in range(0, len(paths), CH):
            chunk = paths[k:k + CH]
            try:
                out = subprocess.run(["exiftool", "-j", "-n", "-api", "largefilesupport=1",
                    "-DateTimeOriginal", "-CreateDate", "-GPSLatitude", "-GPSLongitude",
                    *chunk], capture_output=True, timeout=900)
                data = json.loads(out.stdout.decode("utf-8", "replace") or "[]")
            except Exception:
                continue
            ups = []
            for d in data:
                pid = by_path.get(d.get("SourceFile"))
                if pid is None:
                    continue
                vals = {}
                taken = _parse_dt(d.get("DateTimeOriginal") or d.get("CreateDate"))
                if taken: vals["taken_at"] = taken
                lat, lon = d.get("GPSLatitude"), d.get("GPSLongitude")
                if isinstance(lat, (int, float)) and isinstance(lon, (int, float)) and (lat or lon):
                    vals["latitude"] = float(lat); vals["longitude"] = float(lon)
                    geo.append((pid, float(lat), float(lon)))
                if vals: ups.append((pid, vals))
            if ups:
                async for db in get_db():
                    for pid, vals in ups:
                        await db.execute(_upd(Photo).where(Photo.id == pid).values(**vals))
                        if "taken_at" in vals: dt_set += 1
                        if "latitude" in vals: gps_set += 1
                    await db.commit(); break
        # reverse-geocode the freshly set coordinates (offline)
        try:
            import reverse_geocoder as rg
            if geo:
                res = rg.search([(la, lo) for (_, la, lo) in geo], mode=1)
                for (pid, _, _), r in zip(geo, res):
                    v = {}
                    if (r.get("name") or "").strip(): v["city"] = r["name"].strip()
                    if (r.get("admin1") or "").strip(): v["location_name"] = r["admin1"].strip()
                    if v:
                        async for db in get_db():
                            await db.execute(_upd(Photo).where(Photo.id == pid).values(**v))
                            await db.commit(); break
        except Exception:
            pass
        flog("scanner", "INFO", f"Metadaten-Backfill fertig: {dt_set} Datum, {gps_set} GPS gesetzt")
        return {"checked": len(paths), "dates": dt_set, "gps": gps_set}
    return _run(_main())


@celery_app.task(bind=True, name="suggest_faces")
def suggest_faces_task(self, low: Optional[float] = None, margin: Optional[float] = None,
                       topk: Optional[int] = None, min_exemplars: Optional[int] = None):
    """For each unassigned face, suggest the most-likely NAMED person using a ROBUST
    per-person score: the MEAN of that person's top-K most-similar exemplars — NOT a
    single nearest exemplar (1-NN). Why: 1-NN let whoever has the most exemplars win by
    sheer count (a noisy frame landed on Lea because one of her ~hundreds of exemplars was
    incidentally closest), and one stray/mislabeled exemplar could drag in random faces.
    Top-K mean is robust to both. A suggestion is stored ONLY if:
      • the person has >= `min_exemplars` exemplars (face.suggest_min_exemplars, 3), AND
      • its top-K-mean score >= `low` (face.suggest_min_score, 0.42) — NO upper cap, so the
        genuinely strong matches (sim ≥0.5, even near-duplicates at ~1.0) surface as the BEST
        suggestions; the old `sc < thr` cap wrongly dropped exactly those, leaving obvious
        faces of known people permanently unassigned, AND
      • it beats the 2nd-best PERSON's score by >= `margin` (face.suggest_margin, 0.06) —
        distinctiveness is now between PERSONS, not between individual exemplar faces.
    All bars are settings-driven so they can be tuned without a redeploy. Chunked (no OOM).
    Scan queue. Clears stale suggestions first so a re-run prunes the old junk."""
    async def _main():
        import numpy as np
        from collections import Counter
        from app.core.database import init_db, get_db
        from app.models.face import Face
        from app.models.person import Person
        from app.services.settings_loader import load_settings
        from app.services.feature_log import log as flog
        from sqlalchemy import select, update as _upd
        init_db()
        async for db in get_db():
            s = await load_settings(db)
            engine = str(s.get("face.engine", "insightface")).lower()
            floor = low if low is not None else float(s.get("face.suggest_min_score", "0.42") or 0.42)
            mrg = margin if margin is not None else float(s.get("face.suggest_margin", "0.06") or 0.06)
            K = int(topk if topk is not None else int(s.get("face.suggest_topk", "3") or 3))
            min_ex = int(min_exemplars if min_exemplars is not None
                         else int(s.get("face.suggest_min_exemplars", "3") or 3))
            cmin = float(s.get("face.cluster_min_confidence", "0.65") or 0.65)
            # Reset previous suggestions (re-run prunes old, too-loose matches).
            await db.execute(_upd(Face).where(Face.suggested_person_id.isnot(None))
                             .values(suggested_person_id=None, suggested_score=None))
            await db.commit()
            named_ids = [pid for (pid,) in (await db.execute(
                select(Person.id).where(Person.name != ""))).all()]
            if not named_ids:
                return {"suggested": 0}
            ex = (await db.execute(select(Face.person_id, Face.embedding).where(
                Face.person_id.in_(named_ids), Face.embedding.isnot(None),
                Face.detector == engine))).all()
            un = (await db.execute(select(Face.id, Face.embedding).where(
                Face.person_id == None, Face.is_ignored == False,  # noqa: E711,E712
                Face.embedding.isnot(None), Face.detector == engine,
                Face.confidence >= cmin))).all()
            break
        if not ex or not un:
            return {"suggested": 0}

        def _norm(a):
            n = np.linalg.norm(a, axis=-1, keepdims=True); return a / np.clip(n, 1e-9, None)
        E = _norm(np.array([e for _, e in ex], dtype="float32"))
        Ep = np.array([p for p, _ in ex])
        # Only persons with enough exemplars can receive suggestions; precompute their columns.
        plist = [int(p) for p in np.unique(Ep) if int((Ep == p).sum()) >= min_ex]
        if not plist:
            flog("scanner", "INFO", f"Gesichts-Vorschläge: 0 (keine Person mit ≥ {min_ex} Exemplaren)")
            return {"suggested": 0}
        cols = {p: np.where(Ep == p)[0] for p in plist}

        ids = [r[0] for r in un]
        X = _norm(np.array([r[1] for r in un], dtype="float32"))
        sug = 0
        per_person: Counter = Counter()
        P = len(plist)
        CH = 500                                              # 500×61k×4B ≈ 122 MB/chunk (OOM-safe)
        for c0 in range(0, len(ids), CH):
            Xc = X[c0:c0 + CH]
            sims = Xc @ E.T                                   # (n, M) cosine to every exemplar
            n = Xc.shape[0]
            pscore = np.full((n, P), -1.0, dtype="float32")
            for j, p in enumerate(plist):                     # robust per-person score = top-K mean
                cs = sims[:, cols[p]]
                kk = min(K, cs.shape[1])
                part = np.partition(cs, cs.shape[1] - kk, axis=1)[:, -kk:]
                pscore[:, j] = part.mean(axis=1)
            order = np.argsort(-pscore, axis=1)
            best = order[:, 0]
            sb = pscore[np.arange(n), best]
            second = (pscore[np.arange(n), order[:, 1]] if P > 1
                      else np.full(n, -1.0, dtype="float32"))
            updates = []
            for k in range(n):
                sc = float(sb[k])
                if sc < floor:                               # NO upper cap: strong matches (≥0.5,
                    continue                                 # incl. near-duplicates) are the BEST
                if float(second[k]) > sc - mrg:              # suggestions — old code wrongly dropped
                    continue                                 # them via sc<thr → they stayed unassigned
                    continue
                pid = plist[int(best[k])]
                updates.append((ids[c0 + k], pid, sc))
                per_person[pid] += 1
            if updates:
                async for db in get_db():
                    for fid, pid, sc in updates:
                        await db.execute(_upd(Face).where(Face.id == fid).values(
                            suggested_person_id=pid, suggested_score=sc))
                    await db.commit(); break
                sug += len(updates)
        top = ", ".join(f"{pid}×{c}" for pid, c in per_person.most_common(5))
        flog("scanner", "INFO",
             f"Gesichts-Vorschläge: {sug} (Top-{K}-Mittel ≥ {floor}, Marge {mrg}); häufigste {top}")
        return {"suggested": sug}
    return _run(_main())


@celery_app.task(bind=True, name="transcode_video")
def transcode_video_task(self, photo_id: int, resolution: int = 1080):
    """On-demand: produce a web-optimised H.264 MP4 (HW/QSV, +faststart) so the
    player starts instantly instead of downloading the un-streamable original.
    Triggered lazily by the stream endpoint; single-flight via a Redis lock."""
    async def _run_tc():
        import os, subprocess, pathlib, time as _t
        from app.core.database import init_db, get_db
        from app.models.photo import Photo
        from app.core.config import get_settings
        from app.services.hw_accel import detect_hw, build_transcode_cmd
        from app.services.feature_log import log as flog
        init_db()
        settings = get_settings()
        r = None
        try:
            import redis.asyncio as aioredis
            r = aioredis.from_url(settings.redis_url)
            if not await r.set(f"transcode:lock:{photo_id}", "1", nx=True, ex=3600):
                await r.aclose(); return {"skipped": "running"}
        except Exception:
            r = None
        tmp_path = None
        try:
            out_dir = pathlib.Path(settings.cache_path) / "videos"
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / f"{photo_id}_{resolution}.mp4"
            tmp_path = out_dir / f"{photo_id}_{resolution}.mp4.part"

            def _probe_ok(p):
                """A transcode is only usable if ffprobe reads a positive duration —
                catches truncated / no-moov files left by an interrupted ffmpeg run."""
                try:
                    pr = subprocess.run(
                        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                         "-of", "csv=p=0", str(p)], capture_output=True, timeout=60)
                    d = (pr.stdout or b"").decode().strip()
                    return pr.returncode == 0 and d not in ("", "N/A") and float(d) > 0
                except Exception:
                    return False
            # 1) SHORT session: resolve the source path / early-exit if cached. We
            #    must NOT hold a DB transaction open across the long ffmpeg run —
            #    idle_in_transaction_session_timeout (60s) would kill the connection
            #    on big 4K transcodes and the final commit would fail (→ task error
            #    → re-queue → the queue never drains).
            src_path = fname = None
            async for db in get_db():
                photo = await db.get(Photo, photo_id)
                if not photo or not photo.is_video:
                    return {"error": "not a video"}
                src_path, fname = photo.path, photo.filename
                if out_path.exists():
                    if _probe_ok(out_path):
                        photo.video_webm_path = str(out_path); await db.commit()
                        return {"cached": True}
                    # Broken leftover from an interrupted run — drop it (and clear a
                    # stale path) so we re-transcode instead of serving a no-moov torso.
                    try: out_path.unlink()
                    except Exception: pass
                    if photo.video_webm_path:
                        photo.video_webm_path = None; await db.commit()
                break
            # 2) Transcode to a .part file — NO DB session held while ffmpeg runs.
            hw = detect_hw()
            t0 = _t.time()
            cmd = build_transcode_cmd(src_path, str(tmp_path), resolution=resolution, codec="h264", hw=hw)
            proc = subprocess.run(cmd, capture_output=True, timeout=1800)
            ok = proc.returncode == 0 and tmp_path.exists() and _probe_ok(tmp_path)
            if not ok:
                # Software fallback — same no-upscale cap as build_transcode_cmd.
                _long = int(resolution * 16 / 9)
                sw_scale = (f"scale=w='min({_long},iw)':h='min({_long},ih)'"
                            ":force_original_aspect_ratio=decrease:force_divisible_by=2")
                import os as _os
                _ff_threads = _os.environ.get("FFMPEG_THREADS", "3")
                sw = ["ffmpeg", "-y", "-i", src_path, "-c:v", "libx264",
                      "-threads", _ff_threads,  # cap cores so the UI stays responsive
                      "-vf", sw_scale, "-map", "0:v:0?", "-map", "0:a:0?", "-dn", "-sn",
                      "-c:a", "aac", "-b:a", "128k",
                      "-movflags", "+faststart", str(tmp_path)]
                proc = subprocess.run(sw, capture_output=True, timeout=1800)
                ok = proc.returncode == 0 and tmp_path.exists() and _probe_ok(tmp_path)
                hwname = "software"
            else:
                hwname = hw.name
            # 3) Only a VALIDATED transcode becomes the served file (atomic rename), so
            #    a crashed / timed-out ffmpeg never leaves a no-moov torso at out_path.
            if ok:
                os.replace(str(tmp_path), str(out_path))
                async for db in get_db():
                    photo = await db.get(Photo, photo_id)
                    if photo:
                        photo.video_webm_path = str(out_path); await db.commit()
                    break
                flog("video", "INFO", f"Web-Version erstellt ({hwname}, {resolution}p, {_t.time()-t0:.1f}s): {fname}")
                return {"ok": True, "hw": hwname}
            flog("video", "WARNING", f"Transkodierung fehlgeschlagen: {fname}: {proc.stderr.decode(errors='replace')[-200:]}")
            return {"error": "ffmpeg"}
        finally:
            try:
                if tmp_path is not None and tmp_path.exists():
                    tmp_path.unlink()
            except Exception:
                pass
            if r is not None:
                try:
                    await r.delete(f"transcode:lock:{photo_id}"); await r.aclose()
                except Exception:
                    pass
    return _run(_run_tc())


@celery_app.task(bind=True, name="revalidate_transcodes")
def revalidate_transcodes_task(self, resolution: int = 1080):
    """Self-heal the web-MP4 backlog: ffprobe every video that has a video_webm_path
    and, for any unreadable / no-moov torso (left by older interrupted transcodes),
    delete the file, clear the path, reset ai_error, and re-enqueue a fresh transcode.
    Idempotent — safe to re-run; only touches broken files."""
    async def _run_rv():
        import os, subprocess
        from app.core.database import init_db, get_db
        from app.models.photo import Photo
        from app.services.feature_log import log as flog
        from sqlalchemy import select, update
        init_db()

        def _probe_ok(p):
            try:
                pr = subprocess.run(
                    ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                     "-of", "csv=p=0", str(p)], capture_output=True, timeout=60)
                d = (pr.stdout or b"").decode().strip()
                return pr.returncode == 0 and d not in ("", "N/A") and float(d) > 0
            except Exception:
                return False

        checked = broken = missing = 0
        # 1) One short read for all candidate ids.
        rows = []
        async for db in get_db():
            rows = (await db.execute(
                select(Photo.id, Photo.video_webm_path).where(
                    Photo.is_video == True,                      # noqa: E712
                    Photo.video_webm_path.isnot(None)))).all()
            break
        # 2) ffprobe each WITHOUT holding a DB session (the slow part). Collect the
        #    broken ids — do NOT open a session per item (that leaks async generators).
        bad = []
        for pid, wp in rows:
            checked += 1
            if wp and os.path.exists(wp):
                if _probe_ok(wp):
                    continue
                try: os.unlink(wp)
                except Exception: pass
                broken += 1
            else:
                missing += 1  # path set but file gone — also re-transcode
            bad.append(pid)
        # 3) One session: bulk-clear the broken ones, then re-enqueue transcodes.
        if bad:
            async for db in get_db():
                await db.execute(update(Photo).where(Photo.id.in_(bad)).values(
                    video_webm_path=None, ai_error=False))
                await db.commit()
                break
            for pid in bad:
                transcode_video_task.delay(pid, resolution)
        flog("video", "INFO",
             f"Transcode-Revalidierung: {checked} geprüft, {broken} kaputt, "
             f"{missing} fehlend → neu eingereiht.")
        return {"checked": checked, "broken": broken, "missing": missing,
                "requeued": broken + missing}
    return _run(_run_rv())


@celery_app.task(bind=True, name="process_photo")
def process_photo_task(self, photo_id: int, job_id: Optional[int] = None, redo_faces: bool = False, redo_thumbs: bool = False):
    async def _run_process():
        from app.core.database import init_db, get_db
        from app.models.photo import Photo, PhotoStatus
        from app.models.job import JobLog
        from app.models.tag import Tag, PhotoTag
        from app.services.processing.thumbnails import (
            generate_thumbnail, generate_video_thumbnail, generate_video_preview_webp,
            video_duration, video_dimensions, open_image_for_ai,
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
                    # The scan no longer extracts EXIF (kept lightweight), so populate
                    # the finer photographic fields here too — not just on reprocess.
                    if not photo.lens_model and ex.lens_model:
                        photo.lens_model = ex.lens_model[:120]
                    if photo.focal_length is None and ex.focal_length is not None:
                        photo.focal_length = ex.focal_length
                    if photo.aperture is None and ex.aperture is not None:
                        photo.aperture = ex.aperture
                    if not photo.shutter_speed and ex.shutter_speed:
                        photo.shutter_speed = ex.shutter_speed
                    if photo.iso is None and ex.iso is not None:
                        photo.iso = ex.iso
                except Exception:
                    pass

                # Persist the CHEAP metadata (date/GPS/camera) right now — before the
                # slow thumbnail step — so the map/timeline populate immediately even
                # while a long thumbnail backlog drains (and survive a worker restart).
                try:
                    await db.commit()
                except Exception:
                    pass

                # Generate all thumbnail sizes — videos need a frame extracted via ffmpeg
                if photo.is_video:
                    import time as _vt, os as _os
                    _v0 = _vt.time()
                    flog("video", "INFO", f"Verarbeitung gestartet: {photo.filename}")
                    # Read frames from the 1080p web MP4 on the SSD when it exists —
                    # MUCH faster than seeking the 4K original on the HDD (which
                    # clogged worker-cpu and starved image thumbnails). Cache key stays
                    # the original path inside the helpers.
                    vsrc = (photo.video_webm_path
                            if (photo.video_webm_path and _os.path.exists(photo.video_webm_path)) else None)
                    for size in ("small", "medium", "large"):
                        try:
                            thumb = generate_video_thumbnail(photo.path, settings.cache_path, size,
                                                             force=redo_thumbs, source_path=vsrc)
                            if thumb:
                                setattr(photo, f"thumb_{size}", thumb)
                        except Exception as ve:
                            flog("video", "WARNING", f"Frame-Extraktion ({size}) fehlgeschlagen: {photo.filename}: {str(ve)[:120]}")
                    if photo.duration_seconds is None:
                        photo.duration_seconds = video_duration(photo.path)
                    # Real dimensions (rotation-aware) so the gallery lays videos out
                    # with the correct aspect ratio instead of a 4:3 guess.
                    vw, vh = video_dimensions(photo.path)
                    if vw and vh:
                        photo.width, photo.height = vw, vh
                    # animated hover preview (best-effort). The 10-24 ffmpeg seeks make
                    # this the slow part — SKIP it on a thumbnail-backfill (redo_thumbs)
                    # so re-attempting a missing thumbnail stays fast and never clogs the
                    # worker; never force-regenerate it either. It's generated on the
                    # initial scan, and a present one is kept.
                    preview_ok = bool(photo.video_preview_path)
                    if not redo_thumbs:
                        try:
                            preview = generate_video_preview_webp(photo.path, settings.cache_path,
                                                                  force=False, source_path=vsrc)
                            if preview:
                                photo.video_preview_path = preview; preview_ok = True
                        except Exception as ve:
                            flog("video", "WARNING", f"Hover-Vorschau fehlgeschlagen: {photo.filename}: {str(ve)[:120]}")
                    dur = photo.duration_seconds
                    if photo.thumb_small:
                        flog("video", "INFO",
                             f"Frames erstellt: {photo.filename} — Länge {f'{dur:.0f}s' if dur else '?'}, "
                             f"{vw or '?'}×{vh or '?'}, Hover-Vorschau {'ja' if preview_ok else 'nein'}, "
                             f"in {_vt.time() - _v0:.1f}s")
                    else:
                        # Count the attempt so retry_missing_thumbnails (cap = thumb_attempts<5)
                        # stops re-queueing a genuinely undecodable clip (VOB/MKV/corrupt) — it
                        # used to retry forever, spamming this line dozens of times per day.
                        # WARNING (not ERROR): a broken/unsupported file isn't a system fault.
                        photo.thumb_attempts = (photo.thumb_attempts or 0) + 1
                        flog("video", "WARNING",
                             f"Kein Frame extrahierbar (ffmpeg, Versuch {photo.thumb_attempts}/5) — "
                             f"übersprungen: {photo.filename}")
                else:
                    for size in ("small", "medium", "large"):
                        thumb = generate_thumbnail(photo.path, settings.cache_path, size, force=redo_thumbs)
                        if thumb:
                            setattr(photo, f"thumb_{size}", thumb)
                    if not photo.thumb_small:
                        photo.thumb_attempts = (photo.thumb_attempts or 0) + 1
                        flog("scanner", "WARNING", f"Thumbnail fehlgeschlagen (Versuch {photo.thumb_attempts}): {photo.filename}")

                # Persist thumbnails immediately — AI is best-effort and must
                # never cost us the thumbnail or stick the photo on a transient error.
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
                return  # don't hand a broken photo to the AI stage

            # Optional: pre-transcode every video to a web-optimised MP4 now
            # (Settings → Video-AI → "Automatisch transkodieren"). Off by default
            # — videos otherwise transcode lazily on first play (cheaper). Heavy
            # if on (software encode), so opt-in.
            if photo.is_video:
                try:
                    from app.services.settings_loader import load_settings as _ls
                    s_tc = await _ls(db)
                    if str(s_tc.get("video.auto_transcode", "false")).lower() == "true":
                        res = int(float(s_tc.get("video.transcode_resolution", "1080") or 1080))
                        transcode_video_task.delay(photo_id, res)
                except Exception:
                    pass

            # Thumbnails are done & committed and the photo already shows in the
            # gallery. Hand the slow GPU work (AI description, embedding, face
            # detection) to the single-slot GPU queue so it never blocks scans
            # or thumbnails for other photos.
            # Skip the AI stage when the description was IMPORTED from existing
            # file metadata (scanner) — unless this is an explicit re-process.
            if photo.description_model == "imported" and not (redo_faces or redo_thumbs):
                # Imported metadata → no AI describe. Mark done so it shows in the
                # gallery; the remote then claims it for a faces-only pass (faces
                # aren't in file metadata), unless scan.faces_on_import is off.
                photo.status = PhotoStatus.done
                photo.processed_at = datetime.now(timezone.utc)
                await db.commit()
                flog("scanner", "INFO", f"KI übersprungen (Metadaten importiert): {photo.filename}")
            else:
                ai_photo_task.delay(photo_id, job_id, redo_faces)

    _run(_run_process())


@celery_app.task(bind=True, name="ai_photo")
def ai_photo_task(self, photo_id: int, job_id: Optional[int] = None, redo_faces: bool = False):
    """GPU stage: AI description, tags, XMP, embedding and face detection.
    Runs on the dedicated single-slot `gpu` worker so the one VLM copy that fits
    the 8 GB card is never duplicated. Thumbnails already exist at this point."""
    async def _run_ai():
        from app.core.database import init_db, get_db
        from app.models.photo import Photo, PhotoStatus
        from app.models.job import JobLog
        from app.models.tag import Tag, PhotoTag
        from app.services.processing.thumbnails import open_image_for_ai
        from app.services.ai.manager import AIManager
        from app.services.feature_log import log as flog
        from app.core.config import get_settings
        from sqlalchemy import select
        import time

        init_db()
        settings = get_settings()  # noqa: F841 (kept for parity / future use)

        async for db in get_db():
            photo = await db.get(Photo, photo_id)
            if not photo:
                return
            start = time.time()

            # Remote-worker dispatch, provider-aware. The remote agent runs the
            # LOCAL VLM, so it only DESCRIBES media whose effective provider is
            # 'local'. If this photo's description provider is local and a worker is
            # alive → yield the whole job (description + faces) to the remote. If the
            # provider is Gemini/etc (e.g. images switched to Gemini) → describe it
            # locally below, but still let the remote do the FACES (faces-only claim)
            # so all faces use the same engine. skip_local_faces records that.
            skip_local_faces = False
            try:
                from app.services.settings_loader import load_settings as _ls
                from app.services.ai.manager import build_video_settings as _bvs
                _s = await _ls(db)
                if str(_s.get("remote.enabled", "false")).lower() == "true":
                    from app.api.routes.remote import remote_worker_alive
                    if await remote_worker_alive() > 0:
                        eff_prov = (_bvs(_s).get("ai.provider") if photo.is_video
                                    else _s.get("ai.provider")) or "none"
                        if eff_prov == "local":
                            return  # remote does description + faces
                        skip_local_faces = True  # remote will do faces-only
            except Exception:
                pass

            try:
                # AI processing — load provider config from DB settings (non-fatal)
                photo.ai_error = False  # cleared on success; set in except below
                ai_settings = {}  # ensure defined even if load_settings below throws (face block reads it)
                try:
                    from app.services.settings_loader import load_settings
                    from app.services.ai.manager import build_video_settings
                    ai_settings = await load_settings(db)
                    # Per-folder AI override: the source whose path is the longest
                    # prefix of this photo can force a provider or disable AI ('off').
                    skip_ai = False
                    try:
                        from app.models.source import PhotoSource
                        srcs = (await db.execute(
                            select(PhotoSource.path, PhotoSource.ai_provider).where(PhotoSource.ai_provider.isnot(None))
                        )).all()
                        best = None
                        for spath, prov in srcs:
                            pref = spath.rstrip("/")
                            if photo.path == pref or photo.path.startswith(pref + "/"):
                                if best is None or len(pref) > len(best[0]):
                                    best = (pref, prov)
                        if best:
                            if best[1] == "off":
                                skip_ai = True
                            else:
                                ai_settings = {**ai_settings, "ai.provider": best[1], "video.ai_provider": "same"}
                    except Exception:
                        pass
                    # Videos use the separate video.* provider (e.g. moondream/ollama)
                    eff_settings = build_video_settings(ai_settings) if photo.is_video else ai_settings
                    ai = AIManager(eff_settings)

                    # Videos: describe from the extracted frame; else the photo
                    img = open_image_for_ai(photo.thumb_large or photo.thumb_medium or photo.path) if photo.is_video \
                        else open_image_for_ai(photo.path)
                    if img and not skip_ai:
                        lang = ai_settings.get("ai.language", "de")
                        custom_prompt = ai_settings.get("ai.prompt.video" if photo.is_video else "ai.prompt.image") or None
                        # One combined call (Gemini): description + tags in a single
                        # vision request → ~halved image-input tokens vs. two calls.
                        # Local providers fall back to two calls inside the manager.
                        tag_prompt = (ai_settings.get("ai.prompt.tags") or "").strip() or None
                        description, tags, provider = await ai.describe_and_tag(img, lang, custom_prompt, tag_prompt)
                        if description:
                            photo.description = description
                            photo.description_model = (provider or "")[:120]
                            flog("ai", "INFO", f"Beschreibung ({provider}): {photo.filename} — {description}")
                            if photo.is_video:
                                flog("video", "INFO", f"KI-Beschreibung ({provider}): {photo.filename} — {description[:120]}")
                        elif provider == "none":
                            flog("ai", "WARNING", f"Kein AI-Provider aktiv/erreichbar für {photo.filename}")
                        else:
                            flog("ai", "WARNING", f"AI lieferte keine Beschreibung ({provider}): {photo.filename}")

                        if tags:
                            flog("ai", "INFO", f"Tags ({provider}): {photo.filename} — {', '.join(tags[:20])}")
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
                        kw = [t for t in tags[:20]]
                        # Write XMP for ANY model (local/gemini/…) whenever there's a
                        # description OR keywords — not gemini-only, not description-only.
                        if (description or kw) and xmp_mode in ("file", "file_sidecar", "sidecar"):
                            try:
                                # Videos never embed (exiftool can't write MTS/AVCHD etc.) → sidecar only.
                                if xmp_mode in ("file", "file_sidecar") and not photo.is_video:
                                    from app.services.exif_edit import write_description as _wd, write_keywords as _wk, ensure_capture_date as _ecd
                                    # No capture date? Derive one from the file date before editing.
                                    set_date = await _ecd(photo.path)
                                    if set_date and photo.taken_at is None:
                                        try:
                                            photo.taken_at = datetime.strptime(set_date[:19], "%Y:%m:%d %H:%M:%S")
                                            flog("ai", "INFO", f"Aufnahmedatum aus Dateidatum gesetzt: {photo.filename} → {set_date}")
                                        except Exception:
                                            pass
                                    if description:
                                        await _wd(photo.path, description, overwrite=True)
                                    if kw:
                                        await _wk(photo.path, kw)
                                    flog("ai", "INFO", f"Beschreibung in Datei geschrieben: {photo.filename}")
                                if photo.is_video or xmp_mode in ("file_sidecar", "sidecar"):
                                    from app.services.xmp_sidecar import write_sidecar, file_capture_date
                                    cap = photo.taken_at or file_capture_date(photo.path)
                                    if cap and photo.taken_at is None:
                                        photo.taken_at = cap
                                        flog("ai", "INFO", f"Aufnahmedatum aus Dateidatum gesetzt (Sidecar): {photo.filename} → {cap}")
                                    xmp_path = write_sidecar(
                                        photo.path,
                                        description=description,
                                        title=photo.title,
                                        keywords=kw or None,
                                        latitude=photo.latitude, longitude=photo.longitude,
                                        city=photo.city, country=photo.country,
                                        capture_date=cap.strftime("%Y-%m-%dT%H:%M:%S") if cap else None,
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
                        photo.ai_attempts = (photo.ai_attempts or 0) + 1  # retry queue caps on this
                    flog("ai", "WARNING", f"AI übersprungen (Thumbnail bleibt): {photo.filename if photo else photo_id}: {str(ai_err)[:160]}")

                # ── Face detection (local, best-effort) ───────────────────────
                # Skipped when a remote worker will do the faces (so all faces use
                # the same insightface engine and clustering stays consistent).
                if not skip_local_faces and str(ai_settings.get("faces.enabled", "true")).lower() != "false":
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
                                min_conf = float(ai_settings.get("face.min_confidence", "0.7") or 0.7)
                                min_size_px = float(ai_settings.get("face.min_size_px", "40") or 0)
                                faces = detect_faces_engine(face_img, min_conf, face_engine, min_size_px)
                                for f in faces:
                                    db.add(Face(
                                        photo_id=photo_id,
                                        bbox_x=f.bbox_x, bbox_y=f.bbox_y, bbox_w=f.bbox_w, bbox_h=f.bbox_h,
                                        confidence=f.confidence, embedding=f.embedding, detector=face_engine,
                                    ))
                                if faces:
                                    # Face-aware crop centre (avg face centre, 0..1) so
                                    # the gallery's object-cover keeps heads in frame.
                                    cxs = [f.bbox_x + f.bbox_w / 2 for f in faces]
                                    cys = [f.bbox_y + f.bbox_h / 2 for f in faces]
                                    photo.focus_x = min(1.0, max(0.0, sum(cxs) / len(cxs)))
                                    photo.focus_y = min(1.0, max(0.0, sum(cys) / len(cys)))
                                photo.faces_scanned = True  # pass ran (even if 0)
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
                flog("system", "ERROR", f"AI-Verarbeitung fehlgeschlagen: {fname}: {str(e)[:200]}")
                if job_id:
                    try:
                        db.add(JobLog(job_id=job_id, photo_id=photo_id, level="ERROR", message=f"❌ {fname}: {e}"))
                        await db.commit()
                    except Exception:
                        pass

    _run(_run_ai())


@celery_app.task(bind=True, name="render_highlight")
def render_highlight_task(self, highlight_id: int):
    """Render a highlight slideshow MP4: select photos for the motto, build the
    video from their cached large thumbnails, and update the Highlight record."""
    async def _run_render():
        from app.core.database import init_db, get_db
        from app.core.config import get_settings
        from app.models.highlight import Highlight, HighlightStatus
        from app.services import highlights as hl
        from app.services.feature_log import log as flog

        init_db()
        cache_path = get_settings().cache_path

        async for db in get_db():
            h = await db.get(Highlight, highlight_id)
            if not h:
                return {"error": "Highlight not found"}
            h.status = HighlightStatus.rendering
            await db.commit()

            try:
                opts = dict(h.params or {})
                opts.setdefault("duration_sec", h.duration_sec or 60.0)
                photos = await hl.select_photos_for_motto(db, h.motto, opts)
                if not photos:
                    h.status = HighlightStatus.error
                    h.error_message = "Keine passenden Fotos für dieses Motto gefunden."
                    await db.commit()
                    flog("highlights", "WARNING",
                         f"Highlight {highlight_id} ({h.motto}): keine Fotos")
                    return {"error": "no photos"}

                image_paths = [p.thumb_large for p in photos if p.thumb_large]
                cover_id = photos[0].id
                duration = float(h.duration_sec or 60.0)
                seconds_per = max(0.8, duration / max(1, len(image_paths)))
                out_path = hl.highlight_output_path(cache_path, highlight_id)

                # End the read txn and run the BLOCKING ffmpeg/ffprobe OFF the event loop.
                # Holding the asyncpg connection across the synchronous subprocess starved
                # it → ConnectionDoesNotExistError (same root cause as the clustering bug).
                import asyncio
                from app.services.processing.thumbnails import video_duration
                await db.commit()

                def _render():
                    if not hl.render_slideshow(image_paths, out_path, seconds_per):
                        return (False, None)
                    return (True, video_duration(out_path))
                ok, actual = await asyncio.to_thread(_render)
                if not ok:
                    h.status = HighlightStatus.error
                    h.error_message = "Video-Erstellung (ffmpeg) fehlgeschlagen."
                    await db.commit()
                    flog("highlights", "ERROR",
                         f"Highlight {highlight_id} ({h.motto}): ffmpeg fehlgeschlagen")
                    return {"error": "render failed"}

                h.file_path = out_path
                h.photo_count = len(image_paths)
                h.cover_photo_id = cover_id
                if actual:
                    h.duration_sec = round(actual, 1)
                h.status = HighlightStatus.done
                h.error_message = None
                await db.commit()
                flog("highlights", "INFO",
                     f"Highlight {highlight_id} ({h.motto}) fertig: "
                     f"{len(image_paths)} Fotos, {h.duration_sec}s")
                return {"ok": True, "photos": len(image_paths)}
            except Exception as e:
                try:
                    await db.rollback()
                    h2 = await db.get(Highlight, highlight_id)
                    if h2:
                        h2.status = HighlightStatus.error
                        h2.error_message = str(e)[:500]
                        await db.commit()
                except Exception:
                    pass
                flog("highlights", "ERROR",
                     f"Highlight {highlight_id} fehlgeschlagen: {str(e)[:200]}")
                return {"error": str(e)[:200]}

    return _run(_run_render())


@celery_app.task(bind=True, name="animate_photo")
def animate_photo_task(self, highlight_id: int):
    """MVP external video-AI: animate ONE still photo into a short clip via Veo 3.1 Fast.
    Strictly opt-in (highlights.ai_enabled) and budget-capped. Reuses the Highlight record
    (motto='photo_animate', cover_photo_id=source photo). Result MP4 plays like any highlight."""
    async def _run_animate():
        import os
        from datetime import datetime, timezone
        from app.core.database import init_db, get_db
        from app.core.config import get_settings
        from app.models.highlight import Highlight, HighlightStatus
        from app.models.photo import Photo
        from app.services.settings_loader import load_settings
        from app.services.ai.video_gen import veo, fal
        from app.services.feature_log import log as flog
        from sqlalchemy import select, func

        init_db()
        cache_path = get_settings().cache_path
        async for db in get_db():
            h = await db.get(Highlight, highlight_id)
            if not h:
                return {"error": "Highlight not found"}
            s = await load_settings(db)
            try:
                if str(s.get("highlights.ai_enabled", "false")).lower() != "true":
                    raise RuntimeError("KI-Video ist deaktiviert (Einstellungen → Highlights).")
                provider = str(s.get("highlights.ai_provider", "veo")).lower()
                if provider not in ("veo", "fal"):
                    raise RuntimeError(f"Provider '{provider}' nicht unterstützt (veo, fal).")
                seconds = int(float(s.get("highlights.ai_clip_seconds", "4") or 4))
                budget = int(float(s.get("highlights.ai_budget_seconds_month", "300") or 300))
                custom = (h.params or {}).get("prompt")
                if custom:
                    # Creative scene (e.g. "walk through an underwater world") — still ask the
                    # model to keep the person recognizable.
                    prompt = (f"{custom}. Keep the person's face and identity recognizable "
                              f"and consistent throughout.")
                else:
                    prompt = (s.get("highlights.ai_prompt")
                              or "Gentle, natural camera motion. Keep faces and identities stable. "
                                 "Subtle, realistic movement only — no morphing, no new objects.")

                # Hard monthly budget: sum seconds already spent this calendar month.
                now = datetime.now(timezone.utc)
                spent = (await db.execute(
                    select(func.coalesce(func.sum(Highlight.duration_sec), 0.0)).where(
                        Highlight.motto == "photo_animate",
                        Highlight.status == HighlightStatus.done,
                        func.extract("year", Highlight.created_at) == now.year,
                        func.extract("month", Highlight.created_at) == now.month,
                    ))).scalar() or 0.0
                if spent + seconds > budget:
                    raise RuntimeError(
                        f"Monatsbudget erreicht ({int(spent)}/{budget}s). "
                        f"Erhöhe highlights.ai_budget_seconds_month oder warte bis nächsten Monat.")

                photo = await db.get(Photo, h.cover_photo_id) if h.cover_photo_id else None
                if not photo or not photo.thumb_large or not os.path.exists(photo.thumb_large):
                    raise RuntimeError("Quellfoto/Thumbnail nicht gefunden.")

                h.status = HighlightStatus.rendering
                await db.commit()

                with open(photo.thumb_large, "rb") as f:
                    img = f.read()
                # Portrait vs landscape → matching Veo aspect ratio.
                aspect = "16:9"
                try:
                    from PIL import Image
                    import io
                    with Image.open(io.BytesIO(img)) as im:
                        if im.height > im.width:
                            aspect = "9:16"
                except Exception:
                    pass

                if provider == "fal":
                    fal_key = s.get("highlights.fal_api_key") or ""
                    fal_model = s.get("highlights.fal_model") or fal.DEFAULT_MODEL
                    clip = await fal.animate_image(fal_key, img, prompt, model=fal_model)
                else:  # veo (default) — reuses the Gemini key
                    clip = await veo.animate_image(s.get("ai.gemini.api_key") or "", img,
                                                   prompt, seconds=seconds, aspect=aspect)

                out_dir = os.path.join(cache_path, "highlights", "clips")
                os.makedirs(out_dir, exist_ok=True)
                out_path = os.path.join(out_dir, f"{highlight_id}.mp4")
                tmp = out_path + ".part"
                with open(tmp, "wb") as f:
                    f.write(clip)
                os.replace(tmp, out_path)

                from app.services.processing.thumbnails import video_duration
                actual = video_duration(out_path)
                h.file_path = out_path
                h.photo_count = 1
                h.duration_sec = round(actual, 1) if actual else float(seconds)
                h.status = HighlightStatus.done
                h.error_message = None
                await db.commit()
                flog("highlights", "INFO", f"Foto animiert (Highlight {highlight_id}, {h.duration_sec}s, Veo)")
                return {"ok": True, "seconds": h.duration_sec}
            except Exception as e:
                try:
                    await db.rollback()
                    h2 = await db.get(Highlight, highlight_id)
                    if h2:
                        h2.status = HighlightStatus.error
                        h2.error_message = str(e)[:500]
                        await db.commit()
                except Exception:
                    pass
                flog("highlights", "ERROR", f"Foto-Animation {highlight_id} fehlgeschlagen: {str(e)[:200]}")
                return {"error": str(e)[:200]}

    return _run(_run_animate())


@celery_app.task(bind=True, name="generate_weekly_highlight")
def generate_weekly_highlight_task(self):
    """Beat task: auto-create a 'Highlight der Woche' (week_review slideshow). Opt-in via
    highlights.weekly_enabled (default off). Skips if one was already created in the last
    6 days, so a manual run + the schedule don't produce duplicates."""
    async def _run_weekly():
        from datetime import datetime, timezone, timedelta
        from app.core.database import init_db, get_db
        from app.models.highlight import Highlight, HighlightStatus
        from app.services.settings_loader import load_settings
        from app.services.feature_log import log as flog
        from sqlalchemy import select, func
        init_db()
        async for db in get_db():
            s = await load_settings(db)
            if str(s.get("highlights.weekly_enabled", "false")).lower() != "true":
                return {"skipped": "disabled"}
            since = datetime.now(timezone.utc) - timedelta(days=6)
            recent = (await db.execute(select(func.count()).where(
                Highlight.motto == "week_review", Highlight.created_at >= since))).scalar() or 0
            if recent:
                return {"skipped": "already created this week"}
            kw = datetime.now(timezone.utc).isocalendar().week
            h = Highlight(title=f"Highlight der Woche (KW {kw})", motto="week_review",
                          duration_sec=60.0, params={"duration_sec": 60.0},
                          status=HighlightStatus.pending)
            db.add(h)
            await db.commit()
            await db.refresh(h)
            render_highlight_task.delay(h.id)
            flog("highlights", "INFO", f"Auto-Wochenhighlight angelegt (KW {kw}, Highlight {h.id})")
            return {"created": h.id}
    return _run(_run_weekly())


@celery_app.task(bind=True, name="reap_stuck_highlights")
def reap_stuck_highlights_task(self):
    """Self-heal highlights stuck in 'rendering' (worker killed mid-task, e.g. by a deploy).
    Slideshow highlights are re-queued (free); paid photo_animate jobs are marked error
    so the user can retry deliberately (no surprise re-charge). Runs periodically."""
    async def _main():
        from app.core.database import init_db, get_db
        from app.models.highlight import Highlight, HighlightStatus
        from app.services.feature_log import log as flog
        from sqlalchemy import select, text
        init_db()
        requeue_ids, failed = [], 0
        async for db in get_db():
            rows = (await db.execute(select(Highlight).where(
                Highlight.status == HighlightStatus.rendering,
                Highlight.updated_at < text("now() - interval '15 minutes'"),
            ))).scalars().all()
            for h in rows:
                if h.motto == "photo_animate":
                    h.status = HighlightStatus.error
                    h.error_message = "Generierung unterbrochen — bitte erneut starten."
                    failed += 1
                else:
                    h.status = HighlightStatus.pending
                    requeue_ids.append(h.id)
            if rows:
                await db.commit()
            break
        for hid in requeue_ids:
            render_highlight_task.delay(hid)
        if requeue_ids or failed:
            flog("highlights", "INFO", f"Reaper: {len(requeue_ids)} neu eingereiht, {failed} als Fehler markiert")
        return {"requeued": len(requeue_ids), "failed": failed}
    return _run(_main())
