"""
AI Provider Manager — loads provider based on DB settings, supports fallback chain.
"""
from typing import Optional, List
from PIL import Image
from .base import AIProvider, AIResult, DetectedFace
from .gemini import GeminiProvider
from .ollama import OllamaProvider


def build_video_settings(settings: dict) -> dict:
    """Map the separate `video.*` AI settings onto the `ai.*` keys AIManager
    understands, so videos can use a different provider than photos.

    video.ai_provider: same | ollama | gemini | moondream
      - same      → use the photo provider unchanged
      - ollama    → Ollama at video.ollama_url with video.ollama_model
      - moondream → Ollama serving the 'moondream' model (small/fast, local)
      - gemini    → Gemini (reuses the photo Gemini key)
    """
    vp = (settings.get("video.ai_provider") or "same").strip()
    if vp in ("", "same"):
        return settings
    out = dict(settings)  # keep API keys etc.
    if vp == "gemini":
        out["ai.provider"] = "gemini"
    elif vp == "local":
        out["ai.provider"] = "local"
        out["ai.local.model"] = settings.get("video.local.model") or settings.get("ai.local.model", "florence2-base")
    elif vp in ("ollama", "moondream"):
        out["ai.provider"] = "ollama"
        out["ai.ollama.url"] = settings.get("video.ollama_url") or settings.get("ai.ollama.url", "http://localhost:11434")
        out["ai.ollama.vision_model"] = (
            "moondream" if vp == "moondream"
            else (settings.get("video.ollama_model") or settings.get("ai.ollama.vision_model", "llava:7b"))
        )
    return out


class AIManager:
    def __init__(self, settings: dict):
        self._settings = settings
        self._providers: List[AIProvider] = []
        self._build_providers()

    def _build_providers(self):
        s = self._settings
        # Primary
        provider_name = s.get("ai.provider", "none")
        if provider_name == "gemini" and s.get("ai.gemini.api_key"):
            self._providers.append(GeminiProvider(
                api_key=s["ai.gemini.api_key"],
                model=s.get("ai.gemini.model", "gemini-2.5-flash"),
                embed_model=s.get("ai.gemini.embed_model", "text-embedding-004"),
            ))
        elif provider_name == "ollama":
            self._providers.append(OllamaProvider(
                base_url=s.get("ai.ollama.url", "http://localhost:11434"),
                vision_model=s.get("ai.ollama.vision_model", "llava:7b"),
                embed_model=s.get("ai.ollama.embed_model", "nomic-embed-text"),
            ))
        elif provider_name == "local":
            from .local_vlm import LocalVLMProvider
            self._providers.append(LocalVLMProvider(
                model_key=s.get("ai.local.model", "florence2-base"),
            ))

        # Fallback Ollama (only if explicitly configured and not the primary)
        fallback_ollama = s.get("ai.ollama.url")
        if fallback_ollama and provider_name not in ("ollama", "local"):
            self._providers.append(OllamaProvider(base_url=fallback_ollama))

    async def _get_active(self) -> Optional[AIProvider]:
        for p in self._providers:
            if await p.is_available():
                return p
        return None

    async def describe_image(self, image: Image.Image, language: str = "de", prompt: Optional[str] = None) -> tuple[str, str]:
        provider = await self._get_active()
        if not provider:
            return "", "none"
        result = await provider.describe_image(image, language, prompt)
        return result, provider.label

    async def generate_tags(self, image: Image.Image, language: str = "de", prompt: Optional[str] = None) -> tuple[List[str], str]:
        provider = await self._get_active()
        if not provider:
            return [], "none"
        tags = await provider.generate_tags(image, language, prompt)
        return tags, provider.label

    async def embed_text(self, text: str) -> tuple[Optional[List[float]], str]:
        provider = await self._get_active()
        if not provider:
            return None, "none"
        embedding = await provider.embed_text(text)
        return embedding, provider.name
