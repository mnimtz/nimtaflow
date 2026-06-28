"""Backup management endpoints."""
import os
from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from app.services.backup import (
    run_full_backup, list_backups, prune_backups, rclone_sync,
    restore_database, restore_archive, verify_database_dump, delete_backup, BACKUP_DIR,
)
from app.services.hw_accel import detect_hw

router = APIRouter(prefix="/backup", tags=["backup"])

_DB_URL = os.getenv("DATABASE_URL", "")
_CONFIG = os.getenv("CONFIG_PATH", "/config")
_CACHE = os.getenv("CACHE_PATH", "/cache")


@router.post("/run")
async def trigger_backup(rclone_remote: str = "", include_thumbnails: bool = True,
                         background_tasks: BackgroundTasks = None):
    """Start a full backup (DB + config + optionally thumbnails). Async."""
    async def _do():
        await run_full_backup(_DB_URL, _CONFIG, rclone_remote or None,
                              include_thumbnails=include_thumbnails)

    if background_tasks:
        background_tasks.add_task(_do)
        return {"status": "started"}
    result = await run_full_backup(_DB_URL, _CONFIG, rclone_remote or None,
                                   include_thumbnails=include_thumbnails)
    return result


@router.get("/list")
async def get_backups():
    return list_backups()


@router.get("/download/{filename}")
async def download_backup(filename: str):
    from app.services.backup import BACKUP_DIR
    path = BACKUP_DIR / filename
    if not path.exists() or not path.name.endswith(".gz"):
        raise HTTPException(404, "Backup not found")
    return FileResponse(str(path), filename=filename)


def _safe_backup_file(filename: str):
    """Resolve a filename to a path inside BACKUP_DIR (no traversal)."""
    p = (BACKUP_DIR / filename).resolve()
    if BACKUP_DIR.resolve() not in p.parents or not p.exists():
        raise HTTPException(404, "Backup not found")
    return p


@router.post("/verify")
async def verify_backup(filename: str):
    """Non-destructive check that a db_*.sql.gz dump is actually restorable
    (restores into a scratch DB, counts photos, drops it). Proves the backup."""
    p = _safe_backup_file(filename)
    if not p.name.startswith("db_"):
        raise HTTPException(400, "Verify only applies to a db_*.sql.gz dump")
    return await verify_database_dump(_DB_URL, str(p))


@router.post("/restore/db")
async def restore_db(filename: str):
    """DESTRUCTIVE: restore the live database from a db_*.sql.gz dump."""
    p = _safe_backup_file(filename)
    return await restore_database(_DB_URL, str(p))


@router.post("/restore/files")
async def restore_files(filename: str):
    """Restore a config_*/cache_*.tar.gz back into /config or /cache."""
    p = _safe_backup_file(filename)
    dest = _CACHE if p.name.startswith("cache_") else _CONFIG
    return await restore_archive(str(p), dest)


@router.delete("/prune")
async def prune(keep_days: int = 30, keep_count: int = 0):
    deleted = prune_backups(keep_days, keep_count)
    return {"deleted": deleted, "keep_days": keep_days, "keep_count": keep_count}


@router.delete("/file/{filename}")
async def delete_one(filename: str):
    """Delete a single backup file (path-traversal-safe)."""
    p = _safe_backup_file(filename)
    ok = delete_backup(p.name)
    if not ok:
        raise HTTPException(404, "Backup nicht gefunden")
    return {"deleted": ok, "name": p.name}


@router.post("/rclone/test")
async def test_rclone(remote: str):
    return await rclone_sync(remote, dry_run=True)


@router.post("/mirror-originals")
async def mirror_originals_now():
    """Trigger a one-off offsite mirror of the ORIGINAL photo/video files (reads
    backup.mirror_remote + enabled sources from settings). Queued to the worker —
    a full mirror can take hours, so it runs in the background, not inline."""
    from app.worker.tasks import mirror_originals_task
    task = mirror_originals_task.delay(force=True)
    return {"status": "queued", "task_id": task.id}


# ── Hardware info ──────────────────────────────────────────────────────────────

@router.get("/hw", tags=["system"])
async def hardware_info():
    """Return detected hardware acceleration profile."""
    hw = detect_hw()
    return {
        "name": hw.name,
        "available": hw.available,
        "info": hw.info,
        "encode_video_codec": hw.encode_video_codec,
        "encode_h264_codec": hw.encode_h264_codec,
    }
