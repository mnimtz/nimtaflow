import base64
import io
import time
from typing import List, Optional
from PIL import Image
import httpx
from .base import AIProvider, DetectedFace


LANG_PROMPTS = {
    "de": ("Beschreibe dieses Foto sachlich und ausführlich auf Deutsch in 4-6 Sätzen. "
           "Nenne konkret: die Personen (Anzahl, ungefähres Alter, Kleidung, Tätigkeit), die "
           "wichtigsten Objekte, den Ort bzw. Hintergrund und die Bildsituation. Verwende KEINE "
           "wertenden oder gefühlsbetonten Adjektive (kein 'süß', 'niedlich', 'idyllisch'). "
           "Beginne direkt mit der Beschreibung."),
    "en": ("Describe this photo factually and in detail in English in 4-6 sentences. State "
           "concretely: the people (count, approximate age, clothing, activity), the main "
           "objects, the place/background and the situation. Use NO subjective or emotional "
           "adjectives (no 'cute', 'adorable', 'idyllic'). Start directly with the description."),
    "fr": ("Décris cette photo de manière factuelle et détaillée en français en 4-6 phrases. "
           "Indique concrètement : les personnes (nombre, âge approximatif, vêtements, activité), "
           "les objets principaux, le lieu/l'arrière-plan et la situation. N'utilise AUCUN "
           "adjectif subjectif ou émotionnel. Commence directement par la description."),
}

TAG_PROMPTS = {
    "de": ("Nenne 20 bis 30 konkrete, sichtbare Schlagwörter auf Deutsch zu diesem Foto: "
           "Personen, Objekte, Kleidung, Farben, Ort, Tätigkeit, Anlass. Nur eine kommagetrennte "
           "Liste in Kleinbuchstaben, ausschließlich deutsche Begriffe. Keine Gefühle oder "
           "Wertungen, keine Erklärungen, keine Dopplungen."),
    "en": ("List 20 to 30 concrete, visible keywords in English for this photo: people, objects, "
           "clothing, colors, place, activity, occasion. Only a comma-separated lowercase list, "
           "only English terms, no feelings or judgements, no explanations, no duplicates."),
    "fr": ("Donne 20 à 30 mots-clés concrets et visibles en français pour cette photo : personnes, "
           "objets, vêtements, couleurs, lieu, activité, occasion. Uniquement une liste minuscule "
           "séparée par des virgules, sans émotions ni jugements, sans explications ni doublons."),
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

    @property
    def label(self) -> str:
        return f"gemini:{self.model}"

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

    async def generate_tags(self, image: Image.Image, language: str = "de", prompt: Optional[str] = None,
                            caption: Optional[str] = None) -> List[str]:
        text = await self._generate(
            _image_to_b64(image),
            prompt or TAG_PROMPTS.get(language, TAG_PROMPTS["de"]),
        )
        # de-dupe (keep order), lowercase
        seen, out = set(), []
        for t in (x.strip().lower() for x in text.split(",")):
            if t and t not in seen:
                seen.add(t); out.append(t)
        return out

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
