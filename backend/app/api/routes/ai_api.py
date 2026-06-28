"""AI provider utilities — model listing, health checks."""
import asyncio
import httpx
from typing import List, Optional
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/ai", tags=["ai"])

GEMINI_MODELS_URL = "https://generativelanguage.googleapis.com/v1beta/models"
OPENAI_MODELS_URL = "https://api.openai.com/v1/models"
AZURE_MODELS_URL = "https://{endpoint}.openai.azure.com/openai/models?api-version=2024-02-01"


class ModelInfo(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    supports_vision: bool = False
    supports_embedding: bool = False


@router.get("/models/gemini", response_model=List[ModelInfo])
async def list_gemini_models(api_key: str = Query(...)):
    """Fetch available Gemini models from Google API."""
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            r = await client.get(f"{GEMINI_MODELS_URL}?key={api_key}&pageSize=100")
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise HTTPException(e.response.status_code, f"Gemini API error: {e.response.text[:200]}")
        except httpx.RequestError as e:
            raise HTTPException(503, f"Cannot reach Gemini API: {e}")

    data = r.json().get("models", [])
    models = []
    for m in data:
        name = m.get("name", "")
        model_id = name.replace("models/", "")
        display = m.get("displayName", model_id)
        supported = m.get("supportedGenerationMethods", [])

        is_vision = "generateContent" in supported
        is_embed = "embedContent" in supported

        # Filter to useful models only
        if not any(x in supported for x in ["generateContent", "embedContent"]):
            continue

        models.append(ModelInfo(
            id=model_id,
            name=display,
            description=m.get("description", "")[:120],
            supports_vision=is_vision,
            supports_embedding=is_embed,
        ))

    models.sort(key=lambda m: (0 if "flash" in m.id else 1 if "pro" in m.id else 2, m.id))
    return models


@router.get("/models/openai", response_model=List[ModelInfo])
async def list_openai_models(api_key: str = Query(...), base_url: str = Query("https://api.openai.com/v1")):
    """Fetch available OpenAI-compatible models. Works for OpenAI and Azure OpenAI."""
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            r = await client.get(
                f"{base_url.rstrip('/')}/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise HTTPException(e.response.status_code, f"API error: {e.response.text[:200]}")
        except httpx.RequestError as e:
            raise HTTPException(503, f"Cannot reach API: {e}")

    data = r.json().get("data", [])
    models = []
    VISION_MODELS = {"gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-4-vision", "o1", "o3"}
    EMBED_MODELS = {"text-embedding", "embed"}

    for m in data:
        mid = m.get("id", "")
        is_vision = any(v in mid for v in VISION_MODELS) or "vision" in mid
        is_embed = any(e in mid for e in EMBED_MODELS)

        # Filter out fine-tuned, whisper, tts, dall-e, babbage, davinci legacy
        if any(x in mid for x in ["whisper", "tts", "dall-e", "babbage", "davinci", "curie", "ada-0"]):
            continue

        models.append(ModelInfo(id=mid, name=mid, supports_vision=is_vision, supports_embedding=is_embed))

    models.sort(key=lambda m: (0 if "gpt-4o" in m.id else 1 if "gpt-4" in m.id else 2 if "gpt-3" in m.id else 3, m.id))
    return models


@router.get("/models/ollama", response_model=List[ModelInfo])
async def list_ollama_models(base_url: str = Query("http://localhost:11434")):
    """List locally available Ollama models."""
    async with httpx.AsyncClient(timeout=8) as client:
        try:
            r = await client.get(f"{base_url.rstrip('/')}/api/tags")
            r.raise_for_status()
        except Exception as e:
            raise HTTPException(503, f"Cannot reach Ollama at {base_url}: {e}")

    VISION_HINTS = {"llava", "bakllava", "moondream", "minicpm", "cogvlm", "internvl", "phi3-vision"}
    EMBED_HINTS = {"embed", "nomic", "mxbai", "snowflake", "all-minilm"}

    models = []
    for m in r.json().get("models", []):
        mid = m.get("name", "")
        base = mid.split(":")[0].lower()
        is_vision = any(h in base for h in VISION_HINTS)
        is_embed = any(h in base for h in EMBED_HINTS)
        size = m.get("size", 0)
        size_gb = f"{size / 1e9:.1f}GB" if size else ""
        models.append(ModelInfo(
            id=mid,
            name=mid,
            description=size_gb,
            supports_vision=is_vision,
            supports_embedding=is_embed,
        ))
    return models


@router.get("/health/{provider}")
async def check_provider_health(provider: str,
                                 api_key: Optional[str] = Query(None),
                                 base_url: Optional[str] = Query(None)):
    """Quick reachability check for a provider."""
    if provider == "ollama":
        url = f"{(base_url or 'http://localhost:11434').rstrip('/')}/api/tags"
        try:
            async with httpx.AsyncClient(timeout=5) as c:
                r = await c.get(url)
            return {"ok": r.status_code == 200, "status": r.status_code}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    if provider == "gemini":
        if not api_key:
            raise HTTPException(400, "api_key required")
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}&pageSize=1"
        try:
            async with httpx.AsyncClient(timeout=6) as c:
                r = await c.get(url)
            return {"ok": r.status_code == 200, "status": r.status_code}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    if provider in ("openai", "azure"):
        if not api_key:
            raise HTTPException(400, "api_key required")
        url = f"{(base_url or 'https://api.openai.com/v1').rstrip('/')}/models"
        try:
            async with httpx.AsyncClient(timeout=6) as c:
                r = await c.get(url, headers={"Authorization": f"Bearer {api_key}"})
            return {"ok": r.status_code == 200, "status": r.status_code}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    raise HTTPException(400, f"Unknown provider: {provider}")
