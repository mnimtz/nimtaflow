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


@router.get("/status")
async def chat_status(db: AsyncSession = Depends(get_db)):
    s = await load_settings(db)
    return {
        "provider": (s.get("chat.provider") or "gemini").lower(),
        "gemini_ready": bool((s.get("ai.gemini.api_key") or "").strip()),
    }


@router.post("")
async def chat(body: ChatRequest, db: AsyncSession = Depends(get_db),
               user=Depends(current_user_optional)):
    s = await load_settings(db)
    hist = [{"role": m.role, "content": m.content} for m in body.history]
    return await chat_svc.chat(body.message, hist, s, db, provider=body.provider, user=user)
