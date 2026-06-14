"""Backup orchestration: DB dump + cache archive + optional rclone offsite sync."""
import asyncio
import datetime
import os
import shutil
import subprocess
import pathlib
import json
from typing import Optional, Dict, Any

BACKUP_DIR = pathlib.Path(os.getenv("CACHE_PATH", "/cache")) / "backups"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

_RCLONE = shutil.which("rclone")
_PG_DUMP = shutil.which("pg_dump") or "pg_dump"


def _ts() -> str:
    return datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")


# ── Database dump ─────────────────────────────────────────────────────────────

async def dump_database(db_url: str) -> Optional[str]:
    """Async pg_dump to <backup_dir>/db_<ts>.sql.gz"""
    ts = _ts()
    out = BACKUP_DIR / f"db_{ts}.sql.gz"

    # Convert asyncpg URL → psql URL
    pg_url = db_url.replace("postgresql+asyncpg://", "postgresql://")

    try:
        proc = await asyncio.create_subprocess_exec(
            _PG_DUMP, "--clean", "--if-exists", "--no-owner",
            "--dbname", pg_url,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        gz_proc = await asyncio.create_subprocess_exec(
            "gzip", "-c",
            stdin=proc.stdout, stdout=open(str(out), "wb"), stderr=subprocess.PIPE,
        )
        await asyncio.gather(proc.wait(), gz_proc.wait())

        if proc.returncode == 0 and out.exists() and out.stat().st_size > 100:
            return str(out)
        out.unlink(missing_ok=True)
    except Exception as e:
        return None
    return None


# ── Config/metadata archive ───────────────────────────────────────────────────

async def archive_config(config_path: str) -> Optional[str]:
    """Tar-gz the config directory (settings, logs etc.)."""
    ts = _ts()
    out = BACKUP_DIR / f"config_{ts}.tar.gz"
    try:
        proc = await asyncio.create_subprocess_exec(
            "tar", "-czf", str(out), "-C", config_path, ".",
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        await proc.wait()
        if proc.returncode == 0 and out.exists():
            return str(out)
    except Exception:
        pass
    return None


# ── Rclone offsite sync ───────────────────────────────────────────────────────

async def rclone_sync(remote: str, dry_run: bool = False) -> Dict[str, Any]:
    """Sync backup dir to rclone remote (e.g. 'b2:my-bucket/photoflow')."""
    if not _RCLONE:
        return {"ok": False, "error": "rclone not installed"}

    cmd = [_RCLONE, "sync", str(BACKUP_DIR), remote, "--progress", "--stats-one-line"]
    if dry_run:
        cmd.append("--dry-run")

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=600)
        ok = proc.returncode == 0
        return {
            "ok": ok,
            "remote": remote,
            "dry_run": dry_run,
            "output": (stdout + stderr).decode(errors="replace")[-1000:],
        }
    except asyncio.TimeoutError:
        return {"ok": False, "error": "rclone timeout (>10 min)"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── List + cleanup ────────────────────────────────────────────────────────────

def list_backups() -> list[Dict[str, Any]]:
    """Return all backup files sorted newest first."""
    files = []
    for f in sorted(BACKUP_DIR.glob("*.gz"), reverse=True):
        stat = f.stat()
        files.append({
            "name": f.name,
            "path": str(f),
            "size_mb": round(stat.st_size / 1024 / 1024, 2),
            "created_at": datetime.datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "type": "db" if f.name.startswith("db_") else "config",
        })
    return files


def prune_backups(keep_days: int = 30) -> int:
    """Delete backups older than keep_days. Returns count deleted."""
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=keep_days)
    deleted = 0
    for f in BACKUP_DIR.glob("*.gz"):
        mtime = datetime.datetime.fromtimestamp(f.stat().st_mtime)
        if mtime < cutoff:
            f.unlink()
            deleted += 1
    return deleted


# ── Full backup ───────────────────────────────────────────────────────────────

async def run_full_backup(db_url: str, config_path: str, rclone_remote: Optional[str] = None) -> Dict[str, Any]:
    """Orchestrate a complete backup: DB + config + optional offsite."""
    db_file, cfg_file = await asyncio.gather(
        dump_database(db_url),
        archive_config(config_path),
    )

    result: Dict[str, Any] = {
        "ts": _ts(),
        "db": {"ok": bool(db_file), "file": db_file},
        "config": {"ok": bool(cfg_file), "file": cfg_file},
        "rclone": None,
    }

    if rclone_remote and (db_file or cfg_file):
        result["rclone"] = await rclone_sync(rclone_remote)

    return result
