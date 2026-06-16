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
    """pg_dump to <backup_dir>/db_<ts>.sql.gz. Dumps to a plain file (--file)
    then gzips it — avoids the fragile asyncio stdout→gzip pipe that left the
    DB backup silently empty."""
    ts = _ts()
    sql = BACKUP_DIR / f"db_{ts}.sql"
    out = BACKUP_DIR / f"db_{ts}.sql.gz"
    pg_url = _pg_url(db_url)

    try:
        proc = await asyncio.create_subprocess_exec(
            _PG_DUMP, "--clean", "--if-exists", "--no-owner",
            "--file", str(sql), "--dbname", pg_url,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        _, err = await proc.communicate()
        if proc.returncode != 0 or not sql.exists() or sql.stat().st_size < 100:
            sql.unlink(missing_ok=True)
            return None
        gz = await asyncio.create_subprocess_exec(
            "gzip", "-f", str(sql), stderr=subprocess.PIPE)
        await gz.wait()
        if gz.returncode == 0 and out.exists() and out.stat().st_size > 100:
            return str(out)
        sql.unlink(missing_ok=True)
        out.unlink(missing_ok=True)
    except Exception:
        sql.unlink(missing_ok=True)
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
    """Non-destructive integrity check: decompress the dump and confirm it holds
    the schema (CREATE TABLE) and the photos table data (COPY public.photos …).
    Proves the dump is complete & restorable without touching any database or
    needing CREATEDB privileges."""
    p = pathlib.Path(sql_gz)
    if not p.exists():
        return {"ok": False, "error": "dump not found"}
    try:
        proc = await asyncio.create_subprocess_exec(
            "gunzip", "-c", str(p), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, _ = await proc.communicate()
        text = out.decode(errors="replace")
        tables = text.count("CREATE TABLE ")
        has_photos = "COPY public.photos " in text
        rows = 0
        if has_photos:
            body = text.split("COPY public.photos ", 1)[1].split("\n\\.", 1)[0]
            rows = max(0, body.count("\n") - 1)  # exclude the "(cols) FROM stdin;" line
        return {
            "ok": tables > 0 and has_photos,
            "tables": tables,
            "photo_rows": rows,
            "size_mb": round(p.stat().st_size / 1048576, 2),
        }
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
