import base64
import io
import time
from typing import List, Optional
from PIL import Image
import httpx
from .base import AIProvider, DetectedFace


LANG_PROMPTS = {
    "de": "Beschreibe dieses Foto auf Deutsch in 2-3 Sätzen. Beschreibe Personen, Orte, Aktivitäten und Stimmung.",
    "en": "Describe this photo in English in 2-3 sentences. Describe people, places, activities and mood.",
    "fr": "Décris cette photo en français en 2-3 phrases. Décris les personnes, lieux, activités et l'ambiance.",
}


def _image_to_b64(image: Image.Image) -> str:
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


class GeminiProvider(AIProvider):
    name = "gemini"

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash", embed_model: str = "text-embedding-004"):
        self.api_key = api_key
        self.model = model
        self.embed_model = embed_model
        self._base = "https://generativelanguage.googleapis.com/v1beta"

    @staticmethod
    def _extract_text(data: dict) -> str:
        """Safely pull the text out of a generateContent response.

        Returns "" when Gemini blocked the response or returned no content
        (finishReason SAFETY/RECITATION) instead of raising KeyError('content').
        """
        try:
            cand = (data.get("candidates") or [{}])[0]
            parts = (cand.get("content") or {}).get("parts") or []
            return "".join(p.get("text", "") for p in parts).strip()
        except (IndexError, AttributeError, TypeError):
            return ""

    async def _generate(self, b64: str, text_prompt: str) -> str:
        """POST a vision generateContent request with retry on transient 5xx/429."""
        import asyncio
        payload = {"contents": [{"parts": [
            {"inlineData": {"mimeType": "image/jpeg", "data": b64}},
            {"text": text_prompt},
        ]}]}
        last_exc = None
        async with httpx.AsyncClient(timeout=60) as client:
            for attempt in range(4):
                try:
                    resp = await client.post(
                        f"{self._base}/models/{self.model}:generateContent",
                        params={"key": self.api_key}, json=payload,
                    )
                    if resp.status_code in (429, 500, 503) and attempt < 3:
                        await asyncio.sleep(2 ** attempt)  # 1,2,4s backoff
                        continue
                    resp.raise_for_status()
                    return self._extract_text(resp.json())
                except httpx.HTTPStatusError as e:
                    last_exc = e
                    if e.response.status_code in (429, 500, 503) and attempt < 3:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    raise
        if last_exc:
            raise last_exc
        return ""

    async def describe_image(self, image: Image.Image, language: str = "de", prompt: Optional[str] = None) -> str:
        prompt = prompt or LANG_PROMPTS.get(language, LANG_PROMPTS["de"])
        return await self._generate(_image_to_b64(image), prompt)

    async def generate_tags(self, image: Image.Image) -> List[str]:
        text = await self._generate(
            _image_to_b64(image),
            "List up to 15 descriptive tags for this photo. Return only a comma-separated list, no explanations.",
        )
        return [t.strip().lower() for t in text.split(",") if t.strip()]

    async def detect_faces(self, image: Image.Image) -> List[DetectedFace]:
        # Gemini doesn't return bounding boxes — use local model for faces
        return []

    async def embed_text(self, text: str) -> List[float]:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{self._base}/models/{self.embed_model}:embedContent",
                params={"key": self.api_key},
                json={"content": {"parts": [{"text": text}]}},
            )
            resp.raise_for_status()
            return (resp.json().get("embedding") or {}).get("values") or []

    async def is_available(self) -> bool:
        try:
            await self.embed_text("test")
            return True
        except Exception:
            return False
