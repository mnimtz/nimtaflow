import os
from datetime import datetime, timezone
from pathlib import Path

import aiofiles
import httpx
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel

from app.core.auth_guard import require_admin

APK_PATH = Path(os.getenv("APK_PATH", "/apk/nimtaflow-tv.apk"))

router = APIRouter(prefix="/api/v1/software", tags=["software"])


def _apk_info() -> dict:
    if APK_PATH.exists():
        stat = APK_PATH.stat()
        return {
            "available": True,
            "size_bytes": stat.st_size,
            "size_mb": round(stat.st_size / 1024 / 1024, 1),
            "updated_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        }
    return {"available": False, "size_bytes": 0, "size_mb": 0.0, "updated_at": None}


@router.get("/firetv")
async def firetv_info():
    return _apk_info()


class FetchBody(BaseModel):
    url: str | None = None


@router.post("/firetv/fetch")
async def firetv_fetch(body: FetchBody, _: None = Depends(require_admin)):
    url = body.url or os.getenv("FIRETV_APK_URL", "")
    if not url:
        raise HTTPException(400, "Keine URL angegeben und FIRETV_APK_URL nicht konfiguriert")
    await _download_apk(url)
    return _apk_info()


@router.post("/firetv/upload")
async def firetv_upload(file: UploadFile = File(...), _: None = Depends(require_admin)):
    APK_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = APK_PATH.with_suffix(".tmp")
    try:
        async with aiofiles.open(tmp, "wb") as f:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                await f.write(chunk)
        tmp.replace(APK_PATH)
    except Exception as e:
        tmp.unlink(missing_ok=True)
        raise HTTPException(500, str(e))
    return _apk_info()


async def _download_apk(url: str) -> None:
    APK_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = APK_PATH.with_suffix(".tmp")
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=120) as client:
            async with client.stream("GET", url) as resp:
                resp.raise_for_status()
                async with aiofiles.open(tmp, "wb") as f:
                    async for chunk in resp.aiter_bytes(1024 * 1024):
                        await f.write(chunk)
        tmp.replace(APK_PATH)
    except httpx.HTTPStatusError as e:
        tmp.unlink(missing_ok=True)
        raise HTTPException(502, f"Download fehlgeschlagen: HTTP {e.response.status_code}")
    except Exception as e:
        tmp.unlink(missing_ok=True)
        raise HTTPException(502, f"Download fehlgeschlagen: {e}")


async def auto_fetch_if_missing() -> None:
    """Called at startup: pulls APK from FIRETV_APK_URL if not already present."""
    url = os.getenv("FIRETV_APK_URL", "")
    if url and not APK_PATH.exists():
        import logging
        log = logging.getLogger("photoflow")
        log.info("FIRETV_APK_URL gesetzt, APK fehlt → lade automatisch...")
        try:
            await _download_apk(url)
            log.info("FireTV APK erfolgreich geladen: %s", APK_PATH)
        except Exception as e:
            log.warning("FireTV-APK-Auto-Download fehlgeschlagen: %s", e)
