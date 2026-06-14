from typing import Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.settings import Setting

router = APIRouter(prefix="/settings", tags=["settings"])

SECRET_KEYS = {"ai.gemini.api_key", "ai.openai.api_key", "ai.anthropic.api_key"}


@router.get("")
async def get_settings(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    result = await db.execute(select(Setting))
    settings = result.scalars().all()
    out = {}
    for s in settings:
        out[s.key] = "***" if s.is_secret else s.value
    return out


@router.put("")
async def update_settings(data: Dict[str, Any], db: AsyncSession = Depends(get_db)):
    for key, value in data.items():
        if value == "***":
            continue  # Don't overwrite secrets with placeholder
        existing = await db.scalar(select(Setting).where(Setting.key == key))
        is_secret = key in SECRET_KEYS
        if existing:
            existing.value = str(value) if value is not None else None
            existing.is_secret = is_secret
        else:
            db.add(Setting(key=key, value=str(value) if value is not None else None, is_secret=is_secret))
    await db.commit()
    return {"ok": True}


@router.get("/defaults")
async def get_defaults():
    return {
        "ai.provider": "none",
        "ai.language": "de",
        "ai.gemini.model": "gemini-2.5-flash",
        "ai.gemini.embed_model": "text-embedding-004",
        "ai.ollama.url": "http://localhost:11434",
        "ai.ollama.vision_model": "llava:7b",
        "ai.ollama.embed_model": "nomic-embed-text",
        "pipeline.batch_size": "50",
        "pipeline.workers": "4",
        "pipeline.retry_count": "3",
        "pipeline.cron": "0 2 * * *",
        "thumbnail.small": "320",
        "thumbnail.medium": "800",
        "thumbnail.large": "1920",
        "map.provider": "nominatim",
        "face.clustering_threshold": "0.6",
        "face.min_confidence": "0.7",
        "face.min_size_px": "40",
    }
