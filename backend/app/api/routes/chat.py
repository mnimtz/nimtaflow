"""Conversational assistant endpoint — chat over the photo library."""
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.auth_guard import current_user_optional
from app.services.settings_loader import load_settings
from app.services import chat as chat_svc

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatMsg(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: List[ChatMsg] = []
    provider: Optional[str] = None   # "gemini" | "local" — overrides chat.provider
    # IDs des letzten Suchergebnisses des Frontends. Ermöglicht "davon nur
    # Videos", "welche davon zeigen Anja" etc. — Chat filtert dann in diesem
    # Set statt frisch zu suchen. Ohne dieses Feld war der Kontext-Modus im
    # Chat-Service totes Code-Pfad.
    context_ids: Optional[List[int]] = None


@router.get("/status")
async def chat_status(db: AsyncSession = Depends(get_db)):
    s = await load_settings(db)
    return {
        "provider": (s.get("chat.provider") or "gemini").lower(),
        # chat-specific key OR the shared image-AI key (matches chat.py's fallback).
        "gemini_ready": bool((s.get("chat.gemini.api_key") or s.get("ai.gemini.api_key") or "").strip()),
        "chat_enabled": (s.get("features.chat") or "true").lower() != "false",
    }


@router.post("")
async def chat(body: ChatRequest, db: AsyncSession = Depends(get_db),
               user=Depends(current_user_optional)):
    s = await load_settings(db)
    hist = [{"role": m.role, "content": m.content} for m in body.history]
    return await chat_svc.chat(body.message, hist, s, db, provider=body.provider,
                                user=user, context_ids=body.context_ids)
