"""Backup orchestration: DB dump + cache archive + optional rclone offsite sync."""
import asyncio
import datetime
import os
import shutil
import subprocess
import pathlib
import json
from typing import Optional, Dict, Any

_cache = pathlib.Path(os.getenv("CACHE_PATH", "/cache"))
BACKUP_DIR = _cache / "backups"
try:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
except PermissionError:
    BACKUP_DIR = pathlib.Path("/tmp/photoflow-backups")
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

_RCLONE = shutil.which("rclone")
_PG_DUMP = shutil.which("pg_dump") or "pg_dump"
_PSQL = shutil.which("psql") or "psql"


def _pg_url(db_url: str) -> str:
    return db_url.replace("postgresql+asyncpg://", "postgresql://")


def _ts() -> str:
    return datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")


# ── Database dump ─────────────────────────────────────────────────────────────

async def dump_database(db_url: str) -> Optional[str]:
    """Async pg_dump to <backup_dir>/db_<ts>.sql.gz"""
    ts = _ts()
    out = BACKUP_DIR / f"db_{ts}.sql.gz"

    # Convert asyncpg URL → psql URL
    pg_url = _pg_url(db_url)

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


# ── Cache/thumbnail archive ───────────────────────────────────────────────────

async def archive_cache(cache_path: str) -> Optional[str]:
    """Tar-gz the thumbnail/cache dir so a restore doesn't have to regenerate
    every thumbnail. Excludes the backups dir itself (would recurse)."""
    ts = _ts()
    out = BACKUP_DIR / f"cache_{ts}.tar.gz"
    try:
        proc = await asyncio.create_subprocess_exec(
            "tar", "-czf", str(out), "-C", cache_path,
            "--exclude=./backups", ".",
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        await proc.wait()
        if proc.returncode in (0, 1) and out.exists() and out.stat().st_size > 100:
            # tar exit 1 = "file changed while reading" (a thumbnail was written
            # mid-archive); the archive is still valid.
            return str(out)
        out.unlink(missing_ok=True)
    except Exception:
        pass
    return None


# ── Restore ───────────────────────────────────────────────────────────────────

async def restore_database(db_url: str, sql_gz: str) -> Dict[str, Any]:
    """Restore a db_*.sql.gz dump (created with --clean --if-exists, so it drops
    and recreates objects). DESTRUCTIVE for the target database."""
    p = pathlib.Path(sql_gz)
    if not p.exists():
        return {"ok": False, "error": "dump not found"}
    try:
        gunzip = await asyncio.create_subprocess_exec(
            "gunzip", "-c", str(p), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        psql = await asyncio.create_subprocess_exec(
            _PSQL, "--dbname", _pg_url(db_url), "-v", "ON_ERROR_STOP=0",
            stdin=gunzip.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        _, perr = await psql.communicate()
        await gunzip.wait()
        ok = psql.returncode == 0
        return {"ok": ok, "stderr": perr.decode(errors="replace")[-800:]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def verify_database_dump(db_url: str, sql_gz: str) -> Dict[str, Any]:
    """Non-destructive integrity check: restore the dump into a scratch database
    and count the photos table, then drop the scratch DB. Proves the dump is
    actually restorable without touching live data."""
    p = pathlib.Path(sql_gz)
    if not p.exists():
        return {"ok": False, "error": "dump not found"}
    base = _pg_url(db_url)
    scratch = "photoflow_verify"
    admin = base.rsplit("/", 1)[0] + "/postgres"
    target = base.rsplit("/", 1)[0] + "/" + scratch
    try:
        async def _psql_run(dsn, sql):
            pr = await asyncio.create_subprocess_exec(
                _PSQL, "--dbname", dsn, "-c", sql,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            o, e = await pr.communicate()
            return pr.returncode, (o + e).decode(errors="replace")
        await _psql_run(admin, f"DROP DATABASE IF EXISTS {scratch}")
        await _psql_run(admin, f"CREATE DATABASE {scratch}")
        await _psql_run(target, "CREATE EXTENSION IF NOT EXISTS vector")
        restore = await restore_database(target.replace("postgresql://", "postgresql+asyncpg://"), sql_gz)
        rc, out = await _psql_run(target, "SELECT count(*) FROM photos")
        await _psql_run(admin, f"DROP DATABASE IF EXISTS {scratch}")
        import re
        m = re.search(r"\d+", out)
        return {"ok": rc == 0 and m is not None, "photos": int(m.group()) if m else None,
                "restore_ok": restore.get("ok")}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def restore_archive(tar_gz: str, dest: str) -> Dict[str, Any]:
    """Extract a config_*/cache_*.tar.gz back into dest (e.g. /config, /cache)."""
    p = pathlib.Path(tar_gz)
    if not p.exists():
        return {"ok": False, "error": "archive not found"}
    try:
        proc = await asyncio.create_subprocess_exec(
            "tar", "-xzf", str(p), "-C", dest,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        _, err = await proc.communicate()
        return {"ok": proc.returncode == 0, "stderr": err.decode(errors="replace")[-400:]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


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
            "type": "db" if f.name.startswith("db_") else ("cache" if f.name.startswith("cache_") else "config"),
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

async def run_full_backup(db_url: str, config_path: str, rclone_remote: Optional[str] = None,
                          cache_path: Optional[str] = None) -> Dict[str, Any]:
    """Orchestrate a complete backup: DB + config + thumbnails + optional offsite."""
    cache_path = cache_path or os.getenv("CACHE_PATH", "/cache")
    db_file, cfg_file, cache_file = await asyncio.gather(
        dump_database(db_url),
        archive_config(config_path),
        archive_cache(cache_path),
    )

    result: Dict[str, Any] = {
        "ts": _ts(),
        "db": {"ok": bool(db_file), "file": db_file},
        "config": {"ok": bool(cfg_file), "file": cfg_file},
        "cache": {"ok": bool(cache_file), "file": cache_file},
        "rclone": None,
    }

    if rclone_remote and (db_file or cfg_file or cache_file):
        result["rclone"] = await rclone_sync(rclone_remote)

    return result
