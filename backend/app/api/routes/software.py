import asyncio
import json
import os
import socket
from datetime import datetime, timezone
from pathlib import Path

import aiofiles
import httpx
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel

from app.core.auth_guard import require_admin

APK_PATH = Path(os.getenv("APK_PATH", "/apk/nimtaflow-tv.apk"))
META_PATH = APK_PATH.with_suffix(".meta")

# Serialisiert konkurrierende Downloads — verhindert Race bei parallelem Startup-Hook + API-Request
_download_lock = asyncio.Lock()


def _parse_gh_date(s: str) -> datetime:
    """GitHub gibt 'Z'-suffixe zurück; fromisoformat braucht '+00:00'."""
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _save_meta(release_name: str) -> None:
    META_PATH.write_text(json.dumps({"installed_version": release_name}))


def _read_meta() -> dict:
    try:
        return json.loads(META_PATH.read_text())
    except Exception:
        return {}


router = APIRouter(prefix="/api/v1/software", tags=["software"])


def _apk_info() -> dict:
    if APK_PATH.exists():
        stat = APK_PATH.stat()
        meta = _read_meta()
        return {
            "available": True,
            "size_bytes": stat.st_size,
            "size_mb": round(stat.st_size / 1024 / 1024, 1),
            "updated_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            "installed_version": meta.get("installed_version") or "",
        }
    return {"available": False, "size_bytes": 0, "size_mb": 0.0, "updated_at": None, "installed_version": None}


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
async def firetv_info(_: None = Depends(require_admin)):
    return _apk_info()


@router.get("/firetv/update-check")
async def firetv_update_check(_: None = Depends(require_admin)):
    """Compare current APK mtime with the GitHub asset upload date."""
    release = await _fetch_latest_release()
    if not release:
        return {"has_update": False, "reason": "no_release", "release": None}

    # Use the asset's updated_at (changes on every CI push), NOT release published_at
    # (published_at stays fixed for a rolling 'firetv-latest' tag release)
    apk_asset = next(
        (a for a in release.get("assets", []) if a["name"].endswith(".apk")),
        None,
    )
    asset_url = apk_asset["browser_download_url"] if apk_asset else None
    release_date = (
        apk_asset.get("updated_at") or apk_asset.get("created_at")
        if apk_asset else
        release.get("published_at") or release.get("created_at")
    )
    apk = _apk_info()

    has_update = False
    if not apk["available"]:
        has_update = True
    elif release_date and apk["updated_at"]:
        has_update = _parse_gh_date(release_date) > _parse_gh_date(apk["updated_at"])

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
    release_name = release.get("name") or release.get("tag_name") or ""
    await _download_apk(asset_url, extra_headers=_gh_headers(), release_name=release_name)
    return _apk_info()


class FetchBody(BaseModel):
    url: str | None = None


@router.post("/firetv/fetch")
async def firetv_fetch(body: FetchBody, _: None = Depends(require_admin)):
    url = body.url or os.getenv("FIRETV_APK_URL", "")
    if not url:
        raise HTTPException(400, "Keine URL angegeben und FIRETV_APK_URL nicht konfiguriert")
    await _download_apk(url, release_name="Manuell geladen")
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
        _save_meta("Manuell hochgeladen")
    except Exception as e:
        tmp.unlink(missing_ok=True)
        raise HTTPException(500, str(e))
    return _apk_info()


async def _download_apk(url: str, extra_headers: dict | None = None, release_name: str | None = None) -> None:
    async with _download_lock:
        await _do_download_apk(url, extra_headers, release_name)


async def _do_download_apk(url: str, extra_headers: dict | None = None, release_name: str | None = None) -> None:
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
        if release_name is not None:
            _save_meta(release_name)
    except httpx.HTTPStatusError as e:
        tmp.unlink(missing_ok=True)
        raise HTTPException(502, f"Download fehlgeschlagen: HTTP {e.response.status_code}")
    except Exception as e:
        tmp.unlink(missing_ok=True)
        raise HTTPException(502, f"Download fehlgeschlagen: {e}")


# ── ADB Autodiscover ─────────────────────────────────────────────────────────

async def _adb(*args: str, timeout: float = 15) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        "adb", *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return proc.returncode or 0, stdout.decode(errors="replace")
    except asyncio.TimeoutError:
        proc.kill()
        return -1, "timeout"


async def _port_open(ip: str, port: int = 5555, timeout: float = 0.25) -> bool:
    try:
        _, writer = await asyncio.wait_for(asyncio.open_connection(ip, port), timeout=timeout)
        writer.close()
        await writer.wait_closed()
        return True
    except Exception:
        return False


def _local_subnet() -> str | None:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ".".join(ip.split(".")[:3])
    except Exception:
        return None


@router.get("/firetv/adb-devices")
async def firetv_adb_devices(
    subnet: str | None = None,
    _: None = Depends(require_admin),
):
    """Scant das /24-Subnetz auf ADB-Geräte (Port 5555).

    subnet: z.B. '192.168.0' — wird vom Client übergeben damit der Server
    das richtige Heimnetz scannt (nicht die Docker-Bridge).
    """
    if not subnet:
        subnet = _local_subnet()
    if not subnet:
        return {"devices": [], "error": "Subnetz nicht erkennbar"}

    ips = [f"{subnet}.{i}" for i in range(1, 255)]
    open_flags = await asyncio.gather(*[_port_open(ip) for ip in ips])
    open_ips = [ip for ip, ok in zip(ips, open_flags) if ok]

    devices = []
    for ip in open_ips:
        addr = f"{ip}:5555"
        await _adb("connect", addr, timeout=5)
        _, output = await _adb("devices", "-l")
        for line in output.splitlines():
            if ip in line and "device" in line:
                parts = line.split()
                state = parts[1] if len(parts) > 1 else "unknown"
                model = next((p.split(":")[-1] for p in parts if p.startswith("model:")), addr)
                devices.append({"id": addr, "model": model, "state": state, "ip": ip})
                break

    return {"devices": devices}


class AdbInstallBody(BaseModel):
    device_id: str


@router.post("/firetv/adb-install")
async def firetv_adb_install(body: AdbInstallBody, _: None = Depends(require_admin)):
    """Schickt das APK via ADB auf ein Gerät."""
    if not APK_PATH.exists():
        raise HTTPException(404, "APK fehlt — zuerst bereitstellen")
    rc, output = await _adb("-s", body.device_id, "install", "-r", "-t", str(APK_PATH), timeout=120)
    if rc != 0:
        raise HTTPException(500, f"ADB-Install fehlgeschlagen: {output[:500]}")
    return {"success": True, "device_id": body.device_id, "output": output[:300]}


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
