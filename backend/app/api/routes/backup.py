"""Backup management endpoints."""
import os
from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from app.services.backup import (
    run_full_backup, list_backups, prune_backups, rclone_sync,
)
from app.services.hw_accel import detect_hw

router = APIRouter(prefix="/backup", tags=["backup"])

_DB_URL = os.getenv("DATABASE_URL", "")
_CONFIG = os.getenv("CONFIG_PATH", "/config")


@router.post("/run")
async def trigger_backup(rclone_remote: str = "", background_tasks: BackgroundTasks = None):
    """Start a full backup (DB + config). Async — returns immediately."""
    async def _do():
        await run_full_backup(_DB_URL, _CONFIG, rclone_remote or None)

    if background_tasks:
        background_tasks.add_task(_do)
        return {"status": "started"}
    # Sync for small installations
    result = await run_full_backup(_DB_URL, _CONFIG, rclone_remote or None)
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


@router.delete("/prune")
async def prune(keep_days: int = 30):
    deleted = prune_backups(keep_days)
    return {"deleted": deleted, "keep_days": keep_days}


@router.post("/rclone/test")
async def test_rclone(remote: str):
    return await rclone_sync(remote, dry_run=True)


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
