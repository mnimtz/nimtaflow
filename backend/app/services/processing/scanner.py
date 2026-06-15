"""Scan photo source directories and upsert Photo records."""
import hashlib
import os
from pathlib import Path
from typing import List, Optional, AsyncGenerator
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.photo import Photo, PhotoStatus
from app.models.source import PhotoSource
from .exif import extract_exif
from .thumbnails import generate_thumbnail

VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".webm", ".mts", ".3gp"}

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

            await session.commit()
            stats["new"] += 1
            new_photo_ids.append(photo.id)

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

    # Queue processing for all new photos (thumbnails + AI)
    if new_photo_ids:
        from app.worker.tasks import process_photo_task
        for pid in new_photo_ids:
            process_photo_task.delay(pid)

    try:
        from app.services.feature_log import log as flog
        flog("scanner", "INFO",
             f"Scan {root}: {stats['new']} neu, {stats['skipped']} übersprungen, "
             f"{stats['missing']} fehlend, {stats['errors']} Fehler")
    except Exception:
        pass

    return stats
