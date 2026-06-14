"""Per-feature file logger consumed by the Settings → Logs UI.

Writes lines like `2026-06-14 12:00:00 [INFO] message` to /config/logs/<feature>.log
(shared volume between backend + worker). Falls back to /tmp if /config is read-only.
"""
import os
import pathlib
from datetime import datetime, timezone

_VALID = {"scanner", "ai", "video", "faces", "system"}

_LOG_DIR = pathlib.Path(os.getenv("CONFIG_PATH", "/config")) / "logs"
try:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    _LOG_DIR = pathlib.Path("/tmp/photoflow-logs")
    _LOG_DIR.mkdir(parents=True, exist_ok=True)

# keep each file from growing unbounded
_MAX_BYTES = 2_000_000


def log(feature: str, level: str, message: str) -> None:
    """Append a structured log line. Never raises."""
    try:
        feat = feature if feature in _VALID else "system"
        f = _LOG_DIR / f"{feat}.log"
        # naive rotation: truncate head if file too big
        if f.exists() and f.stat().st_size > _MAX_BYTES:
            tail = f.read_text(errors="replace").splitlines()[-5000:]
            f.write_text("\n".join(tail) + "\n")
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        with f.open("a") as fh:
            fh.write(f"{ts} [{level.upper()}] {message}\n")
    except Exception:
        pass


def info(feature: str, message: str) -> None:
    log(feature, "INFO", message)


def warning(feature: str, message: str) -> None:
    log(feature, "WARNING", message)


def error(feature: str, message: str) -> None:
    log(feature, "ERROR", message)
