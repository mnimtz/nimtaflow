"""Load persisted settings from the DB into a plain dict for AIManager etc."""
from typing import Dict, Optional
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.settings import Setting


async def load_settings(db: AsyncSession) -> Dict[str, str]:
    """Return all settings as a {key: value} dict (secrets included — server-side only)."""
    result = await db.execute(select(Setting))
    return {s.key: s.value for s in result.scalars().all() if s.value is not None}


async def save_setting(db: AsyncSession, key: str, value: Optional[str]) -> None:
    """Upsert a single setting. Pass value=None or '' to clear it."""
    if not value:
        await db.execute(
            __import__("sqlalchemy", fromlist=["delete"]).delete(Setting).where(Setting.key == key)
        )
    else:
        stmt = pg_insert(Setting).values(key=key, value=value)
        stmt = stmt.on_conflict_do_update(index_elements=["key"], set_={"value": value})
        await db.execute(stmt)
    await db.commit()
