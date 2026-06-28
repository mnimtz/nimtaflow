"""Load persisted settings from the DB into a plain dict for AIManager etc."""
from typing import Dict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.settings import Setting


async def load_settings(db: AsyncSession) -> Dict[str, str]:
    """Return all settings as a {key: value} dict (secrets included — server-side only)."""
    result = await db.execute(select(Setting))
    return {s.key: s.value for s in result.scalars().all() if s.value is not None}
