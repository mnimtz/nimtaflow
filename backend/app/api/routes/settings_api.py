from datetime import timedelta
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.auth_guard import current_user_optional
from app.core.security import create_access_token
from app.models.settings import Setting
from app.models.user import User, UserRole

router = APIRouter(prefix="/settings", tags=["settings"])

SECRET_KEYS = {"ai.gemini.api_key", "ai.openai.api_key", "ai.anthropic.api_key", "remote.token"}


@router.get("")
async def get_settings(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    result = await db.execute(select(Setting))
    settings = result.scalars().all()
    out = {}
    for s in settings:
        out[s.key] = "***" if s.is_secret else s.value
    return out


@router.patch("")
async def patch_settings(data: Dict[str, Any], db: AsyncSession = Depends(get_db)):
    return await update_settings(data, db)


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
    # Re-sync hidden-folder flags whenever the list is saved.
    if "display.hidden_folders" in data:
        try:
            from app.worker.tasks import apply_hidden_folders_task
            apply_hidden_folders_task.delay()
        except Exception:
            pass
    return {"ok": True}


@router.get("/defaults")
async def get_defaults():
    return {
        "ai.provider": "none",
        "ai.language": "de",
        "chat.provider": "gemini",
        "scan.force_reindex": "false",
        "scan.faces_on_import": "true",
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
        # ── MCP-Server (NimtaFlow als MCP für Claude & Co.) ──────────────────────
        "mcp.enabled": "false",
        "mcp.mode": "read",            # read | read_write
        "mcp.share_ttl_hours": "24",   # Lebensdauer der vom MCP erzeugten Share-Links
    }


# ── MCP-Server ──────────────────────────────────────────────────────────────────

async def _resolve_user(user: Optional[User], db: AsyncSession) -> Optional[User]:
    """In offenem Single-User-Modus (kein Login erzwungen) ist `user` None → dann den
    ersten Admin nehmen, damit der MCP-Token ein echtes Konto referenziert."""
    if user:
        return user
    return await db.scalar(
        select(User).where(User.is_active == True)  # noqa: E712
        .order_by((User.role == UserRole.admin).desc(), User.id).limit(1)
    )


@router.get("/mcp-status")
async def mcp_status(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """Vom MCP-Server bei jedem Tool-Aufruf gelesen → respektiert den An/Aus-Schalter."""
    rows = (await db.execute(select(Setting).where(
        Setting.key.in_(["mcp.enabled", "mcp.mode", "mcp.share_ttl_hours"])
    ))).scalars().all()
    cur = {s.key: s.value for s in rows}
    return {
        "enabled": str(cur.get("mcp.enabled", "false")).lower() == "true",
        "mode": (cur.get("mcp.mode") or "read").lower(),
        "share_ttl_hours": int(cur.get("mcp.share_ttl_hours") or 24),
    }


@router.post("/mcp-token")
async def mint_mcp_token(db: AsyncSession = Depends(get_db),
                         user: Optional[User] = Depends(current_user_optional)) -> Dict[str, Any]:
    """Erzeugt ein langlebiges JWT (10 Jahre) für den MCP-Client. Der MCP-Server reicht
    es als Bearer an die normale /api durch → ACL/Sichtbarkeit gelten unverändert.
    Wird einmalig im Klartext zurückgegeben (nicht gespeichert)."""
    u = await _resolve_user(user, db)
    if not u:
        raise HTTPException(400, "Kein Benutzerkonto vorhanden.")
    token = create_access_token(subject=str(u.id), expires_delta=timedelta(days=3650))
    return {"token": token, "user": u.email, "expires_days": 3650}
