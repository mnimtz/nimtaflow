import base64
import io
import time
from typing import List, Optional
from PIL import Image
import httpx
from .base import AIProvider, DetectedFace


# Quality-first prompts (the user's explicit priority: do NOT shorten / cheap out
# on the AI answers). These are DEFAULTS only — the live run uses the richer custom
# `settings.ai.prompt.image` / `ai.prompt.tags`. The cost win comes purely from the
# single-call path below (describe_and_tag → image uploaded ONCE, not twice), which
# does not touch answer quality.
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
    "de": ("20 bis 30 konkrete, sichtbare Schlagwörter auf Deutsch (Personen, Objekte, Kleidung, "
           "Farben, Ort, Tätigkeit, Anlass), kommagetrennt in Kleinbuchstaben, ausschließlich "
           "deutsche Begriffe, keine Wertungen, keine Erklärungen, keine Dopplungen"),
    "en": ("20 to 30 concrete, visible English keywords (people, objects, clothing, colors, place, "
           "activity, occasion), comma-separated lowercase, only English terms, no feelings or "
           "judgements, no explanations, no duplicates"),
    "fr": ("20 à 30 mots-clés concrets et visibles en français (personnes, objets, vêtements, couleurs, "
           "lieu, activité, occasion), séparés par des virgules en minuscules, sans émotions ni "
           "jugements, sans explications ni doublons"),
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
        # Shorter timeout + fewer in-task retries so a Gemini outage frees the
        # worker slot quickly; the beat retry-queue re-attempts later (no photo lost).
        async with httpx.AsyncClient(timeout=25) as client:
            for attempt in range(3):
                try:
                    resp = await client.post(
                        f"{self._base}/models/{self.model}:generateContent",
                        params={"key": self.api_key}, json=payload,
                    )
                    if resp.status_code in (429, 500, 503) and attempt < 2:
                        await asyncio.sleep(2 ** attempt)  # 1,2,4s backoff
                        continue
                    resp.raise_for_status()
                    return self._extract_text(resp.json())
                except httpx.HTTPStatusError as e:
                    last_exc = e
                    if e.response.status_code in (429, 500, 503) and attempt < 2:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    raise
        if last_exc:
            raise last_exc
        return ""

    @staticmethod
    def _parse_tags(text: str) -> List[str]:
        """Comma/newline/semicolon-separated → de-duped lowercase list, bullets stripped."""
        import re
        seen, out = set(), []
        for raw in re.split(r"[,\n;]", text or ""):
            t = raw.strip().lstrip("-•*").strip().lower()
            if t and t not in seen:
                seen.add(t); out.append(t)
        return out

    @staticmethod
    def _split_desc_tags(raw: str) -> tuple:
        """Split a combined 'description … TAGS: a, b, c' response into (desc, [tags])."""
        import re
        if not raw:
            return "", []
        parts = re.split(r"(?im)^[\s>*\-]*tags\s*:\s*", raw, maxsplit=1)
        desc = parts[0].strip()
        tags = GeminiProvider._parse_tags(parts[1]) if len(parts) > 1 else []
        return desc, tags

    async def describe_image(self, image: Image.Image, language: str = "de", prompt: Optional[str] = None) -> str:
        prompt = prompt or LANG_PROMPTS.get(language, LANG_PROMPTS["de"])
        return await self._generate(_image_to_b64(image), prompt)

    async def generate_tags(self, image: Image.Image, language: str = "de", prompt: Optional[str] = None,
                            caption: Optional[str] = None) -> List[str]:
        frag = prompt or TAG_PROMPTS.get(language, TAG_PROMPTS["de"])
        text = await self._generate(_image_to_b64(image), f"Nenne {frag}.")
        return self._parse_tags(text)

    async def describe_and_tag(self, image: Image.Image, language: str = "de",
                               desc_prompt: Optional[str] = None,
                               tag_prompt: Optional[str] = None) -> tuple:
        """ONE vision call returns BOTH a description and tags — halves the image
        input tokens vs. separate describe + tag calls (cost + a Gemini roundtrip
        saved). Response: '<description>\\nTAGS: tag1, tag2, …'."""
        dp = desc_prompt or LANG_PROMPTS.get(language, LANG_PROMPTS["de"])
        tp = tag_prompt or TAG_PROMPTS.get(language, TAG_PROMPTS["de"])
        combined = f"{dp}\n\nGib anschließend in einer NEUEN Zeile, beginnend mit 'TAGS:', {tp}."
        raw = await self._generate(_image_to_b64(image), combined)
        return self._split_desc_tags(raw)

    async def detect_faces(self, image: Image.Image) -> List[DetectedFace]:
        # Gemini doesn't return bounding boxes — use local model for faces
        return []

    async def embed_text(self, text: str) -> List[float]:
        # outputDimensionality=768 fits the pgvector column. gemini-embedding-001 is
        # Matryoshka-trained, so 768 keeps near-full quality (and text-embedding-004
        # accepts it too). Avoids returning 3072 dims that we'd just truncate.
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{self._base}/models/{self.embed_model}:embedContent",
                params={"key": self.api_key},
                json={"content": {"parts": [{"text": text}]}, "outputDimensionality": 768},
            )
            resp.raise_for_status()
            return (resp.json().get("embedding") or {}).get("values") or []

    async def describe_video(self, video_path: str, language: str = "de",
                             desc_prompt: Optional[str] = None,
                             tag_prompt: Optional[str] = None,
                             mime_type: str = "video/mp4") -> tuple:
        """Uploads the local web-mp4 via the Gemini File API and asks for
        description+tags in ONE call. Returns (description, [tags]).

        Fallback für Videos, bei denen das lokale VLM (Qwen3-VL/MLX) nur
        „degenerate output" liefert — meist 3GP-Handys, JGA-Nachtaufnahmen,
        alte MOVs, bei denen das Model kein klares Motiv findet. Gemini kommt
        über die eigene Video-Pipeline meist zurecht.
        """
        import asyncio
        # 1) Upload the file — Gemini's simple `uploadType=media` accepts binary body.
        #    Response contains .file.name (e.g. "files/abc123") and .file.state.
        upload_base = "https://generativelanguage.googleapis.com/upload/v1beta/files"
        try:
            with open(video_path, "rb") as f:
                data = f.read()
        except Exception as e:
            raise RuntimeError(f"video read failed: {e}")
        headers = {
            "X-Goog-Upload-Command": "start, upload, finalize",
            "X-Goog-Upload-Header-Content-Length": str(len(data)),
            "X-Goog-Upload-Header-Content-Type": mime_type,
            "Content-Type": mime_type,
        }
        async with httpx.AsyncClient(timeout=180) as client:
            r = await client.post(
                upload_base, params={"key": self.api_key},
                headers=headers, content=data,
            )
            r.raise_for_status()
            j = r.json()
            file_uri = j.get("file", {}).get("uri") or j.get("uri")
            file_name = j.get("file", {}).get("name") or j.get("name")
            state = (j.get("file", {}).get("state") or j.get("state") or "").upper()
            if not file_uri or not file_name:
                raise RuntimeError(f"unexpected upload response: {str(j)[:200]}")

            # 2) Poll bis der File ACTIVE ist (Gemini transkodiert Videos server-seitig).
            for _ in range(60):
                if state == "ACTIVE":
                    break
                if state == "FAILED":
                    raise RuntimeError(f"gemini file processing FAILED for {file_name}")
                await asyncio.sleep(2)
                fr = await client.get(f"https://generativelanguage.googleapis.com/v1beta/{file_name}",
                                      params={"key": self.api_key})
                fr.raise_for_status()
                fj = fr.json()
                state = (fj.get("state") or "").upper()
                file_uri = fj.get("uri", file_uri)
            if state != "ACTIVE":
                raise RuntimeError(f"gemini file never became ACTIVE (state={state})")

            # 3) generateContent mit file_data-Referenz
            dp = desc_prompt or LANG_PROMPTS.get(language, LANG_PROMPTS["de"])
            tp = tag_prompt or TAG_PROMPTS.get(language, TAG_PROMPTS["de"])
            combined = f"{dp}\n\nGib anschließend in einer NEUEN Zeile, beginnend mit 'TAGS:', {tp}."
            payload = {"contents": [{"parts": [
                {"fileData": {"mimeType": mime_type, "fileUri": file_uri}},
                {"text": combined},
            ]}]}
            gr = await client.post(
                f"{self._base}/models/{self.model}:generateContent",
                params={"key": self.api_key}, json=payload,
            )
            gr.raise_for_status()
            raw = self._extract_text(gr.json())

            # 4) Aufräumen — Datei wird sonst 48h auf Google gehostet
            try:
                await client.delete(f"https://generativelanguage.googleapis.com/v1beta/{file_name}",
                                    params={"key": self.api_key})
            except Exception:
                pass

        return self._split_desc_tags(raw)

    async def is_available(self) -> bool:
        try:
            await self.embed_text("test")
            return True
        except Exception:
            return False
