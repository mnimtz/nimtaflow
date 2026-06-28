"""Timezone-aware UTC helper for DB timestamp defaults.

Use `utcnow` for `timestamptz` column defaults/onupdate. The naive `datetime.utcnow()`
gets misinterpreted by asyncpg as the container's LOCAL timezone (Europe/Berlin, +2)
when bound to a timestamptz column → timestamps are stored hours in the past.
An aware UTC datetime binds correctly.
"""
from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
