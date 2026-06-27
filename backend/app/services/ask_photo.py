"""Frag-das-Foto — ask a free-text question about a single photo via a VLM.

Reuses the AI provider manager: the question is passed as the describe prompt =
visual question answering, so it works across the same local + cloud models as
photo descriptions.

Model choice (per the project rule): provider is selectable. Default LOCAL
(Ollama on the M3 / in-process) — privacy-preserving. Cloud (Gemini) is opt-in
and DOES send the photo to the provider; the UI must say so. We deliberately
prefer HTTP providers (Ollama/Gemini) in the request path and avoid loading a
heavy in-process model in the API container.
"""
import os
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.photo import Photo


def _ask_settings(settings: dict, provider: Optional[str]) -> dict:
    """Overlay an ask-specific provider onto the ai.* keys (like build_video_settings).
    provider: auto (use configured) | local | ollama | gemini | cloud."""
    p = (provider or settings.get("ask.provider") or "auto").strip().lower()
    out = dict(settings)
    # The Gemini key is often only stored under chat.gemini.* — mirror it so the
    # AIManager (which reads ai.gemini.*) can use it for VQA.
    if not out.get("ai.gemini.api_key") and out.get("chat.gemini.api_key"):
        out["ai.gemini.api_key"] = out["chat.gemini.api_key"]
        if out.get("chat.gemini.model"):
            out.setdefault("ai.gemini.model", out["chat.gemini.model"])
    if p in ("", "auto", "same"):
        return out
    if p in ("gemini", "cloud"):
        out["ai.provider"] = "gemini"
    elif p in ("local", "ollama"):
        # Prefer the local Ollama (e.g. the M3) — keeps it off the API box and fully
        # on-device. Fall back to in-process only if no Ollama URL is configured.
        out["ai.provider"] = "ollama" if settings.get("ai.ollama.url") else "local"
    return out


async def ask_photo(db: AsyncSession, photo_id: int, question: str,
                    settings: dict, provider: Optional[str] = None) -> dict:
    q = (question or "").strip()
    if not q:
        return {"answer": "", "provider": "none", "error": "empty"}
    photo = await db.get(Photo, photo_id)
    if not photo:
        return {"answer": "", "provider": "none", "error": "not_found"}
    path = photo.thumb_large or photo.thumb_medium or photo.thumb_small or photo.path
    if not path or not os.path.exists(path):
        return {"answer": "", "provider": "none", "error": "no_image"}
    try:
        from PIL import Image
        img = Image.open(path).convert("RGB")
    except Exception:
        return {"answer": "", "provider": "none", "error": "image_load"}
    prompt = ("Beantworte die folgende Frage zu diesem Foto kurz und konkret auf Deutsch. "
              "Wenn die Antwort nicht sicher erkennbar ist, sage das ehrlich.\nFrage: " + q)
    try:
        from app.services.ai.manager import AIManager
        mgr = AIManager(_ask_settings(settings, provider))
        answer, label = await mgr.describe_image(img, "de", prompt)
    except Exception as e:
        return {"answer": "", "provider": "none", "error": str(e)[:160]}
    if not (answer or "").strip():
        # Be honest + actionable instead of an empty reply. Never silently switch a
        # "local" request to the cloud (privacy) — tell the user how to enable it.
        hint = ("Lokales Modell lieferte keine Antwort. Konfiguriere unter "
                "Einstellungen ein lokales Vision-Modell (Ollama) — oder wähle „Cloud".")
        if label.startswith(("gemini", "ollama")):
            hint = "Das Modell konnte dazu nichts sagen. Formuliere die Frage anders."
        return {"answer": "", "provider": label, "error": hint}
    return {"answer": answer.strip(), "provider": label}
