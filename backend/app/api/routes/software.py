import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path

import aiofiles
import httpx
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel

from app.core.auth_guard import require_admin

APK_PATH = Path(os.getenv("APK_PATH", "/apk/nimtaflow-tv.apk"))

# Serialisiert konkurrierende Downloads — verhindert Race bei parallelem Startup-Hook + API-Request
_download_lock = asyncio.Lock()


def _parse_gh_date(s: str) -> datetime:
    """GitHub gibt 'Z'-suffixe zurück; fromisoformat braucht '+00:00'."""
    return datetime.fromisoformat(s.replace("Z", "+00:00"))

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


def _gh_headers() -> dict:
    token = os.getenv("FIRETV_GITHUB_TOKEN", "")
    return {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"} if token else {"Accept": "application/vnd.github+json"}


async def _fetch_latest_release() -> dict | None:
    """Returns the GitHub release info dict for tag 'firetv-latest', or None."""
    repo = os.getenv("FIRETV_GITHUB_REPO", "mnimtz/nimtaflow")
    url = f"https://api.github.com/repos/{repo}/releases/tags/firetv-latest"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(url, headers=_gh_headers())
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()
    except Exception:
        return None


@router.get("/firetv")
async def firetv_info():
    return _apk_info()


@router.get("/firetv/update-check")
async def firetv_update_check(_: None = Depends(require_admin)):
    """Compare current APK mtime with the firetv-latest GitHub Release date."""
    release = await _fetch_latest_release()
    if not release:
        return {"has_update": False, "reason": "no_release", "release": None}

    release_date = release.get("published_at") or release.get("created_at")
    apk = _apk_info()

    has_update = False
    if not apk["available"]:
        has_update = True
    elif release_date and apk["updated_at"]:
        has_update = _parse_gh_date(release_date) > _parse_gh_date(apk["updated_at"])

    # Find the APK asset download URL
    asset_url = next(
        (a["browser_download_url"] for a in release.get("assets", []) if a["name"].endswith(".apk")),
        None,
    )

    return {
        "has_update": has_update,
        "release_name": release.get("name") or release.get("tag_name"),
        "release_date": release_date,
        "download_url": asset_url,
        "current_updated_at": apk["updated_at"],
    }


@router.post("/firetv/update-now")
async def firetv_update_now(_: None = Depends(require_admin)):
    """Pull the firetv-latest GitHub Release APK right now."""
    release = await _fetch_latest_release()
    if not release:
        raise HTTPException(404, "Kein 'firetv-latest'-Release auf GitHub gefunden")
    asset_url = next(
        (a["browser_download_url"] for a in release.get("assets", []) if a["name"].endswith(".apk")),
        None,
    )
    if not asset_url:
        raise HTTPException(404, "Kein APK-Asset im Release gefunden")
    await _download_apk(asset_url, extra_headers=_gh_headers())
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


async def _download_apk(url: str, extra_headers: dict | None = None) -> None:
    async with _download_lock:
        await _do_download_apk(url, extra_headers)


async def _do_download_apk(url: str, extra_headers: dict | None = None) -> None:
    APK_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = APK_PATH.with_suffix(".tmp")
    headers = extra_headers or {}
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=120) as client:
            async with client.stream("GET", url, headers=headers) as resp:
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
