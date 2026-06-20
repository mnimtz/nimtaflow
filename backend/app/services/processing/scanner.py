"""Scan photo source directories and upsert Photo records."""
import hashlib
import os
from pathlib import Path
from typing import List, Optional, AsyncGenerator
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.photo import Photo, PhotoStatus
from app.models.source import PhotoSource
from app.models.tag import Tag, PhotoTag
from .exif import extract_exif
from .thumbnails import generate_thumbnail

VIDEO_EXTENSIONS = {
    ".mp4", ".mov", ".avi", ".mkv", ".m4v", ".webm", ".mts", ".3gp",
    # AVCHD camcorder + DVD + older formats (all ffmpeg-decodable)
    ".m2ts", ".m2t", ".ts", ".vob", ".mpg", ".mpeg", ".wmv", ".flv", ".ogv", ".mod",
}

SUPPORTED_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp",
    ".heic", ".heif", ".tiff", ".tif", ".bmp",
    ".raw", ".cr2", ".cr3", ".nef", ".arw", ".dng",
} | VIDEO_EXTENSIONS

import mimetypes


def _should_exclude(path: Path, patterns: List[str]) -> bool:
    for pattern in patterns:
        p = pattern.strip()
        if not p:
            continue
        if p in path.parts:
            return True
        if path.name == p:
            return True
    return False


def _file_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


