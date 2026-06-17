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


_EMBEDDER = None


def _get_embedder():
    """Cached local e5 text embedder. LocalVLMProvider.embed_text uses
    sentence-transformers (independent of the VLM, which is never loaded here), so
    this is cheap and works on any host. Used for ALL embeddings for vector-space
    consistency — see AIManager.embed_text."""
    global _EMBEDDER
    if _EMBEDDER is None:
        from .local_vlm import LocalVLMProvider
        _EMBEDDER = LocalVLMProvider("florence2-base")  # model arg unused for embeddings
    return _EMBEDDER


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

    async def generate_tags(self, image: Image.Image, language: str = "de", prompt: Optional[str] = None,
                            caption: Optional[str] = None) -> tuple[List[str], str]:
        provider = await self._get_active()
        if not provider:
            return [], "none"
        tags = await provider.generate_tags(image, language, prompt, caption)
        return tags, provider.label

    async def describe_and_tag(self, image: Image.Image, language: str = "de",
                               desc_prompt: Optional[str] = None,
                               tag_prompt: Optional[str] = None) -> tuple[str, List[str], str]:
        """Description + tags in a SINGLE provider call where supported (Gemini) to
        halve image-input tokens; falls back to two calls for providers without a
        combined method (local VLMs). Returns (description, tags, provider_label)."""
        provider = await self._get_active()
        if not provider:
            return "", [], "none"
        combined = getattr(provider, "describe_and_tag", None)
        if combined is not None:
            desc, tags = await combined(image, language, desc_prompt, tag_prompt)
            return desc, tags, provider.label
        desc = await provider.describe_image(image, language, desc_prompt)
        tags = await provider.generate_tags(image, language, tag_prompt, caption=desc)
        return desc, tags, provider.label

    async def embed_text(self, text: str) -> tuple[Optional[List[float]], str]:
        # Embeddings use the ACTIVE provider. With Gemini this is text-embedding-004
        # (a free network call) — no local e5 model on the server, which is what
        # overloaded the small box before. Photos AND the search query both embed via
        # the same provider, so the vector space stays consistent (re-embed existing
        # photos once after switching — see reembed_descriptions_task).
        if not (text or "").strip():
            return None, "none"
        provider = await self._get_active()
        if not provider:
            return None, "none"
        try:
            embedding = await provider.embed_text(text)
            return (embedding or None), provider.label
        except Exception:
            return None, "none"
