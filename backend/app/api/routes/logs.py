"""Structured log reader for the UI — returns recent log entries per feature."""
import os, re, pathlib
from typing import List, Optional
from fastapi import APIRouter, Query
from pydantic import BaseModel

router = APIRouter(prefix="/logs", tags=["logs"])

# Each feature writes to its own rotating file in /config/logs/
LOG_DIR = pathlib.Path(os.getenv("CONFIG_PATH", "/config")) / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

FEATURES = {
    "scanner": "scanner.log",
    "ai": "ai.log",
    "video": "video.log",
    "faces": "faces.log",
    "system": "system.log",
}


class LogEntry(BaseModel):
    ts: str
    level: str
    feature: str
    message: str


def _parse_line(line: str, feature: str) -> Optional[LogEntry]:
    # Expect: 2026-06-14 12:00:00 [INFO] message
    m = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+\[(\w+)\]\s+(.*)", line.strip())
    if not m:
        return None
    return LogEntry(ts=m.group(1), level=m.group(2), feature=feature, message=m.group(3))


@router.get("/{feature}", response_model=List[LogEntry])
async def get_logs(
    feature: str,
    limit: int = Query(200, ge=1, le=2000),
    level: Optional[str] = Query(None, description="Filter: DEBUG|INFO|WARNING|ERROR"),
):
    if feature not in FEATURES:
        from fastapi import HTTPException
        raise HTTPException(400, f"Unknown feature. Valid: {list(FEATURES)}")

    log_file = LOG_DIR / FEATURES[feature]
    if not log_file.exists():
        return []

    lines = log_file.read_text(errors="replace").splitlines()
    entries = [_parse_line(l, feature) for l in lines if l.strip()]
    entries = [e for e in entries if e is not None]

    if level:
        entries = [e for e in entries if e.level == level.upper()]

    return entries[-limit:]


@router.get("", response_model=List[LogEntry])
async def get_all_logs(
    limit: int = Query(200, ge=1, le=2000),
    level: Optional[str] = Query(None),
    feature: Optional[str] = Query(None),
):
    """Merged log stream across all features, newest last."""
    all_entries: List[LogEntry] = []
    features = [feature] if feature and feature in FEATURES else list(FEATURES)

    for feat in features:
        log_file = LOG_DIR / FEATURES[feat]
        if not log_file.exists():
            continue
        lines = log_file.read_text(errors="replace").splitlines()
        for l in lines:
            e = _parse_line(l, feat)
            if e:
                all_entries.append(e)

    if level:
        all_entries = [e for e in all_entries if e.level == level.upper()]

    all_entries.sort(key=lambda e: e.ts)
    return all_entries[-limit:]
