import base64
import io
from typing import List, Optional
import httpx
from PIL import Image
from .base import AIProvider, DetectedFace


class OllamaProvider(AIProvider):
    name = "ollama"

    def __init__(self, base_url: str = "http://localhost:11434", vision_model: str = "llava:7b", embed_model: str = "nomic-embed-text"):
        self.base_url = base_url.rstrip("/")
        self.vision_model = vision_model
        self.embed_model = embed_model

    @property
    def label(self) -> str:
        return f"ollama:{self.vision_model}"

    def _image_to_b64(self, image: Image.Image) -> str:
        buf = io.BytesIO()
        image.save(buf, format="JPEG", quality=85)
        return base64.b64encode(buf.getvalue()).decode()

    async def describe_image(self, image: Image.Image, language: str = "de", prompt: Optional[str] = None) -> str:
        lang_map = {"de": "German", "en": "English", "fr": "French"}
        lang = lang_map.get(language, "German")
        the_prompt = prompt or f"Describe this photo in {lang} in 2-3 sentences. Describe people, places, activities and mood."
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.vision_model,
                    "prompt": the_prompt,
                    "images": [self._image_to_b64(image)],
                    "stream": False,
                },
            )
            resp.raise_for_status()
            return resp.json()["response"].strip()

    async def generate_tags(self, image: Image.Image, language: str = "de", prompt: Optional[str] = None) -> List[str]:
        lang = {"de": "auf Deutsch", "en": "in English", "fr": "en français"}.get(language, "auf Deutsch")
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.vision_model,
                    "prompt": prompt or f"Liste bis zu 15 beschreibende Schlagwörter {lang} für dieses Foto. Nur eine kommagetrennte Liste.",
                    "images": [self._image_to_b64(image)],
                    "stream": False,
                },
            )
            resp.raise_for_status()
            text = resp.json()["response"].strip()
            return [t.strip().lower() for t in text.split(",") if t.strip()]

    async def detect_faces(self, image: Image.Image) -> List[DetectedFace]:
        return []

    async def embed_text(self, text: str) -> List[float]:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.base_url}/api/embed",
                json={"model": self.embed_model, "input": text},
            )
            resp.raise_for_status()
            return resp.json()["embeddings"][0]

    async def list_models(self) -> List[str]:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{self.base_url}/api/tags")
            resp.raise_for_status()
            return [m["name"] for m in resp.json().get("models", [])]

    async def is_available(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
                return resp.status_code == 200
        except Exception:
            return False
