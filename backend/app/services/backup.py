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
_OPENSSL = shutil.which("openssl") or "openssl"


def _pg_url(db_url: str) -> str:
    return db_url.replace("postgresql+asyncpg://", "postgresql://")


def _ts() -> str:
    return datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")


# ── Encryption (openssl AES-256-CBC) ──────────────────────────────────────────

class BackupError(Exception):
    """Raised when a backup cannot proceed safely (e.g. encryption requested but
    no passphrase available — we must NOT silently write plaintext)."""


def _resolve_passphrase(settings: Optional[Dict[str, str]] = None) -> Optional[str]:
    """Encryption passphrase: env PHOTOFLOW_BACKUP_PASSPHRASE wins over the DB
    setting backup.passphrase. Returns None if neither is set."""
    env = os.getenv("PHOTOFLOW_BACKUP_PASSPHRASE")
    if env:
        return env
    if settings:
        v = (settings.get("backup.passphrase") or "").strip()
        if v:
            return v
    return None


def _encryption_enabled(settings: Optional[Dict[str, str]] = None) -> bool:
    if not settings:
        return False
    return str(settings.get("backup.encrypt", "false")).lower() == "true"


async def encrypt_file(path: str, passphrase: str) -> str:
    """Encrypt <path> → <path>.enc with openssl AES-256-CBC (PBKDF2 + salt), then
    remove the plaintext input. Returns the .enc path. Raises BackupError on failure."""
    src = pathlib.Path(path)
    out = pathlib.Path(str(path) + ".enc")
    proc = await asyncio.create_subprocess_exec(
        _OPENSSL, "enc", "-aes-256-cbc", "-pbkdf2", "-salt",
        "-pass", f"pass:{passphrase}", "-in", str(src), "-out", str(out),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    _, err = await proc.communicate()
    if proc.returncode != 0 or not out.exists() or out.stat().st_size < 1:
        out.unlink(missing_ok=True)
        raise BackupError(f"openssl encrypt failed: {err.decode(errors='replace')[-300:]}")
    src.unlink(missing_ok=True)
    return str(out)


async def decrypt_file(path: str, passphrase: str, dest: Optional[str] = None) -> str:
    """Decrypt a *.enc file (openssl -d) into dest (default: strip the .enc suffix).
    Returns the decrypted path. Raises BackupError on failure."""
    src = pathlib.Path(path)
    if dest is None:
        dest = str(src)[:-4] if str(src).endswith(".enc") else str(src) + ".dec"
    out = pathlib.Path(dest)
    proc = await asyncio.create_subprocess_exec(
        _OPENSSL, "enc", "-d", "-aes-256-cbc", "-pbkdf2",
        "-pass", f"pass:{passphrase}", "-in", str(src), "-out", str(out),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    _, err = await proc.communicate()
    if proc.returncode != 0 or not out.exists():
        out.unlink(missing_ok=True)
        raise BackupError(f"openssl decrypt failed (wrong passphrase?): {err.decode(errors='replace')[-300:]}")
    return str(out)


async def _maybe_decrypt_to_temp(path: str, passphrase: Optional[str]) -> tuple[str, bool]:
    """If <path> ends in .enc, decrypt it to a temp .gz and return (temp_path, True).
    Otherwise return (path, False). Caller must clean up when the 2nd element is True."""
    if not str(path).endswith(".enc"):
        return path, False
    if not passphrase:
        raise BackupError("encrypted backup (.enc) but no passphrase available")
    import tempfile
    fd, tmp = tempfile.mkstemp(suffix=".gz", dir=str(BACKUP_DIR))
    os.close(fd)
    await decrypt_file(path, passphrase, dest=tmp)
    return tmp, True


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
        if proc.returncode in (0, 1) and out.exists() and out.stat().st_size > 100:
            return str(out)
        out.unlink(missing_ok=True)
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

async def restore_database(db_url: str, sql_gz: str,
                           settings: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Restore a db_*.sql.gz (or db_*.sql.gz.enc) dump (created with --clean
    --if-exists, so it drops and recreates objects). DESTRUCTIVE for the target
    database. An .enc artifact is decrypted to a temp .gz first."""
    import shlex
    p = pathlib.Path(sql_gz)
    if not p.exists():
        return {"ok": False, "error": "dump not found"}
    tmp = None
    try:
        use, tmp_made = await _maybe_decrypt_to_temp(str(p), _resolve_passphrase(settings))
        if tmp_made:
            tmp = use
        # Use a shell pipe — chaining two asyncio subprocesses via stdout/stdin
        # fails ("StreamReader has no fileno"). gunzip → psql.
        # Keep ON_ERROR_STOP=0 (benign idempotent DROP/CREATE EXTENSION noise must
        # not abort a real restore), but DON'T blindly report success: count real
        # "ERROR:" lines and fail the restore if any appear. The old code returned
        # ok=True purely on the (almost-always-0) return code, masking broken restores.
        cmd = f"gunzip -c {shlex.quote(use)} | {shlex.quote(_PSQL)} --dbname {shlex.quote(_pg_url(db_url))} -v ON_ERROR_STOP=0"
        proc = await asyncio.create_subprocess_shell(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        _, perr = await proc.communicate()
        err = perr.decode(errors="replace")
        n_errors = err.count("ERROR:")
        return {"ok": proc.returncode == 0 and n_errors == 0,
                "errors": n_errors, "stderr": err[-1200:]}
    except BackupError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        if tmp:
            pathlib.Path(tmp).unlink(missing_ok=True)


async def verify_database_dump(db_url: str, sql_gz: str,
                               settings: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Non-destructive integrity check: decompress the dump and confirm it holds
    the schema (CREATE TABLE) and the photos table data (COPY public.photos …),
    AND that the gzip stream itself is intact (gunzip -t). Proves the dump is
    complete & restorable without touching any database or needing CREATEDB
    privileges. Handles .enc artifacts (decrypts to a temp .gz first)."""
    p = pathlib.Path(sql_gz)
    if not p.exists():
        return {"ok": False, "error": "dump not found"}
    size_mb = round(p.stat().st_size / 1048576, 2)
    tmp = None
    try:
        use, tmp_made = await _maybe_decrypt_to_temp(str(p), _resolve_passphrase(settings))
        if tmp_made:
            tmp = use
        # 1) True gzip integrity check — catches truncated/corrupt archives that the
        #    old string-count would happily pass once content was readable.
        gt = await asyncio.create_subprocess_exec(
            "gunzip", "-t", use, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        _, gterr = await gt.communicate()
        gzip_ok = gt.returncode == 0
        if not gzip_ok:
            return {"ok": False, "gzip_ok": False, "size_mb": size_mb,
                    "error": "gzip integrity check failed: " + gterr.decode(errors="replace")[-200:]}
        # 2) Content check.
        proc = await asyncio.create_subprocess_exec(
            "gunzip", "-c", use, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, _ = await proc.communicate()
        text = out.decode(errors="replace")
        tables = text.count("CREATE TABLE ")
        # Anchor on the opening paren so we don't match e.g. "photos_tags".
        marker = "COPY public.photos ("
        has_photos = marker in text
        rows = 0
        if has_photos:
            body = text.split(marker, 1)[1].split("\n\\.", 1)[0]
            rows = max(0, body.count("\n") - 1)  # exclude the "(cols) FROM stdin;" line
        return {
            "ok": gzip_ok and tables > 0 and has_photos,
            "gzip_ok": gzip_ok,
            "tables": tables,
            "photo_rows": rows,
            "encrypted": str(p).endswith(".enc"),
            "size_mb": size_mb,
        }
    except BackupError as e:
        return {"ok": False, "error": str(e), "size_mb": size_mb}
    except Exception as e:
        return {"ok": False, "error": str(e), "size_mb": size_mb}
    finally:
        if tmp:
            pathlib.Path(tmp).unlink(missing_ok=True)


async def restore_archive(tar_gz: str, dest: str,
                          settings: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Extract a config_*/cache_*.tar.gz (or .tar.gz.enc) back into dest (e.g.
    /config, /cache). An .enc artifact is decrypted to a temp .gz first."""
    p = pathlib.Path(tar_gz)
    if not p.exists():
        return {"ok": False, "error": "archive not found"}
    tmp = None
    try:
        use, tmp_made = await _maybe_decrypt_to_temp(str(p), _resolve_passphrase(settings))
        if tmp_made:
            tmp = use
        proc = await asyncio.create_subprocess_exec(
            "tar", "-xzf", use, "-C", dest,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        _, err = await proc.communicate()
        return {"ok": proc.returncode == 0, "stderr": err.decode(errors="replace")[-400:]}
    except BackupError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        if tmp:
            pathlib.Path(tmp).unlink(missing_ok=True)


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


# ── Originals offsite mirror ──────────────────────────────────────────────────

async def mirror_originals_to_remote(sources: list[str], remote: str) -> Dict[str, Any]:
    """ONE-WAY mirror of the original photo/video files to <remote>, reflecting
    local deletions but keeping a recoverable dated trash on the remote.

    Each enabled source is mirrored to <remote>/<basename> with deletions moved to
    <remote>-trash/<YYYY-MM-DD>/<basename> (so a deletion is undoable for a while).
    rclone sync = make dest match src; --backup-dir captures whatever would be
    deleted/overwritten instead of dropping it."""
    if not _RCLONE:
        return {"ok": False, "error": "rclone not installed"}
    remote = remote.rstrip("/")
    if not remote:
        return {"ok": False, "error": "no remote configured"}
    if not sources:
        return {"ok": False, "error": "no enabled sources"}
    trash_base = f"{remote}-trash"
    day = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    results = []
    overall_ok = True
    for src in sources:
        base = os.path.basename(os.path.normpath(src)) or "root"
        dest = f"{remote}/{base}"
        backup_dir = f"{trash_base}/{day}/{base}"
        cmd = [_RCLONE, "sync", src, dest,
               "--backup-dir", backup_dir,
               "--fast-list", "--transfers", "4", "--checkers", "8",
               "--stats-one-line"]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=6 * 3600)
            ok = proc.returncode == 0
            overall_ok = overall_ok and ok
            results.append({
                "source": src, "dest": dest, "ok": ok, "rc": proc.returncode,
                "output": (stdout + stderr).decode(errors="replace")[-800:],
            })
        except asyncio.TimeoutError:
            overall_ok = False
            results.append({"source": src, "dest": dest, "ok": False, "error": "rclone timeout (>6h)"})
        except Exception as e:
            overall_ok = False
            results.append({"source": src, "dest": dest, "ok": False, "error": str(e)})
    return {"ok": overall_ok, "remote": remote, "trash": trash_base,
            "day": day, "sources": results}


# ── List + cleanup ────────────────────────────────────────────────────────────

def list_backups() -> list[Dict[str, Any]]:
    """Return all backup files sorted newest first."""
    files = []
    seen = set()
    for pattern in ("*.gz", "*.gz.enc"):
        for f in BACKUP_DIR.glob(pattern):
            if f in seen:
                continue
            seen.add(f)
            stat = f.stat()
            files.append({
                "name": f.name,
                "path": str(f),
                "size_mb": round(stat.st_size / 1024 / 1024, 2),
                "created_at": datetime.datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "encrypted": f.name.endswith(".enc"),
                "type": "db" if f.name.startswith("db_") else ("cache" if f.name.startswith("cache_") else "config"),
            })
    files.sort(key=lambda x: x["name"], reverse=True)
    return files


def prune_backups(keep_days: int = 30) -> int:
    """Delete backups older than keep_days. Returns count deleted."""
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=keep_days)
    deleted = 0
    seen = set()
    for pattern in ("*.gz", "*.gz.enc"):
        for f in BACKUP_DIR.glob(pattern):
            if f in seen:
                continue
            seen.add(f)
            mtime = datetime.datetime.fromtimestamp(f.stat().st_mtime)
            if mtime < cutoff:
                f.unlink()
                deleted += 1
    return deleted


# ── Full backup ───────────────────────────────────────────────────────────────

async def run_full_backup(db_url: str, config_path: str, rclone_remote: Optional[str] = None,
                          cache_path: Optional[str] = None,
                          include_thumbnails: bool = True,
                          settings: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Orchestrate a complete backup: DB (always — includes the pgvector embeddings,
    so search/faces survive) + config + optionally the thumbnail cache + optional
    offsite. Thumbnails are fully REGENERABLE, so include_thumbnails lets the user
    shrink the backup and just re-derive them on restore.
    NOTE: original photo/video FILES are intentionally NOT in the backup (only their
    DB path references) — that's why a full backup is far smaller than the library."""
    cache_path = cache_path or os.getenv("CACHE_PATH", "/cache")
    tasks = [dump_database(db_url), archive_config(config_path)]
    if include_thumbnails:
        tasks.append(archive_cache(cache_path))
    done = await asyncio.gather(*tasks)
    db_file, cfg_file = done[0], done[1]
    cache_file = done[2] if include_thumbnails else None

    # Optional symmetric encryption of every produced artifact. The DB dump can
    # contain API keys in plaintext, so when enabled we encrypt each .gz → .gz.enc
    # and drop the plaintext. If enabled but no passphrase is available we FAIL the
    # backup (BackupError) rather than leaving plaintext on disk.
    encrypt = _encryption_enabled(settings)
    if encrypt:
        passphrase = _resolve_passphrase(settings)
        if not passphrase:
            # Remove the plaintext artifacts we just wrote — never leave them behind.
            for f in (db_file, cfg_file, cache_file):
                if f:
                    pathlib.Path(f).unlink(missing_ok=True)
            raise BackupError("backup.encrypt is on but no passphrase set "
                              "(set PHOTOFLOW_BACKUP_PASSPHRASE or backup.passphrase)")
        if db_file:
            db_file = await encrypt_file(db_file, passphrase)
        if cfg_file:
            cfg_file = await encrypt_file(cfg_file, passphrase)
        if cache_file:
            cache_file = await encrypt_file(cache_file, passphrase)

    result: Dict[str, Any] = {
        "ts": _ts(),
        "db": {"ok": bool(db_file), "file": db_file},
        "config": {"ok": bool(cfg_file), "file": cfg_file},
        "cache": {"ok": bool(cache_file), "file": cache_file,
                  "skipped": not include_thumbnails},
        "encrypted": encrypt,
        "originals_included": False,   # by design — see docstring
        "rclone": None,
    }

    if rclone_remote and (db_file or cfg_file or cache_file):
        result["rclone"] = await rclone_sync(rclone_remote)

    return result