async def scan_source(
    source: PhotoSource,
    session: AsyncSession,
    cache_root: str,
) -> dict:
    # Capture every source attribute we need into plain locals NOW, while the
    # ORM object is still attached and fresh. The scan runs for a long time and
    # commits per file; if the connection is reaped (idle timeout) mid-walk the
    # `source` object becomes expired, and a later attribute access would trigger
    # a *sync* lazy-load inside the async loop → MissingGreenlet, killing the
    # whole scan before the big folders are indexed. Reading scalars up front and
    # never touching `source` again after the loop avoids that entirely.
    src_id = source.id
    src_path = source.path
    src_recursive = source.recursive
    src_exclusion = source.exclusion_patterns or ""
    src_detect_deletions = getattr(source, "detect_deletions", True)

    patterns = [p for p in src_exclusion.split(",") if p.strip()]
    root = Path(src_path)
    stats = {"new": 0, "skipped": 0, "errors": 0, "missing": 0, "restored": 0}

    def _slog(level, msg):
        try:
            from app.services.feature_log import log as flog
            flog("scanner", level, msg)
        except Exception:
            pass

    _slog("INFO", f"Scan gestartet: {root} (rekursiv={src_recursive})")

    # Read existing AI metadata (embedded XMP/IPTC or a .xmp sidecar) and import
    # it instead of re-running the AI — unless the user forces a re-index.
    try:
        from app.services.settings_loader import load_settings
        _s = await load_settings(session)
        _force_reindex = str(_s.get("scan.force_reindex", "false")).lower() == "true"
    except Exception:
        _force_reindex = False

    if not root.exists():
        # Most common cause of "noch nicht gescannt": the path doesn't exist
        # inside the container (wrong mount/typo). Make it visible.
        _slog("ERROR", f"Pfad existiert nicht im Container: {root} — Mount/Schreibweise prüfen")
        from sqlalchemy import update as _sa_update0
        await session.execute(
            _sa_update0(PhotoSource).where(PhotoSource.id == src_id)
            .values(last_scan_at=datetime.now(timezone.utc), last_scan_count=0)
        )
        await session.commit()
        return stats

    # ── Live progress (so the UI can show "X / Y gescannt" during a long scan) ──
    # The user couldn't see a grand total during the multi-hour initial scan. We
    # do one fast count-only pre-pass to get the total, then publish running
    # counters to Redis. ALL of this is best-effort: a progress failure must never
    # break the actual scan.
    import json as _json
    _pr = None
    try:
        import redis.asyncio as _aioredis
        from app.core.config import get_settings as _gs
        _pr = _aioredis.from_url(_gs().redis_url)
    except Exception:
        _pr = None

    total_files = 0
    try:
        _count_walk = root.rglob("*") if src_recursive else root.iterdir()
        for _e in _count_walk:
            try:
                if (_e.is_file() and _e.suffix.lower() in SUPPORTED_EXTENSIONS
                        and not _should_exclude(_e, patterns)):
                    total_files += 1
            except Exception:
                continue
    except Exception:
        total_files = 0

    async def _progress(running=True):
        if _pr is None:
            return
        try:
            await _pr.set(f"scan:progress:{src_id}", _json.dumps({
                "root": str(root), "total": total_files,
                "scanned": stats["new"] + stats["skipped"] + stats["errors"],
                "new": stats["new"], "skipped": stats["skipped"],
                "errors": stats["errors"], "running": running,
            }), ex=24 * 3600)
        except Exception:
            pass

    await _progress(running=True)
    _slog("INFO", f"Scan: {total_files} Mediendateien gefunden unter {root}")

    walk_fn = root.rglob("*") if src_recursive else root.iterdir()
    new_photo_ids: List[int] = []

    for entry in walk_fn:
        if not entry.is_file():
            continue
        if entry.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        if _should_exclude(entry, patterns):
            stats["skipped"] += 1
            continue

        path_str = str(entry)

        # Check if already indexed
        existing = await session.scalar(select(Photo).where(Photo.path == path_str))
        if existing:
            stats["skipped"] += 1
            if stats["skipped"] % 500 == 0:
                await _progress(running=True)
            continue

        try:
            exif = extract_exif(path_str)
            stat = entry.stat()
            ext = entry.suffix.lower()
            is_video = ext in VIDEO_EXTENSIONS
            mime_type = mimetypes.guess_type(path_str)[0] or (
                "video/quicktime" if ext == ".mov" else None
            )

            photo = Photo(
                path=path_str,
                filename=entry.name,
                file_size=stat.st_size,
                is_video=is_video,
                mime_type=mime_type,
                status=PhotoStatus.pending,
                taken_at=exif.taken_at,
                width=exif.width,
                height=exif.height,
                camera_make=exif.camera_make,
                camera_model=exif.camera_model,
                lens_model=exif.lens_model,
                focal_length=exif.focal_length,
                aperture=exif.aperture,
                shutter_speed=exif.shutter_speed,
                iso=exif.iso,
                latitude=exif.latitude,
                longitude=exif.longitude,
                altitude=exif.altitude,
                indexed_at=datetime.now(timezone.utc),
            )
            session.add(photo)
            await session.flush()

            # Generate small thumbnail synchronously during scan
            thumb = generate_thumbnail(path_str, cache_root, "small")
            if thumb:
                photo.thumb_small = thumb

            # Import already-present metadata (embedded XMP/IPTC or .xmp sidecar)
            # so we don't re-run the AI on already-described media. Setting the
            # description here means the remote/local AI skips it (claim filters
            # description IS NULL). Opt-out via scan.force_reindex.
            imported = False
            if not _force_reindex:
                try:
                    from app.services.exif_edit import read_existing_ai_metadata
                    desc, kws = await read_existing_ai_metadata(path_str)
                    if desc:
                        photo.description = desc
                        photo.description_model = "imported"
                        for name in [k[:120] for k in (kws or [])[:20] if k.strip()]:
                            tag = await session.scalar(select(Tag).where(Tag.name == name))
                            if not tag:
                                try:
                                    async with session.begin_nested():
                                        tag = Tag(name=name); session.add(tag); await session.flush()
                                except IntegrityError:
                                    tag = await session.scalar(select(Tag).where(Tag.name == name))
                            if tag and not await session.scalar(select(PhotoTag).where(
                                    PhotoTag.photo_id == photo.id, PhotoTag.tag_id == tag.id)):
                                session.add(PhotoTag(photo_id=photo.id, tag_id=tag.id, source="imported"))
                        imported = True
                        _slog("INFO", f"Metadaten aus Datei übernommen (KI übersprungen): {entry.name}")
                    # Durable user metadata: rating (XMP:Rating), favourite (rating==5
                    # by our convention) and the person names in the file. Read even
                    # when there is no AI description, so favourites/people round-trip.
                    try:
                        from app.services.exif_edit import read_existing_extras
                        rating, persons = await read_existing_extras(path_str)
                        if rating is not None:
                            photo.user_rating = rating
                            if rating >= 5:
                                photo.is_favorite = True
                        if persons:
                            photo.imported_person_names = ",".join(persons[:50])
                        # Title + place names (otherwise only re-derivable from GPS).
                        from app.services.exif_edit import read_file_location
                        title, city, country = await read_file_location(path_str)
                        if title and not photo.title:
                            photo.title = title[:512]
                        if city and not photo.city:
                            photo.city = city
                        if country and not photo.country:
                            photo.country = country
                    except Exception:
                        pass
                    # Face regions (MWG): recreate the detected faces from the boxes
                    # in the file, so face DETECTION never re-runs on a re-import.
                    # Named regions are linked to the person; unknown regions keep
                    # just the box (no embedding — clustering can't be recovered).
                    try:
                        from app.services.exif_edit import read_face_regions
                        from app.models.face import Face
                        from app.models.person import Person
                        regions = await read_face_regions(path_str)
                        for reg in regions:
                            bx = min(1.0, max(0.0, reg["cx"] - reg["w"] / 2))
                            by = min(1.0, max(0.0, reg["cy"] - reg["h"] / 2))
                            pid = None
                            nm = (reg.get("name") or "").strip()
                            if nm:
                                person = await session.scalar(select(Person).where(Person.name == nm))
                                if not person:
                                    try:
                                        async with session.begin_nested():
                                            person = Person(name=nm); session.add(person); await session.flush()
                                    except IntegrityError:
                                        person = await session.scalar(select(Person).where(Person.name == nm))
                                pid = person.id if person else None
                            session.add(Face(
                                photo_id=photo.id, bbox_x=bx, bbox_y=by,
                                bbox_w=reg["w"], bbox_h=reg["h"],
                                confidence=1.0, detector="imported", person_id=pid,
                            ))
                        if regions:
                            _slog("INFO", f"{len(regions)} Gesicht(er) aus Datei-Regionen übernommen: {entry.name}")
                    except Exception as e:
                        _slog("WARNING", f"Gesichts-Regionen-Import fehlgeschlagen: {entry.name}: {str(e)[:100]}")
                except Exception as e:
                    _slog("WARNING", f"Metadaten-Import fehlgeschlagen: {entry.name}: {str(e)[:120]}")

            await session.commit()
            stats["new"] += 1
            # Enqueue processing immediately (not in one batch at the end) so it
            # starts right away, survives an interrupted scan, and shows progress.
            # (process_photo skips the AI stage when a description was imported.)
            from app.worker.tasks import process_photo_task
            process_photo_task.delay(photo.id)
            if stats["new"] % 100 == 0:
                _slog("INFO", f"Scan läuft ({root.name}): {stats['new']} neu, {stats['skipped']} übersprungen …")
                await _progress(running=True)

        except IntegrityError:
            # Another scan (overlapping/nested source, parallel cpu worker) already
            # inserted this exact path between our check and insert. Idempotent →
            # treat as skipped, not an error. No log spam.
            await session.rollback()
            stats["skipped"] += 1
            continue
        except Exception as e:
            await session.rollback()
            stats["errors"] += 1
            _slog("WARNING", f"Datei übersprungen (Fehler): {entry.name}: {str(e)[:140]}")

    # ── Deletion detection ──────────────────────────────────────────────
    # Flag DB photos under this source root whose files vanished from disk;
    # un-flag any that reappeared. (Recursive sources match the whole subtree.)
    if src_detect_deletions:
        root_prefix = str(root)
        from sqlalchemy import update as _sa_upd_del

        async def _apply(missing_ids, restored_ids):
            # Apply a batch and COMMIT, so we never hold one transaction open
            # across an os.path.exists() loop over the whole library (137k rows)
            # — that long idle-in-transaction got the connection reaped and
            # crashed the scan. Batching also keeps memory flat.
            if missing_ids:
                await session.execute(
                    _sa_upd_del(Photo).where(Photo.id.in_(missing_ids))
                    .values(is_missing=True, missing_at=datetime.now(timezone.utc))
                )
                stats["missing"] += len(missing_ids)
            if restored_ids:
                await session.execute(
                    _sa_upd_del(Photo).where(Photo.id.in_(restored_ids))
                    .values(is_missing=False, missing_at=None)
                )
                stats["restored"] += len(restored_ids)
            if missing_ids or restored_ids:
                await session.commit()

        # Stream only the columns we need (id/path/is_missing) — not full ORM rows
        # incl. the 768-dim embedding vector — and process in batches.
        result = await session.stream(
            select(Photo.id, Photo.path, Photo.is_missing)
            .where(Photo.path.startswith(root_prefix))
            .execution_options(yield_per=2000)
        )
        batch_missing: List[int] = []
        batch_restored: List[int] = []
        checked = 0
        async for pid, ppath, is_missing in result:
            on_disk = os.path.exists(ppath)
            if not on_disk and not is_missing:
                batch_missing.append(pid)
            elif on_disk and is_missing:
                batch_restored.append(pid)
            checked += 1
            if checked % 2000 == 0:
                await _apply(batch_missing, batch_restored)
                batch_missing, batch_restored = [], []
        await _apply(batch_missing, batch_restored)

    # Update via explicit UPDATE (not ORM attribute set) so we never lazy-load the
    # possibly-expired `source` object after the long-running loop.
    from sqlalchemy import update as _sa_update
    await session.execute(
        _sa_update(PhotoSource)
        .where(PhotoSource.id == src_id)
        .values(last_scan_at=datetime.now(timezone.utc), last_scan_count=stats["new"])
    )
    await session.commit()

    # (process_photo is now enqueued per-photo during the scan loop above.)

    # Final progress snapshot (running=False) + release the Redis client.
    await _progress(running=False)
    if _pr is not None:
        try:
            await _pr.aclose()
        except Exception:
            pass

    try:
        from app.services.feature_log import log as flog
        flog("scanner", "INFO",
             f"Scan {root}: {stats['new']} neu, {stats['skipped']} übersprungen, "
             f"{stats['missing']} fehlend, {stats['errors']} Fehler")
    except Exception:
        pass

    return stats
