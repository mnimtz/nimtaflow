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
    patterns = [p for p in (source.exclusion_patterns or "").split(",") if p.strip()]
    root = Path(source.path)
    stats = {"new": 0, "skipped": 0, "errors": 0, "missing": 0, "restored": 0}

    def _slog(level, msg):
        try:
            from app.services.feature_log import log as flog
            flog("scanner", level, msg)
        except Exception:
            pass

    _slog("INFO", f"Scan gestartet: {root} (rekursiv={source.recursive})")

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
        source.last_scan_at = datetime.now(timezone.utc)
        source.last_scan_count = 0
        await session.commit()
        return stats

    walk_fn = root.rglob("*") if source.recursive else root.iterdir()
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
    if getattr(source, "detect_deletions", True):
        root_prefix = str(root)
        result = await session.execute(
            select(Photo).where(Photo.path.startswith(root_prefix))
        )
        for photo in result.scalars():
            on_disk = os.path.exists(photo.path)
            if not on_disk and not photo.is_missing:
                photo.is_missing = True
                photo.missing_at = datetime.now(timezone.utc)
                stats["missing"] += 1
            elif on_disk and photo.is_missing:
                photo.is_missing = False
                photo.missing_at = None
                stats["restored"] += 1
        await session.commit()

    source.last_scan_at = datetime.now(timezone.utc)
    source.last_scan_count = stats["new"]
    await session.commit()

    # (process_photo is now enqueued per-photo during the scan loop above.)

    try:
        from app.services.feature_log import log as flog
        flog("scanner", "INFO",
             f"Scan {root}: {stats['new']} neu, {stats['skipped']} übersprungen, "
             f"{stats['missing']} fehlend, {stats['errors']} Fehler")
    except Exception:
        pass

    return stats
