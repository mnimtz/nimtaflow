import base64
import io
import time
from typing import List
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

    async def describe_image(self, image: Image.Image, language: str = "de") -> str:
        prompt = LANG_PROMPTS.get(language, LANG_PROMPTS["de"])
        b64 = _image_to_b64(image)
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self._base}/models/{self.model}:generateContent",
                params={"key": self.api_key},
                json={
                    "contents": [{"parts": [
                        {"inlineData": {"mimeType": "image/jpeg", "data": b64}},
                        {"text": prompt},
                    ]}]
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()

    async def generate_tags(self, image: Image.Image) -> List[str]:
        b64 = _image_to_b64(image)
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self._base}/models/{self.model}:generateContent",
                params={"key": self.api_key},
                json={
                    "contents": [{"parts": [
                        {"inlineData": {"mimeType": "image/jpeg", "data": b64}},
                        {"text": "List up to 15 descriptive tags for this photo. Return only a comma-separated list, no explanations."},
                    ]}]
                },
            )
            resp.raise_for_status()
            text = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
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
            return resp.json()["embedding"]["values"]

    async def is_available(self) -> bool:
        try:
            await self.embed_text("test")
            return True
        except Exception:
            return False
